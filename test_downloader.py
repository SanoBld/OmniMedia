"""
tests/test_downloader.py — OmniMedia v4.5
Unit tests for the non-UI logic in downloader.py.
Run with:  pytest tests/
"""
import pytest
from downloader import sanitize_filename, DownloadHistory
import tempfile, json
from pathlib import Path


# ── sanitize_filename ─────────────────────────────────────────────────────────

class TestSanitizeFilename:
    def test_forbidden_chars_replaced(self):
        assert "\\" not in sanitize_filename("a\\b/c:d*e?f\"g<h>i|j")
        assert "/" not in sanitize_filename("a\\b/c:d*e?f\"g<h>i|j")

    def test_whitespace_collapsed(self):
        result = sanitize_filename("  hello   world  ")
        assert result == "hello world"

    def test_max_length_respected(self):
        long_name = "a" * 300
        result = sanitize_filename(long_name, max_length=200)
        assert len(result) <= 200

    def test_empty_string_becomes_download(self):
        assert sanitize_filename("") == "download"
        assert sanitize_filename("   ") == "download"

    def test_only_forbidden_chars_becomes_download(self):
        # All chars replaced → stripped → empty → "download"
        assert sanitize_filename("\\/:*?\"<>|") == "download"

    def test_normal_name_unchanged(self):
        assert sanitize_filename("My Song Title") == "My Song Title"

    def test_unicode_preserved(self):
        assert sanitize_filename("Ça va — été") == "Ça va — été"


# ── DownloadHistory ───────────────────────────────────────────────────────────

class TestDownloadHistory:
    def _make_history(self, tmp_path: Path) -> DownloadHistory:
        """Patch CONFIG_DIR to a temp directory and return a fresh DownloadHistory."""
        import downloader as dl_mod
        dl_mod.CONFIG_DIR   = tmp_path
        dl_mod.HISTORY_FILE = tmp_path / "history.json"
        return dl_mod.DownloadHistory()

    def test_add_and_retrieve(self, tmp_path):
        h = self._make_history(tmp_path)
        h.add("https://example.com/v1", "Video 1", "/tmp/v1.mp4", "video")
        entries = h.all()
        assert len(entries) == 1
        assert entries[0]["url"] == "https://example.com/v1"
        assert entries[0]["mode"] == "video"

    def test_most_recent_first(self, tmp_path):
        h = self._make_history(tmp_path)
        h.add("https://a.com", "A", "/tmp/a.mp3", "audio")
        h.add("https://b.com", "B", "/tmp/b.mp3", "audio")
        assert h.all()[0]["url"] == "https://b.com"

    def test_max_200_entries(self, tmp_path):
        h = self._make_history(tmp_path)
        for i in range(210):
            h.add(f"https://x.com/{i}", f"Title {i}", f"/tmp/{i}.mp3", "audio")
        assert len(h.all()) == 200

    def test_clear(self, tmp_path):
        h = self._make_history(tmp_path)
        h.add("https://example.com", "X", "/tmp/x.mp4", "video")
        h.clear()
        assert h.all() == []

    def test_persisted_to_disk(self, tmp_path):
        h = self._make_history(tmp_path)
        h.add("https://persist.com", "Persist", "/tmp/p.mp4", "video")
        # Read raw JSON to confirm it was actually written
        data = json.loads((tmp_path / "history.json").read_text())
        assert data[0]["url"] == "https://persist.com"

    def test_corrupt_history_file_returns_empty(self, tmp_path):
        (tmp_path / "history.json").write_text("NOT JSON", encoding="utf-8")
        h = self._make_history(tmp_path)
        assert h.all() == []
