# EssilorLuxottica Catalogue Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an EssilorLuxottica source that matches frames by name to the authenticated B2B catalogue and downloads the official image (exact color when the code matches; otherwise a color-thumbnail pick).

**Architecture:** New `luxottica.py` — pure matching helpers (unit-tested) + authenticated API functions over a saved Edge profile (`el_profile`, msedge persistent context, cookie auth). `app.py` gains a separate "Match via EssilorLuxottica" button and a color-pick UI. Official images are public URLs, downloaded with the existing `fetcher.download_url_bytes`.

**Tech Stack:** Python, Playwright (msedge channel), Streamlit, pytest.

---

## File Structure

- `luxottica.py` — CREATE: matching (pure) + catalogue API (network).
- `app.py` — MODIFY (full rewrite): EL button, match loop, color-pick UI.
- `tests/test_luxottica.py` — CREATE: unit tests (pure) + opt-in live tests.

Discovery scripts (`discovery.py`, `discovery2.py`) and `el_profile/` already exist and stay.

---

## Task 1: Matching logic (pure, TDD)

**Files:**
- Create: `luxottica.py` (matching section)
- Test: `tests/test_luxottica.py`

- [ ] **Step 1: Write the failing tests** — create `tests/test_luxottica.py`:

```python
from luxottica import normalize, model_key, match_model, match_color

INDEX = [
    {"partNumber": "0MU 01YV", "brand": "MU", "image": "http://img/mu01yv", "norm": "MU01YV"},
    {"partNumber": "0PO0649", "brand": "PO", "image": "http://img/po0649", "norm": "PO0649"},
    {"partNumber": "0OO9431", "brand": "OO", "image": "http://img/oo9431", "norm": "OO9431"},
]


def test_normalize_strips_and_uppercases():
    assert normalize("0MU 01YV") == "0MU01YV"
    assert normalize("12w1o1 ") == "12W1O1"
    assert normalize(None) == ""


def test_model_key_drops_single_leading_zero():
    assert model_key("0MU 01YV") == "MU01YV"
    assert model_key("0PO0649") == "PO0649"


def test_match_model_finds_miu_miu_and_color_guess():
    m = match_model("Miu Miu MU 01YV 12W1O1", INDEX)
    assert m is not None
    assert m["partNumber"] == "0MU 01YV"
    assert m["colorGuess"] == "12W1O1"


def test_match_model_persol():
    m = match_model("Persol PO0649 95/31", INDEX)
    assert m["partNumber"] == "0PO0649"


def test_match_model_longest_wins():
    idx = INDEX + [{"partNumber": "0MU 01", "brand": "MU", "image": "x", "norm": "MU01"}]
    m = match_model("Miu Miu MU 01YV 12W1O1", idx)
    assert m["partNumber"] == "0MU 01YV"  # MU01YV beats MU01


def test_match_model_no_match_returns_none():
    assert match_model("Hugo Boss BOSS 1949 FWM", INDEX) is None


def test_match_color_exact_and_miss():
    variants = [
        {"colorCode": "12W1O1", "partNumber": "0MU 01YV_12W1O1", "image": "http://i/a"},
        {"colorCode": "14L1O1", "partNumber": "0MU 01YV_14L1O1", "image": "http://i/b"},
    ]
    assert match_color(variants, "12W1O1")["image"] == "http://i/a"
    assert match_color(variants, "99Z9Z9") is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_luxottica.py -v`
Expected: `ModuleNotFoundError: No module named 'luxottica'`.

- [ ] **Step 3: Implement the pure section** — create `luxottica.py` with:

