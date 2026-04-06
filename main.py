"""
main.py — OmniMedia v4
Changes vs v3:
  - Uses ConfigManager (config_manager.py) for all settings.
  - resource_path() replaces raw Path(__file__) for bundle compat.
  - DownloadAdvancedPanel: playlist_mode + auto_tag checkboxes.
  - DownloadTab: visual download queue (QListWidget) with status badges.
  - ConvertTab: Batch Compressor panel (target-size mode).
  - SettingsTab: custom FFmpeg path field + Light theme button.
"""
from __future__ import annotations

import sys, os, subprocess
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
            f"\n╔══════════════════════════════════════════╗\n"
            f"║  OmniMedia — Missing dependencies        ║\n"
            f"╠══════════════════════════════════════════╣\n"
            f"║  Modules : {', '.join(missing):<32}║\n"
            f"║  Command : pip install {pkgs:<27}║\n"
            f"╚══════════════════════════════════════════╝\n",
            file=sys.stderr,
        )
        input("Press Enter to close…")
        sys.exit(1)

_check_dependencies()
# ─────────────────────────────────────────────────────────────────────────────

from PyQt6.QtCore    import Qt, QTimer, QSize
from PyQt6.QtGui     import QDragEnterEvent, QDropEvent, QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QButtonGroup,
    QProgressBar, QTabWidget, QFrame, QFileDialog, QListWidget,
    QListWidgetItem, QComboBox, QSizePolicy, QMessageBox,
    QScrollArea, QSystemTrayIcon, QMenu, QCheckBox, QSpinBox,
)

from config_manager import cfg, resource_path
from i18n           import t, set_language, current_language
from ui_styles      import get_stylesheet, get_palette, COLORS, badge_style, section_label_style
from downloader     import (
    DownloadWorker, AdvancedOptions, YtdlpUpdateWorker, VersionChecker,
    history as dl_history, SUPPORTED_BROWSERS,
    BROWSER_COOKIE3_AVAILABLE, BrowserCookieWorker, MUTAGEN_AVAILABLE,
)
from converter import (
    ConvertWorker, BatchConvertWorker,
    classify_file, suggested_formats, ffmpeg_available, find_ffmpeg,
    PRESETS, PresetManager, _refresh_presets,
    get_media_info, format_media_info, COMPRESS_TARGETS,
)

# ── Constants ─────────────────────────────────────────────────────────────────
APP_NAME     = "OmniMedia"
APP_VERSION  = "4.0.0"
LOGO_PATH    = resource_path("logoOmniMedia.png")

# Apply saved language on startup
set_language(cfg.language)


# ── Windows Taskbar Progress ──────────────────────────────────────────────────

class _WinTaskbar:
    TBPF_NOPROGRESS    = 0
    TBPF_INDETERMINATE = 1
    TBPF_NORMAL        = 2
    TBPF_ERROR         = 4
    TBPF_PAUSED        = 8

    def __init__(self) -> None:
        self._com  = None
        self._hwnd = 0
        if sys.platform == "win32":
            self._try_init()

    def _try_init(self) -> None:
        try:
            import ctypes, ctypes.wintypes
            ctypes.windll.ole32.CoInitialize(None)
            clsid = (ctypes.c_byte * 16)(
                0x44,0xF3,0xFD,0x56,0x6D,0xFD,0xD0,0x11,
                0x95,0x8A,0x00,0x60,0x97,0xC9,0xA0,0x90,
            )
            iid = (ctypes.c_byte * 16)(
                0x91,0xFB,0x1A,0xEA,0x28,0x9E,0x86,0x4B,
                0x90,0xE9,0x9E,0x9F,0x8A,0x5E,0xEF,0xAF,
            )
            obj = ctypes.c_void_p()
            hr  = ctypes.windll.ole32.CoCreateInstance(clsid, None, 1, iid, ctypes.byref(obj))
            if hr == 0 and obj.value:
                self._com = obj
                vt  = ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p))
                vtp = ctypes.cast(vt[0], ctypes.POINTER(ctypes.c_void_p))
                ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vtp[3])(obj)
        except Exception:
            self._com = None

    def attach(self, hwnd: int) -> None:
        self._hwnd = hwnd

    def _vtp(self):
        import ctypes
        vt = ctypes.cast(self._com, ctypes.POINTER(ctypes.c_void_p))
        return ctypes.cast(vt[0], ctypes.POINTER(ctypes.c_void_p))

    def set_progress(self, value: int, total: int = 100) -> None:
        if not self._com or not self._hwnd or sys.platform != "win32": return
        try:
            import ctypes, ctypes.wintypes
            ctypes.WINFUNCTYPE(
                ctypes.c_long, ctypes.c_void_p,
                ctypes.wintypes.HWND, ctypes.c_ulonglong, ctypes.c_ulonglong,
            )(self._vtp()[9])(self._com, ctypes.wintypes.HWND(self._hwnd), value, total)
        except Exception: pass

    def set_state(self, state: int) -> None:
        if not self._com or not self._hwnd or sys.platform != "win32": return
        try:
            import ctypes, ctypes.wintypes
            ctypes.WINFUNCTYPE(
                ctypes.c_long, ctypes.c_void_p, ctypes.wintypes.HWND, ctypes.c_int,
            )(self._vtp()[10])(self._com, ctypes.wintypes.HWND(self._hwnd), state)
        except Exception: pass

    def clear(self) -> None:
        self.set_state(self.TBPF_NOPROGRESS)


_taskbar = _WinTaskbar()


# ── ThemeManager ──────────────────────────────────────────────────────────────

class ThemeManager:
    _app:   QApplication | None = None
    _theme: str = cfg.theme

    @classmethod
    def setup(cls, app: QApplication) -> None:
        cls._app = app
        cls.apply(cls._theme)

    @classmethod
    def apply(cls, theme: str) -> None:
        cls._theme = theme
        cfg.theme  = theme          # persists via config_manager
        if cls._app:
            cls._app.setStyleSheet(get_stylesheet(theme))

    @classmethod
    def current(cls) -> str:
        return cls._theme


# ── UI helpers ────────────────────────────────────────────────────────────────

