"""
app_logger.py — OmniMedia v4.5
Centralised logging setup.
- Writes DEBUG+ to ~/.omnimedia/logs/app.log  (rotating, 3 × 1 MB)
- Writes WARNING+ to stderr
- All modules grab their logger with get_logger(__name__)
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

_LOG_DIR  : Path = Path.home() / ".omnimedia" / "logs"
_LOG_FILE : Path = _LOG_DIR / "app.log"
_INITIALISED = False


def setup_logging(level: int = logging.DEBUG) -> None:
    """
    Call once at application startup (before any other import that uses logging).
    Idempotent — safe to call more than once.
    """
    global _INITIALISED
    if _INITIALISED:
        return
    _INITIALISED = True

    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("omnimedia")
    root.setLevel(level)

    # ── Rotating file handler — DEBUG and above ────────────────────────────────
    try:
        fh = logging.handlers.RotatingFileHandler(
            _LOG_FILE,
            maxBytes=1 * 1024 * 1024,   # 1 MB per file
            backupCount=3,
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)-8s  %(name)s  —  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        root.addHandler(fh)
    except OSError as exc:
        # Can't write logs → at least warn on stderr
        logging.warning("OmniMedia: could not open log file %s: %s", _LOG_FILE, exc)

    # ── Stderr handler — WARNING and above ────────────────────────────────────
    sh = logging.StreamHandler()
    sh.setLevel(logging.WARNING)
    sh.setFormatter(logging.Formatter("%(levelname)s  %(name)s  —  %(message)s"))
    root.addHandler(sh)

    root.debug("Logging initialised → %s", _LOG_FILE)


def get_logger(name: str) -> logging.Logger:
    """
    Returns a child logger of the 'omnimedia' hierarchy.
    Usage: logger = get_logger(__name__)
    """
    if not name.startswith("omnimedia"):
        name = f"omnimedia.{name}"
    return logging.getLogger(name)


def log_path() -> Path:
    """Return the current log file path (useful for a 'Show log' button in Settings)."""
    return _LOG_FILE
