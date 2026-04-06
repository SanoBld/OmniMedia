"""
ui_styles.py — OmniMedia v4.2
Themes: Dark / OLED / Light / Auto (darkdetect).
Modernisation : dégradés sur boutons, progressbars fines néon, toggle switches,
                cartes settings, boutons thème avec aperçu couleur.
"""
from __future__ import annotations
import sys

# ── Palettes ──────────────────────────────────────────────────────────────────

_DARK: dict[str, str] = {
    "bg_deep":          "#080C12",
    "bg_card":          "#0F1320",
    "bg_input":         "#161B2C",
    "bg_hover":         "#1C2235",
    "bg_panel":         "#111522",
    "accent":           "#3B7DF8",
    "accent_light":     "#5A96FF",
    "accent_glow":      "#172047",
    "accent_dim":       "#1B2E60",
    "accent2":          "#7C5CFF",    # couleur d'accentuation secondaire (violet)
    "success":          "#2DD68A",
    "success_dim":      "#0B2820",
    "warning":          "#F5A623",
    "warning_dim":      "#2C1C06",
    "danger":           "#E8445A",
    "danger_dim":       "#2B0910",
    "text_primary":     "#DCE4F5",
    "text_secondary":   "#8A93AD",
    "text_muted":       "#50587A",
    "border":           "#1C2235",
    "border_soft":      "#232B42",
    "border_focus":     "#3B7DF8",
    "border_drag_over": "#5A96FF",
    "drop_bg":          "#0E1220",
    "drop_border":      "#232B42",
    # Couleur d'accentuation personnalisable (variable globale)
    "accent_custom":    "#3B7DF8",
}

_OLED: dict[str, str] = {
    **_DARK,
    "bg_deep":          "#000000",
    "bg_card":          "#060810",
    "bg_input":         "#090C14",
    "bg_hover":         "#0C0F18",
    "bg_panel":         "#040509",
    "border":           "#0C0F18",
    "border_soft":      "#111520",
    "drop_bg":          "#000000",
    "drop_border":      "#111520",
}

_LIGHT: dict[str, str] = {
    "bg_deep":          "#F2F5FB",
    "bg_card":          "#FFFFFF",
    "bg_input":         "#EBEEf7",
    "bg_hover":         "#E2E7F3",
    "bg_panel":         "#EDF0F8",
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

    # Détermine si on est en mode clair pour inverser certaines couleurs
    is_light = theme == "light"
    btn_gradient_stop1 = c['accent']
    btn_gradient_stop2 = c['accent2']

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

/* ═══ Scrollbars ════════════════════════════════════════════════════════ */
QScrollBar:vertical {{ background: transparent; width: 4px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {c['border_soft']}; border-radius: 2px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {c['accent']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent; height: 0;
}}
QScrollBar:horizontal {{ background: transparent; height: 4px; }}
QScrollBar::handle:horizontal {{
    background: {c['border_soft']}; border-radius: 2px;
}}
QScrollBar::handle:horizontal:hover {{ background: {c['accent']}; }}

/* ═══ Tabs ══════════════════════════════════════════════════════════════ */
QTabWidget::pane {{
    border: 1px solid {c['border_soft']}; border-radius: 0;
    background: {c['bg_deep']}; top: -1px;
}}
QTabBar {{ background: {c['bg_panel']}; border-bottom: 1px solid {c['border_soft']}; }}
QTabBar::tab {{
    background: transparent; color: {c['text_muted']};
    padding: 13px 28px; margin: 0; font-size: 13px; font-weight: 500;
    letter-spacing: 0.2px; border-bottom: 2px solid transparent;
    min-width: 80px;
}}
QTabBar::tab:selected {{
    color: {c['text_primary']}; border-bottom: 2px solid {c['accent']};
    font-weight: 600;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 transparent, stop:1 {c['accent_glow']});
}}
QTabBar::tab:hover:!selected {{
    color: {c['text_secondary']}; border-bottom: 2px solid {c['border_soft']};
    background: {c['bg_hover']};
}}

/* ═══ Cards / Frames ════════════════════════════════════════════════════ */
QFrame#card {{
    background: {c['bg_card']}; border: 1px solid {c['border_soft']}; border-radius: 16px;
}}
QFrame#card_inner {{
    background: {c['bg_panel']}; border: 1px solid {c['border']}; border-radius: 10px;
}}
/* Carte settings avec padding et effet glassmorphisme léger */
QFrame#settings_card {{
    background: {c['bg_card']}; border: 1px solid {c['border_soft']}; border-radius: 14px;
}}
QFrame#settings_card_accent {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {c['bg_card']}, stop:1 {c['accent_glow']});
    border: 1px solid {c['accent_dim']}; border-radius: 14px;
}}