def open_folder(path: str | Path) -> None:
    p = Path(path)
    target = p if p.is_dir() else p.parent
    if sys.platform == "win32":    os.startfile(str(target))
    elif sys.platform == "darwin": subprocess.Popen(["open", str(target)])
    else:                          subprocess.Popen(["xdg-open", str(target)])

def hline() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet(f"background:{COLORS['border']}; border:none; margin:2px 0;")
    return f

def make_label(text: str, obj: str = "") -> QLabel:
    lbl = QLabel(text)
    if obj: lbl.setObjectName(obj)
    return lbl

def make_section(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(section_label_style())
    return lbl

def set_status(lbl: QLabel, text: str, kind: str = "info") -> None:
    lbl.setObjectName({
        "info": "status_info", "ok": "status_ok",
        "err":  "status_err",  "warn": "status_warn",
    }.get(kind, "status_info"))
    lbl.setText(text)
    lbl.style().unpolish(lbl); lbl.style().polish(lbl)

def app_icon() -> QIcon:
    if LOGO_PATH.exists():
        return QIcon(str(LOGO_PATH))
    pm = QPixmap(64, 64); pm.fill(QColor(COLORS["accent"]))
    return QIcon(pm)

def notifications_enabled() -> bool:
    return cfg.notifications

def parallel_workers() -> int:
    return cfg.max_workers


# ── Per-file progress widget ──────────────────────────────────────────────────

class FileProgressItem(QWidget):
    def __init__(self, icon: str, name: str, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 3, 8, 3); lay.setSpacing(8)

        self._status = QLabel("·")
        self._status.setFixedWidth(14)
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet(f"color:{COLORS['text_muted']}; background:transparent; font-size:13px;")

        icon_lbl = QLabel(icon); icon_lbl.setFixedWidth(18)
        icon_lbl.setStyleSheet("background:transparent; font-size:13px;")

        self._name = QLabel(name)
        self._name.setStyleSheet(f"background:transparent; color:{COLORS['text_secondary']}; font-size:12px;")
        self._name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._bar = QProgressBar()
        self._bar.setValue(0); self._bar.setTextVisible(False); self._bar.setFixedSize(90, 5)
        self._bar.setStyleSheet(
            f"QProgressBar {{ background:{COLORS['bg_hover']}; border:none; border-radius:3px; }}"
            f"QProgressBar::chunk {{ background:{COLORS['accent']}; border-radius:3px; }}"
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
        super().__init__(parent)
        self.setObjectName("drop_zone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(120)
        self._on_drop = on_drop
        lay = QVBoxLayout(self); lay.setAlignment(Qt.AlignmentFlag.AlignCenter); lay.setSpacing(8)
        self.icon_lbl = QLabel("⬇"); self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setStyleSheet("font-size:32px; background:transparent; color:#5C96FF;")
        self.text_lbl = QLabel(t("drop_zone_text")); self.text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_lbl.setStyleSheet(f"font-size:15px; font-weight:600; color:{COLORS['text_primary']}; background:transparent;")
        self.sub_lbl  = QLabel(t("drop_zone_sub")); self.sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_lbl.setStyleSheet(f"font-size:12px; color:{COLORS['text_muted']}; background:transparent;")
        lay.addWidget(self.icon_lbl); lay.addWidget(self.text_lbl); lay.addWidget(self.sub_lbl)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("drag_active", "true")
            self.style().unpolish(self); self.style().polish(self)
            self.text_lbl.setText(t("drop_zone_active"))
        else:
            event.ignore()

    def dragLeaveEvent(self, _) -> None:
        self.setProperty("drag_active", "false")
        self.style().unpolish(self); self.style().polish(self)
        self.text_lbl.setText(t("drop_zone_text"))

    def dropEvent(self, event: QDropEvent) -> None:
        self.setProperty("drag_active", "false")
        self.style().unpolish(self); self.style().polish(self)
        self.text_lbl.setText(t("drop_zone_text"))
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls()]
        if paths: self._on_drop(paths)


# ══════════════════════════════════════════════════════════════════════════════
#  Advanced download panel
# ══════════════════════════════════════════════════════════════════════════════

class DownloadAdvancedPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cookies_path = ""
        self._browser_cookie_worker: BrowserCookieWorker | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.setSpacing(6)

        self.toggle_btn = QPushButton(t("adv_options_closed"))
        self.toggle_btn.setObjectName("btn_advanced")
        self.toggle_btn.setCheckable(True); self.toggle_btn.setFixedHeight(32)
        self.toggle_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.toggle_btn.clicked.connect(self._toggle)
        outer.addWidget(self.toggle_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self.panel = QFrame(); self.panel.setObjectName("advanced_panel"); self.panel.hide()
        pl = QVBoxLayout(self.panel); pl.setContentsMargins(16,14,16,14); pl.setSpacing(14)

        # Bitrate + Resolution
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

        # Playlist items
        row2 = QVBoxLayout(); row2.addWidget(make_section(t("playlist_items")))
        self.playlist_input = QLineEdit(); self.playlist_input.setPlaceholderText(t("playlist_placeholder"))
        row2.addWidget(self.playlist_input); pl.addLayout(row2)

        # Playlist mode checkbox (NEW)
        self.playlist_mode_cb = QCheckBox(t("playlist_mode"))
        self.playlist_mode_cb.setChecked(cfg.playlist_mode)
        pl.addWidget(self.playlist_mode_cb)

        # Cookies.txt
        row3 = QVBoxLayout(); row3.addWidget(make_section(t("cookies_file")))
        cookie_row = QHBoxLayout()
        self.cookie_label = QLabel(t("no_file_selected")); self.cookie_label.setObjectName("status_info")
        cookie_btn = QPushButton(t("load_cookies")); cookie_btn.setObjectName("btn_secondary")
        cookie_btn.setFixedHeight(34); cookie_btn.clicked.connect(self._pick_cookie)
        cookie_row.addWidget(self.cookie_label, 1); cookie_row.addWidget(cookie_btn)
        row3.addLayout(cookie_row); pl.addLayout(row3)

        # Browser cookies
        row4 = QVBoxLayout(); row4.addWidget(make_section(t("browser_cookies_section")))
        browser_row = QHBoxLayout()
        self.browser_combo = QComboBox(); self.browser_combo.addItem("—", "")
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

        # Embed thumbnail
        self.embed_thumb_cb = QCheckBox(t("embed_thumbnail"))
        self.embed_thumb_cb.setChecked(cfg.get("embed_thumbnail", True))
        self.embed_thumb_cb.setEnabled(MUTAGEN_AVAILABLE)
        pl.addWidget(self.embed_thumb_cb)

        # Smart auto-tag (NEW)
        self.auto_tag_cb = QCheckBox(t("auto_tag"))
        self.auto_tag_cb.setChecked(cfg.auto_tag)
        self.auto_tag_cb.setEnabled(MUTAGEN_AVAILABLE)
        self.auto_tag_cb.setToolTip("Requires mutagen. Embeds artist, album, year, cover art in MP3.")
        pl.addWidget(self.auto_tag_cb)

        outer.addWidget(self.panel)

    def _toggle(self) -> None:
        visible = self.panel.isVisible()
        self.panel.setVisible(not visible)
        self.toggle_btn.setText(t("adv_options_open" if not visible else "adv_options_closed"))

    def _pick_cookie(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select cookies.txt", str(Path.home()), "Text (*.txt);;All (*)")
        if path:
            self._cookies_path = path
            self.cookie_label.setText(Path(path).name)

    def _import_browser_cookies(self) -> None:
        browser = self.browser_combo.currentData()
        if not browser: return
        self.import_browser_btn.setEnabled(False)
        self._browser_cookie_worker = BrowserCookieWorker(browser, parent=self)
        self._browser_cookie_worker.finished.connect(self._on_browser_cookies)
        self._browser_cookie_worker.start()

    def _on_browser_cookies(self, ok: bool, result: str) -> None:
        self.import_browser_btn.setEnabled(True)
        if ok:
            self._cookies_path = result
            set_status(self.browser_status, f"✔ {Path(result).name}", "ok")
        else:
            set_status(self.browser_status, f"✗ {result[:60]}", "err")

    def get_options(self) -> AdvancedOptions:
        return AdvancedOptions(
            audio_bitrate   = self.bitrate_combo.currentData(),
            video_codec     = "h264",
            max_resolution  = self.res_combo.currentData(),
            playlist_items  = self.playlist_input.text().strip(),
            cookies_file    = self._cookies_path,
            browser_cookies = "",
            embed_thumbnail = self.embed_thumb_cb.isChecked(),
        )

    def playlist_mode_enabled(self) -> bool:
        return self.playlist_mode_cb.isChecked()

    def auto_tag_enabled(self) -> bool:
        return self.auto_tag_cb.isChecked()


# ══════════════════════════════════════════════════════════════════════════════
#  Download tab  (with queue)
# ══════════════════════════════════════════════════════════════════════════════

class DownloadTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._worker: DownloadWorker | None = None
        self._last_file: str = ""
        self._output_dir: Path = cfg.download_dir
        self._queue_items: list[dict] = []   # {url, mode, item_widget}
        self._setup_ui()
        self._reload_history()

    def _setup_ui(self) -> None:
        scroll = QScrollArea(self); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget(); scroll.setWidget(container)
        outer = QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.addWidget(scroll)

        root = QVBoxLayout(container); root.setContentsMargins(28,24,28,24); root.setSpacing(18)

        # Header
        hdr = QHBoxLayout()
        ic = QLabel("⬇"); ic.setStyleSheet("font-size:24px; background:transparent;")
        hdr.addWidget(ic); hdr.addWidget(make_label(t("download_title"), "title")); hdr.addStretch()
        root.addLayout(hdr)

        # URL card
        card = QFrame(); card.setObjectName("card")
        cl = QVBoxLayout(card); cl.setSpacing(16); cl.setContentsMargins(20,20,20,20)

        cl.addWidget(make_section(t("url_section")))
        url_row = QHBoxLayout(); url_row.setSpacing(8)
        self.url_input = QLineEdit(); self.url_input.setPlaceholderText(t("url_placeholder"))
        self.url_input.setMinimumHeight(42)
        paste_btn = QPushButton("📋"); paste_btn.setObjectName("btn_secondary")
        paste_btn.setFixedSize(42,42); paste_btn.setToolTip("Paste from clipboard")
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
        cl.addLayout(folder_row)
        root.addWidget(card)

        # Advanced panel
        self.advanced = DownloadAdvancedPanel()
        root.addWidget(self.advanced)

        # Progress
        self.progress = QProgressBar(); self.progress.setValue(0)
        self.progress.setTextVisible(False); self.progress.setFixedHeight(6)
        root.addWidget(self.progress)

        # Status + open
        status_row = QHBoxLayout()
        self.status_lbl = QLabel(t("ready")); self.status_lbl.setObjectName("status_info")
        self.status_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.open_btn = QPushButton(t("open_folder")); self.open_btn.setObjectName("btn_secondary")
        self.open_btn.setFixedHeight(34); self.open_btn.hide()
        self.open_btn.clicked.connect(lambda: open_folder(self._last_file or self._output_dir))
        status_row.addWidget(self.status_lbl, 1); status_row.addWidget(self.open_btn)
        root.addLayout(status_row)

        # Action buttons
        btn_row = QHBoxLayout(); btn_row.addStretch()
        self.cancel_btn = QPushButton(t("cancel")); self.cancel_btn.setObjectName("btn_secondary")
        self.cancel_btn.setEnabled(False); self.cancel_btn.setFixedHeight(42)
        self.cancel_btn.clicked.connect(self._cancel)
        self.dl_btn = QPushButton(t("download_btn"))
        self.dl_btn.setMinimumWidth(170); self.dl_btn.setFixedHeight(42)
        self.dl_btn.clicked.connect(self._start_download)
        btn_row.addWidget(self.cancel_btn); btn_row.addWidget(self.dl_btn)
        root.addLayout(btn_row)

        # ── Download queue (NEW) ──────────────────────────────────────────
        root.addWidget(hline())
        q_hdr = QHBoxLayout(); q_hdr.addWidget(make_section(t("dl_queue_section"))); q_hdr.addStretch()
        clear_q = QPushButton(t("dl_queue_clear")); clear_q.setObjectName("btn_secondary")
        clear_q.setFixedHeight(26); clear_q.setStyleSheet("font-size:11px; padding:2px 10px;")
        clear_q.clicked.connect(self._clear_queue)
        q_hdr.addWidget(clear_q); root.addLayout(q_hdr)
        self.queue_list = QListWidget(); self.queue_list.setMaximumHeight(160)
        self.queue_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        root.addWidget(self.queue_list)

        # History
        root.addWidget(hline())
        hist_hdr = QHBoxLayout(); hist_hdr.addWidget(make_section(t("download_history")))
        hist_hdr.addStretch()
        clr_hist = QPushButton(t("clear_history")); clr_hist.setObjectName("btn_secondary")
        clr_hist.setFixedHeight(26); clr_hist.setStyleSheet("font-size:11px; padding:2px 10px;")
        clr_hist.clicked.connect(self._clear_history); hist_hdr.addWidget(clr_hist)
        root.addLayout(hist_hdr)
        self.history = QListWidget(); self.history.setMinimumHeight(90)
        self.history.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.history.itemDoubleClicked.connect(self._restore_url)
        root.addWidget(self.history, 1)

    # ── Queue helpers ─────────────────────────────────────────────────────────

    def _add_to_queue(self, url: str, mode: str) -> None:
        icon = "🎵" if mode == "audio" else "🎬"
        short_url = url[:70] + "…" if len(url) > 70 else url
        item = QListWidgetItem(f"{icon}  {short_url}  —  {t('dl_queue_pending')}")
        item.setData(Qt.ItemDataRole.UserRole, url)
        self.queue_list.addItem(item)
        self._queue_items.append({"url": url, "mode": mode, "item": item})

    def _update_queue_item(self, url: str, status_key: str) -> None:
        for q in self._queue_items:
            if q["url"] == url:
                icon = "🎵" if q["mode"] == "audio" else "🎬"
                short = url[:70] + "…" if len(url) > 70 else url
                q["item"].setText(f"{icon}  {short}  —  {t(status_key)}")
                return

    def _clear_queue(self) -> None:
        self.queue_list.clear(); self._queue_items.clear()

    # ── Download lifecycle ────────────────────────────────────────────────────

    def _reload_history(self) -> None:
        self.history.clear()
        for e in dl_history.all()[:50]:
            date = e.get("date","")[:10]
            mode = "🎵" if e.get("mode") == "audio" else "🎬"
            item = QListWidgetItem(f"{mode}  {e.get('title','?')}  —  {date}")
            item.setData(Qt.ItemDataRole.UserRole, e.get("url",""))
            item.setToolTip(e.get("url",""))
            self.history.addItem(item)

    def _restore_url(self, item: QListWidgetItem) -> None:
        url = item.data(Qt.ItemDataRole.UserRole)
        if url: self.url_input.setText(url)

    def _clear_history(self) -> None:
        dl_history.clear(); self.history.clear()

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Destination folder")
        if folder:
            self._output_dir = Path(folder)
            cfg.download_dir = folder
            self.folder_label.setText(str(self._output_dir))

    def _set_busy(self, busy: bool) -> None:
        self.dl_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        self.url_input.setEnabled(not busy)
        self.advanced.setEnabled(not busy)
        if not busy: self.progress.setValue(0); _taskbar.clear()

    def _cancel(self) -> None:
        if self._worker: self._worker.cancel()
        self._set_busy(False)
        set_status(self.status_lbl, t("download_cancelled"))

    def _start_download(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            set_status(self.status_lbl, t("paste_url_first"), "err"); return
        mode = "audio" if self.rb_audio.isChecked() else "video"
        opts = self.advanced.get_options()
        playlist = self.advanced.playlist_mode_enabled()
        auto_tag  = self.advanced.auto_tag_enabled()

        self._add_to_queue(url, mode)
        self._set_busy(True); self.open_btn.hide()
        set_status(self.status_lbl, "Starting…")
        _taskbar.set_state(_WinTaskbar.TBPF_INDETERMINATE)
        self._update_queue_item(url, "dl_queue_downloading")

        self._worker = DownloadWorker(
            url, self._output_dir, mode, opts,
            playlist_mode=playlist, auto_tag=auto_tag, parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.status.connect(lambda msg, _=None: self.status_lbl.setText(msg))
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, v: int) -> None:
        self.progress.setValue(v)
        _taskbar.set_state(_WinTaskbar.TBPF_NORMAL)
        _taskbar.set_progress(v)

    def _on_finished(self, ok: bool, path: str) -> None:
        self._last_file = path
        self._set_busy(False)
        if ok:
            self.progress.setValue(100); self.open_btn.show()
            set_status(self.status_lbl, f"✔  {Path(path).name}", "ok")
            # Mark last queue item done
            if self._queue_items:
                self._queue_items[-1]["item"].setText(
                    self._queue_items[-1]["item"].text().replace(
                        t("dl_queue_downloading"), t("dl_queue_done")
                    )
                )
            self._reload_history()
            if notifications_enabled():
                win = self.window()
                if hasattr(win, "notify"):
                    win.notify(t("notif_dl_done"), Path(path).name)
        else:
            _taskbar.set_state(_WinTaskbar.TBPF_ERROR)
            set_status(self.status_lbl, f"✗  {path.splitlines()[0]}", "err")
            if self._queue_items:
                self._queue_items[-1]["item"].setText(
                    self._queue_items[-1]["item"].text().replace(
                        t("dl_queue_downloading"), t("dl_queue_error")
                    )
                )


# ══════════════════════════════════════════════════════════════════════════════
#  Convert tab  (with batch compressor)
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
        hdr.addWidget(ic); hdr.addWidget(make_label(t("convert_title"), "title")); hdr.addStretch()
        root.addLayout(hdr)

        self.drop_zone = DropZone(self._on_files_dropped)
        root.addWidget(self.drop_zone, 1)

        browse_row = QHBoxLayout(); browse_row.addStretch()
        browse_btn = QPushButton(t("browse")); browse_btn.setObjectName("btn_secondary")
        browse_btn.setFixedHeight(34); browse_btn.clicked.connect(self._browse_files)
        browse_row.addWidget(browse_btn); browse_row.addStretch(); root.addLayout(browse_row)

        # Queue list
        q_hdr = QHBoxLayout(); q_hdr.addWidget(make_section(t("queue_section"))); q_hdr.addStretch()
        self.batch_count_lbl = QLabel(""); self.batch_count_lbl.setObjectName("status_info")
        q_hdr.addWidget(self.batch_count_lbl)
        clr_q = QPushButton(t("clear_queue")); clr_q.setObjectName("btn_secondary")
        clr_q.setFixedHeight(26); clr_q.setStyleSheet("font-size:11px; padding:2px 10px;")
        clr_q.clicked.connect(self._clear_queue); q_hdr.addWidget(clr_q); root.addLayout(q_hdr)
        self.queue_list = QListWidget(); self.queue_list.setMaximumHeight(150)
        self.queue_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        root.addWidget(self.queue_list)

        # Options card
        opts_card = QFrame(); opts_card.setObjectName("card")
        ocl = QHBoxLayout(opts_card); ocl.setSpacing(16); ocl.setContentsMargins(16,14,16,14)

        preset_col = QVBoxLayout(); preset_col.setSpacing(6)
        preset_col.addWidget(make_section(t("preset_section")))
        self.preset_combo = QComboBox(); self._reload_presets_combo()
        self.preset_combo.setMinimumWidth(200)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        preset_col.addWidget(self.preset_combo)
        self.preset_desc = QLabel(list(PRESETS.values())[0]["desc"])
        self.preset_desc.setObjectName("subtitle"); self.preset_desc.setWordWrap(True)
        preset_col.addWidget(self.preset_desc); ocl.addLayout(preset_col)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color:{COLORS['border_soft']};"); ocl.addWidget(sep)

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
        fmt_col.addLayout(outdir_row); ocl.addLayout(fmt_col, 1)
        root.addWidget(opts_card)

        # Trim card
        trim_card = QFrame(); trim_card.setObjectName("card_inner")
        tcl = QHBoxLayout(trim_card); tcl.setContentsMargins(16,12,16,12); tcl.setSpacing(16)
        trim_lbl = QLabel(t("trim_section"))
        trim_lbl.setStyleSheet(f"color:{COLORS['text_secondary']}; font-size:12px; font-weight:600; background:transparent;")
        tcl.addWidget(trim_lbl); tcl.addSpacing(8)
        for attr, key_lbl, key_ph, w in [
            ("trim_start","trim_start","trim_start_ph",110),
            ("trim_end","trim_end","trim_end_ph",130),
        ]:
            col = QVBoxLayout(); col.setSpacing(4)
            col.addWidget(make_section(t(key_lbl)))
            inp = QLineEdit(); inp.setPlaceholderText(t(key_ph)); inp.setFixedWidth(w)
            setattr(self, attr, inp); col.addWidget(inp); tcl.addLayout(col)
        tcl.addStretch(); root.addWidget(trim_card)

        # ── Batch Compressor panel (NEW) ──────────────────────────────────────
        comp_card = QFrame(); comp_card.setObjectName("compress_panel")
        comp_layout = QVBoxLayout(comp_card); comp_layout.setContentsMargins(16,12,16,12); comp_layout.setSpacing(10)
        comp_hdr = QHBoxLayout()
        comp_hdr.addWidget(make_section(t("compress_section"))); comp_hdr.addStretch()
        self.compress_cb = QCheckBox(t("compress_enable"))
        self.compress_cb.setChecked(False)
        self.compress_cb.toggled.connect(self._on_compress_toggled)
        comp_hdr.addWidget(self.compress_cb); comp_layout.addLayout(comp_hdr)

        self.compress_row = QWidget()
        cr = QHBoxLayout(self.compress_row); cr.setContentsMargins(0,0,0,0); cr.setSpacing(10)
        cr.addWidget(make_section(t("compress_target_label")))
        self.compress_combo = QComboBox()
        for label, key in [
            (t("compress_discord"),  "discord"),
            (t("compress_whatsapp"), "whatsapp"),
            (t("compress_email"),    "email"),
            (t("compress_telegram"), "telegram"),
        ]:
            self.compress_combo.addItem(label, key)
        cr.addWidget(self.compress_combo); cr.addStretch()
        comp_desc = QLabel(t("compress_desc")); comp_desc.setObjectName("subtitle"); comp_desc.setWordWrap(True)
        comp_layout.addWidget(self.compress_row)
        comp_layout.addWidget(comp_desc)
        self.compress_row.setVisible(False)
        root.addWidget(comp_card)

        # Global progress
        prog_row = QHBoxLayout(); prog_row.addWidget(make_section(t("global_progress"))); prog_row.addStretch()
        root.addLayout(prog_row)
        self.progress = QProgressBar(); self.progress.setValue(0)
        self.progress.setTextVisible(False); self.progress.setFixedHeight(6)
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

    def _on_compress_toggled(self, checked: bool) -> None:
        self.compress_row.setVisible(checked)

    def _reload_presets_combo(self) -> None:
        _refresh_presets()
        self.preset_combo.blockSignals(True); self.preset_combo.clear()
        for key, p in PRESETS.items(): self.preset_combo.addItem(p["label"], key)
        self.preset_combo.blockSignals(False)

    def refresh_presets(self) -> None:
        self._reload_presets_combo()

    def _on_preset_changed(self) -> None:
        key = self.preset_combo.currentData(); p = PRESETS.get(key, {})
        self.preset_desc.setText(p.get("desc", ""))
        if p.get("fmt"):
            idx = self.fmt_combo.findData(p["fmt"])
            if idx >= 0: self.fmt_combo.setCurrentIndex(idx)

    def _browse_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choose files", str(Path.home()),
            "Media (*.webp *.jpg *.jpeg *.png *.bmp *.gif *.mp4 *.mkv *.avi "
            "*.mov *.webm *.mp3 *.wav *.aac *.flac *.ogg *.m4a);;All (*)",
        )
        if paths: self._on_files_dropped([Path(p) for p in paths])

    def _on_files_dropped(self, paths: list[Path]) -> None:
        added = 0
        for p in paths:
            if classify_file(p) != "unknown" and p not in self._queued_files:
                self._queued_files.append(p)
                # Use get_media_info for icon + duration preview
                info   = get_media_info(p)
                label  = format_media_info(info)
                item   = QListWidgetItem()
                widget = FileProgressItem(info.icon, label)
                item.setSizeHint(widget.sizeHint())
                self.queue_list.addItem(item)
                self.queue_list.setItemWidget(item, widget)
                self._file_widgets.append(widget)
                added += 1
        if added:
            self.convert_btn.setEnabled(True)
            set_status(self.status_lbl, t("queue_count", n=len(self._queued_files)))

    def _clear_queue(self) -> None:
        self._queued_files.clear(); self._file_widgets.clear(); self.queue_list.clear()
        self.convert_btn.setEnabled(False); set_status(self.status_lbl, t("queue_cleared"))

    def _choose_out_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Output folder")
        if folder: self._output_dir = Path(folder); self.out_dir_label.setText(folder)

    def _set_busy(self, busy: bool) -> None:
        self.convert_btn.setEnabled(not busy and len(self._queued_files) > 0)
        self.cancel_btn.setEnabled(busy); self.drop_zone.setEnabled(not busy)
        if not busy: self.progress.setValue(0); _taskbar.clear()

    def _cancel(self) -> None:
        if self._batch_worker: self._batch_worker.cancel()
        self._set_busy(False); set_status(self.status_lbl, t("conversion_cancelled"))

    def _start_batch(self) -> None:
        if not self._queued_files: return
        if not ffmpeg_available():
            QMessageBox.critical(self, "FFmpeg", t("ffmpeg_missing_msg")); return

        fmt            = self.fmt_combo.currentData()
        preset_key     = self.preset_combo.currentData()
        trim_s         = self.trim_start.text().strip()
        trim_e         = self.trim_end.text().strip()
        workers        = parallel_workers()
        compress_target = (
            self.compress_combo.currentData()
            if self.compress_cb.isChecked() else ""
        )

        self._set_busy(True); self.open_btn.hide()
        self.batch_count_lbl.setText(f"0 / {len(self._queued_files)}")
        _taskbar.set_state(_WinTaskbar.TBPF_NORMAL)

        self._batch_worker = BatchConvertWorker(
            self._queued_files, fmt, self._output_dir,
            preset_key, workers, trim_s, trim_e,
            compress_target=compress_target, parent=self,
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
        self._set_busy(False); self.progress.setValue(100); self.open_btn.show()
        msg = f"✔  {success} converted" + (f"  ·  ✗ {errors} error(s)" if errors else "")
        set_status(self.status_lbl, msg, "ok" if not errors else "warn")
        if notifications_enabled():
            win = self.window()
            if hasattr(win, "notify"): win.notify(t("notif_conv_done"), msg)

    def add_files(self, paths: list[Path]) -> None:
        self._on_files_dropped(paths)


# ══════════════════════════════════════════════════════════════════════════════
#  Settings tab  (with custom FFmpeg path + Light theme)
# ══════════════════════════════════════════════════════════════════════════════

class SettingsTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._update_worker: YtdlpUpdateWorker | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self); root.setContentsMargins(28,24,28,24); root.setSpacing(20)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget(); scroll.setWidget(container); root.addWidget(scroll)
        inner = QVBoxLayout(container); inner.setContentsMargins(0,0,0,0); inner.setSpacing(20)

        hdr = QHBoxLayout()
        ic = QLabel("⚙"); ic.setStyleSheet("font-size:24px; background:transparent;")
        hdr.addWidget(ic); hdr.addWidget(make_label(t("settings_title"), "title")); hdr.addStretch()
        inner.addLayout(hdr)

        # ── Appearance (includes Light + Auto) ────────────────────────────────
        theme_card = QFrame(); theme_card.setObjectName("card")
        tcl = QVBoxLayout(theme_card); tcl.setSpacing(14); tcl.setContentsMargins(20,18,20,18)
        tcl.addWidget(make_section(t("appearance_section")))
        theme_row = QHBoxLayout(); theme_row.setSpacing(10)
        self._theme_btns: dict[str, QPushButton] = {}
        current_theme = ThemeManager.current()
        for label, key in [
            (t("theme_dark"),"dark"), (t("theme_oled"),"oled"),
            (t("theme_light"),"light"), (t("theme_auto"),"auto"),
        ]:
            btn = QPushButton(label); btn.setObjectName("theme_btn")
            btn.setCheckable(True); btn.setChecked(key == current_theme)
            btn.setFixedHeight(36); btn.clicked.connect(lambda _, k=key: self._apply_theme(k))
            self._theme_btns[key] = btn; theme_row.addWidget(btn)
        theme_row.addStretch(); tcl.addLayout(theme_row)
        desc = QLabel(t("theme_desc")); desc.setObjectName("subtitle"); desc.setWordWrap(True)
        tcl.addWidget(desc); inner.addWidget(theme_card)

        # ── Language ──────────────────────────────────────────────────────────
        lang_card = QFrame(); lang_card.setObjectName("card")
        lcl = QVBoxLayout(lang_card); lcl.setSpacing(14); lcl.setContentsMargins(20,18,20,18)
        lcl.addWidget(make_section(t("language_section")))
        lang_row = QHBoxLayout(); lang_row.setSpacing(10)
        self._lang_btns: dict[str, QPushButton] = {}
        cur_lang = current_language()
        for label, key in [(t("lang_en"),"en"),(t("lang_fr"),"fr")]:
            btn = QPushButton(label); btn.setObjectName("theme_btn")
            btn.setCheckable(True); btn.setChecked(key == cur_lang)
            btn.setFixedHeight(36); btn.clicked.connect(lambda _, k=key: self._apply_language(k))
            self._lang_btns[key] = btn; lang_row.addWidget(btn)
        lang_row.addStretch(); lcl.addLayout(lang_row)
        lcl.addWidget(QLabel("⚠ Language change applies after restart."))
        inner.addWidget(lang_card)

        # ── Notifications ─────────────────────────────────────────────────────
        notif_card = QFrame(); notif_card.setObjectName("card")
        ncl = QVBoxLayout(notif_card); ncl.setSpacing(12); ncl.setContentsMargins(20,18,20,18)
        ncl.addWidget(make_section(t("notif_section")))
        self.notif_cb = QCheckBox(t("notif_enable")); self.notif_cb.setChecked(cfg.notifications)
        self.notif_cb.toggled.connect(lambda v: setattr(cfg, "notifications", v))
        ncl.addWidget(self.notif_cb)
        nd = QLabel(t("notif_desc")); nd.setObjectName("subtitle"); nd.setWordWrap(True)
        ncl.addWidget(nd); inner.addWidget(notif_card)

        # ── Parallel workers ──────────────────────────────────────────────────
        par_card = QFrame(); par_card.setObjectName("card")
        pcl = QVBoxLayout(par_card); pcl.setSpacing(12); pcl.setContentsMargins(20,18,20,18)
        pcl.addWidget(make_section(t("parallel_section")))
        par_row = QHBoxLayout(); par_row.addWidget(QLabel(t("parallel_label"))); par_row.addStretch()
        self.workers_spin = QSpinBox(); self.workers_spin.setRange(1,4)
        self.workers_spin.setValue(cfg.max_workers); self.workers_spin.setFixedWidth(70)
        self.workers_spin.valueChanged.connect(lambda v: setattr(cfg, "max_workers", v))
        par_row.addWidget(self.workers_spin); pcl.addLayout(par_row)
        pd = QLabel(t("parallel_desc")); pd.setObjectName("subtitle"); pd.setWordWrap(True)
        pcl.addWidget(pd); inner.addWidget(par_card)

        # ── FFmpeg (with custom path field) ───────────────────────────────────
        ffmpeg_card = QFrame(); ffmpeg_card.setObjectName("card")
        fcl = QVBoxLayout(ffmpeg_card); fcl.setSpacing(12); fcl.setContentsMargins(20,18,20,18)
        fcl.addWidget(make_section(t("ffmpeg_section")))
        ffpath = find_ffmpeg()
        ff_lbl = QLabel(t("ffmpeg_found", path=ffpath) if ffpath else t("ffmpeg_missing_lbl"))
        ff_lbl.setObjectName("status_ok" if ffpath else "status_err"); fcl.addWidget(ff_lbl)
        if not ffpath:
            link = QLabel(f'<a href="https://ffmpeg.org/download.html" style="color:#5C96FF;">{t("ffmpeg_guide")}</a>')
            link.setOpenExternalLinks(True); link.setTextFormat(Qt.TextFormat.RichText); fcl.addWidget(link)
            hint = QLabel(t("ffmpeg_hint")); hint.setObjectName("subtitle"); fcl.addWidget(hint)

        # Custom FFmpeg path (NEW)
        fcl.addWidget(make_section(t("ffmpeg_custom_path")))
        ffp_row = QHBoxLayout(); ffp_row.setSpacing(8)
        self.ffmpeg_path_inp = QLineEdit(); self.ffmpeg_path_inp.setText(cfg.ffmpeg_path)
        self.ffmpeg_path_inp.setPlaceholderText(t("ffmpeg_custom_placeholder"))
        ffp_browse = QPushButton(t("ffmpeg_custom_browse")); ffp_browse.setObjectName("btn_secondary")
        ffp_browse.setFixedHeight(34); ffp_browse.clicked.connect(self._browse_ffmpeg)
        ffp_save = QPushButton("💾"); ffp_save.setObjectName("btn_secondary")
        ffp_save.setFixedHeight(34); ffp_save.clicked.connect(self._save_ffmpeg_path)
        ffp_row.addWidget(self.ffmpeg_path_inp, 1); ffp_row.addWidget(ffp_browse); ffp_row.addWidget(ffp_save)
        fcl.addLayout(ffp_row)
        self.ffmpeg_path_status = QLabel(""); self.ffmpeg_path_status.setObjectName("status_info")
        fcl.addWidget(self.ffmpeg_path_status)
        inner.addWidget(ffmpeg_card)

        # ── Custom presets ────────────────────────────────────────────────────
        preset_card = QFrame(); preset_card.setObjectName("card")
        prcl = QVBoxLayout(preset_card); prcl.setSpacing(12); prcl.setContentsMargins(20,18,20,18)
        prcl.addWidget(make_section(t("presets_section")))
        self.preset_name_inp = QLineEdit(); self.preset_name_inp.setPlaceholderText(t("preset_name_ph"))
        prcl.addWidget(self.preset_name_inp)
        pr_row = QHBoxLayout(); pr_row.setSpacing(12)
        fmt_col = QVBoxLayout(); fmt_col.addWidget(make_section(t("preset_fmt_label")))
        self.preset_fmt_combo = QComboBox()
        for f in ["mp4","mp3","mkv","flac","wav","gif","jpg","png"]: self.preset_fmt_combo.addItem(f, f)
        fmt_col.addWidget(self.preset_fmt_combo); pr_row.addLayout(fmt_col)
        args_col = QVBoxLayout(); args_col.addWidget(make_section(t("preset_args_label")))
        self.preset_args_inp = QLineEdit(); self.preset_args_inp.setPlaceholderText(t("preset_args_ph"))
        args_col.addWidget(self.preset_args_inp); pr_row.addLayout(args_col, 1)
        prcl.addLayout(pr_row)
        pr_btn_row = QHBoxLayout()
        save_btn = QPushButton(t("save_preset")); save_btn.setFixedHeight(34); save_btn.clicked.connect(self._save_preset)
        del_btn = QPushButton(t("delete_preset")); del_btn.setObjectName("btn_danger"); del_btn.setFixedHeight(34)
        del_btn.clicked.connect(self._delete_preset)
        pr_btn_row.addWidget(save_btn); pr_btn_row.addWidget(del_btn); pr_btn_row.addStretch()
        prcl.addLayout(pr_btn_row)
        self.preset_status = QLabel(""); self.preset_status.setObjectName("status_info"); prcl.addWidget(self.preset_status)
        self.preset_list = QListWidget(); self.preset_list.setMaximumHeight(80)
        self.preset_list.itemClicked.connect(self._select_preset); prcl.addWidget(self.preset_list)
        self._refresh_preset_list(); inner.addWidget(preset_card)

        # ── yt-dlp ────────────────────────────────────────────────────────────
        ytdlp_card = QFrame(); ytdlp_card.setObjectName("card")
        ycl = QVBoxLayout(ytdlp_card); ycl.setSpacing(12); ycl.setContentsMargins(20,18,20,18)
        ycl.addWidget(make_section(t("ytdlp_section")))
        ytdlp_row = QHBoxLayout()
        try:
            import yt_dlp as _ydl; ver = getattr(_ydl.version, "__version__", "?")
            ytdlp_row.addWidget(QLabel(t("ytdlp_version", ver=ver)))
        except Exception:
            ytdlp_row.addWidget(QLabel(t("ytdlp_not_installed")))
        ytdlp_row.addStretch()
        self.update_btn = QPushButton(t("ytdlp_update_btn")); self.update_btn.setFixedHeight(36)
        self.update_btn.clicked.connect(self._run_ytdlp_update); ytdlp_row.addWidget(self.update_btn)
        ycl.addLayout(ytdlp_row)
        self.update_status = QLabel(""); self.update_status.setObjectName("status_info"); self.update_status.setWordWrap(True)
        ycl.addWidget(self.update_status); inner.addWidget(ytdlp_card)

        # ── About ─────────────────────────────────────────────────────────────
        about_card = QFrame(); about_card.setObjectName("card")
        acl = QVBoxLayout(about_card); acl.setSpacing(10); acl.setContentsMargins(20,18,20,18)
        acl.addWidget(make_section(t("about_section")))
        acl.addWidget(QLabel(f"OmniMedia  v{APP_VERSION}"))
        self.version_status = QLabel(t("checking_version")); self.version_status.setObjectName("status_info")
        acl.addWidget(self.version_status)
        gh = QLabel(f'<a href="https://github.com/SanoBld/OmniMedia" style="color:#5C96FF;">{t("github_link")}</a>')
        gh.setOpenExternalLinks(True); gh.setTextFormat(Qt.TextFormat.RichText); acl.addWidget(gh)
        inner.addWidget(about_card); inner.addStretch()

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _apply_theme(self, key: str) -> None:
        ThemeManager.apply(key)
        for k, btn in self._theme_btns.items(): btn.setChecked(k == key)

    def _apply_language(self, lang: str) -> None:
        set_language(lang); cfg.language = lang
        for k, btn in self._lang_btns.items(): btn.setChecked(k == lang)

    def _browse_ffmpeg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select ffmpeg binary", str(Path.home()),
            "Executable (ffmpeg ffmpeg.exe *.exe);;All (*)",
        )
        if path: self.ffmpeg_path_inp.setText(path)

    def _save_ffmpeg_path(self) -> None:
        val = self.ffmpeg_path_inp.text().strip()
        if val and not Path(val).is_file():
            set_status(self.ffmpeg_path_status, t("ffmpeg_custom_invalid"), "err"); return
        cfg.ffmpeg_path = val
        set_status(self.ffmpeg_path_status, t("ffmpeg_custom_saved"), "ok")

    def _refresh_preset_list(self) -> None:
        self.preset_list.clear()
        for name in PresetManager.list_names(): self.preset_list.addItem(f"⭐  {name}")

    def _select_preset(self, item: QListWidgetItem) -> None:
        name = item.text().replace("⭐  ","").strip()
        self.preset_name_inp.setText(name)
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
        self.update_btn.setEnabled(False); set_status(self.update_status, "Updating…")
        self._update_worker = YtdlpUpdateWorker(parent=self)
        self._update_worker.finished.connect(self._on_update_done); self._update_worker.start()

    def _on_update_done(self, ok: bool, msg: str) -> None:
        self.update_btn.setEnabled(True)
        set_status(self.update_status, msg, "ok" if ok else "err")
        if notifications_enabled():
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
        ff_badge = QLabel(t("ffmpeg_ok") if ffok else t("ffmpeg_err")); ff_badge.setStyleSheet(badge_style("ok" if ffok else "err"))
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
        self.setWindowIcon(app_icon()); self.setMinimumSize(660,640); self.resize(820,920)
        self.setAcceptDrops(True)
        self._tray: QSystemTrayIcon | None = None
        self._settings_tab: SettingsTab | None = None
        self._setup_ui(); self._setup_tray(); self._attach_taskbar(); self._check_github_version()

    def _setup_ui(self) -> None:
        central = QWidget(); self.setCentralWidget(central)
        root_layout = QVBoxLayout(central); root_layout.setContentsMargins(0,0,0,0); root_layout.setSpacing(0)
        root_layout.addWidget(HeaderBar())
        self.tabs = QTabWidget(); self.tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._dl_tab       = DownloadTab()
        self._conv_tab     = ConvertTab()
        self._settings_tab = SettingsTab()
        self.tabs.addTab(self._dl_tab,       t("tab_download"))
        self.tabs.addTab(self._conv_tab,     t("tab_convert"))
        self.tabs.addTab(self._settings_tab, t("tab_settings"))
        root_layout.addWidget(self.tabs, 1)
        footer = QLabel(t("footer", ver=APP_VERSION))
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(f"font-size:11px; color:{COLORS['text_muted']}; background:{COLORS['bg_card']}; border-top:1px solid {COLORS['border_soft']}; padding:7px;")
        root_layout.addWidget(footer)

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

    def _check_github_version(self) -> None:
        checker = VersionChecker(APP_VERSION, parent=self)
        checker.update_available.connect(self._on_update_available)
        checker.up_to_date.connect(self._on_up_to_date)
        checker.start()

    def _on_update_available(self, latest: str) -> None:
        if self._settings_tab:
            self._settings_tab.set_version_status(t("version_new", latest=latest, ver=APP_VERSION), "warn")
        if notifications_enabled():
            self.notify(t("notif_update_title"), t("notif_update_body", latest=latest))

    def _on_up_to_date(self) -> None:
        if self._settings_tab:
            self._settings_tab.set_version_status(t("version_ok", ver=APP_VERSION), "ok")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls(): event.acceptProposedAction()
        else: event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls()]
        media = [p for p in paths if classify_file(p) != "unknown"]
        if media:
            self.tabs.setCurrentWidget(self._conv_tab); self._conv_tab.add_files(media)
        event.acceptProposedAction()

    def closeEvent(self, event) -> None:
        if self._tray and QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore(); self.hide()
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
