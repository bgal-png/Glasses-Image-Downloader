# -*- coding: utf-8 -*-
"""⚙️ Settings — EssilorLuxottica auto-login credentials + the update token.

No token or password is ever baked into a build. The EssilorLuxottica login is
stored in the Windows Credential Manager (via `luxottica`), the update token in
QSettings; both are per user.
"""
from __future__ import annotations

import luxottica
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QLabel, QLineEdit,
    QVBoxLayout,
)


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        self.resize(540, 320)

        layout = QVBoxLayout(self)

        # --- EssilorLuxottica auto-login ---
        el_box = QGroupBox("EssilorLuxottica auto-login (optional)")
        el_form = QFormLayout(el_box)
        el_note = QLabel(
            "Saved in the Windows Credential Manager — never in a file or a build. "
            "When set, EssilorLuxottica matching logs in by itself if the session "
            "has expired."
        )
        el_note.setWordWrap(True)
        el_form.addRow(el_note)
        creds = luxottica.get_credentials() or ("", "")
        self.el_user = QLineEdit(creds[0])
        self.el_user.setPlaceholderText("username / email")
        self.el_pass = QLineEdit(creds[1])
        self.el_pass.setEchoMode(QLineEdit.Password)
        self.el_pass.setPlaceholderText("password")
        el_form.addRow("Username", self.el_user)
        el_form.addRow("Password", self.el_pass)
        layout.addWidget(el_box)

        # --- Update token ---
        up_box = QGroupBox("Updates")
        up_form = QFormLayout(up_box)
        up_note = QLabel(
            "This repo is private, so checking for updates needs a GitHub "
            "fine-grained token with read access to its Contents and Releases."
        )
        up_note.setWordWrap(True)
        up_form.addRow(up_note)
        self.token = QLineEdit(settings.update_token)
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText("github_pat_… (optional)")
        up_form.addRow("Update token", self.token)
        layout.addWidget(up_box)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        self.settings.update_token = self.token.text()
        user = self.el_user.text().strip()
        password = self.el_pass.text()
        if user and password:
            luxottica.set_credentials(user, password)
        elif not user and not password:
            luxottica.clear_credentials()
        super().accept()
