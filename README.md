# 🎞 OmniMedia Converter & Downloader

> Application de bureau professionnelle pour télécharger et convertir des médias.  
> Construite avec **PyQt6**, **yt-dlp** et **FFmpeg**.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![PyQt6](https://img.shields.io/badge/PyQt6-6.6%2B-green?logo=qt)
![License](https://img.shields.io/badge/License-MIT-lightgrey)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-informational)

---

## ✨ Fonctionnalités

| Catégorie | Détails |
|---|---|
| **Téléchargement** | Coller n'importe quelle URL (YouTube, Vimeo, SoundCloud, 1000+ sites) |
| **Formats DL** | Vidéo MP4 (meilleure qualité) ou Audio MP3 (192 kbps) |
| **Threads** | Téléchargement non-bloquant — l'interface reste réactive |
| **Conversion** | Glisser-déposer (Drag & Drop) ou parcourir les fichiers |
| **Images** | `.webp` → `.jpg` / `.png` / `.bmp` / `.webp` |
| **Vidéos** | `.mp4` ↔ `.mkv` / `.avi` / `.webm` / `.mp3` / `.gif` |
| **Audio** | `.mp3` ↔ `.wav` / `.aac` / `.flac` / `.ogg` |
| **Progression** | Barre de progression en temps réel avec vitesse et ETA |
| **Dark Mode** | Interface sombre moderne avec coins arrondis |
| **Historique** | Journal des fichiers téléchargés / convertis |
| **Notifications** | Badges de statut colorés (succès, erreur, avertissement) |
| **Dossier** | Bouton « Ouvrir le dossier » post-opération |

---

## 📋 Prérequis

### 1. Python 3.10+

Téléchargez Python depuis [python.org](https://www.python.org/downloads/).

### 2. FFmpeg *(obligatoire pour la conversion et le téléchargement MP4)*

FFmpeg doit être installé **séparément** et accessible dans votre `PATH`.

<details>
<summary><b>🪟 Windows</b></summary>

**Option A — winget :**
```powershell
winget install ffmpeg
```

**Option B — Chocolatey :**
```powershell
choco install ffmpeg
```

**Option C — Manuel :**
1. Téléchargez depuis [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/)
2. Extrayez l'archive, ex. dans `C:\ffmpeg\`
3. Ajoutez `C:\ffmpeg\bin` à votre variable d'environnement `PATH`

Vérifiez l'installation :
```powershell
ffmpeg -version
```
</details>

<details>
<summary><b>🍎 macOS</b></summary>

```bash
brew install ffmpeg
```
</details>

<details>
<summary><b>🐧 Linux (Debian/Ubuntu)</b></summary>

```bash
sudo apt update && sudo apt install ffmpeg
```
</details>

---

## 🚀 Installation

```bash
# 1. Clonez le dépôt
git clone https://github.com/votre-user/omnimedia.git
cd omnimedia

# 2. (Recommandé) Créez un environnement virtuel
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Installez les dépendances Python
pip install -r requirements.txt

# 4. Lancez l'application
python main.py
```

---

## 📁 Structure du projet

```
OmniMedia/
├── main.py           # Point d'entrée — fenêtre principale, onglets Download & Convert
├── ui_styles.py      # Feuille de style QSS Dark Mode, tokens de couleurs, badges
├── downloader.py     # Logique yt-dlp — DownloadWorker (QThread)
├── converter.py      # Logique FFmpeg — ConvertWorker (QThread)
├── requirements.txt  # Dépendances Python
└── README.md         # Ce fichier
```

---

## 🖥 Utilisation

### Onglet Télécharger

1. Collez une URL dans le champ (ou cliquez **📋 Coller**).
2. Choisissez **Vidéo (MP4)** ou **Audio (MP3)**.
3. Optionnellement, changez le dossier de destination.
4. Cliquez **⬇ Télécharger**.
5. Suivez la progression en temps réel.
6. Cliquez **📂 Ouvrir le dossier** pour accéder au fichier.

### Onglet Convertir

1. **Glissez** un fichier dans la zone de dépôt *ou* cliquez **📂 Parcourir…**.
2. L'application détecte automatiquement le type (image / vidéo / audio).
3. Sélectionnez le format de sortie dans la liste déroulante.
4. Cliquez **🔄 Convertir**.
5. Suivez la progression (basée sur la durée réelle via FFmpeg).
6. Cliquez **📂 Ouvrir le dossier** pour accéder au résultat.

---

## 🔧 Dépannage

| Symptôme | Solution |
|---|---|
| Badge `FFmpeg ✗` rouge | FFmpeg absent du PATH — voir section Installation |
| Badge `yt-dlp ✗` rouge | `pip install yt-dlp` |
| Erreur `403 Forbidden` | Mettez yt-dlp à jour : `pip install -U yt-dlp` |
| Conversion GIF très lente | Normal — le GIF nécessite deux passes FFmpeg |
| Interface qui ne s'affiche pas | Vérifiez PyQt6 : `pip install PyQt6` |

---

## 📦 Sites supportés (téléchargement)

yt-dlp supporte plus de **1000 sites** :  
YouTube, Vimeo, Dailymotion, SoundCloud, Twitch, Twitter/X, Instagram, TikTok, Reddit, Bandcamp, et bien d'autres.

Consultez la [liste complète](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md).

---

## 🛡 Avertissement légal

Cet outil est destiné à un usage **personnel et éducatif**.  
Respectez les droits d'auteur et les conditions d'utilisation des plateformes.  
Ne téléchargez que du contenu dont vous avez le droit de disposer.

---

## 📄 Licence

MIT © 2024 — Libre d'utilisation, de modification et de distribution.
