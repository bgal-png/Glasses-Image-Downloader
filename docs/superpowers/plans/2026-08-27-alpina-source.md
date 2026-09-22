# Alpina Catalogue Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Match via Alpina" source that matches frame names to alpina-sports.com and downloads the official product image (right frame color), hybrid auto/pick.

**Architecture:** New `alpina.py` — pure matching helpers (unit-tested) + HTTP search/parse + a headless login-free browser to read per-color images (Shopware variant AJAX). Public images downloaded via `fetcher.download_url_bytes`. `app.py` gains a fourth match button + "alpina" bucket.

**Tech Stack:** Python, urllib (HTTP), Playwright (headless, no login), Streamlit, pytest.

---

## File Structure

- `alpina.py` — CREATE: pure (`normalize` reuse, `search_query`, `match_model`, `_color_words`, `match_color`, `_hires`) + network (`_http_get`, `search`, `product_variants`, `resolve`).
- `app.py` — MODIFY: `import alpina`, `alpina_variants` state, "Match via Alpina" button + handler, pick UI, ZIP bucket.
- `tests/test_alpina.py` — CREATE: unit tests + opt-in live tests.

---

## Task 1: Pure matching + helpers (TDD)

**Files:**
- Create: `alpina.py` (pure section)
- Test: `tests/test_alpina.py`

- [ ] **Step 1: Create `tests/test_alpina.py`:**

```python
from alpina import search_query, match_model, match_color, _color_words, _hires

TILES = [
    {"title": "DEFEY", "url": "https://www.alpina-sports.com/de/de/eyewear/sportbrillen/defey/", "norm": "DEFEY"},
    {"title": "DEFEY HR", "url": "https://www.alpina-sports.com/de/de/eyewear/sportbrillen/defey-hr/", "norm": "DEFEYHR"},
]


def test_search_query_model_extraction():
    assert search_query("Alpina DEFEY 2 black matt") == "DEFEY 2"
    assert search_query("Alpina MITZO II Cars") == "MITZO II"
    assert search_query("Alpina RAM 2.0 black matt Q-LITE yello") == "RAM 2.0"
    assert search_query("Alpina TWIST 7 M sand matt Q-LITE purp") == "TWIST 7"
    assert search_query("Alpina TURBO PRO YOUTH white matt") == "TURBO PRO YOUTH"
    assert search_query("Alpina EYEWEAR STRAP STYLE black") == "EYEWEAR STRAP STYLE"


def test_match_model_substring_longest():
    m = match_model("Alpina DEFEY 2 black matt", TILES)
    assert m["norm"] == "DEFEY"        # DEFEYHR is not a substring of the name
    assert "defey/" in m["url"]


def test_match_model_none():
    assert match_model("Alpina TWIST 7 M sand matt", TILES) is None


def test_color_words_after_model():
    assert _color_words("Alpina DEFEY 2 black matt") == "BLACKMATT"
    assert _color_words("Alpina TURBO PRO YOUTH white matt") == "WHITEMATT"


def test_match_color_frame_color():
    variants = [
        {"colorText": "black matt / mirror blue", "image": "http://i/a"},
        {"colorText": "moon-grey matt / mirror bronce", "image": "http://i/b"},
    ]
    assert match_color(variants, "Alpina DEFEY 2 black matt")["image"] == "http://i/a"
    assert match_color(variants, "Alpina DEFEY 2 pink glow") is None


def test_hires_swaps_size():
    assert _hires("https://x/A1_Main_600x600.jpg") == "https://x/A1_Main_1200x1200.jpg"
    assert _hires("https://x/A1_Main_600x600@2x.jpg") == "https://x/A1_Main_1200x1200.jpg"
```

- [ ] **Step 2: Run `python -m pytest tests/test_alpina.py -v`** → fails (no module alpina).

- [ ] **Step 3: Create `alpina.py` pure section:**

