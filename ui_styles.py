"""
ui_styles.py — OmniMedia v4
Themes: Dark / OLED / Light / Auto (darkdetect).
"""
from __future__ import annotations
import sys

# ── Palettes ──────────────────────────────────────────────────────────────────

_DARK: dict[str, str] = {
    "bg_deep":        "#090D13",
    "bg_card":        "#111520",
    "bg_input":       "#181D2C",
    "bg_hover":       "#1E2538",
    "bg_panel":       "#141824",
    "accent":         "#3D7EF5",
    "accent_light":   "#5C96FF",
    "accent_glow":    "#1A3A7A",
    "accent_dim":     "#1E3260",
    "success":        "#2ECC8A",
    "success_dim":    "#0D2E1E",
    "warning":        "#F5A623",
    "warning_dim":    "#2E1E06",
    "danger":         "#E8445A",
    "danger_dim":     "#2E0A10",
    "text_primary":   "#DDE3F0",
    "text_secondary": "#8C94AD",
    "text_muted":     "#545C72",
    "border":         "#1E2538",
    "border_soft":    "#252D42",
    "border_focus":   "#3D7EF5",
    "border_drag_over": "#5C96FF",   # drag-hover highlight
    "drop_bg":        "#10141F",
    "drop_border":    "#252D42",
}

_OLED: dict[str, str] = {
    **_DARK,
    "bg_deep":        "#000000",
    "bg_card":        "#070A0F",
    "bg_input":       "#0A0D14",
    "bg_hover":       "#0E1118",
    "bg_panel":       "#050709",
    "border":         "#0E1118",
    "border_soft":    "#141824",
    "drop_bg":        "#000000",
    "drop_border":    "#141824",
}

_LIGHT: dict[str, str] = {
    "bg_deep":        "#F4F6FB",
    "bg_card":        "#FFFFFF",
    "bg_input":       "#EDF0F7",
    "bg_hover":       "#E4E8F3",
    "bg_panel":       "#F0F2F9",
    "accent":         "#2563EB",
    "accent_light":   "#3B82F6",
    "accent_glow":    "#DBEAFE",
    "accent_dim":     "#BFDBFE",
    "success":        "#16A34A",
    "success_dim":    "#DCFCE7",
    "warning":        "#D97706",
    "warning_dim":    "#FEF9C3",
    "danger":         "#DC2626",
    "danger_dim":     "#FEE2E2",
    "text_primary":   "#111827",
    "text_secondary": "#374151",
    "text_muted":     "#9CA3AF",
    "border":         "#D1D5DB",
    "border_soft":    "#E5E7EB",
    "border_focus":   "#2563EB",
    "border_drag_over": "#3B82F6",
    "drop_bg":        "#F8FAFF",
    "drop_border":    "#CBD5E1",
}


# ── System dark-mode detection ────────────────────────────────────────────────

def _detect_system_dark() -> bool:
    """Return True if the OS is currently using a dark appearance."""
    # Prefer darkdetect (cross-platform, real-time)
    try:
        import darkdetect
        return darkdetect.isDark() or False
    except Exception:
        pass
    # Windows fallback via registry
    try:
        if sys.platform == "win32":
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return val == 0
        if sys.platform == "darwin":
            import subprocess
            r = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True,
            )
            return "Dark" in r.stdout
    except Exception:
        pass
    return True  # default: dark


def get_palette(theme: str = "dark") -> dict[str, str]:
    """Return the colour dict for the given theme name."""
    if theme == "oled":
        return dict(_OLED)
    if theme == "light":
        return dict(_LIGHT)
    if theme == "auto":
        return dict(_DARK if _detect_system_dark() else _LIGHT)
    return dict(_DARK)


# ── Global colour dict (updated by get_stylesheet) ───────────────────────────

COLORS: dict[str, str] = dict(_DARK)


# ── Stylesheet builder ────────────────────────────────────────────────────────

