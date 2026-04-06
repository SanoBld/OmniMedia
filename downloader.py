"""
downloader.py — OmniMedia v4
New in v4: sanitize_filename, .part cleanup on cancel,
playlist folder mode, smart ID3 auto-tagging via yt-dlp metadata.
"""
from __future__ import annotations

import re, os, json, shutil, tempfile, urllib.request
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal

from config_manager import cfg, resource_path  # centralised settings

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False

try:
    import mutagen
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

try:
    import browser_cookie3
    BROWSER_COOKIE3_AVAILABLE = True
except ImportError:
    BROWSER_COOKIE3_AVAILABLE = False

# ── Config dir ────────────────────────────────────────────────────────────────
CONFIG_DIR   = Path.home() / ".omnimedia"
HISTORY_FILE = CONFIG_DIR / "history.json"

# ── Supported browsers for auto cookie import ─────────────────────────────────
SUPPORTED_BROWSERS = ["chrome", "firefox", "edge", "brave", "opera", "safari"]


# ── Filename sanitisation ─────────────────────────────────────────────────────

_FORBIDDEN = re.compile(r'[\\/:*?"<>|]')
_WHITESPACE = re.compile(r'\s+')

def sanitize_filename(name: str, max_length: int = 200) -> str:
    """
    Strip characters forbidden on Windows/macOS/Linux filesystems,
    collapse runs of whitespace, and truncate to *max_length* chars.
    Returns 'download' if the result would be empty.
    """
    name = _FORBIDDEN.sub("_", name)          # replace forbidden chars
    name = _WHITESPACE.sub(" ", name).strip() # collapse whitespace
    name = name[:max_length]                   # truncate
    return name or "download"


# ── Advanced options ──────────────────────────────────────────────────────────

@dataclass
class AdvancedOptions:
    audio_bitrate:   str  = "192k"
    video_codec:     str  = "h264"
    max_resolution:  str  = "best"
    playlist_items:  str  = ""
    cookies_file:    str  = ""
    browser_cookies: str  = ""    # browser name for auto-import
    embed_thumbnail: bool = True  # embed album art for audio


# ── Download History ───────────────────────────────────────────────────────────

