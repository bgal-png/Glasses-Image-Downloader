# Safilo Catalogue Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Match via Safilo" source that indexes the youandsafilo.com catalogue (during a login), matches frame names to Safilo model/color codes, and downloads the official public image.

**Architecture:** New `safilo.py` — pure matching + `image_url` construction (unit-tested), plus session/index functions that scrape the catalogue during a live login (the session can't persist). Images are public DAM URLs downloaded via `fetcher.download_url_bytes`. `app.py` gains a third match button mirroring EssilorLuxottica.

**Tech Stack:** Python, Playwright (msedge channel), Streamlit, pytest.

**Important reality:** The Salesforce session does NOT persist across browser closes, so index (re)build requires a login. The enumeration scrape in Task 2 is finalized against the live site in that task (a login is required to run it).

---

## File Structure

- `safilo.py` — CREATE: pure (`normalize` reuse, `match`, `image_url`) + network (`open_context`, `is_logged_in`, `login`, `build_index`, `save_index`, `load_index`).
- `app.py` — MODIFY: add the "Match via Safilo" action + a `safilo` source bucket.
- `tests/test_safilo.py` — CREATE: unit tests (pure) + opt-in live test.

---

## Task 1: Pure matching + image URL (TDD)

**Files:**
- Create: `safilo.py` (pure section)
- Test: `tests/test_safilo.py`

- [ ] **Step 1: Create `tests/test_safilo.py`:**

```python
from safilo import normalize, match, image_url

INDEX = [
    {"modelText": "Hugo Boss BOSS 1949", "modelCode": "205918", "colorCode": "R80", "norm": "HUGOBOSSBOSS1949"},
    {"modelText": "Marc Jacobs MARC 496", "modelCode": "207993", "colorCode": "AOZ", "norm": "MARCJACOBSMARC496"},
]


def test_normalize():
    assert normalize("Marc Jacobs MARC 496/SHINY 807/IR") == "MARCJACOBSMARC496SHINY807IR"
    assert normalize(None) == ""


def test_image_url_builds_public_dam_url():
    url = image_url("207993", "807")
    assert url == ("https://safilo-pd-cdn002.safilo.com/damapi/damimage/public/"
                   "sfcc.getimagenofb?modelCode=207993&colorCode=807&detail=00&imagesize=medium")


def test_match_finds_model_and_color_from_name():
    m = match("Marc Jacobs MARC 496/SHINY 807/IR", INDEX)
    assert m["modelCode"] == "207993"
    assert m["colorCode"] == "807"  # color token from the name, not the index default


def test_match_uses_index_default_color_when_name_has_none():
    m = match("Hugo Boss BOSS 1949", INDEX)
    assert m["modelCode"] == "205918"
    assert m["colorCode"] == "R80"  # falls back to index default


def test_match_no_hit_returns_none():
    assert match("Oakley Holbrook", INDEX) is None
```

- [ ] **Step 2: Run `python -m pytest tests/test_safilo.py -v`** → fails (no module safilo).

- [ ] **Step 3: Create `safilo.py` pure section:**

```python
# safilo.py — match frames to the Safilo catalogue and build official image URLs.
import re

from luxottica import normalize  # same normalization (uppercase, alnum only)

DAM = ("https://safilo-pd-cdn002.safilo.com/damapi/damimage/public/"
       "sfcc.getimagenofb?modelCode={model}&colorCode={color}&detail=00&imagesize=medium")

# A Safilo color code is a 3-char alphanumeric token (e.g. 807, AOZ, 6HT).
_COLOR_RE = re.compile(r"(?<![A-Za-z0-9])([0-9A-Za-z]{3})(?![0-9A-Za-z])")


def image_url(model_code, color_code):
    return DAM.format(model=model_code, color=color_code)


def _color_from_name(name):
    """Last 3-char token that looks like a Safilo color code, or None."""
    tokens = _COLOR_RE.findall(name or "")
    # Prefer a token containing a digit (color codes usually do), last one wins.
    digits = [t for t in tokens if any(c.isdigit() for c in t)]
    if digits:
        return digits[-1].upper()
    return tokens[-1].upper() if tokens else None


def match(name, index):
    """Return {'modelCode','colorCode','modelText'} for the best model match, or None.

    Matches the longest index `norm` that is a substring of the normalized name;
    color code is taken from the name when present, else the index entry default.
    """
    nn = normalize(name)
    best = None
    for entry in index:
        key = entry["norm"]
        if key and key in nn and (best is None or len(key) > len(best["norm"])):
            best = entry
    if best is None:
        return None
    color = _color_from_name(name) or best.get("colorCode") or ""
    return {"modelCode": best["modelCode"], "colorCode": color, "modelText": best["modelText"]}
```

- [ ] **Step 4: Run `python -m pytest tests/test_safilo.py -v`** → 5 passed.

- [ ] **Step 5: Commit** — SKIP (not a git repo).

---

## Task 2: Session + catalogue index (LIVE-VERIFIED)

**Files:**
- Modify: `safilo.py` (append network section)
- Test: `tests/test_safilo.py` (append live test)

This task REQUIRES a login. The enumeration scrape below is a starting point;
Step 3b verifies it against the live catalogue and adjusts the tile selectors /
pagination as needed (like the barcodelookup selector confirmation did earlier).

- [ ] **Step 1: Append the live test:**

```python
import os
import pytest

live = pytest.mark.skipif(os.environ.get("RUN_LIVE") != "1",
                          reason="set RUN_LIVE=1 (needs a fresh Safilo login)")


@live
def test_build_index_and_image_download():
    import safilo
    from fetcher import download_url_bytes
    with safilo.open_context(headless=False) as ctx:
        assert safilo.is_logged_in(ctx) or safilo.login_in_context(ctx), "log in when the window opens"
        index = safilo.build_index(ctx)
        assert len(index) > 100
        e = index[0]
        assert e["modelCode"] and e["modelText"]
        dl = download_url_bytes(safilo.image_url(e["modelCode"], e["colorCode"]))
        assert dl is not None and len(dl[0]) > 3000
```

- [ ] **Step 2: Run `RUN_LIVE=1 python -m pytest tests/test_safilo.py::test_build_index_and_image_download -v`** → fails (no `open_context`).

- [ ] **Step 3: Append the network section to `safilo.py`:**

```python
import json
import pathlib
import time
import urllib.parse
from contextlib import contextmanager

from playwright.sync_api import sync_playwright

from fetcher import _proactor_loop_policy

BASE = "https://www.youandsafilo.com"
SAFILO_PROFILE_DIR = str(pathlib.Path(__file__).parent / "safilo_profile")
INDEX_CACHE = pathlib.Path(__file__).parent / "safilo_catalog_index.json"
CATEGORIES = {
    "frames": "0ZG7T000000PB0fWAG",
    "sunglasses": "0ZG7T000000PB0gWAG",
}


@contextmanager
def open_context(headless=True):
    with _proactor_loop_policy():
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                SAFILO_PROFILE_DIR, channel="msedge", headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
                no_viewport=headless is False,
            )
            try:
                yield ctx
            finally:
                ctx.close()


def _page(ctx):
    return ctx.pages[0] if ctx.pages else ctx.new_page()


def _category_url(cat_id):
    return f"{BASE}/cs/category/rootother/x/{cat_id}"


def is_logged_in(ctx):
    page = _page(ctx)
    try:
        page.goto(_category_url(CATEGORIES["frames"]), wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
    except Exception:
        return False
    return "/login" not in page.url and page.evaluate(
        "() => Array.from(document.images).some(i => i.src.includes('getimagenofb'))")


def login_in_context(ctx, timeout=600):
    """Poll until the (visible) context is logged in on a category page."""
    page = _page(ctx)
    try:
        page.goto(_category_url(CATEGORIES["frames"]), wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(5)
        if "/login" not in page.url and page.evaluate(
                "() => Array.from(document.images).some(i => i.src.includes('getimagenofb'))"):
            return True
    return False


def _scrape_tiles(page):
    """Return [{'modelText','modelCode','colorCode'}] from currently rendered tiles."""
    return page.evaluate(
        """() => {
            const out = [];
            for (const img of Array.from(document.images)) {
                const m = img.src.match(/modelCode=([^&]+)&colorCode=([^&]+)/);
                if (!m) continue;
                let el = img, text = '';
                for (let k = 0; k < 6 && el; k++) {
                    el = el.parentElement;
                    if (el && el.innerText && el.innerText.length > text.length) text = el.innerText;
                }
                out.push({modelText: (text || '').replace(/\\s+/g, ' ').trim().slice(0, 80),
                          modelCode: decodeURIComponent(m[1]), colorCode: decodeURIComponent(m[2])});
            }
            return out;
        }"""
    )


def build_index(ctx, progress=None):
    """Enumerate both categories by scrolling each page and scraping tiles."""
    from luxottica import normalize as _norm
    page = _page(ctx)
    seen = {}
    for cat_id in CATEGORIES.values():
        try:
            page.goto(_category_url(cat_id), wait_until="domcontentloaded", timeout=60000)
        except Exception:
            continue
        page.wait_for_timeout(6000)
        stagnant = 0
        for _ in range(400):  # safety cap on scroll iterations
            for t in _scrape_tiles(page):
                key = (t["modelCode"], t["colorCode"])
                if t["modelCode"] and key not in seen:
                    seen[key] = {**t, "norm": _norm(t["modelText"])}
            if progress:
                progress(len(seen))
            before = len(seen)
            page.mouse.wheel(0, 20000)
            page.wait_for_timeout(2500)
            after_tiles = _scrape_tiles(page)
            for t in after_tiles:
                key = (t["modelCode"], t["colorCode"])
                if t["modelCode"] and key not in seen:
                    seen[key] = {**t, "norm": _norm(t["modelText"])}
            stagnant = stagnant + 1 if len(seen) == before else 0
            if stagnant >= 3:  # no new tiles after 3 scrolls → next category
                break
    return list(seen.values())


def save_index(models):
    INDEX_CACHE.write_text(json.dumps({"built": time.time(), "models": models}), encoding="utf-8")


def load_index():
    if INDEX_CACHE.exists():
        try:
            return json.loads(INDEX_CACHE.read_text(encoding="utf-8")).get("models", [])
        except Exception:
            return []
    return []
```

- [ ] **Step 3b: LIVE VERIFY & ADJUST (required).** With a login, run the spike below and confirm the scrape works; if tiles or model text aren't captured, adjust `_scrape_tiles` (the text-climb depth, or target the tile card selector) and the scroll/pagination in `build_index` until `build_index` returns >100 entries with non-empty `modelText` and `modelCode`, and a couple of `modelText` values look like real model names (e.g. contain a brand). Report the real numbers.

```
RUN_LIVE=1 python -c "
import safilo
with safilo.open_context(headless=False) as ctx:
    print('logged in:', safilo.is_logged_in(ctx) or safilo.login_in_context(ctx))
    idx = safilo.build_index(ctx, progress=lambda n: None)
    print('models:', len(idx))
    for e in idx[:5]: print('  ', e['modelText'][:40], '|', e['modelCode'], e['colorCode'])
    safilo.save_index(idx)
"
```
Expected: logged in True; models > 100; sample rows show real model names + numeric modelCodes. If model text is empty, fix `_scrape_tiles` to read the tile's product-name element and re-run.

- [ ] **Step 4: Run `RUN_LIVE=1 python -m pytest tests/test_safilo.py -v`** → pure tests pass and the live test passes (index >100, a constructed image downloads).

- [ ] **Step 5: Commit** — SKIP (not a git repo).

---

## Task 3: App integration

**Files:**
- Modify: `app.py`

Add a third action button "Match via Safilo" beside the EssilorLuxottica one, a
`safilo_variants` session-state (ambiguous picks, same shape as `el_variants`),
and a `safilo` image-source bucket in the ZIP summary.

- [ ] **Step 1: Add `import safilo` and a `safilo_variants` state key.** In `app.py`, change the import block and the session-state init:

Change:
```python
import luxottica
```
to:
```python
import luxottica
import safilo
```
And add `("safilo_variants", {})` to the `for key, default in [...]` session-state list.

- [ ] **Step 2: Add the Safilo action.** Immediately AFTER the EssilorLuxottica `if do_el:` block (before `if st.session_state.el_needs_login:`), add a Safilo button + handler. Place the button next to the EL one by adding a third column: change the EL section's button area to include Safilo. Concretely, after the `do_el` handler block, insert:

```python
    # --- Safilo (separate, on-demand; login builds the index) ---
    st.subheader("3b. Match via Safilo")
    st.caption("Official images for Safilo brands (Hugo Boss, Marc Jacobs, Carrera, Kate Spade…).")
    refresh = st.checkbox("Rebuild Safilo catalogue (requires login)", value=False)
    if st.button("Match via Safilo"):
        index = [] if refresh else safilo.load_index()
        with safilo.open_context(headless=(bool(index))) as ctx:
            if not index:
                st.info("Opening a browser window — log into Safilo there to build the catalogue…")
                if not (safilo.is_logged_in(ctx) or safilo.login_in_context(ctx)):
                    st.warning("Safilo login not detected — try again.")
                    st.stop()
                prog = st.progress(0.0, text="Building Safilo catalogue…")
                index = safilo.build_index(ctx, progress=lambda n: prog.progress(min(n / 3000.0, 1.0),
                                                                                 text=f"Safilo catalogue: {n} models"))
                safilo.save_index(index)
                prog.progress(1.0, text=f"Catalogue ready ({len(index)} models).")
        recs = st.session_state.records
        todo = [i for i in range(len(recs)) if recs[i]["name"] and i not in st.session_state.images]
        for i in todo:
            m = safilo.match(recs[i]["name"], index)
            if not m:
                continue
            dl = download_url_bytes(safilo.image_url(m["modelCode"], m["colorCode"]))
            if not dl and m["colorCode"]:
                # exact color combo may not exist; retry with no explicit color fallback handled by match default
                alt = safilo.match(recs[i]["name"], index)
                dl = download_url_bytes(safilo.image_url(m["modelCode"], alt["colorCode"])) if alt else None
            if dl:
                _store_image(i, dl[0], dl[1], "safilo")
        st.rerun()
```

- [ ] **Step 3: Add `safilo` to the ZIP summary.** Change the counts block in the ZIP section from:

```python
    by_barcode = sum(1 for v in images.values() if v["source"] == "barcode")
    el_count = sum(1 for v in images.values() if v["source"] == "luxottica")
    manual = len(images) - by_barcode - el_count
    st.write(f"{len(images)} image(s): {by_barcode} barcode, {el_count} EssilorLuxottica, {manual} manual.")
```
to:
```python
    by_barcode = sum(1 for v in images.values() if v["source"] == "barcode")
    el_count = sum(1 for v in images.values() if v["source"] == "luxottica")
    sf_count = sum(1 for v in images.values() if v["source"] == "safilo")
    manual = len(images) - by_barcode - el_count - sf_count
    st.write(f"{len(images)} image(s): {by_barcode} barcode, {el_count} EssilorLuxottica, "
             f"{sf_count} Safilo, {manual} manual.")
```

- [ ] **Step 4: Boot test.** Run (Bash):
```
cd "C:\Users\blank\Desktop\Random codes\barcode-image-downloader" && python -m py_compile app.py safilo.py && (python -m streamlit run app.py --server.headless true --server.port 8616 >/tmp/st16.log 2>&1 &) && sleep 12 && curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8616/_stcore/health && cat /tmp/st16.log
```
Expected: `200`, no traceback. Then stop the process on port 8616.

- [ ] **Step 5: Commit** — SKIP (not a git repo).

---

## Controller verification (after Task 3)

With a Safilo login (index built in Task 2), the controller verifies in the real
app: load a Safilo-brand name (e.g. "Marc Jacobs MARC 496/SHINY 807/IR"), click
**Match via Safilo** (uses cached index, no login), confirm the frame fills with
"✅ safilo image" and the ZIP contains the official Safilo JPEG.

---

## Notes

- `safilo.py` matching is pure/unit-tested; network functions take `ctx`; no Streamlit import.
- Images are public DAM URLs → `fetcher.download_url_bytes`.
- Index build needs a login (session can't persist); matching/downloads are offline afterward.
- The `_scrape_tiles`/`build_index` scrape is finalized in Task 2 Step 3b against the live site.
```
