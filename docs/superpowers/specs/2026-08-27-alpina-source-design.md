# Alpina Catalogue Source — Design

**Date:** 2026-08-27
**Author:** bgal@alensa.eu

## Purpose

Add an Alpina source so the tool downloads official images for Alpina eyewear
(sunglasses / sports & ski glasses) by matching the frame NAME to
alpina-sports.com. Alpina is a new supplier; the input file is Alpina products
(name + EAN), e.g. "Alpina DEFEY 2 black matt".

## Discovery findings (verified live, public HTTP — no login)

- alpina-sports.com is a public Shopware store. **No login, no session, no CSRF.**
- Search: `GET https://www.alpina-sports.com/de/de/search?q=<term>` returns
  server-rendered HTML (plain `requests`/`urllib` — no browser/JS needed).
- Search is **fuzzy**: it returns mixed categories (helmets, protectors, eyewear)
  and searching the full name (with color) returns worse results than searching
  the model alone. EAN search returns nothing → match by name.
- Result tiles: `<a ... class="...product--title..." href="<product url>">NAME</a>`.
  Eyewear product URLs are under `/eyewear/` (sportbrillen, lifestylebrillen,
  kinder) or `/skibrillen/`.
- Product page lists color variants with titles like "black matt / mirror blue",
  "black matt / mirror red" (frame color / lens color).
- Images are **public** on CloudFront (`d12nqbfxx2yid0.cloudfront.net/media/image/
  …/A<article>_Main…_1200x1200.jpg`), multiple views per article (Main/F1/S1/A1),
  in sizes 200/600/1200. Verified downloadable (real JPEG, no auth).

## Architecture

New module `alpina.py` — pure matching helpers (unit-tested) + fetch/parse
functions. Search and model-matching are plain HTTP. **Per-color images load via
Shopware's variant AJAX (not static HTML), so enumerating a model's color images
uses a headless, login-free browser** (plain `chromium.launch()` — no profile, no
login, no session; none of Safilo's problems). Confirmed live: clicking a frame
color navigates to `?number=<ordernumber>` and swaps the Main image (e.g.
moon-grey → A8645321). Only the **frame color** needs matching — all lens
sub-variants of one frame color share the same frame photo. Image URLs come back
at `_600x600`; swap to `_1200x1200` for full-res (both exist on the CDN).
Downloads via `fetcher.download_url_bytes` (public images). `app.py` gains a
"Match via Alpina" button + an "alpina" bucket.

### `alpina.py`

- `SEARCH_URL = "https://www.alpina-sports.com/de/de/search?q={q}"`.
- `EYEWEAR_PATHS = ("/eyewear/", "/skibrillen/")` — result filter.
- `normalize(s)` — reuse `luxottica.normalize` (uppercase, alphanumeric only).
- `search_query(name)` — strip a leading "ALPINA"/"Alpina", then take tokens up
  to and including the first token that contains a digit or is a roman numeral
  (II/III/IV/…); if none, take the first 3 tokens. Examples:
  "Alpina DEFEY 2 black matt" → "DEFEY 2"; "Alpina MITZO II Cars" → "MITZO II";
  "Alpina RAM 2.0 black matt…" → "RAM 2.0"; "Alpina TURBO PRO YOUTH white matt"
  → "TURBO PRO YOUTH".
- `_http_get(url) -> str | None` — GET with a browser User-Agent, return text or
  None on error.
- `search(name) -> list[dict]` — GET the search page for `search_query(name)`,
  parse tiles into `[{"title","url","norm"}]`, keep only tiles whose url contains
  an `EYEWEAR_PATHS` segment.
- `match_model(name, tiles) -> dict | None` — the eyewear tile whose `norm` is a
  substring of `normalize(name)` (longest wins), or None.
- `product_variants(url) -> list[dict]` — open the product page in a headless
  login-free browser; read the default variant's Main image + colorText, then
  click each remaining frame-color option, wait for the image to change, and read
  its colorText + Main image. De-duplicate by frame color. Each `image` is the
  Main URL with `_600x600`/`@2x` swapped to `_1200x1200`. Returns
  `[{"colorText","image"}]`. (Uses `fetcher._proactor_loop_policy` for the
  Windows event-loop fix; a plain `chromium.launch(headless=True)` — no msedge
  channel, no profile, no login.)
- `_color_words(name) -> str` — the part of the name after the model
  (`search_query`), normalized, used to match color variants.
- `match_color(variants, name) -> dict | None` — the variant whose normalized
  `colorText` best contains the name's color words (longest overlap), or None.
- `resolve(name) -> dict` — orchestrates: returns
  `{"status": "ok", "image": bytes, "ext": str}` on a confident single match;
  `{"status": "choose", "candidates": [{"label","image_url"}]}` when ambiguous
  (multiple eyewear models, or several matching color variants); or
  `{"status": "none"}`. Downloads via `fetcher.download_url_bytes`.

### Hybrid confidence rule

- Exactly one eyewear tile matches the model AND exactly one variant matches the
  color → auto (`"ok"`).
- Multiple candidate models, or multiple matching color variants, or a model
  match with no color match → `"choose"` with candidate thumbnails (each candidate
  = a variant image the user can pick; downloaded on selection).
- No eyewear model match → `"none"` (left for manual).

## App integration (`app.py`)

A "Match via Alpina" button beside the others (no login/window — it's HTTP, fast).
New session state `alpina_variants` (idx -> candidate list) for the pick UI,
reusing the EssilorLuxottica color-pick pattern (thumbnails + "Use this").

On click, for each named frame not yet imaged:
- `r = alpina.resolve(name)`.
- `"ok"` → store bytes (source `"alpina"`).
- `"choose"` → stash `r["candidates"]` in `alpina_variants[idx]` for a pick.
- `"none"` → skip.

Pick UI (section, when `alpina_variants` non-empty): per frame, show candidate
thumbnails (`st.image(url)`) + "Use this" → download that candidate's image and
store (source `"alpina"`); guarded by the existing `applied` dict.

Results label shows `"✅ alpina image"`; ZIP counts an `alpina` bucket alongside
barcode / EssilorLuxottica / Safilo / manual.

## Error handling

- Search/product HTTP failure for one frame → skip it (leave for other sources);
  never crash the loop.
- Image download failure → skip that candidate/frame.
- No eyewear match / no color match → `"none"` / `"choose"` as above.

## Testing

- **Pure (unit):** `search_query` (model extraction incl. roman numerals + the
  no-number fallback), `match_model` (eyewear substring longest-match), `match_color`
  (color-word overlap), `_color_words`. Hand-built fixtures, no network.
- **Live (opt-in `RUN_LIVE=1`, public — no login):** `search("Alpina DEFEY 2 black
  matt")` returns ≥1 eyewear tile; `product_variants` of a real product yields
  variants with 1200x1200 image URLs; a returned image downloads (>3000 bytes);
  `resolve` on a real name returns "ok" or "choose" with a working image URL.
- **app.py:** controller verifies in the real app against the file's Alpina names.

## Out of scope

- Non-Alpina brands.
- The exact lens sub-variant when several share a frame color (the pick UI covers
  this; auto picks only when a single variant matches).
- Alpina products that aren't eyewear (helmets, protectors).

## Notes

- NOT a git repo; skip git.
- `alpina.py` stays Streamlit-free; matching pure/unit-tested; HTTP functions are
  plain `urllib`/`requests` (no browser, no login) — the most robust source.
- Images are public → `fetcher.download_url_bytes`.
