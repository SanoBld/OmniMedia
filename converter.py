"""
converter.py — OmniMedia v4.5
New in v4.5: check_ffmpeg_capabilities() validates version and available
             codecs (H.265/HEVC, VP9, AV1) at startup.
             All errors now route through the 'omnimedia.converter' logger
             instead of silent except-pass blocks.
"""
from __future__ import annotations

import sys, os, shutil, subprocess, re, json
from pathlib import Path
from dataclasses import dataclass
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6.QtCore import QThread, pyqtSignal

from config_manager import cfg  # centralised settings
from app_logger import get_logger

logger = get_logger(__name__)


# ── FFmpeg helpers ────────────────────────────────────────────────────────────

def find_ffmpeg() -> str | None:
    """
    Locate the ffmpeg binary.
    Priority: 1) user setting  2) exe directory  3) system PATH
    """
    # 1. User-configured path
    user_path = cfg.ffmpeg_path
    if user_path and Path(user_path).is_file():
        return user_path

    # 2. Alongside the frozen executable
    exe_dir = Path(getattr(os, "frozen_path", Path(__file__).parent))
    candidate = exe_dir / "ffmpeg.exe"
    if candidate.exists():
        return str(candidate)

    # 3. System PATH
    return shutil.which("ffmpeg")


def find_ffprobe() -> str | None:
    """Same priority search as find_ffmpeg() but for ffprobe."""
    user_ffmpeg = cfg.ffmpeg_path
    if user_ffmpeg:
        probe = Path(user_ffmpeg).parent / "ffprobe.exe"
        if probe.exists():
            return str(probe)

    exe_dir = Path(getattr(os, "frozen_path", Path(__file__).parent))
    candidate = exe_dir / "ffprobe.exe"
    if candidate.exists():
        return str(candidate)

    return shutil.which("ffprobe")


def ffmpeg_available() -> bool:
    return find_ffmpeg() is not None


# ── FFmpeg capability check ───────────────────────────────────────────────────

FFMPEG_MIN_YEAR = 2021  # builds before this are considered too old

@dataclass
class FFmpegCapabilities:
    """Result of check_ffmpeg_capabilities()."""
    available   : bool
    version_str : str                    # e.g. "6.1.1"
    year        : int | None             # build year parsed from version output
    too_old     : bool                   # True if year < FFMPEG_MIN_YEAR
    codecs      : dict[str, bool]        # {"hevc": True, "vp9": True, "av1": False, …}
    warnings    : list[str]              # human-readable issues for the UI


