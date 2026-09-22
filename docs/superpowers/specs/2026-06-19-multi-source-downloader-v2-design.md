# Multi-Source Image Downloader (v2) — Design

**Date:** 2026-06-19
**Author:** bgal@alensa.eu

## Purpose

Extend the existing Barcode Image Downloader so it finds product images for as
many glasses as possible, given a **barcode and full name** per frame. Automates
the part that is reliable (barcode lookup) and provides a fast, reliable
**human-assisted** path for the rest, instead of fragile name-search scraping.

## Key finding that shaped this design

Automated free **name → image** search was tested against Bing, Google,
DuckDuckGo, SmartBuyGlasses, and barcodelookup's own name search. All proved
unreliable for bots: Bing poisons automated queries (returns unrelated images),
Google serves the bot an empty page, DuckDuckGo requires a JS token dance,
SmartBuyGlasses search is JS-only, and barcodelookup's POST `/search` triggers a
harder Cloudflare challenge that blocks the browser on repeat. Conclusion: do
NOT build on automated name-search. Keep automation where it works (barcode),
and make the name fallback human-assisted.

## Context / what already exists (v1)

- `barcode_parser.py` — parses paste/txt/csv/xlsx into a list of barcode strings.
- `fetcher.py` — Playwright engine; `make_browser()` + `fetch_image(browser, barcode)`
  returns the main image from barcodelookup.com. Has the Windows/Streamlit
  ProactorEventLoop fix and a `download_image_bytes`-style download path.
- `app.py` — Streamlit UI: input → run → results table → ZIP.

v2 reuses all of this. Only the barcode path is automated; the name fallback is
manual-assist.

## Input (both modes; paired records)

Parser returns **paired (barcode, name)** records, not just barcodes:
- **xlsx / csv:** read the `Barcode` column (case-insensitive header, first-column
  fallback) AND the `Glasses name` column (case-insensitive match on
  "glasses name", else a column literally named "name"; empty if neither exists).
- **Pasted text / txt:** each line is either just a barcode, or
  `barcode,name` / `barcode<TAB>name`. A line with no comma/tab → barcode with
  empty name.
- v1 cleaning rules still apply to the barcode (strip `\xa0`/whitespace, numeric
  coercion). Name is trimmed; empty names allowed.
- A record needs at least one of {barcode, name}; rows blank in both are dropped.

Data type: `{"barcode": str, "name": str}` (either may be "", not both).

## Engine (`fetcher.py`) — small additions

- Keep `FetchResult`, `make_browser`, `fetch_image` as-is.
- Add `download_url_bytes(url) -> tuple[bytes, str] | None` returning
  (bytes, extension) for an arbitrary direct image URL the user pasted. Uses a
  plain HTTP GET with a browser User-Agent and a Referer derived from the URL's
  origin (helps with simple hotlink checks). Returns None on failure (caller
  tells the user to upload the file instead). Reuses the existing
  extension-detection helper. No Playwright needed for this (the user already
  located the image; we just fetch the direct link).
- Add `search_links(name) -> dict[str, str]` returning ready-to-open search URLs
  for a frame name, e.g.
  `{"Google Images": "https://www.google.com/search?tbm=isch&q=<name>",
    "SmartBuyGlasses": "https://www.smartbuyglasses.com/search?q=<name>"}`.
  Pure string building; no network.

## App flow (`app.py`)

State lives in `st.session_state` so the manual step survives Streamlit reruns.

1. **Input:** paste box + file uploader (xlsx/csv/txt), yielding paired records.
   Show "N frame(s) ready (M with names)".
2. **Run barcode lookup** (button): one browser session. For each record with a
   barcode, call `fetch_image`. `ok` → auto-accepted image stored. Miss / no
   barcode → flagged "needs image". Progress bar `[i/N]` as v1. Results saved to
   session_state.
3. **Results table:** columns Barcode, Name, Status (`✅ found by barcode` /
   `✋ needs image` / `❌ no barcode & no name`), plus a thumbnail for
   auto-accepted images.
4. **Manual-assist section** (only for "needs image" frames with a name): for
   each such frame, show:
   - the frame name,
   - the search links from `search_links(name)` as clickable buttons/links that
     open in a new browser tab,
   - a **"Paste image URL"** text box (on submit, `download_url_bytes` fetches it;
     on success store the image + show a preview; on failure show
     "couldn't fetch — try uploading the file instead"),
   - a **file uploader** as the bulletproof alternative (store the uploaded
     bytes directly).
   Each provided image is stored against that frame in session_state.
5. **Download all as ZIP:** auto-accepted (barcode) images + manually provided
   images, named `<barcode>.jpg` (or a sanitized `<name>.jpg` when barcode is
   empty). v1 duplicate-name guard retained. Show counts (auto vs manual).

## Error handling

- Per-frame barcode-lookup failures mark that frame "needs image" and the loop
  continues (v1 philosophy).
- `download_url_bytes` failure → the frame stays "needs image"; UI suggests file
  upload. Never crashes the app.
- A frame with no barcode hit and no name → ❌ (cannot assist).

## Testing

- **Parser (pure, unit):** paired extraction from xlsx (both columns), csv,
  `barcode,name` paste lines, barcode-only lines, name-only rows, blank-row drop.
  Extends `tests/test_barcode_parser.py`. New function `parse_records`; keep
  `parse_barcodes` working (or have it delegate) so nothing else breaks.
- **search_links (pure, unit):** returns correctly URL-encoded links for a name.
- **download_url_bytes (live, opt-in `RUN_LIVE=1`):** downloads a known direct
  image URL and returns bytes + extension; returns None for a bogus URL.
- Existing barcodelookup live tests + the Streamlit-thread regression test stay.

## Out of scope

- Automated name-search scraping (tested, unreliable — see finding above).
- Icecat / paid APIs / distributor feeds.
- Persisting results between app launches.

## Notes

- NOT a git repo (per user decision); implementers skip git steps.
- Keep `fetcher.py` free of Streamlit imports; keep parser / engine / UI separate.