def get_stylesheet(theme: str = "dark") -> str:
    """Build and return a complete Qt stylesheet for the given theme."""
    c = get_palette(theme)
    COLORS.update(c)  # keep the global in sync for inline badge usage

    return f"""
/* ═══ Reset & Global ═══════════════════════════════════════════════════ */
* {{ outline: none; }}
QWidget {{
    background-color: {c['bg_deep']};
    color: {c['text_primary']};
    font-family: "Segoe UI", "SF Pro Text", "Inter", "Helvetica Neue", sans-serif;
    font-size: 13px;
    selection-background-color: {c['accent_dim']};
    selection-color: {c['text_primary']};
}}
QMainWindow, QDialog {{ background-color: {c['bg_deep']}; }}

/* ═══ Scrollbars ════════════════════════════════════════════════════════ */
QScrollBar:vertical {{ background:transparent; width:5px; margin:0; }}
QScrollBar::handle:vertical {{ background:{c['border_soft']}; border-radius:3px; min-height:24px; }}
QScrollBar::handle:vertical:hover {{ background:{c['accent']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:transparent; height:0; }}
QScrollBar:horizontal {{ background:transparent; height:5px; }}
QScrollBar::handle:horizontal {{ background:{c['border_soft']}; border-radius:3px; }}
QScrollBar::handle:horizontal:hover {{ background:{c['accent']}; }}

/* ═══ Tabs ══════════════════════════════════════════════════════════════ */
QTabWidget::pane {{
    border:1px solid {c['border_soft']}; border-radius:0;
    background:{c['bg_deep']}; top:-1px;
}}
QTabBar {{ background:{c['bg_panel']}; border-bottom:1px solid {c['border_soft']}; }}
QTabBar::tab {{
    background:transparent; color:{c['text_muted']};
    padding:12px 26px; margin:0; font-size:13px; font-weight:500;
    letter-spacing:0.3px; border-bottom:2px solid transparent;
}}
QTabBar::tab:selected {{ color:{c['text_primary']}; border-bottom:2px solid {c['accent']}; font-weight:600; }}
QTabBar::tab:hover:!selected {{ color:{c['text_secondary']}; border-bottom:2px solid {c['border_soft']}; }}

/* ═══ Cards / Frames ════════════════════════════════════════════════════ */
QFrame#card {{
    background:{c['bg_card']}; border:1px solid {c['border_soft']}; border-radius:16px;
}}
QFrame#card_inner {{
    background:{c['bg_panel']}; border:1px solid {c['border']}; border-radius:10px;
}}

/* ═══ Text inputs ═══════════════════════════════════════════════════════ */
QLineEdit {{
    background:{c['bg_input']}; border:1.5px solid {c['border_soft']};
    border-radius:10px; padding:10px 14px; color:{c['text_primary']}; font-size:13px;
}}
QLineEdit:focus {{ border:1.5px solid {c['border_focus']}; background:{c['bg_hover']}; }}
QLineEdit:disabled {{ background:{c['bg_panel']}; color:{c['text_muted']}; border-color:{c['border']}; }}

/* ═══ Primary buttons ═══════════════════════════════════════════════════ */
QPushButton {{
    background:{c['accent']}; color:#FFFFFF; border:none; border-radius:10px;
    padding:10px 22px; font-size:13px; font-weight:600; letter-spacing:0.2px;
}}
QPushButton:hover {{ background:{c['accent_light']}; }}
QPushButton:pressed {{ background:{c['accent_dim']}; padding-top:11px; padding-bottom:9px; }}
QPushButton:disabled {{ background:{c['bg_hover']}; color:{c['text_muted']}; }}

QPushButton#btn_secondary {{
    background:{c['bg_hover']}; color:{c['text_secondary']};
    border:1px solid {c['border_soft']}; font-weight:500;
}}
QPushButton#btn_secondary:hover {{
    background:{c['bg_input']}; color:{c['text_primary']}; border-color:{c['border_focus']};
}}
QPushButton#btn_secondary:pressed {{ background:{c['bg_panel']}; }}

QPushButton#btn_success {{ background:{c['success']}; color:#071A10; font-weight:700; }}
QPushButton#btn_success:hover {{ background:{c['accent_light']}; }}

QPushButton#btn_danger {{
    background:{c['danger_dim']}; color:{c['danger']};
    border:1px solid {c['danger']}; font-weight:600;
}}
QPushButton#btn_danger:hover {{ background:{c['danger']}; color:#fff; }}

QPushButton#btn_advanced {{
    background:transparent; color:{c['text_muted']};
    border:1px solid {c['border']}; border-radius:8px;
    padding:6px 14px; font-size:12px; font-weight:500;
}}
QPushButton#btn_advanced:hover {{
    background:{c['bg_hover']}; color:{c['text_secondary']}; border-color:{c['border_soft']};
}}
QPushButton#btn_advanced:checked {{
    color:{c['accent_light']}; border-color:{c['accent_dim']}; background:{c['accent_glow']};
}}

/* ═══ Radio buttons ═════════════════════════════════════════════════════ */
QRadioButton {{ color:{c['text_secondary']}; spacing:9px; font-size:13px; }}
QRadioButton:hover {{ color:{c['text_primary']}; }}
QRadioButton::indicator {{
    width:17px; height:17px; border-radius:9px;
    border:2px solid {c['border_soft']}; background:{c['bg_input']};
}}
QRadioButton::indicator:checked {{ background:{c['accent']}; border:2px solid {c['accent_light']}; }}
QRadioButton::indicator:hover {{ border:2px solid {c['accent']}; }}

/* ═══ ComboBox ══════════════════════════════════════════════════════════ */
QComboBox {{
    background:{c['bg_input']}; border:1.5px solid {c['border_soft']};
    border-radius:10px; padding:8px 36px 8px 14px; color:{c['text_primary']}; font-size:13px;
}}
QComboBox:focus, QComboBox:hover {{ border-color:{c['border_focus']}; background:{c['bg_hover']}; }}
QComboBox::drop-down {{ subcontrol-origin:padding; subcontrol-position:center right; width:32px; border:none; }}
QComboBox::down-arrow {{
    image:none; width:0; height:0;
    border-left:4px solid transparent; border-right:4px solid transparent;
    border-top:5px solid {c['text_muted']}; margin-right:10px;
}}
QComboBox QAbstractItemView {{
    background:{c['bg_card']}; border:1px solid {c['border_soft']}; border-radius:10px;
    selection-background-color:{c['accent_dim']}; color:{c['text_primary']}; padding:4px; outline:0;
}}
QComboBox QAbstractItemView::item {{ padding:8px 12px; border-radius:6px; }}

/* ═══ Progress bar ══════════════════════════════════════════════════════ */
QProgressBar {{
    background:{c['bg_hover']}; border:none; border-radius:5px;
    height:6px; color:transparent; text-align:center;
}}
QProgressBar::chunk {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {c['accent']}, stop:0.6 {c['accent_light']}, stop:1 #7EB8FF);
    border-radius:5px;
}}

/* ═══ Labels ════════════════════════════════════════════════════════════ */
QLabel#title {{
    font-size:20px; font-weight:700; color:{c['text_primary']};
    letter-spacing:-0.5px; background:transparent;
}}
QLabel#status_ok   {{ color:{c['success']}; font-weight:600; font-size:12px; background:transparent; }}
QLabel#status_err  {{ color:{c['danger']};  font-weight:600; font-size:12px; background:transparent; }}
QLabel#status_warn {{ color:{c['warning']}; font-weight:600; font-size:12px; background:transparent; }}
QLabel#status_info {{ color:{c['text_muted']}; font-size:12px; background:transparent; }}
QLabel#subtitle    {{ color:{c['text_muted']}; font-size:12px; background:transparent; }}
QLabel#lnk {{ color:{c['accent_light']}; font-size:12px; text-decoration:underline; background:transparent; }}

/* ═══ Drag & Drop zone ══════════════════════════════════════════════════ */
QFrame#drop_zone {{
    background:{c['drop_bg']}; border:2px dashed {c['drop_border']}; border-radius:18px;
}}
/* Activated when a file is dragged over the window */
QFrame#drop_zone[drag_active="true"] {{
    border:2px dashed {c['border_drag_over']};
    background:{c['accent_glow']};
}}

/* ═══ Panels ════════════════════════════════════════════════════════════ */
QFrame#advanced_panel {{ background:{c['bg_panel']}; border:1px solid {c['border']}; border-radius:12px; }}
QFrame#settings_panel {{ background:{c['bg_card']}; border:1px solid {c['border_soft']}; border-radius:14px; }}
QFrame#compress_panel {{ background:{c['bg_panel']}; border:1px solid {c['border_soft']}; border-radius:12px; }}

/* ═══ List widgets ══════════════════════════════════════════════════════ */
QListWidget {{
    background:{c['bg_panel']}; border:1px solid {c['border']}; border-radius:10px;
    padding:4px; color:{c['text_primary']}; font-size:12px; outline:0;
}}
QListWidget::item {{ padding:7px 10px; border-radius:7px; color:{c['text_secondary']}; }}
QListWidget::item:hover {{ background:{c['bg_hover']}; color:{c['text_primary']}; }}
QListWidget::item:selected {{ background:{c['accent_dim']}; color:{c['text_primary']}; }}

/* ═══ GroupBox ══════════════════════════════════════════════════════════ */
QGroupBox {{
    border:1px solid {c['border_soft']}; border-radius:12px; margin-top:16px;
    padding:14px 12px 12px 12px; font-size:11px; font-weight:600;
    color:{c['text_muted']}; letter-spacing:0.5px;
}}
QGroupBox::title {{
    subcontrol-origin:margin; subcontrol-position:top left;
    left:14px; top:-1px; padding:0 6px; background:{c['bg_card']};
}}

/* ═══ Tooltip ═══════════════════════════════════════════════════════════ */
QToolTip {{
    background:{c['bg_hover']}; color:{c['text_primary']};
    border:1px solid {c['border_focus']}; border-radius:7px; padding:6px 10px; font-size:12px;
}}

/* ═══ Checkbox ══════════════════════════════════════════════════════════ */
QCheckBox {{ color:{c['text_secondary']}; spacing:8px; font-size:12px; }}
QCheckBox::indicator {{
    width:16px; height:16px; border-radius:5px;
    border:1.5px solid {c['border_soft']}; background:{c['bg_input']};
}}
QCheckBox::indicator:checked {{ background:{c['accent']}; border-color:{c['accent_light']}; }}
QCheckBox::indicator:hover {{ border-color:{c['accent']}; }}

/* ═══ SpinBox ═══════════════════════════════════════════════════════════ */
QSpinBox {{
    background:{c['bg_input']}; border:1.5px solid {c['border_soft']};
    border-radius:8px; padding:6px 10px; color:{c['text_primary']}; font-size:13px;
}}
QSpinBox:focus {{ border-color:{c['border_focus']}; }}
QSpinBox::up-button, QSpinBox::down-button {{ width:0; }}

/* ═══ Theme selector buttons ════════════════════════════════════════════ */
QPushButton#theme_btn {{
    background:{c['bg_hover']}; color:{c['text_secondary']};
    border:1px solid {c['border_soft']}; border-radius:8px;
    padding:8px 18px; font-size:12px; font-weight:500;
}}
QPushButton#theme_btn:hover {{ background:{c['bg_input']}; color:{c['text_primary']}; }}
QPushButton#theme_btn:checked {{
    background:{c['accent_glow']}; color:{c['accent_light']};
    border-color:{c['accent_dim']}; font-weight:600;
}}
"""


# ── Badge / section helpers ───────────────────────────────────────────────────

def badge_style(kind: str = "info") -> str:
    mapping = {
        "info": (COLORS["bg_hover"],    COLORS["text_muted"]),
        "ok":   (COLORS["success_dim"], COLORS["success"]),
        "warn": (COLORS["warning_dim"], COLORS["warning"]),
        "err":  (COLORS["danger_dim"],  COLORS["danger"]),
    }
    bg, fg = mapping.get(kind, mapping["info"])
    return (
        f"background:{bg}; color:{fg}; border-radius:7px; "
        f"padding:3px 10px; font-size:11px; font-weight:600; letter-spacing:0.3px;"
    )


def section_label_style() -> str:
    return (
        f"font-size:10px; font-weight:700; color:{COLORS['text_muted']}; "
        f"letter-spacing:1.2px; background:transparent;"
    )
