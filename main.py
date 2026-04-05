"""
main.py — OmniMedia Converter & Downloader v2
Améliorations : UI scalable, Options Avancées, design raffiné, downloader corrigé.
"""
from __future__ import annotations

import sys
import os
import subprocess
from pathlib import Path

# ── Vérification des dépendances AVANT tout import PyQt6 ─────────────────────
def _check_dependencies() -> None:
    missing = []
    try:
        import PyQt6  # noqa: F401
    except ImportError:
        missing.append("PyQt6")
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        missing.append("yt-dlp")

    if missing:
        pkgs = " ".join(missing)
        msg = (
            "\n"
            "╔══════════════════════════════════════════════════════════╗\n"
            "║          OmniMedia — Dépendances manquantes              ║\n"
            "╠══════════════════════════════════════════════════════════╣\n"
            f"║  Modules manquants : {', '.join(missing):<37}║\n"
            "║                                                          ║\n"
            "║  Lancez la commande suivante dans PowerShell / CMD :     ║\n"
            f"║    pip install {pkgs:<44}║\n"
            "╚══════════════════════════════════════════════════════════╝\n"
        )
        print(msg, file=sys.stderr)
        input("Appuyez sur Entrée pour fermer…")
        sys.exit(1)

_check_dependencies()
# ─────────────────────────────────────────────────────────────────────────────

from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui  import QDragEnterEvent, QDropEvent, QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QButtonGroup,
    QProgressBar, QTabWidget, QFrame, QFileDialog, QListWidget,
    QListWidgetItem, QComboBox, QGroupBox, QSizePolicy, QMessageBox,
    QScrollArea, QSpacerItem,
)

from ui_styles   import get_stylesheet, COLORS, badge_style, section_label_style
from downloader  import DownloadWorker, AdvancedOptions
from converter   import (
    ConvertWorker, classify_file, suggested_formats,
    ffmpeg_available, find_ffmpeg,
)

# ── Constantes ────────────────────────────────────────────────────────────────
APP_NAME    = "OmniMedia"
APP_VERSION = "2.0.0"
DEFAULT_DL_DIR = Path.home() / "Downloads" / "OmniMedia"


# ── Helpers globaux ───────────────────────────────────────────────────────────

def open_folder(path: str | Path) -> None:
    p = Path(path)
    target = p if p.is_dir() else p.parent
    if sys.platform == "win32":
        os.startfile(str(target))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])


def hline() -> QFrame:
    f = QFrame()
    f.setObjectName("separator")
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet(f"background:{COLORS['border']}; border:none; margin: 2px 0;")
    return f


def make_label(text: str, obj_name: str = "") -> QLabel:
    lbl = QLabel(text)
    if obj_name:
        lbl.setObjectName(obj_name)
    return lbl


