# -*- coding: utf-8 -*-
"""Common contract for every tab.

Tabs are plain QWidgets sharing one Session. The main window owns the toolbar
and the right dock; it asks the current tab for its control panel and hides the
dock entirely on tabs that return None.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget


class BaseTab(QWidget):
    TITLE = "Tab"

    status_message = Signal(str)
    busy = Signal(bool)
    changed = Signal()  # session mutated — main asks every tab to refresh

    def __init__(self, session, settings, parent=None):
        super().__init__(parent)
        self.session = session
        self.settings = settings

    def refresh(self) -> None:
        """Re-read the shared session into this tab's widgets."""

    def control_panel(self) -> QWidget | None:
        return None

    def has_unsaved_changes(self) -> bool:
        return False
