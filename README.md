# 🎞 OmniMedia Converter & Downloader

> A desktop application to download and convert media files.  
> Built with **PyQt6**, **yt-dlp**, and **FFmpeg**.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![PyQt6](https://img.shields.io/badge/PyQt6-6.6%2B-green?logo=qt)
![License](https://img.shields.io/badge/License-MIT-lightgrey)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-informational)

---

## ✨ Features

| Category | Details |
|---|---|
| **Downloader** | Paste any URL (YouTube, Vimeo, SoundCloud, 1000+ sites) |
| **Advanced Options** | Custom Video Codecs (H.264, H.265, VP9) and Audio Bitrate (up to 320kbps) |
| **Multithreading** | Non-blocking operations — the UI remains perfectly fluid |
| **Converter** | Simple Drag & Drop support for files and folders |
| **Images** | Convert between `.webp`, `.jpg`, `.png`, `.bmp`, and more |
| **Videos** | `.mp4` ↔ `.mkv`, `.avi`, `.webm`, `.mp3`, `.gif` |
| **Audio** | `.mp3` ↔ `.wav`, `.aac`, `.flac`, `.ogg` |
| **Scalable UI** | 100% Responsive interface that adapts to any screen size |
| **Dark Mode v2** | Modern refined dark theme with smooth transitions |

---

## 📋 Prerequisites

### 🚀 For End-Users (.exe version)
If you downloaded the **OmniMedia.exe** from the [Releases](https://github.com/SanoBld/OmniMedia/releases) page:
* **No Python required:** You don't need to install Python or any libraries.
* **FFmpeg:** You still need FFmpeg installed on your system (see below).

### 🛠 For Developers (Source Code)
If you want to run the code manually:
1. **Python 3.10+**
2. **Install dependencies:** `pip install -r requirements.txt`

### ⚙️ FFmpeg Setup (Required for everyone)
FFmpeg is the engine used for conversion. It must be accessible in your system `PATH`.

<details>
<summary><b>🪟 Windows Setup</b></summary>

**Option A — Quick Install (Recommended):**
Open PowerShell as Administrator and type:
```powershell
winget install ffmpeg
