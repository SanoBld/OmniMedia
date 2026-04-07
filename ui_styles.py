"""
ui_styles.py — OmniMedia v4.4
Themes: Dark / OLED / Light / Auto (darkdetect).
v4.4 : Refonte visuelle — bouton primaire solide, tabs épurés,
       séparateurs supprimés, typographie et spacing uniformisés.
"""
from __future__ import annotations
import sys

# ── Palettes ──────────────────────────────────────────────────────────────────

_DARK: dict[str, str] = {
    "bg_deep":          "#090E1A",
    "bg_card":          "#111827",
    "bg_input":         "#19213A",
    "bg_hover":         "#1E2840",
    "bg_panel":         "#131C30",
    "accent":           "#3B7DF8",
    "accent_light":     "#6199FF",
    "accent_glow":      "#1A2D60",
    "accent_dim":       "#1B2E60",
    "accent2":          "#7C5CFF",
    "success":          "#2DD68A",
    "success_dim":      "#0B2820",
    "warning":          "#F5A623",
    "warning_dim":      "#2C1C06",
    "danger":           "#E8445A",
    "danger_dim":       "#2B0910",
    "text_primary":     "#E2EAF8",
    "text_secondary":   "#8A96B8",
    "text_muted":       "#4D5780",
    "border":           "#1C2540",
    "border_soft":      "#242E4C",
    "border_focus":     "#3B7DF8",
    "border_drag_over": "#6199FF",
    "drop_bg":          "#111827",
    "drop_border":      "#2A3558",
    "accent_custom":    "#3B7DF8",
}

_OLED: dict[str, str] = {
    **_DARK,
    "bg_deep":          "#000000",
    "bg_card":          "#060912",
    "bg_input":         "#090E1A",
    "bg_hover":         "#0C1020",
    "bg_panel":         "#040709",
    "border":           "#0C1020",
    "border_soft":      "#141A2E",
    "drop_bg":          "#000000",
    "drop_border":      "#141A2E",
}

_LIGHT: dict[str, str] = {
    "bg_deep":          "#F0F4FC",
    "bg_card":          "#FFFFFF",
    "bg_input":         "#E8EDF8",
    "bg_hover":         "#DDE4F4",
    "bg_panel":         "#EBF0FA",
    "accent":           "#2563EB",
    "accent_light":     "#3B82F6",
    "accent_glow":      "#DBEAFE",
    "accent_dim":       "#BFDBFE",
    "accent2":          "#7C3AED",
    "success":          "#16A34A",
    "success_dim":      "#DCFCE7",
    "warning":          "#D97706",
    "warning_dim":      "#FEF9C3",
    "danger":           "#DC2626",
    "danger_dim":       "#FEE2E2",
    "text_primary":     "#0F172A",
    "text_secondary":   "#334155",
    "text_muted":       "#94A3B8",
    "border":           "#CBD5E1",
    "border_soft":      "#E2E8F0",
    "border_focus":     "#2563EB",
    "border_drag_over": "#3B82F6",
    "drop_bg":          "#F8FAFF",
    "drop_border":      "#CBD5E1",
    "accent_custom":    "#2563EB",
}


# ── System dark-mode detection ────────────────────────────────────────────────

def _detect_system_dark() -> bool:
    try:
        import darkdetect
        return darkdetect.isDark() or False
    except Exception:
        pass
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
    return True


