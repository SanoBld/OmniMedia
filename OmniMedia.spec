# -*- mode: python ; coding: utf-8 -*-
# OmniMedia.spec — PyInstaller build script for OmniMedia v4
#
# Build command:
#   pyinstaller OmniMedia.spec
#
# The output is a single self-contained executable:
#   dist/OmniMedia.exe   (Windows)
#   dist/OmniMedia       (macOS / Linux)
#
# ─── Notes ────────────────────────────────────────────────────────────────────
# • FFmpeg is NOT bundled here (licensing). Users must place ffmpeg.exe
#   alongside OmniMedia.exe OR have it in PATH.
#   The app will detect ffmpeg.exe in its own directory automatically.
# • yt-dlp is bundled as a Python package (hidden import below).
# • All image / style assets are included via the datas list.
# ──────────────────────────────────────────────────────────────────────────────

import sys
from pathlib import Path

block_cipher = None

# ── Collect datas (resources) ─────────────────────────────────────────────────
# Format: (source_glob_or_file, destination_folder_inside_bundle)

datas = [
    # Application icon
    ("logoOmniMedia.png", "."),
]

# ── Hidden imports ────────────────────────────────────────────────────────────
# Modules that PyInstaller cannot detect through static analysis.

hidden_imports = [
    # yt-dlp extractors (large but required)
    "yt_dlp",
    "yt_dlp.extractor",
    "yt_dlp.extractor._extractors",
    "yt_dlp.postprocessor",
    "yt_dlp.downloader",
    "yt_dlp.utils",
    # mutagen codecs
    "mutagen",
    "mutagen.id3",
    "mutagen.mp3",
    "mutagen.flac",
    "mutagen.mp4",
    "mutagen.ogg",
    # PyQt6 sub-modules sometimes missed
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.QtNetwork",
    # System theme detection
    "darkdetect",
    # Optional browser cookies
    "browser_cookie3",
    # Stdlib modules occasionally missed in one-file mode
    "json",
    "pathlib",
    "subprocess",
    "urllib.request",
    "ctypes",
    "ctypes.wintypes",
    "winreg",   # Windows only — silently ignored on macOS/Linux
]

# ── Analysis ──────────────────────────────────────────────────────────────────

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy unused packages to reduce exe size
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "PIL",       # Pillow (not used)
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

# ── One-File executable ───────────────────────────────────────────────────────

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="OmniMedia",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,           # UPX compression — reduces exe size by ~30 %
                        # Install UPX from https://upx.github.io/
    upx_exclude=[
        # Some Qt DLLs crash when compressed with UPX — exclude them
        "qwindows.dll",
        "qoffscreen.dll",
    ],
    runtime_tmpdir=None,
    console=False,      # no terminal window for end-users
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # ── Windows-specific ──────────────────────────────────────────────────────
    icon="logoOmniMedia.png",        # .ico recommended; .png accepted by newer PyInstaller
    version_file=None,               # optional: add a version_info.txt here
    uac_admin=False,                 # do NOT request admin — breaks portability
    uac_uiaccess=False,
)