```python
# alpina.py — match frames to alpina-sports.com and download official images.
from luxottica import normalize  # uppercase, alphanumeric only

_ROMAN = {"II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"}


def search_query(name):
    """Reduce a name to the model for the (fuzzy) site search.

    Strips a leading "Alpina", then takes tokens up to and including the first
    token with a digit or a roman numeral (the model number); if none, the first
    three tokens. Searching the full name (with color) returns worse results.
    """
    toks = (name or "").split()
    if toks and toks[0].lower() == "alpina":
        toks = toks[1:]
    for i, t in enumerate(toks):
        if any(c.isdigit() for c in t) or t.upper() in _ROMAN:
            return " ".join(toks[: i + 1])
    return " ".join(toks[:3])


def match_model(name, tiles):
    """Eyewear tile whose norm is a substring of the name (longest wins), or None."""
    nn = normalize(name)
    best = None
    for t in tiles:
        if t["norm"] and t["norm"] in nn and (best is None or len(t["norm"]) > len(best["norm"])):
            best = t
    return best


def _color_words(name):
    """Normalized color portion of the name (tokens after the model)."""
    toks = (name or "").split()
    if toks and toks[0].lower() == "alpina":
        toks = toks[1:]
    model_len = len(search_query(name).split())
    return normalize(" ".join(toks[model_len:]))


def match_color(variants, name):
    """Variant whose colorText contains the name's color words, or None.

    Matches the FRAME color; lens sub-variants of one frame share the image, so
    the first hit is fine.
    """
    cw = _color_words(name)
    if not cw:
        return None
    for v in variants:
        if cw in normalize(v["colorText"]):
            return v
    return None


def _hires(url):
    """Swap a CloudFront image size token up to 1200x1200."""
    return (url.replace("_600x600@2x", "_1200x1200")
               .replace("_600x600", "_1200x1200")
               .replace("_200x200@2x", "_1200x1200")
               .replace("_200x200", "_1200x1200"))
```

- [ ] **Step 4: Run `python -m pytest tests/test_alpina.py -v`** → 6 passed.

- [ ] **Step 5: Commit** — SKIP (not a git repo).

---

## Task 2: Search + variants + resolve (network, live-tested)

**Files:**
- Modify: `alpina.py` (append network section)
- Test: `tests/test_alpina.py` (append live tests)

- [ ] **Step 1: Append live tests:**

```python
import os
import pytest

live = pytest.mark.skipif(os.environ.get("RUN_LIVE") != "1", reason="set RUN_LIVE=1 (public HTTP)")


@live
def test_search_returns_eyewear_tiles():
    import alpina
    tiles = alpina.search("Alpina DEFEY 2 black matt")
    assert len(tiles) >= 1
    assert all("/eyewear/" in t["url"] or "/skibrillen/" in t["url"] for t in tiles)


@live
def test_product_variants_and_resolve():
    import alpina
    tiles = alpina.search("Alpina DEFEY 2 black matt")
    m = alpina.match_model("Alpina DEFEY 2 black matt", tiles)
    assert m is not None
    variants = alpina.product_variants(m["url"])
    assert len(variants) >= 1
    assert all(v["image"].startswith("http") and "1200x1200" in v["image"] for v in variants)
    r = alpina.resolve("Alpina DEFEY 2 black matt")
    assert r["status"] in ("ok", "choose")
    if r["status"] == "ok":
        assert len(r["image"]) > 3000
    else:
        assert r["candidates"] and r["candidates"][0]["image_url"].startswith("http")
```

- [ ] **Step 2: Run `RUN_LIVE=1 python -m pytest tests/test_alpina.py -k "search_returns or product_variants" -v`** → fails (no `search`).

- [ ] **Step 3: Append the network section to `alpina.py`:**