def get_palette(theme: str = "dark") -> dict[str, str]:
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
    c = get_palette(theme)
    COLORS.update(c)

    return f"""
/* ═══ Reset & Global ═══════════════════════════════════════════════════ */
* {{ outline: none; }}
QWidget {{
    background-color: {c['bg_deep']};
    color: {c['text_primary']};
    font-family: "Segoe UI Variable", "Segoe UI", "SF Pro Text", "Helvetica Neue", sans-serif;
    font-size: 13px;
    selection-background-color: {c['accent_dim']};
    selection-color: {c['text_primary']};
}}
QMainWindow, QDialog {{ background-color: {c['bg_deep']}; }}

/* ═══ Scrollbars — ultra-fines ══════════════════════════════════════════ */
QScrollBar:vertical {{
    background: transparent; width: 5px; margin: 4px 0;
}}
QScrollBar::handle:vertical {{
    background: {c['border_soft']}; border-radius: 3px; min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{ background: {c['accent']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent; height: 0;
}}
QScrollBar:horizontal {{ background: transparent; height: 5px; }}
QScrollBar::handle:horizontal {{
    background: {c['border_soft']}; border-radius: 3px;
}}
QScrollBar::handle:horizontal:hover {{ background: {c['accent']}; }}

/* ═══ Tabs ══════════════════════════════════════════════════════════════ */
QTabWidget::pane {{
    border: none;
    background: {c['bg_deep']};
    top: 0;
}}
QTabBar {{
    background: {c['bg_card']};
    border-bottom: 1px solid {c['border_soft']};
}}
QTabBar::tab {{
    background: transparent;
    color: {c['text_muted']};
    padding: 16px 32px;
    margin: 0;
    font-size: 13px;
    font-weight: 500;
    letter-spacing: 0.1px;
    border-bottom: 2px solid transparent;
    min-width: 90px;
}}
QTabBar::tab:selected {{
    color: {c['accent_light']};
    border-bottom: 2px solid {c['accent']};
    font-weight: 700;
    background: transparent;
}}
QTabBar::tab:hover:!selected {{
    color: {c['text_secondary']};
    background: {c['bg_hover']};
    border-bottom: 2px solid {c['border_soft']};
}}

/* ═══ Cards / Frames ════════════════════════════════════════════════════ */
QFrame#card {{
    background: {c['bg_card']};
    border: 1px solid {c['border']};
    border-radius: 15px;
}}
QFrame#card_inner {{
    background: {c['bg_panel']};
    border: 1px solid {c['border']};
    border-radius: 12px;
}}
QFrame#settings_card {{
    background: {c['bg_card']};
    border: 1px solid {c['border']};
    border-radius: 15px;
}}
QFrame#settings_card_accent {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {c['bg_card']}, stop:1 {c['accent_glow']});
    border: 1px solid {c['accent_dim']};
    border-radius: 15px;
}}

/* ═══ Text inputs ═══════════════════════════════════════════════════════ */
QLineEdit {{
    background: {c['bg_input']};
    border: 1.5px solid {c['border_soft']};
    border-radius: 12px;
    padding: 11px 16px;
    color: {c['text_primary']};
    font-size: 13px;
    min-height: 20px;
}}
QLineEdit:focus {{
    border: 2px solid {c['border_focus']};
    background: {c['bg_hover']};
}}
QLineEdit:disabled {{
    background: {c['bg_panel']};
    color: {c['text_muted']};
    border-color: {c['border']};
}}

/* ═══ PRIMARY button — Bleu solide ══════════════════════════════════════ */
QPushButton {{
    background: {c['accent']};
    color: #FFFFFF;
    border: none;
    border-radius: 12px;
    padding: 11px 28px;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.1px;
}}
QPushButton:hover {{
    background: {c['accent_light']};
}}
QPushButton:pressed {{
    background: {c['accent_dim']};
    padding-top: 12px;
    padding-bottom: 10px;
}}
QPushButton:disabled {{
    background: {c['bg_hover']};
    color: {c['text_muted']};
    border: none;
}}

/* Secondary */
QPushButton#btn_secondary {{
    background: transparent;
    color: {c['text_secondary']};
    border: 1.5px solid {c['border_soft']};
    font-weight: 500;
    border-radius: 10px;
    padding: 8px 18px;
}}
QPushButton#btn_secondary:hover {{
    background: {c['bg_hover']};
    color: {c['text_primary']};
    border-color: {c['border_focus']};
}}
QPushButton#btn_secondary:pressed {{ background: {c['bg_panel']}; }}
QPushButton#btn_secondary:disabled {{
    background: transparent;
    color: {c['text_muted']};
    border-color: {c['border']};
}}

/* Tray minimize */
QPushButton#btn_tray_minimize {{
    background: transparent;
    color: {c['text_muted']};
    border: 1.5px solid {c['border_soft']};
    font-weight: 500;
    border-radius: 10px;
    padding: 7px 14px;
    font-size: 12px;
}}
QPushButton#btn_tray_minimize:hover {{
    background: {c['accent_glow']};
    color: {c['accent_light']};
    border-color: {c['accent_dim']};
}}

/* Success */
QPushButton#btn_success {{
    background: {c['success']};
    color: #071A10;
    font-weight: 700;
    border-radius: 12px;
    padding: 11px 26px;
}}
QPushButton#btn_success:hover {{
    background: #3DE89A;
}}

/* Danger */
QPushButton#btn_danger {{
    background: {c['danger_dim']};
    color: {c['danger']};
    border: 1.5px solid {c['danger']}33;
    font-weight: 600;
    border-radius: 10px;
    padding: 8px 18px;
}}
QPushButton#btn_danger:hover {{ background: {c['danger']}; color: #fff; border: none; }}

/* Advanced toggle */
QPushButton#btn_advanced {{
    background: transparent;
    color: {c['text_muted']};
    border: 1.5px solid {c['border']};
    border-radius: 8px;
    padding: 7px 16px;
    font-size: 12px;
    font-weight: 500;
}}
QPushButton#btn_advanced:hover {{
    background: {c['bg_hover']};
    color: {c['text_secondary']};
    border-color: {c['border_soft']};
}}
QPushButton#btn_advanced:checked {{
    color: {c['accent_light']};
    border-color: {c['accent_dim']};
    background: {c['accent_glow']};
}}

/* ═══ Radio buttons ═════════════════════════════════════════════════════ */
QRadioButton {{ color: {c['text_secondary']}; spacing: 10px; font-size: 13px; }}
QRadioButton:hover {{ color: {c['text_primary']}; }}
QRadioButton::indicator {{
    width: 18px; height: 18px; border-radius: 9px;
    border: 2px solid {c['border_soft']}; background: {c['bg_input']};
}}
QRadioButton::indicator:checked {{
    background: {c['accent']};
    border: 2px solid {c['accent_light']};
}}
QRadioButton::indicator:hover {{ border: 2px solid {c['accent']}; }}

/* ═══ ComboBox ══════════════════════════════════════════════════════════ */
QComboBox {{
    background: {c['bg_input']};
    border: 1.5px solid {c['border_soft']};
    border-radius: 12px;
    padding: 10px 38px 10px 16px;
    color: {c['text_primary']};
    font-size: 13px;
}}
QComboBox:focus, QComboBox:hover {{
    border-color: {c['border_focus']};
    background: {c['bg_hover']};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 36px;
    border: none;
}}
QComboBox::down-arrow {{
    image: none; width: 0; height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {c['text_muted']};
    margin-right: 12px;
}}
QComboBox QAbstractItemView {{
    background: {c['bg_card']};
    border: 1px solid {c['border_soft']};
    border-radius: 12px;
    selection-background-color: {c['accent_dim']};
    color: {c['text_primary']};
    padding: 6px;
    outline: 0;
}}
QComboBox QAbstractItemView::item {{ padding: 10px 14px; border-radius: 8px; }}

/* ═══ Progress bar — fine néon ═══════════════════════════════════════════ */
QProgressBar {{
    background: {c['bg_hover']};
    border: none;
    border-radius: 4px;
    height: 5px;
    color: transparent;
    text-align: center;
    max-height: 5px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {c['accent']}, stop:0.6 {c['accent_light']}, stop:1 #A0C4FF);
    border-radius: 4px;
}}

/* ═══ Labels ════════════════════════════════════════════════════════════ */
QLabel#title {{
    font-size: 20px;
    font-weight: 700;
    color: {c['text_primary']};
    letter-spacing: -0.5px;
    background: transparent;
}}
QLabel#status_ok   {{ color: {c['success']};  font-weight: 600; font-size: 12px; background: transparent; }}
QLabel#status_err  {{ color: {c['danger']};   font-weight: 600; font-size: 12px; background: transparent; }}
QLabel#status_warn {{ color: {c['warning']};  font-weight: 600; font-size: 12px; background: transparent; }}
QLabel#status_info {{ color: {c['text_muted']}; font-size: 12px; background: transparent; }}
QLabel#subtitle    {{ color: {c['text_muted']}; font-size: 12px; background: transparent; }}
QLabel#lnk {{
    color: {c['accent_light']};
    font-size: 12px;
    text-decoration: underline;
    background: transparent;
}}
QLabel#card_section_title {{
    font-size: 15px;
    font-weight: 700;
    color: {c['text_primary']};
    background: transparent;
}}
QLabel#card_section_icon {{
    font-size: 18px;
    background: transparent;
}}

/* ═══ Drag & Drop zone ══════════════════════════════════════════════════ */
QFrame#drop_zone {{
    background: {c['drop_bg']};
    border: 2px dashed {c['drop_border']};
    border-radius: 20px;
    min-height: 130px;
}}
QFrame#drop_zone[drag_active="true"] {{
    border: 2px dashed {c['border_drag_over']};
    background: {c['accent_glow']};
}}

/* ═══ Panneaux ══════════════════════════════════════════════════════════ */
QFrame#advanced_panel {{
    background: {c['bg_panel']};
    border: 1px solid {c['border']};
    border-radius: 14px;
}}
QFrame#settings_panel {{
    background: {c['bg_card']};
    border: 1px solid {c['border_soft']};
    border-radius: 16px;
}}
QFrame#compress_panel {{
    background: {c['bg_panel']};
    border: 1px solid {c['border_soft']};
    border-radius: 14px;
}}

/* ═══ Barre comparative Compressor ══════════════════════════════════════ */
QFrame#compare_bar_bg {{
    background: {c['bg_hover']};
    border-radius: 6px;
    border: none;
}}
QFrame#compare_bar_fill {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {c['accent']}, stop:1 {c['accent_light']});
    border-radius: 6px;
    border: none;
}}

/* ═══ Badges qualité compression ════════════════════════════════════════ */
QLabel#badge_optimal {{
    background: {c['success_dim']}; color: {c['success']};
    border-radius: 8px; padding: 4px 12px;
    font-size: 11px; font-weight: 700; letter-spacing: 0.4px;
}}
QLabel#badge_warn {{
    background: {c['warning_dim']}; color: {c['warning']};
    border-radius: 8px; padding: 4px 12px;
    font-size: 11px; font-weight: 700; letter-spacing: 0.4px;
}}
QLabel#badge_danger {{
    background: {c['danger_dim']}; color: {c['danger']};
    border-radius: 8px; padding: 4px 12px;
    font-size: 11px; font-weight: 700; letter-spacing: 0.4px;
}}

/* ═══ Dashboard stats bar ════════════════════════════════════════════════ */
QFrame#stats_bar {{
    background: {c['bg_card']};
    border-top: 1px solid {c['border_soft']};
    border-radius: 0;
}}
QLabel#stat_value {{
    font-size: 17px; font-weight: 700;
    color: {c['accent_light']}; background: transparent;
}}
QLabel#stat_label {{
    font-size: 10px; font-weight: 600; color: {c['text_muted']};
    background: transparent; letter-spacing: 0.6px;
}}

/* ═══ List widgets ══════════════════════════════════════════════════════ */
QListWidget {{
    background: {c['bg_panel']};
    border: 1px solid {c['border']};
    border-radius: 12px;
    padding: 6px;
    color: {c['text_primary']};
    font-size: 12px;
    outline: 0;
}}
QListWidget::item {{
    padding: 9px 12px;
    border-radius: 8px;
    color: {c['text_secondary']};
}}
QListWidget::item:hover {{ background: {c['bg_hover']}; color: {c['text_primary']}; }}
QListWidget::item:selected {{ background: {c['accent_dim']}; color: {c['text_primary']}; }}

/* ═══ GroupBox ══════════════════════════════════════════════════════════ */
QGroupBox {{
    border: 1px solid {c['border_soft']};
    border-radius: 14px;
    margin-top: 18px;
    padding: 16px 14px 14px 14px;
    font-size: 11px; font-weight: 700;
    color: {c['text_muted']}; letter-spacing: 0.5px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 16px; top: -1px; padding: 0 8px;
    background: {c['bg_card']};
}}

/* ═══ Tooltip ═══════════════════════════════════════════════════════════ */
QToolTip {{
    background: {c['bg_hover']};
    color: {c['text_primary']};
    border: 1px solid {c['border_focus']};
    border-radius: 10px;
    padding: 8px 12px;
    font-size: 12px;
}}

/* ═══ Toggle Switch ══════════════════════════════════════════════════════ */
QCheckBox {{
    color: {c['text_secondary']}; spacing: 12px; font-size: 13px;
}}
QCheckBox::indicator {{
    width: 17px; height: 17px; border-radius: 5px;
    border: 1.5px solid {c['border_soft']}; background: {c['bg_input']};
}}
QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent_light']}; }}
QCheckBox::indicator:hover {{ border-color: {c['accent']}; }}

QCheckBox#toggle_switch {{
    color: {c['text_primary']}; spacing: 14px; font-size: 13px;
}}
QCheckBox#toggle_switch::indicator {{
    width: 42px; height: 23px; border-radius: 12px;
    border: none; background: {c['border_soft']};
}}
QCheckBox#toggle_switch::indicator:checked {{
    background: {c['accent']};
}}
QCheckBox#toggle_switch::indicator:hover {{
    border: 2px solid {c['accent']};
}}

/* ═══ SpinBox ═══════════════════════════════════════════════════════════ */
QSpinBox {{
    background: {c['bg_input']};
    border: 1.5px solid {c['border_soft']};
    border-radius: 10px;
    padding: 8px 12px;
    color: {c['text_primary']};
    font-size: 13px;
}}
QSpinBox:focus {{ border-color: {c['border_focus']}; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; }}

/* ═══ Slider ════════════════════════════════════════════════════════════ */
QSlider::groove:horizontal {{
    background: {c['bg_hover']}; height: 5px; border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {c['accent']}; width: 18px; height: 18px;
    border-radius: 9px; margin: -7px 0; border: 2px solid {c['bg_deep']};
}}
QSlider::handle:horizontal:hover {{ background: {c['accent_light']}; }}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {c['accent']}, stop:1 {c['accent_light']});
    border-radius: 3px;
}}

/* ═══ Boutons thème (aperçu) ════════════════════════════════════════════ */
QPushButton#theme_btn {{
    background: {c['bg_hover']};
    color: {c['text_secondary']};
    border: 1.5px solid {c['border_soft']};
    border-radius: 10px;
    padding: 9px 20px;
    font-size: 12px;
    font-weight: 500;
    text-align: left;
}}
QPushButton#theme_btn:hover {{
    background: {c['bg_input']};
    color: {c['text_primary']};
    border-color: {c['border_focus']};
}}
QPushButton#theme_btn:checked {{
    background: {c['accent_glow']};
    color: {c['accent_light']};
    border: 2px solid {c['accent']};
    font-weight: 700;
}}

QPushButton#theme_preview_dark {{
    background: #111827; border: 2px solid {c['border_soft']};
    border-radius: 12px; min-width: 92px; min-height: 54px;
    color: #DCE4F5; font-size: 11px; font-weight: 600; padding: 4px 8px;
}}
QPushButton#theme_preview_dark:checked {{ border: 2px solid {c['accent']}; }}
QPushButton#theme_preview_oled {{
    background: #000000; border: 2px solid {c['border_soft']};
    border-radius: 12px; min-width: 92px; min-height: 54px;
    color: #666; font-size: 11px; font-weight: 600; padding: 4px 8px;
}}
QPushButton#theme_preview_oled:checked {{ border: 2px solid {c['accent']}; }}
QPushButton#theme_preview_light {{
    background: #F0F4FC; border: 2px solid {c['border_soft']};
    border-radius: 12px; min-width: 92px; min-height: 54px;
    color: #0F172A; font-size: 11px; font-weight: 600; padding: 4px 8px;
}}
QPushButton#theme_preview_light:checked {{ border: 2px solid {c['accent']}; }}
QPushButton#theme_preview_auto {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #111827, stop:1 #F0F4FC);
    border: 2px solid {c['border_soft']};
    border-radius: 12px; min-width: 92px; min-height: 54px;
    color: {c['accent_light']}; font-size: 11px; font-weight: 600; padding: 4px 8px;
}}
QPushButton#theme_preview_auto:checked {{ border: 2px solid {c['accent']}; }}

/* ═══ Pastille statut FFmpeg ═════════════════════════════════════════════ */
QLabel#ffmpeg_dot_ok {{
    background: {c['success']}; border-radius: 5px;
    min-width: 10px; max-width: 10px; min-height: 10px; max-height: 10px;
}}
QLabel#ffmpeg_dot_err {{
    background: {c['danger']}; border-radius: 5px;
    min-width: 10px; max-width: 10px; min-height: 10px; max-height: 10px;
}}
QLabel#ffmpeg_dot_warn {{
    background: {c['warning']}; border-radius: 5px;
    min-width: 10px; max-width: 10px; min-height: 10px; max-height: 10px;
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
        f"background:{bg}; color:{fg}; border-radius:8px; "
        f"padding:3px 11px; font-size:11px; font-weight:700; letter-spacing:0.2px;"
    )


def section_label_style() -> str:
    return (
        f"font-size:10px; font-weight:700; color:{COLORS['text_muted']}; "
        f"letter-spacing:1.0px; background:transparent;"
    )


def card_title_style() -> str:
    return (
        f"font-size:15px; font-weight:700; color:{COLORS['text_primary']}; background:transparent;"
    )


def toggle_switch_style() -> str:
    return ""  # Style déjà dans la feuille globale via #toggle_switch


def compression_badge_style(kind: str = "optimal") -> str:
    mapping = {
        "optimal": (COLORS["success_dim"], COLORS["success"]),
        "warn":    (COLORS["warning_dim"], COLORS["warning"]),
        "danger":  (COLORS["danger_dim"],  COLORS["danger"]),
    }
    bg, fg = mapping.get(kind, mapping["optimal"])
    return (
        f"background:{bg}; color:{fg}; border-radius:8px; padding:4px 12px; "
        f"font-size:11px; font-weight:700; letter-spacing:0.4px;"
    )
