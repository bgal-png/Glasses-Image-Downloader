# -*- coding: utf-8 -*-
r"""Filesystem locations, PyInstaller-aware.

Bundled files are located via sys._MEIPASS when frozen; per-user data
(the EssilorLuxottica catalogue cache, the Safilo profile) lives in
%LOCALAPPDATA%\GlassesImageDownloader so it survives .exe replacement.
"""
from __future__ import annotations

import os
import sys

from version import APP_NAME


def _slug(name: str) -> str:
    return "".join(ch for ch in name if ch.isalnum()) or "App"


def resource_path(*parts: str) -> str:
    """Path to a file bundled with the app (spec `datas`), or alongside the
    source when running from a checkout."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def repo_root() -> str:
    """Repo root, so the shared core modules import when running from source."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cache_dir(*parts: str) -> str:
    r"""%LOCALAPPDATA%\GlassesImageDownloader[\parts] — created if missing."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, _slug(APP_NAME), *parts)
    os.makedirs(path, exist_ok=True)
    return path


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)
