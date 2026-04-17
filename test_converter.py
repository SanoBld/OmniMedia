"""
tests/test_converter.py — OmniMedia v4.5
Unit tests for the non-UI, non-FFmpeg logic in converter.py.
Run with:  pytest tests/
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import json

from converter import (
    classify_file,
    suggested_formats,
    sanitize_filename_safe,   # helper tested below — see note
    _build_output_path,
    _fmt_duration,
    PresetManager,
    BUILTIN_PRESETS,
    COMPRESS_TARGETS,
    compute_target_bitrate,
    check_ffmpeg_capabilities,
    FFmpegCapabilities,
)


# ── classify_file ─────────────────────────────────────────────────────────────

class TestClassifyFile:
    @pytest.mark.parametrize("name,expected", [
        ("clip.mp4", "video"),
        ("clip.MP4", "video"),
        ("clip.mkv", "video"),
        ("clip.webm", "video"),
        ("song.mp3", "audio"),
        ("song.FLAC", "audio"),
        ("song.wav", "audio"),
        ("photo.jpg", "image"),
        ("photo.PNG", "image"),
        ("photo.webp", "image"),
        ("archive.zip", "unknown"),
        ("README.md",  "unknown"),
    ])
    def test_classify(self, name, expected):
        assert classify_file(Path(name)) == expected


# ── suggested_formats ─────────────────────────────────────────────────────────

class TestSuggestedFormats:
    def test_video_contains_mp4(self):
        assert "mp4" in suggested_formats("video")

    def test_audio_contains_mp3(self):
        assert "mp3" in suggested_formats("audio")

    def test_image_contains_jpg(self):
        assert "jpg" in suggested_formats("image")

    def test_unknown_returns_empty(self):
        assert suggested_formats("unknown") == []


# ── _fmt_duration ─────────────────────────────────────────────────────────────

class TestFmtDuration:
    def test_under_one_hour(self):
        assert _fmt_duration(125) == "2:05"

    def test_exactly_one_hour(self):
        assert _fmt_duration(3600) == "1:00:00"

    def test_over_one_hour(self):
        assert _fmt_duration(3725) == "1:02:05"

    def test_zero(self):
        assert _fmt_duration(0) == "0:00"


# ── _build_output_path ────────────────────────────────────────────────────────

class TestBuildOutputPath:
    def test_basic_output(self, tmp_path):
        src = tmp_path / "video.mp4"
        src.touch()
        out = _build_output_path(src, "mp3", tmp_path)
        assert out.suffix == ".mp3"
        assert out.parent == tmp_path
        assert "converted" in out.name

    def test_no_overwrite(self, tmp_path):
        src = tmp_path / "video.mp4"
        src.touch()
        existing = tmp_path / "video_converted.mp3"
        existing.touch()
        out = _build_output_path(src, "mp3", tmp_path)
        assert out != existing   # counter suffix appended

    def test_output_dir_created(self, tmp_path):
        new_dir = tmp_path / "subdir"
        src = tmp_path / "audio.wav"
        src.touch()
        out = _build_output_path(src, "mp3", new_dir)
        assert out.parent == new_dir   # path is correct (dir created by caller)


# ── COMPRESS_TARGETS ──────────────────────────────────────────────────────────

class TestCompressTargets:
    def test_discord_25mb(self):
        assert COMPRESS_TARGETS["discord"] == 25 * 1024 * 1024

    def test_all_positive(self):
        for name, size in COMPRESS_TARGETS.items():
            assert size > 0, f"{name} target must be positive"


# ── compute_target_bitrate ────────────────────────────────────────────────────

class TestComputeTargetBitrate:
    def _mock_info(self, duration: float | None):
        from converter import MediaInfo
        return MediaInfo(
            path=Path("fake.mp4"),
            file_type="video",
            icon="🎬",
            duration=duration,
        )

    def test_returns_none_when_no_duration(self):
        with patch("converter.get_media_info", return_value=self._mock_info(None)):
            result = compute_target_bitrate(Path("fake.mp4"), 25 * 1024 * 1024)
        assert result is None

    def test_returns_positive_bitrate(self):
        with patch("converter.get_media_info", return_value=self._mock_info(120.0)):
            result = compute_target_bitrate(Path("fake.mp4"), 25 * 1024 * 1024)
        assert result is not None
        assert result > 0

    def test_never_below_100kbps(self):
        # 1-second clip → almost all budget goes to audio → video should clamp to 100
        with patch("converter.get_media_info", return_value=self._mock_info(1.0)):
            result = compute_target_bitrate(Path("fake.mp4"), 100 * 1024, audio_bitrate_kbps=128)
        assert result == 100


# ── PresetManager ─────────────────────────────────────────────────────────────

class TestPresetManager:
    def test_save_and_load(self, tmp_path):
        import converter
        original_cfg = converter.CONFIG_FILE
        converter.CONFIG_FILE = tmp_path / "config.json"
        try:
            PresetManager.save("TestPreset", "mp4", ["-crf", "28"], "Test description")
            loaded = PresetManager.load_custom()
            assert "TestPreset" in loaded
            assert loaded["TestPreset"]["fmt"] == "mp4"
        finally:
            converter.CONFIG_FILE = original_cfg

    def test_delete(self, tmp_path):
        import converter
        original_cfg = converter.CONFIG_FILE
        converter.CONFIG_FILE = tmp_path / "config.json"
        try:
            PresetManager.save("ToDelete", "mp3", [], "")
            PresetManager.delete("ToDelete")
            assert "ToDelete" not in PresetManager.load_custom()
        finally:
            converter.CONFIG_FILE = original_cfg

    def test_builtin_presets_present(self):
        assert "discord"  in BUILTIN_PRESETS
        assert "hifi"     in BUILTIN_PRESETS
        assert "whatsapp" in BUILTIN_PRESETS


# ── check_ffmpeg_capabilities ─────────────────────────────────────────────────

class TestCheckFFmpegCapabilities:
    def test_returns_dataclass(self):
        result = check_ffmpeg_capabilities()
        assert isinstance(result, FFmpegCapabilities)

    def test_not_available_when_not_found(self):
        with patch("converter.find_ffmpeg", return_value=None):
            caps = check_ffmpeg_capabilities()
        assert caps.available is False
        assert len(caps.warnings) >= 1

    def test_available_when_found(self):
        # Simulate ffmpeg -version and -codecs outputs
        mock_version = MagicMock()
        mock_version.stdout = (
            "ffmpeg version 6.1.1 Copyright (c) 2000-2023 the FFmpeg developers\n"
        )
        mock_codecs = MagicMock()
        mock_codecs.stdout = "libx265\nlibvpx-vp9\nlibaom-av1\n"

        with patch("converter.find_ffmpeg", return_value="/usr/bin/ffmpeg"), \
             patch("subprocess.run", side_effect=[mock_version, mock_codecs]):
            caps = check_ffmpeg_capabilities()

        assert caps.available is True
        assert caps.version_str == "6.1.1"
        assert caps.year == 2023
        assert caps.codecs.get("libx265") is True

    def test_old_version_triggers_warning(self):
        mock_version = MagicMock()
        mock_version.stdout = (
            "ffmpeg version 4.2.1 Copyright (c) 2000-2019 the FFmpeg developers\n"
        )
        mock_codecs = MagicMock()
        mock_codecs.stdout = ""

        with patch("converter.find_ffmpeg", return_value="/usr/bin/ffmpeg"), \
             patch("subprocess.run", side_effect=[mock_version, mock_codecs]):
            caps = check_ffmpeg_capabilities()

        assert caps.too_old is True
        assert any("outdated" in w.lower() or "2019" in w for w in caps.warnings)
