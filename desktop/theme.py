# -*- coding: utf-8 -*-
"""Dark/light theming and the house colour constants.

Colours are fixed by the family convention (see the desktop-tool conventions):
keep them identical across Alensa desktop tools.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

# --- Cell highlight colours (shared with the validator) ---
COLOR_ERROR = "#ffb3b3"
COLOR_WARNING = "#ffe08a"
COLOR_OK = "#c8e6c9"
# Highlighted cells force dark text so they stay readable in dark mode.
COLOR_FORCED_TEXT = "#111111"

# --- Status text colours ---
STATUS_LOADING = "#a06f00"
STATUS_READY = "#1a7f37"
STATUS_ERROR = "#b30000"


def status_style(state: str) -> str:
    """Qt stylesheet for the status label."""
    colour = {
        "loading": STATUS_LOADING,
        "ready": STATUS_READY,
        "error": STATUS_ERROR,
    }.get(state, STATUS_LOADING)
    return (
        f"color: {colour}; background-color: {colour}0f;"
        "padding: 4px 8px; border-radius: 4px; font-weight: 600;"
    )


def dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.Window, QColor(45, 45, 48))
    p.setColor(QPalette.WindowText, QColor(230, 230, 230))
    p.setColor(QPalette.Base, QColor(30, 30, 32))
    p.setColor(QPalette.AlternateBase, QColor(40, 40, 44))
    p.setColor(QPalette.ToolTipBase, QColor(45, 45, 48))
    p.setColor(QPalette.ToolTipText, QColor(230, 230, 230))
    p.setColor(QPalette.Text, QColor(230, 230, 230))
    p.setColor(QPalette.Button, QColor(55, 55, 60))
    p.setColor(QPalette.ButtonText, QColor(230, 230, 230))
    p.setColor(QPalette.BrightText, QColor(255, 80, 80))
    p.setColor(QPalette.Link, QColor(38, 110, 190))
    p.setColor(QPalette.Highlight, QColor(38, 110, 190))
    p.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.PlaceholderText, QColor(150, 150, 150))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor(130, 130, 130))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(130, 130, 130))
    p.setColor(QPalette.Disabled, QPalette.WindowText, QColor(130, 130, 130))
    return p


def apply_theme(app: QApplication, dark: bool) -> None:
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setPalette(dark_palette() if dark else app.style().standardPalette())
