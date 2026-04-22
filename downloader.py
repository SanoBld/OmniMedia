"""
downloader.py — OmniMedia v4.5
FIX: Smart Auto-Tagging now works correctly.
ROOT CAUSE: quiet=True suppressed yt-dlp hooks AND metadata; the output
path captured in _progress_hook was the pre-FFmpeg filename (e.g. .webm),
not the final .mp3. Using postprocessor_hooks + quiet=False/noprogress=True.
v4.5: All print() calls replaced with proper logger (app_logger).
"""
from __future__ import annotations

import re, os, json, shutil, tempfile, urllib.request
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal

from config_manager import cfg, resource_path
from app_logger import get_logger

logger = get_logger(__name__)

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

CONFIG_DIR   = Path.home() / ".omnimedia"
HISTORY_FILE = CONFIG_DIR / "history.json"
SUPPORTED_BROWSERS = ["chrome", "firefox", "edge", "brave", "opera", "safari"]

# ── Filename sanitisation ─────────────────────────────────────────────────────

_FORBIDDEN  = re.compile(r'[\\/:*?"<>|]')
_WHITESPACE = re.compile(r'\s+')

def sanitize_filename(name: str, max_length: int = 200) -> str:
    name = _FORBIDDEN.sub("_", name)
    name = _WHITESPACE.sub(" ", name).strip()
    return name[:max_length] or "download"


# ── Advanced options ──────────────────────────────────────────────────────────

@dataclass
class AdvancedOptions:
    audio_bitrate:   str  = "192k"
    video_codec:     str  = "h264"
    max_resolution:  str  = "best"
    playlist_items:  str  = ""
    cookies_file:    str  = ""
    browser_cookies: str  = ""
    embed_thumbnail: bool = True
    ignore_errors:   bool = True   # Playlist : continuer même en cas d'erreur sur un élément
    output_format:   str  = ""     # "" = défaut selon mode (mp3/mp4), sinon format explicite


# ── Download History ──────────────────────────────────────────────────────────

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
            "url": url, "title": title, "path": path, "mode": mode,
            "date": datetime.now().isoformat(timespec="seconds"),
        })
        self._entries = self._entries[:200]
        self._save()

    def all(self) -> list[dict]:
        return list(self._entries)

    def clear(self) -> None:
        self._entries = []
        self._save()


history = DownloadHistory()


# ── MusicBrainz metadata enrichment ──────────────────────────────────────────

_MB_BASE = "https://musicbrainz.org/ws/2"
_MB_HEADERS = {
    "User-Agent": "OmniMedia/5.5.0 (https://github.com/SanoBld/OmniMedia)",
    "Accept": "application/json",
}

def _query_musicbrainz(title: str, artist: str) -> dict:
    """
    Query MusicBrainz to enrich audio metadata.
    Returns a dict with enriched fields or {} on failure.
    All errors are silently caught — this is optional enrichment.
    """
    if not title:
        return {}
    try:
        import urllib.parse
        # Search for recording matching title + artist
        query_parts = [f'recording:"{urllib.parse.quote(title)}"']
        if artist:
            query_parts.append(f'artist:"{urllib.parse.quote(artist)}"')
        query = " AND ".join(query_parts)
        url = (
            f"{_MB_BASE}/recording"
            f"?query={urllib.parse.quote(query)}&limit=1&inc=artists+releases+genres+isrcs"
            f"&fmt=json"
        )
        req = urllib.request.Request(url, headers=_MB_HEADERS)
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))

        recordings = data.get("recordings", [])
        if not recordings:
            return {}
        rec = recordings[0]

        # ── Score de pertinence minimum ───────────────────────────────────────
        score = int(rec.get("score", 0))
        if score < 60:
            return {}

        enriched: dict = {}
        enriched["mbid"] = rec.get("id", "")

        # Titre officiel
        if rec.get("title"):
            enriched["title"] = rec["title"]

        # Artiste(s)
        artist_credits = rec.get("artist-credit", [])
        if artist_credits:
            artists = " & ".join(
                ac.get("artist", {}).get("name", ac.get("name", ""))
                for ac in artist_credits
                if isinstance(ac, dict)
            )
            if artists:
                enriched["artist"] = artists
            # Sort name du premier artiste
            if artist_credits[0]:
                sort = artist_credits[0].get("artist", {}).get("sort-name", "")
                if sort: enriched["artist_sort"] = sort

        # Genres (tags MusicBrainz)
        genres = rec.get("genres") or rec.get("tags", [])
        if genres:
            enriched["genre"] = genres[0].get("name", "")

        # ISRC
        isrcs = rec.get("isrcs", [])
        if isrcs:
            enriched["isrc"] = isrcs[0]

        # Release (album, date, label, tracknumber)
        releases = rec.get("releases", [])
        if releases:
            rel = releases[0]
            if rel.get("title"):
                enriched["album"] = rel["title"]
            date = rel.get("date", "")
            if date:
                enriched["year"] = date[:4]
            # Numéro de piste
            media_list = rel.get("media", [])
            if media_list:
                tracks = media_list[0].get("tracks", [])
                if tracks:
                    enriched["tracknumber"] = str(tracks[0].get("number", ""))
                enriched["discnumber"] = str(media_list[0].get("position", ""))

            # Label
            label_info = rel.get("label-info", [])
            if label_info and isinstance(label_info, list):
                label = label_info[0].get("label", {})
                if label.get("name"):
                    enriched["label"] = label["name"]
                if label_info[0].get("catalog-number"):
                    enriched["catalog"] = label_info[0]["catalog-number"]

        logger.info("[MusicBrainz] Enriched: %s (score=%d MBID=%s)",
                    enriched.get("title", title), score, enriched.get("mbid", "?"))
        return enriched

    except Exception as exc:
        logger.debug("[MusicBrainz] Query failed for '%s': %s", title, exc)
        return {}