/* ═══ Text inputs ═══════════════════════════════════════════════════════ */
QLineEdit {{
    background: {c['bg_input']}; border: 1.5px solid {c['border_soft']};
    border-radius: 10px; padding: 10px 14px;
    color: {c['text_primary']}; font-size: 13px;
}}
QLineEdit:focus {{
    border: 1.5px solid {c['border_focus']}; background: {c['bg_hover']};
}}
QLineEdit:disabled {{
    background: {c['bg_panel']}; color: {c['text_muted']}; border-color: {c['border']};
}}

/* ═══ PRIMARY buttons — dégradé + bord arrondi 12px ════════════════════ */
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {btn_gradient_stop1}, stop:1 {btn_gradient_stop2});
    color: #FFFFFF; border: none; border-radius: 12px;
    padding: 10px 22px; font-size: 13px; font-weight: 600; letter-spacing: 0.2px;
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {c['accent_light']}, stop:1 #9B7CFF);
}}
QPushButton:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {c['accent_dim']}, stop:1 {c['accent_glow']});
    padding-top: 11px; padding-bottom: 9px;
}}
QPushButton:disabled {{
    background: {c['bg_hover']}; color: {c['text_muted']}; border: none;
}}

/* Secondary */
QPushButton#btn_secondary {{
    background: {c['bg_hover']}; color: {c['text_secondary']};
    border: 1px solid {c['border_soft']}; font-weight: 500; border-radius: 10px;
}}
QPushButton#btn_secondary:hover {{
    background: {c['bg_input']}; color: {c['text_primary']};
    border-color: {c['border_focus']};
}}
QPushButton#btn_secondary:pressed {{ background: {c['bg_panel']}; }}

/* Success */
QPushButton#btn_success {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {c['success']}, stop:1 #22D3A5);
    color: #071A10; font-weight: 700; border-radius: 12px;
}}
QPushButton#btn_success:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {c['accent_light']}, stop:1 #22D3A5);
}}

/* Danger */
QPushButton#btn_danger {{
    background: {c['danger_dim']}; color: {c['danger']};
    border: 1px solid {c['danger']}; font-weight: 600; border-radius: 10px;
}}
QPushButton#btn_danger:hover {{ background: {c['danger']}; color: #fff; border: none; }}

/* Advanced toggle (petit) */
QPushButton#btn_advanced {{
    background: transparent; color: {c['text_muted']};
    border: 1px solid {c['border']}; border-radius: 8px;
    padding: 6px 14px; font-size: 12px; font-weight: 500;
}}
QPushButton#btn_advanced:hover {{
    background: {c['bg_hover']}; color: {c['text_secondary']};
    border-color: {c['border_soft']};
}}
QPushButton#btn_advanced:checked {{
    color: {c['accent_light']}; border-color: {c['accent_dim']};
    background: {c['accent_glow']};
}}

/* ═══ Radio buttons ═════════════════════════════════════════════════════ */
QRadioButton {{ color: {c['text_secondary']}; spacing: 9px; font-size: 13px; }}
QRadioButton:hover {{ color: {c['text_primary']}; }}
QRadioButton::indicator {{
    width: 17px; height: 17px; border-radius: 9px;
    border: 2px solid {c['border_soft']}; background: {c['bg_input']};
}}
QRadioButton::indicator:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {c['accent']}, stop:1 {c['accent2']});
    border: 2px solid {c['accent_light']};
}}
QRadioButton::indicator:hover {{ border: 2px solid {c['accent']}; }}