def check_ffmpeg_capabilities() -> FFmpegCapabilities:
    """
    Run 'ffmpeg -version' and 'ffmpeg -codecs' to detect the installed
    version and whether key encoders (H.265/HEVC, VP9, AV1) are available.

    Returns an FFmpegCapabilities dataclass. Never raises — all errors are
    captured and surfaced as warnings in the result.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return FFmpegCapabilities(
            available=False, version_str="", year=None,
            too_old=False, codecs={},
            warnings=["FFmpeg not found. Conversion and compression will be disabled."],
        )

    version_str = ""
    year: int | None = None
    too_old = False
    codecs: dict[str, bool] = {}
    warnings: list[str] = []

    # Masquer la console sur Windows
    _no_win: dict = {}
    if sys.platform == "win32":
        _no_win["creationflags"] = 0x08000000  # CREATE_NO_WINDOW

    # ── 1. Version ────────────────────────────────────────────────────────────
    try:
        result = subprocess.run(
            [ffmpeg, "-version"],
            capture_output=True, text=True, timeout=8, **_no_win,
        )
        first_line = result.stdout.splitlines()[0] if result.stdout else ""
        m = re.search(r"version\s+([\d.N\-]+)", first_line)
        if m:
            version_str = m.group(1)
        year_m = re.search(r"2000-(\d{4})", result.stdout)
        if year_m:
            year = int(year_m.group(1))
            if year < FFMPEG_MIN_YEAR:
                too_old = True
                warnings.append(
                    f"FFmpeg {version_str} (build year ≈ {year}) is outdated. "
                    f"H.265 / AV1 encoding may not work correctly. "
                    f"Please upgrade to a build from {FFMPEG_MIN_YEAR} or later."
                )
        logger.info("FFmpeg version: %s (year %s)", version_str, year)
    except Exception as exc:
        logger.warning("Could not run 'ffmpeg -version': %s", exc)
        warnings.append(f"Could not determine FFmpeg version: {exc}")

    # ── 2. Codec availability ─────────────────────────────────────────────────
    CODEC_KEYS = {
        "hevc"       : "H.265 / HEVC encoding",
        "libx265"    : "H.265 (libx265)",
        "vp9"        : "VP9 (WebM)",
        "libvpx-vp9" : "VP9 (libvpx-vp9)",
        "av1"        : "AV1",
        "libaom-av1" : "AV1 (libaom)",
        "libsvtav1"  : "AV1 (SVT-AV1, fast)",
    }
    try:
        result = subprocess.run(
            [ffmpeg, "-codecs"],
            capture_output=True, text=True, timeout=10, **_no_win,
        )
        output = result.stdout.lower()
        for key in CODEC_KEYS:
            codecs[key] = key in output

        if not codecs.get("libx265") and not codecs.get("hevc"):
            warnings.append(
                "H.265 (HEVC) encoder not found in your FFmpeg build. "
                "The H.265 preset will fall back to H.264."
            )
        if not codecs.get("libvpx-vp9") and not codecs.get("vp9"):
            warnings.append("VP9 encoder not found — WebM output will fall back to VP8.")

        logger.debug("FFmpeg codecs detected: %s", {k: v for k, v in codecs.items() if v})
    except Exception as exc:
        logger.warning("Could not run 'ffmpeg -codecs': %s", exc)
        warnings.append(f"Could not query available codecs: {exc}")

    return FFmpegCapabilities(
        available=True,
        version_str=version_str,
        year=year,
        too_old=too_old,
        codecs=codecs,
        warnings=warnings,
    )


# ── File classification ───────────────────────────────────────────────────────

IMAGE_EXTENSIONS = {".webp", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".gif", ".avif"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v", ".ts"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".aac", ".ogg", ".flac", ".m4a", ".opus"}

# Emoji icons for each file type — used in the convert queue preview
TYPE_ICONS: dict[str, str] = {
    "image": "🖼",
    "video": "🎬",
    "audio": "🎵",
    "unknown": "❓",
}


def classify_file(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTENSIONS: return "image"
    if ext in VIDEO_EXTENSIONS: return "video"
    if ext in AUDIO_EXTENSIONS: return "audio"
    return "unknown"


def suggested_formats(file_type: str) -> list[str]:
    if file_type == "image": return ["jpg", "png", "webp", "bmp"]
    if file_type == "video": return ["mp4", "mp3", "mkv", "avi", "webm", "gif"]
    if file_type == "audio": return ["mp3", "wav", "aac", "flac", "ogg"]
    return []


# ── Media info (preview) ──────────────────────────────────────────────────────

@dataclass
class MediaInfo:
    """Lightweight metadata used for the conversion queue preview."""
    path     : Path
    file_type: str          # "image" | "video" | "audio" | "unknown"
    icon     : str          # emoji
    duration : float | None # seconds, None for images / on error


def _fmt_duration(seconds: float) -> str:
    """Format a duration in seconds as HH:MM:SS or MM:SS."""
    s = int(seconds)
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def get_media_info(path: Path) -> MediaInfo:
    """
    Return a MediaInfo for *path*.
    Uses ffprobe to extract duration for video/audio files.
    Falls back gracefully if ffprobe is unavailable.
    """
    file_type = classify_file(path)
    icon      = TYPE_ICONS.get(file_type, "❓")
    duration  = None

    if file_type in ("video", "audio"):
        ffprobe = find_ffprobe()
        if ffprobe:
            try:
                _nw: dict = {}
                if sys.platform == "win32":
                    _nw["creationflags"] = 0x08000000
                result = subprocess.run(
                    [
                        ffprobe, "-v", "quiet",
                        "-print_format", "json",
                        "-show_format", str(path),
                    ],
                    capture_output=True, text=True, timeout=8, **_nw,
                )
                data     = json.loads(result.stdout)
                duration = float(data["format"]["duration"])
            except Exception:
                logger.debug("ffprobe failed on %s", path, exc_info=True)

    return MediaInfo(path=path, file_type=file_type, icon=icon, duration=duration)


def format_media_info(info: MediaInfo) -> str:
    """
    Return a human-readable one-line description for the queue item label.
    Example: '🎬  clip.mp4  ·  3:42'
    """
    parts = [info.icon, f"  {info.path.name}"]
    if info.duration is not None:
        parts.append(f"  ·  {_fmt_duration(info.duration)}")
    return "".join(parts)


# ── Batch Video Compressor ────────────────────────────────────────────────────

# Target sizes (bytes) for common sharing platforms
COMPRESS_TARGETS: dict[str, int] = {
    "discord":   25 * 1024 * 1024,   # 25 MB
    "whatsapp":  16 * 1024 * 1024,   # 16 MB
    "email":     10 * 1024 * 1024,   # 10 MB
    "telegram": 100 * 1024 * 1024,   # 100 MB (Nitro-like)
}


def compute_target_bitrate(
    input_path: Path,
    target_bytes: int,
    audio_bitrate_kbps: int = 128,
) -> int | None:
    """
    Compute the video bitrate (kbps) needed so that the output file
    does not exceed *target_bytes*.

    Formula:  video_kbps = (target_bytes*8/1000 / duration_s) - audio_kbps
    Returns None if ffprobe is unavailable or the file has no video stream.
    """
    info = get_media_info(input_path)
    if info.duration is None or info.duration <= 0:
        return None

    total_kbps   = (target_bytes * 8) / (info.duration * 1000)
    video_kbps   = int(total_kbps - audio_bitrate_kbps)
    return max(video_kbps, 100)  # never go below 100 kbps


def build_compress_args(
    input_path: Path,
    target_key: str,
    audio_bitrate_kbps: int = 128,
) -> list[str]:
    """
    Return the FFmpeg argument list to compress *input_path* to the
    given *target_key* (e.g. "discord"), or an empty list on failure.
    If ffprobe cannot read the duration, falls back to an aggressive CRF
    preset calibrated to the target size.
    """
    target_bytes = COMPRESS_TARGETS.get(target_key)
    if not target_bytes:
        return []

    vbr = compute_target_bitrate(input_path, target_bytes, audio_bitrate_kbps)

    if vbr is None:
        # Fallback : CRF calibré sur la taille cible — sans connaitre la durée
        target_mb = target_bytes / (1024 * 1024)
        if target_mb <= 10:   crf = 34
        elif target_mb <= 16: crf = 32
        elif target_mb <= 25: crf = 28
        elif target_mb <= 50: crf = 24
        else:                 crf = 20
        logger.warning(
            "build_compress_args: duration unknown for %s — using CRF %d fallback",
            input_path.name, crf
        )
        return [
            "-c:v", "libx264", "-crf", str(crf), "-preset", "fast",
            "-c:a", "aac", "-b:a", f"{audio_bitrate_kbps}k",
            "-movflags", "+faststart",
        ]

    return [
        "-c:v", "libx264",
        "-b:v", f"{vbr}k",
        "-maxrate", f"{vbr}k",
        "-bufsize", f"{vbr * 2}k",
        "-c:a", "aac",
        "-b:a", f"{audio_bitrate_kbps}k",
        "-movflags", "+faststart",
    ]


# ── Built-in Presets ──────────────────────────────────────────────────────────

BUILTIN_PRESETS: dict[str, dict[str, Any]] = {
    "custom": {
        "label": "🔧  Custom",
        "fmt":   None,
        "args":  [],
        "desc":  "Choose the format manually.",
    },
    "discord": {
        "label": "💬  Discord (≤ 25 MB)",
        "fmt":   "mp4",
        "args":  ["-c:v", "libx264", "-crf", "28", "-preset", "fast",
                  "-c:a", "aac", "-b:a", "128k", "-fs", "26214400"],
        "desc":  "H.264 MP4 optimised to stay under 25 MB.",
    },
    "instagram": {
        "label": "📸  Instagram (1080p H.264)",
        "fmt":   "mp4",
        "args":  ["-c:v", "libx264", "-crf", "23", "-preset", "fast",
                  "-vf", "scale=-2:1080", "-c:a", "aac", "-b:a", "192k",
                  "-movflags", "+faststart"],
        "desc":  "1080p MP4, optimised for Instagram Reels/Feed.",
    },
    "hifi": {
        "label": "🎵  Audio Hi-Fi (FLAC)",
        "fmt":   "flac",
        "args":  ["-c:a", "flac", "-compression_level", "8"],
        "desc":  "Lossless audio extraction in FLAC.",
    },
    "fast_audio": {
        "label": "⚡  Fast Extract (stream copy)",
        "fmt":   None,
        "args":  ["-vn", "-c:a", "copy"],
        "desc":  "Extract audio without re-encoding (very fast).",
        "fast":  True,
    },
    "whatsapp": {
        "label": "📱  WhatsApp Video",
        "fmt":   "mp4",
        "args":  ["-c:v", "libx264", "-crf", "30", "-preset", "fast",
                  "-vf", "scale=-2:720", "-c:a", "aac", "-b:a", "128k",
                  "-fs", "16777216"],
        "desc":  "MP4 720p under 16 MB, suitable for WhatsApp.",
    },
}

PRESETS: dict[str, dict[str, Any]] = {}

CONFIG_FILE = Path.home() / ".omnimedia" / "config.json"


# ── PresetManager ─────────────────────────────────────────────────────────────

class PresetManager:
    """Persists custom presets to ~/.omnimedia/config.json."""

    @classmethod
    def _read_config(cls) -> dict:
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    @classmethod
    def _write_config(cls, data: dict) -> None:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @classmethod
    def load_custom(cls) -> dict[str, dict[str, Any]]:
        return cls._read_config().get("custom_presets", {})

    @classmethod
    def save(cls, name: str, fmt: str, extra_args: list[str], desc: str = "") -> None:
        data   = cls._read_config()
        custom = data.get("custom_presets", {})
        custom[name] = {
            "label": f"⭐  {name}",
            "fmt":   fmt or None,
            "args":  extra_args,
            "desc":  desc or f"Custom preset: {name}",
            "custom": True,
        }
        data["custom_presets"] = custom
        cls._write_config(data)
        _refresh_presets()

    @classmethod
    def delete(cls, name: str) -> None:
        data   = cls._read_config()
        custom = data.get("custom_presets", {})
        custom.pop(name, None)
        data["custom_presets"] = custom
        cls._write_config(data)
        _refresh_presets()

    @classmethod
    def list_names(cls) -> list[str]:
        return list(cls.load_custom().keys())


def _refresh_presets() -> None:
    PRESETS.clear()
    PRESETS.update(BUILTIN_PRESETS)
    for name, p in PresetManager.load_custom().items():
        key = "user_" + re.sub(r"\W+", "_", name.lower())
        PRESETS[key] = p


_refresh_presets()


# ── Output path helper ────────────────────────────────────────────────────────

def _build_output_path(input_path: Path, output_fmt: str, output_dir: Path) -> Path:
    stem = input_path.stem
    out  = output_dir / f"{stem}_converted.{output_fmt}"
    ctr  = 1
    while out.exists():
        out = output_dir / f"{stem}_converted_{ctr}.{output_fmt}"
        ctr += 1
    return out


# ── FFmpeg command builder ────────────────────────────────────────────────────

def _build_ffmpeg_cmd(
    input_path:   Path,
    output_path:  Path,
    output_fmt:   str,
    preset:       dict[str, Any],
    trim_start:   str = "",
    trim_end:     str = "",
    compress_args: list[str] | None = None,
) -> list[str]:
    """
    Build the full FFmpeg command list.
    *compress_args* overrides the format auto-args when the
    Batch Compressor mode is active.
    """
    ffmpeg      = find_ffmpeg() or "ffmpeg"
    preset_args = preset.get("args", [])
    kind        = classify_file(input_path)
    fmt         = output_fmt

    trim_pre: list[str] = []
    trim_post: list[str] = []
    if trim_start.strip():
        trim_pre  = ["-ss", trim_start.strip()]
    if trim_end.strip():
        trim_post = ["-to", trim_end.strip()]

    base = [ffmpeg, "-y"] + trim_pre + ["-i", str(input_path)] + trim_post

    # Compressor mode takes priority
    if compress_args:
        return base + compress_args + [str(output_path)]

    # Named preset with explicit args
    if preset_args and not preset.get("custom") and preset["label"] != "🔧  Custom":
        return base + preset_args + [str(output_path)]

    # Auto-build from file type
    extra: list[str] = []
    if kind == "image":
        if fmt in ("jpg", "jpeg"): extra = ["-q:v", "2"]
        elif fmt == "png":         extra = ["-compression_level", "6"]
        elif fmt == "webp":        extra = ["-q:v", "80"]
    elif kind == "video":
        if fmt == "mp4":    extra = ["-c:v", "libx264", "-crf", "23", "-preset", "fast", "-c:a", "aac", "-b:a", "192k"]
        elif fmt == "mp3":  extra = ["-vn", "-c:a", "libmp3lame", "-b:a", "192k"]
        elif fmt == "mkv":  extra = ["-c:v", "copy", "-c:a", "copy"]
        elif fmt == "webm": extra = ["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0", "-c:a", "libopus"]
        elif fmt == "gif":
            palette = str(output_path.with_suffix(".palette.png"))
            return (
                base + ["-vf", "fps=12,scale=480:-1:flags=lanczos,palettegen", palette]
                + ["&&", ffmpeg, "-y", "-i", str(input_path), "-i", palette,
                   "-filter_complex", "fps=12,scale=480:-1:flags=lanczos[x];[x][1:v]paletteuse",
                   str(output_path)]
            )
    elif kind == "audio":
        if fmt == "mp3":    extra = ["-c:a", "libmp3lame", "-b:a", "192k"]
        elif fmt == "aac":  extra = ["-c:a", "aac", "-b:a", "192k"]
        elif fmt == "wav":  extra = ["-c:a", "pcm_s16le"]
        elif fmt == "flac": extra = ["-c:a", "flac"]
        elif fmt == "ogg":  extra = ["-c:a", "libvorbis", "-q:a", "4"]
        else:               extra = ["-c:a", "copy"]

    if preset.get("custom") and preset_args:
        extra = preset_args

    return base + extra + [str(output_path)]


# ── Sync per-file conversion (used by workers) ────────────────────────────────

def _convert_sync(
    input_path:    Path,
    output_fmt:    str,
    output_dir:    Path,
    preset_key:    str = "custom",
    trim_start:    str = "",
    trim_end:      str = "",
    progress_cb:   Any = None,
    compress_target: str = "",  # "" | "discord" | "whatsapp" | "email"
) -> tuple[bool, str]:
    if not ffmpeg_available():
        return False, "FFmpeg not found."
    if not input_path.exists():
        return False, f"Source not found: {input_path}"

    output_dir.mkdir(parents=True, exist_ok=True)
    preset = PRESETS.get(preset_key, PRESETS["custom"])

    fmt = output_fmt
    if preset.get("fmt"):
        fmt = preset["fmt"]
    elif preset.get("fast"):
        ext = input_path.suffix.lstrip(".")
        fmt = ext if ext in ("m4a", "aac", "ogg", "opus") else "m4a"

    output_path = _build_output_path(input_path, fmt, output_dir)

    # Build compress args if target is set
    compress_args: list[str] | None = None
    if compress_target and compress_target in COMPRESS_TARGETS:
        compress_args = build_compress_args(input_path, compress_target)

    cmd       = _build_ffmpeg_cmd(input_path, output_path, fmt, preset,
                                   trim_start, trim_end, compress_args)
    use_shell = "&&" in cmd
    duration  = get_media_info(input_path).duration
    time_re   = re.compile(r"time=(\d+):(\d+):(\d+\.?\d*)")

    # Masquer la console sur Windows
    _kwargs: dict = {}
    if sys.platform == "win32":
        import ctypes
        _kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW

    try:
        if use_shell:
            cmd_str = " ".join(f'"{c}"' if " " in c else c for c in cmd)
            proc = subprocess.Popen(cmd_str, shell=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    universal_newlines=True, **_kwargs)
        else:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    universal_newlines=True, **_kwargs)

        for line in proc.stdout:
            m = time_re.search(line)
            if m and duration and progress_cb:
                h, mn, s = float(m.group(1)), float(m.group(2)), float(m.group(3))
                elapsed  = h * 3600 + mn * 60 + s
                progress_cb(min(int(elapsed / duration * 95) + 5, 98))

        proc.wait()

        if proc.returncode != 0:
            return False, f"FFmpeg exit {proc.returncode} — source may be corrupt."
        if not output_path.exists():
            return False, "Output file missing after conversion."

        if progress_cb:
            progress_cb(100)
        return True, str(output_path)

    except Exception as exc:
        return False, str(exc)


# ── Single-file Worker ────────────────────────────────────────────────────────

class ConvertWorker(QThread):
    progress = pyqtSignal(int)
    status   = pyqtSignal(str)
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(
        self,
        input_path:      Path,
        output_fmt:      str,
        output_dir:      Path | None = None,
        preset_key:      str = "custom",
        trim_start:      str = "",
        trim_end:        str = "",
        compress_target: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.input_path      = Path(input_path)
        self.output_fmt      = output_fmt.lower().lstrip(".")
        self.output_dir      = Path(output_dir) if output_dir else self.input_path.parent
        self.preset_key      = preset_key
        self.trim_start      = trim_start
        self.trim_end        = trim_end
        self.compress_target = compress_target
        self._cancelled      = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        label = "Compressing" if self.compress_target else "Converting"
        self.status.emit(f"⚙  {label} → .{self.output_fmt}…")
        self.progress.emit(5)

        def _prog(v: int) -> None:
            if not self._cancelled:
                self.progress.emit(v)

        ok, val = _convert_sync(
            self.input_path, self.output_fmt, self.output_dir,
            self.preset_key, self.trim_start, self.trim_end,
            progress_cb=_prog,
            compress_target=self.compress_target,
        )
        if self._cancelled:
            return
        if ok:
            self.finished.emit(val)
        else:
            self.error.emit(val)


# ── Batch Worker ──────────────────────────────────────────────────────────────

class BatchConvertWorker(QThread):
    file_started     = pyqtSignal(int, str)
    file_progress    = pyqtSignal(int, int)
    file_done        = pyqtSignal(int, str, str)
    file_error       = pyqtSignal(int, str, str)
    overall_progress = pyqtSignal(int)
    all_done         = pyqtSignal(int, int)
    status           = pyqtSignal(str)

    def __init__(
        self,
        files:           list[Path],
        output_fmt:      str,
        output_dir:      Path,
        preset_key:      str = "custom",
        max_workers:     int = 2,
        trim_start:      str = "",
        trim_end:        str = "",
        compress_target: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.files           = [Path(f) for f in files]
        self.output_fmt      = output_fmt
        self.output_dir      = output_dir
        self.preset_key      = preset_key
        self.max_workers     = max(1, min(max_workers, 4))
        self.trim_start      = trim_start
        self.trim_end        = trim_end
        self.compress_target = compress_target
        self._cancelled      = False
        self._executor: ThreadPoolExecutor | None = None

    def cancel(self) -> None:
        self._cancelled = True
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=True)

    def run(self) -> None:
        import threading
        total   = len(self.files)
        success = 0
        errors  = 0
        done    = 0

        for i, f in enumerate(self.files):
            self.file_started.emit(i, str(f))

        def _make_cb(idx: int):
            def _cb(v: int):
                if not self._cancelled:
                    self.file_progress.emit(idx, v)
            return _cb

        def _task(idx: int, f: Path):
            if self._cancelled:
                return idx, False, "Cancelled", str(f)
            ok, val = _convert_sync(
                f, self.output_fmt, self.output_dir,
                self.preset_key, self.trim_start, self.trim_end,
                progress_cb=_make_cb(idx),
                compress_target=self.compress_target,
            )
            return idx, ok, val, str(f)

        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            self._executor = ex
            futures = {ex.submit(_task, i, f): (i, f) for i, f in enumerate(self.files)}
            for future in as_completed(futures):
                if self._cancelled:
                    break
                try:
                    idx, ok, val, src = future.result()
                except Exception as exc:
                    i, f = futures[future]
                    logger.error("Batch convert task failed for %s: %s", f, exc, exc_info=True)
                    self.file_error.emit(i, str(f), str(exc))
                    errors += 1
                else:
                    if ok:
                        success += 1
                        self.file_done.emit(idx, src, val)
                    else:
                        errors += 1
                        self.file_error.emit(idx, src, val)
                done += 1
                self.overall_progress.emit(int(done / total * 100))
                self.status.emit(f"⚙  [{done}/{total}] done")

        self._executor = None
        self.overall_progress.emit(100)
        self.all_done.emit(success, errors)