```python
# luxottica.py — match frames by name to the EssilorLuxottica catalogue and
# fetch official images. Pure matching helpers + authenticated API functions.
import re


def normalize(s):
    """Uppercase, keep only A-Z/0-9 (drops spaces, slashes, punctuation)."""
    return re.sub(r"[^A-Za-z0-9]", "", s or "").upper()


def model_key(part_number):
    """Normalized model key for matching: partNumber without its leading '0'.

    The catalogue prefixes models with '0' (e.g. '0MU 01YV', '0PO0649') but the
    user's names omit it ('Miu Miu MU 01YV …'), so we strip one leading zero.
    """
    n = normalize(part_number)
    return n[1:] if n.startswith("0") else n


def match_model(name, index):
    """Find the catalogue model whose key is contained in the (normalized) name.

    Returns {"partNumber","brand","image","colorGuess"} for the LONGEST matching
    key (most specific), or None. colorGuess = the 6 alphanumerics right after
    the matched key in the normalized name (the color code, e.g. '12W1O1').
    """
    nn = normalize(name)
    best = None
    for entry in index:
        key = entry["norm"]
        if key and key in nn and (best is None or len(key) > len(best["norm"])):
            best = entry
    if best is None:
        return None
    pos = nn.find(best["norm"]) + len(best["norm"])
    color_guess = nn[pos:pos + 6]
    return {
        "partNumber": best["partNumber"],
        "brand": best["brand"],
        "image": best["image"],
        "colorGuess": color_guess,
    }


def match_color(variants, color_guess):
    """Return the variant whose colorCode equals color_guess (normalized), else None."""
    cg = normalize(color_guess)
    if not cg:
        return None
    for v in variants:
        if normalize(v["colorCode"]) == cg:
            return v
    return None
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_luxottica.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit** — SKIP (not a git repo).

---

## Task 2: Catalogue API (network, live tests)

**Files:**
- Modify: `luxottica.py` (append API section)
- Test: `tests/test_luxottica.py` (append live tests)

- [ ] **Step 1: Append live tests** to `tests/test_luxottica.py`:

```python
import os
import pytest

live = pytest.mark.skipif(os.environ.get("RUN_LIVE") != "1",
                          reason="set RUN_LIVE=1 (needs the saved EL session)")


@live
def test_logged_in_and_index_and_variants():
    import luxottica
    with luxottica.open_context(headless=True) as ctx:
        assert luxottica.is_logged_in(ctx), "EL session not logged in — run luxottica.login() first"
        index = luxottica.build_catalog_index(ctx)
        assert len(index) > 1000
        assert all("norm" in m and m["image"] for m in index[:5])
        variants = luxottica.get_variants(ctx, "0MU 01YV")
        codes = [v["colorCode"] for v in variants]
        assert "12W1O1" in codes
        assert all(v["image"].startswith("http") for v in variants)
```

- [ ] **Step 2: Run to verify it fails**

Run: `RUN_LIVE=1 python -m pytest tests/test_luxottica.py::test_logged_in_and_index_and_variants -v`
Expected: FAIL with `AttributeError: module 'luxottica' has no attribute 'open_context'`.

- [ ] **Step 3: Append the API section** to `luxottica.py`:

```python
import json
import pathlib
import time
import urllib.parse
from contextlib import contextmanager

from playwright.sync_api import sync_playwright

from fetcher import _proactor_loop_policy  # reuse Windows event-loop fix

BASE = "https://my.essilorluxottica.com"
EL_PROFILE_DIR = str(pathlib.Path(__file__).parent / "el_profile")
INDEX_CACHE = pathlib.Path(__file__).parent / "el_catalog_index.json"
PLP_PATH = "/myl-hu/cs-CZ/plp/frames"
USERCONTEXT = BASE + "/fo-bff/api/priv/v1/myl-hu/usercontext"
LISTING = (BASE + "/fo-bff/api/priv/v1/myl-hu/cs-CZ/categories/3074457345616677185/"
           "contents/3562826?pageSize=24&pageNumber={page}&orderBy=RELEVANCE&facet=noBrand")
VARIANTS = BASE + "/fo-bff/api/priv/v1/myl-hu/cs-CZ/products/partnumber/{pn}/variants"


@contextmanager
def open_context(headless=True):
    with _proactor_loop_policy():
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                EL_PROFILE_DIR, channel="msedge", headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1440, "height": 900},
            )
            try:
                yield ctx
            finally:
                ctx.close()


