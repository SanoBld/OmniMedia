"""
main.py — OmniMedia v4.2  (UI Premium)
Nouveautés vs v4.1 :
  - Overlay Drag & Drop semi-transparent sur toute la fenêtre
  - Dashboard de statistiques (fichiers traités, espace gagné, temps total)
  - Animation de fondu (opacity) au changement d'onglet
  - SettingsTab refonte : cartes, toggle switches, aperçus thème, pastille FFmpeg
  - CompressorTab : barre comparative visuelle + badge qualité dynamique
"""
from __future__ import annotations

import sys, os, subprocess, time
from pathlib import Path

# ── Dependency check ──────────────────────────────────────────────────────────
def _check_dependencies() -> None:
    missing = []
    try: import PyQt6       # noqa
    except ImportError: missing.append("PyQt6")
    try: import yt_dlp      # noqa
    except ImportError: missing.append("yt-dlp")
    if missing:
        pkgs = " ".join(missing)
        print(
            f"\n╔══════════════════════════════════════════════════╗\n"
            f"║  OmniMedia — Missing dependencies                ║\n"
            f"╠══════════════════════════════════════════════════╣\n"
            f"║  Modules : {', '.join(missing):<40}║\n"
            f"║  Command : pip install {pkgs:<35}║\n"
            f"╚══════════════════════════════════════════════════╝\n",
            file=sys.stderr,
        )
        input("Press Enter to close…")
        sys.exit(1)

_check_dependencies()
# ─────────────────────────────────────────────────────────────────────────────

from PyQt6.QtCore    import (QThread, pyqtSignal, Qt, QTimer,
                              QPropertyAnimation, QEasingCurve, pyqtProperty)
from PyQt6.QtGui     import QDragEnterEvent, QDropEvent, QColor, QIcon, QPixmap, QPainter
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QButtonGroup,
    QProgressBar, QTabWidget, QFrame, QFileDialog, QListWidget,
    QListWidgetItem, QComboBox, QSizePolicy, QMessageBox,
    QScrollArea, QSystemTrayIcon, QMenu, QCheckBox, QSpinBox,
    QGraphicsOpacityEffect,
)

from config_manager import cfg, resource_path
from i18n           import t, set_language, current_language
from ui_styles      import (get_stylesheet, get_palette, COLORS, badge_style,
                             section_label_style, compression_badge_style)
from downloader     import (
    DownloadWorker, AdvancedOptions, YtdlpUpdateWorker, VersionChecker,
    history as dl_history, SUPPORTED_BROWSERS,
    BROWSER_COOKIE3_AVAILABLE, BrowserCookieWorker, MUTAGEN_AVAILABLE,
)
from converter import (
    ConvertWorker, BatchConvertWorker,
    classify_file, suggested_formats, ffmpeg_available, find_ffmpeg,
    PRESETS, PresetManager, _refresh_presets,
    get_media_info, format_media_info,
    COMPRESS_TARGETS, build_compress_args, compute_target_bitrate,
)

APP_NAME    = "OmniMedia"
APP_VERSION = "4.2.0"
LOGO_PATH   = resource_path("logoOmniMedia.png")

set_language(cfg.language)

# ── Stats globales (dashboard) ────────────────────────────────────────────────
_stats = {
    "files_processed": 0,
    "space_saved_mb":  0.0,
    "total_seconds":   0.0,
    "_start_time":     None,
}
_stats_listeners: list = []   # callbacks appelés après mise à jour

def _stats_notify() -> None:
    for cb in _stats_listeners:
        try: cb()
        except Exception: pass

def stats_add_file(space_saved_bytes: float = 0.0, elapsed: float = 0.0) -> None:
    _stats["files_processed"] += 1
    _stats["space_saved_mb"]  += space_saved_bytes / (1024 * 1024)
    _stats["total_seconds"]   += elapsed
    _stats_notify()


# ── Windows Taskbar Progress ──────────────────────────────────────────────────

class _WinTaskbar:
    TBPF_NOPROGRESS    = 0
    TBPF_INDETERMINATE = 1
    TBPF_NORMAL        = 2
    TBPF_ERROR         = 4

    def __init__(self) -> None:
        self._com = None; self._hwnd = 0
        if sys.platform == "win32": self._try_init()

    def _try_init(self) -> None:
        try:
            import ctypes, ctypes.wintypes
            ctypes.windll.ole32.CoInitialize(None)
            clsid = (ctypes.c_byte * 16)(0x44,0xF3,0xFD,0x56,0x6D,0xFD,0xD0,0x11,0x95,0x8A,0x00,0x60,0x97,0xC9,0xA0,0x90)
            iid   = (ctypes.c_byte * 16)(0x91,0xFB,0x1A,0xEA,0x28,0x9E,0x86,0x4B,0x90,0xE9,0x9E,0x9F,0x8A,0x5E,0xEF,0xAF)
            obj = ctypes.c_void_p()
            if ctypes.windll.ole32.CoCreateInstance(clsid, None, 1, iid, ctypes.byref(obj)) == 0 and obj.value:
                self._com = obj
        except Exception:
            self._com = None

    def attach(self, hwnd: int) -> None: self._hwnd = hwnd

    def _vtp(self):
        import ctypes
        vt = ctypes.cast(self._com, ctypes.POINTER(ctypes.c_void_p))
        return ctypes.cast(vt[0], ctypes.POINTER(ctypes.c_void_p))

    def set_progress(self, value: int, total: int = 100) -> None:
        if not self._com or not self._hwnd or sys.platform != "win32": return
        try:
            import ctypes, ctypes.wintypes
            ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
                ctypes.wintypes.HWND, ctypes.c_ulonglong, ctypes.c_ulonglong,
            )(self._vtp()[9])(self._com, ctypes.wintypes.HWND(self._hwnd), value, total)
        except Exception: pass

    def set_state(self, state: int) -> None:
        if not self._com or not self._hwnd or sys.platform != "win32": return
        try:
            import ctypes, ctypes.wintypes
            ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
                ctypes.wintypes.HWND, ctypes.c_int,
            )(self._vtp()[10])(self._com, ctypes.wintypes.HWND(self._hwnd), state)
        except Exception: pass

    def clear(self) -> None: self.set_state(self.TBPF_NOPROGRESS)

_taskbar = _WinTaskbar()


# ── ThemeManager ──────────────────────────────────────────────────────────────

class ThemeManager:
    _app:   QApplication | None = None
    _theme: str = cfg.theme

    @classmethod
    def setup(cls, app: QApplication) -> None:
        cls._app = app; cls.apply(cls._theme)

    @classmethod
    def apply(cls, theme: str) -> None:
        cls._theme = theme; cfg.theme = theme
        if cls._app: cls._app.setStyleSheet(get_stylesheet(theme))

    @classmethod
    def current(cls) -> str: return cls._theme


# ── UI helpers ────────────────────────────────────────────────────────────────

def open_folder(path: str | Path) -> None:
    p = Path(path); target = p if p.is_dir() else p.parent
    if sys.platform == "win32":    os.startfile(str(target))
    elif sys.platform == "darwin": subprocess.Popen(["open", str(target)])
    else:                          subprocess.Popen(["xdg-open", str(target)])

def hline() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.Shape.HLine); f.setFixedHeight(1)
    f.setStyleSheet(f"background:{COLORS['border']}; border:none; margin:2px 0;")
    return f

def vline() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.Shape.VLine)
    f.setStyleSheet(f"color:{COLORS['border_soft']};")
    return f

def make_label(text: str, obj: str = "") -> QLabel:
    lbl = QLabel(text)
    if obj: lbl.setObjectName(obj)
    return lbl

def make_section(text: str) -> QLabel:
    lbl = QLabel(text.upper()); lbl.setStyleSheet(section_label_style())
    return lbl

def set_status(lbl: QLabel, text: str, kind: str = "info") -> None:
    lbl.setObjectName({"info":"status_info","ok":"status_ok","err":"status_err","warn":"status_warn"}.get(kind,"status_info"))
    lbl.setText(text); lbl.style().unpolish(lbl); lbl.style().polish(lbl)

def app_icon() -> QIcon:
    if LOGO_PATH.exists(): return QIcon(str(LOGO_PATH))
    pm = QPixmap(64, 64); pm.fill(QColor(COLORS["accent"])); return QIcon(pm)

def _can_notify(event: str) -> bool:
    if not cfg.notifications:
        return False
    if event == "download":  return cfg.notif_on_download
    if event == "convert":   return cfg.notif_on_convert
    if event == "compress":  return cfg.notif_on_convert
    if event == "error":     return cfg.notif_on_error
    return True

def make_toggle(label: str, checked: bool, callback) -> QCheckBox:
    """Crée un QCheckBox stylisé en toggle switch."""
    cb = QCheckBox(label)
    cb.setObjectName("toggle_switch")
    cb.setChecked(checked)
    cb.toggled.connect(callback)
    return cb

def make_card(icon: str, title: str) -> tuple[QFrame, QVBoxLayout, QVBoxLayout]:
    """
    Crée une carte settings avec icône + titre.
    Retourne (frame, header_layout, content_layout).
    """
    card = QFrame(); card.setObjectName("settings_card")
    outer = QVBoxLayout(card); outer.setContentsMargins(20, 18, 20, 18); outer.setSpacing(14)

    # Header de la carte
    hdr = QHBoxLayout(); hdr.setSpacing(10)
    icon_lbl = QLabel(icon); icon_lbl.setObjectName("card_section_icon")
    title_lbl = QLabel(title); title_lbl.setObjectName("card_section_title")
    hdr.addWidget(icon_lbl); hdr.addWidget(title_lbl); hdr.addStretch()
    outer.addLayout(hdr)
    outer.addWidget(hline())

    # Layout contenu
    content = QVBoxLayout(); content.setSpacing(12)
    outer.addLayout(content)

    return card, hdr, content


# ── Per-file progress widget ──────────────────────────────────────────────────

class FileProgressItem(QWidget):
    def __init__(self, icon: str, name: str, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self); lay.setContentsMargins(8,3,8,3); lay.setSpacing(8)
        self._status = QLabel("·"); self._status.setFixedWidth(14)
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet(f"color:{COLORS['text_muted']}; background:transparent; font-size:13px;")
        icon_lbl = QLabel(icon); icon_lbl.setFixedWidth(18)
        icon_lbl.setStyleSheet("background:transparent; font-size:13px;")
        self._name = QLabel(name)
        self._name.setStyleSheet(f"background:transparent; color:{COLORS['text_secondary']}; font-size:12px;")
        self._name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._bar = QProgressBar(); self._bar.setValue(0); self._bar.setTextVisible(False)
        self._bar.setFixedSize(90, 4)
        self._bar.setStyleSheet(
            f"QProgressBar{{background:{COLORS['bg_hover']};border:none;border-radius:2px;}}"
            f"QProgressBar::chunk{{background:{COLORS['accent']};border-radius:2px;}}"
        )
        lay.addWidget(self._status); lay.addWidget(icon_lbl)
        lay.addWidget(self._name, 1); lay.addWidget(self._bar)

    def set_progress(self, v: int) -> None: self._bar.setValue(v)

    def set_done(self, name: str) -> None:
        self._status.setText("✔")
        self._status.setStyleSheet(f"color:{COLORS['success']}; background:transparent; font-size:13px;")
        self._name.setText(name)
        self._name.setStyleSheet(f"background:transparent; color:{COLORS['success']}; font-size:12px;")
        self._bar.setValue(100)

    def set_error(self, err: str) -> None:
        self._status.setText("✗")
        self._status.setStyleSheet(f"color:{COLORS['danger']}; background:transparent; font-size:13px;")
        self._name.setText(err.splitlines()[0][:55])
        self._name.setStyleSheet(f"background:transparent; color:{COLORS['danger']}; font-size:12px;")


# ── Drop zone ─────────────────────────────────────────────────────────────────

class DropZone(QFrame):
    def __init__(self, on_drop, parent=None) -> None:
        super().__init__(parent); self.setObjectName("drop_zone")
        self.setAcceptDrops(True); self.setMinimumHeight(120); self._on_drop = on_drop
        lay = QVBoxLayout(self); lay.setAlignment(Qt.AlignmentFlag.AlignCenter); lay.setSpacing(8)
        self.icon_lbl = QLabel("⬇"); self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setStyleSheet("font-size:32px; background:transparent; color:#5A96FF;")
        self.text_lbl = QLabel(t("drop_zone_text")); self.text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_lbl.setStyleSheet(f"font-size:15px; font-weight:600; color:{COLORS['text_primary']}; background:transparent;")
        self.sub_lbl = QLabel(t("drop_zone_sub")); self.sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_lbl.setStyleSheet(f"font-size:12px; color:{COLORS['text_muted']}; background:transparent;")
        lay.addWidget(self.icon_lbl); lay.addWidget(self.text_lbl); lay.addWidget(self.sub_lbl)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("drag_active","true"); self.style().unpolish(self); self.style().polish(self)
            self.text_lbl.setText(t("drop_zone_active"))
        else: event.ignore()

    def dragLeaveEvent(self, _) -> None:
        self.setProperty("drag_active","false"); self.style().unpolish(self); self.style().polish(self)
        self.text_lbl.setText(t("drop_zone_text"))

    def dropEvent(self, event: QDropEvent) -> None:
        self.setProperty("drag_active","false"); self.style().unpolish(self); self.style().polish(self)
        self.text_lbl.setText(t("drop_zone_text"))
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls()]
        if paths: self._on_drop(paths)


