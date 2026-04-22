"""
ui_styles.py — OmniMedia v5.0
Thèmes : Dark / OLED / Light / Auto / System (couleur d'accent du PC).
v5.0 :
  - text_muted amélioré (#4D5780 → #6A789A) — meilleur contraste WCAG
  - État :pressed sur tous les boutons — retour tactile satisfaisant
  - Halo glow discret sur le bouton principal au :hover
  - Barre de progression "pill" (6px max-height, border-radius 3px)
  - Séparateurs OLED adoucis — évitent l'éblouissement
  - RadioButton stylisé (cohérence avec les CheckBox)
  - Badges : fonds *_dim systématiques
  - section_label_style couleur relevée à text_muted
"""
from __future__ import annotations
import sys


# ══════════════════════════════════════════════════════════════════════════════
#  Détection de la couleur d'accent système
# ══════════════════════════════════════════════════════════════════════════════

def get_system_accent_color() -> str | None:
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM")
            val, _ = winreg.QueryValueEx(key, "AccentColor")
            abgr = int(val) & 0xFFFFFFFF
            r, g, b = abgr & 0xFF, (abgr >> 8) & 0xFF, (abgr >> 16) & 0xFF
            if r + g + b > 80:
                return f"#{r:02X}{g:02X}{b:02X}"
        except Exception:
            pass
    elif sys.platform == "darwin":
        try:
            import subprocess
            r = subprocess.run(["defaults", "read", "-g", "AppleAccentColor"],
                               capture_output=True, text=True, timeout=3)
            return {
                "0": "#FF3B30", "1": "#FF9500", "2": "#FFCC00",
                "3": "#28CD41", "4": "#007AFF", "5": "#AF52DE", "6": "#FF2D55",
            }.get(r.stdout.strip(), "#007AFF")
        except Exception:
            pass
    else:
        try:
            import subprocess
            r = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "accent-color"],
                capture_output=True, text=True, timeout=3)
            name = r.stdout.strip().strip("'\"")
            return {
                "blue": "#3584E4", "teal": "#2190A4", "green": "#3A944A",
                "yellow": "#E5A50A", "orange": "#E66100", "red": "#E01B24",
                "pink": "#D56199", "purple": "#9141AC", "slate": "#6F8396",
            }.get(name)
        except Exception:
            pass
    return None


def _accent_variants(hex_color: str) -> dict[str, str]:
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        rl, gl, bl = min(r+40, 255), min(g+40, 255), min(b+40, 255)
        return {
            "accent_light": f"#{rl:02X}{gl:02X}{bl:02X}",
            "accent_glow":  f"#{r//6:02X}{g//6:02X}{b//6:02X}",
            "accent_dim":   f"#{r//5:02X}{g//5:02X}{b//5:02X}",
            "accent2":      f"#{min(r+60,255):02X}{g//5:02X}{min(b+40,255):02X}",
        }
    except Exception:
        return {"accent_light":"#6199FF","accent_glow":"#1A2D60",
                "accent_dim":"#1B2E60","accent2":"#7C5CFF"}


# ══════════════════════════════════════════════════════════════════════════════
#  Palettes
# ══════════════════════════════════════════════════════════════════════════════

_DARK: dict[str, str] = {
    "bg_deep": "#090E1A", "bg_card": "#111827", "bg_input": "#19213A",
    "bg_hover": "#1E2840", "bg_panel": "#131C30",
    "accent": "#3B7DF8", "accent_light": "#6199FF",
    "accent_glow": "#1A2D60", "accent_dim": "#1B2E60", "accent2": "#7C5CFF",
    "success": "#2DD68A", "success_dim": "#0B2820",
    "warning": "#F5A623", "warning_dim": "#2C1C06",
    "danger": "#E8445A",  "danger_dim": "#2B0910",
    # #6A789A au lieu de #4D5780 — meilleur contraste sur bg_deep (#090E1A)
    "text_primary": "#E2EAF8", "text_secondary": "#8A96B8", "text_muted": "#6A789A",
    "border": "#1C2540", "border_soft": "#242E4C",
    "border_focus": "#3B7DF8", "border_drag_over": "#6199FF",
    "drop_bg": "#111827", "drop_border": "#2A3558",
    "warn_bg": "#2C1C06", "warn_border": "#7A5C00", "warn_text": "#F5D78E",
    "accent_custom": "#3B7DF8",
}

