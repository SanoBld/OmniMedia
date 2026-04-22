"""
main.py — OmniMedia v5.5
v5.5 :
  - Icônes SVG inline remplacent les emojis dans les sections clés
  - Surlignage souris adapté au thème via QSS
  - Console Windows masquée (CREATE_NO_WINDOW sur tous les subprocess)
  - MusicBrainz : enrichissement metadata audio (artiste, album, genre, ISRC, MBID…)
  - À propos enrichi : tous les services utilisés avec remerciements
  - Sections vitesse/ETA corrigées (polices sans fallback emoji)
"""
from __future__ import annotations

import sys, os, subprocess, time
from pathlib import Path

# ── Logging (avant tout autre import OmniMedia) ───────────────────────────────
from app_logger import setup_logging, get_logger, log_path
setup_logging()
logger = get_logger(__name__)

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

from PyQt6.QtCore    import (QThread, pyqtSignal, Qt, QTimer, QSize, QPoint,
                              QPropertyAnimation, QEasingCurve, pyqtProperty)
from PyQt6.QtGui     import (QDragEnterEvent, QDropEvent, QColor, QIcon, QPixmap,
                              QPainter, QPainterPath)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QButtonGroup,
    QProgressBar, QTabWidget, QFrame, QFileDialog, QListWidget,
    QListWidgetItem, QComboBox, QSizePolicy, QMessageBox,
    QScrollArea, QSystemTrayIcon, QMenu, QCheckBox, QSpinBox,
    QGraphicsOpacityEffect,
)

from icons import icon as svg_icon

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
    check_ffmpeg_capabilities,
)

APP_NAME    = "OmniMedia"
APP_VERSION = "5.5.0"
LOGO_PATH   = resource_path("logoOmniMedia.png")

set_language(cfg.language)

# ── Stats globales (dashboard) ────────────────────────────────────────────────
_stats = {
    "files_processed": 0,
    "space_saved_mb":  0.0,
    "total_seconds":   0.0,
    "_start_time":     None,
}
_stats_listeners: list = []

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
    _app:    QApplication | None = None
    _theme:  str = cfg.theme
    _timer:  QTimer | None = None
    _last_dark: bool | None = None

    @classmethod
    def setup(cls, app: QApplication) -> None:
        cls._app = app
        cls.apply(cls._theme)
        # Re-détection automatique pour les thèmes "auto" et "system"
        cls._timer = QTimer()
        cls._timer.setInterval(30_000)   # 30 secondes
        cls._timer.timeout.connect(cls._check_system_theme)
        cls._timer.start()

    @classmethod
    def apply(cls, theme: str) -> None:
        cls._theme = theme; cfg.theme = theme
        if cls._app:
            cls._app.setStyleSheet(get_stylesheet(theme))

    @classmethod
    def current(cls) -> str:
        return cls._theme

    @classmethod
    def _check_system_theme(cls) -> None:
        """Appelé toutes les 30s — recharge le thème si dark/light a changé dans l'OS."""
        if cls._theme not in ("auto", "system"):
            return
        from ui_styles import _detect_system_dark
        is_dark = _detect_system_dark()
        if is_dark != cls._last_dark:
            cls._last_dark = is_dark
            if cls._app:
                cls._app.setStyleSheet(get_stylesheet(cls._theme))


# ── UI helpers ────────────────────────────────────────────────────────────────

def open_folder(path: str | Path) -> None:
    p = Path(path); target = p if p.is_dir() else p.parent
    if sys.platform == "win32":
        os.startfile(str(target))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen(["xdg-open", str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def hline() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.Shape.HLine); f.setFixedHeight(1)
    # Le style est géré par QSS via QFrame[frameShape="4"] dans ui_styles.py
    f.setStyleSheet("")
    return f

def vline() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.Shape.VLine); f.setFixedWidth(1)
    f.setStyleSheet("")
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

def make_toggle(label: str, checked: bool, callback) -> "AnimatedToggle":
    """Compatibilité — redirige vers AnimatedToggle."""
    tog = AnimatedToggle(label)
    tog.setChecked(checked)
    tog.toggled.connect(callback)
    return tog


# ══════════════════════════════════════════════════════════════════════════════
#  AnimatedToggle — toggle pill custom avec knob animé
# ══════════════════════════════════════════════════════════════════════════════

class AnimatedToggle(QCheckBox):
    """
    Toggle switch avec knob circulaire animé.
    Utilise pyqtProperty + QPropertyAnimation pour une compatibilité PyQt6 garantie.
    Respecte cfg.animations_enabled.
    """
    _TW, _TH = 46, 26   # track width / height
    _KR       = 10       # knob radius

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self._knob_pos: float = 1.0 if self.isChecked() else 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(max(32, self._TH + 6))
        # Pas de stateChanged — toggled est le signal correct et non déprécié
        self.toggled.connect(self._on_toggled)

    # ── pyqtProperty float pour QPropertyAnimation ────────────────────────────

    def _get_knob_pos(self) -> float:
        return self._knob_pos

    def _set_knob_pos(self, v: float) -> None:
        self._knob_pos = float(v)
        self.update()

    knob_pos = pyqtProperty(float, _get_knob_pos, _set_knob_pos)

    # ── Animation ─────────────────────────────────────────────────────────────

    def _on_toggled(self, checked: bool) -> None:
        target = 1.0 if checked else 0.0
        if cfg.animations_enabled:
            anim = QPropertyAnimation(self, b"knob_pos", self)
            anim.setDuration(180)
            anim.setStartValue(self._knob_pos)
            anim.setEndValue(target)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.start()
        else:
            self._knob_pos = target
            self.update()

    # ── Taille ────────────────────────────────────────────────────────────────

    def sizeHint(self) -> QSize:
        sh = super().sizeHint()
        return QSize(sh.width() + self._TW + 14, max(sh.height(), self._TH + 8))

    # ── Rendu ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        tw, th = self._TW, self._TH
        ty = (self.height() - th) // 2

        # ── Track (couleur interpolée off→on) ─────────────────────────────
        off_c = QColor(COLORS.get("border_soft", "#242E4C"))
        on_c  = QColor(COLORS.get("accent",      "#3B7DF8"))
        t = max(0.0, min(1.0, self._knob_pos))
        tr = int(off_c.red()   + (on_c.red()   - off_c.red())   * t)
        tg = int(off_c.green() + (on_c.green() - off_c.green()) * t)
        tb = int(off_c.blue()  + (on_c.blue()  - off_c.blue())  * t)

        track = QPainterPath()
        track.addRoundedRect(0.0, float(ty), float(tw), float(th), th / 2.0, th / 2.0)
        p.fillPath(track, QColor(tr, tg, tb))

        # ── Knob ──────────────────────────────────────────────────────────
        margin = 3
        kr = float(self._KR)  # Force en float
        travel = float(tw - 2 * margin - 2 * kr)
        kx = float(margin + kr + travel * self._knob_pos)
        ky = float(ty + th / 2.0)

        # Shadow subtile — addEllipse(x, y, w, h) positionne le coin supérieur gauche
        # → décaler de -kr pour centrer sur (kx, ky)
        shadow = QPainterPath()
        shadow.addEllipse(kx - kr, ky - kr + 1.0, kr * 2, kr * 2)
        p.fillPath(shadow, QColor(0, 0, 0, 35))

        # Knob blanc centré
        knob = QPainterPath()
        knob.addEllipse(kx - kr, ky - kr, kr * 2, kr * 2)
        p.fillPath(knob, QColor("#FFFFFF"))

        # ── Label ─────────────────────────────────────────────────────────
        if self.text():
            col = QColor(COLORS.get("text_primary" if self.isEnabled() else "text_muted",
                                    "#E2EAF8"))
            p.setPen(col)
            font = self.font(); font.setPixelSize(13); p.setFont(font)
            p.drawText(
                self.rect().adjusted(tw + 14, 0, 0, 0),
                Qt.AlignmentFlag.AlignVCenter,
                self.text(),
            )

        p.end()

def make_card(icon: str, title: str) -> tuple[QFrame, QHBoxLayout, QVBoxLayout]:
    """
    Crée une carte settings avec icône + titre.
    Retourne (frame, header_layout, content_layout).
    Sans séparateur visuel — l'espace blanc fait office de séparation.
    """
    card = QFrame(); card.setObjectName("settings_card")
    outer = QVBoxLayout(card); outer.setContentsMargins(28, 22, 28, 22); outer.setSpacing(18)

    # Header
    hdr = QHBoxLayout(); hdr.setSpacing(12)
    icon_lbl = QLabel(icon); icon_lbl.setObjectName("card_section_icon")
    title_lbl = QLabel(title); title_lbl.setObjectName("card_section_title")
    hdr.addWidget(icon_lbl); hdr.addWidget(title_lbl); hdr.addStretch()
    outer.addLayout(hdr)
    # Pas de hline ici — le spacing du layout suffit

    # Layout contenu — espacement 20px pour une meilleure aération
    content = QVBoxLayout(); content.setSpacing(20)
    outer.addLayout(content)

    return card, hdr, content


# ── Scroll tab helper ─────────────────────────────────────────────────────────

def _make_scroll_tab(parent: QWidget, max_width: int = 700) -> QVBoxLayout:
    """
    Crée un QScrollArea centré avec largeur max et marges généreuses.
    Retourne le layout racine (root) à utiliser pour ajouter des widgets.
    À appeler en début de chaque _setup_ui() de tab.
    """
    scroll = QScrollArea(parent)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    # Wrapper qui remplit la scroll area
    outer_widget = QWidget()
    scroll.setWidget(outer_widget)

    # Layout horizontal pour centrer le contenu
    h_wrap = QHBoxLayout(outer_widget)
    h_wrap.setContentsMargins(0, 0, 0, 0)
    h_wrap.setSpacing(0)
    h_wrap.addStretch(1)

    # Widget de contenu à largeur max
    content = QWidget()
    content.setMaximumWidth(max_width)
    h_wrap.addWidget(content, 10)
    h_wrap.addStretch(1)

    root = QVBoxLayout(content)
    root.setContentsMargins(40, 40, 40, 40)
    root.setSpacing(25)

    # Layout principal du tab
    tab_layout = QVBoxLayout(parent)
    tab_layout.setContentsMargins(0, 0, 0, 0)
    tab_layout.setSpacing(0)
    tab_layout.addWidget(scroll)

    return root


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
        self._bar.setFixedSize(90, 5)
        self._bar.setStyleSheet("")  # hérite du QSS global
        lay.addWidget(self._status); lay.addWidget(icon_lbl)
        lay.addWidget(self._name, 1); lay.addWidget(self._bar)

    def set_progress(self, v: int) -> None: self._bar.setValue(v)

    def set_done(self, name: str) -> None:
        self._status.setText("✔")
        self._status.setStyleSheet(f"color:{COLORS['success']}; background:transparent; font-size:13px;")
        self._name.setText(name)
        self._name.setStyleSheet(f"background:transparent; color:{COLORS['success']}; font-size:12px;")
        self._bar.setValue(100)
        self._flash()

    def set_error(self, err: str) -> None:
        self._status.setText("✗")
        self._status.setStyleSheet(f"color:{COLORS['danger']}; background:transparent; font-size:13px;")
        self._name.setText(err.splitlines()[0][:55])
        self._name.setStyleSheet(f"background:transparent; color:{COLORS['danger']}; font-size:12px;")
        self._flash()

    def _flash(self) -> None:
        if not cfg.animations_enabled:
            return
        eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(400)
        anim.setStartValue(0.25)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._flash_anim = anim  # référence Python — évite crash GC PyQt6
        anim.start()


# ── Drop zone ─────────────────────────────────────────────────────────────────

class DropZone(QFrame):
    def __init__(self, on_drop, parent=None) -> None:
        super().__init__(parent); self.setObjectName("drop_zone")
        self.setAcceptDrops(True); self.setMinimumHeight(120); self._on_drop = on_drop
        lay = QVBoxLayout(self); lay.setAlignment(Qt.AlignmentFlag.AlignCenter); lay.setSpacing(8)
        self.icon_lbl = QLabel("⬇"); self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setStyleSheet(f"font-size:28px; background:transparent; color:{COLORS['accent']};")
        self.text_lbl = QLabel(t("drop_zone_text")); self.text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_lbl.setStyleSheet(
            f"font-size:14px; font-weight:600; color:{COLORS['text_secondary']}; background:transparent;"
        )
        self.sub_lbl = QLabel(t("drop_zone_sub")); self.sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_lbl.setStyleSheet(
            f"font-size:12px; color:{COLORS['text_muted']}; background:transparent;"
        )
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
    quand un fichier est survolé.
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
        if self.parent():
            self.setGeometry(8, 8,
                             self.parent().width() - 16,
                             self.parent().height() - 16)
        super().resizeEvent(event)


