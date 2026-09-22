# EssilorLuxottica Catalogue Source — Design

**Date:** 2026-06-19
**Author:** bgal@alensa.eu

## Purpose

Add a new image source: match frames by **name** against the authenticated
EssilorLuxottica B2B catalogue and download the **official** product image —
exact, high-quality, and (for matching color codes) fully automatic. Covers
Luxottica-made brands (Ray-Ban, Oakley, Persol, Prada, Miu Miu, Versace, etc.).

## Discovery findings (verified live)

- Auth: a saved Edge profile (`el_profile`) keeps the login; headless Playwright
  reuses it, and the internal JSON API accepts the session cookies. No password
  stored. (User logs in once via a visible Edge window; re-login when it expires.)
- **Listing API** (models): `GET /fo-bff/api/priv/v1/myl-hu/cs-CZ/categories/3074457345616677185/contents/3562826?pageSize=24&pageNumber=N&orderBy=RELEVANCE&facet=noBrand`
  → `data.resultList[]`, each: `partNumber` (e.g. `0PO0649`, `0MU 01YV`),
  `manufacturer` (brand code), `fullImage` (official image URL),
  `recordSetTotal` ≈ 4045. **`pageSize` is capped at 24 server-side**, so the
  full catalogue = ~169 paged calls.
- **Variants API** (colors): `GET /fo-bff/api/priv/v1/myl-hu/cs-CZ/products/partnumber/{partNumber}/variants`
  → `data.catalogEntryView[]`, each: `partNumber` (`0MU 01YV_12W1O1`),
  attribute `DL_COLOR_CODE` (`12W1O1`), `fullImage` (per-color official image).
- **partNumber spacing varies by brand** (`0PO0649` vs `0MU 01YV`) → matching
  must normalize (strip spaces, uppercase).
- The user's names encode model + color exactly: "Miu Miu MU 01YV 12W1O1" →
  model `0MU 01YV`, color `12W1O1` (confirmed present as a real variant).

## Architecture

New module `luxottica.py` (no Streamlit import); app.py gains a separate button.
Engine and other sources unchanged.

### `luxottica.py`

- `EL_PROFILE_DIR` = `./el_profile`. `BASE = https://my.essilorluxottica.com`.
- `open_context(headless=True)` — context manager yielding a persistent msedge
  context on `EL_PROFILE_DIR`. Reuses the existing browser-policy helper pattern
  (Windows Proactor loop) from fetcher if needed.
- `is_logged_in(context) -> bool` — request the usercontext endpoint
  (`/fo-bff/api/priv/v1/myl-hu/usercontext`); True if 200 with user data, False
  if 401/redirect. Used to prompt re-login.
- `build_catalog_index(context, progress=None) -> list[dict]` — page the listing
  API from pageNumber=1 until `recordSetStartNumber+count >= recordSetTotal`,
  collecting `{"partNumber","brand","image","norm"}` where
  `norm = normalize(partNumber)`. Cache to `el_catalog_index.json` with a
  timestamp; `load_or_build_index(context, max_age_days=7)` returns the cached
  list unless missing/stale.
- `normalize(s) -> str` — uppercase, keep only A–Z/0–9 (drops spaces, slashes).
- `match_model(name, index) -> dict | None` — `nn = normalize(name)`; among index
  entries whose `norm` is a substring of `nn`, return the one with the LONGEST
  `norm` (most specific). None if no match. Also return the leftover color guess:
  the alphanumerics in `nn` immediately AFTER the matched `norm` (first 6 chars).
  Shape: `{"partNumber","brand","image","colorGuess"}`.
- `get_variants(context, partNumber) -> list[dict]` — call variants API; return
  `[{"colorCode","partNumber","image"}]` from `catalogEntryView` (colorCode from
  `DL_COLOR_CODE`).
- `match_color(variants, colorGuess) -> dict | None` — exact case-insensitive
  match of `colorGuess` to a variant `colorCode`; else None.
- `download_image(context, url) -> tuple[bytes,str] | None` — download an
  official image URL via the authenticated context request; returns (bytes, ext)
  or None. (Used because the image host may require the session.)

### Matching outcome per frame (model found)

1. `match_model` hits → call `get_variants`.
2. `match_color` hits → **auto-accept** that variant's image (exact).
3. color miss but variants exist → queue the frame's variants for **thumbnail
   pick** (review).
4. no model match → leave the frame untouched (barcode/manual handles it).

## App integration (`app.py`)

A separate button **"Match via EssilorLuxottica"** in the results area (only
shown after a barcode run, operating on frames that have a name). New session
state: `el_variants` (idx -> list of `{colorCode,image,partNumber}` awaiting a
color pick).

On click:
1. `open_context()`; if `not is_logged_in` → show an error with a **"Log in to
   EssilorLuxottica"** button (runs `login` flow: opens a VISIBLE context to
   `BASE` so the user logs in; on next run the saved session works). Stop.
2. `load_or_build_index` (progress bar while building).
3. For each record with a name and not already imaged by barcode:
   - `m = match_model`. None → skip (leave for other sources).
   - `variants = get_variants(m.partNumber)`.
   - `match_color(variants, m.colorGuess)` → store image (source `"luxottica"`),
     auto-accepted.
   - else → `st.session_state.el_variants[idx] = variants` (for thumbnail pick).
4. Results table label: matched frames show `"✅ luxottica image"` (reuses the
   non-"barcode" source label rule). 

**Color-pick UI** (new section, shown when `el_variants` non-empty): for each
such frame, show the name + a row of the model's color thumbnails
(`st.image` per variant with the color code as caption) and a **"Use this"**
button per color. Clicking downloads that variant image and stores it
(source `"luxottica"`), then clears the frame from `el_variants` and reruns.
Guard re-processing with the existing `applied` pattern (key
`el_{idx}_{colorCode}`).

**ZIP**: unchanged — picks up `luxottica`-sourced images like any other.

## Error handling

- Not logged in / session expired → detected via `is_logged_in`; prompt
  re-login; never crash.
- Variants/listing call fails for one frame → that frame is skipped (left for
  other sources), loop continues.
- `download_image` failure → frame not stored; remains for barcode/manual.
- Index build interrupted/partial → cache only on full completion; otherwise
  rebuild next time.

## Testing

- **`normalize` / `match_model` / `match_color` (pure, unit):** real examples —
  "Miu Miu MU 01YV 12W1O1" → model norm `0MU01YV`, colorGuess `12W1O1`;
  spacing (`0PO0649`) and brand-word removal; longest-match wins; no-match → None.
  Uses a small hand-built index fixture (no network).
- **Live (opt-in `RUN_LIVE=1`, needs the saved session):** `build_catalog_index`
  returns >1000 models with image URLs; `get_variants("0MU 01YV")` returns
  variants incl. color `12W1O1`; `download_image` of a returned URL yields bytes.
- **app.py**: glue; controller verifies in the real app (button → auto-match a
  Miu Miu name → image; a color-miss → thumbnail pick → image; ZIP contains them).

## Out of scope

- Non-Luxottica brands (Safilo etc.) — handled by barcode/manual.
- Auto re-login without the user (session refresh is manual).
- Buying/cart/price features of the portal.

## Notes

- NOT a git repo; implementers skip git steps.
- `luxottica.py` stays Streamlit-free; matching logic is pure and unit-tested;
  network functions take the `context`.
- The `el_profile` dir and `el_catalog_index.json` are local caches (gitignore
  if a repo is ever created; they may contain session data — do not share).
