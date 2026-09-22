# Barcode Image Downloader — Design

**Date:** 2026-06-19
**Author:** bgal@alensa.eu

## Purpose

Given a list of barcodes, download the main (biggest) product image for each
from barcodelookup.com. Built as a local Streamlit app, launched from a desktop
shortcut.

## Why a browser engine

barcodelookup.com sits behind Cloudflare bot protection. A plain
`requests`/`BeautifulSoup` scraper gets blocked (403 / challenge page). The app
drives a real headless Chromium via **Playwright**, which passes the Cloudflare
check from the user's own IP. This is why the app runs **locally**, not on
Streamlit Cloud (datacenter IPs get blocked harder, and Playwright browser
binaries are fiddly to install there).

## How it runs

- Streamlit app stored in a GitHub repo, run locally.
- A desktop shortcut (`run.bat` launcher + a `.lnk` on the Desktop) starts the
  app and opens it in the browser — one double-click, no terminal needed.

## UI

- Input barcodes by either:
  - Pasting (one per line), or
  - Uploading `.xlsx`, `.csv`, or `.txt`.
- A "Download images" button.
- Live progress as it works through the list.
- A results table: each barcode → ✅ found / ❌ not found / ⚠️ error.
- A "Download all as ZIP" button at the end.

## Input parsing

- **Paste / `.txt`:** one barcode per line.
- **`.csv` / `.xlsx`:** auto-detect the column whose header is `Barcode`
  (case-insensitive). Fall back to the first column if no such header.
- **Cleaning:** strip whitespace including non-breaking spaces (`\xa0`),
  coerce numeric cells to plain digit strings (no `.0`), drop blanks.
- No dedup required by user, but blank rows are skipped.

## Engine (per barcode)

1. Open `https://www.barcodelookup.com/<barcode>` in headless Chromium.
2. Wait for the product image to render (past Cloudflare).
3. Select the **main/biggest** product image element (the large top-left image,
   not the thumbnail gallery, not site chrome).
4. Read its image URL and download the file at original resolution.
5. Save named by barcode: `<barcode>.jpg` (extension from the served content).

## Behavior details

- Short polite delay between barcodes (~1–2s) to avoid rate limiting.
- Always re-fetch (no skip-if-already-downloaded within a session).
- Page not found / no product image → marked ❌, run continues.
- Errors (timeout, Cloudflare block, network) → marked ⚠️ with reason, run
  continues.
- Results + image bytes held in memory for the session; ZIP built on demand.
  Nothing permanently written to disk unless the user saves the ZIP.

## Scale

- Designed for tens to low hundreds per run (current real list: 117).

## Repo contents

- `app.py` — Streamlit UI + Playwright engine.
- `requirements.txt` — `streamlit`, `playwright`, `openpyxl`, `pandas`.
- `run.bat` — launcher (starts streamlit, opens browser).
- `README.md` — setup (incl. `playwright install chromium`) and how to make the
  desktop shortcut.

## Out of scope

- Thumbnail / gallery images (only the main image).
- Site logos/icons.
- Cloud deployment.
- A stored database of past downloads.