# ── Stats Dashboard (barre du bas) ───────────────────────────────────────────

class StatsBar(QFrame):
    """Panneau minimaliste : liste des fichiers modifiés."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("stats_bar")
        self.setFixedHeight(36)
        lay = QHBoxLayout(self); lay.setContentsMargins(24, 0, 24, 0); lay.setSpacing(8)

        self._lbl = QLabel("Aucun fichier modifié pour l'instant.")
        self._lbl.setObjectName("stat_label")
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._lbl)

        _stats_listeners.append(self.refresh)

    def refresh(self) -> None:
        n = _stats["files_processed"]
        if n == 0:
            self._lbl.setText("Aucun fichier modifié pour l'instant.")
        elif n == 1:
            self._lbl.setText("✔  1 fichier modifié")
        else:
            self._lbl.setText(f"✔  {n} fichiers modifiés")


# ── Onglets avec animation fondu ──────────────────────────────────────────────

class FadingTabWidget(QTabWidget):
    """QTabWidget avec fondu + légère translation verticale au changement d'onglet."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._anim: QPropertyAnimation | None = None
        self._pos_anim: QPropertyAnimation | None = None
        self.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int) -> None:
        widget = self.widget(index)
        if widget is None:
            return
        if not cfg.animations_enabled:
            return

        # Fondu opacité
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: widget.setGraphicsEffect(None))
        self._anim = anim

        anim.start()


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
        # Restaurer l'état ouvert/fermé
        _panel_open = cfg.get("adv_panel_open", False)
        self.toggle_btn = QPushButton(t("adv_options_open" if _panel_open else "adv_options_closed"))
        self.toggle_btn.setObjectName("btn_advanced"); self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(_panel_open)
        self.toggle_btn.setFixedHeight(32)
        self.toggle_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.toggle_btn.clicked.connect(self._toggle)
        outer.addWidget(self.toggle_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self.panel = QFrame(); self.panel.setObjectName("advanced_panel")
        self.panel.setVisible(_panel_open)   # ouvert si sauvegardé comme tel
        pl = QVBoxLayout(self.panel); pl.setContentsMargins(20,18,20,18); pl.setSpacing(18)

        row1 = QHBoxLayout(); row1.setSpacing(20)
        col_br = QVBoxLayout(); col_br.setSpacing(8)
        col_br.addWidget(make_section(t("audio_bitrate")))
        self.bitrate_combo = QComboBox()
        for lbl, val in [(t("bitrate_128"),"128k"),(t("bitrate_192"),"192k"),(t("bitrate_320"),"320k")]:
            self.bitrate_combo.addItem(lbl, val)
        # Restaurer le bitrate sauvegardé
        saved_br = cfg.get("dl_audio_bitrate", "192k")
        br_idx = self.bitrate_combo.findData(saved_br)
        self.bitrate_combo.setCurrentIndex(br_idx if br_idx >= 0 else 1)
        self.bitrate_combo.setMinimumWidth(150)
        self.bitrate_combo.currentIndexChanged.connect(
            lambda: cfg.set("dl_audio_bitrate", self.bitrate_combo.currentData())
        )
        col_br.addWidget(self.bitrate_combo); row1.addLayout(col_br)
        col_res = QVBoxLayout(); col_res.setSpacing(8)
        col_res.addWidget(make_section(t("max_resolution")))
        self.res_combo = QComboBox()
        for lbl, val in [(t("res_best"),"best"),("1080p","1080"),("720p","720"),("480p","480")]:
            self.res_combo.addItem(lbl, val)
        # Restaurer la résolution sauvegardée
        saved_res = cfg.get("dl_max_resolution", "best")
        res_idx = self.res_combo.findData(saved_res)
        self.res_combo.setCurrentIndex(res_idx if res_idx >= 0 else 0)
        self.res_combo.setMinimumWidth(130)
        self.res_combo.currentIndexChanged.connect(
            lambda: cfg.set("dl_max_resolution", self.res_combo.currentData())
        )
        col_res.addWidget(self.res_combo)
        row1.addLayout(col_res); row1.addStretch(); pl.addLayout(row1)

        row2 = QVBoxLayout(); row2.setSpacing(8)
        row2.addWidget(make_section(t("playlist_items")))
        self.playlist_input = QLineEdit(); self.playlist_input.setPlaceholderText(t("playlist_placeholder"))
        row2.addWidget(self.playlist_input); pl.addLayout(row2)

        self.playlist_mode_cb = make_toggle(t("playlist_mode"), cfg.playlist_mode, self._on_playlist_mode_changed)
        pl.addWidget(self.playlist_mode_cb)

        # Options spécifiques aux playlists (sous-dossier)
        self._playlist_opts = QWidget()
        plo = QVBoxLayout(self._playlist_opts)
        plo.setContentsMargins(18, 0, 0, 0); plo.setSpacing(6)
        self._playlist_opts.setVisible(cfg.playlist_mode)
        pl.addWidget(self._playlist_opts)

        # "Continuer si indisponible" — toujours visible
        self.ignore_errors_cb = make_toggle(
            "Continuer si une vidéo est indisponible",
            cfg.get("ignore_errors", True),
            lambda v: cfg.set("ignore_errors", v),
        )
        pl.addWidget(self.ignore_errors_cb)
        err_hint = QLabel("Les erreurs seront listées à la fin du téléchargement.")
        err_hint.setObjectName("subtitle"); pl.addWidget(err_hint)

        # ── Métadonnées — toujours actives (pas conditionné à mutagen) ─────────
        self.embed_thumb_cb = make_toggle(
            t("embed_thumbnail"),
            cfg.get("embed_thumbnail", True),
            lambda v: cfg.set("embed_thumbnail", v),
        )
        pl.addWidget(self.embed_thumb_cb)

        self.auto_tag_cb = make_toggle(
            t("auto_tag"),
            cfg.auto_tag,
            lambda v: setattr(cfg, "auto_tag", v),
        )
        if not MUTAGEN_AVAILABLE:
            self.auto_tag_cb.setToolTip("mutagen non installé — pip install mutagen")
        pl.addWidget(self.auto_tag_cb)

        pl.addSpacing(4)

        row3 = QVBoxLayout(); row3.setSpacing(8)
        row3.addWidget(make_section(t("cookies_file")))
        cookie_row = QHBoxLayout()
        self.cookie_label = QLabel(t("no_file_selected")); self.cookie_label.setObjectName("status_info")
        cookie_btn = QPushButton(t("load_cookies")); cookie_btn.setObjectName("btn_secondary")
        cookie_btn.setFixedHeight(34); cookie_btn.clicked.connect(self._pick_cookie)
        cookie_row.addWidget(self.cookie_label, 1); cookie_row.addWidget(cookie_btn)
        row3.addLayout(cookie_row); pl.addLayout(row3)

        row4 = QVBoxLayout(); row4.setSpacing(8)
        row4.addWidget(make_section(t("browser_cookies_section")))
        browser_row = QHBoxLayout()
        self.browser_combo = QComboBox(); self.browser_combo.addItem("—","")
        for b in SUPPORTED_BROWSERS: self.browser_combo.addItem(b.capitalize(), b)
        self.browser_combo.setMinimumWidth(120)
        self.import_browser_btn = QPushButton(t("import_browser_btn"))
        self.import_browser_btn.setObjectName("btn_secondary"); self.import_browser_btn.setFixedHeight(34)
        self.import_browser_btn.setEnabled(BROWSER_COOKIE3_AVAILABLE)
        if not BROWSER_COOKIE3_AVAILABLE:
            self.import_browser_btn.setToolTip("browser-cookie3 non installé — pip install browser-cookie3")
        self.import_browser_btn.clicked.connect(self._import_browser_cookies)
        self.browser_status = QLabel(""); self.browser_status.setObjectName("status_info")
        browser_row.addWidget(self.browser_combo); browser_row.addWidget(self.import_browser_btn)
        browser_row.addWidget(self.browser_status, 1)
        row4.addLayout(browser_row); pl.addLayout(row4)

        outer.addWidget(self.panel)

    def _on_playlist_mode_changed(self, enabled: bool) -> None:
        cfg.playlist_mode = enabled
        self._playlist_opts.setVisible(enabled)

    def _toggle(self) -> None:
        visible = self.panel.isVisible()
        self.panel.setVisible(not visible)
        self.toggle_btn.setText(t("adv_options_open" if not visible else "adv_options_closed"))
        cfg.set("adv_panel_open", not visible)
        if not visible and cfg.animations_enabled:
            eff = QGraphicsOpacityEffect(self.panel)
            self.panel.setGraphicsEffect(eff)
            anim = QPropertyAnimation(eff, b"opacity", self)
            anim.setDuration(220)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.finished.connect(lambda: self.panel.setGraphicsEffect(None))
            self._toggle_anim = anim  # anti-GC
            anim.start()

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

    def get_options(self, output_format: str = "") -> AdvancedOptions:
        return AdvancedOptions(
            audio_bitrate   = self.bitrate_combo.currentData(),
            video_codec     = "h264",
            max_resolution  = self.res_combo.currentData(),
            playlist_items  = self.playlist_input.text().strip(),
            cookies_file    = self._cookies_path,
            browser_cookies = "",
            embed_thumbnail = self.embed_thumb_cb.isChecked(),
            ignore_errors   = self.ignore_errors_cb.isChecked(),
            output_format   = output_format,
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
        root = _make_scroll_tab(self)

        # ── En-tête ──────────────────────────────────────────────────────────
        hdr = QHBoxLayout(); hdr.setSpacing(12)
        ic = QLabel("⬇"); ic.setStyleSheet("font-size:26px; background:transparent;")
        hdr.addWidget(ic); hdr.addWidget(make_label(t("download_title"), "title")); hdr.addStretch()
        root.addLayout(hdr)

        # ── Carte principale ─────────────────────────────────────────────────
        card = QFrame(); card.setObjectName("card")
        cl = QVBoxLayout(card); cl.setSpacing(20); cl.setContentsMargins(28, 28, 28, 28)

        cl.addWidget(make_section(t("url_section")))
        url_row = QHBoxLayout(); url_row.setSpacing(10)
        self.url_input = QLineEdit(); self.url_input.setPlaceholderText(t("url_placeholder"))
        self.url_input.setObjectName("url_input")
        self.url_input.setMinimumHeight(48)
        paste_btn = QPushButton("📋"); paste_btn.setObjectName("btn_secondary")
        paste_btn.setFixedSize(44, 44)
        paste_btn.clicked.connect(lambda: self.url_input.setText(QApplication.clipboard().text().strip()))
        url_row.addWidget(self.url_input, 1); url_row.addWidget(paste_btn)
        cl.addLayout(url_row)

        cl.addSpacing(4)
        cl.addWidget(make_section(t("format_section")))

        fmt_row = QHBoxLayout(); fmt_row.setSpacing(8)

        # Mode Vidéo / Audio — 2 boutons radio
        self.rb_video = QRadioButton("🎬  Vidéo")
        self.rb_audio = QRadioButton("🎵  Audio")
        saved_mode = cfg.get("dl_mode", "video")
        self.rb_audio.setChecked(saved_mode == "audio")
        self.rb_video.setChecked(saved_mode != "audio")
        grp = QButtonGroup(self); grp.addButton(self.rb_video); grp.addButton(self.rb_audio)
        self.rb_video.toggled.connect(self._on_mode_changed)
        fmt_row.addWidget(self.rb_video); fmt_row.addWidget(self.rb_audio)
        fmt_row.addSpacing(16)

        # Format de sortie — combo détaillé
        self.dl_fmt_combo = QComboBox(); self.dl_fmt_combo.setMinimumWidth(180)
        self._update_format_combo(saved_mode)
        saved_fmt = cfg.get("dl_output_format", "")
        # Tenter de restaurer le format sauvegardé
        fi = self.dl_fmt_combo.findData(saved_fmt)
        if fi >= 0: self.dl_fmt_combo.setCurrentIndex(fi)
        self.dl_fmt_combo.currentIndexChanged.connect(
            lambda: cfg.set("dl_output_format", self.dl_fmt_combo.currentData())
        )
        fmt_row.addWidget(self.dl_fmt_combo)
        fmt_row.addStretch()
        cl.addLayout(fmt_row)

        cl.addSpacing(4)
        cl.addWidget(make_section(t("dest_folder")))
        folder_row = QHBoxLayout(); folder_row.setSpacing(10)
        self.folder_label = QLabel(str(self._output_dir)); self.folder_label.setObjectName("status_info")
        self.folder_label.setWordWrap(True)
        self.folder_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        folder_btn = QPushButton(t("change_folder")); folder_btn.setObjectName("btn_secondary")
        folder_btn.setFixedHeight(36); folder_btn.clicked.connect(self._choose_folder)
        folder_row.addWidget(self.folder_label, 1); folder_row.addWidget(folder_btn)
        cl.addLayout(folder_row)

        root.addWidget(card)

        # ── Options avancées ─────────────────────────────────────────────────
        self.advanced = DownloadAdvancedPanel()
        root.addWidget(self.advanced)

        # ── Barre de progression ─────────────────────────────────────────────
        self.progress = QProgressBar(); self.progress.setValue(0)
        self.progress.setTextVisible(False); self.progress.setFixedHeight(5)
        self.progress.setStyleSheet("")  # style via QSS global
        root.addWidget(self.progress)

        # ── Carte vitesse / ETA — design propre sans carrés ───────────────────
        self._prog_info_card = QFrame()
        self._prog_info_card.setObjectName("card_inner")
        self._prog_info_card.setFixedHeight(54)
        pil = QHBoxLayout(self._prog_info_card)
        pil.setContentsMargins(24, 0, 24, 0); pil.setSpacing(16)

        # % grand
        self._pct_lbl = QLabel("0%")
        self._pct_lbl.setStyleSheet(
            f"font-family:'Segoe UI Variable','Segoe UI',sans-serif;"
            f"font-size:22px; font-weight:800; color:{COLORS['accent_light']};"
            f"background:transparent; min-width:64px;"
        )

        # Séparateur vertical
        sep1 = QFrame(); sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setFixedHeight(24)
        sep1.setStyleSheet(f"color:{COLORS['border_soft']}; background:{COLORS['border_soft']}; border:none; max-width:1px;")

        # Vitesse
        speed_col = QVBoxLayout(); speed_col.setSpacing(1); speed_col.setContentsMargins(0,0,0,0)
        speed_lbl_title = QLabel("VITESSE")
        speed_lbl_title.setStyleSheet(f"font-size:9px; font-weight:700; color:{COLORS['text_muted']}; background:transparent; letter-spacing:0.8px; font-family:'Segoe UI Variable','Segoe UI',sans-serif;")
        self._speed_lbl = QLabel("—")
        self._speed_lbl.setStyleSheet(f"font-size:13px; font-weight:600; color:{COLORS['text_primary']}; background:transparent; font-family:'Segoe UI Variable','Segoe UI',sans-serif;")
        speed_col.addWidget(speed_lbl_title)
        speed_col.addWidget(self._speed_lbl)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setFixedHeight(24)
        sep2.setStyleSheet(f"color:{COLORS['border_soft']}; background:{COLORS['border_soft']}; border:none; max-width:1px;")

        # ETA
        eta_col = QVBoxLayout(); eta_col.setSpacing(1); eta_col.setContentsMargins(0,0,0,0)
        eta_lbl_title = QLabel("TEMPS RESTANT")
        eta_lbl_title.setStyleSheet(f"font-size:9px; font-weight:700; color:{COLORS['text_muted']}; background:transparent; letter-spacing:0.8px; font-family:'Segoe UI Variable','Segoe UI',sans-serif;")
        self._eta_lbl = QLabel("—")
        self._eta_lbl.setStyleSheet(f"font-size:13px; font-weight:600; color:{COLORS['text_primary']}; background:transparent; font-family:'Segoe UI Variable','Segoe UI',sans-serif;")
        eta_col.addWidget(eta_lbl_title)
        eta_col.addWidget(self._eta_lbl)

        pil.addWidget(self._pct_lbl)
        pil.addWidget(sep1)
        pil.addLayout(speed_col)
        pil.addWidget(sep2)
        pil.addLayout(eta_col)
        pil.addStretch()

        self._prog_info_card.hide()
        root.addWidget(self._prog_info_card)

        # ── Statut + bouton ouvrir ────────────────────────────────────────────
        status_row = QHBoxLayout(); status_row.setSpacing(10)
        self.status_lbl = QLabel(t("ready")); self.status_lbl.setObjectName("status_info")
        self.status_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.open_btn = QPushButton(t("open_folder")); self.open_btn.setObjectName("btn_secondary")
        self.open_btn.setFixedHeight(36); self.open_btn.hide()
        self.open_btn.clicked.connect(lambda: open_folder(self._last_file or self._output_dir))
        status_row.addWidget(self.status_lbl, 1); status_row.addWidget(self.open_btn)
        root.addLayout(status_row)

        # ── Boutons d'action ─────────────────────────────────────────────────
        btn_row = QHBoxLayout(); btn_row.setSpacing(10); btn_row.addStretch()
        self.cancel_btn = QPushButton(t("cancel")); self.cancel_btn.setObjectName("btn_secondary")
        self.cancel_btn.setEnabled(False); self.cancel_btn.setFixedHeight(44)
        self.cancel_btn.setMinimumWidth(110)
        self.cancel_btn.clicked.connect(self._cancel)
        self.dl_btn = QPushButton(t("download_btn"))
        self.dl_btn.setMinimumWidth(180); self.dl_btn.setFixedHeight(44)
        self.dl_btn.clicked.connect(self._start_download)
        btn_row.addWidget(self.cancel_btn); btn_row.addWidget(self.dl_btn)
        root.addLayout(btn_row)

        # ── File d'attente ───────────────────────────────────────────────────
        root.addSpacing(8)
        q_hdr = QHBoxLayout()
        q_hdr.addWidget(make_section(t("dl_queue_section"))); q_hdr.addStretch()
        self._toggle_q_btn = QPushButton("▾"); self._toggle_q_btn.setObjectName("btn_secondary")
        self._toggle_q_btn.setFixedSize(26, 26); self._toggle_q_btn.setCheckable(True)
        self._toggle_q_btn.setChecked(cfg.get("show_dl_queue", True))
        self._toggle_q_btn.setToolTip("Afficher / Masquer la file")
        clear_q = QPushButton(t("dl_queue_clear")); clear_q.setObjectName("btn_secondary")
        clear_q.setFixedHeight(28); clear_q.setStyleSheet("font-size:11px; padding:2px 12px;")
        clear_q.clicked.connect(self._clear_queue)
        q_hdr.addWidget(self._toggle_q_btn); q_hdr.addWidget(clear_q)
        root.addLayout(q_hdr)
        self.queue_list = QListWidget(); self.queue_list.setMaximumHeight(165)
        self.queue_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.queue_list.setVisible(cfg.get("show_dl_queue", True))
        root.addWidget(self.queue_list)
        self._toggle_q_btn.toggled.connect(lambda v: (
            self.queue_list.setVisible(v),
            self._toggle_q_btn.setText("▾" if v else "▸"),
            cfg.set("show_dl_queue", v)
        ))
        self._toggle_q_btn.setText("▾" if cfg.get("show_dl_queue", True) else "▸")

        # ── Historique ───────────────────────────────────────────────────────
        root.addSpacing(8)
        hist_hdr = QHBoxLayout()
        hist_hdr.addWidget(make_section(t("download_history"))); hist_hdr.addStretch()
        self._toggle_hist_btn = QPushButton("▾"); self._toggle_hist_btn.setObjectName("btn_secondary")
        self._toggle_hist_btn.setFixedSize(26, 26); self._toggle_hist_btn.setCheckable(True)
        self._toggle_hist_btn.setChecked(cfg.get("show_dl_history", True))
        self._toggle_hist_btn.setToolTip("Afficher / Masquer l'historique")
        clr_hist = QPushButton(t("clear_history")); clr_hist.setObjectName("btn_secondary")
        clr_hist.setFixedHeight(28); clr_hist.setStyleSheet("font-size:11px; padding:2px 12px;")
        clr_hist.clicked.connect(self._clear_history)
        hist_hdr.addWidget(self._toggle_hist_btn); hist_hdr.addWidget(clr_hist)
        root.addLayout(hist_hdr)
        self.history = QListWidget(); self.history.setMinimumHeight(90)
        self.history.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.history.itemDoubleClicked.connect(self._restore_url)
        self.history.setVisible(cfg.get("show_dl_history", True))
        root.addWidget(self.history, 1)
        self._toggle_hist_btn.toggled.connect(lambda v: (
            self.history.setVisible(v),
            self._toggle_hist_btn.setText("▾" if v else "▸"),
            cfg.set("show_dl_history", v)
        ))
        self._toggle_hist_btn.setText("▾" if cfg.get("show_dl_history", True) else "▸")

        root.addStretch()

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

    def _update_format_combo(self, mode: str) -> None:
        """Met à jour les options du combo format selon le mode vidéo/audio."""
        self.dl_fmt_combo.blockSignals(True)
        self.dl_fmt_combo.clear()
        if mode == "audio":
            for lbl, val in [
                ("🎵  MP3  (recommandé)", "mp3"),
                ("🎵  FLAC  (sans perte)", "flac"),
                ("🎵  AAC  (Apple / mobile)", "aac"),
                ("🎵  WAV  (non compressé)", "wav"),
                ("🎵  OPUS  (léger)", "opus"),
                ("🎵  M4A  (iTunes / iPhone)", "m4a"),
                ("🎵  OGG  (Vorbis)", "ogg"),
            ]:
                self.dl_fmt_combo.addItem(lbl, val)
        else:
            for lbl, val in [
                ("🎬  MP4  (recommandé)", "mp4"),
                ("🎬  WEBM  (VP9/AV1)", "webm"),
                ("🎬  MKV  (sans re-encodage)", "mkv"),
                ("🎬  AVI  (compatibilité)", "avi"),
                ("🎬  MOV  (Apple)", "mov"),
            ]:
                self.dl_fmt_combo.addItem(lbl, val)
        self.dl_fmt_combo.blockSignals(False)

    def _on_mode_changed(self, video_checked: bool) -> None:
        mode = "video" if video_checked else "audio"
        cfg.set("dl_mode", mode)
        self._update_format_combo(mode)
        # Restaurer le dernier format pour ce mode
        saved = cfg.get("dl_output_format", "")
        fi = self.dl_fmt_combo.findData(saved)
        if fi >= 0: self.dl_fmt_combo.setCurrentIndex(fi)

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Destination folder")
        if folder: self._output_dir = Path(folder); cfg.download_dir = folder; self.folder_label.setText(folder)

    def _set_busy(self, busy: bool) -> None:
        self.dl_btn.setEnabled(not busy); self.cancel_btn.setEnabled(busy)
        self.url_input.setEnabled(not busy); self.advanced.setEnabled(not busy)
        self._prog_info_card.setVisible(busy)
        if busy:
            self.progress.setRange(0, 100); self.progress.setValue(2)
            self._pct_lbl.setText("…"); self._speed_lbl.setText("—"); self._eta_lbl.setText("—")
        else:
            self.progress.setRange(0, 100); self.progress.setValue(0); _taskbar.clear()
            self._pct_lbl.setText("0%"); self._speed_lbl.setText("—"); self._eta_lbl.setText("—")

    def _cancel(self) -> None:
        if self._worker: self._worker.cancel()
        self._set_busy(False); set_status(self.status_lbl, t("download_cancelled"))

    def _start_download(self) -> None:
        url = self.url_input.text().strip()
        if not url: set_status(self.status_lbl, t("paste_url_first"), "err"); return
        mode = "audio" if self.rb_audio.isChecked() else "video"
        out_fmt = self.dl_fmt_combo.currentData() or ("mp3" if mode == "audio" else "mp4")
        cfg.set("dl_output_format", out_fmt)
        opts = self.advanced.get_options(output_format=out_fmt)
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
        self._worker.speed.connect(self._on_speed)
        self._worker.eta.connect(self._on_eta)
        self._worker.item_error.connect(self._on_item_error)
        self._worker.status.connect(lambda msg, _=None: self.status_lbl.setText(msg))
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, v: int) -> None:
        self._pct_lbl.setText(f"{v}%")
        if cfg.animations_enabled:
            anim = QPropertyAnimation(self.progress, b"value", self)
            anim.setDuration(180)
            anim.setStartValue(self.progress.value())
            anim.setEndValue(v)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._prog_anim = anim
            anim.start()
        else:
            self.progress.setValue(v)
        _taskbar.set_state(_WinTaskbar.TBPF_NORMAL); _taskbar.set_progress(v)

    def _on_speed(self, speed: str) -> None:
        self._dl_speed = speed
        self._speed_lbl.setText(speed)

    def _on_eta(self, eta: str) -> None:
        self._dl_eta = eta
        self._eta_lbl.setText(eta if eta else "—")

    def _on_item_error(self, title: str, error: str) -> None:
        """Un élément de playlist a été ignoré — on le marque dans la file."""
        short_title = title[:50] + "…" if len(title) > 50 else title
        short_err   = error[:60]  + "…" if len(error) > 60 else error
        # Ajouter l'entrée dans la file d'attente avec statut erreur
        item = QListWidgetItem(f"⚠  {short_title}  —  {short_err}")
        item.setForeground(QColor(COLORS.get("warning", "#F5A623")))
        self.queue_list.addItem(item)
        self.queue_list.scrollToBottom()

    def _on_finished(self, ok: bool, path: str) -> None:
        elapsed = time.monotonic() - getattr(self, "_start_time", time.monotonic())
        self._last_file = path; self._set_busy(False)
        self._dl_speed = ""; self._dl_eta = ""
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
        root = _make_scroll_tab(self)

        # ── En-tête ──────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        ic = QLabel("🔄"); ic.setStyleSheet("font-size:24px; background:transparent;")
        hdr.addWidget(ic); hdr.addWidget(make_label(t("convert_title"), "title")); hdr.addStretch()
        root.addLayout(hdr)

        # ── Zone de dépôt ────────────────────────────────────────────────────
        self.drop_zone = DropZone(self._on_files_dropped)
        root.addWidget(self.drop_zone, 1)

        browse_row = QHBoxLayout(); browse_row.addStretch()
        browse_btn = QPushButton(t("browse")); browse_btn.setObjectName("btn_secondary")
        browse_btn.setFixedHeight(34); browse_btn.clicked.connect(self._browse_files)
        browse_row.addWidget(browse_btn); browse_row.addStretch()
        root.addLayout(browse_row)

        # ── File d'attente ───────────────────────────────────────────────────
        q_hdr = QHBoxLayout()
        q_hdr.addWidget(make_section(t("queue_section"))); q_hdr.addStretch()
        self.batch_count_lbl = QLabel(""); self.batch_count_lbl.setObjectName("status_info")
        q_hdr.addWidget(self.batch_count_lbl)
        self._toggle_q_btn = QPushButton("▾"); self._toggle_q_btn.setObjectName("btn_secondary")
        self._toggle_q_btn.setFixedSize(26, 26); self._toggle_q_btn.setCheckable(True)
        self._toggle_q_btn.setChecked(cfg.get("show_conv_queue", True))
        self._toggle_q_btn.setToolTip("Afficher / Masquer la file")
        clr_q = QPushButton(t("clear_queue")); clr_q.setObjectName("btn_secondary")
        clr_q.setFixedHeight(26); clr_q.setStyleSheet("font-size:11px; padding:2px 10px;")
        clr_q.clicked.connect(self._clear_queue)
        q_hdr.addWidget(self._toggle_q_btn); q_hdr.addWidget(clr_q)
        root.addLayout(q_hdr)
        self.queue_list = QListWidget(); self.queue_list.setMinimumHeight(80); self.queue_list.setMaximumHeight(200)
        self.queue_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.queue_list.setVisible(cfg.get("show_conv_queue", True))
        root.addWidget(self.queue_list)
        self._toggle_q_btn.toggled.connect(lambda v: (
            self.queue_list.setVisible(v),
            self._toggle_q_btn.setText("▾" if v else "▸"),
            cfg.set("show_conv_queue", v)
        ))
        self._toggle_q_btn.setText("▾" if cfg.get("show_conv_queue", True) else "▸")

        # ── Carte options ────────────────────────────────────────────────────
        opts_card = QFrame(); opts_card.setObjectName("card")
        ocl = QHBoxLayout(opts_card); ocl.setSpacing(28); ocl.setContentsMargins(24, 20, 24, 20)

        preset_col = QVBoxLayout(); preset_col.setSpacing(8)
        preset_col.addWidget(make_section(t("preset_section")))
        self.preset_combo = QComboBox(); self._reload_presets_combo()
        self.preset_combo.setMinimumWidth(200)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        preset_col.addWidget(self.preset_combo)
        self.preset_desc = QLabel(list(PRESETS.values())[0]["desc"])
        self.preset_desc.setObjectName("subtitle")
        self.preset_desc.setWordWrap(True)
        preset_col.addWidget(self.preset_desc)
        ocl.addLayout(preset_col)

        fmt_col = QVBoxLayout(); fmt_col.setSpacing(8)
        fmt_col.addWidget(make_section(t("output_format")))
        self.fmt_combo = QComboBox(); self.fmt_combo.setMinimumWidth(140)
        for f in ["mp4","mp3","mkv","avi","webm","flac","wav","gif","jpg","png"]:
            self.fmt_combo.addItem(f".{f}", f)
        # Restaurer le format sauvegardé
        saved_fmt = cfg.get("conv_last_format", "mp4")
        fi = self.fmt_combo.findData(saved_fmt)
        if fi >= 0: self.fmt_combo.setCurrentIndex(fi)
        self.fmt_combo.currentIndexChanged.connect(
            lambda: cfg.set("conv_last_format", self.fmt_combo.currentData())
        )
        fmt_col.addWidget(self.fmt_combo)
        fmt_col.addSpacing(8)
        fmt_col.addWidget(make_section(t("output_folder")))
        outdir_row = QHBoxLayout(); outdir_row.setSpacing(6)
        self.out_dir_label = QLabel(str(self._output_dir)); self.out_dir_label.setObjectName("status_info")
        self.out_dir_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        outdir_btn = QPushButton("📁"); outdir_btn.setObjectName("btn_secondary"); outdir_btn.setFixedSize(34, 34)
        outdir_btn.clicked.connect(self._choose_out_folder)
        outdir_row.addWidget(self.out_dir_label, 1); outdir_row.addWidget(outdir_btn)
        fmt_col.addLayout(outdir_row)
        ocl.addLayout(fmt_col, 1)
        root.addWidget(opts_card)

        # ── Trim (carte intérieure) ───────────────────────────────────────────
        trim_card = QFrame(); trim_card.setObjectName("card_inner")
        tcl = QHBoxLayout(trim_card); tcl.setContentsMargins(20, 14, 20, 14); tcl.setSpacing(20)
        trim_lbl = QLabel(t("trim_section"))
        trim_lbl.setStyleSheet(f"color:{COLORS['text_secondary']}; font-size:12px; font-weight:600; background:transparent;")
        tcl.addWidget(trim_lbl); tcl.addSpacing(8)
        for attr, key_lbl, key_ph, w in [
            ("trim_start", "trim_start", "trim_start_ph", 110),
            ("trim_end",   "trim_end",   "trim_end_ph",   130),
        ]:
            col = QVBoxLayout(); col.setSpacing(4)
            col.addWidget(make_section(t(key_lbl)))
            inp = QLineEdit(); inp.setPlaceholderText(t(key_ph)); inp.setFixedWidth(w)
            setattr(self, attr, inp); col.addWidget(inp); tcl.addLayout(col)
        tcl.addStretch()
        root.addWidget(trim_card)

        # ── Progression ──────────────────────────────────────────────────────
        prog_row = QHBoxLayout()
        prog_row.addWidget(make_section(t("global_progress"))); prog_row.addStretch()
        self._conv_prog_lbl = QLabel("")
        self._conv_prog_lbl.setStyleSheet(f"font-size:11px; color:{COLORS['text_secondary']}; background:transparent;")
        prog_row.addWidget(self._conv_prog_lbl)
        root.addLayout(prog_row)
        self.progress = QProgressBar(); self.progress.setValue(0)
        self.progress.setTextVisible(False); self.progress.setFixedHeight(5)
        self.progress.setStyleSheet("")  # style via QSS global
        root.addWidget(self.progress)

        # ── Statut ───────────────────────────────────────────────────────────
        status_row = QHBoxLayout()
        self.status_lbl = QLabel(t("drop_or_browse")); self.status_lbl.setObjectName("status_info")
        self.status_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.open_btn = QPushButton(t("open_folder")); self.open_btn.setObjectName("btn_secondary")
        self.open_btn.setFixedHeight(34); self.open_btn.hide()
        self.open_btn.clicked.connect(lambda: open_folder(self._output_dir))
        status_row.addWidget(self.status_lbl, 1); status_row.addWidget(self.open_btn)
        root.addLayout(status_row)

        # ── Boutons d'action ─────────────────────────────────────────────────
        btn_row = QHBoxLayout(); btn_row.addStretch()
        self.cancel_btn = QPushButton(t("cancel")); self.cancel_btn.setObjectName("btn_secondary")
        self.cancel_btn.setEnabled(False); self.cancel_btn.setFixedHeight(42)
        self.cancel_btn.clicked.connect(self._cancel)
        self.convert_btn = QPushButton(t("convert_btn"))
        self.convert_btn.setMinimumWidth(170); self.convert_btn.setFixedHeight(42)
        self.convert_btn.setEnabled(False); self.convert_btn.clicked.connect(self._start_batch)
        btn_row.addWidget(self.cancel_btn); btn_row.addWidget(self.convert_btn)
        root.addLayout(btn_row)

        root.addStretch()

    def _reload_presets_combo(self) -> None:
        _refresh_presets(); self.preset_combo.blockSignals(True); self.preset_combo.clear()
        for key, p in PRESETS.items(): self.preset_combo.addItem(p["label"], key)
        # Restaurer le preset sauvegardé
        saved = cfg.get("conv_last_preset", "custom")
        idx = self.preset_combo.findData(saved)
        if idx >= 0: self.preset_combo.setCurrentIndex(idx)
        self.preset_combo.blockSignals(False)

    def refresh_presets(self) -> None: self._reload_presets_combo()

    def _on_preset_changed(self) -> None:
        key = self.preset_combo.currentData(); p = PRESETS.get(key, {})
        self.preset_desc.setText(p.get("desc",""))
        if p.get("fmt"):
            idx = self.fmt_combo.findData(p["fmt"])
            if idx >= 0: self.fmt_combo.setCurrentIndex(idx)
        cfg.set("conv_last_preset", key)

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
        if busy:
            self.progress.setRange(0, 100); self.progress.setValue(2)
            self._conv_prog_lbl.setText("")
        else:
            self.progress.setRange(0, 100); self.progress.setValue(0); _taskbar.clear()
            self._conv_prog_lbl.setText("")

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
        self._conv_prog_lbl.setText(f"{v}%")
        if cfg.animations_enabled:
            anim = QPropertyAnimation(self.progress, b"value", self)
            anim.setDuration(200)
            anim.setStartValue(self.progress.value())
            anim.setEndValue(v)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._conv_anim = anim
            anim.start()
        else:
            self.progress.setValue(v)
        _taskbar.set_state(_WinTaskbar.TBPF_NORMAL); _taskbar.set_progress(v)

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
#  Compressor tab
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
        root = _make_scroll_tab(self)

        # ── En-tête ──────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        ic = QLabel("📦"); ic.setStyleSheet("font-size:24px; background:transparent;")
        hdr.addWidget(ic)
        hdr.addWidget(make_label("Compresseur vidéo", "title")); hdr.addStretch()
        root.addLayout(hdr)

        # ── Bannière info ────────────────────────────────────────────────────
        info_card = QFrame(); info_card.setObjectName("card_inner")
        info_layout = QHBoxLayout(info_card); info_layout.setContentsMargins(18, 14, 18, 14)
        info_txt = QLabel(
            "ℹ  FFmpeg calcule automatiquement le bitrate vidéo pour respecter "
            "la limite de taille choisie."
        )
        info_txt.setObjectName("subtitle"); info_txt.setWordWrap(True)
        info_layout.addWidget(info_txt)
        root.addWidget(info_card)

        # ── Zone de dépôt ────────────────────────────────────────────────────
        self.drop_zone = DropZone(self._on_files_dropped)
        self.drop_zone.text_lbl.setText("Glissez vos vidéos ici")
        self.drop_zone.sub_lbl.setText("Formats supportés : MP4, MKV, AVI, MOV, WEBM…")
        root.addWidget(self.drop_zone, 1)

        browse_row = QHBoxLayout(); browse_row.addStretch()
        browse_btn = QPushButton("📂  Parcourir des vidéos…")
        browse_btn.setObjectName("btn_secondary"); browse_btn.setFixedHeight(34)
        browse_btn.clicked.connect(self._browse_files)
        browse_row.addWidget(browse_btn); browse_row.addStretch()
        root.addLayout(browse_row)

        # ── File d'attente ───────────────────────────────────────────────────
        q_hdr = QHBoxLayout()
        q_hdr.addWidget(make_section("File d'attente")); q_hdr.addStretch()
        self.batch_count_lbl = QLabel(""); self.batch_count_lbl.setObjectName("status_info")
        q_hdr.addWidget(self.batch_count_lbl)
        self._toggle_q_btn = QPushButton("▾"); self._toggle_q_btn.setObjectName("btn_secondary")
        self._toggle_q_btn.setFixedSize(26, 26); self._toggle_q_btn.setCheckable(True)
        self._toggle_q_btn.setChecked(cfg.get("show_comp_queue", True))
        self._toggle_q_btn.setToolTip("Afficher / Masquer la file")
        clr_q = QPushButton("🗑  Vider"); clr_q.setObjectName("btn_secondary")
        clr_q.setFixedHeight(26); clr_q.setStyleSheet("font-size:11px; padding:2px 10px;")
        clr_q.clicked.connect(self._clear_queue)
        q_hdr.addWidget(self._toggle_q_btn); q_hdr.addWidget(clr_q)
        root.addLayout(q_hdr)
        self.queue_list = QListWidget(); self.queue_list.setMaximumHeight(140)
        self.queue_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.queue_list.setVisible(cfg.get("show_comp_queue", True))
        root.addWidget(self.queue_list)
        self._toggle_q_btn.toggled.connect(lambda v: (
            self.queue_list.setVisible(v),
            self._toggle_q_btn.setText("▾" if v else "▸"),
            cfg.set("show_comp_queue", v)
        ))
        self._toggle_q_btn.setText("▾" if cfg.get("show_comp_queue", True) else "▸")

        # ── Carte cible de compression ────────────────────────────────────────
        target_card = QFrame(); target_card.setObjectName("card")
        tcl = QVBoxLayout(target_card); tcl.setSpacing(20); tcl.setContentsMargins(24, 22, 24, 22)
        tcl.addWidget(make_section("🎯  Cible de compression"))

        # Presets plateforme
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

        # Taille personnalisée
        self.custom_row = QWidget()
        cr = QHBoxLayout(self.custom_row); cr.setContentsMargins(0,0,0,0); cr.setSpacing(10)
        cr.addWidget(make_section("Taille max (MB)"))
        self.custom_size_spin = QSpinBox(); self.custom_size_spin.setRange(1, 2000)
        self.custom_size_spin.setValue(50); self.custom_size_spin.setFixedWidth(80)
        self.custom_size_spin.setSuffix(" MB"); cr.addWidget(self.custom_size_spin)
        cr.addStretch(); self.custom_row.hide(); tcl.addWidget(self.custom_row)

        # Aperçu comparatif
        tcl.addSpacing(4)
        compare_section = QLabel("APERÇU DU GAIN ESTIMÉ")
        compare_section.setStyleSheet(section_label_style()); tcl.addWidget(compare_section)

        compare_container = QWidget()
        compare_layout = QVBoxLayout(compare_container)
        compare_layout.setContentsMargins(0,0,0,0); compare_layout.setSpacing(8)

        orig_row = QHBoxLayout()
        orig_lbl = QLabel("Taille actuelle"); orig_lbl.setObjectName("status_info"); orig_lbl.setFixedWidth(110)
        self._orig_bar_bg = QFrame(); self._orig_bar_bg.setObjectName("compare_bar_bg")
        self._orig_bar_bg.setFixedHeight(12)
        self._orig_bar_fill = QFrame(self._orig_bar_bg); self._orig_bar_fill.setObjectName("compare_bar_fill")
        self._orig_bar_fill.setFixedHeight(12)
        self._orig_size_lbl = QLabel("—"); self._orig_size_lbl.setObjectName("status_info"); self._orig_size_lbl.setFixedWidth(60)
        orig_row.addWidget(orig_lbl); orig_row.addWidget(self._orig_bar_bg, 1); orig_row.addWidget(self._orig_size_lbl)
        compare_layout.addLayout(orig_row)

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

        badge_row = QHBoxLayout(); badge_row.addStretch()
        self._quality_badge = QLabel("—")
        self._quality_badge.setStyleSheet(compression_badge_style("optimal"))
        badge_row.addWidget(self._quality_badge)
        compare_layout.addLayout(badge_row)
        tcl.addWidget(compare_container)

        # Qualité audio + dossier de sortie
        aq_row = QHBoxLayout(); aq_row.setSpacing(20)
        aq_col = QVBoxLayout(); aq_col.setSpacing(8)
        aq_col.addWidget(make_section("Qualité audio"))
        self.audio_br_combo = QComboBox()
        for lbl, val in [("128 kbps (standard)", 128), ("192 kbps (haute)", 192), ("96 kbps (léger)", 96)]:
            self.audio_br_combo.addItem(lbl, val)
        # Restaurer la qualité audio sauvegardée
        saved_kbps = cfg.get("comp_audio_kbps", 128)
        kbps_idx = self.audio_br_combo.findData(saved_kbps)
        if kbps_idx >= 0: self.audio_br_combo.setCurrentIndex(kbps_idx)
        self.audio_br_combo.setMinimumWidth(180); aq_col.addWidget(self.audio_br_combo)
        self.audio_br_combo.currentIndexChanged.connect(lambda: (
            cfg.set("comp_audio_kbps", self.audio_br_combo.currentData()),
            self._refresh_compare()
        ))
        aq_row.addLayout(aq_col)

        of_col = QVBoxLayout(); of_col.setSpacing(8)
        of_col.addWidget(make_section("Dossier de sortie"))
        of_row = QHBoxLayout(); of_row.setSpacing(6)
        self.out_dir_label = QLabel(str(self._output_dir)); self.out_dir_label.setObjectName("status_info")
        self.out_dir_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        outdir_btn = QPushButton("📁"); outdir_btn.setObjectName("btn_secondary"); outdir_btn.setFixedSize(34, 34)
        outdir_btn.clicked.connect(self._choose_out_folder)
        of_row.addWidget(self.out_dir_label, 1); of_row.addWidget(outdir_btn)
        of_col.addLayout(of_row); aq_row.addLayout(of_col, 1)
        tcl.addLayout(aq_row)

        root.addWidget(target_card)

        # ── Description plateforme ────────────────────────────────────────────
        self.platform_desc = QLabel("Choisissez une plateforme cible ci-dessus.")
        self.platform_desc.setObjectName("subtitle"); self.platform_desc.setWordWrap(True)
        root.addWidget(self.platform_desc)

        # ── Progression ──────────────────────────────────────────────────────
        prog_hdr = QHBoxLayout()
        prog_hdr.addWidget(make_section("PROGRESSION"))
        prog_hdr.addStretch()
        self._comp_prog_lbl = QLabel("")
        self._comp_prog_lbl.setStyleSheet(
            f"font-size:11px; color:{COLORS['text_secondary']}; background:transparent;"
        )
        prog_hdr.addWidget(self._comp_prog_lbl)
        root.addLayout(prog_hdr)

        self.progress = QProgressBar(); self.progress.setValue(0)
        self.progress.setObjectName("compress_progress")
        self.progress.setTextVisible(False); self.progress.setFixedHeight(5)
        self.progress.setStyleSheet("")  # style via QSS global
        root.addWidget(self.progress)

        # ── Statut ───────────────────────────────────────────────────────────
        status_row = QHBoxLayout()
        self.status_lbl = QLabel("Ajoutez des vidéos pour commencer.")
        self.status_lbl.setObjectName("status_info")
        self.status_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.open_btn = QPushButton(t("open_folder")); self.open_btn.setObjectName("btn_secondary")
        self.open_btn.setFixedHeight(34); self.open_btn.hide()
        self.open_btn.clicked.connect(lambda: open_folder(self._output_dir))
        status_row.addWidget(self.status_lbl, 1); status_row.addWidget(self.open_btn)
        root.addLayout(status_row)

        # ── Boutons d'action ─────────────────────────────────────────────────
        btn_row = QHBoxLayout(); btn_row.addStretch()
        self.cancel_btn = QPushButton(t("cancel")); self.cancel_btn.setObjectName("btn_secondary")
        self.cancel_btn.setEnabled(False); self.cancel_btn.setFixedHeight(42)
        self.cancel_btn.clicked.connect(self._cancel)
        self.compress_btn = QPushButton("📦  Compresser tout")
        self.compress_btn.setMinimumWidth(180); self.compress_btn.setFixedHeight(42)
        self.compress_btn.setEnabled(False); self.compress_btn.clicked.connect(self._start_compression)
        btn_row.addWidget(self.cancel_btn); btn_row.addWidget(self.compress_btn)
        root.addLayout(btn_row)

        # Restaurer la plateforme sauvegardée
        saved_platform = cfg.get("comp_last_platform", "discord")
        if saved_platform not in self._platform_btns:
            saved_platform = "discord"
        self._platform_btns[saved_platform].setChecked(True)
        self._selected_platform = saved_platform
        self._update_platform_desc(saved_platform)
        self.custom_row.setVisible(saved_platform == "custom")

        root.addStretch()

    # ── Barre comparative ─────────────────────────────────────────────────────

    def _refresh_compare(self) -> None:
        if not self._queued_files:
            self._orig_size_lbl.setText("—")
            self._target_size_lbl.setText("—")
            self._orig_bar_fill.setFixedWidth(0)
            self._target_bar_fill.setFixedWidth(0)
            self._quality_badge.setText("—")
            return

        target_bytes = self._get_target_bytes()
        target_mb = target_bytes / (1024 * 1024)
        total_orig_bytes = sum(f.stat().st_size for f in self._queued_files if f.exists())
        orig_mb = total_orig_bytes / (1024 * 1024)

        self._orig_size_lbl.setText(f"{orig_mb:.1f} MB" if orig_mb < 1024 else f"{orig_mb/1024:.2f} GB")
        est_target_mb = min(target_mb * len(self._queued_files), orig_mb)
        self._target_size_lbl.setText(f"{est_target_mb:.1f} MB")

        bar_width = self._orig_bar_bg.width() or 200
        if orig_mb > 0:
            self._orig_bar_fill.setFixedWidth(bar_width)
            ratio = min(est_target_mb / orig_mb, 1.0)
            self._target_bar_fill.setFixedWidth(int(bar_width * ratio))

        if self._queued_files:
            f = self._queued_files[0]
            abr = self.audio_br_combo.currentData() or 128
            vbr = compute_target_bitrate(f, target_bytes, abr)
            if vbr is None:
                # ffprobe ne peut pas lire la durée — compression CRF quand même possible
                kind, text = "warn", "⚠  Taille estimée — mode CRF"
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
        cfg.set("comp_last_platform", key)
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
            if classify_file(p) != "video" or p in self._queued_files:
                continue
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
        if busy:
            self.progress.setRange(0, 100); self.progress.setValue(2)
            self._comp_prog_lbl.setText("")
        else:
            self.progress.setRange(0, 100); self.progress.setValue(0); _taskbar.clear()
            self._comp_prog_lbl.setText("")

    def _cancel(self) -> None:
        if self._batch_worker: self._batch_worker.cancel()
        self._set_busy(False); set_status(self.status_lbl, "Compression annulée.")

    def _start_compression(self) -> None:
        if not self._queued_files: return
        if not ffmpeg_available():
            QMessageBox.critical(self, "FFmpeg", t("ffmpeg_missing_msg")); return

        self._set_busy(True); self.open_btn.hide()
        self.batch_count_lbl.setText(f"0 / {len(self._queued_files)}")
        self._start_time = time.monotonic()
        _taskbar.set_state(_WinTaskbar.TBPF_NORMAL)
        set_status(self.status_lbl, "Démarrage de la compression…")

        if self._selected_platform == "custom":
            self._run_custom_compression()
            return

        # Plateforme prédéfinie (discord / whatsapp / email / telegram)
        self._batch_worker = BatchConvertWorker(
            self._queued_files, "mp4", self._output_dir,
            "custom", cfg.max_workers, "", "",
            compress_target=self._selected_platform,
            parent=self,
        )
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
                from converter import compute_target_bitrate, _convert_sync, PRESETS as _P
                _success = 0; _errors = 0
                for i, f in enumerate(self_.files):
                    if self_._cancelled: break
                    self_.status.emit(f"⚙  [{i+1}/{len(self_.files)}]  {f.name}")
                    vbr = compute_target_bitrate(f, self_.tb, self_.abr)
                    if vbr is not None:
                        cargs = [
                            "-c:v", "libx264", "-b:v", f"{vbr}k",
                            "-maxrate", f"{vbr}k", "-bufsize", f"{vbr*2}k",
                            "-c:a", "aac", "-b:a", f"{self_.abr}k",
                            "-movflags", "+faststart",
                        ]
                    else:
                        # Fallback CRF quand la durée est illisible
                        target_mb = self_.tb / (1024 * 1024)
                        if target_mb <= 10:   crf = 34
                        elif target_mb <= 16: crf = 32
                        elif target_mb <= 25: crf = 28
                        elif target_mb <= 50: crf = 24
                        else:                 crf = 20
                        cargs = [
                            "-c:v", "libx264", "-crf", str(crf), "-preset", "fast",
                            "-c:a", "aac", "-b:a", f"{self_.abr}k",
                            "-movflags", "+faststart",
                        ]
                    _P["__custom_compress__"] = {
                        "label": "custom", "fmt": "mp4", "args": cargs, "desc": "",
                    }
                    def _prog(v, idx=i): self_.file_progress.emit(idx, v)
                    ok, val = _convert_sync(f, "mp4", self_.out_dir,
                                            "__custom_compress__", progress_cb=_prog)
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
        self._comp_prog_lbl.setText(f"{v}%")
        if cfg.animations_enabled:
            anim = QPropertyAnimation(self.progress, b"value", self)
            anim.setDuration(200)
            anim.setStartValue(self.progress.value())
            anim.setEndValue(v)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._comp_anim = anim
            anim.start()
        else:
            self.progress.setValue(v)
        _taskbar.set_state(_WinTaskbar.TBPF_NORMAL); _taskbar.set_progress(v)

    def _on_file_progress(self, idx: int, v: int) -> None:
        if 0 <= idx < len(self._file_widgets): self._file_widgets[idx].set_progress(v)

    def _on_file_done(self, idx: int, src: str, out: str) -> None:
        if 0 <= idx < len(self._file_widgets): self._file_widgets[idx].set_done(Path(out).name)
        self.batch_count_lbl.setText(f"{idx+1} / {len(self._queued_files)}")
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
#  Settings tab
# ══════════════════════════════════════════════════════════════════════════════

class SettingsTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._update_worker: YtdlpUpdateWorker | None = None
        self._ffmpeg_timer: QTimer | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:  # noqa: C901
        root = _make_scroll_tab(self)

        # ── En-tête ──────────────────────────────────────────────────────────
        hdr = QHBoxLayout(); hdr.setSpacing(14)
        ic_lbl = QLabel()
        ic_lbl.setPixmap(svg_icon("settings", color=COLORS.get("accent","#3B7DF8"), size=26).pixmap(QSize(26,26)))
        ic_lbl.setStyleSheet("background:transparent;")
        hdr.addWidget(ic_lbl)
        hdr.addWidget(make_label(t("settings_title"), "title"))
        hdr.addStretch()
        root.addLayout(hdr)
        root.addSpacing(8)

        # ══════════════════════════════════════════════════════════════════════
        # CARTE 1 : Apparence & Interface
        # ══════════════════════════════════════════════════════════════════════
        app_card, _, app_content = make_card("🎨", t("appearance_card_title"))

        # ── Thème ─────────────────────────────────────────────────────────
        app_content.addWidget(make_section("THÈME VISUEL"))
        self._theme_btns: dict[str, QPushButton] = {}
        current_theme = ThemeManager.current()

        # Ligne 1 : Sombre / OLED / Clair
        theme_row1 = QHBoxLayout(); theme_row1.setSpacing(8)
        for key, obj_name, label in [
            ("dark",  "theme_preview_dark",  t("theme_dark")),
            ("oled",  "theme_preview_oled",  t("theme_oled")),
            ("light", "theme_preview_light", t("theme_light")),
        ]:
            btn = QPushButton(label); btn.setObjectName(obj_name)
            btn.setCheckable(True); btn.setChecked(key == current_theme)
            btn.setMinimumWidth(110); btn.setFixedHeight(48)
            btn.clicked.connect(lambda _, k=key: self._apply_theme(k))
            self._theme_btns[key] = btn; theme_row1.addWidget(btn)
        theme_row1.addStretch()
        app_content.addLayout(theme_row1)

        # Ligne 2 : Suivre le système / Couleur du PC
        theme_row2 = QHBoxLayout(); theme_row2.setSpacing(8)
        for key, obj_name, label in [
            ("auto",   "theme_preview_auto",   t("theme_auto")),
            ("system", "theme_preview_system", t("theme_system")),
        ]:
            btn = QPushButton(label); btn.setObjectName(obj_name)
            btn.setCheckable(True); btn.setChecked(key == current_theme)
            btn.setMinimumWidth(160); btn.setFixedHeight(48)
            btn.clicked.connect(lambda _, k=key: self._apply_theme(k))
            self._theme_btns[key] = btn; theme_row2.addWidget(btn)
        theme_row2.addStretch()
        app_content.addLayout(theme_row2)

        theme_desc = QLabel(t("theme_desc")); theme_desc.setObjectName("subtitle")
        app_content.addWidget(theme_desc)

        app_content.addSpacing(16)

        # ── Langue ────────────────────────────────────────────────────────
        app_content.addWidget(make_section("LANGUE"))
        lang_row = QHBoxLayout(); lang_row.setSpacing(8)
        self._lang_btns: dict[str, QPushButton] = {}
        cur_lang = current_language()
        for label, key in [(t("lang_en"), "en"), (t("lang_fr"), "fr")]:
            btn = QPushButton(label); btn.setObjectName("theme_btn"); btn.setCheckable(True)
            btn.setChecked(key == cur_lang); btn.setFixedHeight(36)
            btn.clicked.connect(lambda _, k=key: self._apply_language(k))
            self._lang_btns[key] = btn; lang_row.addWidget(btn)
        lang_row.addStretch(); app_content.addLayout(lang_row)
        restart_lbl = QLabel("Le changement de langue s'applique après redémarrage de l'application.")
        restart_lbl.setObjectName("subtitle"); restart_lbl.setWordWrap(True)
        app_content.addWidget(restart_lbl)

        app_content.addSpacing(16)

        # ── Animations ────────────────────────────────────────────────────
        app_content.addWidget(make_section("INTERFACE"))
        self._anim_toggle = make_toggle(
            "Activer les transitions et animations",
            cfg.animations_enabled,
            self._on_anim_toggled,
        )
        app_content.addWidget(self._anim_toggle)
        anim_hint = QLabel("Désactivez si l'application est lente sur votre PC.")
        anim_hint.setObjectName("subtitle"); app_content.addWidget(anim_hint)

        self._statsbar_toggle = make_toggle(
            "Afficher la barre de statistiques en bas de l'écran",
            cfg.get("show_stats_bar", True),
            lambda v: (cfg.set("show_stats_bar", v), self._apply_statsbar(v)),
        )
        app_content.addWidget(self._statsbar_toggle)

        root.addWidget(app_card)

        # ══════════════════════════════════════════════════════════════════════
        # CARTE 2 : Comportement à la fermeture
        # ══════════════════════════════════════════════════════════════════════
        tray_card, _, tray_content = make_card("🗔", "Comportement à la fermeture")

        self._tray_close_cb = make_toggle(
            t("tray_on_close"), cfg.minimize_to_tray, self._on_tray_close_toggled
        )
        tray_content.addWidget(self._tray_close_cb)

        close_hint = QLabel("Par défaut, fermer la fenêtre quitte complètement l'application.")
        close_hint.setObjectName("subtitle"); close_hint.setWordWrap(True)
        tray_content.addWidget(close_hint)

        # Widgets cachés nécessaires pour compatibilité avec les handlers existants
        self._tray_sub_widget = QWidget()
        tray_sub = QVBoxLayout(self._tray_sub_widget)
        tray_sub.setContentsMargins(0, 0, 0, 0); tray_sub.setSpacing(0)
        self._tray_start_cb = make_toggle(
            t("start_in_tray"), cfg.start_in_tray, lambda v: setattr(cfg, "start_in_tray", v)
        )
        self.notif_tray_cb = make_toggle(
            t("notif_tray_bg"), cfg.notif_tray_bg, lambda v: setattr(cfg, "notif_tray_bg", v)
        )
        tray_sub.addWidget(self._tray_start_cb)
        tray_sub.addWidget(self.notif_tray_cb)
        tray_content.addWidget(self._tray_sub_widget)
        self._tray_sub_widget.setVisible(False)

        self._dis_tray_btn = QPushButton(t("disable_tray_btn"))
        self._dis_tray_btn.setVisible(False)
        self._dis_tray_btn.clicked.connect(self._maint_disable_tray)
        self._tray_status = QLabel(""); self._tray_status.setObjectName("status_info")
        tray_content.addWidget(self._tray_status)

        root.addWidget(tray_card)

        # ══════════════════════════════════════════════════════════════════════
        # CARTE 3 : Moteur de téléchargement (yt-dlp)
        # ══════════════════════════════════════════════════════════════════════
        dl_eng_card, _, dl_eng_content = make_card("⬇", t("download_engine_card"))

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

        dl_eng_content.addSpacing(12)
        self._playlist_mode_cb = make_toggle(
            t("playlist_mode"), cfg.playlist_mode, lambda v: setattr(cfg, "playlist_mode", v)
        )
        self._auto_tag_cb = make_toggle(
            t("auto_tag"), cfg.auto_tag, lambda v: setattr(cfg, "auto_tag", v)
        )
        dl_eng_content.addWidget(self._playlist_mode_cb)
        dl_eng_content.addWidget(self._auto_tag_cb)

        dl_eng_content.addSpacing(12)
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

        dl_eng_content.addSpacing(12)
        dl_eng_content.addWidget(make_section("MISE À JOUR DU MOTEUR"))
        ytdlp_row = QHBoxLayout(); ytdlp_row.setSpacing(12)
        try:
            import yt_dlp as _ydl; ver = getattr(_ydl.version, "__version__", "?")
            ytdlp_row.addWidget(QLabel(t("ytdlp_version", ver=ver)))
        except Exception:
            ytdlp_row.addWidget(QLabel(t("ytdlp_not_installed")))
        ytdlp_row.addStretch()
        self.update_btn = QPushButton(t("ytdlp_update_btn")); self.update_btn.setFixedHeight(36)
        self.update_btn.clicked.connect(self._run_ytdlp_update); ytdlp_row.addWidget(self.update_btn)
        dl_eng_content.addLayout(ytdlp_row)
        self.update_status = QLabel(""); self.update_status.setObjectName("status_info")
        self.update_status.setWordWrap(True); dl_eng_content.addWidget(self.update_status)

        root.addWidget(dl_eng_card)

        # ══════════════════════════════════════════════════════════════════════
        # CARTE 4 : Conversion & Compression (FFmpeg)
        # ══════════════════════════════════════════════════════════════════════
        ffmpeg_card, ffmpeg_hdr, ffmpeg_content = make_card("🎞", t("conversion_card_title"))

        self._ffmpeg_dot = QLabel(); self._ffmpeg_dot.setFixedSize(12, 12)
        ffmpeg_hdr.insertWidget(2, self._ffmpeg_dot)
        self._update_ffmpeg_dot()

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

        ffmpeg_content.addSpacing(8)
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

        ffmpeg_content.addSpacing(12)
        cpu_row = QHBoxLayout(); cpu_row.setSpacing(24)

        threads_col = QVBoxLayout(); threads_col.setSpacing(8)
        threads_col.addWidget(make_section(t("ffmpeg_threads_label")))
        self._threads_spin = QSpinBox(); self._threads_spin.setRange(0, 32)
        self._threads_spin.setValue(cfg.ffmpeg_threads); self._threads_spin.setFixedWidth(80)
        self._threads_spin.setSpecialValueText("Auto")
        self._threads_spin.valueChanged.connect(lambda v: setattr(cfg, "ffmpeg_threads", v))
        threads_col.addWidget(self._threads_spin)
        cpu_row.addLayout(threads_col)

        priority_col = QVBoxLayout(); priority_col.setSpacing(8)
        priority_col.addWidget(make_section(t("ffmpeg_priority_label")))
        self._priority_combo = QComboBox(); self._priority_combo.setMinimumWidth(200)
        for key, lbl in [("low", t("priority_low")), ("normal", t("priority_normal")), ("high", t("priority_high"))]:
            self._priority_combo.addItem(lbl, key)
        pidx = self._priority_combo.findData(cfg.ffmpeg_priority)
        if pidx >= 0: self._priority_combo.setCurrentIndex(pidx)
        self._priority_combo.currentIndexChanged.connect(
            lambda: setattr(cfg, "ffmpeg_priority", self._priority_combo.currentData())
        )
        priority_col.addWidget(self._priority_combo)
        cpu_row.addLayout(priority_col)
        cpu_row.addStretch()
        ffmpeg_content.addLayout(cpu_row)

        ffmpeg_content.addSpacing(12)
        par_row = QHBoxLayout(); par_row.setSpacing(12)
        par_lbl = QLabel(t("parallel_label")); par_lbl.setObjectName("status_info")
        par_row.addWidget(par_lbl); par_row.addStretch()
        self.workers_spin = QSpinBox(); self.workers_spin.setRange(1, 4)
        self.workers_spin.setValue(cfg.max_workers); self.workers_spin.setFixedWidth(70)
        self.workers_spin.valueChanged.connect(lambda v: setattr(cfg, "max_workers", v))
        par_row.addWidget(self.workers_spin); ffmpeg_content.addLayout(par_row)
        pd = QLabel(t("parallel_desc")); pd.setObjectName("subtitle"); pd.setWordWrap(True)
        ffmpeg_content.addWidget(pd)

        ffmpeg_content.addSpacing(8)
        self._del_source_cb = make_toggle(
            t("delete_source_toggle"), cfg.delete_source,
            lambda v: setattr(cfg, "delete_source", v)
        )
        ffmpeg_content.addWidget(self._del_source_cb)

        root.addWidget(ffmpeg_card)

        # ══════════════════════════════════════════════════════════════════════
        # CARTE 5 : Destinations & Organisation
        # ══════════════════════════════════════════════════════════════════════
        dest_card, _, dest_content = make_card("📁", t("destinations_card_title"))

        dest_content.addWidget(make_section(t("output_dir_label")))
        dest_dir_row = QHBoxLayout(); dest_dir_row.setSpacing(8)
        self._dest_dir_lbl = QLabel(str(cfg.download_dir))
        self._dest_dir_lbl.setObjectName("status_info"); self._dest_dir_lbl.setWordWrap(True)
        self._dest_dir_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        dest_browse_btn = QPushButton("📁 Choisir"); dest_browse_btn.setObjectName("btn_secondary")
        dest_browse_btn.setFixedHeight(34); dest_browse_btn.clicked.connect(self._choose_output_dir)
        dest_dir_row.addWidget(self._dest_dir_lbl, 1); dest_dir_row.addWidget(dest_browse_btn)
        dest_content.addLayout(dest_dir_row)

        dest_content.addSpacing(8)
        self._auto_sub_cb = make_toggle(
            t("auto_subfolders_toggle"), cfg.auto_subfolders,
            lambda v: setattr(cfg, "auto_subfolders", v)
        )
        dest_content.addWidget(self._auto_sub_cb)

        dest_content.addSpacing(8)
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

        root.addWidget(dest_card)

        # ══════════════════════════════════════════════════════════════════════
        # CARTE 6 : Notifications & Sons
        # ══════════════════════════════════════════════════════════════════════
        notif_card, _, notif_content = make_card("🔔", t("notif_card_title"))

        self.notif_master = make_toggle(
            "Activer les notifications système", cfg.notifications, self._on_notif_master_toggled
        )
        notif_content.addWidget(self.notif_master)

        self._notif_options_widget = QWidget()
        nopt = QVBoxLayout(self._notif_options_widget)
        nopt.setContentsMargins(16, 4, 0, 0); nopt.setSpacing(8)

        self.notif_dl_cb    = make_toggle("📥  Fin de téléchargement",          cfg.notif_on_download, lambda v: setattr(cfg, "notif_on_download", v))
        self.notif_conv_cb  = make_toggle("🔄  Fin de conversion / compression", cfg.notif_on_convert,  lambda v: setattr(cfg, "notif_on_convert", v))
        self.notif_err_cb   = make_toggle("❌  En cas d'erreur",                 cfg.notif_on_error,    lambda v: setattr(cfg, "notif_on_error", v))
        self.notif_sound_cb = make_toggle("🔊  Son de notification (Windows / macOS)", cfg.notif_sound,  lambda v: setattr(cfg, "notif_sound", v))

        for w in [self.notif_dl_cb, self.notif_conv_cb, self.notif_err_cb, self.notif_sound_cb]:
            nopt.addWidget(w)

        notif_content.addWidget(self._notif_options_widget)
        self._notif_options_widget.setEnabled(cfg.notifications)

        root.addWidget(notif_card)

        # ══════════════════════════════════════════════════════════════════════
        # CARTE 7 : Presets personnalisés
        # ══════════════════════════════════════════════════════════════════════
        preset_card, _, preset_content = make_card("⭐", "Presets personnalisés")

        self.preset_name_inp = QLineEdit()
        self.preset_name_inp.setPlaceholderText(t("preset_name_ph"))
        preset_content.addWidget(self.preset_name_inp)

        pr_row = QHBoxLayout(); pr_row.setSpacing(12)
        fmt_col = QVBoxLayout(); fmt_col.setSpacing(8)
        fmt_col.addWidget(make_section(t("preset_fmt_label")))
        self.preset_fmt_combo = QComboBox()
        for f in ["mp4", "mp3", "mkv", "flac", "wav", "gif", "jpg", "png"]:
            self.preset_fmt_combo.addItem(f, f)
        fmt_col.addWidget(self.preset_fmt_combo); pr_row.addLayout(fmt_col)
        args_col = QVBoxLayout(); args_col.setSpacing(8)
        args_col.addWidget(make_section(t("preset_args_label")))
        self.preset_args_inp = QLineEdit()
        self.preset_args_inp.setPlaceholderText(t("preset_args_ph"))
        args_col.addWidget(self.preset_args_inp); pr_row.addLayout(args_col, 1)
        preset_content.addLayout(pr_row)

        pr_btn_row = QHBoxLayout()
        save_btn = QPushButton(t("save_preset")); save_btn.setFixedHeight(34)
        save_btn.clicked.connect(self._save_preset)
        del_btn = QPushButton(t("delete_preset")); del_btn.setObjectName("btn_danger")
        del_btn.setFixedHeight(34); del_btn.clicked.connect(self._delete_preset)
        pr_btn_row.addWidget(save_btn); pr_btn_row.addWidget(del_btn); pr_btn_row.addStretch()
        preset_content.addLayout(pr_btn_row)

        self.preset_status = QLabel(""); self.preset_status.setObjectName("status_info")
        preset_content.addWidget(self.preset_status)
        self.preset_list = QListWidget(); self.preset_list.setMaximumHeight(80)
        self.preset_list.itemClicked.connect(self._select_preset)
        preset_content.addWidget(self.preset_list)
        self._refresh_preset_list()
        root.addWidget(preset_card)

        # ══════════════════════════════════════════════════════════════════════
        # CARTE 8 : Maintenance & Aide
        # ══════════════════════════════════════════════════════════════════════
        maint_card, _, maint_content = make_card("🔧", t("maintenance_card_title"))

        util_row = QHBoxLayout(); util_row.setSpacing(10)
        clr_hist_btn = QPushButton(t("clear_dl_history_btn"))
        clr_hist_btn.setObjectName("btn_secondary"); clr_hist_btn.setFixedHeight(36)
        clr_hist_btn.clicked.connect(self._maint_clear_history)
        open_log_btn = QPushButton(t("open_log_btn"))
        open_log_btn.setObjectName("btn_secondary"); open_log_btn.setFixedHeight(36)
        open_log_btn.clicked.connect(self._maint_open_log)
        util_row.addWidget(clr_hist_btn); util_row.addWidget(open_log_btn); util_row.addStretch()
        maint_content.addLayout(util_row)

        maint_content.addSpacing(12)
        reset_row = QHBoxLayout()
        reset_btn = QPushButton(t("reset_settings_btn")); reset_btn.setObjectName("btn_danger")
        reset_btn.setFixedHeight(36); reset_btn.clicked.connect(self._maint_reset_settings)
        reset_row.addWidget(reset_btn); reset_row.addStretch()
        maint_content.addLayout(reset_row)

        self._maint_status = QLabel(""); self._maint_status.setObjectName("status_info")
        maint_content.addWidget(self._maint_status)

        root.addWidget(maint_card)

        # ══════════════════════════════════════════════════════════════════════
        # CARTE 9 : À propos
        # ══════════════════════════════════════════════════════════════════════
        about_card, _, about_content = make_card("ℹ", "À propos d'OmniMedia")

        # Logo + titre
        title_row = QHBoxLayout(); title_row.setSpacing(12)
        logo_lbl = QLabel()
        if LOGO_PATH.exists():
            pm = QPixmap(str(LOGO_PATH)).scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(pm)
        logo_lbl.setStyleSheet("background:transparent;")
        name_col = QVBoxLayout(); name_col.setSpacing(2)
        app_lbl = QLabel(f"OmniMedia  <span style='font-size:13px;font-weight:400;color:{COLORS['text_muted']};'>v{APP_VERSION}</span>")
        app_lbl.setStyleSheet(f"font-size:20px; font-weight:800; color:{COLORS['text_primary']}; background:transparent;")
        app_lbl.setTextFormat(Qt.TextFormat.RichText)
        tag_lbl = QLabel("Tous les formats. Sans limites.")
        tag_lbl.setStyleSheet(f"font-size:12px; color:{COLORS['text_secondary']}; background:transparent;")
        name_col.addWidget(app_lbl); name_col.addWidget(tag_lbl)
        title_row.addWidget(logo_lbl); title_row.addLayout(name_col); title_row.addStretch()
        about_content.addLayout(title_row)

        self.version_status = QLabel(t("checking_version"))
        self.version_status.setObjectName("status_info")
        about_content.addWidget(self.version_status)

        about_content.addSpacing(6)
        desc = QLabel(
            "OmniMedia est une application de bureau gratuite et open-source pour "
            "télécharger, convertir et compresser vos fichiers médias. "
            "Elle fonctionne entièrement en local — aucune donnée personnelle n'est envoyée."
        )
        desc.setObjectName("subtitle"); desc.setWordWrap(True)
        about_content.addWidget(desc)

        about_content.addSpacing(14)

        # ── Moteurs open-source ────────────────────────────────────────────────
        about_content.addWidget(make_section("MOTEURS OPEN-SOURCE"))
        _c = COLORS["accent_light"]
        _services = [
            ("yt-dlp",      "https://github.com/yt-dlp/yt-dlp",           "Téléchargement  (1000+ sites)"),
            ("FFmpeg",       "https://ffmpeg.org",                          "Conversion & compression"),
            ("PyQt6",        "https://riverbankcomputing.com",              "Interface graphique"),
            ("mutagen",      "https://github.com/quodlibet/mutagen",        "Tags audio (ID3, FLAC…)"),
            ("darkdetect",   "https://github.com/albertosottile/darkdetect","Détection thème OS"),
        ]
        for eng, url, role in _services:
            row = QHBoxLayout(); row.setSpacing(8)
            lnk = QLabel(f'<a href="{url}" style="color:{_c}; font-weight:700; text-decoration:none;">{eng}</a>')
            lnk.setOpenExternalLinks(True); lnk.setTextFormat(Qt.TextFormat.RichText)
            lnk.setStyleSheet("background:transparent; min-width:100px;")
            rl = QLabel(f"— {role}"); rl.setObjectName("subtitle")
            row.addWidget(lnk); row.addWidget(rl, 1)
            about_content.addLayout(row)

        about_content.addSpacing(14)

        # ── Services externes utilisés ─────────────────────────────────────────
        about_content.addWidget(make_section("SERVICES EXTERNES"))
        _ext = [
            ("MusicBrainz",  "https://musicbrainz.org",                   "Métadonnées musicales (titre, artiste, album, ISRC, genre…)"),
            ("YouTube",      "https://youtube.com",                        "Source principale de téléchargement via yt-dlp"),
            ("GitHub API",   "https://api.github.com",                     "Vérification des mises à jour de l'application"),
            ("Lucide Icons", "https://lucide.dev",                         "Bibliothèque d'icônes SVG"),
        ]
        for svc, url, role in _ext:
            row = QHBoxLayout(); row.setSpacing(8)
            lnk = QLabel(f'<a href="{url}" style="color:{_c}; font-weight:700; text-decoration:none;">{svc}</a>')
            lnk.setOpenExternalLinks(True); lnk.setTextFormat(Qt.TextFormat.RichText)
            lnk.setStyleSheet("background:transparent; min-width:100px;")
            rl = QLabel(f"— {role}"); rl.setObjectName("subtitle")
            row.addWidget(lnk); row.addWidget(rl, 1)
            about_content.addLayout(row)

        about_content.addSpacing(14)

        # ── Remerciements ──────────────────────────────────────────────────────
        about_content.addWidget(make_section("REMERCIEMENTS"))
        thanks = QLabel(
            "Un merci à <b>yt-dlp</b>, "
            "<b>FFmpeg</b>, <b>MusicBrainz</b>, <b>mutagen</b>, <b>PyQt6</b> et "
            "<b>Lucide</b> — sans qui OmniMedia ne serait qu'une page blanche. "
        )
        thanks.setObjectName("subtitle"); thanks.setWordWrap(True)
        thanks.setTextFormat(Qt.TextFormat.RichText)
        about_content.addWidget(thanks)

        about_content.addSpacing(12)

        # ── Liens projet ───────────────────────────────────────────────────────
        links_row = QHBoxLayout(); links_row.setSpacing(10)
        for label, url in [
            ("GitHub", "https://github.com/SanoBld/OmniMedia"),
            ("Releases", "https://github.com/SanoBld/OmniMedia/releases"),
            ("Signaler un bug", "https://github.com/SanoBld/OmniMedia/issues"),
        ]:
            btn = QPushButton(label); btn.setObjectName("btn_secondary")
            btn.setFixedHeight(34)
            btn.clicked.connect(lambda _, u=url: __import__("webbrowser").open(u))
            links_row.addWidget(btn)
        links_row.addStretch()
        about_content.addLayout(links_row)

        root.addWidget(about_card)

        root.addStretch()

    # ── Pastille FFmpeg dynamique ─────────────────────────────────────────────

    def _update_ffmpeg_dot(self) -> None:
        ok = ffmpeg_available()
        self._ffmpeg_dot.setObjectName("ffmpeg_dot_ok" if ok else "ffmpeg_dot_err")
        self._ffmpeg_dot.setToolTip("FFmpeg détecté ✔" if ok else "FFmpeg introuvable ✗")
        self._ffmpeg_dot.style().unpolish(self._ffmpeg_dot)
        self._ffmpeg_dot.style().polish(self._ffmpeg_dot)

    def _schedule_ffmpeg_check(self) -> None:
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

    def _on_tray_close_toggled(self, enabled: bool) -> None:
        cfg.minimize_to_tray = enabled
        self._tray_sub_widget.setEnabled(enabled)
        self._dis_tray_btn.setEnabled(enabled)
        win = self.window()
        if not enabled and hasattr(win, "_tray") and win._tray is not None:
            win._tray.hide()
        elif enabled and hasattr(win, "_tray") and win._tray is not None:
            win._tray.show()

    def _apply_accent(self, key: str) -> None:
        pass  # supprimé — l'accent vient du thème système ou du thème sélectionné

    def _on_opacity_changed(self, value: int) -> None:
        pass  # supprimé — opacité fixée à 100 %

    def _on_anim_toggled(self, enabled: bool) -> None:
        cfg.animations_enabled = enabled

    def _apply_statsbar(self, visible: bool) -> None:
        win = self.window()
        if hasattr(win, "_stats_bar"):
            win._stats_bar.setVisible(visible)

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
        p = log_path()
        if p.exists():
            open_folder(p)
        else:
            set_status(self._maint_status, t("log_not_found"), "warn")

    def _maint_disable_tray(self) -> None:
        cfg.minimize_to_tray = False
        cfg.start_in_tray = False
        self._tray_close_cb.setChecked(False)
        self._tray_start_cb.setChecked(False)
        self._tray_sub_widget.setEnabled(False)
        self._dis_tray_btn.setEnabled(False)
        win = self.window()
        if hasattr(win, "_tray") and win._tray is not None:
            win._tray.hide()
        set_status(self._tray_status, "✔  Mode arrière-plan désactivé.", "ok")

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
        # Refresh system theme preview button color when system accent is applied
        if key == "system":
            from ui_styles import get_system_accent_color, COLORS
            accent = get_system_accent_color()
            if accent:
                hint = (f"color:{accent}; font-weight:700; font-size:12px;"
                        f"background:{COLORS['bg_card']}; border:2px solid {accent};")
                self._theme_btns["system"].setStyleSheet(hint)
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
    minimize_to_tray_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent); self.setFixedHeight(56)
        self.setStyleSheet(
            f"background:{COLORS['bg_card']}; "
            f"border-bottom:1px solid {COLORS['border_soft']};"
        )
        lay = QHBoxLayout(self); lay.setContentsMargins(28, 0, 24, 0); lay.setSpacing(12)

        name_lbl = QLabel("OmniMedia")
        name_lbl.setStyleSheet(
            f"font-size:17px; font-weight:800; color:{COLORS['text_primary']}; "
            f"letter-spacing:-0.5px; background:transparent;"
        )
        ver = QLabel(f"v{APP_VERSION}")
        ver.setStyleSheet(badge_style("info"))

        lay.addWidget(name_lbl)
        lay.addWidget(ver)
        lay.addStretch()
        # Le bouton ⚙ est supprimé — Paramètres accessible via le corner widget de la TabBar
        self._settings_btn = None  # gardé pour compat, non affiché