```python
import re
import urllib.parse
import urllib.request
from contextlib import contextmanager

from playwright.sync_api import sync_playwright

from fetcher import _proactor_loop_policy, download_url_bytes

SEARCH_URL = "https://www.alpina-sports.com/de/de/search?q={q}"
EYEWEAR_PATHS = ("/eyewear/", "/skibrillen/")
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def _http_get(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None


def search(name):
    """Return eyewear result tiles [{'title','url','norm'}] for a name."""
    html = _http_get(SEARCH_URL.format(q=urllib.parse.quote(search_query(name))))
    if not html:
        return []
    tiles = []
    seen = set()
    for m in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*class="[^"]*product--title[^"]*"[^>]*>(.*?)</a>',
                         html, re.S):
        url = m.group(1)
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if not any(seg in url for seg in EYEWEAR_PATHS):
            continue
        if url in seen:
            continue
        seen.add(url)
        tiles.append({"title": title, "url": url, "norm": normalize(title)})
    return tiles


def product_variants(url):
    """Headless (no login) enumeration of a model's frame colors + hi-res images.

    Clicking a frame-color option navigates to ?number=<ordernumber> and swaps the
    Main image, so we re-open the base URL per unique frame color to get fresh
    element handles. Returns [{'colorText','image'}] (image at 1200x1200).
    """
    def _main(pg):
        return pg.evaluate(
            "() => { const i = Array.from(document.images).find(x => /_Main/.test(x.src));"
            " return i ? i.src : null; }")

    results = []
    with _proactor_loop_policy():
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            try:
                pg = b.new_page()
                pg.goto(url, wait_until="domcontentloaded", timeout=45000)
                pg.wait_for_timeout(2500)
                titles = [r.get_attribute("title") or ""
                          for r in pg.query_selector_all('input.option--input[name^="group"]')]
                # one representative title per unique frame color (part before "/")
                frames = {}
                for t in titles:
                    f = normalize(t.split("/")[0])
                    if f and f not in frames:
                        frames[f] = t
                if not frames:  # no variant selector: use the default image
                    img = _main(pg)
                    if img:
                        results.append({"colorText": "", "image": _hires(img)})
                for t in frames.values():
                    try:
                        pg.goto(url, wait_until="domcontentloaded", timeout=45000)
                        pg.wait_for_timeout(1500)
                        el = pg.query_selector('input.option--input[title="%s"]' % t.replace('"', ''))
                        if el:
                            el.click(force=True)
                            pg.wait_for_timeout(2500)
                        img = _main(pg)
                        if img:
                            results.append({"colorText": t, "image": _hires(img)})
                    except Exception:
                        continue
            finally:
                b.close()
    return results


def resolve(name):
    """Match a name to an Alpina image. Returns one of:
      {"status":"ok","image":bytes,"ext":str}
      {"status":"choose","candidates":[{"label","image_url"}]}
      {"status":"none"}
    """
    tiles = search(name)
    if not tiles:
        return {"status": "none"}
    nn = normalize(name)
    matches = [t for t in tiles if t["norm"] and t["norm"] in nn]
    if not matches:
        return {"status": "none"}
    matches.sort(key=lambda t: len(t["norm"]), reverse=True)
    top = [t for t in matches if len(t["norm"]) == len(matches[0]["norm"])]
    variants = product_variants(matches[0]["url"])
    if not variants:
        return {"status": "none"}
    cw = _color_words(name)
    color_hits = [v for v in variants if cw and cw in normalize(v["colorText"])]
    if len(top) == 1 and len(color_hits) >= 1:
        dl = download_url_bytes(color_hits[0]["image"])
        if dl:
            return {"status": "ok", "image": dl[0], "ext": dl[1]}
    candidates = [{"label": v["colorText"] or matches[0]["title"], "image_url": v["image"]}
                  for v in (color_hits or variants)]
    return {"status": "choose", "candidates": candidates}
```

- [ ] **Step 4: Run `RUN_LIVE=1 python -m pytest tests/test_alpina.py -v`** → all pass (pure + live: search returns eyewear tiles; variants have 1200x1200 images; resolve returns ok/choose with a working image).

- [ ] **Step 5: Commit** — SKIP (not a git repo).

---

## Task 3: App integration

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add import and state.** Change `import safilo` to:
```python
import safilo
import alpina
```
And add `("alpina_variants", {})` to the `for key, default in [...]` session-state list.

- [ ] **Step 2: Add the Alpina action.** Immediately AFTER the `if do_safilo:` block's final `st.rerun()` (and before `if st.session_state.get("safilo_msg"):`), insert:

```python
if do_alpina:
    if st.session_state.records != records:
        _init_state(records)
    recs = st.session_state.records
    todo = [i for i in range(len(recs)) if recs[i]["name"] and i not in st.session_state.images]
    matched = 0
    with st.spinner("Matching via Alpina (public site, no login)…"):
        prog = st.progress(0.0, text="Alpina…")
        for n, i in enumerate(todo):
            prog.progress((n + 1) / max(len(todo), 1),
                          text=f"Alpina [{n+1}/{len(todo)}] {recs[i]['name'][:30]}")
            r = alpina.resolve(recs[i]["name"])
            if r["status"] == "ok":
                _store_image(i, r["image"], r["ext"], "alpina")
                matched += 1
            elif r["status"] == "choose":
                st.session_state.alpina_variants[i] = r["candidates"]
        prog.progress(1.0, text=f"Alpina done — auto-matched {matched}.")
    st.rerun()
```

- [ ] **Step 3: Add the Alpina button.** In the "2. Get images" section, change the columns line and add a fourth button. Replace:
```python
ca, cb, cc = st.columns(3)
```
with:
```python
ca, cb, cc, cd = st.columns(4)
```
and after the `with cc:` block add:
```python
with cd:
    do_alpina = st.button("Match via Alpina", disabled=not records)
    st.caption("Alpina sunglasses & sports/ski glasses (public, no login)")
```

- [ ] **Step 4: Add the Alpina color-pick UI.** Immediately AFTER the EssilorLuxottica color-pick block (the `if el_pick:` section, after its `st.divider()`), insert:

```python
    al_pick = [i for i in st.session_state.alpina_variants if i not in images]
    if al_pick:
        st.subheader("4b. Pick an Alpina image")
        for i in al_pick:
            st.markdown(f"**{records[i]['name']}**")
            cands = st.session_state.alpina_variants[i]
            cols = st.columns(min(len(cands), 5) or 1)
            for j, c in enumerate(cands[:10]):
                with cols[j % len(cols)]:
                    st.image(c["image_url"], width=120, caption=(c["label"] or "?")[:24])
                    if st.button("Use this", key=f"al_{i}_{j}"):
                        if st.session_state.applied.get(f"al_{i}") != c["image_url"]:
                            dl = download_url_bytes(c["image_url"])
                            if dl:
                                _store_image(i, dl[0], dl[1], "alpina")
                                st.session_state.applied[f"al_{i}"] = c["image_url"]
                                st.rerun()
            st.divider()
```

- [ ] **Step 5: Add `alpina` to the ZIP summary.** Replace:
```python
    sf_count = sum(1 for v in images.values() if v["source"] == "safilo")
    manual = len(images) - by_barcode - el_count - sf_count
    st.write(f"{len(images)} image(s): {by_barcode} barcode, {el_count} EssilorLuxottica, "
             f"{sf_count} Safilo, {manual} manual.")
```
with:
```python
    sf_count = sum(1 for v in images.values() if v["source"] == "safilo")
    al_count = sum(1 for v in images.values() if v["source"] == "alpina")
    manual = len(images) - by_barcode - el_count - sf_count - al_count
    st.write(f"{len(images)} image(s): {by_barcode} barcode, {el_count} EssilorLuxottica, "
             f"{sf_count} Safilo, {al_count} Alpina, {manual} manual.")
```

- [ ] **Step 6: Boot test.** Run (Bash):
```
cd "C:\Users\blank\Desktop\Random codes\barcode-image-downloader" && python -m py_compile app.py alpina.py && (python -m streamlit run app.py --server.headless true --server.port 8622 >/tmp/st22.log 2>&1 &) && sleep 12 && curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8622/_stcore/health && cat /tmp/st22.log
```
Expected: `200`, no traceback. Then stop the process on port 8622.

- [ ] **Step 7: Commit** — SKIP (not a git repo).

---

## Controller verification (after Task 3)

Controller verifies in the real app (public, no login) with the file's Alpina
names: click **Match via Alpina** → confirm auto-matched frames fill ("✅ alpina
image"), ambiguous ones show the pick section, and the ZIP contains real Alpina
JPEGs named by barcode.

---

## Notes

- `alpina.py` matching is pure/unit-tested; network functions do HTTP + a headless
  login-free browser (no profile, no session, no login — the most robust source).
- Images are public → `fetcher.download_url_bytes`; URLs upgraded to 1200x1200.
- `product_variants` re-opens the base URL per frame color to avoid stale handles
  after the variant navigation.
```
