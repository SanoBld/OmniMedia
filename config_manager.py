"""
config_manager.py — OmniMedia v4
Centralizes all persistent settings in ~/.omnimedia/settings.json.
Provides path helpers for PyInstaller bundle compatibility.
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
    """
    Return the absolute path to a bundled resource.
    Works both in script mode and in a PyInstaller one-file .exe
    (sys._MEIPASS points to the temp extraction folder).
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base / relative


# ── Defaults ──────────────────────────────────────────────────────────────────

_DEFAULTS: dict[str, Any] = {
    "language"          : "en",          # "en" | "fr"
    "theme"             : "dark",        # "dark" | "oled" | "light" | "auto"
    "download_dir"      : str(Path.home() / "Downloads" / "OmniMedia"),
    "ffmpeg_path"       : "",            # "" → auto-detect
    "max_workers"       : 3,             # parallel download threads
    "notifications"     : True,
    "embed_thumbnail"   : True,
    "auto_tag"          : True,          # smart ID3 auto-tagging
    "playlist_mode"     : False,         # create sub-folder for playlists
    "compress_target"   : "",            # "" | "discord" | "whatsapp" | "email"
}


# ── Manager ───────────────────────────────────────────────────────────────────

class ConfigManager:
    """Singleton-like settings store. Use the module-level `cfg` instance."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = dict(_DEFAULTS)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            self._data.update(stored)
        except Exception:
            pass  # first run or corrupt file → use defaults

    def save(self) -> None:
        """Persist current settings to disk."""
        try:
            SETTINGS_FILE.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            print(f"[ConfigManager] Could not save settings: {exc}")

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default if default is not None else _DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()

    def update(self, mapping: dict[str, Any]) -> None:
        self._data.update(mapping)
        self.save()

    def reset(self) -> None:
        """Restore factory defaults and save."""
        self._data = dict(_DEFAULTS)
        self.save()

    # ── Convenience properties ─────────────────────────────────────────────────

    @property
    def language(self) -> str:
        return self._data.get("language", "en")

    @language.setter
    def language(self, v: str) -> None:
        self.set("language", v)

    @property
    def theme(self) -> str:
        return self._data.get("theme", "dark")

    @theme.setter
    def theme(self, v: str) -> None:
        self.set("theme", v)

    @property
    def download_dir(self) -> Path:
        return Path(self._data.get("download_dir", _DEFAULTS["download_dir"]))

    @download_dir.setter
    def download_dir(self, v: str | Path) -> None:
        self.set("download_dir", str(v))

    @property
    def ffmpeg_path(self) -> str:
        return self._data.get("ffmpeg_path", "")

    @ffmpeg_path.setter
    def ffmpeg_path(self, v: str) -> None:
        self.set("ffmpeg_path", v)

    @property
    def notifications(self) -> bool:
        return bool(self._data.get("notifications", True))

    @notifications.setter
    def notifications(self, v: bool) -> None:
        self.set("notifications", v)

    @property
    def auto_tag(self) -> bool:
        return bool(self._data.get("auto_tag", True))

    @auto_tag.setter
    def auto_tag(self, v: bool) -> None:
        self.set("auto_tag", v)

    @property
    def playlist_mode(self) -> bool:
        return bool(self._data.get("playlist_mode", False))

    @playlist_mode.setter
    def playlist_mode(self, v: bool) -> None:
        self.set("playlist_mode", v)

    @property
    def compress_target(self) -> str:
        return self._data.get("compress_target", "")

    @compress_target.setter
    def compress_target(self, v: str) -> None:
        self.set("compress_target", v)

    @property
    def max_workers(self) -> int:
        return int(self._data.get("max_workers", 3))

    @max_workers.setter
    def max_workers(self, v: int) -> None:
        self.set("max_workers", max(1, min(v, 8)))


# ── Module-level singleton ────────────────────────────────────────────────────

cfg = ConfigManager()