/* ═══ ComboBox ══════════════════════════════════════════════════════════ */
QComboBox {{
    background: {c['bg_input']}; border: 1.5px solid {c['border_soft']};
    border-radius: 10px; padding: 8px 36px 8px 14px;
    color: {c['text_primary']}; font-size: 13px;
}}
QComboBox:focus, QComboBox:hover {{
    border-color: {c['border_focus']}; background: {c['bg_hover']};
}}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 32px; border: none; }}
QComboBox::down-arrow {{
    image: none; width: 0; height: 0;
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid {c['text_muted']}; margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background: {c['bg_card']}; border: 1px solid {c['border_soft']};
    border-radius: 10px; selection-background-color: {c['accent_dim']};
    color: {c['text_primary']}; padding: 4px; outline: 0;
}}
QComboBox QAbstractItemView::item {{ padding: 8px 12px; border-radius: 6px; }}

/* ═══ Progress bar — fine, néon ══════════════════════════════════════════ */
QProgressBar {{
    background: {c['bg_hover']}; border: none; border-radius: 3px;
    height: 4px; color: transparent; text-align: center;
    max-height: 4px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {c['accent']}, stop:0.5 {c['accent_light']}, stop:1 #A0C4FF);
    border-radius: 3px;
}}

/* ═══ Labels ════════════════════════════════════════════════════════════ */
QLabel#title {{
    font-size: 20px; font-weight: 700; color: {c['text_primary']};
    letter-spacing: -0.5px; background: transparent;
}}
QLabel#status_ok   {{ color: {c['success']}; font-weight: 600; font-size: 12px; background: transparent; }}
QLabel#status_err  {{ color: {c['danger']};  font-weight: 600; font-size: 12px; background: transparent; }}
QLabel#status_warn {{ color: {c['warning']}; font-weight: 600; font-size: 12px; background: transparent; }}
QLabel#status_info {{ color: {c['text_muted']}; font-size: 12px; background: transparent; }}
QLabel#subtitle    {{ color: {c['text_muted']}; font-size: 12px; background: transparent; }}
QLabel#lnk {{ color: {c['accent_light']}; font-size: 12px; text-decoration: underline; background: transparent; }}

/* Section headers dans les cartes settings */
QLabel#card_section_title {{
    font-size: 14px; font-weight: 600; color: {c['text_primary']}; background: transparent;
}}
QLabel#card_section_icon {{
    font-size: 18px; background: transparent;
}}

/* ═══ Drag & Drop zone ══════════════════════════════════════════════════ */
QFrame#drop_zone {{
    background: {c['drop_bg']}; border: 2px dashed {c['drop_border']}; border-radius: 18px;
}}
QFrame#drop_zone[drag_active="true"] {{
    border: 2px dashed {c['border_drag_over']};
    background: {c['accent_glow']};
}}

/* ═══ Panneau avancé ════════════════════════════════════════════════════ */
QFrame#advanced_panel {{ background: {c['bg_panel']}; border: 1px solid {c['border']}; border-radius: 12px; }}
QFrame#settings_panel {{ background: {c['bg_card']}; border: 1px solid {c['border_soft']}; border-radius: 14px; }}
QFrame#compress_panel {{ background: {c['bg_panel']}; border: 1px solid {c['border_soft']}; border-radius: 12px; }}

/* ═══ Barre comparative Compressor ══════════════════════════════════════ */
QFrame#compare_bar_bg {{
    background: {c['bg_hover']}; border-radius: 6px; border: none;
}}
QFrame#compare_bar_fill {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {c['accent']}, stop:1 {c['accent_light']});
    border-radius: 6px; border: none;
}}

