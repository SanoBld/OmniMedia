# -*- mode: python ; coding: utf-8 -*-
# OmniMedia.spec — PyInstaller build script for OmniMedia v4.5
#
# TWO BUILD PROFILES (set via environment variable or edit BUNDLE_FFMPEG below):
#
#   Standard build  — FFmpeg NOT included (smaller exe, ~60 MB)
#     pyinstaller OmniMedia.spec
#
#   Complete build  — FFmpeg binaries bundled inside the exe (no setup for users)
#     set OMNIMEDIA_BUNDLE_FFMPEG=1 && pyinstaller OmniMedia.spec   (Windows)
#     OMNIMEDIA_BUNDLE_FFMPEG=1 pyinstaller OmniMedia.spec          (macOS/Linux)
#
# For the "Complete" build, place the FFmpeg binaries next to this spec file:
#   Windows : ffmpeg.exe  ffprobe.exe
#   macOS   : ffmpeg      ffprobe         (from https://evermeet.cx/ffmpeg/)
#   Linux   : ffmpeg      ffprobe         (from https://johnvansickle.com/ffmpeg/)
#
# The app detects bundled ffmpeg.exe / ffmpeg in its own directory automatically.
# ──────────────────────────────────────────────────────────────────────────────

import os
import sys
from pathlib import Path

block_cipher = None

bundle_ffmpeg = False  # Mets True si tu veux tenter d'inclure les binaires

# ── Build profile ─────────────────────────────────────────────────────────────

BUNDLE_FFMPEG: bool = os.environ.get("OMNIMEDIA_BUNDLE_FFMPEG", "0").strip() == "1"

# ── Locate FFmpeg binaries for the Complete build ─────────────────────────────

def _find_local_ffmpeg() -> list[tuple[str, str]]:
    """
    Return a list of (source_path, dest_folder) tuples for PyInstaller's
    `binaries` list.  Only called when BUNDLE_FFMPEG is True.
    Raises FileNotFoundError if the binaries are missing.
    """
    here = Path(__file__).parent
    names = (
        ["ffmpeg.exe", "ffprobe.exe"]
        if sys.platform == "win32"
        else ["ffmpeg", "ffprobe"]
    )
    result = []
    missing = []
    for name in names:
        p = here / name
        if p.exists():
            result.append((str(p), "."))
        else:
            missing.append(str(p))
    if missing:
        raise FileNotFoundError(
            f"Complete build requested but FFmpeg binaries not found:\n"
            + "\n".join(f"  {m}" for m in missing)
            + "\n\nDownload from:\n"
            + "  Windows : https://www.gyan.dev/ffmpeg/builds/ (ffmpeg-release-essentials)\n"
            + "  macOS   : https://evermeet.cx/ffmpeg/\n"
            + "  Linux   : https://johnvansickle.com/ffmpeg/\n"
        )
    return result


bundled_binaries = _find_local_ffmpeg() if BUNDLE_FFMPEG else []

if bundle_ffmpeg:
    # ton code pour inclure ffmpeg ici
    print("\n[OmniMedia.spec] Bundling FFmpeg...\n")
else:
    print("\n[OmniMedia.spec] INFO: Standard build - FFmpeg NOT bundled...\n")

# ── Collect datas (resources) ─────────────────────────────────────────────────

datas = [
    ("logoOmniMedia.png", "."),
]

# ── Hidden imports ────────────────────────────────────────────────────────────

hidden_imports = [
    # yt-dlp
    "yt_dlp",
    "yt_dlp.extractor",
    "yt_dlp.extractor._extractors",
    "yt_dlp.postprocessor",
    "yt_dlp.downloader",
    "yt_dlp.utils",
    # mutagen
    "mutagen",
    "mutagen.id3",
    "mutagen.mp3",
    "mutagen.flac",
    "mutagen.mp4",
    "mutagen.ogg",
    # PyQt6
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.QtNetwork",
    # Misc
    "darkdetect",
    "browser_cookie3",
    "logging.handlers",     # RotatingFileHandler used by app_logger
    "json",
    "pathlib",
    "subprocess",
    "urllib.request",
    "ctypes",
    "ctypes.wintypes",
    "winreg",
]

# ── Analysis ──────────────────────────────────────────────────────────────────

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=bundled_binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "tkinter",
        "test",
        "unittest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── Exe name reflects build profile ──────────────────────────────────────────

exe_name = "OmniMedia-Complete" if BUNDLE_FFMPEG else "OmniMedia"

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=exe_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        "qwindows.dll",
        "qoffscreen.dll",
        # Never UPX-compress the bundled FFmpeg — it breaks the binary
        "ffmpeg.exe",
        "ffprobe.exe",
        "ffmpeg",
        "ffprobe",
    ],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="logoOmniMedia.png",
    version_file=None,
    uac_admin=False,
    uac_uiaccess=False,
)
