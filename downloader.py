"""
downloader.py — yt-dlp download logic running in a QThread.

CORRECTIONS v2 :
  - Suppression du double appel extract_info/download (causait le blocage).
  - quiet=True désactivait les hooks de progression → remplacé par noprogress=True.
  - Un seul extract_info(download=True) gère tout en un passage.
  - Passage des options avancées (codec, bitrate, résolution) via AdvancedOptions.
"""
from __future__ import annotations

import re
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False


# ── Options avancées (partagées avec main.py) ─────────────────────────────────

@dataclass
class AdvancedOptions:
    audio_bitrate:  str = "192k"   # "128k" | "192k" | "320k"
    video_codec:    str = "h264"   # "h264" | "h265" | "vp9"
    max_resolution: str = "best"   # "best" | "1080" | "720" | "480"


# ── Helpers ───────────────────────────────────────────────────────────────────

def sanitize_url(url: str) -> str:
    return url.strip()


def is_valid_url(url: str) -> bool:
    pattern = re.compile(
        r'^(https?://)'
        r'([\w\-]+(\.[\w\-]+)+)'
        r'(:\d+)?(/[^\s]*)?$',
        re.IGNORECASE,
    )
    return bool(pattern.match(url))


# ── Progress hook factory ─────────────────────────────────────────────────────

def make_progress_hook(
    progress_cb: Callable[[int], None],
    status_cb:   Callable[[str], None],
) -> Callable:
    """Return a yt-dlp progress hook that emits Qt signals."""

    def hook(d: dict) -> None:
        status = d.get("status", "")

        if status == "downloading":
            total      = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            speed      = d.get("_speed_str", "").strip()
            eta        = d.get("_eta_str", "").strip()

            if total > 0:
                pct = int(min(downloaded / total * 95, 95))
                progress_cb(pct)

            dl_str = d.get("_downloaded_bytes_str", "").strip()
            info = f"⬇  {dl_str}" if dl_str else "⬇  Téléchargement…"
            if speed and speed != "N/A":
                info += f"  ·  {speed}"
            if eta and eta != "N/A":
                info += f"  ·  ETA {eta}"
            status_cb(info)

        elif status == "finished":
            progress_cb(97)
            status_cb("⚙  Post-traitement…")

        elif status == "error":
            status_cb("✗  Erreur pendant le téléchargement")

    return hook


# ── Download Worker ───────────────────────────────────────────────────────────

class DownloadWorker(QThread):
    """QThread qui télécharge une URL via yt-dlp."""

    progress  = pyqtSignal(int)
    status    = pyqtSignal(str)
    finished  = pyqtSignal(str)
    error     = pyqtSignal(str)

    def __init__(
        self,
        url:        str,
        output_dir: Path,
        mode:       str = "video",
        options:    AdvancedOptions | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.url        = sanitize_url(url)
        self.output_dir = Path(output_dir)
        self.mode       = mode
        self.options    = options or AdvancedOptions()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def _build_format_selector(self) -> str:
        if self.mode == "audio":
            return "bestaudio/best"
        res = self.options.max_resolution
        if res == "best":
            return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best"
        return (
            f"bestvideo[height<={res}][ext=mp4]+bestaudio[ext=m4a]"
            f"/bestvideo[height<={res}]+bestaudio/best[height<={res}]/best"
        )

    def _build_postprocessors(self) -> list[dict]:
        if self.mode == "audio":
            bitrate = self.options.audio_bitrate.replace("k", "")
            return [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
                     "preferredquality": bitrate}]
        return []

    def run(self) -> None:
        if not YT_DLP_AVAILABLE:
            self.error.emit("yt-dlp n'est pas installé.\nLancez : pip install yt-dlp")
            return

        if not is_valid_url(self.url):
            self.error.emit("URL invalide. Vérifiez le lien collé.")
            return

        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_template = str(self.output_dir / "%(title)s.%(ext)s")
        downloaded_paths: list[str] = []

        def on_progress(pct: int) -> None:
            if not self._cancelled:
                self.progress.emit(pct)

        def on_status(msg: str) -> None:
            if not self._cancelled:
                self.status.emit(msg)

        def pp_hook(d: dict) -> None:
            if d.get("status") == "finished":
                path = (
                    d.get("info_dict", {}).get("filepath")
                    or d.get("info_dict", {}).get("filename")
                    or d.get("filename", "")
                )
                if path:
                    downloaded_paths.append(str(path))

        ydl_opts: dict = {
            "format":         self._build_format_selector(),
            "outtmpl":        output_template,
            "postprocessors": self._build_postprocessors(),
            # ── CORRECTIF CLÉ ────────────────────────────────────────────────
            # quiet=True supprimait les hooks de progression dans certaines
            # versions de yt-dlp. On utilise noprogress=True à la place :
            # cela cache la barre texte en console SANS bloquer les hooks Python.
            "quiet":          False,
            "noprogress":     True,
            "no_warnings":    True,
            # ─────────────────────────────────────────────────────────────────
            "progress_hooks":      [make_progress_hook(on_progress, on_status)],
            "postprocessor_hooks": [pp_hook],
        }

        if self.mode == "video":
            ydl_opts["merge_output_format"] = "mp4"

        self.status.emit("🔍  Analyse de l'URL…")
        self.progress.emit(2)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # ── CORRECTIF PRINCIPAL ───────────────────────────────────────
                # Ancien code : extract_info(download=False) puis download([url])
                # → deux sessions yt-dlp indépendantes, hooks ignorés sur la 2e.
                # Nouveau code : un seul appel extract_info(download=True).
                info = ydl.extract_info(self.url, download=True)
                # ─────────────────────────────────────────────────────────────

            if self._cancelled:
                return

            # Résolution du chemin final
            if downloaded_paths:
                final_path = downloaded_paths[-1]
            else:
                ext = ".mp3" if self.mode == "audio" else ".mp4"
                candidates = sorted(
                    self.output_dir.glob(f"*{ext}"),
                    key=os.path.getmtime, reverse=True,
                )
                if candidates:
                    final_path = str(candidates[0])
                else:
                    all_files = sorted(
                        [f for f in self.output_dir.iterdir() if f.is_file()],
                        key=os.path.getmtime, reverse=True,
                    )
                    final_path = str(all_files[0]) if all_files else str(self.output_dir)

            self.progress.emit(100)
            self.finished.emit(final_path)

        except Exception as exc:
            if not self._cancelled:
                msg = str(exc)
                if "HTTP Error 403" in msg:
                    msg = "Accès refusé (403). Mettez yt-dlp à jour :\npip install -U yt-dlp"
                elif "Video unavailable" in msg:
                    msg = "Vidéo indisponible ou privée."
                self.error.emit(msg)