class DownloadHistory:
    def __init__(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._entries: list[dict] = self._load()

    def _load(self) -> list[dict]:
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self) -> None:
        try:
            HISTORY_FILE.write_text(
                json.dumps(self._entries, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def add(self, url: str, title: str, path: str, mode: str) -> None:
        self._entries.insert(0, {
            "url":   url,
            "title": title,
            "path":  path,
            "mode":  mode,
            "date":  datetime.now().isoformat(timespec="seconds"),
        })
        self._entries = self._entries[:200]
        self._save()

    def all(self) -> list[dict]:
        return list(self._entries)

    def clear(self) -> None:
        self._entries = []
        self._save()


history = DownloadHistory()


# ── Smart auto-tagger ─────────────────────────────────────────────────────────

def _embed_id3_tags(filepath: Path, info: dict) -> None:
    """
    Embed ID3 tags (title, artist, album, year, genre) and cover art
    into an MP3 file using mutagen. Falls back silently if unavailable.
    """
    if not MUTAGEN_AVAILABLE:
        return
    try:
        from mutagen.id3 import (
            ID3, TIT2, TPE1, TALB, TDRC, TCON, APIC, ID3NoHeaderError
        )
        try:
            tags = ID3(str(filepath))
        except ID3NoHeaderError:
            tags = ID3()

        title    = info.get("title", "")
        uploader = info.get("uploader") or info.get("channel", "")
        album    = info.get("album") or info.get("playlist_title", "")
        year     = str(info.get("upload_date", ""))[:4]
        genre    = info.get("genre", "")

        if title:    tags["TIT2"] = TIT2(encoding=3, text=title)
        if uploader: tags["TPE1"] = TPE1(encoding=3, text=uploader)
        if album:    tags["TALB"] = TALB(encoding=3, text=album)
        if year:     tags["TDRC"] = TDRC(encoding=3, text=year)
        if genre:    tags["TCON"] = TCON(encoding=3, text=genre)

        # Embed thumbnail if available
        thumb_url = info.get("thumbnail") or ""
        if thumb_url:
            try:
                with urllib.request.urlopen(thumb_url, timeout=8) as r:
                    img_data = r.read()
                mime = "image/jpeg" if thumb_url.lower().endswith(".jpg") else "image/png"
                tags["APIC"] = APIC(
                    encoding=3, mime=mime,
                    type=3,          # Cover (front)
                    desc="Cover",
                    data=img_data,
                )
            except Exception:
                pass  # thumbnail download is best-effort

        tags.save(str(filepath), v2_version=3)
    except Exception as exc:
        print(f"[AutoTag] Could not embed tags: {exc}")


# ── Download Worker ────────────────────────────────────────────────────────────

class DownloadWorker(QThread):
    """
    Background thread that handles a single download via yt-dlp.
    Emits granular progress / status signals for UI binding.
    """

    progress    = pyqtSignal(int)           # 0-100
    speed       = pyqtSignal(str)           # human-readable speed string
    eta         = pyqtSignal(str)           # human-readable ETA string
    status      = pyqtSignal(str, str)      # (message, level)  level ∈ ok|err|info|warn
    finished    = pyqtSignal(bool, str)     # (success, output_path)

    def __init__(
        self,
        url           : str,
        output_dir    : str | Path,
        mode          : str = "audio",          # "audio" | "video"
        options       : AdvancedOptions | None = None,
        playlist_mode : bool = False,            # create sub-folder per playlist
        auto_tag      : bool = True,             # embed smart ID3 tags
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.url           = url.strip()
        self.output_dir    = Path(output_dir)
        self.mode          = mode
        self.options       = options or AdvancedOptions()
        self.playlist_mode = playlist_mode
        self.auto_tag      = auto_tag
        self._cancelled    = False
        self._output_path  = ""

    # ── Cancellation & cleanup ────────────────────────────────────────────────

    def cancel(self) -> None:
        """Request cancellation. Triggers cleanup of .part files."""
        self._cancelled = True

    def cleanup(self) -> None:
        """Delete any leftover .part / .ytdl residue files in output_dir."""
        try:
            for f in self.output_dir.glob("*.part"):
                f.unlink(missing_ok=True)
            for f in self.output_dir.glob("*.ytdl"):
                f.unlink(missing_ok=True)
        except Exception as exc:
            print(f"[DownloadWorker.cleanup] {exc}")

    # ── yt-dlp hooks ─────────────────────────────────────────────────────────

    def _progress_hook(self, d: dict) -> None:
        if self._cancelled:
            raise Exception("Download cancelled by user")

        status = d.get("status", "")
        if status == "downloading":
            pct_raw = d.get("_percent_str", "0%").strip().rstrip("%")
            try:
                self.progress.emit(int(float(pct_raw)))
            except ValueError:
                pass
            self.speed.emit(d.get("_speed_str", "").strip())
            self.eta.emit(d.get("_eta_str", "").strip())
        elif status == "finished":
            self._output_path = d.get("filename", "")
            self.progress.emit(100)

    def _build_ydl_opts(self) -> dict:
        """Build the yt-dlp options dict from current settings."""
        o = self.options

        # Determine effective output directory (playlist sub-folder if requested)
        out_dir = self.output_dir
        if self.playlist_mode:
            # %(playlist_title)s falls back to the video title when not a playlist
            out_dir_template = str(out_dir / "%(playlist_title|NA)s" / "%(title)s.%(ext)s")
        else:
            out_dir_template = str(out_dir / "%(title)s.%(ext)s")

        # Sanitise output template title component
        # yt-dlp handles template substitution, but we guard the directory part
        out_dir.mkdir(parents=True, exist_ok=True)

        # Build ffmpeg location: prefer user setting, then exe folder, then PATH
        ffmpeg_loc = cfg.ffmpeg_path
        if not ffmpeg_loc:
            # Check alongside the frozen executable first
            exe_dir = Path(getattr(os, "frozen_path", Path(__file__).parent))
            candidate = exe_dir / "ffmpeg.exe"
            if candidate.exists():
                ffmpeg_loc = str(candidate)

        opts: dict = {
            "outtmpl"         : out_dir_template,
            "progress_hooks"  : [self._progress_hook],
            "noplaylist"      : not self.playlist_mode,
            "quiet"           : True,
            "no_warnings"     : True,
            "restrictfilenames": True,   # yt-dlp built-in sanitisation
        }

        if ffmpeg_loc:
            opts["ffmpeg_location"] = ffmpeg_loc

        # Cookies
        if o.cookies_file:
            opts["cookiefile"] = o.cookies_file
        elif o.browser_cookies and BROWSER_COOKIE3_AVAILABLE:
            opts["cookiesfrombrowser"] = (o.browser_cookies,)

        # Format selection
        if self.mode == "audio":
            opts["format"]           = "bestaudio/best"
            opts["postprocessors"]   = [{
                "key"            : "FFmpegExtractAudio",
                "preferredcodec" : "mp3",
                "preferredquality": o.audio_bitrate.rstrip("k"),
            }]
            if o.embed_thumbnail and MUTAGEN_AVAILABLE:
                opts["writethumbnail"] = False   # we embed manually after download
        else:
            # Video
            res_map = {
                "best": "bestvideo+bestaudio/best",
                "1080": "bestvideo[height<=1080]+bestaudio/best",
                "720" : "bestvideo[height<=720]+bestaudio/best",
                "480" : "bestvideo[height<=480]+bestaudio/best",
                "360" : "bestvideo[height<=360]+bestaudio/best",
            }
            opts["format"] = res_map.get(o.max_resolution, "bestvideo+bestaudio/best")
            opts["merge_output_format"] = "mp4"

        return opts

    # ── Thread entry point ────────────────────────────────────────────────────

    def run(self) -> None:
        if not YT_DLP_AVAILABLE:
            self.finished.emit(False, "yt-dlp not installed")
            return

        try:
            self.status.emit("Starting download…", "info")
            opts    = self._build_ydl_opts()
            info_dict: dict = {}

            with yt_dlp.YoutubeDL(opts) as ydl:
                info_dict = ydl.extract_info(self.url, download=True) or {}

            if self._cancelled:
                self.cleanup()
                self.finished.emit(False, "Cancelled")
                return

            # Resolve actual output path
            out_path = Path(self._output_path) if self._output_path else self.output_dir

            # Sanitise any title-based filenames (belt-and-suspenders)
            raw_title = info_dict.get("title", "")
            if raw_title:
                sanitize_filename(raw_title)   # validation only; yt-dlp already wrote the file

            # Smart auto-tagging for MP3 output
            if self.mode == "audio" and self.auto_tag and cfg.auto_tag:
                mp3_path = out_path.with_suffix(".mp3") if out_path.suffix != ".mp3" else out_path
                if mp3_path.exists():
                    _embed_id3_tags(mp3_path, info_dict)

            history.add(
                url   = self.url,
                title = sanitize_filename(info_dict.get("title", self.url)),
                path  = str(out_path),
                mode  = self.mode,
            )

            self.status.emit("Download complete", "ok")
            self.finished.emit(True, str(out_path))

        except Exception as exc:
            msg = str(exc)
            if self._cancelled:
                self.cleanup()
                self.finished.emit(False, "Cancelled")
            else:
                self.status.emit(f"Error: {msg}", "err")
                self.finished.emit(False, msg)


# ── Queue item ────────────────────────────────────────────────────────────────

@dataclass
class QueueItem:
    """Represents a single entry in the download queue."""
    url    : str
    mode   : str            # "audio" | "video"
    status : str = "pending"   # "pending" | "downloading" | "done" | "error" | "cancelled"
    title  : str = ""
    worker : DownloadWorker | None = field(default=None, repr=False)


# ── yt-dlp update worker ──────────────────────────────────────────────────────

class YtdlpUpdateWorker(QThread):
    finished = pyqtSignal(bool, str)

    def run(self) -> None:
        try:
            import subprocess
            result = subprocess.run(
                ["pip", "install", "--upgrade", "yt-dlp"],
                capture_output=True, text=True, timeout=120,
            )
            ok  = result.returncode == 0
            msg = "yt-dlp updated successfully" if ok else result.stderr.strip()[:200]
            self.finished.emit(ok, msg)
        except Exception as exc:
            self.finished.emit(False, str(exc))


# ── GitHub version checker ────────────────────────────────────────────────────

class VersionChecker(QThread):
    update_available = pyqtSignal(str)
    up_to_date       = pyqtSignal()

    def __init__(self, current_version: str, parent=None) -> None:
        super().__init__(parent)
        self._current = current_version

    def run(self) -> None:
        try:
            url = "https://api.github.com/repos/SanoBld/OmniMedia/releases/latest"
            with urllib.request.urlopen(url, timeout=6) as r:
                data    = json.loads(r.read())
                latest  = data.get("tag_name", "").lstrip("v")
                if latest and latest != self._current:
                    self.update_available.emit(latest)
                else:
                    self.up_to_date.emit()
        except Exception:
            self.up_to_date.emit()


# ── Browser cookie worker ─────────────────────────────────────────────────────

class BrowserCookieWorker(QThread):
    finished = pyqtSignal(bool, str)   # (success, cookies_file_path | error_msg)

    def __init__(self, browser: str, parent=None) -> None:
        super().__init__(parent)
        self.browser = browser

    def run(self) -> None:
        if not BROWSER_COOKIE3_AVAILABLE:
            self.finished.emit(False, "browser-cookie3 not installed")
            return
        try:
            getter = getattr(browser_cookie3, self.browser, None)
            if getter is None:
                self.finished.emit(False, f"Browser '{self.browser}' not supported")
                return
            cookies    = getter()
            tmp        = tempfile.NamedTemporaryFile(
                suffix=".txt", delete=False, mode="w", encoding="utf-8"
            )
            # Write Netscape cookie format
            tmp.write("# Netscape HTTP Cookie File\n")
            for c in cookies:
                tmp.write(
                    f"{c.domain}\tTRUE\t{c.path}\t"
                    f"{'TRUE' if c.secure else 'FALSE'}\t"
                    f"{int(c.expires) if c.expires else 0}\t"
                    f"{c.name}\t{c.value}\n"
                )
            tmp.close()
            self.finished.emit(True, tmp.name)
        except Exception as exc:
            self.finished.emit(False, str(exc))