def _ensure_origin(ctx):
    """Make sure a page is on the EL domain so request cookies are in scope."""
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    if "my.essilorluxottica.com" not in (page.url or ""):
        try:
            page.goto(BASE + PLP_PATH, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass
    return page


def is_logged_in(ctx):
    _ensure_origin(ctx)
    try:
        r = ctx.request.get(USERCONTEXT)
        return r.ok
    except Exception:
        return False


def get_variants(ctx, part_number):
    """Return [{'colorCode','partNumber','image'}] for a model partNumber."""
    _ensure_origin(ctx)
    try:
        r = ctx.request.get(VARIANTS.format(pn=urllib.parse.quote(part_number)))
        if not r.ok:
            return []
        cev = r.json().get("data", {}).get("catalogEntryView", [])
    except Exception:
        return []
    out = []
    for v in cev:
        img = v.get("fullImage")
        if not img:
            continue
        pn = v.get("partNumber", "")
        color = pn.split("_")[-1] if "_" in pn else ""
        out.append({"colorCode": color, "partNumber": pn, "image": img})
    return out


def build_catalog_index(ctx, progress=None):
    """Page the listing API into [{'partNumber','brand','image','norm'}]."""
    _ensure_origin(ctx)
    models = []
    for page_num in range(1, 251):  # safety cap (~169 pages real)
        try:
            r = ctx.request.get(LISTING.format(page=page_num))
            if not r.ok:
                break
            data = r.json().get("data", {})
        except Exception:
            break
        rl = data.get("resultList", [])
        if not rl:
            break
        for x in rl:
            pn = x.get("partNumber")
            img = x.get("fullImage")
            if pn and img:
                models.append({"partNumber": pn, "brand": x.get("manufacturer", ""),
                               "image": img, "norm": model_key(pn)})
        total = data.get("recordSetTotal", 0)
        if progress:
            progress(len(models), total)
        start = data.get("recordSetStartNumber", 0)
        cnt = data.get("recordSetCount", len(rl))
        if total and start + cnt >= total:
            break
    return models


def load_or_build_index(ctx, max_age_days=7, progress=None):
    """Return a cached index unless missing/stale, else build and cache it."""
    if INDEX_CACHE.exists():
        try:
            blob = json.loads(INDEX_CACHE.read_text(encoding="utf-8"))
            if time.time() - blob.get("built", 0) < max_age_days * 86400 and blob.get("models"):
                return blob["models"]
        except Exception:
            pass
    models = build_catalog_index(ctx, progress=progress)
    if models:
        INDEX_CACHE.write_text(json.dumps({"built": time.time(), "models": models}),
                               encoding="utf-8")
    return models


def login(timeout=300):
    """Open a VISIBLE Edge window for the user to log in; poll until authed."""
    with open_context(headless=False) as ctx:
        _ensure_origin(ctx)
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(5)
            if is_logged_in(ctx):
                return True
        return False
```

- [ ] **Step 4: Run to verify it passes**

Run: `RUN_LIVE=1 python -m pytest tests/test_luxottica.py -v`
Expected: all pure tests + the live test PASS. (If the live test reports "not logged in", run `RUN_LIVE=1 python -c "import luxottica; print(luxottica.login())"`, log in, then re-run.)

- [ ] **Step 5: Commit** — SKIP (not a git repo).

---

## Task 3: App integration

**Files:**
- Modify (full rewrite): `app.py`

- [ ] **Step 1: Replace `app.py` entirely** with EXACTLY this content:

```python
# app.py
import io
import re
import zipfile

import pandas as pd
import streamlit as st

from barcode_parser import parse_records
from fetcher import make_browser, fetch_image, search_links, download_url_bytes
import luxottica

st.set_page_config(page_title="Glasses Image Downloader", page_icon="📷")
st.title("📷 Glasses Image Downloader")
st.caption("Barcode + EssilorLuxottica matching, with manual fill/replace.")


def _safe_name(text):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
    return cleaned or "image"


def _store_image(idx, image_bytes, extension, source):
    st.session_state.images[idx] = {"bytes": image_bytes, "ext": extension or ".jpg", "source": source}


for key, default in [("records", []), ("results", []), ("images", {}),
                     ("applied", {}), ("el_variants", {}), ("el_needs_login", False)]:
    if key not in st.session_state:
        st.session_state[key] = default

# --- 1. Input ---
st.subheader("1. Provide frames")
col1, col2 = st.columns(2)
with col1:
    pasted = st.text_area("Paste (barcode, or `barcode, name` per line)", height=180,
                          placeholder="197737257521, Hugo Boss BOSS 1949 FWM")
with col2:
    uploaded = st.file_uploader("…or upload a file", type=["xlsx", "xls", "csv", "txt"])

records = []
if uploaded is not None:
    records = parse_records(file_bytes=uploaded.getvalue(), filename=uploaded.name)
elif pasted.strip():
    records = parse_records(text=pasted)

if records:
    wn = sum(1 for r in records if r["name"])
    wb = sum(1 for r in records if r["barcode"])
    st.info(f"{len(records)} frame(s) ready — {wb} with a barcode, {wn} with a name.")

delay = st.slider("Delay between barcodes (seconds)", 0.0, 5.0, 1.5, 0.5)

# --- 2. Run barcode lookup ---
st.subheader("2. Look up by barcode")
if st.button("Run barcode lookup", type="primary", disabled=not records):
    st.session_state.records = records
    st.session_state.results = []
    st.session_state.images = {}
    st.session_state.applied = {}
    st.session_state.el_variants = {}
    st.session_state.pop("redo_select", None)
    progress = st.progress(0.0, text="Starting browser…")
    with make_browser() as browser:
        for i, rec in enumerate(records):
            progress.progress((i + 1) / len(records), text=f"[{i+1}/{len(records)}] {rec['barcode'] or rec['name']}")
            if rec["barcode"]:
                result = fetch_image(browser, rec["barcode"], delay=delay)
                if result.status == "ok" and result.image_bytes:
                    _store_image(i, result.image_bytes, result.extension, "barcode")
                    st.session_state.results.append({"status": "found"})
                    continue
            st.session_state.results.append({"status": "needs_image" if rec["name"] else "no_source"})
    progress.progress(1.0, text="Done.")

if st.session_state.results:
    records = st.session_state.records
    results = st.session_state.results
    images = st.session_state.images

    # --- 3. EssilorLuxottica matching (separate, on-demand) ---
    st.subheader("3. Match via EssilorLuxottica")
    st.caption("Official images for Luxottica brands (Ray-Ban, Oakley, Persol, Prada, Miu Miu, Versace…).")
    if st.button("Match via EssilorLuxottica"):
        with luxottica.open_context(headless=True) as ctx:
            if not luxottica.is_logged_in(ctx):
                st.session_state.el_needs_login = True
            else:
                st.session_state.el_needs_login = False
                prog = st.progress(0.0, text="Loading catalogue…")
                index = luxottica.load_or_build_index(
                    ctx, progress=lambda n, t: prog.progress(min(n / t, 1.0) if t else 0.0,
                                                              text=f"Catalogue: {n}/{t or '?'}"))
                prog.progress(1.0, text=f"Catalogue ready ({len(index)} models). Matching…")
                todo = [i for i, r in enumerate(records) if records[i]["name"] and i not in images]
                for n, i in enumerate(todo):
                    m = luxottica.match_model(records[i]["name"], index)
                    if not m:
                        continue
                    variants = luxottica.get_variants(ctx, m["partNumber"])
                    if not variants:
                        continue
                    hit = luxottica.match_color(variants, m["colorGuess"])
                    if hit:
                        dl = download_url_bytes(hit["image"])
                        if dl:
                            _store_image(i, dl[0], dl[1], "luxottica")
                    else:
                        st.session_state.el_variants[i] = variants
                prog.progress(1.0, text="EssilorLuxottica matching done.")
                st.rerun()
    if st.session_state.el_needs_login:
        st.warning("Your EssilorLuxottica session is expired or not set up.")
        if st.button("Log in to EssilorLuxottica"):
            with st.spinner("Opening a browser window — log in there…"):
                ok = luxottica.login()
            st.session_state.el_needs_login = not ok
            if ok:
                st.success("Logged in. Click 'Match via EssilorLuxottica' again.")

    # --- 4. Results table ---
    st.subheader("4. Results")

    def _label(i):
        status = results[i]["status"]
        if i in images and images[i]["source"] != "barcode":
            return f"✅ {images[i]['source']} image"
        if status == "found":
            return "✅ found by barcode"
        if i in st.session_state.el_variants:
            return "🎨 pick a color (EL)"
        return {"needs_image": "✋ needs image", "no_source": "❌ no barcode & no name"}[status]

    rows = [{"Barcode": records[i]["barcode"], "Name": records[i]["name"], "Status": _label(i)}
            for i in range(len(records))]
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    # --- 5. EssilorLuxottica color pick ---
    el_pick = [i for i in st.session_state.el_variants if i not in images]
    if el_pick:
        st.subheader("5. Pick a color (EssilorLuxottica)")
        for i in el_pick:
            st.markdown(f"**{records[i]['name']}**")
            variants = st.session_state.el_variants[i]
            cols = st.columns(min(len(variants), 5) or 1)
            for j, v in enumerate(variants[:10]):
                with cols[j % len(cols)]:
                    st.image(v["image"], width=120, caption=v["colorCode"] or "?")
                    if st.button("Use this", key=f"el_{i}_{v['colorCode']}_{j}"):
                        if st.session_state.applied.get(f"el_{i}") != v["partNumber"]:
                            dl = download_url_bytes(v["image"])
                            if dl:
                                _store_image(i, dl[0], dl[1], "luxottica")
                                st.session_state.applied[f"el_{i}"] = v["partNumber"]
                                st.rerun()
            st.divider()

    # --- 6. Pick frames to redo/replace ---
    imaged = [i for i in range(len(records)) if i in images]
    if imaged:
        st.subheader("6. Replace an image you don't like")
        st.multiselect("Frames to redo", options=imaged,
                       format_func=lambda i: f"{records[i]['barcode'] or '(no barcode)'} — {records[i]['name'] or '(no name)'}",
                       key="redo_select")
    redo = list(st.session_state.get("redo_select", []))

    # --- 7. Fill / replace by name (paste URL / upload) ---
    misses = [i for i, r in enumerate(results) if r["status"] == "needs_image" and i not in images]
    fill_list = sorted(set(misses) | set(redo))
    if fill_list:
        st.subheader("7. Fill / replace images")
        for i in fill_list:
            rec = records[i]
            st.markdown(f"**{rec['name'] or '(no name)'}**  \n`{rec['barcode'] or 'no barcode'}`")
            if i in images:
                st.image(images[i]["bytes"], width=160, caption=f"current: {images[i]['source']}")
            if rec["name"]:
                links = search_links(rec["name"])
                st.markdown("Search: " + " · ".join(f"[{label}]({url})" for label, url in links.items()))
            c1, c2 = st.columns([2, 1])
            with c1:
                url = st.text_input("Paste image URL", key=f"url_{i}")
                if url and st.session_state.applied.get(f"url_{i}") != url:
                    fetched = download_url_bytes(url)
                    if fetched:
                        _store_image(i, fetched[0], fetched[1], "url")
                        st.session_state.applied[f"url_{i}"] = url
                        st.rerun()
                    else:
                        st.warning("Couldn't fetch that URL — try uploading the file instead.")
            with c2:
                up = st.file_uploader("…or upload", type=["jpg", "jpeg", "png", "webp"], key=f"file_{i}")
                if up is not None and st.session_state.applied.get(f"file_{i}") != up.file_id:
                    ext = "." + up.name.rsplit(".", 1)[-1].lower()
                    _store_image(i, up.getvalue(), ext, "upload")
                    st.session_state.applied[f"file_{i}"] = up.file_id
                    st.rerun()
            st.divider()

    # --- 8. ZIP ---
    st.subheader("8. Download")
    by_barcode = sum(1 for v in images.values() if v["source"] == "barcode")
    el_count = sum(1 for v in images.values() if v["source"] == "luxottica")
    manual = len(images) - by_barcode - el_count
    st.write(f"{len(images)} image(s): {by_barcode} barcode, {el_count} EssilorLuxottica, {manual} manual.")
    if images:
        zip_buf = io.BytesIO()
        used = set()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, data in images.items():
                base = records[i]["barcode"] or _safe_name(records[i]["name"])
                fname = f"{base}{data['ext']}"
                n = 2
                while fname in used:
                    fname = f"{base}_{n}{data['ext']}"; n += 1
                used.add(fname)
                zf.writestr(fname, data["bytes"])
        st.download_button("⬇️ Download all as ZIP", data=zip_buf.getvalue(),
                           file_name="glasses_images.zip", mime="application/zip")
    else:
        st.warning("No images yet.")
```

- [ ] **Step 2: Boot test**

Run (Bash):
```
cd "C:\Users\blank\Desktop\Random codes\barcode-image-downloader" && python -m py_compile app.py luxottica.py && (python -m streamlit run app.py --server.headless true --server.port 8613 >/tmp/st13.log 2>&1 &) && sleep 12 && curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8613/_stcore/health && cat /tmp/st13.log
```
Expected: `200`, no traceback. Then stop the process on port 8613.

- [ ] **Step 3: Commit** — SKIP (not a git repo).

---

## Controller verification (after Task 3)

Controller verifies in the real running app (session already logged in):
1. Paste `, Miu Miu MU 01YV 12W1O1` (leading comma → name only, no barcode) and `, Miu Miu MU 01YV 99Z9Z9` (bad color). Run barcode lookup (both become needs_image).
2. Click **Match via EssilorLuxottica** → catalogue builds (progress), then: the exact-color frame auto-fills ("✅ luxottica image" / EL count = 1); the bad-color frame shows a **color-pick** section with thumbnails.
3. Click a color's **"Use this"** → that frame fills (EL count = 2).
4. **Download ZIP** → contains both images named by `_safe_name(name)` (no barcode).

---

## Notes

- `luxottica.py` matching is pure/unit-tested; API functions take `ctx`; no Streamlit import.
- Official images are public URLs → downloaded via `fetcher.download_url_bytes`.
- `el_catalog_index.json` caches the catalogue (7-day freshness); rebuilt on demand.
- The color-pick "Use this" buttons are guarded by `applied["el_<idx>"]` to avoid the rerun-loop class of bug.
```