# ── Smart auto-tagger ─────────────────────────────────────────────────────────

def _embed_id3_tags(filepath: Path, info: dict) -> None:
    """
    Embed ID3 tags (title, artist, album, year, genre, tracknumber, ISRC, MBID…)
    into an MP3/audio file using mutagen.
    Enriched first via MusicBrainz API, falls back to yt-dlp metadata.
    """
    if not MUTAGEN_AVAILABLE:
        return
    if not filepath.exists():
        logger.warning("[AutoTag] File not found: %s", filepath)
        return

    try:
        from mutagen.id3 import (
            ID3, TIT2, TPE1, TPE2, TALB, TDRC, TCON, APIC,
            TRCK, TPOS, TPUB, TSRC, TXXX, ID3NoHeaderError
        )
        try:
            tags = ID3(str(filepath))
        except ID3NoHeaderError:
            tags = ID3()

        # ── Données de base depuis yt-dlp ─────────────────────────────────────
        title    = info.get("title", "")
        uploader = info.get("uploader") or info.get("channel", "")
        album    = info.get("album") or info.get("playlist_title", "")
        year     = str(info.get("upload_date", ""))[:4]
        genre    = info.get("genre", "")

        # ── Enrichissement MusicBrainz ────────────────────────────────────────
        mb = _query_musicbrainz(title, uploader)
        if mb:
            if mb.get("title"):   title    = mb["title"]
            if mb.get("artist"):  uploader = mb["artist"]
            if mb.get("album"):   album    = mb["album"]
            if mb.get("year"):    year     = mb["year"]
            if mb.get("genre"):   genre    = mb["genre"]

        # ── Tags principaux ───────────────────────────────────────────────────
        if title:    tags["TIT2"] = TIT2(encoding=3, text=title)
        if uploader: tags["TPE1"] = TPE1(encoding=3, text=uploader)
        if album:    tags["TALB"] = TALB(encoding=3, text=album)
        if year:     tags["TDRC"] = TDRC(encoding=3, text=year)
        if genre:    tags["TCON"] = TCON(encoding=3, text=genre)

        # ── Tags enrichis MusicBrainz ──────────────────────────────────────────
        if mb.get("artist_sort"):
            tags["TSOP"] = __import__("mutagen.id3", fromlist=["TSOP"]).TSOP(
                encoding=3, text=mb["artist_sort"]
            )
        if mb.get("tracknumber"):
            tags["TRCK"] = TRCK(encoding=3, text=mb["tracknumber"])
        if mb.get("discnumber"):
            tags["TPOS"] = TPOS(encoding=3, text=mb["discnumber"])
        if mb.get("label"):
            tags["TPUB"] = TPUB(encoding=3, text=mb["label"])
        if mb.get("isrc"):
            tags["TSRC"] = TSRC(encoding=3, text=mb["isrc"])
        if mb.get("mbid"):
            tags["TXXX:MusicBrainz Recording Id"] = TXXX(
                encoding=3, desc="MusicBrainz Recording Id", text=mb["mbid"]
            )
        if mb.get("catalog"):
            tags["TXXX:CATALOGNUMBER"] = TXXX(
                encoding=3, desc="CATALOGNUMBER", text=mb["catalog"]
            )

        # ── Cover art ─────────────────────────────────────────────────────────
        thumbnails = info.get("thumbnails") or []
        if thumbnails:
            sorted_thumbs = sorted(
                thumbnails,
                key=lambda t: (t.get("preference", 0), t.get("width", 0)),
                reverse=True,
            )
        else:
            sorted_thumbs = []

        thumb_url = info.get("thumbnail", "")
        if sorted_thumbs:
            thumb_url = sorted_thumbs[0].get("url", thumb_url)

        if thumb_url:
            try:
                req = urllib.request.Request(
                    thumb_url, headers={"User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=10) as r:
                    img_data = r.read()
                url_lower = thumb_url.lower().split("?")[0]
                if url_lower.endswith(".png"):
                    mime = "image/png"
                elif url_lower.endswith(".webp"):
                    mime = "image/webp"
                else:
                    mime = "image/jpeg"
                tags["APIC"] = APIC(
                    encoding=3, mime=mime,
                    type=3, desc="Cover", data=img_data,
                )
            except Exception as e:
                logger.warning("[AutoTag] Thumbnail download failed: %s", e)

        tags.save(str(filepath), v2_version=3)
        logger.info("[AutoTag] Tags embedded: %s (MusicBrainz: %s)",
                    filepath.name, "yes" if mb else "no")

    except Exception as exc:
        logger.error("[AutoTag] Could not embed tags in %s: %s", filepath, exc, exc_info=True)


# ── yt-dlp logger (capture erreurs par élément de playlist) ──────────────────

class _YtdlpLogger:
    """
    Logger yt-dlp compatible.
    Capture les messages d'erreur et les reporte via item_error sur le worker.
    """
    def __init__(self, worker: "DownloadWorker") -> None:
        self._worker = worker

    def debug(self, msg: str) -> None:
        if msg.startswith("[debug]"):
            return
        logger.debug("[yt-dlp] %s", msg)

    def info(self, msg: str) -> None:
        logger.debug("[yt-dlp] %s", msg)

    def warning(self, msg: str) -> None:
        logger.warning("[yt-dlp] %s", msg)

    def error(self, msg: str) -> None:
        logger.error("[yt-dlp] %s", msg)
        # Émet item_error pour afficher l'erreur dans la file UI
        self._worker._errors.append({"title": "?", "error": msg})
        self._worker.item_error.emit("?", msg[:120])


# ── Download Worker ───────────────────────────────────────────────────────────

class DownloadWorker(QThread):
    progress      = pyqtSignal(int)
    speed         = pyqtSignal(str)
    eta           = pyqtSignal(str)
    status        = pyqtSignal(str, str)          # (message, level)
    item_error    = pyqtSignal(str, str)          # (title, error_msg) — erreur sur un élément playlist
    finished      = pyqtSignal(bool, str)         # (success, output_path ou rapport)

    def __init__(
        self,
        url           : str,
        output_dir    : str | Path,
        mode          : str = "audio",
        options       : AdvancedOptions | None = None,
        playlist_mode : bool = False,
        auto_tag      : bool = True,
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
        self._final_mp3    = ""
        self._errors: list[dict] = []   # [{title, url, error}] collectés en mode ignore_errors

    def cancel(self) -> None:
        self._cancelled = True

    def cleanup(self) -> None:
        try:
            for f in self.output_dir.glob("*.part"):
                f.unlink(missing_ok=True)
            for f in self.output_dir.glob("*.ytdl"):
                f.unlink(missing_ok=True)
        except Exception as exc:
            logger.error("[DownloadWorker.cleanup] %s", exc)

# ── yt-dlp hooks ─────────────────────────────────────────────────────────

    def _error_hook(self, d: dict) -> None:
        """
        Appelé par yt-dlp pour chaque erreur en mode ignoreerrors=True.
        """
        info  = d.get("info_dict", {})
        title = info.get("title") or info.get("id") or "?"
        error = d.get("error", "Unknown error")
        self._errors.append({"title": title, "error": str(error)})
        self.item_error.emit(title, str(error))
        logger.warning("Playlist item skipped: %s — %s", title, error)

    def _progress_hook(self, d: dict) -> None:
        """Called during download — tracks progress and pre-FFmpeg filename."""
        if self._cancelled:
            raise Exception("Download cancelled by user")

        s = d.get("status", "")
        if s == "downloading":
            # On nettoie la chaîne de pourcentage (ex: " 45.2%")
            pct_raw = d.get("_percent_str", "0%").strip().rstrip("%")
            try:
                self.progress.emit(int(float(pct_raw)))
            except (ValueError, TypeError):
                pass
            
            self.speed.emit(d.get("_speed_str", "").strip())
            self.eta.emit(d.get("_eta_str", "").strip())
            
        elif s == "finished":
            # Chemin temporaire avant conversion
            self._output_path = d.get("filename", "")

    def _postprocessor_hook(self, d: dict) -> None:
        """
        Appelé APRÈS chaque post-processeur (ex: FFmpeg).
        C'est ici qu'on récupère le chemin final du fichier .mp3.
        """
        if d.get("status") == "finished":
            fp = (
                d.get("info_dict", {}).get("filepath")
                or d.get("filename", "")
            )
            if fp:
                self._final_mp3 = fp

    def _build_ydl_opts(self) -> dict:
        o = self.options
        out_dir = self.output_dir

        if self.playlist_mode:
            out_template = str(out_dir / "%(playlist_title|NA)s" / "%(title)s.%(ext)s")
        else:
            out_template = str(out_dir / "%(title)s.%(ext)s")

        out_dir.mkdir(parents=True, exist_ok=True)

        ffmpeg_loc = cfg.ffmpeg_path
        if not ffmpeg_loc:
            exe_dir = Path(getattr(os, "frozen_path", Path(__file__).parent))
            candidate = exe_dir / "ffmpeg.exe"
            if candidate.exists():
                ffmpeg_loc = str(candidate)

        opts: dict = {
            "outtmpl"            : out_template,
            "progress_hooks"     : [self._progress_hook],
            "postprocessor_hooks": [self._postprocessor_hook],
            "noplaylist"         : not self.playlist_mode,
            "quiet"              : False,
            "noprogress"         : True,
            "no_warnings"        : True,
            "restrictfilenames"  : True,
            # Passe un logger yt-dlp pour capturer les erreurs par élément
            "logger"             : _YtdlpLogger(self),
        }

        # ── Mode tolérant aux erreurs (ignoreerrors) ──────────────────────────
        # Activé dès que l'option est cochée, indépendamment du mode playlist.
        if self.options.ignore_errors:
            opts["ignoreerrors"] = True

        if ffmpeg_loc:
            opts["ffmpeg_location"] = ffmpeg_loc

        if o.cookies_file:
            opts["cookiefile"] = o.cookies_file
        elif o.browser_cookies and BROWSER_COOKIE3_AVAILABLE:
            opts["cookiesfrombrowser"] = (o.browser_cookies,)

        if self.mode == "audio":
            opts["format"] = "bestaudio/best"
            # Déterminer le codec audio cible
            audio_fmt = (o.output_format or "mp3").lower()
            # Formats supportés par FFmpegExtractAudio
            _lossless = {"flac", "wav", "alac"}
            _extract_codecs = {"mp3", "aac", "flac", "wav", "opus", "vorbis", "m4a", "ogg"}
            if audio_fmt == "ogg":
                codec = "vorbis"
            elif audio_fmt == "m4a":
                codec = "m4a"
            elif audio_fmt in _extract_codecs:
                codec = audio_fmt
            else:
                codec = "mp3"  # fallback

            pp_extract: dict = {"key": "FFmpegExtractAudio", "preferredcodec": codec}
            if codec not in _lossless:
                pp_extract["preferredquality"] = o.audio_bitrate.rstrip("k")
            opts["postprocessors"] = [
                pp_extract,
                {"key": "FFmpegMetadata", "add_metadata": True},
            ]
            if o.embed_thumbnail:
                opts["writethumbnail"] = True
                opts["postprocessors"].append(
                    {"key": "EmbedThumbnail", "already_have_thumbnail": False}
                )
        else:
            res_map = {
                "best": "bestvideo+bestaudio/best",
                "1080": "bestvideo[height<=1080]+bestaudio/best",
                "720" : "bestvideo[height<=720]+bestaudio/best",
                "480" : "bestvideo[height<=480]+bestaudio/best",
                "360" : "bestvideo[height<=360]+bestaudio/best",
            }
            opts["format"] = res_map.get(o.max_resolution, "bestvideo+bestaudio/best")
            # Format de conteneur vidéo
            video_fmt = (o.output_format or "mp4").lower()
            if video_fmt == "mkv":
                # MKV : stream copy sans re-encodage
                opts["merge_output_format"] = "mkv"
            elif video_fmt == "webm":
                opts["merge_output_format"] = "webm"
            elif video_fmt in ("avi", "mov"):
                opts["merge_output_format"] = video_fmt
            else:
                opts["merge_output_format"] = "mp4"
            opts["postprocessors"] = [
                {"key": "FFmpegMetadata", "add_metadata": True},
            ]
            if o.embed_thumbnail:
                opts["writethumbnail"] = True
                opts["postprocessors"].append(
                    {"key": "EmbedThumbnail", "already_have_thumbnail": False}
                )

        return opts

    # ── Thread entry point ────────────────────────────────────────────────────

    def run(self) -> None:
        if not YT_DLP_AVAILABLE:
            self.finished.emit(False, "yt-dlp not installed")
            return

        try:
            logger.info("Download started: %s [mode=%s]", self.url, self.mode)
            self.status.emit("Starting download…", "info")
            opts      = self._build_ydl_opts()
            info_dict : dict = {}

            with yt_dlp.YoutubeDL(opts) as ydl:
                info_dict = ydl.extract_info(self.url, download=True) or {}

            if self._cancelled:
                self.cleanup()
                self.finished.emit(False, "Cancelled")
                return

            # ── Resolve final output path ──────────────────────────────────────
            # Priority: postprocessor hook path > progress hook path > output_dir
            if self._final_mp3:
                out_path = Path(self._final_mp3)
            elif self._output_path:
                # Pre-FFmpeg path — for audio, try changing suffix to .mp3
                raw = Path(self._output_path)
                if self.mode == "audio" and raw.suffix.lower() != ".mp3":
                    mp3_guess = raw.with_suffix(".mp3")
                    out_path = mp3_guess if mp3_guess.exists() else raw
                else:
                    out_path = raw
            else:
                out_path = self.output_dir

            # ── Smart ID3 auto-tagging ──────────────────────────────────────────
            if self.mode == "audio" and self.auto_tag and cfg.auto_tag:
                # Use the definitive MP3 path from postprocessor_hook when possible
                mp3_path = (
                    Path(self._final_mp3)
                    if self._final_mp3
                    else out_path
                )
                # Ensure .mp3 extension
                if mp3_path.suffix.lower() != ".mp3":
                    mp3_path = mp3_path.with_suffix(".mp3")

                if mp3_path.exists():
                    self.status.emit("🏷  Embedding ID3 tags & cover art…", "info")
                    _embed_id3_tags(mp3_path, info_dict)
                else:
                    logger.warning("[AutoTag] MP3 not found at: %s", mp3_path)

            # ── History ────────────────────────────────────────────────────────
            history.add(
                url   = self.url,
                title = sanitize_filename(info_dict.get("title", self.url)),
                path  = str(out_path),
                mode  = self.mode,
            )

            self.status.emit("Download complete", "ok")
            logger.info("Download finished: %s → %s", self.url, out_path)

            # ── Rapport d'erreurs playlist ─────────────────────────────────────
            if self._errors:
                n = len(self._errors)
                report = (
                    f"✔  Téléchargement terminé — {n} élément(s) ignoré(s) :\n"
                    + "\n".join(
                        f"  • {e['title']}: {e['error'][:80]}"
                        for e in self._errors
                    )
                )
                self.finished.emit(True, report)
            else:
                self.finished.emit(True, str(out_path))

        except Exception as exc:
            msg = str(exc)
            if self._cancelled:
                self.cleanup()
                self.finished.emit(False, "Cancelled")
            else:
                logger.error("Download failed: %s — %s", self.url, msg, exc_info=True)
                self.status.emit(f"Error: {msg}", "err")
                self.finished.emit(False, msg)


# ── Queue item ────────────────────────────────────────────────────────────────

@dataclass
class QueueItem:
    url    : str
    mode   : str
    status : str = "pending"
    title  : str = ""
    worker : DownloadWorker | None = field(default=None, repr=False)


# ── yt-dlp update worker ──────────────────────────────────────────────────────

class YtdlpUpdateWorker(QThread):
    finished = pyqtSignal(bool, str)

    def run(self) -> None:
        try:
            import subprocess, sys as _sys
            result = subprocess.run(
                [_sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
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
                data   = json.loads(r.read())
                latest = data.get("tag_name", "").lstrip("v")
                if latest and latest != self._current:
                    self.update_available.emit(latest)
                else:
                    self.up_to_date.emit()
        except Exception:
            self.up_to_date.emit()


# ── Browser cookie worker ─────────────────────────────────────────────────────

class BrowserCookieWorker(QThread):
    finished = pyqtSignal(bool, str)

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
            cookies = getter()
            tmp = tempfile.NamedTemporaryFile(
                suffix=".txt", delete=False, mode="w", encoding="utf-8"
            )
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
