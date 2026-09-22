# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — single-file, windowed .exe.

Build from the SHORT-PATH venv (the Store Python's path is long enough that
installing PySide6 fails with "enable-long-paths"), from the repo root:

    "C:\\gv\\Scripts\\pyinstaller.exe" desktop\\GlassesImageDownloader.spec

Output: dist\\GlassesImageDownloader.exe. It drives the SYSTEM Edge (msedge
channel) for every browser source, so no Playwright browser download is needed
on the target — only the Playwright driver, which is bundled here via
collect_all('playwright'). Large and unsigned, so SmartScreen warns once.
"""
import os

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.getcwd())
DESKTOP = os.path.join(ROOT, "desktop")

pw_datas, pw_binaries, pw_hidden = collect_all("playwright")

a = Analysis(
    [os.path.join(DESKTOP, "main.py")],
    pathex=[DESKTOP, ROOT],   # desktop modules + the shared core modules at root
    binaries=pw_binaries,
    datas=[(os.path.join(DESKTOP, "app_icon.ico"), ".")] + pw_datas,
    hiddenimports=[
        "openpyxl.cell._writer",
        "keyring.backends.Windows",
        "keyring.backends.chainer",
        "keyring.backends.fail",
    ] + pw_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "sklearn", "scipy", "streamlit", "pyarrow"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="GlassesImageDownloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(DESKTOP, "app_icon.ico"),
)