_OLED: dict[str, str] = {
    **_DARK,
    "bg_deep": "#000000", "bg_card": "#060912", "bg_input": "#090E1A",
    "bg_hover": "#0C1020", "bg_panel": "#040709",
    # Séparateurs adoucis pour OLED
    "border": "#101522", "border_soft": "#181F34",
    "drop_bg": "#000000", "drop_border": "#141A2E",
    "warn_bg": "#1C1000", "warn_border": "#4A3800",
}

_LIGHT: dict[str, str] = {
    "bg_deep": "#F0F4FC", "bg_card": "#FFFFFF", "bg_input": "#E8EDF8",
    "bg_hover": "#DDE4F4", "bg_panel": "#EBF0FA",
    "accent": "#2563EB", "accent_light": "#3B82F6",
    "accent_glow": "#DBEAFE", "accent_dim": "#BFDBFE", "accent2": "#7C3AED",
    "success": "#16A34A", "success_dim": "#DCFCE7",
    "warning": "#D97706", "warning_dim": "#FEF9C3",
    "danger": "#DC2626",  "danger_dim": "#FEE2E2",
    "text_primary": "#0F172A", "text_secondary": "#334155", "text_muted": "#64748B",
    "border": "#CBD5E1", "border_soft": "#E2E8F0",
    "border_focus": "#2563EB", "border_drag_over": "#3B82F6",
    "drop_bg": "#F8FAFF", "drop_border": "#CBD5E1",
    "warn_bg": "#FFFBEB", "warn_border": "#FDE68A", "warn_text": "#92400E",
    "accent_custom": "#2563EB",
}


# ══════════════════════════════════════════════════════════════════════════════
#  Détection dark mode
# ══════════════════════════════════════════════════════════════════════════════

def _detect_system_dark() -> bool:
    try:
        import darkdetect
        return darkdetect.isDark() or False
    except Exception:
        pass
    try:
        if sys.platform == "win32":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize")
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return val == 0
        if sys.platform == "darwin":
            import subprocess
            r = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                               capture_output=True, text=True)
            return "Dark" in r.stdout
    except Exception:
        pass
    return True


# ══════════════════════════════════════════════════════════════════════════════
#  API publique
# ══════════════════════════════════════════════════════════════════════════════

def get_palette(theme: str = "dark") -> dict[str, str]:
    if theme == "oled":  return dict(_OLED)
    if theme == "light": return dict(_LIGHT)
    if theme == "auto":  return dict(_DARK if _detect_system_dark() else _LIGHT)
    if theme == "system":
        base = dict(_DARK if _detect_system_dark() else _LIGHT)
        accent = get_system_accent_color()
        if accent:
            variants = _accent_variants(accent)
            base.update({"accent": accent, "border_focus": accent,
                         "border_drag_over": variants["accent_light"],
                         "accent_custom": accent, **variants})
        return base
    return dict(_DARK)


COLORS: dict[str, str] = dict(_DARK)


# ══════════════════════════════════════════════════════════════════════════════
#  Feuille de style principale
# ══════════════════════════════════════════════════════════════════════════════

