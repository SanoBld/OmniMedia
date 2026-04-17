"""
tests/test_config_manager.py — OmniMedia v4.5
Unit tests for ConfigManager (read/write/reset/defaults).
Run with:  pytest tests/
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_cfg(tmp_path: Path):
    """Return a fresh ConfigManager writing to tmp_path instead of ~/.omnimedia."""
    import config_manager as cm
    cm.CONFIG_DIR    = tmp_path
    cm.SETTINGS_FILE = tmp_path / "settings.json"
    return cm.ConfigManager()


# ── Defaults ──────────────────────────────────────────────────────────────────

class TestDefaults:
    def test_language_default_is_fr(self, tmp_path):
        cfg = _make_cfg(tmp_path)
        assert cfg.language == "fr"

    def test_theme_default_is_dark(self, tmp_path):
        cfg = _make_cfg(tmp_path)
        assert cfg.theme == "dark"

    def test_max_workers_default(self, tmp_path):
        cfg = _make_cfg(tmp_path)
        assert cfg.max_workers == 3

    def test_notifications_default_true(self, tmp_path):
        cfg = _make_cfg(tmp_path)
        assert cfg.notifications is True

    def test_notif_sound_default_false(self, tmp_path):
        cfg = _make_cfg(tmp_path)
        assert cfg.notif_sound is False


# ── Persistence ───────────────────────────────────────────────────────────────

class TestPersistence:
    def test_set_saves_to_disk(self, tmp_path):
        cfg = _make_cfg(tmp_path)
        cfg.set("language", "en")
        data = json.loads((tmp_path / "settings.json").read_text())
        assert data["language"] == "en"

    def test_reload_reads_from_disk(self, tmp_path):
        cfg = _make_cfg(tmp_path)
        cfg.set("theme", "light")
        cfg2 = _make_cfg(tmp_path)   # fresh instance, same dir
        assert cfg2.theme == "light"

    def test_corrupt_settings_file_falls_back_to_defaults(self, tmp_path):
        (tmp_path / "settings.json").write_text("NOT JSON", encoding="utf-8")
        cfg = _make_cfg(tmp_path)
        assert cfg.language == "fr"   # default


# ── Property setters ──────────────────────────────────────────────────────────

class TestPropertySetters:
    def test_language_setter(self, tmp_path):
        cfg = _make_cfg(tmp_path)
        cfg.language = "de"
        assert cfg.language == "de"

    def test_window_opacity_clamped_low(self, tmp_path):
        cfg = _make_cfg(tmp_path)
        cfg.window_opacity = 10       # below 70 → clamped to 70
        assert cfg.window_opacity == 70

    def test_window_opacity_clamped_high(self, tmp_path):
        cfg = _make_cfg(tmp_path)
        cfg.window_opacity = 200      # above 100 → clamped to 100
        assert cfg.window_opacity == 100

    def test_max_workers_clamped(self, tmp_path):
        cfg = _make_cfg(tmp_path)
        cfg.max_workers = 99          # above 8 → clamped to 8
        assert cfg.max_workers == 8
        cfg.max_workers = 0           # below 1 → clamped to 1
        assert cfg.max_workers == 1

    def test_ffmpeg_threads_clamped(self, tmp_path):
        cfg = _make_cfg(tmp_path)
        cfg.ffmpeg_threads = 100
        assert cfg.ffmpeg_threads == 32


# ── update() and reset() ──────────────────────────────────────────────────────

class TestUpdateReset:
    def test_update_multiple_keys(self, tmp_path):
        cfg = _make_cfg(tmp_path)
        cfg.update({"language": "ja", "theme": "light", "max_workers": 2})
        assert cfg.language == "ja"
        assert cfg.theme == "light"
        assert cfg.max_workers == 2

    def test_reset_restores_defaults(self, tmp_path):
        cfg = _make_cfg(tmp_path)
        cfg.language = "en"
        cfg.theme = "light"
        cfg.reset()
        assert cfg.language == "fr"
        assert cfg.theme == "dark"

    def test_reset_persisted(self, tmp_path):
        cfg = _make_cfg(tmp_path)
        cfg.language = "en"
        cfg.reset()
        cfg2 = _make_cfg(tmp_path)
        assert cfg2.language == "fr"


# ── Notification granularity ──────────────────────────────────────────────────

class TestNotifications:
    def test_granular_flags_independent(self, tmp_path):
        cfg = _make_cfg(tmp_path)
        cfg.notif_on_download = False
        assert cfg.notif_on_download is False
        assert cfg.notif_on_convert is True   # unchanged

    def test_master_switch_persisted(self, tmp_path):
        cfg = _make_cfg(tmp_path)
        cfg.notifications = False
        cfg2 = _make_cfg(tmp_path)
        assert cfg2.notifications is False
