"""
tests/conftest.py — OmniMedia v4.5
Shared pytest configuration and fixtures.
Ensures PyQt6 is not required to run non-UI tests by mocking it if absent.
"""
import sys
from unittest.mock import MagicMock

# ── Mock PyQt6 so tests can run without a display / Qt installation ────────────
# If PyQt6 is already installed, this is a no-op.
if "PyQt6" not in sys.modules:
    qt_mock = MagicMock()
    sys.modules.update({
        "PyQt6"              : qt_mock,
        "PyQt6.QtCore"       : qt_mock,
        "PyQt6.QtGui"        : qt_mock,
        "PyQt6.QtWidgets"    : qt_mock,
    })