/* ═══ Badges de qualité compression ═════════════════════════════════════ */
QLabel#badge_optimal {{
    background: {c['success_dim']}; color: {c['success']};
    border-radius: 8px; padding: 4px 12px;
    font-size: 11px; font-weight: 700; letter-spacing: 0.5px;
}}
QLabel#badge_warn {{
    background: {c['warning_dim']}; color: {c['warning']};
    border-radius: 8px; padding: 4px 12px;
    font-size: 11px; font-weight: 700; letter-spacing: 0.5px;
}}
QLabel#badge_danger {{
    background: {c['danger_dim']}; color: {c['danger']};
    border-radius: 8px; padding: 4px 12px;
    font-size: 11px; font-weight: 700; letter-spacing: 0.5px;
}}

/* ═══ Dashboard stats bar ════════════════════════════════════════════════ */
QFrame#stats_bar {{
    background: {c['bg_card']}; border-top: 1px solid {c['border_soft']};
    border-radius: 0;
}}
QLabel#stat_value {{
    font-size: 16px; font-weight: 700; color: {c['accent_light']}; background: transparent;
}}
QLabel#stat_label {{
    font-size: 10px; font-weight: 500; color: {c['text_muted']};
    background: transparent; letter-spacing: 0.8px;
}}

/* ═══ List widgets ══════════════════════════════════════════════════════ */
QListWidget {{
    background: {c['bg_panel']}; border: 1px solid {c['border']}; border-radius: 10px;
    padding: 4px; color: {c['text_primary']}; font-size: 12px; outline: 0;
}}
QListWidget::item {{ padding: 7px 10px; border-radius: 7px; color: {c['text_secondary']}; }}
QListWidget::item:hover {{ background: {c['bg_hover']}; color: {c['text_primary']}; }}
QListWidget::item:selected {{ background: {c['accent_dim']}; color: {c['text_primary']}; }}

/* ═══ GroupBox ══════════════════════════════════════════════════════════ */
QGroupBox {{
    border: 1px solid {c['border_soft']}; border-radius: 12px; margin-top: 16px;
    padding: 14px 12px 12px 12px; font-size: 11px; font-weight: 600;
    color: {c['text_muted']}; letter-spacing: 0.5px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 14px; top: -1px; padding: 0 6px; background: {c['bg_card']};
}}

/* ═══ Tooltip ═══════════════════════════════════════════════════════════ */
QToolTip {{
    background: {c['bg_hover']}; color: {c['text_primary']};
    border: 1px solid {c['border_focus']}; border-radius: 8px;
    padding: 6px 10px; font-size: 12px;
}}

/* ═══ Toggle Switch (QCheckBox stylisé) ══════════════════════════════════
   Utilisez setObjectName("toggle_switch") pour activer ce style.
   La piste fait 36×20px, le curseur 16×16px.
═══════════════════════════════════════════════════════════════════════ */
QCheckBox {{
    color: {c['text_secondary']}; spacing: 10px; font-size: 13px;
}}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 5px;
    border: 1.5px solid {c['border_soft']}; background: {c['bg_input']};
}}
QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent_light']}; }}
QCheckBox::indicator:hover {{ border-color: {c['accent']}; }}

/* Toggle switch moderne (piste coulissante) */
QCheckBox#toggle_switch {{
    color: {c['text_primary']}; spacing: 12px; font-size: 13px;
}}
QCheckBox#toggle_switch::indicator {{
    width: 40px; height: 22px; border-radius: 11px;
    border: none;
    background: {c['border_soft']};
    image: none;
}}
QCheckBox#toggle_switch::indicator:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {c['accent']}, stop:1 {c['accent2']});
}}
QCheckBox#toggle_switch::indicator:hover {{
    border: 2px solid {c['accent']};
}}

/* ═══ SpinBox ═══════════════════════════════════════════════════════════ */
QSpinBox {{
    background: {c['bg_input']}; border: 1.5px solid {c['border_soft']};
    border-radius: 8px; padding: 6px 10px; color: {c['text_primary']}; font-size: 13px;
}}
QSpinBox:focus {{ border-color: {c['border_focus']}; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; }}

