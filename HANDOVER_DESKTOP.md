# Glasses Image Downloader — desktop app

A Windows `.exe` build of the multi-source glasses image downloader, following
the Alensa desktop house pattern (same family as Glasses Validator / Import
Filler / Size Import). Same logic as the Streamlit app (`app.py`), built on the
shared Qt-free core modules (`barcode_parser`, `fetcher`, `luxottica`, `alpina`,
`safilo`) plus `pipeline.py` (Qt-free orchestration).

## Run from source

    "C:\gv\Scripts\python.exe" desktop\main.py

`C:\gv` is a venv at a short path — the Microsoft Store Python's path is long
enough that installing PySide6 fails with "enable-long-paths".

## Selftest

    "C:\gv\Scripts\python.exe" desktop\main.py --selftest

Builds both tabs headlessly and exits 0. Run it before every build. The built
.exe accepts the same flag. It leaves no QThread alive at exit.

## Tests

    "C:\gv\Scripts\python.exe" -m pytest tests -k "not live"     # core logic, no network
    "C:\gv\Scripts\python.exe" desktop\test_updater_swap.py      # the self-update swap

Add `RUN_LIVE=1` to also run the live source tests (they hit the real sites;
EssilorLuxottica / Safilo need a login).

## Build

    "C:\gv\Scripts\pyinstaller.exe" desktop\GlassesImageDownloader.spec

Output: `dist\GlassesImageDownloader.exe`. Unsigned, so SmartScreen warns once.

## How it works

- **Sources**, each only filling frames that don't yet have an image:
  - Barcode → barcodelookup.com (headless Edge)
  - EssilorLuxottica → catalogue match (headless Edge; auto-login if credentials
    are saved in ⚙️ Settings / Windows Credential Manager)
  - Alpina → alpina-sports.com (public, headless Edge)
  - Safilo → youandsafilo.com (opens a visible login window; session can't persist)
- **All browser work uses the SYSTEM Edge** (`channel="msedge"`), so the .exe
  needs no downloaded/bundled Chromium — only the Playwright driver, bundled via
  `collect_all("playwright")` in the spec.
- Ambiguous matches become "🎨 pick an image" rows — double-click to choose a
  candidate thumbnail, paste a URL, or pick a file. Double-click any row to
  replace its image.
- **Output**: choose a folder, 💾 Save images → `<barcode>.jpg` (or a sanitized
  product name when there's no barcode). No ZIP.

## Credentials

- EssilorLuxottica login → Windows Credential Manager (via `luxottica`), set in
  ⚙️ Settings. Never in a file or the build.
- Update token → QSettings (per user), set in ⚙️ Settings.
- The app scrapes live sites; there is **no bundled reference snapshot** (the
  only cache is the EssilorLuxottica catalogue index in
  `%LOCALAPPDATA%\GlassesImageDownloader`).

## Shipping an update

1. Bump `desktop/version.py`
2. Rebuild with the spec
3. Scan the .exe for `ghp_`, `github_pat`, `postgresql://`, `sk-ant`
4. Tag `desktop-v<x.y.z>` and attach the .exe to a GitHub Release

The repo (`bgal-png/Glasses-Image-Downloader`) is private, so the in-app update
check needs a fine-grained token with read access to Contents and Releases,
pasted into ⚙️ Settings. No token is ever baked into a build. The self-update
swap uses the PowerShell `Wait-Process` method (see `desktop/updater.py`), proven
by `desktop/test_updater_swap.py`.