# ── Overlay Drag & Drop (fenêtre entière) ────────────────────────────────────

class DragOverlay(QWidget):
    """
    Panneau semi-transparent qui s'affiche par-dessus la fenêtre
    quand un fichier est survolé. Disparaît dès que le fichier quitte
    ou est déposé.
    """
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAcceptDrops(True)
        self._on_drop = None
        self._setup_ui()
        self.hide()

    def _setup_ui(self) -> None:
        self.setStyleSheet(
            f"background: rgba(11, 16, 32, 0.85);"
            f"border: 3px dashed {COLORS['accent']};"
            f"border-radius: 20px;"
        )
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(14)

        icon = QLabel("⬇")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"font-size:56px; background:transparent; color:{COLORS['accent_light']}; border:none;"
        )
        msg = QLabel("Déposer pour traiter")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet(
            f"font-size:22px; font-weight:700; color:{COLORS['text_primary']};"
            f"background:transparent; letter-spacing:-0.5px; border:none;"
        )
        sub = QLabel("Les fichiers seront envoyés à l'onglet approprié")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(
            f"font-size:13px; color:{COLORS['text_secondary']}; background:transparent; border:none;"
        )
        lay.addWidget(icon); lay.addWidget(msg); lay.addWidget(sub)

    def set_drop_callback(self, cb) -> None:
        self._on_drop = cb

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls(): event.acceptProposedAction()
        else: event.ignore()

    def dragLeaveEvent(self, _) -> None:
        self.hide()

    def dropEvent(self, event: QDropEvent) -> None:
        self.hide()
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls()]
        if paths and self._on_drop:
            self._on_drop(paths)
        event.acceptProposedAction()

    def resizeEvent(self, event) -> None:
        # S'étire sur tout le parent
        if self.parent():
            self.setGeometry(8, 8,
                             self.parent().width() - 16,
                             self.parent().height() - 16)
        super().resizeEvent(event)


# ── Stats Dashboard (barre du bas) ───────────────────────────────────────────

class StatsBar(QFrame):
    """Petit panneau en bas de la fenêtre : Fichiers traités, Espace gagné, Temps total."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("stats_bar")
        self.setFixedHeight(54)
        lay = QHBoxLayout(self); lay.setContentsMargins(24, 0, 24, 0); lay.setSpacing(0)

        self._counters: dict[str, QLabel] = {}

        for key, icon, label in [
            ("files_processed", "📄", "FICHIERS TRAITÉS"),
            ("space_saved_mb",  "💾", "ESPACE ÉCONOMISÉ"),
            ("total_seconds",   "⏱",  "TEMPS TOTAL"),
        ]:
            lay.addStretch(1)
            col = QVBoxLayout(); col.setSpacing(0); col.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_val = QLabel("0"); lbl_val.setObjectName("stat_value")
            lbl_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_name = QLabel(f"{icon}  {label}"); lbl_name.setObjectName("stat_label")
            lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(lbl_val); col.addWidget(lbl_name)
            lay.addLayout(col)
            self._counters[key] = lbl_val
            lay.addStretch(1)
            if key != "total_seconds":
                sep = QFrame(); sep.setFrameShape(QFrame.Shape.VLine)
                sep.setStyleSheet(f"color:{COLORS['border_soft']};")
                lay.addWidget(sep)

        # Enregistrement comme listener
        _stats_listeners.append(self.refresh)

    def refresh(self) -> None:
        self._counters["files_processed"].setText(str(_stats["files_processed"]))
        mb = _stats["space_saved_mb"]
        self._counters["space_saved_mb"].setText(
            f"{mb:.1f} MB" if mb < 1024 else f"{mb/1024:.2f} GB"
        )
        sec = int(_stats["total_seconds"])
        h, rem = divmod(sec, 3600); m, s = divmod(rem, 60)
        self._counters["total_seconds"].setText(
            f"{h}h {m:02d}m {s:02d}s" if h else f"{m}m {s:02d}s" if m else f"{s}s"
        )


# ── Onglets avec animation fondu ──────────────────────────────────────────────

class FadingTabWidget(QTabWidget):
    """QTabWidget avec effet de fondu entre les onglets."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_effect: QGraphicsOpacityEffect | None = None
        self._anim: QPropertyAnimation | None = None
        self.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int) -> None:
        widget = self.widget(index)
        if widget is None:
            return
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(200)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: widget.setGraphicsEffect(None))
        anim.start()
        self._anim = anim


# ══════════════════════════════════════════════════════════════════════════════
#  Advanced download panel
# ══════════════════════════════════════════════════════════════════════════════

class DownloadAdvancedPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent); self._cookies_path = ""
        self._browser_cookie_worker: BrowserCookieWorker | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.setSpacing(6)
        self.toggle_btn = QPushButton(t("adv_options_closed"))
        self.toggle_btn.setObjectName("btn_advanced"); self.toggle_btn.setCheckable(True)
        self.toggle_btn.setFixedHeight(32)
        self.toggle_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.toggle_btn.clicked.connect(self._toggle)
        outer.addWidget(self.toggle_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self.panel = QFrame(); self.panel.setObjectName("advanced_panel"); self.panel.hide()
        pl = QVBoxLayout(self.panel); pl.setContentsMargins(16,14,16,14); pl.setSpacing(14)

        row1 = QHBoxLayout(); row1.setSpacing(20)
        col_br = QVBoxLayout(); col_br.addWidget(make_section(t("audio_bitrate")))
        self.bitrate_combo = QComboBox()
        for lbl, val in [(t("bitrate_128"),"128k"),(t("bitrate_192"),"192k"),(t("bitrate_320"),"320k")]:
            self.bitrate_combo.addItem(lbl, val)
        self.bitrate_combo.setCurrentIndex(1); self.bitrate_combo.setMinimumWidth(150)
        col_br.addWidget(self.bitrate_combo); row1.addLayout(col_br)
        col_res = QVBoxLayout(); col_res.addWidget(make_section(t("max_resolution")))
        self.res_combo = QComboBox()
        for lbl, val in [(t("res_best"),"best"),("1080p","1080"),("720p","720"),("480p","480")]:
            self.res_combo.addItem(lbl, val)
        self.res_combo.setMinimumWidth(130); col_res.addWidget(self.res_combo)
        row1.addLayout(col_res); row1.addStretch(); pl.addLayout(row1)

        row2 = QVBoxLayout(); row2.addWidget(make_section(t("playlist_items")))
        self.playlist_input = QLineEdit(); self.playlist_input.setPlaceholderText(t("playlist_placeholder"))
        row2.addWidget(self.playlist_input); pl.addLayout(row2)

        self.playlist_mode_cb = QCheckBox(t("playlist_mode"))
        self.playlist_mode_cb.setChecked(cfg.playlist_mode); pl.addWidget(self.playlist_mode_cb)

        row3 = QVBoxLayout(); row3.addWidget(make_section(t("cookies_file")))
        cookie_row = QHBoxLayout()
        self.cookie_label = QLabel(t("no_file_selected")); self.cookie_label.setObjectName("status_info")
        cookie_btn = QPushButton(t("load_cookies")); cookie_btn.setObjectName("btn_secondary")
        cookie_btn.setFixedHeight(34); cookie_btn.clicked.connect(self._pick_cookie)
        cookie_row.addWidget(self.cookie_label, 1); cookie_row.addWidget(cookie_btn)
        row3.addLayout(cookie_row); pl.addLayout(row3)

        row4 = QVBoxLayout(); row4.addWidget(make_section(t("browser_cookies_section")))
        browser_row = QHBoxLayout()
        self.browser_combo = QComboBox(); self.browser_combo.addItem("—","")
        for b in SUPPORTED_BROWSERS: self.browser_combo.addItem(b.capitalize(), b)
        self.browser_combo.setMinimumWidth(120)
        self.import_browser_btn = QPushButton(t("import_browser_btn"))
        self.import_browser_btn.setObjectName("btn_secondary"); self.import_browser_btn.setFixedHeight(34)
        self.import_browser_btn.setEnabled(BROWSER_COOKIE3_AVAILABLE)
        self.import_browser_btn.clicked.connect(self._import_browser_cookies)
        self.browser_status = QLabel(""); self.browser_status.setObjectName("status_info")
        browser_row.addWidget(self.browser_combo); browser_row.addWidget(self.import_browser_btn)
        browser_row.addWidget(self.browser_status, 1)
        row4.addLayout(browser_row); pl.addLayout(row4)

        self.embed_thumb_cb = QCheckBox(t("embed_thumbnail"))
        self.embed_thumb_cb.setChecked(cfg.get("embed_thumbnail", True))
        self.embed_thumb_cb.setEnabled(MUTAGEN_AVAILABLE); pl.addWidget(self.embed_thumb_cb)

        self.auto_tag_cb = QCheckBox(t("auto_tag"))
        self.auto_tag_cb.setChecked(cfg.auto_tag); self.auto_tag_cb.setEnabled(MUTAGEN_AVAILABLE)
        self.auto_tag_cb.setToolTip("Requires mutagen — pip install mutagen"); pl.addWidget(self.auto_tag_cb)

        outer.addWidget(self.panel)

    def _toggle(self) -> None:
        visible = self.panel.isVisible(); self.panel.setVisible(not visible)
        self.toggle_btn.setText(t("adv_options_open" if not visible else "adv_options_closed"))

    def _pick_cookie(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select cookies.txt", str(Path.home()), "Text (*.txt);;All (*)")
        if path: self._cookies_path = path; self.cookie_label.setText(Path(path).name)

    def _import_browser_cookies(self) -> None:
        browser = self.browser_combo.currentData()
        if not browser: return
        self.import_browser_btn.setEnabled(False)
        self._browser_cookie_worker = BrowserCookieWorker(browser, parent=self)
        self._browser_cookie_worker.finished.connect(self._on_browser_cookies)
        self._browser_cookie_worker.start()

    def _on_browser_cookies(self, ok: bool, result: str) -> None:
        self.import_browser_btn.setEnabled(True)
        if ok: self._cookies_path = result; set_status(self.browser_status, f"✔ {Path(result).name}", "ok")
        else: set_status(self.browser_status, f"✗ {result[:60]}", "err")

    def get_options(self) -> AdvancedOptions:
        return AdvancedOptions(
            audio_bitrate=self.bitrate_combo.currentData(), video_codec="h264",
            max_resolution=self.res_combo.currentData(),
            playlist_items=self.playlist_input.text().strip(),
            cookies_file=self._cookies_path, browser_cookies="",
            embed_thumbnail=self.embed_thumb_cb.isChecked(),
        )

    def playlist_mode_enabled(self) -> bool: return self.playlist_mode_cb.isChecked()
    def auto_tag_enabled(self) -> bool: return self.auto_tag_cb.isChecked()


# ══════════════════════════════════════════════════════════════════════════════
#  Download tab
# ══════════════════════════════════════════════════════════════════════════════

class DownloadTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._worker: DownloadWorker | None = None
        self._last_file: str = ""
        self._output_dir: Path = cfg.download_dir
        self._queue_items: list[dict] = []
        self._setup_ui(); self._reload_history()

    def _setup_ui(self) -> None:
        scroll = QScrollArea(self); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget(); scroll.setWidget(container)
        outer = QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.addWidget(scroll)
        root = QVBoxLayout(container); root.setContentsMargins(28,24,28,24); root.setSpacing(18)

        hdr = QHBoxLayout()
        ic = QLabel("⬇"); ic.setStyleSheet("font-size:24px; background:transparent;")
        hdr.addWidget(ic); hdr.addWidget(make_label(t("download_title"),"title")); hdr.addStretch()
        root.addLayout(hdr)

        card = QFrame(); card.setObjectName("card")
        cl = QVBoxLayout(card); cl.setSpacing(16); cl.setContentsMargins(20,20,20,20)
        cl.addWidget(make_section(t("url_section")))
        url_row = QHBoxLayout(); url_row.setSpacing(8)
        self.url_input = QLineEdit(); self.url_input.setPlaceholderText(t("url_placeholder"))
        self.url_input.setMinimumHeight(42)
        paste_btn = QPushButton("📋"); paste_btn.setObjectName("btn_secondary")
        paste_btn.setFixedSize(42,42)
        paste_btn.clicked.connect(lambda: self.url_input.setText(QApplication.clipboard().text().strip()))
        url_row.addWidget(self.url_input, 1); url_row.addWidget(paste_btn)
        cl.addLayout(url_row)
        cl.addWidget(hline()); cl.addWidget(make_section(t("format_section")))
        fmt_row = QHBoxLayout(); fmt_row.setSpacing(16)
        self.rb_video = QRadioButton(t("video_format"))
        self.rb_audio = QRadioButton(t("audio_format"))
        self.rb_video.setChecked(True)
        grp = QButtonGroup(self); grp.addButton(self.rb_video); grp.addButton(self.rb_audio)
        fmt_row.addWidget(self.rb_video); fmt_row.addWidget(self.rb_audio); fmt_row.addStretch()
        cl.addLayout(fmt_row)
        cl.addWidget(hline()); cl.addWidget(make_section(t("dest_folder")))
        folder_row = QHBoxLayout(); folder_row.setSpacing(8)
        self.folder_label = QLabel(str(self._output_dir)); self.folder_label.setObjectName("status_info")
        self.folder_label.setWordWrap(True)
        self.folder_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        folder_btn = QPushButton(t("change_folder")); folder_btn.setObjectName("btn_secondary")
        folder_btn.setFixedHeight(34); folder_btn.clicked.connect(self._choose_folder)
        folder_row.addWidget(self.folder_label, 1); folder_row.addWidget(folder_btn)
        cl.addLayout(folder_row); root.addWidget(card)

        self.advanced = DownloadAdvancedPanel(); root.addWidget(self.advanced)
        self.progress = QProgressBar(); self.progress.setValue(0)
        self.progress.setTextVisible(False); self.progress.setFixedHeight(4)
        root.addWidget(self.progress)

        status_row = QHBoxLayout()
        self.status_lbl = QLabel(t("ready")); self.status_lbl.setObjectName("status_info")
        self.status_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.open_btn = QPushButton(t("open_folder")); self.open_btn.setObjectName("btn_secondary")
        self.open_btn.setFixedHeight(34); self.open_btn.hide()
        self.open_btn.clicked.connect(lambda: open_folder(self._last_file or self._output_dir))
        status_row.addWidget(self.status_lbl, 1); status_row.addWidget(self.open_btn)
        root.addLayout(status_row)

        btn_row = QHBoxLayout(); btn_row.addStretch()
        self.cancel_btn = QPushButton(t("cancel")); self.cancel_btn.setObjectName("btn_secondary")
        self.cancel_btn.setEnabled(False); self.cancel_btn.setFixedHeight(42)
        self.cancel_btn.clicked.connect(self._cancel)
        self.dl_btn = QPushButton(t("download_btn"))
        self.dl_btn.setMinimumWidth(170); self.dl_btn.setFixedHeight(42)
        self.dl_btn.clicked.connect(self._start_download)
        btn_row.addWidget(self.cancel_btn); btn_row.addWidget(self.dl_btn)
        root.addLayout(btn_row)

        root.addWidget(hline())
        q_hdr = QHBoxLayout(); q_hdr.addWidget(make_section(t("dl_queue_section"))); q_hdr.addStretch()
        clear_q = QPushButton(t("dl_queue_clear")); clear_q.setObjectName("btn_secondary")
        clear_q.setFixedHeight(26); clear_q.setStyleSheet("font-size:11px; padding:2px 10px;")
        clear_q.clicked.connect(self._clear_queue); q_hdr.addWidget(clear_q); root.addLayout(q_hdr)
        self.queue_list = QListWidget(); self.queue_list.setMaximumHeight(160)
        self.queue_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        root.addWidget(self.queue_list)

        root.addWidget(hline())
        hist_hdr = QHBoxLayout(); hist_hdr.addWidget(make_section(t("download_history"))); hist_hdr.addStretch()
        clr_hist = QPushButton(t("clear_history")); clr_hist.setObjectName("btn_secondary")
        clr_hist.setFixedHeight(26); clr_hist.setStyleSheet("font-size:11px; padding:2px 10px;")
        clr_hist.clicked.connect(self._clear_history); hist_hdr.addWidget(clr_hist); root.addLayout(hist_hdr)
        self.history = QListWidget(); self.history.setMinimumHeight(90)
        self.history.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.history.itemDoubleClicked.connect(self._restore_url)
        root.addWidget(self.history, 1)

    def _add_to_queue(self, url: str, mode: str) -> None:
        icon = "🎵" if mode == "audio" else "🎬"
        short = url[:70] + "…" if len(url) > 70 else url
        item = QListWidgetItem(f"{icon}  {short}  —  {t('dl_queue_pending')}")
        item.setData(Qt.ItemDataRole.UserRole, url)
        self.queue_list.addItem(item); self._queue_items.append({"url":url,"mode":mode,"item":item})

    def _clear_queue(self) -> None: self.queue_list.clear(); self._queue_items.clear()

    def _reload_history(self) -> None:
        self.history.clear()
        for e in dl_history.all()[:50]:
            date = e.get("date","")[:10]; mode = "🎵" if e.get("mode")=="audio" else "🎬"
            item = QListWidgetItem(f"{mode}  {e.get('title','?')}  —  {date}")
            item.setData(Qt.ItemDataRole.UserRole, e.get("url",""))
            item.setToolTip(e.get("url","")); self.history.addItem(item)

    def _restore_url(self, item: QListWidgetItem) -> None:
        url = item.data(Qt.ItemDataRole.UserRole)
        if url: self.url_input.setText(url)

    def _clear_history(self) -> None: dl_history.clear(); self.history.clear()

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Destination folder")
        if folder: self._output_dir = Path(folder); cfg.download_dir = folder; self.folder_label.setText(folder)

    def _set_busy(self, busy: bool) -> None:
        self.dl_btn.setEnabled(not busy); self.cancel_btn.setEnabled(busy)
        self.url_input.setEnabled(not busy); self.advanced.setEnabled(not busy)
        if not busy: self.progress.setValue(0); _taskbar.clear()

    def _cancel(self) -> None:
        if self._worker: self._worker.cancel()
        self._set_busy(False); set_status(self.status_lbl, t("download_cancelled"))

    def _start_download(self) -> None:
        url = self.url_input.text().strip()
        if not url: set_status(self.status_lbl, t("paste_url_first"), "err"); return
        mode = "audio" if self.rb_audio.isChecked() else "video"
        opts = self.advanced.get_options()
        playlist = self.advanced.playlist_mode_enabled()
        auto_tag  = self.advanced.auto_tag_enabled()
        self._add_to_queue(url, mode); self._set_busy(True); self.open_btn.hide()
        self._start_time = time.monotonic()
        set_status(self.status_lbl, "Démarrage…"); _taskbar.set_state(_WinTaskbar.TBPF_INDETERMINATE)
        if self._queue_items:
            self._queue_items[-1]["item"].setText(
                self._queue_items[-1]["item"].text().replace(t("dl_queue_pending"), t("dl_queue_downloading"))
            )
        self._worker = DownloadWorker(url, self._output_dir, mode, opts,
                                      playlist_mode=playlist, auto_tag=auto_tag, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.status.connect(lambda msg, _=None: self.status_lbl.setText(msg))
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, v: int) -> None:
        self.progress.setValue(v); _taskbar.set_state(_WinTaskbar.TBPF_NORMAL); _taskbar.set_progress(v)

    def _on_finished(self, ok: bool, path: str) -> None:
        elapsed = time.monotonic() - getattr(self, "_start_time", time.monotonic())
        self._last_file = path; self._set_busy(False)
        if ok:
            self.progress.setValue(100); self.open_btn.show()
            set_status(self.status_lbl, f"✔  {Path(path).name}", "ok")
            if self._queue_items:
                self._queue_items[-1]["item"].setText(
                    self._queue_items[-1]["item"].text().replace(t("dl_queue_downloading"), t("dl_queue_done"))
                )
            self._reload_history()
            stats_add_file(elapsed=elapsed)
            if _can_notify("download"):
                win = self.window()
                if hasattr(win, "notify"): win.notify(t("notif_dl_done"), Path(path).name)
        else:
            _taskbar.set_state(_WinTaskbar.TBPF_ERROR)
            set_status(self.status_lbl, f"✗  {path.splitlines()[0]}", "err")
            if self._queue_items:
                self._queue_items[-1]["item"].setText(
                    self._queue_items[-1]["item"].text().replace(t("dl_queue_downloading"), t("dl_queue_error"))
                )
            if _can_notify("error"):
                win = self.window()
                if hasattr(win, "notify"): win.notify(t("error_download"), path.splitlines()[0])


# ══════════════════════════════════════════════════════════════════════════════
#  Convert tab
# ══════════════════════════════════════════════════════════════════════════════

class ConvertTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._batch_worker: BatchConvertWorker | None = None
        self._queued_files: list[Path] = []
        self._file_widgets: list[FileProgressItem] = []
        self._output_dir: Path = cfg.download_dir
        self._setup_ui()

    def _setup_ui(self) -> None:
        scroll = QScrollArea(self); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget(); scroll.setWidget(container)
        outer = QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.addWidget(scroll)
        root = QVBoxLayout(container); root.setContentsMargins(28,24,28,24); root.setSpacing(16)

        hdr = QHBoxLayout()
        ic = QLabel("🔄"); ic.setStyleSheet("font-size:24px; background:transparent;")
        hdr.addWidget(ic); hdr.addWidget(make_label(t("convert_title"),"title")); hdr.addStretch()
        root.addLayout(hdr)

        self.drop_zone = DropZone(self._on_files_dropped); root.addWidget(self.drop_zone, 1)
        browse_row = QHBoxLayout(); browse_row.addStretch()
        browse_btn = QPushButton(t("browse")); browse_btn.setObjectName("btn_secondary")
        browse_btn.setFixedHeight(34); browse_btn.clicked.connect(self._browse_files)
        browse_row.addWidget(browse_btn); browse_row.addStretch(); root.addLayout(browse_row)

        q_hdr = QHBoxLayout(); q_hdr.addWidget(make_section(t("queue_section"))); q_hdr.addStretch()
        self.batch_count_lbl = QLabel(""); self.batch_count_lbl.setObjectName("status_info")
        q_hdr.addWidget(self.batch_count_lbl)
        clr_q = QPushButton(t("clear_queue")); clr_q.setObjectName("btn_secondary")
        clr_q.setFixedHeight(26); clr_q.setStyleSheet("font-size:11px; padding:2px 10px;")
        clr_q.clicked.connect(self._clear_queue); q_hdr.addWidget(clr_q); root.addLayout(q_hdr)
        self.queue_list = QListWidget(); self.queue_list.setMaximumHeight(150)
        self.queue_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        root.addWidget(self.queue_list)

        opts_card = QFrame(); opts_card.setObjectName("card")
        ocl = QHBoxLayout(opts_card); ocl.setSpacing(16); ocl.setContentsMargins(16,14,16,14)
        preset_col = QVBoxLayout(); preset_col.setSpacing(6)
        preset_col.addWidget(make_section(t("preset_section")))
        self.preset_combo = QComboBox(); self._reload_presets_combo()
        self.preset_combo.setMinimumWidth(200); self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        preset_col.addWidget(self.preset_combo)
        self.preset_desc = QLabel(list(PRESETS.values())[0]["desc"]); self.preset_desc.setObjectName("subtitle")
        self.preset_desc.setWordWrap(True); preset_col.addWidget(self.preset_desc); ocl.addLayout(preset_col)
        ocl.addWidget(vline())
        fmt_col = QVBoxLayout(); fmt_col.setSpacing(6)
        fmt_col.addWidget(make_section(t("output_format")))
        self.fmt_combo = QComboBox(); self.fmt_combo.setMinimumWidth(140)
        for f in ["mp4","mp3","mkv","avi","webm","flac","wav","gif","jpg","png"]:
            self.fmt_combo.addItem(f".{f}", f)
        fmt_col.addWidget(self.fmt_combo); fmt_col.addSpacing(6)
        fmt_col.addWidget(make_section(t("output_folder")))
        outdir_row = QHBoxLayout(); outdir_row.setSpacing(6)
        self.out_dir_label = QLabel(str(self._output_dir)); self.out_dir_label.setObjectName("status_info")
        self.out_dir_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        outdir_btn = QPushButton("📁"); outdir_btn.setObjectName("btn_secondary"); outdir_btn.setFixedSize(34,34)
        outdir_btn.clicked.connect(self._choose_out_folder)
        outdir_row.addWidget(self.out_dir_label, 1); outdir_row.addWidget(outdir_btn)
        fmt_col.addLayout(outdir_row); ocl.addLayout(fmt_col, 1); root.addWidget(opts_card)

        trim_card = QFrame(); trim_card.setObjectName("card_inner")
        tcl = QHBoxLayout(trim_card); tcl.setContentsMargins(16,12,16,12); tcl.setSpacing(16)
        trim_lbl = QLabel(t("trim_section"))
        trim_lbl.setStyleSheet(f"color:{COLORS['text_secondary']}; font-size:12px; font-weight:600; background:transparent;")
        tcl.addWidget(trim_lbl); tcl.addSpacing(8)
        for attr, key_lbl, key_ph, w in [("trim_start","trim_start","trim_start_ph",110),("trim_end","trim_end","trim_end_ph",130)]:
            col = QVBoxLayout(); col.setSpacing(4); col.addWidget(make_section(t(key_lbl)))
            inp = QLineEdit(); inp.setPlaceholderText(t(key_ph)); inp.setFixedWidth(w)
            setattr(self, attr, inp); col.addWidget(inp); tcl.addLayout(col)
        tcl.addStretch(); root.addWidget(trim_card)

        prog_row = QHBoxLayout(); prog_row.addWidget(make_section(t("global_progress"))); prog_row.addStretch()
        root.addLayout(prog_row)
        self.progress = QProgressBar(); self.progress.setValue(0)
        self.progress.setTextVisible(False); self.progress.setFixedHeight(4)
        root.addWidget(self.progress)

        status_row = QHBoxLayout()
        self.status_lbl = QLabel(t("drop_or_browse")); self.status_lbl.setObjectName("status_info")
        self.status_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.open_btn = QPushButton(t("open_folder")); self.open_btn.setObjectName("btn_secondary")
        self.open_btn.setFixedHeight(34); self.open_btn.hide()
        self.open_btn.clicked.connect(lambda: open_folder(self._output_dir))
        status_row.addWidget(self.status_lbl, 1); status_row.addWidget(self.open_btn)
        root.addLayout(status_row)

        btn_row = QHBoxLayout(); btn_row.addStretch()
        self.cancel_btn = QPushButton(t("cancel")); self.cancel_btn.setObjectName("btn_secondary")
        self.cancel_btn.setEnabled(False); self.cancel_btn.setFixedHeight(42)
        self.cancel_btn.clicked.connect(self._cancel)
        self.convert_btn = QPushButton(t("convert_btn"))
        self.convert_btn.setMinimumWidth(170); self.convert_btn.setFixedHeight(42)
        self.convert_btn.setEnabled(False); self.convert_btn.clicked.connect(self._start_batch)
        btn_row.addWidget(self.cancel_btn); btn_row.addWidget(self.convert_btn)
        root.addLayout(btn_row)

    def _reload_presets_combo(self) -> None:
        _refresh_presets(); self.preset_combo.blockSignals(True); self.preset_combo.clear()
        for key, p in PRESETS.items(): self.preset_combo.addItem(p["label"], key)
        self.preset_combo.blockSignals(False)

    def refresh_presets(self) -> None: self._reload_presets_combo()

    def _on_preset_changed(self) -> None:
        key = self.preset_combo.currentData(); p = PRESETS.get(key, {})
        self.preset_desc.setText(p.get("desc",""))
        if p.get("fmt"):
            idx = self.fmt_combo.findData(p["fmt"])
            if idx >= 0: self.fmt_combo.setCurrentIndex(idx)

    def _browse_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choisir des fichiers", str(Path.home()),
            "Médias (*.webp *.jpg *.jpeg *.png *.bmp *.gif *.mp4 *.mkv *.avi *.mov *.webm *.mp3 *.wav *.aac *.flac *.ogg *.m4a);;Tous (*)",
        )
        if paths: self._on_files_dropped([Path(p) for p in paths])

    def _on_files_dropped(self, paths: list[Path]) -> None:
        added = 0
        for p in paths:
            if classify_file(p) != "unknown" and p not in self._queued_files:
                self._queued_files.append(p)
                info = get_media_info(p); label = format_media_info(info)
                item = QListWidgetItem(); widget = FileProgressItem(info.icon, label)
                item.setSizeHint(widget.sizeHint())
                self.queue_list.addItem(item); self.queue_list.setItemWidget(item, widget)
                self._file_widgets.append(widget); added += 1
        if added:
            self.convert_btn.setEnabled(True)
            set_status(self.status_lbl, t("queue_count", n=len(self._queued_files)))

    def _clear_queue(self) -> None:
        self._queued_files.clear(); self._file_widgets.clear(); self.queue_list.clear()
        self.convert_btn.setEnabled(False); set_status(self.status_lbl, t("queue_cleared"))

    def _choose_out_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Dossier de sortie")
        if folder: self._output_dir = Path(folder); self.out_dir_label.setText(folder)

    def _set_busy(self, busy: bool) -> None:
        self.convert_btn.setEnabled(not busy and bool(self._queued_files))
        self.cancel_btn.setEnabled(busy); self.drop_zone.setEnabled(not busy)
        if not busy: self.progress.setValue(0); _taskbar.clear()

    def _cancel(self) -> None:
        if self._batch_worker: self._batch_worker.cancel()
        self._set_busy(False); set_status(self.status_lbl, t("conversion_cancelled"))

    def _start_batch(self) -> None:
        if not self._queued_files: return
        if not ffmpeg_available(): QMessageBox.critical(self, "FFmpeg", t("ffmpeg_missing_msg")); return
        fmt = self.fmt_combo.currentData(); preset_key = self.preset_combo.currentData()
        trim_s = self.trim_start.text().strip(); trim_e = self.trim_end.text().strip()
        self._set_busy(True); self.open_btn.hide()
        self.batch_count_lbl.setText(f"0 / {len(self._queued_files)}")
        self._start_time = time.monotonic()
        _taskbar.set_state(_WinTaskbar.TBPF_NORMAL)
        self._batch_worker = BatchConvertWorker(
            self._queued_files, fmt, self._output_dir,
            preset_key, cfg.max_workers, trim_s, trim_e, parent=self,
        )
        self._batch_worker.overall_progress.connect(self._on_overall_progress)
        self._batch_worker.status.connect(self.status_lbl.setText)
        self._batch_worker.file_progress.connect(self._on_file_progress)
        self._batch_worker.file_done.connect(self._on_file_done)
        self._batch_worker.file_error.connect(self._on_file_error)
        self._batch_worker.all_done.connect(self._on_all_done)
        self._batch_worker.start()

    def _on_overall_progress(self, v: int) -> None:
        self.progress.setValue(v); _taskbar.set_progress(v)

    def _on_file_progress(self, idx: int, v: int) -> None:
        if 0 <= idx < len(self._file_widgets): self._file_widgets[idx].set_progress(v)

    def _on_file_done(self, idx: int, _src: str, out: str) -> None:
        if 0 <= idx < len(self._file_widgets): self._file_widgets[idx].set_done(Path(out).name)
        self.batch_count_lbl.setText(f"{idx+1} / {len(self._queued_files)}")

    def _on_file_error(self, idx: int, _src: str, err: str) -> None:
        if 0 <= idx < len(self._file_widgets): self._file_widgets[idx].set_error(err)

    def _on_all_done(self, success: int, errors: int) -> None:
        elapsed = time.monotonic() - getattr(self, "_start_time", time.monotonic())
        self._set_busy(False); self.progress.setValue(100); self.open_btn.show()
        msg = f"✔  {success} converti(s)" + (f"  ·  ✗ {errors} erreur(s)" if errors else "")
        set_status(self.status_lbl, msg, "ok" if not errors else "warn")
        stats_add_file(elapsed=elapsed)
        if _can_notify("convert"):
            win = self.window()
            if hasattr(win, "notify"): win.notify(t("notif_conv_done"), msg)

    def add_files(self, paths: list[Path]) -> None: self._on_files_dropped(paths)


# ══════════════════════════════════════════════════════════════════════════════
#  Compressor tab  — v4.2 : barre comparative + badge qualité
# ══════════════════════════════════════════════════════════════════════════════

class CompressorTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._batch_worker: BatchConvertWorker | None = None
        self._queued_files: list[Path] = []
        self._file_widgets: list[FileProgressItem] = []
        self._output_dir: Path = cfg.download_dir
        self._selected_platform = "discord"
        self._setup_ui()

    def _setup_ui(self) -> None:
        scroll = QScrollArea(self); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget(); scroll.setWidget(container)
        outer = QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.addWidget(scroll)
        root = QVBoxLayout(container); root.setContentsMargins(28,24,28,24); root.setSpacing(18)

        # Header
        hdr = QHBoxLayout()
        ic = QLabel("📦"); ic.setStyleSheet("font-size:24px; background:transparent;")
        hdr.addWidget(ic)
        hdr.addWidget(make_label("Compresseur vidéo", "title")); hdr.addStretch()
        root.addLayout(hdr)

        # Info banner
        info_card = QFrame(); info_card.setObjectName("card_inner")
        info_layout = QHBoxLayout(info_card); info_layout.setContentsMargins(16,12,16,12)
        info_txt = QLabel(
            "ℹ  FFmpeg calcule automatiquement le bitrate vidéo pour respecter "
            "la limite de taille choisie."
        )
        info_txt.setObjectName("subtitle"); info_txt.setWordWrap(True)
        info_layout.addWidget(info_txt); root.addWidget(info_card)

        # Drop zone
        self.drop_zone = DropZone(self._on_files_dropped)
        self.drop_zone.text_lbl.setText("Glissez vos vidéos ici")
        self.drop_zone.sub_lbl.setText("Formats supportés : MP4, MKV, AVI, MOV, WEBM…")
        root.addWidget(self.drop_zone, 1)

        # Browse button
        browse_row = QHBoxLayout(); browse_row.addStretch()
        browse_btn = QPushButton("📂  Parcourir des vidéos…")
        browse_btn.setObjectName("btn_secondary"); browse_btn.setFixedHeight(34)
        browse_btn.clicked.connect(self._browse_files)
        browse_row.addWidget(browse_btn); browse_row.addStretch(); root.addLayout(browse_row)

        # Queue
        q_hdr = QHBoxLayout()
        q_hdr.addWidget(make_section("File d'attente")); q_hdr.addStretch()
        self.batch_count_lbl = QLabel(""); self.batch_count_lbl.setObjectName("status_info")
        q_hdr.addWidget(self.batch_count_lbl)
        clr_q = QPushButton("🗑  Vider"); clr_q.setObjectName("btn_secondary")
        clr_q.setFixedHeight(26); clr_q.setStyleSheet("font-size:11px; padding:2px 10px;")
        clr_q.clicked.connect(self._clear_queue); q_hdr.addWidget(clr_q); root.addLayout(q_hdr)
        self.queue_list = QListWidget(); self.queue_list.setMaximumHeight(140)
        self.queue_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        root.addWidget(self.queue_list)

        # ── Target settings card ──────────────────────────────────────────────
        target_card = QFrame(); target_card.setObjectName("card")
        tcl = QVBoxLayout(target_card); tcl.setSpacing(16); tcl.setContentsMargins(20,18,20,18)
        tcl.addWidget(make_section("🎯  Cible de compression"))

        # Platform presets
        platform_row = QHBoxLayout(); platform_row.setSpacing(10)
        self._platform_btns: dict[str, QPushButton] = {}
        platforms = [
            ("💬 Discord",      "discord",   "25 MB"),
            ("📱 WhatsApp",     "whatsapp",  "16 MB"),
            ("📧 E-mail",       "email",     "10 MB"),
            ("✈ Telegram",     "telegram",  "100 MB"),
            ("🔧 Personnalisé", "custom",    ""),
        ]
        for label, key, size in platforms:
            full_label = f"{label}\n{size}" if size else label
            btn = QPushButton(full_label); btn.setObjectName("theme_btn")
            btn.setCheckable(True); btn.setFixedHeight(48)
            btn.setMinimumWidth(90)
            btn.clicked.connect(lambda _, k=key: self._select_platform(k))
            self._platform_btns[key] = btn; platform_row.addWidget(btn)
        platform_row.addStretch(); tcl.addLayout(platform_row)

        # Custom size row
        self.custom_row = QWidget()
        cr = QHBoxLayout(self.custom_row); cr.setContentsMargins(0,0,0,0); cr.setSpacing(10)
        cr.addWidget(make_section("Taille max (MB)"))
        self.custom_size_spin = QSpinBox(); self.custom_size_spin.setRange(1, 2000)
        self.custom_size_spin.setValue(50); self.custom_size_spin.setFixedWidth(80)
        self.custom_size_spin.setSuffix(" MB"); cr.addWidget(self.custom_size_spin)
        cr.addStretch(); self.custom_row.hide(); tcl.addWidget(self.custom_row)

        # ── Barre comparative visuelle ─────────────────────────────────────────
        compare_section = QLabel("APERÇU DU GAIN ESTIMÉ")
        compare_section.setStyleSheet(section_label_style()); tcl.addWidget(compare_section)

        compare_container = QWidget()
        compare_layout = QVBoxLayout(compare_container); compare_layout.setContentsMargins(0,0,0,0); compare_layout.setSpacing(6)

        # Ligne "Taille actuelle"
        orig_row = QHBoxLayout()
        orig_lbl = QLabel("Taille actuelle"); orig_lbl.setObjectName("status_info"); orig_lbl.setFixedWidth(110)
        self._orig_bar_bg = QFrame(); self._orig_bar_bg.setObjectName("compare_bar_bg")
        self._orig_bar_bg.setFixedHeight(12)
        self._orig_bar_fill = QFrame(self._orig_bar_bg); self._orig_bar_fill.setObjectName("compare_bar_fill")
        self._orig_bar_fill.setFixedHeight(12)
        self._orig_size_lbl = QLabel("—"); self._orig_size_lbl.setObjectName("status_info"); self._orig_size_lbl.setFixedWidth(60)
        orig_row.addWidget(orig_lbl); orig_row.addWidget(self._orig_bar_bg, 1); orig_row.addWidget(self._orig_size_lbl)
        compare_layout.addLayout(orig_row)

        # Ligne "Taille cible"
        target_row = QHBoxLayout()
        target_lbl = QLabel("Taille cible"); target_lbl.setObjectName("status_info"); target_lbl.setFixedWidth(110)
        self._target_bar_bg = QFrame(); self._target_bar_bg.setObjectName("compare_bar_bg")
        self._target_bar_bg.setFixedHeight(12)
        self._target_bar_fill = QFrame(self._target_bar_bg); self._target_bar_fill.setObjectName("compare_bar_fill")
        self._target_bar_fill.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            f"stop:0 {COLORS['success']}, stop:1 #22D3A5); border-radius: 6px; border: none;"
        )
        self._target_bar_fill.setFixedHeight(12)
        self._target_size_lbl = QLabel("—"); self._target_size_lbl.setObjectName("status_ok"); self._target_size_lbl.setFixedWidth(60)
        target_row.addWidget(target_lbl); target_row.addWidget(self._target_bar_bg, 1); target_row.addWidget(self._target_size_lbl)
        compare_layout.addLayout(target_row)

        # Badge qualité
        badge_row = QHBoxLayout()
        badge_row.addStretch()
        self._quality_badge = QLabel("—")
        self._quality_badge.setStyleSheet(compression_badge_style("optimal"))
        badge_row.addWidget(self._quality_badge)
        compare_layout.addLayout(badge_row)

        tcl.addWidget(compare_container)

        # Audio quality row
        aq_row = QHBoxLayout(); aq_row.setSpacing(16)
        aq_col = QVBoxLayout(); aq_col.setSpacing(4)
        aq_col.addWidget(make_section("Qualité audio"))
        self.audio_br_combo = QComboBox()
        for lbl, val in [("128 kbps (standard)", 128), ("192 kbps (haute)", 192), ("96 kbps (léger)", 96)]:
            self.audio_br_combo.addItem(lbl, val)
        self.audio_br_combo.setMinimumWidth(180); aq_col.addWidget(self.audio_br_combo)
        self.audio_br_combo.currentIndexChanged.connect(self._refresh_compare)
        aq_row.addLayout(aq_col)

        # Output folder
        of_col = QVBoxLayout(); of_col.setSpacing(4)
        of_col.addWidget(make_section("Dossier de sortie"))
        of_row = QHBoxLayout(); of_row.setSpacing(6)
        self.out_dir_label = QLabel(str(self._output_dir)); self.out_dir_label.setObjectName("status_info")
        self.out_dir_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        outdir_btn = QPushButton("📁"); outdir_btn.setObjectName("btn_secondary"); outdir_btn.setFixedSize(34,34)
        outdir_btn.clicked.connect(self._choose_out_folder)
        of_row.addWidget(self.out_dir_label, 1); of_row.addWidget(outdir_btn)
        of_col.addLayout(of_row); aq_row.addLayout(of_col, 1); tcl.addLayout(aq_row)
        root.addWidget(target_card)

        self.platform_desc = QLabel("Choisissez une plateforme cible ci-dessus.")
        self.platform_desc.setObjectName("subtitle"); self.platform_desc.setWordWrap(True)
        root.addWidget(self.platform_desc)

        self.progress = QProgressBar(); self.progress.setValue(0)
        self.progress.setTextVisible(False); self.progress.setFixedHeight(4)
        root.addWidget(self.progress)

        status_row = QHBoxLayout()
        self.status_lbl = QLabel("Ajoutez des vidéos pour commencer.")
        self.status_lbl.setObjectName("status_info")
        self.status_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.open_btn = QPushButton(t("open_folder")); self.open_btn.setObjectName("btn_secondary")
        self.open_btn.setFixedHeight(34); self.open_btn.hide()
        self.open_btn.clicked.connect(lambda: open_folder(self._output_dir))
        status_row.addWidget(self.status_lbl, 1); status_row.addWidget(self.open_btn)
        root.addLayout(status_row)

        btn_row = QHBoxLayout(); btn_row.addStretch()
        self.cancel_btn = QPushButton(t("cancel")); self.cancel_btn.setObjectName("btn_secondary")
        self.cancel_btn.setEnabled(False); self.cancel_btn.setFixedHeight(42)
        self.cancel_btn.clicked.connect(self._cancel)
        self.compress_btn = QPushButton("📦  Compresser tout")
        self.compress_btn.setMinimumWidth(180); self.compress_btn.setFixedHeight(42)
        self.compress_btn.setEnabled(False); self.compress_btn.clicked.connect(self._start_compression)
        btn_row.addWidget(self.cancel_btn); btn_row.addWidget(self.compress_btn)
        root.addLayout(btn_row)

        self._platform_btns["discord"].setChecked(True)
        self._update_platform_desc("discord")

    # ── Barre comparative ─────────────────────────────────────────────────────

    def _refresh_compare(self) -> None:
        """Met à jour la barre comparative et le badge qualité."""
        if not self._queued_files:
            self._orig_size_lbl.setText("—")
            self._target_size_lbl.setText("—")
            self._orig_bar_fill.setFixedWidth(0)
            self._target_bar_fill.setFixedWidth(0)
            self._quality_badge.setText("—")
            return

        target_bytes = self._get_target_bytes()
        target_mb = target_bytes / (1024 * 1024)

        # Calcul taille totale originale
        total_orig_bytes = sum(
            f.stat().st_size for f in self._queued_files if f.exists()
        )
        orig_mb = total_orig_bytes / (1024 * 1024)

        # Mise à jour labels
        self._orig_size_lbl.setText(f"{orig_mb:.1f} MB" if orig_mb < 1024 else f"{orig_mb/1024:.2f} GB")
        est_target_mb = min(target_mb * len(self._queued_files), orig_mb)
        self._target_size_lbl.setText(f"{est_target_mb:.1f} MB")

        # Mise à jour barres (proportionnelles)
        bar_width = self._orig_bar_bg.width() or 200
        if orig_mb > 0:
            self._orig_bar_fill.setFixedWidth(bar_width)
            ratio = min(est_target_mb / orig_mb, 1.0)
            self._target_bar_fill.setFixedWidth(int(bar_width * ratio))

        # Estimation du bitrate → badge qualité
        if self._queued_files:
            f = self._queued_files[0]
            abr = self.audio_br_combo.currentData() or 128
            vbr = compute_target_bitrate(f, target_bytes, abr)
            if vbr is None:
                kind, text = "optimal", "Impossible d'estimer"
            elif vbr >= 2000:
                kind, text = "optimal", "✅  Qualité optimale"
            elif vbr >= 800:
                kind, text = "warn", "⚠  Perte de qualité légère"
            else:
                kind, text = "danger", "🔴  Qualité très réduite"
            self._quality_badge.setText(text)
            self._quality_badge.setStyleSheet(compression_badge_style(kind))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._refresh_compare)

    # ── Platform selection ────────────────────────────────────────────────────

    _PLATFORM_DESCS = {
        "discord":  "💬 Discord — limite de 25 MB (fichiers non-Nitro). H.264 MP4 optimisé.",
        "whatsapp": "📱 WhatsApp — limite de 16 MB. Vidéo 720p compressée.",
        "email":    "📧 E-mail — limite de 10 MB. Qualité réduite pour garantir la livraison.",
        "telegram": "✈ Telegram — limite de 100 MB (comptes gratuits).",
        "custom":   "🔧 Taille personnalisée — définissez votre propre limite en MB.",
    }

    def _select_platform(self, key: str) -> None:
        self._selected_platform = key
        for k, btn in self._platform_btns.items(): btn.setChecked(k == key)
        self.custom_row.setVisible(key == "custom")
        self._update_platform_desc(key)
        self._refresh_compare()

    def _update_platform_desc(self, key: str) -> None:
        self.platform_desc.setText(self._PLATFORM_DESCS.get(key, ""))

    def _get_target_bytes(self) -> int:
        if self._selected_platform == "custom":
            return self.custom_size_spin.value() * 1024 * 1024
        return COMPRESS_TARGETS.get(self._selected_platform, 25 * 1024 * 1024)

    # ── File management ───────────────────────────────────────────────────────

    def _browse_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choisir des vidéos", str(Path.home()),
            "Vidéos (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv *.m4v *.ts);;Tous (*)",
        )
        if paths: self._on_files_dropped([Path(p) for p in paths])

    def _on_files_dropped(self, paths: list[Path]) -> None:
        added = 0
        for p in paths:
            ft = classify_file(p)
            if ft not in ("video",) or p in self._queued_files:
                if ft == "unknown": continue
                if p in self._queued_files: continue
            self._queued_files.append(p)
            info = get_media_info(p)
            tb = self._get_target_bytes()
            vbr = compute_target_bitrate(p, tb, self.audio_br_combo.currentData() or 128)
            size_hint = f"  →  ~{tb // (1024*1024)} MB" if vbr else ""
            label = f"{info.icon}  {p.name}{size_hint}"
            item = QListWidgetItem(); widget = FileProgressItem(info.icon, label)
            item.setSizeHint(widget.sizeHint())
            self.queue_list.addItem(item); self.queue_list.setItemWidget(item, widget)
            self._file_widgets.append(widget); added += 1
        if added:
            self.compress_btn.setEnabled(True)
            set_status(self.status_lbl, f"{len(self._queued_files)} vidéo(s) en file d'attente.")
            self.batch_count_lbl.setText(f"0 / {len(self._queued_files)}")
            self._refresh_compare()

    def _clear_queue(self) -> None:
        self._queued_files.clear(); self._file_widgets.clear(); self.queue_list.clear()
        self.compress_btn.setEnabled(False); set_status(self.status_lbl, "File d'attente vidée.")
        self.batch_count_lbl.setText(""); self._refresh_compare()

    def _choose_out_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Dossier de sortie")
        if folder: self._output_dir = Path(folder); self.out_dir_label.setText(folder)

    # ── Compression ───────────────────────────────────────────────────────────

    def _set_busy(self, busy: bool) -> None:
        self.compress_btn.setEnabled(not busy and bool(self._queued_files))
        self.cancel_btn.setEnabled(busy); self.drop_zone.setEnabled(not busy)
        if not busy: self.progress.setValue(0); _taskbar.clear()

    def _cancel(self) -> None:
        if self._batch_worker: self._batch_worker.cancel()
        self._set_busy(False); set_status(self.status_lbl, "Compression annulée.")

    def _start_compression(self) -> None:
        if not self._queued_files: return
        if not ffmpeg_available():
            QMessageBox.critical(self, "FFmpeg", t("ffmpeg_missing_msg")); return

        platform = self._selected_platform if self._selected_platform != "custom" else ""
        self._set_busy(True); self.open_btn.hide()
        self.batch_count_lbl.setText(f"0 / {len(self._queued_files)}")
        self._start_time = time.monotonic()
        _taskbar.set_state(_WinTaskbar.TBPF_NORMAL)
        set_status(self.status_lbl, "Démarrage de la compression…")

        compress_key = platform if platform else f"__custom__{self._get_target_bytes()}"

        self._batch_worker = BatchConvertWorker(
            self._queued_files, "mp4", self._output_dir,
            "custom", cfg.max_workers, "", "",
            compress_target=compress_key if platform else "",
            parent=self,
        )

        if self._selected_platform == "custom":
            self._batch_worker = None
            self._run_custom_compression()
            return

        self._batch_worker.overall_progress.connect(self._on_overall_progress)
        self._batch_worker.status.connect(self.status_lbl.setText)
        self._batch_worker.file_progress.connect(self._on_file_progress)
        self._batch_worker.file_done.connect(self._on_file_done)
        self._batch_worker.file_error.connect(self._on_file_error)
        self._batch_worker.all_done.connect(self._on_all_done)
        self._batch_worker.start()

    def _run_custom_compression(self) -> None:
        target_bytes = self._get_target_bytes()
        audio_kbps   = self.audio_br_combo.currentData() or 128

        from converter import _convert_sync, _build_output_path, build_compress_args

        class _CustomCompressWorker(QThread):
            file_done        = pyqtSignal(int, str, str)
            file_error       = pyqtSignal(int, str, str)
            file_progress    = pyqtSignal(int, int)
            overall_progress = pyqtSignal(int)
            all_done         = pyqtSignal(int, int)
            status           = pyqtSignal(str)

            def __init__(self_, files, out_dir, tb, abr, parent=None):
                super().__init__(parent)
                self_.files = files; self_.out_dir = out_dir
                self_.tb = tb; self_.abr = abr
                self_._cancelled = False

            def cancel(self_): self_._cancelled = True

            def run(self_) -> None:
                from converter import build_compress_args, _build_output_path, _convert_sync
                _success = 0; _errors = 0
                for i, f in enumerate(self_.files):
                    if self_._cancelled: break
                    self_.status.emit(f"⚙  [{i+1}/{len(self_.files)}]  {f.name}")
                    from converter import compute_target_bitrate
                    vbr = compute_target_bitrate(f, self_.tb, self_.abr)
                    if vbr is None:
                        self_.file_error.emit(i, str(f), "Impossible de lire la durée")
                        _errors += 1; continue

                    cargs = [
                        "-c:v", "libx264", "-b:v", f"{vbr}k", "-maxrate", f"{vbr}k",
                        "-bufsize", f"{vbr*2}k", "-c:a", "aac",
                        "-b:a", f"{self_.abr}k", "-movflags", "+faststart",
                    ]
                    from converter import PRESETS as _P
                    _P["__custom_compress__"] = {
                        "label": "custom", "fmt": "mp4", "args": cargs, "desc": ""
                    }
                    def _prog(v, idx=i): self_.file_progress.emit(idx, v)
                    ok, val = _convert_sync(f, "mp4", self_.out_dir, "__custom_compress__",
                                            progress_cb=_prog)
                    _P.pop("__custom_compress__", None)
                    if ok: _success += 1; self_.file_done.emit(i, str(f), val)
                    else:  _errors  += 1; self_.file_error.emit(i, str(f), val)
                    self_.overall_progress.emit(int((i+1)/len(self_.files)*100))
                self_.all_done.emit(_success, _errors)

        self._batch_worker = _CustomCompressWorker(
            self._queued_files, self._output_dir, target_bytes, audio_kbps, parent=self
        )
        self._batch_worker.overall_progress.connect(self._on_overall_progress)
        self._batch_worker.status.connect(self.status_lbl.setText)
        self._batch_worker.file_progress.connect(self._on_file_progress)
        self._batch_worker.file_done.connect(self._on_file_done)
        self._batch_worker.file_error.connect(self._on_file_error)
        self._batch_worker.all_done.connect(self._on_all_done)
        self._batch_worker.start()

    def _on_overall_progress(self, v: int) -> None:
        self.progress.setValue(v); _taskbar.set_progress(v)

    def _on_file_progress(self, idx: int, v: int) -> None:
        if 0 <= idx < len(self._file_widgets): self._file_widgets[idx].set_progress(v)

    def _on_file_done(self, idx: int, src: str, out: str) -> None:
        if 0 <= idx < len(self._file_widgets): self._file_widgets[idx].set_done(Path(out).name)
        self.batch_count_lbl.setText(f"{idx+1} / {len(self._queued_files)}")
        # Mise à jour stats : espace économisé approximatif
        try:
            orig_size = Path(src).stat().st_size if Path(src).exists() else 0
            out_size  = Path(out).stat().st_size if Path(out).exists() else 0
            saved = max(0, orig_size - out_size)
            stats_add_file(space_saved_bytes=saved)
        except Exception:
            stats_add_file()

    def _on_file_error(self, idx: int, _src: str, err: str) -> None:
        if 0 <= idx < len(self._file_widgets): self._file_widgets[idx].set_error(err)

    def _on_all_done(self, success: int, errors: int) -> None:
        elapsed = time.monotonic() - getattr(self, "_start_time", time.monotonic())
        self._set_busy(False); self.progress.setValue(100); self.open_btn.show()
        msg = f"✔  {success} compressé(s)" + (f"  ·  ✗ {errors} erreur(s)" if errors else "")
        set_status(self.status_lbl, msg, "ok" if not errors else "warn")
        _stats["total_seconds"] += elapsed; _stats_notify()
        if _can_notify("compress"):
            win = self.window()
            if hasattr(win, "notify"): win.notify("Compression terminée", msg)

    def add_files(self, paths: list[Path]) -> None:
        self._on_files_dropped([p for p in paths if classify_file(p) == "video"])