/* ═══ Boutons sélecteur de thème (avec aperçu couleur) ═══════════════════ */
QPushButton#theme_btn {{
    background: {c['bg_hover']}; color: {c['text_secondary']};
    border: 1px solid {c['border_soft']}; border-radius: 10px;
    padding: 8px 18px; font-size: 12px; font-weight: 500;
    text-align: left;
}}
QPushButton#theme_btn:hover {{
    background: {c['bg_input']}; color: {c['text_primary']};
    border-color: {c['border_focus']};
}}
QPushButton#theme_btn:checked {{
    background: {c['accent_glow']}; color: {c['accent_light']};
    border: 2px solid {c['accent']}; font-weight: 600;
}}

/* Bouton pastille couleur thème (carré coloré) */
QPushButton#theme_preview_dark {{
    background: #0F1320; border: 2px solid {c['border_soft']};
    border-radius: 10px; min-width: 90px; min-height: 50px;
    color: #DCE4F5; font-size: 11px; font-weight: 600; padding: 4px 8px;
}}
QPushButton#theme_preview_dark:checked {{
    border: 2px solid {c['accent']};
}}
QPushButton#theme_preview_oled {{
    background: #000000; border: 2px solid {c['border_soft']};
    border-radius: 10px; min-width: 90px; min-height: 50px;
    color: #888; font-size: 11px; font-weight: 600; padding: 4px 8px;
}}
QPushButton#theme_preview_oled:checked {{
    border: 2px solid {c['accent']};
}}
QPushButton#theme_preview_light {{
    background: #F2F5FB; border: 2px solid {c['border_soft']};
    border-radius: 10px; min-width: 90px; min-height: 50px;
    color: #0F172A; font-size: 11px; font-weight: 600; padding: 4px 8px;
}}
QPushButton#theme_preview_light:checked {{
    border: 2px solid {c['accent']};
}}
QPushButton#theme_preview_auto {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #0F1320, stop:1 #F2F5FB);
    border: 2px solid {c['border_soft']};
    border-radius: 10px; min-width: 90px; min-height: 50px;
    color: {c['accent_light']}; font-size: 11px; font-weight: 600; padding: 4px 8px;
}}
QPushButton#theme_preview_auto:checked {{
    border: 2px solid {c['accent']};
}}

/* ═══ Pastille de statut FFmpeg ══════════════════════════════════════════ */
QLabel#ffmpeg_dot_ok {{
    background: {c['success']}; border-radius: 6px;
    min-width: 12px; max-width: 12px; min-height: 12px; max-height: 12px;
}}
QLabel#ffmpeg_dot_err {{
    background: {c['danger']}; border-radius: 6px;
    min-width: 12px; max-width: 12px; min-height: 12px; max-height: 12px;
}}
QLabel#ffmpeg_dot_warn {{
    background: {c['warning']}; border-radius: 6px;
    min-width: 12px; max-width: 12px; min-height: 12px; max-height: 12px;
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
        f"padding:3px 10px; font-size:11px; font-weight:600; letter-spacing:0.3px;"
    )


def section_label_style() -> str:
    return (
        f"font-size:10px; font-weight:700; color:{COLORS['text_muted']}; "
        f"letter-spacing:1.2px; background:transparent;"
    )


def card_title_style() -> str:
    """Style pour les titres de sections dans les cartes Settings."""
    return (
        f"font-size:14px; font-weight:600; color:{COLORS['text_primary']}; background:transparent;"
    )


def toggle_switch_style() -> str:
    """
    Style inline pour un QCheckBox toggle switch.
    À combiner avec setObjectName('toggle_switch').
    """
    return ""  # Le style est déjà dans la feuille globale via #toggle_switch


def compression_badge_style(kind: str = "optimal") -> str:
    """Retourne le style inline pour le badge de qualité du compresseur."""
    mapping = {
        "optimal": (COLORS["success_dim"], COLORS["success"]),
        "warn":    (COLORS["warning_dim"], COLORS["warning"]),
        "danger":  (COLORS["danger_dim"],  COLORS["danger"]),
    }
    bg, fg = mapping.get(kind, mapping["optimal"])
    return (
        f"background:{bg}; color:{fg}; border-radius:8px; padding:4px 12px; "
        f"font-size:11px; font-weight:700; letter-spacing:0.5px;"
    )