# ══════════════════════════════════════════════════════════════════════════════
#  Main window
# ══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} Converter & Downloader")
        self.setWindowIcon(app_icon()); self.setMinimumSize(660, 640); self.resize(820, 940)
        self.setAcceptDrops(True)
        self._tray: QSystemTrayIcon | None = None
        self._settings_tab: SettingsTab | None = None
        self._setup_ui(); self._setup_tray(); self._attach_taskbar(); self._check_github_version()
        QTimer.singleShot(400, self._check_ffmpeg)

    def _setup_ui(self) -> None:
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        self._header = HeaderBar()
        self._header.minimize_to_tray_requested.connect(self._minimize_to_tray)
        root.addWidget(self._header)

        tab_container = QWidget()
        tab_container.setObjectName("tab_container")
        tab_container_layout = QVBoxLayout(tab_container)
        tab_container_layout.setContentsMargins(0, 0, 0, 0); tab_container_layout.setSpacing(0)

        self.tabs = FadingTabWidget()
        self.tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._dl_tab       = DownloadTab()
        self._conv_tab     = ConvertTab()
        self._comp_tab     = CompressorTab()
        self._settings_tab = SettingsTab()

        self.tabs.addTab(self._dl_tab,   "  Télécharger  ")
        self.tabs.addTab(self._conv_tab, "  Convertir    ")
        self.tabs.addTab(self._comp_tab, "  Compresser   ")
        # Onglet 3 : Paramètres — caché de la TabBar, activé via corner widget
        self.tabs.addTab(self._settings_tab, "")
        self.tabs.setTabVisible(3, False)

        _ic_color = COLORS.get("text_secondary", "#8A96B8")
        # stroke_width=1.8 à 16px pour cohérence visuelle (proportionnel à 2.0 à 18-26px)
        for icon_name, idx in [("download", 0), ("convert", 1), ("compress", 2)]:
            self.tabs.setTabIcon(idx, svg_icon(icon_name, color=_ic_color, size=16, stroke_width=1.8))

        # ── Bouton Paramètres en coin droit de la TabBar ──────────────────────
        self._settings_corner_btn = QPushButton("  ⚙  Paramètres  ")
        self._settings_corner_btn.setObjectName("corner_settings_btn")
        self._settings_corner_btn.setCheckable(True)
        self._settings_corner_btn.setFixedHeight(34)
        self._settings_corner_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # Le style est défini dans ui_styles.py via #corner_settings_btn
        self._settings_corner_btn.clicked.connect(self._toggle_settings)
        self.tabs.setCornerWidget(self._settings_corner_btn, Qt.Corner.TopRightCorner)

        tab_container_layout.addWidget(self.tabs)
        root.addWidget(tab_container, 1)

        # Overlay Drag & Drop
        self._drag_overlay = DragOverlay(central)
        self._drag_overlay.set_drop_callback(self._route_drop)
        self._drag_overlay.hide()

        # Dashboard stats — visible selon préférence
        self._stats_bar = StatsBar()
        self._stats_bar.setVisible(cfg.get("show_stats_bar", True))
        root.addWidget(self._stats_bar)

        footer = QLabel(t("footer", ver=APP_VERSION))
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(
            f"font-size:11px; color:{COLORS['text_muted']}; background:{COLORS['bg_card']}; "
            f"border-top:1px solid {COLORS['border_soft']}; padding:8px;"
        )
        root.addWidget(footer)

    def _check_ffmpeg(self) -> None:
        """Run FFmpeg capability check and surface any warnings to the user."""
        caps = check_ffmpeg_capabilities()
        logger.info(
            "FFmpeg check — available=%s version=%s codecs=%s",
            caps.available, caps.version_str,
            [k for k, v in caps.codecs.items() if v],
        )
        if caps.warnings:
            for w in caps.warnings:
                logger.warning("FFmpeg: %s", w)
            self._show_ffmpeg_banner(caps.warnings)

    def _show_ffmpeg_banner(self, warnings: list[str]) -> None:
        """
        Inject a dismissible warning banner at the top of the window.
        Shows only the first warning to keep the UI clean; the rest go to the log.
        """
        if not warnings:
            return
        banner = QFrame(self.centralWidget())
        banner.setObjectName("ffmpeg_warning_banner")
        banner.setStyleSheet(
            f"QFrame#ffmpeg_warning_banner {{"
            f"  background: {COLORS.get('warn_bg', '#3D2E00')};"
            f"  border-bottom: 1px solid {COLORS.get('warn_border', '#7A5C00')};"
            f"  padding: 0px;"
            f"}}"
        )
        lay = QHBoxLayout(banner); lay.setContentsMargins(20, 8, 12, 8); lay.setSpacing(10)

        icon = QLabel("⚠")
        icon.setStyleSheet(f"font-size:15px; background:transparent; color:{COLORS.get('warning', '#F5A623')};")

        msg = QLabel(warnings[0])
        msg.setStyleSheet(
            f"font-size:12px; color:{COLORS.get('warn_text', '#F5D78E')}; background:transparent;"
        )
        msg.setWordWrap(True)
        msg.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        close_btn = QPushButton("✕")
        close_btn.setObjectName("btn_secondary")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(
            f"QPushButton{{ background:transparent; color:{COLORS.get('warn_text','#F5D78E')};"
            f"  font-size:12px; border:none; border-radius:4px; }}"
            f"QPushButton:hover{{ background:rgba(255,255,255,0.1); }}"
        )
        close_btn.clicked.connect(banner.deleteLater)

        lay.addWidget(icon); lay.addWidget(msg, 1); lay.addWidget(close_btn)

        # Insert banner just below la header bar (index 1 dans root layout)
        root_layout = self.centralWidget().layout()
        if root_layout:
            root_layout.insertWidget(1, banner)
            eff = QGraphicsOpacityEffect(banner)
            banner.setGraphicsEffect(eff)
            anim = QPropertyAnimation(eff, b"opacity", banner)
            anim.setDuration(400)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.finished.connect(lambda: banner.setGraphicsEffect(None))
            banner._anim = anim  # référence Python — évite crash GC PyQt6
            anim.start()

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable(): return
        self._tray = QSystemTrayIcon(app_icon(), parent=self)
        menu = QMenu()
        show_act = menu.addAction("⬆  " + t("tray_show"))
        show_act.triggered.connect(lambda: (self.show(), self.raise_(), self.activateWindow()))
        tray_act = menu.addAction("⬇  Réduire dans la zone de notification")
        tray_act.triggered.connect(self._minimize_to_tray)
        menu.addSeparator()
        quit_act = menu.addAction("✕  " + t("tray_quit"))
        quit_act.triggered.connect(QApplication.quit)
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
        if hasattr(self, "_drag_overlay") and self.centralWidget():
            cw = self.centralWidget()
            self._drag_overlay.setGeometry(8, 8, cw.width() - 16, cw.height() - 16)

    # ── Drag & Drop ───────────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
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
        """Route les fichiers vers l'onglet actif si possible, sinon vers Convertir."""
        media  = [p for p in paths if classify_file(p) != "unknown"]
        videos = [p for p in paths if classify_file(p) == "video"]
        current = self.tabs.currentWidget()

        # Onglet actif = Compresser ET tous les fichiers sont des vidéos → Compresser
        if current == self._comp_tab and videos:
            self._comp_tab.add_files(videos)
        # Onglet actif = Convertir → Convertir
        elif current == self._conv_tab and media:
            self._conv_tab.add_files(media)
        # Tous les autres cas → Convertir (par défaut)
        elif media:
            self.tabs.setCurrentWidget(self._conv_tab)
            self._conv_tab.add_files(media)

    def _minimize_to_tray(self) -> None:
        if self._tray and QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
            if cfg.notif_tray_bg:
                self._tray.showMessage(
                    "OmniMedia", t("tray_running"),
                    QSystemTrayIcon.MessageIcon.Information, 2000
                )

    def _toggle_settings(self) -> None:
        """Bascule vers/depuis l'onglet Paramètres via le corner widget."""
        going_to_settings = self.tabs.currentIndex() != 3
        self.tabs.setCurrentIndex(3 if going_to_settings else 0)
        self._settings_corner_btn.setChecked(going_to_settings)

    def closeEvent(self, event) -> None:
        # Annuler tous les workers actifs avant que Python ne détruise les threads
        # (évite le crash ThreadPoolExecutor dans threading.py atexit)
        for tab in (self._dl_tab, self._conv_tab, self._comp_tab):
            try:
                w = getattr(tab, "_worker", None) or getattr(tab, "_batch_worker", None)
                if w is not None and w.isRunning():
                    w.cancel()
                    w.quit()
                    w.wait(800)
            except Exception:
                pass
        event.accept()
        QApplication.quit()


# ══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    # Doit être appelé AVANT la création de QApplication
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME); app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(True)
    ThemeManager.setup(app)
    window = MainWindow(); window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
