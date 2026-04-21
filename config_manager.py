"""
config_manager.py — OmniMedia v4.1
Centralizes all persistent settings in ~/.omnimedia/settings.json.
Provides path helpers for PyInstaller bundle compatibility.
Added: granular notification preferences (notif_on_download, notif_on_convert,
       notif_on_error, notif_sound).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# ── Paths ─────────────────────────────────────────────────────────────────────

CONFIG_DIR   : Path = Path.home() / ".omnimedia"
SETTINGS_FILE: Path = CONFIG_DIR / "settings.json"


def resource_path(relative: str | Path) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base / relative


# ── Defaults ──────────────────────────────────────────────────────────────────

_DEFAULTS: dict[str, Any] = {
    "language"           : "fr",
    "theme"              : "dark",
    "download_dir"       : str(Path.home() / "Downloads" / "OmniMedia"),
    "auto_subfolders"    : False,
    "file_naming"        : "title",       # "title" | "artist_title"
    "ffmpeg_path"        : "",
    "ffmpeg_threads"     : 0,             # 0 = auto
    "ffmpeg_priority"    : "normal",      # "low" | "normal" | "high"
    "delete_source"      : False,
    "max_workers"        : 3,
    "preferred_quality"  : "best",        # best | 2160 | 1080 | 720 | 480
    "browser_cookies"    : "",            # chrome | firefox | edge | brave | opera | ""
    # ── Notifications ──────────────────────────────────────────────────────
    "notifications"      : True,
    "notif_on_download"  : True,
    "notif_on_convert"   : True,
    "notif_on_error"     : True,
    "notif_sound"        : False,
    "notif_tray_bg"      : True,
    # ── Interface ──────────────────────────────────────────────────────────
    "animations_enabled" : True,
    "ignore_errors"      : True,
    # ── Téléchargement — options avancées persistées ────────────────────────
    "dl_audio_bitrate"   : "192k",        # bitrate audio par défaut
    "dl_max_resolution"  : "best",        # résolution vidéo par défaut
    "dl_mode"            : "video",       # "video" | "audio"
    "dl_playlist_items"  : "",            # plage items playlist
    # ── Other ──────────────────────────────────────────────────────────────
    "embed_thumbnail"    : True,
    "auto_tag"           : True,
    "playlist_mode"      : False,
    "compress_target"    : "",
    "minimize_to_tray"   : False,
    "start_in_tray"      : False,
    # ── Conversion ─────────────────────────────────────────────────────────
    "conv_last_format"   : "mp4",         # dernier format de sortie utilisé
    "conv_last_preset"   : "custom",      # dernier preset utilisé
    # ── Compression ────────────────────────────────────────────────────────
    "comp_last_platform" : "discord",     # dernière plateforme sélectionnée
    "comp_audio_kbps"    : 128,           # qualité audio compression
}


# ── Manager ───────────────────────────────────────────────────────────────────

class ConfigManager:
    def __init__(self) -> None:
        self._data: dict[str, Any] = dict(_DEFAULTS)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            self._data.update(stored)
        except Exception:
            pass

    def save(self) -> None:
        try:
            SETTINGS_FILE.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            print(f"[ConfigManager] Could not save settings: {exc}")

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default if default is not None else _DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()

    def update(self, mapping: dict[str, Any]) -> None:
        self._data.update(mapping)
        self.save()

    def reset(self) -> None:
        self._data = dict(_DEFAULTS)
        self.save()

    # ── Theme / Language ──────────────────────────────────────────────────────

    @property
    def language(self) -> str: return self._data.get("language", "fr")
    @language.setter
    def language(self, v: str) -> None: self.set("language", v)

    @property
    def theme(self) -> str: return self._data.get("theme", "dark")
    @theme.setter
    def theme(self, v: str) -> None: self.set("theme", v)

    # ── Paths ─────────────────────────────────────────────────────────────────

    @property
    def download_dir(self) -> Path: return Path(self._data.get("download_dir", _DEFAULTS["download_dir"]))
    @download_dir.setter
    def download_dir(self, v: str | Path) -> None: self.set("download_dir", str(v))

    @property
    def ffmpeg_path(self) -> str: return self._data.get("ffmpeg_path", "")
    @ffmpeg_path.setter
    def ffmpeg_path(self, v: str) -> None: self.set("ffmpeg_path", v)

    # ── Apparence / Interface ─────────────────────────────────────────────────

    @property
    def auto_subfolders(self) -> bool: return bool(self._data.get("auto_subfolders", False))
    @auto_subfolders.setter
    def auto_subfolders(self, v: bool) -> None: self.set("auto_subfolders", v)

    @property
    def file_naming(self) -> str: return self._data.get("file_naming", "title")
    @file_naming.setter
    def file_naming(self, v: str) -> None: self.set("file_naming", v)

    # ── Download engine ───────────────────────────────────────────────────────

    @property
    def preferred_quality(self) -> str: return self._data.get("preferred_quality", "best")
    @preferred_quality.setter
    def preferred_quality(self, v: str) -> None: self.set("preferred_quality", v)

    @property
    def browser_cookies(self) -> str: return self._data.get("browser_cookies", "")
    @browser_cookies.setter
    def browser_cookies(self, v: str) -> None: self.set("browser_cookies", v)

    # ── FFmpeg / Conversion ───────────────────────────────────────────────────

    @property
    def ffmpeg_threads(self) -> int: return int(self._data.get("ffmpeg_threads", 0))
    @ffmpeg_threads.setter
    def ffmpeg_threads(self, v: int) -> None: self.set("ffmpeg_threads", max(0, min(v, 32)))

    @property
    def ffmpeg_priority(self) -> str: return self._data.get("ffmpeg_priority", "normal")
    @ffmpeg_priority.setter
    def ffmpeg_priority(self, v: str) -> None: self.set("ffmpeg_priority", v)

    @property
    def delete_source(self) -> bool: return bool(self._data.get("delete_source", False))
    @delete_source.setter
    def delete_source(self, v: bool) -> None: self.set("delete_source", v)

    # ── Tray ─────────────────────────────────────────────────────────────────

    @property
    def minimize_to_tray(self) -> bool: return bool(self._data.get("minimize_to_tray", True))
    @minimize_to_tray.setter
    def minimize_to_tray(self, v: bool) -> None: self.set("minimize_to_tray", v)

    @property
    def start_in_tray(self) -> bool: return bool(self._data.get("start_in_tray", False))
    @start_in_tray.setter
    def start_in_tray(self, v: bool) -> None: self.set("start_in_tray", v)

    # ── Notifications (master + granular) ─────────────────────────────────────

    @property
    def notifications(self) -> bool: return bool(self._data.get("notifications", True))
    @notifications.setter
    def notifications(self, v: bool) -> None: self.set("notifications", v)

    @property
    def notif_on_download(self) -> bool: return bool(self._data.get("notif_on_download", True))
    @notif_on_download.setter
    def notif_on_download(self, v: bool) -> None: self.set("notif_on_download", v)

    @property
    def notif_on_convert(self) -> bool: return bool(self._data.get("notif_on_convert", True))
    @notif_on_convert.setter
    def notif_on_convert(self, v: bool) -> None: self.set("notif_on_convert", v)

    @property
    def notif_on_error(self) -> bool: return bool(self._data.get("notif_on_error", True))
    @notif_on_error.setter
    def notif_on_error(self, v: bool) -> None: self.set("notif_on_error", v)

    @property
    def notif_sound(self) -> bool: return bool(self._data.get("notif_sound", False))
    @notif_sound.setter
    def notif_sound(self, v: bool) -> None: self.set("notif_sound", v)

    @property
    def notif_tray_bg(self) -> bool: return bool(self._data.get("notif_tray_bg", True))
    @notif_tray_bg.setter
    def notif_tray_bg(self, v: bool) -> None: self.set("notif_tray_bg", v)

    @property
    def animations_enabled(self) -> bool: return bool(self._data.get("animations_enabled", True))
    @animations_enabled.setter
    def animations_enabled(self, v: bool) -> None: self.set("animations_enabled", v)

    # ── Features ──────────────────────────────────────────────────────────────

    @property
    def auto_tag(self) -> bool: return bool(self._data.get("auto_tag", True))
    @auto_tag.setter
    def auto_tag(self, v: bool) -> None: self.set("auto_tag", v)

    @property
    def playlist_mode(self) -> bool: return bool(self._data.get("playlist_mode", False))
    @playlist_mode.setter
    def playlist_mode(self, v: bool) -> None: self.set("playlist_mode", v)

    @property
    def compress_target(self) -> str: return self._data.get("compress_target", "")
    @compress_target.setter
    def compress_target(self, v: str) -> None: self.set("compress_target", v)

    @property
    def max_workers(self) -> int: return int(self._data.get("max_workers", 3))
    @max_workers.setter
    def max_workers(self, v: int) -> None: self.set("max_workers", max(1, min(v, 8)))


cfg = ConfigManager()
