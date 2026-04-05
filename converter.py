"""
converter.py — FFmpeg-based file conversion logic running in a QThread.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import re
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal


# ── FFmpeg detection ──────────────────────────────────────────────────────────

def find_ffmpeg() -> str | None:
    """Return the path to ffmpeg, or None if unavailable."""
    return shutil.which("ffmpeg")


def ffmpeg_available() -> bool:
    return find_ffmpeg() is not None


# ── File-type classification ──────────────────────────────────────────────────

IMAGE_EXTENSIONS = {".webp", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".gif", ".avif"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v", ".ts"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".aac", ".ogg", ".flac", ".m4a", ".opus"}


def classify_file(path: Path) -> str:
    """Return 'image', 'video', 'audio', or 'unknown'."""
    ext = path.suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    return "unknown"


def suggested_formats(file_type: str) -> list[str]:
    """Return suggested output formats for a given file type."""
    if file_type == "image":
        return ["jpg", "png", "webp", "bmp"]
    if file_type == "video":
        return ["mp4", "mp3", "mkv", "avi", "webm", "gif"]
    if file_type == "audio":
        return ["mp3", "wav", "aac", "flac", "ogg"]
    return []


# ── Duration helper ───────────────────────────────────────────────────────────

def get_duration_seconds(path: Path) -> float | None:
    """Use ffprobe to get the duration of a media file in seconds."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                str(path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        import json
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception:  # pylint: disable=broad-except
        return None


# ── Conversion Worker ─────────────────────────────────────────────────────────

class ConvertWorker(QThread):
    """QThread that converts a file using FFmpeg."""

    progress  = pyqtSignal(int)    # 0-100
    status    = pyqtSignal(str)
    finished  = pyqtSignal(str)    # output file path
    error     = pyqtSignal(str)

    def __init__(
        self,
        input_path:  Path,
        output_fmt:  str,         # e.g. "mp4", "mp3", "jpg"
        output_dir:  Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.input_path = Path(input_path)
        self.output_fmt = output_fmt.lower().lstrip(".")
        self.output_dir = Path(output_dir) if output_dir else self.input_path.parent
        self._cancelled = False
        self._proc: subprocess.Popen | None = None

    # ------------------------------------------------------------------
    def cancel(self) -> None:
        self._cancelled = True
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    # ------------------------------------------------------------------
    def _build_output_path(self) -> Path:
        stem = self.input_path.stem
        out  = self.output_dir / f"{stem}_converted.{self.output_fmt}"
        # Avoid clobbering
        counter = 1
        while out.exists():
            out = self.output_dir / f"{stem}_converted_{counter}.{self.output_fmt}"
            counter += 1
        return out

    # ------------------------------------------------------------------
    def _build_ffmpeg_cmd(self, output_path: Path) -> list[str]:
        ffmpeg = find_ffmpeg()
        cmd = [ffmpeg, "-y", "-i", str(self.input_path)]

        file_type = classify_file(self.input_path)
        fmt = self.output_fmt

        if file_type == "image":
            if fmt in ("jpg", "jpeg"):
                cmd += ["-q:v", "2"]
            elif fmt == "png":
                cmd += ["-compression_level", "6"]
            elif fmt == "webp":
                cmd += ["-q:v", "80"]

        elif file_type == "video":
            if fmt == "mp4":
                cmd += ["-c:v", "libx264", "-crf", "23",
                        "-preset", "fast", "-c:a", "aac", "-b:a", "192k"]
            elif fmt == "mp3":
                cmd += ["-vn", "-c:a", "libmp3lame", "-b:a", "192k"]
            elif fmt == "mkv":
                cmd += ["-c:v", "copy", "-c:a", "copy"]
            elif fmt == "gif":
                # Two-pass palette GIF
                palette = str(output_path.with_suffix(".palette.png"))
                return [
                    ffmpeg, "-y", "-i", str(self.input_path),
                    "-vf", "fps=15,scale=480:-1:flags=lanczos,palettegen",
                    palette,
                    "&&",
                    ffmpeg, "-y", "-i", str(self.input_path), "-i", palette,
                    "-lavfi", "fps=15,scale=480:-1:flags=lanczos [x]; [x][1:v] paletteuse",
                    str(output_path),
                ]
            elif fmt == "webm":
                cmd += ["-c:v", "libvpx-vp9", "-crf", "30",
                        "-b:v", "0", "-c:a", "libopus"]
            else:
                cmd += ["-c:v", "copy", "-c:a", "copy"]

        elif file_type == "audio":
            if fmt == "mp3":
                cmd += ["-c:a", "libmp3lame", "-b:a", "192k"]
            elif fmt == "aac":
                cmd += ["-c:a", "aac", "-b:a", "192k"]
            elif fmt == "wav":
                cmd += ["-c:a", "pcm_s16le"]
            elif fmt == "flac":
                cmd += ["-c:a", "flac"]
            elif fmt == "ogg":
                cmd += ["-c:a", "libvorbis", "-q:a", "4"]
            else:
                cmd += ["-c:a", "copy"]

        cmd.append(str(output_path))
        return cmd

    # ------------------------------------------------------------------
    def run(self) -> None:
        if not ffmpeg_available():
            self.error.emit(
                "FFmpeg introuvable.\n"
                "Installez-le depuis https://ffmpeg.org/download.html\n"
                "et assurez-vous qu'il est dans votre PATH."
            )
            return

        if not self.input_path.exists():
            self.error.emit(f"Fichier source introuvable :\n{self.input_path}")
            return

        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self._build_output_path()
        cmd = self._build_ffmpeg_cmd(output_path)

        # GIF two-pass needs shell; run via shell=True
        use_shell = "&&" in cmd
        if use_shell:
            cmd_str = " ".join(f'"{c}"' if " " in c else c for c in cmd)
        
        self.status.emit(f"⚙  Conversion → .{self.output_fmt}…")
        self.progress.emit(5)

        # Get duration for progress tracking
        duration = get_duration_seconds(self.input_path)

        try:
            if use_shell:
                self._proc = subprocess.Popen(
                    cmd_str, shell=True,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    universal_newlines=True,
                )
            else:
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    universal_newlines=True,
                )

            time_re = re.compile(r"time=(\d+):(\d+):(\d+\.?\d*)")

            for line in self._proc.stdout:  # type: ignore[union-attr]
                if self._cancelled:
                    break
                m = time_re.search(line)
                if m and duration:
                    h, mn, s = float(m.group(1)), float(m.group(2)), float(m.group(3))
                    elapsed = h * 3600 + mn * 60 + s
                    pct = min(int(elapsed / duration * 95) + 5, 98)
                    self.progress.emit(pct)

            self._proc.wait()

            if self._cancelled:
                output_path.unlink(missing_ok=True)
                return

            if self._proc.returncode != 0:
                self.error.emit(
                    f"FFmpeg a retourné le code {self._proc.returncode}.\n"
                    "Vérifiez que le fichier source n'est pas corrompu."
                )
                return

            if not output_path.exists():
                self.error.emit("La conversion a échoué : fichier de sortie absent.")
                return

            self.progress.emit(100)
            self.finished.emit(str(output_path))

        except Exception as exc:  # pylint: disable=broad-except
            if not self._cancelled:
                self.error.emit(str(exc))
