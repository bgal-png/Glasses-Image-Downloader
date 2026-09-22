# Safilo Catalogue Source — Design

**Date:** 2026-06-19
**Author:** bgal@alensa.eu

## Purpose

Add a second manufacturer source — **Safilo** (youandsafilo.com) — so the tool
covers the brands Luxottica doesn't: Hugo Boss, Marc Jacobs, Carrera, Kate Spade,
Boss, etc. Matches frames by name and downloads the official Safilo image.

## Discovery findings (verified live)

- youandsafilo.com is **Salesforce B2B Commerce (LWR)**. Store id
  `0ZE7T0000010wEUWAY`; account (ALENSA) `001Se00000RzlNR`; frames category
  `0ZG7T000000PB0fWAG`, sunglasses `0ZG7T000000PB0gWAG`.
- Search works via the site UI at `/cs/global-search/{urlencoded term}`; the page
  issues `/…/search/products?searchTerm=…` (e.g. "Marc Jacobs MARC 496" → 3
  results). **Direct API calls are CSRF-blocked** (400/403) — must go through the
  logged-in page, not raw requests.
- **Product images are PUBLIC and constructable** (no auth to download):
  `https://safilo-pd-cdn002.safilo.com/damapi/damimage/public/sfcc.getimagenofb?modelCode={m}&colorCode={c}&detail=00&imagesize=medium`
  (verified: real JPEG). `imagesize=large` alone 500s; `detail=00&imagesize=medium`
  works. Rendered catalogue tiles expose these URLs (so modelCode+colorCode are
  readable from the page).
- The user's color codes match Safilo's (`807`, etc.), and the DAM uses the same
  codes → exact-color images are constructable once the modelCode is known.
- **The Salesforce session does NOT persist** across browser closes (logs out
  even headed). So the login can only be used *within one live browser session*.

## Design

Because the session can't be saved but images are public+constructable, the login
is needed only to turn model NAMES into Safilo `modelCode`s. We do that once per
refresh by browsing the catalogue during a live login, caching a local index;
matching and downloads are then offline.

New module `safilo.py` (no Streamlit import). app.py gains a "Match via Safilo"
button mirroring the Luxottica one.

### `safilo.py`

- Constants: `SAFILO_PROFILE_DIR = ./safilo_profile`, DAM base URL, store/category
  ids, `INDEX_CACHE = safilo_catalog_index.json`.
- `open_context(headless)` — persistent msedge context on `safilo_profile`
  (reuse `fetcher._proactor_loop_policy`).
- `is_logged_in(ctx)` — navigate a catalogue URL; logged in if the URL is NOT the
  `/cs/login…` redirect and product tiles are present.
- `login(timeout=600)` — open a VISIBLE window on the frames category; poll until
  `is_logged_in`; return bool. (Kept open by the caller for the index build.)
- `build_index(ctx, progress=None)` — with a live logged-in `ctx`, enumerate the
  frames + sunglasses catalogues and scrape each tile into
  `{"modelText","modelCode","colorCode","norm"}` where `modelText` is the tile's
  displayed model name and `modelCode`/`colorCode` come from the tile image URL
  (`getimagenofb?modelCode=…&colorCode=…`). `norm = normalize(modelText)`.
  **The exact enumeration mechanism (SPA pagination vs. capturing the page's
  `search/products` + `products?ids=` responses) is confirmed in the plan's first
  live task before the rest is built.**
- `save_index(models)` / `load_index()` — cache to `INDEX_CACHE` with a timestamp;
  no age gate (user refreshes explicitly, since it costs a login).
- `normalize(s)` / `model_key` — same rules as luxottica (uppercase, strip
  non-alphanumeric); reuse by importing from `luxottica` to stay DRY.
- `match(name, index) -> {"modelCode","colorCode","modelText"} | None` — normalize
  the name; find the index entry whose `norm` (or modelText tokens) best matches
  (longest/most-specific), and take the color code from the name (the alphanumeric
  color token, e.g. `807`) if present, else the index entry's default colorCode.
- `image_url(model_code, color_code) -> str` — build the public DAM URL.
- Download uses `fetcher.download_url_bytes` (public image).

### App integration (`app.py`)

Add a **"Match via Safilo"** button next to "Match via EssilorLuxottica" (a third
`do_safilo` action). New session state: none beyond reusing `images`, `applied`,
and an `el_variants`-style `safilo_variants` for ambiguous picks.

On click:
1. `open_context(headless=False)`; if `not is_logged_in`: run `login()` (visible
   window) and, once in, keep the same context.
2. `load_index()`; if missing/empty, `build_index()` (progress bar) and
   `save_index`. Offer a small "Refresh Safilo catalogue" control to force a
   rebuild.
3. For each named frame not yet imaged: `match(name, index)`.
   - Match with a color → construct `image_url`, `download_url_bytes`, store
     (source `"safilo"`). If that exact-color image fails to download (bad combo),
     fall back to the index entry's default colorCode.
   - Ambiguous (several plausible models) → stash candidates in
     `safilo_variants[idx]` for a thumbnail pick (reuse the color-pick UI shape,
     downloading the chosen tile's constructed image).
4. Results label shows `"✅ safilo image"` (same non-barcode rule); ZIP counts a
   `safilo` bucket alongside barcode/EssilorLuxottica/manual.

## Error handling

- Not logged in / session died mid-run → detected via `is_logged_in`; prompt the
  login; never crash. Index build only saved on completion.
- A name that matches nothing → left for other sources.
- Image URL 500/blank → try default color; if still failing, skip (frame stays
  for manual).

## Testing

- **Pure (unit):** `normalize`, `match` (name → modelCode + color from a small
  hand-built index fixture; longest-match; color-token extraction; no-match →
  None), `image_url` construction.
- **Live (opt-in `RUN_LIVE=1`, needs a fresh login):** `build_index` yields >100
  models with modelCodes; `image_url` for a known model+color downloads real JPEG
  bytes via `download_url_bytes`.
- **app.py**: controller verifies the button in the real app (login → build →
  match a Safilo name like a Hugo Boss frame → image; ambiguous → pick; ZIP).

## Out of scope

- Persisting the Safilo login (technically not possible here).
- Non-Safilo, non-Luxottica brands (still barcode/manual).
- Buying/pricing features.

## Notes

- NOT a git repo; skip git.
- `safilo.py` stays Streamlit-free; matching pure/unit-tested; network functions
  take `ctx`.
- `safilo_profile/` and `safilo_catalog_index.json` are local; the profile holds
  session data — do not share.
- Discovery scripts `discovery_safilo.py` / `discovery_safilo2.py` retained.
