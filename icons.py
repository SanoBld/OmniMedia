"""
icons.py — OmniMedia v4.5
Bibliothèque d'icônes SVG inline.
Chemins SVG originaux inspirés du style Lucide (lignes, stroke-linecap:round).
Rendu via QSvgRenderer → QPixmap → QIcon, sans dépendance externe.

Usage :
    from icons import icon
    tab.setTabIcon(0, icon("download"))
    btn.setIcon(icon("folder", color="#8A96B8", size=16))
"""
from __future__ import annotations

from PyQt6.QtCore  import QByteArray, QSize, Qt
from PyQt6.QtGui   import QIcon, QPainter, QPixmap

# ── Paths SVG (viewBox 0 0 24 24, stroke="C", fill="none") ────────────────────

_PATHS: dict[str, str] = {
    # Flèche vers le bas — Télécharger
    "download": (
        'M12 3v13 M5 12l7 7 7-7 M3 21h18'
    ),
    # Deux flèches opposées — Convertir
    "convert": (
        'M7 16V4 M3 8l4-4 4 4 M17 8v12 M13 16l4 4 4-4'
    ),
    # Boîte avec flèche — Compresser / Package
    "compress": (
        'M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8'
        'a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z'
        'M12 22V12 M3.27 6.96L12 12.01l8.73-5.05'
    ),
    # Engrenage — Paramètres
    "settings": (
        'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z'
        'M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06'
        'a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09'
        'A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83'
        'l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09'
        'A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83'
        'l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09'
        'a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83'
        'l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09'
        'a1.65 1.65 0 0 0-1.51 1z'
    ),
    # Dossier ouvert
    "folder": (
        'M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z'
    ),
    # Horloge — Historique
    "history": (
        'M12 22C6.48 22 2 17.52 2 12S6.48 2 12 2s10 4.48 10 10-4.48 10-10 10z'
        'M12 6v6l4 2'
    ),
    # Coche — Succès
    "check": (
        'M20 6L9 17l-5-5'
    ),
    # Croix — Erreur / Fermer
    "x": (
        'M18 6L6 18 M6 6l12 12'
    ),
    # Triangle — Avertissement
    "warning": (
        'M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86'
        'a2 2 0 0 0-3.42 0z M12 9v4 M12 17h.01'
    ),
    # Éclair — Vitesse / Performance
    "zap": (
        'M13 2L3 14h9l-1 8 10-12h-9l1-8z'
    ),
    # Étiquette — Tag / Méta-données
    "tag": (
        'M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z'
        'M7 7h.01'
    ),
    # Cloche — Notifications
    "bell": (
        'M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9'
        'M13.73 21a2 2 0 0 1-3.46 0'
    ),
    # Globe — Langue / Internet
    "globe": (
        'M12 22c5.52 0 10-4.48 10-10S17.52 2 12 2 2 6.48 2 12s4.48 10 10 10z'
        'M2 12h20 M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10'
        '15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z'
    ),
    # Crayon — Presets / Éditer
    "edit": (
        'M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7'
        'M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z'
    ),
    # Corbeille — Supprimer
    "trash": (
        'M3 6h18 M8 6V4h8v2 M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6'
        'M10 11v6 M14 11v6'
    ),
    # Mise à jour / Flèche circulaire
    "refresh": (
        'M23 4v6h-6 M1 20v-6h6'
        'M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15'
    ),
    # CPU / Processeur
    "cpu": (
        'M18 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2z'
        'M9 9h6v6H9z M9 1v3 M15 1v3 M9 20v3 M15 20v3 M20 9h3 M20 14h3 M1 9h3 M1 14h3'
    ),
    # Palette — Apparence
    "palette": (
        'M12 2C6.49 2 2 6.49 2 12s4.49 10 10 10c1.38 0 2.5-1.12 2.5-2.5 0-.61-.23-1.17-.64-1.59'
        '-.08-.1-.13-.21-.13-.33 0-.28.22-.5.5-.5H16c3.31 0 6-2.69 6-6 0-4.96-4.49-9-10-9z'
        'M5.5 13a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z'
        'M8.5 9a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z'
        'M15.5 9a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z'
        'M18.5 13a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z'
    ),
    # Lien / Chaîne
    "link": (
        'M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71'
        'M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71'
    ),
    # Animations / Magic wand
    "wand": (
        'M15 4V2 M15 16v-2 M8 9h2 M20 9h2 M17.8 11.8L19 13 M15 9h.01'
        'M17.8 6.2L19 5 M3 21l9-9 M12.2 6.2L11 5'
    ),
}


def icon(
    name:  str,
    color: str = "#E2EAF8",
    size:  int = 18,
    stroke_width: float = 2.0,
) -> QIcon:
    """
    Retourne un QIcon rendu depuis le path SVG correspondant à *name*.
    Si le nom est inconnu ou si QSvgRenderer n'est pas disponible,
    retourne un QIcon vide (jamais d'exception).

    Args:
        name:         Clé dans _PATHS (ex : "download", "settings").
        color:        Couleur du trait en hex (ex : "#E2EAF8").
        size:         Dimension en pixels (carré).
        stroke_width: Épaisseur du trait SVG.
    """
    try:
        from PyQt6.QtSvg import QSvgRenderer  # type: ignore[import]
    except ImportError:
        return QIcon()

    path_d = _PATHS.get(name)
    if not path_d:
        return QIcon()

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        f' fill="none" stroke="{color}" stroke-width="{stroke_width}"'
        f' stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="{path_d}"/>'
        f'</svg>'
    )

    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pm = QPixmap(QSize(size, size))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p)
    p.end()
    return QIcon(pm)


def icon_pixmap(
    name:  str,
    color: str = "#E2EAF8",
    size:  int = 18,
    stroke_width: float = 2.0,
) -> QPixmap:
    """Même chose qu'icon() mais retourne directement un QPixmap."""
    ic = icon(name, color, size, stroke_width)
    sizes = ic.availableSizes()
    if sizes:
        return ic.pixmap(sizes[0])
    return QPixmap()
