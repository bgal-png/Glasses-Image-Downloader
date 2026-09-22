# -*- coding: utf-8 -*-
"""Persisted user settings (QSettings → Windows registry, per user).

Credentials policy: no token is ever baked into a build. `update_token` is a
fine-grained PAT for this private repo's Releases; the EssilorLuxottica login is
kept in the Windows Credential Manager (via the shared `luxottica` module), not
here. Both are entered in ⚙️ Settings; without them the relevant feature simply
reports it is not configured.
"""
from __future__ import annotations

from PySide6.QtCore import QSettings

from version import APP_NAME, ORG_NAME


class Settings:
    def __init__(self) -> None:
        self._s = QSettings(ORG_NAME, APP_NAME)

    @property
    def dark_mode(self) -> bool:
        return str(self._s.value("dark_mode", "false")).lower() in ("1", "true", "yes")

    @dark_mode.setter
    def dark_mode(self, value: bool) -> None:
        self._s.setValue("dark_mode", bool(value))

    @property
    def update_token(self) -> str:
        return str(self._s.value("update_token", "")).strip()

    @update_token.setter
    def update_token(self, value: str) -> None:
        self._s.setValue("update_token", (value or "").strip())

    def last_dir(self, key: str) -> str:
        return str(self._s.value(f"last_dir/{key}", "")).strip()

    def set_last_dir(self, key: str, path: str) -> None:
        self._s.setValue(f"last_dir/{key}", path or "")