# ══════════════════════════════════════════════════════════════════════════════
#  Settings tab — v4.2 : Cartes, toggles, aperçus thème, pastille FFmpeg
# ══════════════════════════════════════════════════════════════════════════════

class SettingsTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._update_worker: YtdlpUpdateWorker | None = None
        self._ffmpeg_timer: QTimer | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:  # noqa: C901
        from PyQt6.QtWidgets import QSlider
        outer = QVBoxLayout(self); outer.setContentsMargins(0,0,0,0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget(); scroll.setWidget(container); outer.addWidget(scroll)
        inner = QVBoxLayout(container); inner.setContentsMargins(28,24,28,24); inner.setSpacing(18)

        hdr = QHBoxLayout()
        ic = QLabel("⚙"); ic.setStyleSheet("font-size:24px; background:transparent;")
        hdr.addWidget(ic); hdr.addWidget(make_label(t("settings_title"),"title")); hdr.addStretch()
        inner.addLayout(hdr)

        # ══════════════════════════════════════════════════════════════════════
        # CARTE 1 : Apparence & Interface
        # ══════════════════════════════════════════════════════════════════════
        app_card, _, app_content = make_card("🎨", t("appearance_card_title"))

        # Thème
        app_content.addWidget(make_section("THÈME VISUEL"))
        theme_preview_row = QHBoxLayout(); theme_preview_row.setSpacing(12)
        self._theme_btns: dict[str, QPushButton] = {}
        current_theme = ThemeManager.current()
        for key, obj_name, label in [
            ("dark",  "theme_preview_dark",  "🌙 Sombre"),
            ("oled",  "theme_preview_oled",  "⚫ OLED"),
            ("light", "theme_preview_light", "☀ Clair"),
            ("auto",  "theme_preview_auto",  "🔄 Auto"),
        ]:
            btn = QPushButton(label); btn.setObjectName(obj_name)
            btn.setCheckable(True); btn.setChecked(key == current_theme)
            btn.clicked.connect(lambda _, k=key: self._apply_theme(k))
            self._theme_btns[key] = btn; theme_preview_row.addWidget(btn)
        theme_preview_row.addStretch(); app_content.addLayout(theme_preview_row)
        desc = QLabel(t("theme_desc")); desc.setObjectName("subtitle"); desc.setWordWrap(True)
        app_content.addWidget(desc)

        # Couleur d'accent
        app_content.addWidget(make_section(t("accent_color_label")))
        accent_row = QHBoxLayout(); accent_row.setSpacing(10)
        self._accent_btns: dict[str, QPushButton] = {}
        cur_accent = cfg.accent_color
        for key, label in [("blue", t("accent_blue")), ("purple", t("accent_purple")),
                            ("green", t("accent_green")), ("pink", t("accent_pink"))]:
            btn = QPushButton(label); btn.setObjectName("theme_btn"); btn.setCheckable(True)
            btn.setChecked(key == cur_accent); btn.setFixedHeight(36)
            btn.clicked.connect(lambda _, k=key: self._apply_accent(k))
            self._accent_btns[key] = btn; accent_row.addWidget(btn)
        accent_row.addStretch(); app_content.addLayout(accent_row)

        # Opacité
        app_content.addWidget(make_section(t("opacity_label")))
        opacity_row = QHBoxLayout(); opacity_row.setSpacing(12)
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(70, 100); self._opacity_slider.setValue(cfg.window_opacity)
        self._opacity_slider.setFixedWidth(180)
        self._opacity_lbl = QLabel(f"{cfg.window_opacity} %")
        self._opacity_lbl.setObjectName("status_info"); self._opacity_lbl.setFixedWidth(44)
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_row.addWidget(self._opacity_slider); opacity_row.addWidget(self._opacity_lbl)
        opacity_row.addStretch(); app_content.addLayout(opacity_row)

        # Langue
        app_content.addWidget(hline()); app_content.addWidget(make_section("LANGUE"))
        lang_row = QHBoxLayout(); lang_row.setSpacing(10)
        self._lang_btns: dict[str, QPushButton] = {}
        cur_lang = current_language()
        for label, key in [(t("lang_en"),"en"),(t("lang_fr"),"fr")]:
            btn = QPushButton(label); btn.setObjectName("theme_btn"); btn.setCheckable(True)
            btn.setChecked(key == cur_lang); btn.setFixedHeight(36)
            btn.clicked.connect(lambda _, k=key: self._apply_language(k))
            self._lang_btns[key] = btn; lang_row.addWidget(btn)
        lang_row.addStretch(); app_content.addLayout(lang_row)
        restart_lbl = QLabel("⚠  Le changement de langue s'applique après redémarrage.")
        restart_lbl.setObjectName("subtitle"); app_content.addWidget(restart_lbl)

        # Tray toggles
        app_content.addWidget(hline())
        self._tray_close_cb = make_toggle(
            t("tray_on_close"), cfg.minimize_to_tray,
            lambda v: setattr(cfg, "minimize_to_tray", v)
        )
        self._tray_start_cb = make_toggle(
            t("start_in_tray"), cfg.start_in_tray,
            lambda v: setattr(cfg, "start_in_tray", v)
        )
        app_content.addWidget(self._tray_close_cb)
        app_content.addWidget(self._tray_start_cb)

        inner.addWidget(app_card)

        # ══════════════════════════════════════════════════════════════════════
        # CARTE 2 : Moteur de téléchargement (yt-dlp)
        # ══════════════════════════════════════════════════════════════════════
        dl_eng_card, _, dl_eng_content = make_card("⬇", t("download_engine_card"))

        # Qualité préférée
        dl_eng_content.addWidget(make_section(t("preferred_quality_label")))
        self._quality_combo = QComboBox()
        for key, lbl in [("best", t("quality_best")), ("2160", t("quality_4k")),
                          ("1080", t("quality_1080")), ("720", t("quality_720")), ("480", t("quality_480"))]:
            self._quality_combo.addItem(lbl, key)
        idx = self._quality_combo.findData(cfg.preferred_quality)
        if idx >= 0: self._quality_combo.setCurrentIndex(idx)
        self._quality_combo.currentIndexChanged.connect(
            lambda: setattr(cfg, "preferred_quality", self._quality_combo.currentData())
        )
        dl_eng_content.addWidget(self._quality_combo)

        # Mode Playlist
        self._playlist_mode_cb = make_toggle(
            t("playlist_mode"), cfg.playlist_mode,
            lambda v: setattr(cfg, "playlist_mode", v)
        )
        dl_eng_content.addWidget(self._playlist_mode_cb)

        # Auto-Tag
        self._auto_tag_cb = make_toggle(
            t("auto_tag"), cfg.auto_tag,
            lambda v: setattr(cfg, "auto_tag", v)
        )
        dl_eng_content.addWidget(self._auto_tag_cb)

        # Cookies navigateur
        dl_eng_content.addWidget(hline())
        dl_eng_content.addWidget(make_section(t("browser_cookies_label")))
        self._browser_combo = QComboBox()
        self._browser_combo.addItem(t("browser_none"), "")
        for b in ["chrome", "firefox", "edge", "brave", "opera", "safari"]:
            self._browser_combo.addItem(b.capitalize(), b)
        bidx = self._browser_combo.findData(cfg.browser_cookies)
        if bidx >= 0: self._browser_combo.setCurrentIndex(bidx)
        self._browser_combo.currentIndexChanged.connect(
            lambda: setattr(cfg, "browser_cookies", self._browser_combo.currentData())
        )
        dl_eng_content.addWidget(self._browser_combo)

        # Mise à jour yt-dlp
        dl_eng_content.addWidget(hline())
        ytdlp_row = QHBoxLayout()
        try:
            import yt_dlp as _ydl; ver = getattr(_ydl.version, "__version__", "?")
            ytdlp_row.addWidget(QLabel(t("ytdlp_version", ver=ver)))
        except Exception:
            ytdlp_row.addWidget(QLabel(t("ytdlp_not_installed")))
        ytdlp_row.addStretch()
        self.update_btn = QPushButton(t("ytdlp_update_btn")); self.update_btn.setFixedHeight(36)
        self.update_btn.clicked.connect(self._run_ytdlp_update); ytdlp_row.addWidget(self.update_btn)
        dl_eng_content.addLayout(ytdlp_row)
        self.update_status = QLabel(""); self.update_status.setObjectName("status_info"); self.update_status.setWordWrap(True)
        dl_eng_content.addWidget(self.update_status)

        inner.addWidget(dl_eng_card)

        # ══════════════════════════════════════════════════════════════════════
        # CARTE 3 : Conversion & Compression (FFmpeg)
        # ══════════════════════════════════════════════════════════════════════
        ffmpeg_card, ffmpeg_hdr, ffmpeg_content = make_card("🎞", t("conversion_card_title"))

        # Pastille dynamique dans le header
        self._ffmpeg_dot = QLabel(); self._ffmpeg_dot.setFixedSize(12, 12)
        ffmpeg_hdr.insertWidget(2, self._ffmpeg_dot)
        self._update_ffmpeg_dot()

        # Chemin FFmpeg
        ffpath = find_ffmpeg()
        ff_lbl = QLabel(t("ffmpeg_found", path=ffpath) if ffpath else t("ffmpeg_missing_lbl"))
        ff_lbl.setObjectName("status_ok" if ffpath else "status_err")
        ffmpeg_content.addWidget(ff_lbl)
        if not ffpath:
            link = QLabel(f'<a href="https://ffmpeg.org/download.html" style="color:#5A96FF;">{t("ffmpeg_guide")}</a>')
            link.setOpenExternalLinks(True); link.setTextFormat(Qt.TextFormat.RichText)
            ffmpeg_content.addWidget(link)
            hint = QLabel(t("ffmpeg_hint")); hint.setObjectName("subtitle")
            ffmpeg_content.addWidget(hint)

        ffmpeg_content.addWidget(make_section(t("ffmpeg_custom_path")))
        ffp_row = QHBoxLayout(); ffp_row.setSpacing(8)
        self.ffmpeg_path_inp = QLineEdit(); self.ffmpeg_path_inp.setText(cfg.ffmpeg_path)
        self.ffmpeg_path_inp.setPlaceholderText(t("ffmpeg_custom_placeholder"))
        self.ffmpeg_path_inp.textChanged.connect(self._schedule_ffmpeg_check)
        ffp_browse = QPushButton(t("ffmpeg_custom_browse")); ffp_browse.setObjectName("btn_secondary")
        ffp_browse.setFixedHeight(34); ffp_browse.clicked.connect(self._browse_ffmpeg)
        ffp_save = QPushButton("💾"); ffp_save.setObjectName("btn_secondary")
        ffp_save.setFixedHeight(34); ffp_save.clicked.connect(self._save_ffmpeg_path)
        ffp_row.addWidget(self.ffmpeg_path_inp, 1); ffp_row.addWidget(ffp_browse); ffp_row.addWidget(ffp_save)
        ffmpeg_content.addLayout(ffp_row)
        self.ffmpeg_path_status = QLabel(""); self.ffmpeg_path_status.setObjectName("status_info")
        ffmpeg_content.addWidget(self.ffmpeg_path_status)

        # Threads CPU
        ffmpeg_content.addWidget(hline())
        ffmpeg_content.addWidget(make_section(t("ffmpeg_threads_label")))
        threads_row = QHBoxLayout(); threads_row.setSpacing(12)
        self._threads_spin = QSpinBox(); self._threads_spin.setRange(0, 32)
        self._threads_spin.setValue(cfg.ffmpeg_threads); self._threads_spin.setFixedWidth(70)
        self._threads_spin.setSpecialValueText("Auto")
        self._threads_spin.valueChanged.connect(lambda v: setattr(cfg, "ffmpeg_threads", v))
        threads_row.addWidget(self._threads_spin); threads_row.addStretch()
        ffmpeg_content.addLayout(threads_row)

        # Priorité processus
        ffmpeg_content.addWidget(make_section(t("ffmpeg_priority_label")))
        self._priority_combo = QComboBox()
        for key, lbl in [("low", t("priority_low")), ("normal", t("priority_normal")), ("high", t("priority_high"))]:
            self._priority_combo.addItem(lbl, key)
        pidx = self._priority_combo.findData(cfg.ffmpeg_priority)
        if pidx >= 0: self._priority_combo.setCurrentIndex(pidx)
        self._priority_combo.currentIndexChanged.connect(
            lambda: setattr(cfg, "ffmpeg_priority", self._priority_combo.currentData())
        )
        ffmpeg_content.addWidget(self._priority_combo)

        # Supprimer source
        ffmpeg_content.addWidget(hline())
        self._del_source_cb = make_toggle(
            t("delete_source_toggle"), cfg.delete_source,
            lambda v: setattr(cfg, "delete_source", v)
        )
        ffmpeg_content.addWidget(self._del_source_cb)

        # Conversions parallèles
        ffmpeg_content.addWidget(hline())
        par_row = QHBoxLayout(); par_row.setSpacing(12)
        par_lbl = QLabel(t("parallel_label")); par_lbl.setObjectName("status_info")
        par_row.addWidget(par_lbl); par_row.addStretch()
        self.workers_spin = QSpinBox(); self.workers_spin.setRange(1, 4)
        self.workers_spin.setValue(cfg.max_workers); self.workers_spin.setFixedWidth(70)
        self.workers_spin.valueChanged.connect(lambda v: setattr(cfg, "max_workers", v))
        par_row.addWidget(self.workers_spin); ffmpeg_content.addLayout(par_row)
        pd = QLabel(t("parallel_desc")); pd.setObjectName("subtitle"); pd.setWordWrap(True)
        ffmpeg_content.addWidget(pd)

        inner.addWidget(ffmpeg_card)

        # ══════════════════════════════════════════════════════════════════════
        # CARTE 4 : Destinations & Organisation
        # ══════════════════════════════════════════════════════════════════════
        dest_card, _, dest_content = make_card("📁", t("destinations_card_title"))

        dest_content.addWidget(make_section(t("output_dir_label")))
        dest_dir_row = QHBoxLayout(); dest_dir_row.setSpacing(8)
        self._dest_dir_lbl = QLabel(str(cfg.download_dir)); self._dest_dir_lbl.setObjectName("status_info")
        self._dest_dir_lbl.setWordWrap(True)
        self._dest_dir_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        dest_browse_btn = QPushButton("📁 Choisir"); dest_browse_btn.setObjectName("btn_secondary")
        dest_browse_btn.setFixedHeight(34); dest_browse_btn.clicked.connect(self._choose_output_dir)
        dest_dir_row.addWidget(self._dest_dir_lbl, 1); dest_dir_row.addWidget(dest_browse_btn)
        dest_content.addLayout(dest_dir_row)

        dest_content.addWidget(hline())
        self._auto_sub_cb = make_toggle(
            t("auto_subfolders_toggle"), cfg.auto_subfolders,
            lambda v: setattr(cfg, "auto_subfolders", v)
        )
        dest_content.addWidget(self._auto_sub_cb)

        dest_content.addWidget(hline())
        dest_content.addWidget(make_section(t("file_naming_label")))
        self._naming_combo = QComboBox()
        self._naming_combo.addItem(t("naming_title"), "title")
        self._naming_combo.addItem(t("naming_artist_title"), "artist_title")
        nidx = self._naming_combo.findData(cfg.file_naming)
        if nidx >= 0: self._naming_combo.setCurrentIndex(nidx)
        self._naming_combo.currentIndexChanged.connect(
            lambda: setattr(cfg, "file_naming", self._naming_combo.currentData())
        )
        dest_content.addWidget(self._naming_combo)

        inner.addWidget(dest_card)

        # ══════════════════════════════════════════════════════════════════════
        # CARTE 5 : Notifications & Sons
        # ══════════════════════════════════════════════════════════════════════
        notif_card, _, notif_content = make_card("🔔", t("notif_card_title"))

        self.notif_master = make_toggle(
            "Activer les notifications système", cfg.notifications, self._on_notif_master_toggled
        )
        notif_content.addWidget(self.notif_master)

        self._notif_options_widget = QWidget()
        nopt = QVBoxLayout(self._notif_options_widget); nopt.setContentsMargins(8, 4, 0, 0); nopt.setSpacing(10)

        self.notif_dl_cb   = make_toggle("📥  Fin de téléchargement",          cfg.notif_on_download, lambda v: setattr(cfg, "notif_on_download", v))
        self.notif_conv_cb = make_toggle("🔄  Fin de conversion / compression", cfg.notif_on_convert,  lambda v: setattr(cfg, "notif_on_convert", v))
        self.notif_err_cb  = make_toggle("❌  En cas d'erreur",                 cfg.notif_on_error,    lambda v: setattr(cfg, "notif_on_error", v))
        self.notif_tray_cb = make_toggle(t("notif_tray_bg"),                   cfg.notif_tray_bg,     lambda v: setattr(cfg, "notif_tray_bg", v))
        self.notif_sound_cb = make_toggle("🔊  Son de notification (Windows / macOS)", cfg.notif_sound, lambda v: setattr(cfg, "notif_sound", v))

        for w in [self.notif_dl_cb, self.notif_conv_cb, self.notif_err_cb, self.notif_tray_cb, self.notif_sound_cb]:
            nopt.addWidget(w)

        notif_content.addWidget(self._notif_options_widget)
        self._notif_options_widget.setEnabled(cfg.notifications)

        inner.addWidget(notif_card)

        # ══════════════════════════════════════════════════════════════════════
        # CARTE 6 : Presets personnalisés
        # ══════════════════════════════════════════════════════════════════════
        preset_card, _, preset_content = make_card("⭐", "Presets personnalisés")

        self.preset_name_inp = QLineEdit(); self.preset_name_inp.setPlaceholderText(t("preset_name_ph"))
        preset_content.addWidget(self.preset_name_inp)
        pr_row = QHBoxLayout(); pr_row.setSpacing(12)
        fmt_col = QVBoxLayout(); fmt_col.addWidget(make_section(t("preset_fmt_label")))
        self.preset_fmt_combo = QComboBox()
        for f in ["mp4","mp3","mkv","flac","wav","gif","jpg","png"]: self.preset_fmt_combo.addItem(f,f)
        fmt_col.addWidget(self.preset_fmt_combo); pr_row.addLayout(fmt_col)
        args_col = QVBoxLayout(); args_col.addWidget(make_section(t("preset_args_label")))
        self.preset_args_inp = QLineEdit(); self.preset_args_inp.setPlaceholderText(t("preset_args_ph"))
        args_col.addWidget(self.preset_args_inp); pr_row.addLayout(args_col, 1); preset_content.addLayout(pr_row)
        pr_btn_row = QHBoxLayout()
        save_btn = QPushButton(t("save_preset")); save_btn.setFixedHeight(34); save_btn.clicked.connect(self._save_preset)
        del_btn = QPushButton(t("delete_preset")); del_btn.setObjectName("btn_danger"); del_btn.setFixedHeight(34)
        del_btn.clicked.connect(self._delete_preset)
        pr_btn_row.addWidget(save_btn); pr_btn_row.addWidget(del_btn); pr_btn_row.addStretch()
        preset_content.addLayout(pr_btn_row)
        self.preset_status = QLabel(""); self.preset_status.setObjectName("status_info")
        preset_content.addWidget(self.preset_status)
        self.preset_list = QListWidget(); self.preset_list.setMaximumHeight(80)
        self.preset_list.itemClicked.connect(self._select_preset); preset_content.addWidget(self.preset_list)
        self._refresh_preset_list()
        inner.addWidget(preset_card)

        # ══════════════════════════════════════════════════════════════════════
        # CARTE 7 : Maintenance & Aide
        # ══════════════════════════════════════════════════════════════════════
        maint_card, _, maint_content = make_card("🔧", t("maintenance_card_title"))

        maint_btn_row1 = QHBoxLayout(); maint_btn_row1.setSpacing(10)
        clr_hist_btn = QPushButton(t("clear_dl_history_btn")); clr_hist_btn.setObjectName("btn_secondary")
        clr_hist_btn.setFixedHeight(36); clr_hist_btn.clicked.connect(self._maint_clear_history)
        maint_btn_row1.addWidget(clr_hist_btn); maint_btn_row1.addStretch()
        maint_content.addLayout(maint_btn_row1)

        maint_btn_row2 = QHBoxLayout(); maint_btn_row2.setSpacing(10)
        open_log_btn = QPushButton(t("open_log_btn")); open_log_btn.setObjectName("btn_secondary")
        open_log_btn.setFixedHeight(36); open_log_btn.clicked.connect(self._maint_open_log)
        maint_btn_row2.addWidget(open_log_btn); maint_btn_row2.addStretch()
        maint_content.addLayout(maint_btn_row2)

        maint_content.addWidget(hline())

        maint_btn_row3 = QHBoxLayout(); maint_btn_row3.setSpacing(10)
        dis_tray_btn = QPushButton(t("disable_tray_btn")); dis_tray_btn.setObjectName("btn_secondary")
        dis_tray_btn.setFixedHeight(36); dis_tray_btn.clicked.connect(self._maint_disable_tray)
        maint_btn_row3.addWidget(dis_tray_btn); maint_btn_row3.addStretch()
        maint_content.addLayout(maint_btn_row3)

        maint_content.addWidget(hline())

        reset_btn = QPushButton(t("reset_settings_btn")); reset_btn.setObjectName("btn_danger")
        reset_btn.setFixedHeight(36); reset_btn.clicked.connect(self._maint_reset_settings)
        maint_content.addWidget(reset_btn)

        self._maint_status = QLabel(""); self._maint_status.setObjectName("status_info")
        maint_content.addWidget(self._maint_status)

        inner.addWidget(maint_card)

        # ══════════════════════════════════════════════════════════════════════
        # CARTE 8 : À propos
        # ══════════════════════════════════════════════════════════════════════
        about_card, _, about_content = make_card("ℹ", "À propos")

        about_content.addWidget(QLabel(f"OmniMedia  v{APP_VERSION}"))
        self.version_status = QLabel(t("checking_version")); self.version_status.setObjectName("status_info")
        about_content.addWidget(self.version_status)
        gh = QLabel(f'<a href="https://github.com/SanoBld/OmniMedia" style="color:#5A96FF;">{t("github_link")}</a>')
        gh.setOpenExternalLinks(True); gh.setTextFormat(Qt.TextFormat.RichText)
        about_content.addWidget(gh)
        inner.addWidget(about_card)
        inner.addStretch()

    # ── Pastille FFmpeg dynamique ─────────────────────────────────────────────

    def _update_ffmpeg_dot(self) -> None:
        ok = ffmpeg_available()
        self._ffmpeg_dot.setObjectName("ffmpeg_dot_ok" if ok else "ffmpeg_dot_err")
        self._ffmpeg_dot.setToolTip("FFmpeg détecté ✔" if ok else "FFmpeg introuvable ✗")
        self._ffmpeg_dot.style().unpolish(self._ffmpeg_dot)
        self._ffmpeg_dot.style().polish(self._ffmpeg_dot)

    def _schedule_ffmpeg_check(self) -> None:
        """Déclenche la vérification 800 ms après le dernier keystroke."""
        if self._ffmpeg_timer is None:
            self._ffmpeg_timer = QTimer(self)
            self._ffmpeg_timer.setSingleShot(True)
            self._ffmpeg_timer.timeout.connect(self._live_ffmpeg_check)
        self._ffmpeg_timer.start(800)

    def _live_ffmpeg_check(self) -> None:
        val = self.ffmpeg_path_inp.text().strip()
        if val:
            p = Path(val)
            ok = p.is_file()
        else:
            ok = ffmpeg_available()

        self._ffmpeg_dot.setObjectName("ffmpeg_dot_ok" if ok else "ffmpeg_dot_warn")
        self._ffmpeg_dot.setToolTip(
            f"Chemin valide ✔  {val}" if ok else "Chemin introuvable"
        )
        self._ffmpeg_dot.style().unpolish(self._ffmpeg_dot)
        self._ffmpeg_dot.style().polish(self._ffmpeg_dot)

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _on_notif_master_toggled(self, enabled: bool) -> None:
        cfg.notifications = enabled
        self._notif_options_widget.setEnabled(enabled)

    def _apply_accent(self, key: str) -> None:
        cfg.accent_color = key
        for k, btn in self._accent_btns.items(): btn.setChecked(k == key)

    def _on_opacity_changed(self, value: int) -> None:
        cfg.window_opacity = value
        self._opacity_lbl.setText(f"{value} %")
        win = self.window()
        if win: win.setWindowOpacity(value / 100.0)

    def _choose_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Dossier de sortie par défaut")
        if folder:
            cfg.download_dir = folder
            self._dest_dir_lbl.setText(folder)

    def _maint_clear_history(self) -> None:
        from downloader import history as dl_history
        dl_history.clear()
        win = self.window()
        if hasattr(win, "_dl_tab"): win._dl_tab._reload_history()
        set_status(self._maint_status, t("history_cleared"), "ok")

    def _maint_open_log(self) -> None:
        log_path = Path.home() / ".omnimedia" / "omnimedia.log"
        if log_path.exists():
            open_folder(log_path)
        else:
            set_status(self._maint_status, t("log_not_found"), "warn")

    def _maint_disable_tray(self) -> None:
        cfg.minimize_to_tray = False
        self._tray_close_cb.setChecked(False)
        set_status(self._maint_status, "✔  Mode arrière-plan désactivé.", "ok")

    def _maint_reset_settings(self) -> None:
        reply = QMessageBox.question(
            self, t("reset_confirm_title"), t("reset_confirm_msg"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            cfg.reset()
            set_status(self._maint_status, t("reset_done"), "ok")

    def _apply_theme(self, key: str) -> None:
        ThemeManager.apply(key)
        for k, btn in self._theme_btns.items(): btn.setChecked(k == key)
        self._update_ffmpeg_dot()

    def _apply_language(self, lang: str) -> None:
        set_language(lang); cfg.language = lang
        for k, btn in self._lang_btns.items(): btn.setChecked(k == lang)

    def _browse_ffmpeg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Sélectionner l'exécutable ffmpeg",
            str(Path.home()), "Exécutable (ffmpeg ffmpeg.exe *.exe);;Tous (*)")
        if path:
            self.ffmpeg_path_inp.setText(path)
            self._live_ffmpeg_check()

    def _save_ffmpeg_path(self) -> None:
        val = self.ffmpeg_path_inp.text().strip()
        if val and not Path(val).is_file():
            set_status(self.ffmpeg_path_status, t("ffmpeg_custom_invalid"), "err"); return
        cfg.ffmpeg_path = val; set_status(self.ffmpeg_path_status, t("ffmpeg_custom_saved"), "ok")
        self._update_ffmpeg_dot()

    def _refresh_preset_list(self) -> None:
        self.preset_list.clear()
        for name in PresetManager.list_names(): self.preset_list.addItem(f"⭐  {name}")

    def _select_preset(self, item: QListWidgetItem) -> None:
        name = item.text().replace("⭐  ","").strip(); self.preset_name_inp.setText(name)
        custom = PresetManager.load_custom()
        if name in custom:
            p = custom[name]; fmt = p.get("fmt") or ""
            idx = self.preset_fmt_combo.findData(fmt)
            if idx >= 0: self.preset_fmt_combo.setCurrentIndex(idx)
            self.preset_args_inp.setText(" ".join(p.get("args",[])))

    def _save_preset(self) -> None:
        name = self.preset_name_inp.text().strip()
        if not name: set_status(self.preset_status, t("preset_err_name"), "err"); return
        import shlex
        args_text = self.preset_args_inp.text().strip()
        try: args = shlex.split(args_text) if args_text else []
        except ValueError: args = args_text.split()
        PresetManager.save(name, self.preset_fmt_combo.currentData(), args)
        self._refresh_preset_list(); self._notify_conv_tab()
        set_status(self.preset_status, t("preset_saved", name=name), "ok")

    def _delete_preset(self) -> None:
        name = self.preset_name_inp.text().strip()
        if not name: set_status(self.preset_status, t("preset_err_name"), "err"); return
        PresetManager.delete(name); self._refresh_preset_list(); self._notify_conv_tab()
        set_status(self.preset_status, t("preset_deleted", name=name), "ok")
        self.preset_name_inp.clear(); self.preset_args_inp.clear()

    def _notify_conv_tab(self) -> None:
        win = self.window()
        if hasattr(win, "_conv_tab"): win._conv_tab.refresh_presets()

    def _run_ytdlp_update(self) -> None:
        self.update_btn.setEnabled(False); set_status(self.update_status, "Mise à jour…")
        self._update_worker = YtdlpUpdateWorker(parent=self)
        self._update_worker.finished.connect(self._on_update_done); self._update_worker.start()

    def _on_update_done(self, ok: bool, msg: str) -> None:
        self.update_btn.setEnabled(True)
        set_status(self.update_status, msg, "ok" if ok else "err")
        if _can_notify("convert"):
            win = self.window()
            if hasattr(win, "notify"):
                win.notify(t("notif_ytdlp_done" if ok else "notif_ytdlp_err"), msg.splitlines()[0])

    def set_version_status(self, msg: str, kind: str = "info") -> None:
        set_status(self.version_status, msg, kind)


# ══════════════════════════════════════════════════════════════════════════════
#  Header bar
# ══════════════════════════════════════════════════════════════════════════════

class HeaderBar(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent); self.setFixedHeight(60)
        self.setStyleSheet(f"background:{COLORS['bg_card']}; border-bottom:1px solid {COLORS['border_soft']};")
        lay = QHBoxLayout(self); lay.setContentsMargins(20,0,20,0); lay.setSpacing(10)
        logo_lbl = QLabel()
        if LOGO_PATH.exists():
            pm = QPixmap(str(LOGO_PATH)).scaled(32,32,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(pm)
        logo_lbl.setStyleSheet("background:transparent;")
        name_lbl = QLabel("OmniMedia")
        name_lbl.setStyleSheet(f"font-size:16px; font-weight:700; color:{COLORS['text_primary']}; letter-spacing:-0.3px; background:transparent;")
        ver = QLabel(f"v{APP_VERSION}"); ver.setStyleSheet(badge_style("info"))
        ffok = ffmpeg_available()
        ff_badge = QLabel(t("ffmpeg_ok") if ffok else t("ffmpeg_err"))
        ff_badge.setStyleSheet(badge_style("ok" if ffok else "err"))
        ff_badge.setToolTip(find_ffmpeg() or "FFmpeg not found.")
        try:
            import yt_dlp as _; yt_badge = QLabel(t("ytdlp_ok")); yt_badge.setStyleSheet(badge_style("ok"))
        except ImportError:
            yt_badge = QLabel(t("ytdlp_err")); yt_badge.setStyleSheet(badge_style("err"))
        lay.addWidget(logo_lbl); lay.addWidget(name_lbl); lay.addWidget(ver); lay.addStretch()
        lay.addWidget(ff_badge); lay.addWidget(yt_badge)


# ══════════════════════════════════════════════════════════════════════════════
#  Main window
# ══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} Converter & Downloader")
        self.setWindowIcon(app_icon()); self.setMinimumSize(660,640); self.resize(820,940)
        self.setAcceptDrops(True)
        self._tray: QSystemTrayIcon | None = None
        self._settings_tab: SettingsTab | None = None
        self._setup_ui(); self._setup_tray(); self._attach_taskbar(); self._check_github_version()
        if cfg.window_opacity < 100:
            self.setWindowOpacity(cfg.window_opacity / 100.0)

    def _setup_ui(self) -> None:
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        root.addWidget(HeaderBar())

        # Conteneur onglets + overlay superposé
        tab_container = QWidget()
        tab_container.setObjectName("tab_container")
        tab_container_layout = QVBoxLayout(tab_container)
        tab_container_layout.setContentsMargins(0,0,0,0); tab_container_layout.setSpacing(0)

        self.tabs = FadingTabWidget()
        self.tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._dl_tab       = DownloadTab()
        self._conv_tab     = ConvertTab()
        self._comp_tab     = CompressorTab()
        self._settings_tab = SettingsTab()

        self.tabs.addTab(self._dl_tab,       t("tab_download"))
        self.tabs.addTab(self._conv_tab,     t("tab_convert"))
        self.tabs.addTab(self._comp_tab,     "  📦  Compresser")
        self.tabs.addTab(self._settings_tab, t("tab_settings"))

        tab_container_layout.addWidget(self.tabs)
        root.addWidget(tab_container, 1)

        # Overlay Drag & Drop
        self._drag_overlay = DragOverlay(central)
        self._drag_overlay.set_drop_callback(self._route_drop)
        self._drag_overlay.hide()

        # Dashboard stats
        self._stats_bar = StatsBar()
        root.addWidget(self._stats_bar)

        footer = QLabel(t("footer", ver=APP_VERSION))
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(
            f"font-size:11px; color:{COLORS['text_muted']}; background:{COLORS['bg_card']}; "
            f"border-top:1px solid {COLORS['border_soft']}; padding:6px;"
        )
        root.addWidget(footer)

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable(): return
        self._tray = QSystemTrayIcon(app_icon(), parent=self)
        menu = QMenu()
        show_act = menu.addAction(t("tray_show")); show_act.triggered.connect(self.show)
        menu.addSeparator()
        quit_act = menu.addAction(t("tray_quit")); quit_act.triggered.connect(QApplication.quit)
        self._tray.setContextMenu(menu); self._tray.setToolTip("OmniMedia")
        self._tray.activated.connect(self._tray_activated); self._tray.show()

    def _attach_taskbar(self) -> None:
        try: _taskbar.attach(int(self.winId()))
        except Exception: pass

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show(); self.raise_(); self.activateWindow()

    def notify(self, title: str, msg: str) -> None:
        if self._tray and QSystemTrayIcon.isSystemTrayAvailable():
            self._tray.showMessage(title, msg, QSystemTrayIcon.MessageIcon.Information, 4000)
        if cfg.notif_sound and sys.platform == "win32":
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONINFORMATION)
            except Exception:
                pass

    def _check_github_version(self) -> None:
        checker = VersionChecker(APP_VERSION, parent=self)
        checker.update_available.connect(self._on_update_available)
        checker.up_to_date.connect(self._on_up_to_date)
        checker.start()

    def _on_update_available(self, latest: str) -> None:
        if self._settings_tab:
            self._settings_tab.set_version_status(t("version_new", latest=latest, ver=APP_VERSION), "warn")
        if cfg.notifications:
            self.notify(t("notif_update_title"), t("notif_update_body", latest=latest))

    def _on_up_to_date(self) -> None:
        if self._settings_tab:
            self._settings_tab.set_version_status(t("version_ok", ver=APP_VERSION), "ok")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Redimensionne l'overlay
        if hasattr(self, "_drag_overlay") and self.centralWidget():
            cw = self.centralWidget()
            self._drag_overlay.setGeometry(8, 8, cw.width() - 16, cw.height() - 16)

    # ── Drag & Drop (fenêtre entière) ─────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            # Affiche l'overlay
            if hasattr(self, "_drag_overlay") and self.centralWidget():
                cw = self.centralWidget()
                self._drag_overlay.setGeometry(8, 8, cw.width() - 16, cw.height() - 16)
                self._drag_overlay.show()
                self._drag_overlay.raise_()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        if hasattr(self, "_drag_overlay"):
            self._drag_overlay.hide()

    def dropEvent(self, event: QDropEvent) -> None:
        if hasattr(self, "_drag_overlay"):
            self._drag_overlay.hide()
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls()]
        self._route_drop(paths)
        event.acceptProposedAction()

    def _route_drop(self, paths: list[Path]) -> None:
        videos = [p for p in paths if classify_file(p) == "video"]
        media  = [p for p in paths if classify_file(p) != "unknown"]
        if videos and len(videos) == len(media):
            self.tabs.setCurrentWidget(self._comp_tab); self._comp_tab.add_files(videos)
        elif media:
            self.tabs.setCurrentWidget(self._conv_tab); self._conv_tab.add_files(media)

    def closeEvent(self, event) -> None:
        if cfg.minimize_to_tray and self._tray and QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore(); self.hide()
            if cfg.notif_tray_bg:
                self._tray.showMessage("OmniMedia", t("tray_running"), QSystemTrayIcon.MessageIcon.Information, 2000)
        else:
            event.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME); app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(app_icon())
    app.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app.setQuitOnLastWindowClosed(False)
    ThemeManager.setup(app)
    window = MainWindow(); window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