def get_stylesheet(theme: str = "dark") -> str:
    c = get_palette(theme)
    COLORS.update(c)
    return f"""
/* ── Reset ───────────────────────────────────────────────────────────── */
* {{ outline: none; }}
QWidget {{
    background-color: {c['bg_deep']};
    color: {c['text_primary']};
    font-family: "Segoe UI Variable","Segoe UI","SF Pro Text","Inter","Helvetica Neue",Arial,sans-serif;
    font-size: 13px;
    selection-background-color: {c['accent']};
    selection-color: #FFFFFF;
}}
QMainWindow, QDialog {{ background-color: {c['bg_deep']}; }}

/* ── Scrollbars ──────────────────────────────────────────────────────── */
QScrollBar:vertical   {{ background:transparent; width:6px; margin:0; }}
QScrollBar:horizontal {{ background:transparent; height:6px; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background:{c['border_soft']}; border-radius:3px; min-height:36px; min-width:36px;
}}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
    background:{c['accent']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ height:0; width:0; background:transparent; }}

/* ── Onglets ─────────────────────────────────────────────────────────── */
QTabWidget::pane {{ border:none; background:{c['bg_deep']}; top:0; }}
QTabBar {{ background:{c['bg_card']}; border-bottom:1px solid {c['border_soft']}; }}
QTabBar::tab {{
    background:transparent; color:{c['text_muted']};
    padding:14px 28px; margin:0;
    font-size:13px; font-weight:500; letter-spacing:0.3px;
    border-bottom:2px solid transparent; min-width:96px;
}}
QTabBar::tab:selected {{
    color:{c['accent_light']}; border-bottom:2px solid {c['accent']};
    font-weight:700; background:transparent;
}}
QTabBar::tab:hover:!selected {{
    color:{c['text_secondary']}; background:{c['bg_hover']};
    border-bottom:2px solid {c['border_soft']};
}}
QTabBar::tab:disabled {{
    color:transparent; background:transparent;
    border:none; padding:0; min-width:0; max-width:0;
}}

/* ── Cartes ──────────────────────────────────────────────────────────── */
QFrame#card {{
    background:{c['bg_card']};
    border:1px solid {c['border']};
    border-bottom:2px solid {c['border_soft']};
    border-radius:16px;
}}
QFrame#card_inner {{
    background:{c['bg_panel']}; border:1px solid {c['border']}; border-radius:12px;
}}
QFrame#settings_card {{
    background:{c['bg_card']};
    border:1px solid {c['border']};
    border-bottom:2px solid {c['border_soft']};
    border-radius:16px;
}}
QFrame#settings_card_accent {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 {c['bg_card']},stop:1 {c['accent_glow']});
    border:1px solid {c['accent_dim']}; border-radius:16px;
}}

/* ── Champs texte ────────────────────────────────────────────────────── */
QLineEdit {{
    background:{c['bg_input']}; border:1.5px solid {c['border_soft']};
    border-radius:12px; padding:11px 16px;
    color:{c['text_primary']}; font-size:13px;
}}
QLineEdit:hover:!focus {{ border-color:{c['text_muted']}; }}
QLineEdit:focus {{
    border:2px solid {c['border_focus']}; background:{c['bg_hover']};
}}
QLineEdit:disabled {{
    background:{c['bg_panel']}; color:{c['text_muted']}; border-color:{c['border']};
}}
QLineEdit#url_input {{
    background:{c['bg_input']}; border:2px solid {c['border_soft']};
    border-radius:14px; padding:13px 18px; font-size:14px;
}}
QLineEdit#url_input:focus {{
    border:2px solid {c['border_focus']}; background:{c['bg_hover']};
}}

/* ── Bouton PRIMAIRE ─────────────────────────────────────────────────── */
QPushButton {{
    background:{c['accent']}; color:#FFFFFF; border:none;
    border-radius:12px; padding:11px 28px;
    font-size:13px; font-weight:600; letter-spacing:0.2px;
}}
QPushButton:hover {{
    background:{c['accent_light']};
    border:2px solid rgba(97,153,255,0.30);
}}
QPushButton:pressed {{
    background:{c['accent']};
    border:1.5px solid {c['accent_dim']};
    padding-top:13px; padding-bottom:9px;
    color:rgba(255,255,255,0.82);
}}
QPushButton:disabled {{ background:{c['border']}; color:{c['text_muted']}; }}
QPushButton:focus {{ border:2px solid {c['accent_light']}; }}

/* ── Bouton SECONDAIRE ───────────────────────────────────────────────── */
QPushButton#btn_secondary {{
    background:{c['bg_hover']}; color:{c['text_secondary']};
    border:1.5px solid {c['border_soft']}; border-radius:10px;
    padding:9px 18px; font-size:12px; font-weight:500;
}}
QPushButton#btn_secondary:hover {{
    background:{c['bg_input']}; color:{c['text_primary']}; border-color:{c['accent']};
}}
QPushButton#btn_secondary:pressed {{
    background:{c['border_soft']}; color:{c['text_muted']};
    padding-top:10px; padding-bottom:8px; border-color:{c['border']};
}}
QPushButton#btn_secondary:disabled {{
    color:{c['text_muted']}; border-color:{c['border']}; background:{c['bg_panel']};
}}

/* ── Bouton DANGER ───────────────────────────────────────────────────── */
QPushButton#btn_danger {{
    background:{c['danger_dim']}; color:{c['danger']};
    border:1.5px solid {c['danger']}; border-radius:10px;
    padding:9px 18px; font-size:12px; font-weight:600;
}}
QPushButton#btn_danger:hover {{ background:{c['danger']}; color:#FFFFFF; border:none; }}
QPushButton#btn_danger:pressed {{
    background:{c['danger']}; color:rgba(255,255,255,0.82);
    padding-top:10px; padding-bottom:8px;
}}

/* ── Bouton gear Settings ────────────────────────────────────────────── */
QPushButton#btn_settings_gear {{
    background:transparent; color:{c['text_secondary']};
    font-size:18px; border:none; border-radius:8px; padding:2px;
}}
QPushButton#btn_settings_gear:hover {{ background:{c['bg_hover']}; color:{c['text_primary']}; }}
QPushButton#btn_settings_gear:pressed {{ background:{c['border_soft']}; }}

/* ── Bouton coin Paramètres ──────────────────────────────────────────── */
QPushButton#corner_settings_btn {{
    background:transparent; color:{c['text_secondary']};
    border:none; border-left:1px solid {c['border_soft']};
    border-radius:0; padding:0 18px;
    font-size:13px; font-weight:500;
}}
QPushButton#corner_settings_btn:hover {{
    background:{c['bg_hover']}; color:{c['text_primary']};
}}
QPushButton#corner_settings_btn:pressed {{
    background:{c['accent_glow']}; color:{c['accent_light']};
    padding-top:1px;
}}
QPushButton#corner_settings_btn:checked {{
    background:{c['bg_card']}; color:{c['accent_light']};
    border-bottom:2px solid {c['accent']};
}}

/* ── ComboBox ────────────────────────────────────────────────────────── */
QComboBox {{
    background:{c['bg_input']}; border:1.5px solid {c['border_soft']};
    border-radius:11px; padding:9px 14px;
    color:{c['text_primary']}; font-size:13px; min-height:20px;
}}
QComboBox:hover {{ border-color:{c['accent']}; }}
QComboBox:focus {{ border:2px solid {c['border_focus']}; }}
QComboBox::drop-down {{ border:none; width:32px; subcontrol-position:right center; }}
QComboBox::down-arrow {{
    width:0; height:0;
    border-left:5px solid transparent; border-right:5px solid transparent;
    border-top:6px solid {c['text_muted']};
}}
QComboBox QAbstractItemView {{
    background:{c['bg_card']}; border:1px solid {c['border']};
    border-radius:12px; color:{c['text_primary']};
    selection-background-color:{c['accent_dim']}; selection-color:{c['text_primary']};
    padding:6px; outline:none;
}}
QComboBox QAbstractItemView::item {{
    padding:10px 14px; border-radius:8px; min-height:28px;
}}
QComboBox QAbstractItemView::item:hover {{ background:{c['bg_hover']}; }}

/* ── Barre de progression pill 6px ──────────────────────────────────── */
QProgressBar {{
    background:{c['bg_hover']}; border:none; border-radius:3px; max-height:6px;
}}
QProgressBar::chunk {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {c['accent']},stop:1 {c['accent_light']});
    border-radius:3px;
}}
/* Barre compression — variante verte */
QProgressBar#compress_progress::chunk {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {c['success']},stop:1 #22D3A5);
    border-radius:3px;
}}

/* ── Labels ──────────────────────────────────────────────────────────── */
QLabel#title {{
    font-size:22px; font-weight:800; color:{c['text_primary']};
    letter-spacing:-0.5px; background:transparent;
}}
QLabel#subtitle {{ font-size:12px; color:{c['text_muted']}; background:transparent; }}
QLabel#status_info {{ color:{c['text_secondary']}; background:transparent; }}
QLabel#status_ok   {{ color:{c['success']};   background:transparent; font-weight:600; }}
QLabel#status_err  {{ color:{c['danger']};    background:transparent; font-weight:600; }}
QLabel#status_warn {{ color:{c['warning']};   background:transparent; font-weight:600; }}
QLabel#card_section_icon  {{ font-size:18px; background:transparent; }}
QLabel#card_section_title {{
    font-size:13px; font-weight:700; color:{c['text_primary']}; background:transparent;
}}

/* ── Zone de dépôt ───────────────────────────────────────────────────── */
QFrame#drop_zone {{
    background:{c['drop_bg']}; border:2px dashed {c['drop_border']}; border-radius:18px;
}}
QFrame#drop_zone:hover {{
    border-color:{c['accent']}; background:{c['accent_glow']};
}}
QFrame#drop_zone[drag_active="true"] {{
    background:{c['accent_glow']}; border:2.5px dashed {c['accent_light']}; border-radius:18px;
}}

/* ── Checkbox / Toggle ───────────────────────────────────────────────── */
QCheckBox {{ color:{c['text_secondary']}; spacing:12px; font-size:13px; }}
QCheckBox::indicator {{
    width:18px; height:18px; border-radius:6px;
    border:1.5px solid {c['border_soft']}; background:{c['bg_input']};
}}
QCheckBox::indicator:checked {{
    background:{c['accent']}; border-color:{c['accent_light']};
}}
QCheckBox::indicator:hover {{ border-color:{c['accent']}; }}

QCheckBox#toggle_switch {{ color:{c['text_primary']}; spacing:14px; font-size:13px; }}
QCheckBox#toggle_switch::indicator {{
    width:44px; height:24px; border-radius:12px;
    border:none; background:{c['border_soft']};
}}
QCheckBox#toggle_switch::indicator:checked {{ background:{c['accent']}; }}
QCheckBox#toggle_switch::indicator:hover {{ border:2px solid {c['accent']}; }}

/* ── RadioButton ─────────────────────────────────────────────────────── */
QRadioButton {{
    color:{c['text_secondary']}; spacing:10px; font-size:13px;
}}
QRadioButton::indicator {{
    width:18px; height:18px; border-radius:9px;
    border:1.5px solid {c['border_soft']}; background:{c['bg_input']};
}}
QRadioButton::indicator:checked {{
    background:{c['accent']}; border-color:{c['accent_light']};
}}
QRadioButton::indicator:hover {{ border-color:{c['accent']}; }}

/* ── SpinBox ─────────────────────────────────────────────────────────── */
QSpinBox {{
    background:{c['bg_input']}; border:1.5px solid {c['border_soft']};
    border-radius:10px; padding:8px 12px; color:{c['text_primary']}; font-size:13px;
}}
QSpinBox:focus {{ border-color:{c['border_focus']}; }}
QSpinBox::up-button, QSpinBox::down-button {{ width:0; }}

/* ── Slider ──────────────────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    background:{c['bg_hover']}; height:5px; border-radius:3px;
}}
QSlider::handle:horizontal {{
    background:{c['accent']}; width:20px; height:20px;
    border-radius:10px; margin:-8px 0; border:2.5px solid {c['bg_deep']};
}}
QSlider::handle:horizontal:hover {{ background:{c['accent_light']}; }}
QSlider::sub-page:horizontal {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {c['accent']},stop:1 {c['accent_light']});
    border-radius:3px;
}}

/* ── Listes ──────────────────────────────────────────────────────────── */
QListWidget {{
    background:{c['bg_panel']}; border:1px solid {c['border']};
    border-radius:12px; padding:6px; color:{c['text_primary']};
    font-size:12px; outline:0;
}}
QListWidget::item {{
    padding:9px 12px; border-radius:8px; color:{c['text_secondary']};
}}
QListWidget::item:hover    {{ background:{c['bg_hover']};  color:{c['text_primary']}; }}
QListWidget::item:selected {{ background:{c['accent_dim']}; color:{c['text_primary']}; }}

/* ── GroupBox ────────────────────────────────────────────────────────── */
QGroupBox {{
    border:1px solid {c['border_soft']}; border-radius:14px;
    margin-top:18px; padding:16px 14px 14px 14px;
    font-size:11px; font-weight:700; color:{c['text_muted']}; letter-spacing:0.5px;
}}
QGroupBox::title {{
    subcontrol-origin:margin; subcontrol-position:top left;
    left:16px; top:-1px; padding:0 8px; background:{c['bg_card']};
}}

/* ── Tooltip ─────────────────────────────────────────────────────────── */
QToolTip {{
    background:{c['bg_card']}; color:{c['text_primary']};
    border:1px solid {c['border_focus']}; border-radius:10px;
    padding:8px 13px; font-size:12px;
}}

/* ── Boutons thème ───────────────────────────────────────────────────── */
QPushButton#theme_btn {{
    background:{c['bg_hover']}; color:{c['text_secondary']};
    border:1.5px solid {c['border_soft']}; border-radius:10px;
    padding:9px 20px; font-size:12px; font-weight:500; text-align:left;
}}
QPushButton#theme_btn:hover {{
    background:{c['bg_input']}; color:{c['text_primary']}; border-color:{c['border_focus']};
}}
QPushButton#theme_btn:pressed {{
    background:{c['accent_glow']}; padding-top:10px; padding-bottom:8px;
}}
QPushButton#theme_btn:checked {{
    background:{c['accent_glow']}; color:{c['accent_light']};
    border:2px solid {c['accent']}; font-weight:700;
}}

QPushButton#theme_preview_dark {{
    background:#111827; border:2px solid {c['border_soft']};
    border-radius:12px; min-width:78px; min-height:48px;
    color:#DCE4F5; font-size:11px; font-weight:600;
}}
QPushButton#theme_preview_dark:hover  {{ border-color:{c['text_muted']}; }}
QPushButton#theme_preview_dark:checked {{ border:2px solid {c['accent']}; }}
QPushButton#theme_preview_oled {{
    background:#000000; border:2px solid {c['border_soft']};
    border-radius:12px; min-width:78px; min-height:48px;
    color:#555; font-size:11px; font-weight:600;
}}
QPushButton#theme_preview_oled:hover  {{ border-color:{c['text_muted']}; }}
QPushButton#theme_preview_oled:checked {{ border:2px solid {c['accent']}; }}
QPushButton#theme_preview_light {{
    background:#F0F4FC; border:2px solid {c['border_soft']};
    border-radius:12px; min-width:78px; min-height:48px;
    color:#0F172A; font-size:11px; font-weight:600;
}}
QPushButton#theme_preview_light:hover  {{ border-color:{c['text_muted']}; }}
QPushButton#theme_preview_light:checked {{ border:2px solid {c['accent']}; }}
QPushButton#theme_preview_auto {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #111827,stop:1 #F0F4FC);
    border:2px solid {c['border_soft']}; border-radius:12px; min-width:78px; min-height:48px;
    color:{c['accent_light']}; font-size:11px; font-weight:600;
}}
QPushButton#theme_preview_auto:checked {{ border:2px solid {c['accent']}; }}
QPushButton#theme_preview_system {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 {c['bg_card']},stop:1 {c['accent_glow']});
    border:2px solid {c['accent_dim']}; border-radius:12px; min-width:78px; min-height:48px;
    color:{c['accent_light']}; font-size:11px; font-weight:600;
}}
QPushButton#theme_preview_system:checked {{ border:2px solid {c['accent']}; }}

/* ── Pastilles FFmpeg ────────────────────────────────────────────────── */
QLabel#ffmpeg_dot_ok  {{
    background:{c['success']}; border-radius:5px;
    min-width:10px; max-width:10px; min-height:10px; max-height:10px;
}}
QLabel#ffmpeg_dot_err {{
    background:{c['danger']}; border-radius:5px;
    min-width:10px; max-width:10px; min-height:10px; max-height:10px;
}}
QLabel#ffmpeg_dot_warn {{
    background:{c['warning']}; border-radius:5px;
    min-width:10px; max-width:10px; min-height:10px; max-height:10px;
}}

/* ── Barres comparaison Compressor ───────────────────────────────────── */
QFrame#compare_bar_bg  {{
    background:{c['bg_hover']}; border-radius:4px; border:none;
}}
QFrame#compare_bar_fill {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {c['accent']},stop:1 {c['accent_light']});
    border-radius:4px; border:none;
}}

/* ── Badges — fonds *_dim systématiques ──────────────────────────────── */
QLabel#badge_optimal {{
    background:{c['success_dim']}; color:{c['success']};
    border-radius:8px; padding:4px 12px; font-size:11px; font-weight:700;
}}
QLabel#badge_warn {{
    background:{c['warning_dim']}; color:{c['warning']};
    border-radius:8px; padding:4px 12px; font-size:11px; font-weight:700;
}}
QLabel#badge_danger {{
    background:{c['danger_dim']}; color:{c['danger']};
    border-radius:8px; padding:4px 12px; font-size:11px; font-weight:700;
}}

/* ── Barre stats (bas) ───────────────────────────────────────────────── */
QFrame#stats_bar {{
    background:{c['bg_card']}; border-top:1px solid {c['border_soft']}; border-radius:0;
}}
QLabel#stat_value {{
    font-size:16px; font-weight:700; color:{c['accent_light']}; background:transparent;
}}
QLabel#stat_label {{
    font-size:10px; font-weight:600; color:{c['text_muted']};
    background:transparent; letter-spacing:0.6px;
}}

/* ── Bouton options avancées ─────────────────────────────────────────── */
QPushButton#btn_advanced {{
    background:transparent; color:{c['text_muted']};
    border:1.5px solid {c['border_soft']}; border-radius:8px;
    padding:6px 16px; font-size:12px; font-weight:500; text-align:left;
}}
QPushButton#btn_advanced:hover {{
    background:{c['bg_hover']}; color:{c['text_secondary']}; border-color:{c['accent']};
}}
QPushButton#btn_advanced:pressed {{
    background:{c['accent_glow']}; padding-top:7px; padding-bottom:5px;
}}
QPushButton#btn_advanced:checked {{
    color:{c['accent_light']}; border-color:{c['accent']}; background:{c['accent_glow']};
}}

/* ── Panneau options avancées ────────────────────────────────────────── */
QFrame#advanced_panel {{
    background:{c['bg_panel']}; border:1px solid {c['border']};
    border-radius:14px; margin-top:4px;
}}

/* ── Séparateurs (HLine / VLine) ─────────────────────────────────────── */
QFrame[frameShape="4"] {{
    background:{c['border_soft']}; border:none; max-height:1px;
}}
QFrame[frameShape="5"] {{
    background:{c['border_soft']}; border:none; max-width:1px;
}}

"""


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def badge_style(kind: str = "info") -> str:
    m = {
        "info": (COLORS["bg_hover"],    COLORS["text_muted"]),
        "ok":   (COLORS["success_dim"], COLORS["success"]),
        "warn": (COLORS["warning_dim"], COLORS["warning"]),
        "err":  (COLORS["danger_dim"],  COLORS["danger"]),
    }
    bg, fg = m.get(kind, m["info"])
    return (f"background:{bg}; color:{fg}; border-radius:8px; "
            f"padding:3px 11px; font-size:11px; font-weight:700; letter-spacing:0.2px;")


def section_label_style() -> str:
    return (f"font-size:10px; font-weight:700; color:{COLORS['text_muted']}; "
            f"letter-spacing:1.4px; background:transparent; margin-bottom:2px;")


def card_title_style() -> str:
    return f"font-size:15px; font-weight:700; color:{COLORS['text_primary']}; background:transparent;"


def toggle_switch_style() -> str:
    return ""   # défini dans la feuille globale via #toggle_switch


def compression_badge_style(kind: str = "optimal") -> str:
    m = {
        "optimal": (COLORS["success_dim"], COLORS["success"]),
        "warn":    (COLORS["warning_dim"], COLORS["warning"]),
        "danger":  (COLORS["danger_dim"],  COLORS["danger"]),
    }
    bg, fg = m.get(kind, m["optimal"])
    return (f"background:{bg}; color:{fg}; border-radius:8px; padding:4px 12px; "
            f"font-size:11px; font-weight:700; letter-spacing:0.4px;")
