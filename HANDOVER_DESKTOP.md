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
  - Edel-Optics → img.edel-optics.com (public, **plain HTTP, no browser**). The
    URL is built from the name: `.../2000/nobg/<Brand>-<MODEL>-<COLOUR>.jpg`
    with `/` → `-`. **Two CDN segments**: `eoProductsGlassesSunglasses` and `eoProductsGlassesPrescription` (optical) — both are tried, the one that last worked first. The brand spells `&` as `and` (`Dolce-and-Gabbana`). Two traps: an unstocked frame answers **200 with a shared
    ~12 kB placeholder** (not a 404), and the CDN serves **WebP while labelling
    it `image/jpeg`**, so the bytes are sniffed and converted with Pillow.
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

GitHub Actions does the build (`.github/workflows/build-desktop.yml`):

1. Bump `desktop/version.py`
2. Commit and push
3. `git tag desktop-v<x.y.z> && git push origin desktop-v<x.y.z>`

The workflow then checks the tag matches `version.py`, runs the headless tests
and `--selftest`, builds the .exe, scans it for `ghp_` / `github_pat` /
`postgresql://` / `sk-ant`, and attaches it to the Release for that tag.
Installed copies see the new tag and self-update.

Run the workflow manually (Actions → Build desktop .exe → Run workflow) to get a
build as a downloadable artifact without publishing a Release.

To build locally instead:
`"C:\gv\Scripts\pyinstaller.exe" desktop\GlassesImageDownloader.spec --noconfirm`
— **close the app first**: PyInstaller cannot replace a running .exe and still
exits 0, so the build silently keeps the old binary. Check the timestamp.

The repo (`bgal-png/Glasses-Image-Downloader`) is private, so the in-app update
check needs a fine-grained token with read access to Contents and Releases,
pasted into ⚙️ Settings. No token is ever baked into a build. The self-update
swap uses the PowerShell `Wait-Process` method (see `desktop/updater.py`), proven
by `desktop/test_updater_swap.py`.