def make_section_title(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(section_label_style())
    return lbl


def set_status(lbl: QLabel, text: str, kind: str = "info") -> None:
    """Met à jour un label de statut avec le bon style QSS."""
    name_map = {"info": "status_info", "ok": "status_ok", "err": "status_err"}
    lbl.setObjectName(name_map.get(kind, "status_info"))
    lbl.setText(text)
    lbl.style().unpolish(lbl)
    lbl.style().polish(lbl)


# ═══════════════════════════════════════════════════════════════════════════════
#  Widget : Panneau "Options Avancées" (collapsible)
# ═══════════════════════════════════════════════════════════════════════════════

class AdvancedPanel(QWidget):
    """Panneau d'options avancées qui s'affiche/se cache via un bouton toggle."""

    def __init__(self, show_codec: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._show_codec = show_codec
        self._setup_ui()

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        # ── Toggle button ─────────────────────────────────────────────
        self.toggle_btn = QPushButton("⚙  Options avancées  ▾")
        self.toggle_btn.setObjectName("btn_advanced")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setFixedHeight(32)
        self.toggle_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.toggle_btn.clicked.connect(self._toggle)
        outer.addWidget(self.toggle_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        # ── Panel body ────────────────────────────────────────────────
        self.panel = QFrame()
        self.panel.setObjectName("advanced_panel")
        self.panel.hide()
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(16, 14, 16, 14)
        panel_layout.setSpacing(14)

        grid = QHBoxLayout()
        grid.setSpacing(24)

        # Bitrate audio
        col_audio = QVBoxLayout()
        col_audio.setSpacing(6)
        col_audio.addWidget(make_section_title("Bitrate audio"))
        self.bitrate_combo = QComboBox()
        for label, val in [("128 kbps", "128k"), ("192 kbps (défaut)", "192k"), ("320 kbps", "320k")]:
            self.bitrate_combo.addItem(label, val)
        self.bitrate_combo.setCurrentIndex(1)
        self.bitrate_combo.setMinimumWidth(160)
        col_audio.addWidget(self.bitrate_combo)
        grid.addLayout(col_audio)

        # Codec vidéo
        if self._show_codec:
            col_codec = QVBoxLayout()
            col_codec.setSpacing(6)
            col_codec.addWidget(make_section_title("Codec vidéo"))
            self.codec_combo = QComboBox()
            for label, val in [("H.264 (compatible)", "h264"),
                                ("H.265 / HEVC (efficace)", "h265"),
                                ("VP9 (web)", "vp9")]:
                self.codec_combo.addItem(label, val)
            self.codec_combo.setMinimumWidth(190)
            col_codec.addWidget(self.codec_combo)
            grid.addLayout(col_codec)
        else:
            self.codec_combo = None  # type: ignore[assignment]

        # Résolution max
        col_res = QVBoxLayout()
        col_res.setSpacing(6)
        col_res.addWidget(make_section_title("Résolution max"))
        self.res_combo = QComboBox()
        for label, val in [("Meilleure qualité", "best"),
                            ("1080p", "1080"),
                            ("720p", "720"),
                            ("480p", "480")]:
            self.res_combo.addItem(label, val)
        self.res_combo.setMinimumWidth(160)
        col_res.addWidget(self.res_combo)
        grid.addLayout(col_res)

        grid.addStretch()
        panel_layout.addLayout(grid)
        outer.addWidget(self.panel)

    def _toggle(self) -> None:
        expanded = self.toggle_btn.isChecked()
        self.panel.setVisible(expanded)
        self.toggle_btn.setText(
            "⚙  Options avancées  ▴" if expanded else "⚙  Options avancées  ▾"
        )

    def get_options(self) -> AdvancedOptions:
        return AdvancedOptions(
            audio_bitrate  = self.bitrate_combo.currentData(),
            video_codec    = self.codec_combo.currentData() if self.codec_combo else "h264",
            max_resolution = self.res_combo.currentData(),
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  Widget : Zone Drag & Drop
# ═══════════════════════════════════════════════════════════════════════════════

class DropZone(QFrame):
    def __init__(self, on_drop, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._on_drop = on_drop
        self.setObjectName("drop_zone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        self.icon_lbl = QLabel("🗂")
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setStyleSheet("font-size:44px; background:transparent;")

        self.text_lbl = QLabel("Glissez un fichier ici")
        self.text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_lbl.setStyleSheet(
            f"font-size:15px; font-weight:600; color:{COLORS['text_primary']}; background:transparent;"
        )

        self.sub_lbl = QLabel("Images · Vidéos · Audio")
        self.sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_lbl.setStyleSheet(
            f"font-size:12px; color:{COLORS['text_muted']}; background:transparent;"
        )

        layout.addWidget(self.icon_lbl)
        layout.addWidget(self.text_lbl)
        layout.addWidget(self.sub_lbl)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("drag_active", "true")
            self.style().unpolish(self); self.style().polish(self)
            self.text_lbl.setText("Relâchez pour analyser !")
        else:
            event.ignore()

    def dragLeaveEvent(self, _) -> None:
        self.setProperty("drag_active", "false")
        self.style().unpolish(self); self.style().polish(self)
        self.text_lbl.setText("Glissez un fichier ici")

    def dropEvent(self, event: QDropEvent) -> None:
        self.setProperty("drag_active", "false")
        self.style().unpolish(self); self.style().polish(self)
        self.text_lbl.setText("Glissez un fichier ici")
        urls = event.mimeData().urls()
        if urls:
            self._on_drop(Path(urls[0].toLocalFile()))


# ═══════════════════════════════════════════════════════════════════════════════
#  Onglet Téléchargement
# ═══════════════════════════════════════════════════════════════════════════════

class DownloadTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: DownloadWorker | None = None
        self._last_file: str = ""
        self._output_dir: Path = DEFAULT_DL_DIR
        self._setup_ui()

    def _setup_ui(self) -> None:
        # Scroll area pour l'adaptabilité
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        scroll.setWidget(container)

        root_outer = QVBoxLayout(self)
        root_outer.setContentsMargins(0, 0, 0, 0)
        root_outer.addWidget(scroll)

        root = QVBoxLayout(container)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        # ── En-tête ──────────────────────────────────────────────────
        hdr = QHBoxLayout()
        icon = QLabel("⬇")
        icon.setStyleSheet("font-size:24px; background:transparent;")
        title = make_label("Télécharger un média", "title")
        hdr.addWidget(icon)
        hdr.addWidget(title)
        hdr.addStretch()
        root.addLayout(hdr)

        # ── Card principale ──────────────────────────────────────────
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(16)
        card_layout.setContentsMargins(20, 20, 20, 20)

        # URL
        card_layout.addWidget(make_section_title("URL"))
        url_row = QHBoxLayout()
        url_row.setSpacing(8)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Collez une URL YouTube, Vimeo, SoundCloud, TikTok…")
        self.url_input.setMinimumHeight(42)
        self.paste_btn = QPushButton("📋")
        self.paste_btn.setObjectName("btn_secondary")
        self.paste_btn.setFixedSize(42, 42)
        self.paste_btn.setToolTip("Coller depuis le presse-papier")
        self.paste_btn.clicked.connect(self._paste_clipboard)
        url_row.addWidget(self.url_input, 1)
        url_row.addWidget(self.paste_btn)
        card_layout.addLayout(url_row)

        card_layout.addWidget(hline())

        # Format
        card_layout.addWidget(make_section_title("Format"))
        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(16)
        self.rb_video = QRadioButton("🎬  Vidéo (MP4)")
        self.rb_audio = QRadioButton("🎵  Audio (MP3)")
        self.rb_video.setChecked(True)
        btn_grp = QButtonGroup(self)
        btn_grp.addButton(self.rb_video)
        btn_grp.addButton(self.rb_audio)
        fmt_row.addWidget(self.rb_video)
        fmt_row.addWidget(self.rb_audio)
        fmt_row.addStretch()
        card_layout.addLayout(fmt_row)

        card_layout.addWidget(hline())

        # Dossier de sortie
        card_layout.addWidget(make_section_title("Dossier de destination"))
        folder_row = QHBoxLayout()
        folder_row.setSpacing(8)
        self.folder_label = QLabel(str(self._output_dir))
        self.folder_label.setObjectName("status_info")
        self.folder_label.setWordWrap(True)
        self.folder_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        folder_btn = QPushButton("📁 Changer")
        folder_btn.setObjectName("btn_secondary")
        folder_btn.setFixedHeight(34)
        folder_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        folder_btn.clicked.connect(self._choose_folder)
        folder_row.addWidget(self.folder_label, 1)
        folder_row.addWidget(folder_btn)
        card_layout.addLayout(folder_row)

        root.addWidget(card)

        # ── Options avancées ─────────────────────────────────────────
        self.advanced = AdvancedPanel(show_codec=False)
        root.addWidget(self.advanced)

        # ── Progression ──────────────────────────────────────────────
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        root.addWidget(self.progress)

        # ── Statut ───────────────────────────────────────────────────
        status_row = QHBoxLayout()
        self.status_lbl = QLabel("Prêt.")
        self.status_lbl.setObjectName("status_info")
        self.status_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.open_btn = QPushButton("📂 Ouvrir")
        self.open_btn.setObjectName("btn_secondary")
        self.open_btn.setFixedHeight(34)
        self.open_btn.hide()
        self.open_btn.clicked.connect(self._open_output)
        status_row.addWidget(self.status_lbl, 1)
        status_row.addWidget(self.open_btn)
        root.addLayout(status_row)

        # ── Boutons action ────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.cancel_btn = QPushButton("✕ Annuler")
        self.cancel_btn.setObjectName("btn_secondary")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setFixedHeight(42)
        self.cancel_btn.clicked.connect(self._cancel)
        self.dl_btn = QPushButton("⬇  Télécharger")
        self.dl_btn.setMinimumWidth(170)
        self.dl_btn.setFixedHeight(42)
        self.dl_btn.clicked.connect(self._start_download)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.dl_btn)
        root.addLayout(btn_row)

        # ── Historique ────────────────────────────────────────────────
        root.addWidget(hline())
        root.addWidget(make_section_title("Historique"))
        self.history = QListWidget()
        self.history.setMinimumHeight(80)
        self.history.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self.history, 1)

    # ── Actions ──────────────────────────────────────────────────────────────

    def _paste_clipboard(self) -> None:
        self.url_input.setText(QApplication.clipboard().text().strip())

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choisir le dossier de sortie")
        if folder:
            self._output_dir = Path(folder)
            self.folder_label.setText(str(self._output_dir))

    def _open_output(self) -> None:
        open_folder(self._last_file or self._output_dir)

    def _set_busy(self, busy: bool) -> None:
        self.dl_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        self.url_input.setEnabled(not busy)
        self.advanced.setEnabled(not busy)
        if not busy:
            self.progress.setValue(0)

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
        self._set_busy(False)
        set_status(self.status_lbl, "Téléchargement annulé.")

    def _start_download(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            set_status(self.status_lbl, "Collez d'abord une URL.", "err")
            return

        mode = "audio" if self.rb_audio.isChecked() else "video"
        opts = self.advanced.get_options()

        self._set_busy(True)
        self.open_btn.hide()
        set_status(self.status_lbl, "Démarrage…")

        self._worker = DownloadWorker(url, self._output_dir, mode, opts, parent=self)
        self._worker.progress.connect(self.progress.setValue)
        self._worker.status.connect(self.status_lbl.setText)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_finished(self, path: str) -> None:
        self._last_file = path
        self._set_busy(False)
        self.progress.setValue(100)
        self.open_btn.show()
        name = Path(path).name
        set_status(self.status_lbl, f"✔  Téléchargé : {name}", "ok")
        item = QListWidgetItem(f"✔  {name}")
        item.setForeground(QColor(COLORS["success"]))
        self.history.insertItem(0, item)

    def _on_error(self, msg: str) -> None:
        self._set_busy(False)
        set_status(self.status_lbl, f"✗  {msg.splitlines()[0]}", "err")
        QMessageBox.critical(self, "Erreur de téléchargement", msg)


# ═══════════════════════════════════════════════════════════════════════════════
#  Onglet Conversion
# ═══════════════════════════════════════════════════════════════════════════════

class ConvertTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: ConvertWorker | None = None
        self._current_file: Path | None = None
        self._last_output: str = ""
        self._output_dir: Path = DEFAULT_DL_DIR
        self._setup_ui()

    def _setup_ui(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        scroll.setWidget(container)

        root_outer = QVBoxLayout(self)
        root_outer.setContentsMargins(0, 0, 0, 0)
        root_outer.addWidget(scroll)

        root = QVBoxLayout(container)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        # ── En-tête ──────────────────────────────────────────────────
        hdr = QHBoxLayout()
        icon = QLabel("🔄")
        icon.setStyleSheet("font-size:24px; background:transparent;")
        title = make_label("Convertir un fichier", "title")
        hdr.addWidget(icon)
        hdr.addWidget(title)
        hdr.addStretch()
        root.addLayout(hdr)

        # ── Drop zone (flexible) ──────────────────────────────────────
        self.drop_zone = DropZone(self._on_file_dropped)
        root.addWidget(self.drop_zone, 1)

        # Bouton parcourir
        browse_row = QHBoxLayout()
        browse_row.addStretch()
        browse_btn = QPushButton("📂 Parcourir…")
        browse_btn.setObjectName("btn_secondary")
        browse_btn.setFixedHeight(34)
        browse_btn.clicked.connect(self._browse_file)
        browse_row.addWidget(browse_btn)
        browse_row.addStretch()
        root.addLayout(browse_row)

        # ── Card info fichier (cachée par défaut) ─────────────────────
        self.file_card = QFrame()
        self.file_card.setObjectName("card")
        fcl = QVBoxLayout(self.file_card)
        fcl.setContentsMargins(16, 16, 16, 16)
        fcl.setSpacing(14)

        # Nom du fichier + badge type
        file_row = QHBoxLayout()
        self.file_icon = QLabel("📄")
        self.file_icon.setStyleSheet("font-size:20px; background:transparent;")
        self.file_name_lbl = QLabel("—")
        self.file_name_lbl.setStyleSheet(
            f"font-weight:600; font-size:13px; color:{COLORS['text_primary']}; background:transparent;"
        )
        self.file_name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.file_type_badge = QLabel("")
        self.file_type_badge.setFixedHeight(22)
        self.file_type_badge.setStyleSheet(badge_style("info"))
        file_row.addWidget(self.file_icon)
        file_row.addWidget(self.file_name_lbl, 1)
        file_row.addWidget(self.file_type_badge)
        fcl.addLayout(file_row)

        fcl.addWidget(hline())

        # Format + dossier de sortie
        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(12)
        fmt_row.addWidget(make_label("Convertir en :"))
        self.fmt_combo = QComboBox()
        self.fmt_combo.setMinimumWidth(140)
        fmt_row.addWidget(self.fmt_combo)
        fmt_row.addStretch()
        outdir_btn = QPushButton("📁 Dossier")
        outdir_btn.setObjectName("btn_secondary")
        outdir_btn.setFixedHeight(34)
        outdir_btn.clicked.connect(self._choose_out_folder)
        fmt_row.addWidget(outdir_btn)
        fcl.addLayout(fmt_row)

        self.file_card.hide()
        root.addWidget(self.file_card)

        # ── Options avancées ─────────────────────────────────────────
        self.advanced = AdvancedPanel(show_codec=True)
        root.addWidget(self.advanced)

        # ── Progression ──────────────────────────────────────────────
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        root.addWidget(self.progress)

        # ── Statut ───────────────────────────────────────────────────
        status_row = QHBoxLayout()
        self.status_lbl = QLabel("Glissez un fichier pour commencer.")
        self.status_lbl.setObjectName("status_info")
        self.status_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.open_btn = QPushButton("📂 Ouvrir")
        self.open_btn.setObjectName("btn_secondary")
        self.open_btn.setFixedHeight(34)
        self.open_btn.hide()
        self.open_btn.clicked.connect(self._open_output)
        status_row.addWidget(self.status_lbl, 1)
        status_row.addWidget(self.open_btn)
        root.addLayout(status_row)

        # ── Boutons action ────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.cancel_btn = QPushButton("✕ Annuler")
        self.cancel_btn.setObjectName("btn_secondary")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setFixedHeight(42)
        self.cancel_btn.clicked.connect(self._cancel)
        self.convert_btn = QPushButton("🔄  Convertir")
        self.convert_btn.setMinimumWidth(170)
        self.convert_btn.setFixedHeight(42)
        self.convert_btn.setEnabled(False)
        self.convert_btn.clicked.connect(self._start_conversion)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.convert_btn)
        root.addLayout(btn_row)

        # ── Historique ────────────────────────────────────────────────
        root.addWidget(hline())
        root.addWidget(make_section_title("Historique"))
        self.history = QListWidget()
        self.history.setMinimumHeight(80)
        self.history.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self.history, 1)

    # ── Fichier ───────────────────────────────────────────────────────────────

    def _browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir un fichier", str(Path.home()),
            "Médias (*.webp *.jpg *.jpeg *.png *.bmp *.gif *.avif "
            "*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv "
            "*.mp3 *.wav *.aac *.flac *.ogg *.m4a *.opus);;Tous (*)",
        )
        if path:
            self._on_file_dropped(Path(path))

    def _on_file_dropped(self, path: Path) -> None:
        kind = classify_file(path)
        if kind == "unknown":
            QMessageBox.warning(
                self, "Format non supporté",
                f"Le fichier « {path.name} » n'est pas reconnu.\n"
                "Formats acceptés : images, vidéos, audio.",
            )
            return

        self._current_file = path
        icons = {"image": "🖼", "video": "🎬", "audio": "🎵"}
        badge_kinds = {"image": "info", "video": "warn", "audio": "ok"}

        self.file_icon.setText(icons.get(kind, "📄"))
        self.file_name_lbl.setText(path.name)
        self.file_type_badge.setText(f"  {kind.upper()}  ")
        self.file_type_badge.setStyleSheet(badge_style(badge_kinds.get(kind, "info")))

        self.fmt_combo.clear()
        for fmt in suggested_formats(kind):
            self.fmt_combo.addItem(f".{fmt}", fmt)

        self.file_card.show()
        self.convert_btn.setEnabled(True)
        self.open_btn.hide()
        self.progress.setValue(0)
        set_status(self.status_lbl, f"Fichier chargé : {path.name}")

    def _choose_out_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Dossier de sortie")
        if folder:
            self._output_dir = Path(folder)

    def _open_output(self) -> None:
        open_folder(self._last_output or self._output_dir)

    # ── Conversion ────────────────────────────────────────────────────────────

    def _set_busy(self, busy: bool) -> None:
        self.convert_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        self.drop_zone.setEnabled(not busy)
        self.advanced.setEnabled(not busy)
        if not busy:
            self.progress.setValue(0)

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
        self._set_busy(False)
        set_status(self.status_lbl, "Conversion annulée.")

    def _start_conversion(self) -> None:
        if not self._current_file:
            return
        if not ffmpeg_available():
            QMessageBox.critical(
                self, "FFmpeg manquant",
                "FFmpeg est introuvable dans le PATH.\n\n"
                "→ Windows : winget install ffmpeg\n"
                "→ macOS   : brew install ffmpeg\n"
                "→ Linux   : sudo apt install ffmpeg",
            )
            return

        fmt = self.fmt_combo.currentData()
        self._set_busy(True)
        self.open_btn.hide()
        set_status(self.status_lbl, "Démarrage de la conversion…")

        self._worker = ConvertWorker(
            self._current_file, fmt, self._output_dir, parent=self
        )
        self._worker.progress.connect(self.progress.setValue)
        self._worker.status.connect(self.status_lbl.setText)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_finished(self, path: str) -> None:
        self._last_output = path
        self._set_busy(False)
        self.progress.setValue(100)
        self.open_btn.show()
        name = Path(path).name
        set_status(self.status_lbl, f"✔  Converti : {name}", "ok")
        item = QListWidgetItem(f"✔  {name}")
        item.setForeground(QColor(COLORS["success"]))
        self.history.insertItem(0, item)

    def _on_error(self, msg: str) -> None:
        self._set_busy(False)
        set_status(self.status_lbl, f"✗  {msg.splitlines()[0]}", "err")
        QMessageBox.critical(self, "Erreur de conversion", msg)


# ═══════════════════════════════════════════════════════════════════════════════
#  Barre d'en-tête
# ═══════════════════════════════════════════════════════════════════════════════

class HeaderBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(60)
        self.setStyleSheet(
            f"background:{COLORS['bg_card']}; border-bottom:1px solid {COLORS['border_soft']};"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(10)

        logo = QLabel("🎞 OmniMedia")
        logo.setStyleSheet(
            f"font-size:16px; font-weight:700; color:{COLORS['text_primary']}; "
            "letter-spacing:-0.3px; background:transparent;"
        )

        ver = QLabel(f"v{APP_VERSION}")
        ver.setStyleSheet(badge_style("info"))

        ffmpeg_ok = ffmpeg_available()
        ffmpeg_badge = QLabel("  FFmpeg ✔  " if ffmpeg_ok else "  FFmpeg ✗  ")
        ffmpeg_badge.setStyleSheet(badge_style("ok" if ffmpeg_ok else "err"))
        ffmpeg_badge.setToolTip(
            find_ffmpeg() if ffmpeg_ok else "FFmpeg introuvable — conversion désactivée."
        )

        try:
            import yt_dlp as _
            ytdlp_badge = QLabel("  yt-dlp ✔  ")
            ytdlp_badge.setStyleSheet(badge_style("ok"))
        except ImportError:
            ytdlp_badge = QLabel("  yt-dlp ✗  ")
            ytdlp_badge.setStyleSheet(badge_style("err"))
            ytdlp_badge.setToolTip("pip install yt-dlp")

        layout.addWidget(logo)
        layout.addWidget(ver)
        layout.addStretch()
        layout.addWidget(ffmpeg_badge)
        layout.addWidget(ytdlp_badge)


# ═══════════════════════════════════════════════════════════════════════════════
#  Fenêtre principale
# ═══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} Converter & Downloader")
        self.setMinimumSize(640, 600)
        self.resize(780, 860)
        self._setup_ui()

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(HeaderBar())

        tabs = QTabWidget()
        tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        tabs.addTab(DownloadTab(), "  ⬇  Télécharger  ")
        tabs.addTab(ConvertTab(),  "  🔄  Convertir    ")
        root.addWidget(tabs, 1)

        footer = QLabel(
            "OmniMedia v2  ·  FFmpeg + yt-dlp  ·  "
            "Glissez un fichier ou collez une URL"
        )
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(
            f"font-size:11px; color:{COLORS['text_muted']}; "
            f"background:{COLORS['bg_card']}; "
            f"border-top:1px solid {COLORS['border_soft']}; "
            "padding:7px;"
        )
        root.addWidget(footer)


# ═══════════════════════════════════════════════════════════════════════════════
#  Point d'entrée
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setStyleSheet(get_stylesheet())
    app.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
