# Barcode Image Downloader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local Streamlit app that takes a list of barcodes and downloads the main (biggest) product image for each from barcodelookup.com, launched from a desktop shortcut.

**Architecture:** Three layers kept in separate, focused files — (1) a pure barcode-parsing module with no I/O, (2) a Playwright-based fetch engine that drives headless Chromium to bypass Cloudflare and download one image per barcode, (3) a Streamlit UI that wires them together with progress and a ZIP download. The pure parser is unit-tested; the engine is verified against the live site.

**Tech Stack:** Python, Streamlit, Playwright (Chromium), pandas + openpyxl (xlsx/csv parsing), pytest.

---

## File Structure

- `barcode_parser.py` — pure functions: read barcodes from pasted text or an uploaded file, clean them. No network, no Streamlit. Fully unit-tested.
- `fetcher.py` — Playwright engine: given one barcode, open its page, find the main image, return image bytes + extension or a typed failure. No Streamlit.
- `app.py` — Streamlit UI: input widgets, runs the fetcher over the list, progress, results table, ZIP download.
- `requirements.txt` — dependencies.
- `run.bat` — Windows launcher.
- `README.md` — setup + desktop-shortcut instructions.
- `tests/test_barcode_parser.py` — unit tests for the parser.
- `tests/test_fetcher_live.py` — opt-in live integration test for the fetcher.

---

## Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `tests/__init__.py`

- [ ] **Step 1: Write requirements.txt**

```
streamlit==1.40.2
playwright==1.49.1
pandas==2.2.3
openpyxl==3.1.5
pytest==8.3.4
```

- [ ] **Step 2: Create empty tests package marker**

Create `tests/__init__.py` as an empty file.

- [ ] **Step 3: Install dependencies and the Chromium browser**

Run:
```bash
pip install -r requirements.txt
python -m playwright install chromium
```
Expected: pip reports successful install; playwright downloads Chromium (a few hundred MB) with no errors.

- [ ] **Step 4: Commit**

```bash
git init
git add requirements.txt tests/__init__.py
git commit -m "chore: project scaffolding and dependencies"
```
(If not using git yet, skip this step — it can be done later with zero rework.)

---

## Task 2: Barcode parser (pure, TDD)

**Files:**
- Create: `barcode_parser.py`
- Test: `tests/test_barcode_parser.py`

This module never touches the network or Streamlit. It has two public functions:
- `clean_barcode(value) -> str | None` — normalize one cell/line.
- `parse_barcodes(text=None, file_bytes=None, filename=None) -> list[str]` — produce the ordered list of cleaned barcodes from either pasted text or an uploaded file.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_barcode_parser.py
import io
import pandas as pd
from barcode_parser import clean_barcode, parse_barcodes


def test_clean_strips_nbsp_and_whitespace():
    assert clean_barcode("197737241643\xa0") == "197737241643"
    assert clean_barcode("  8056262579640 ") == "8056262579640"


def test_clean_coerces_numeric_without_dot_zero():
    assert clean_barcode(197737257521) == "197737257521"
    assert clean_barcode(197737257521.0) == "197737257521"


def test_clean_returns_none_for_blank():
    assert clean_barcode("") is None
    assert clean_barcode("   ") is None
    assert clean_barcode(None) is None


def test_parse_pasted_text_one_per_line():
    text = "197737257521\n8056262579640\n\n  8056262600115  \n"
    assert parse_barcodes(text=text) == [
        "197737257521",
        "8056262579640",
        "8056262600115",
    ]


def test_parse_txt_file():
    data = "197737257521\n8056262579640\n".encode("utf-8")
    assert parse_barcodes(file_bytes=data, filename="list.txt") == [
        "197737257521",
        "8056262579640",
    ]


def test_parse_csv_uses_barcode_column_case_insensitive():
    df = pd.DataFrame({"Name": ["a", "b"], "BARCODE": [197737257521, "8056262579640\xa0"]})
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    result = parse_barcodes(file_bytes=buf.getvalue(), filename="x.csv")
    assert result == ["197737257521", "8056262579640"]


def test_parse_xlsx_uses_barcode_column():
    df = pd.DataFrame({
        "Glasses name": [None, None],
        "Barcode": ["197737241643\xa0", 197737257521],
    })
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    result = parse_barcodes(file_bytes=buf.getvalue(), filename="260615.xlsx")
    assert result == ["197737241643", "197737257521"]


def test_parse_csv_falls_back_to_first_column_when_no_barcode_header():
    df = pd.DataFrame({"codes": ["197737257521", "8056262579640"]})
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    result = parse_barcodes(file_bytes=buf.getvalue(), filename="x.csv")
    assert result == ["197737257521", "8056262579640"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_barcode_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'barcode_parser'`.

- [ ] **Step 3: Write the implementation**

```python
# barcode_parser.py
import io
import pandas as pd


def clean_barcode(value):
    """Normalize one barcode cell/line to a digit string, or None if blank."""
    if value is None:
        return None
    # Numeric cells (int or float) -> integer string, no trailing .0
    if isinstance(value, float):
        if pd.isna(value):
            return None
        value = int(value)
    if isinstance(value, int):
        return str(value)
    # Strings: strip whitespace including non-breaking space
    text = str(value).replace("\xa0", " ").strip()
    if not text:
        return None
    return text


def _from_dataframe(df):
    """Pick the Barcode column (case-insensitive) or fall back to first column."""
    target = None
    for col in df.columns:
        if str(col).strip().lower() == "barcode":
            target = col
            break
    if target is None:
        target = df.columns[0]
    cleaned = [clean_barcode(v) for v in df[target].tolist()]
    return [b for b in cleaned if b]


def parse_barcodes(text=None, file_bytes=None, filename=None):
    """Return an ordered list of cleaned barcodes from pasted text or a file."""
    if text is not None:
        cleaned = [clean_barcode(line) for line in text.splitlines()]
        return [b for b in cleaned if b]

    if file_bytes is not None:
        name = (filename or "").lower()
        if name.endswith(".xlsx") or name.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(file_bytes), dtype=object)
            return _from_dataframe(df)
        if name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_bytes), dtype=object)
            return _from_dataframe(df)
        # Treat anything else (.txt or unknown) as one-per-line text
        decoded = file_bytes.decode("utf-8", errors="replace")
        cleaned = [clean_barcode(line) for line in decoded.splitlines()]
        return [b for b in cleaned if b]

    return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_barcode_parser.py -v`
Expected: PASS (all 8 tests).

- [ ] **Step 5: Commit**

```bash
git add barcode_parser.py tests/test_barcode_parser.py
git commit -m "feat: barcode parser for paste/txt/csv/xlsx input"
```

---

## Task 3: Fetch engine (Playwright)

**Files:**
- Create: `fetcher.py`
- Test: `tests/test_fetcher_live.py`

Public surface:
- `FetchResult` — a dataclass: `barcode: str`, `status: str` (`"ok"` / `"not_found"` / `"error"`), `image_bytes: bytes | None`, `extension: str` (e.g. `".jpg"`), `message: str`.
- `make_browser()` — context manager yielding a started Playwright Chromium browser (reused across barcodes).
- `fetch_image(browser, barcode, delay=1.5) -> FetchResult` — open the barcode page, find the main image, download it.

The main image on barcodelookup.com is the large image at the top-left of the product block. The selector below targets the main product-image container's `<img>` and is the **primary** path; if it is not found, the engine falls back to picking the largest `<img>` on the page by rendered area (excludes tiny icons/logos). The exact primary selector must be confirmed in Step 3a against the live page.

- [ ] **Step 1: Write the live integration test (opt-in)**

```python
# tests/test_fetcher_live.py
import os
import pytest
from fetcher import make_browser, fetch_image

# This test hits the real site + Cloudflare. Run explicitly with:
#   RUN_LIVE=1 pytest tests/test_fetcher_live.py -v -s
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE") != "1",
    reason="set RUN_LIVE=1 to run live network tests",
)


def test_fetch_known_barcode_returns_image():
    with make_browser() as browser:
        result = fetch_image(browser, "197737257521", delay=0.0)
    assert result.status == "ok", result.message
    assert result.image_bytes is not None
    assert len(result.image_bytes) > 5000  # a real product image, not a 1px pixel
    assert result.extension in (".jpg", ".jpeg", ".png", ".webp")


def test_fetch_nonexistent_barcode_is_not_found():
    with make_browser() as browser:
        result = fetch_image(browser, "000000000000", delay=0.0)
    assert result.status in ("not_found", "error"), result.message
    assert result.image_bytes is None
```

- [ ] **Step 2: Run the test to confirm it is collected but skipped without the engine**

Run: `pytest tests/test_fetcher_live.py -v`
Expected: SKIPPED (because `RUN_LIVE` is unset). This confirms the test file imports cleanly once `fetcher.py` exists — it will currently FAIL to import. That failure is expected and resolved by Step 3.

- [ ] **Step 3: Write the implementation**

```python
# fetcher.py
import time
from contextlib import contextmanager
from dataclasses import dataclass

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE_URL = "https://www.barcodelookup.com/"

# Primary selector for the big product image. Confirm/adjust in Step 3a.
PRIMARY_IMAGE_SELECTOR = "div.product-image img, #product-image img"


@dataclass
class FetchResult:
    barcode: str
    status: str  # "ok" | "not_found" | "error"
    image_bytes: bytes | None = None
    extension: str = ""
    message: str = ""


@contextmanager
def make_browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            yield browser
        finally:
            browser.close()


def _extension_from_url_or_type(url, content_type):
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if ext in url.lower():
            return ".jpg" if ext == ".jpeg" else ext
    if content_type:
        if "png" in content_type:
            return ".png"
        if "webp" in content_type:
            return ".webp"
        if "gif" in content_type:
            return ".gif"
    return ".jpg"


def _find_main_image_url(page):
    """Return the URL of the biggest product image, or None."""
    # Primary: the known product-image container.
    el = page.query_selector(PRIMARY_IMAGE_SELECTOR)
    if el:
        src = el.get_attribute("src")
        if src:
            return src
    # Fallback: largest <img> on the page by rendered area.
    return page.evaluate(
        """() => {
            const imgs = Array.from(document.images);
            let best = null, bestArea = 0;
            for (const im of imgs) {
                const area = im.naturalWidth * im.naturalHeight;
                if (area > bestArea && im.src && im.src.startsWith('http')) {
                    bestArea = area; best = im.src;
                }
            }
            return bestArea > 10000 ? best : null;  // ignore tiny icons
        }"""
    )


def fetch_image(browser, barcode, delay=1.5):
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1366, "height": 900},
    )
    page = context.new_page()
    try:
        resp = page.goto(BASE_URL + barcode, wait_until="domcontentloaded", timeout=45000)
        # Give Cloudflare / lazy images a moment to settle.
        try:
            page.wait_for_selector(PRIMARY_IMAGE_SELECTOR, timeout=15000)
        except PWTimeout:
            pass  # fall through to the largest-image fallback

        if resp is not None and resp.status == 404:
            return FetchResult(barcode, "not_found", message="page 404")

        url = _find_main_image_url(page)
        if not url:
            return FetchResult(barcode, "not_found", message="no product image found")

        # Download the image bytes via the page's request context (shares cookies).
        img_resp = context.request.get(url, timeout=45000)
        if not img_resp.ok:
            return FetchResult(barcode, "error", message=f"image HTTP {img_resp.status}")
        body = img_resp.body()
        if len(body) < 1000:
            return FetchResult(barcode, "not_found", message="image too small / placeholder")

        ext = _extension_from_url_or_type(url, img_resp.headers.get("content-type", ""))
        return FetchResult(barcode, "ok", image_bytes=body, extension=ext, message="ok")
    except PWTimeout:
        return FetchResult(barcode, "error", message="timeout (possible Cloudflare block)")
    except Exception as exc:  # network, navigation, etc.
        return FetchResult(barcode, "error", message=str(exc))
    finally:
        context.close()
        if delay:
            time.sleep(delay)
```

- [ ] **Step 3a: Confirm the primary image selector against the live page**

The `PRIMARY_IMAGE_SELECTOR` is a best guess. Verify it before trusting it:

Run this throwaway script:
```bash
RUN_LIVE=1 python -c "
from fetcher import make_browser, _find_main_image_url
from playwright.sync_api import sync_playwright
with make_browser() as b:
    ctx = b.new_context()
    pg = ctx.new_page()
    pg.goto('https://www.barcodelookup.com/197737257521', wait_until='domcontentloaded', timeout=45000)
    pg.wait_for_timeout(8000)
    print('PRIMARY:', pg.query_selector('div.product-image img, #product-image img'))
    print('URL:', _find_main_image_url(pg))
    ctx.close()
"
```
Expected: prints a non-None URL pointing at the big glasses image. If `PRIMARY` is `None` but `URL` is correct, the fallback is carrying it — open the page in a normal browser, inspect the big image's element, and update `PRIMARY_IMAGE_SELECTOR` to match (e.g. its actual container class/id). Re-run until `PRIMARY` is non-None.

- [ ] **Step 4: Run the live tests to verify the engine works end to end**

Run: `RUN_LIVE=1 pytest tests/test_fetcher_live.py -v -s`
Expected: both tests PASS — a known barcode returns real image bytes; a bogus barcode returns not_found/error.

- [ ] **Step 5: Commit**

```bash
git add fetcher.py tests/test_fetcher_live.py
git commit -m "feat: Playwright fetch engine for main product image"
```

---

## Task 4: Streamlit UI

**Files:**
- Create: `app.py`

Wires the parser + fetcher together with input widgets, live progress, a results table, and a ZIP download. Imports only from `barcode_parser` and `fetcher`.

- [ ] **Step 1: Write the app**

```python
# app.py
import io
import zipfile

import pandas as pd
import streamlit as st

from barcode_parser import parse_barcodes
from fetcher import make_browser, fetch_image

st.set_page_config(page_title="Barcode Image Downloader", page_icon="📷")
st.title("📷 Barcode Image Downloader")
st.caption("Downloads the main product image for each barcode from barcodelookup.com")

st.subheader("1. Provide barcodes")
col1, col2 = st.columns(2)
with col1:
    pasted = st.text_area("Paste barcodes (one per line)", height=200, placeholder="197737257521\n8056262579640")
with col2:
    uploaded = st.file_uploader("…or upload a file", type=["xlsx", "xls", "csv", "txt"])

# Resolve the barcode list (file takes precedence if both given).
barcodes = []
if uploaded is not None:
    barcodes = parse_barcodes(file_bytes=uploaded.getvalue(), filename=uploaded.name)
elif pasted.strip():
    barcodes = parse_barcodes(text=pasted)

if barcodes:
    st.info(f"{len(barcodes)} barcode(s) ready.")

delay = st.slider("Delay between barcodes (seconds)", 0.0, 5.0, 1.5, 0.5,
                  help="A polite pause to avoid rate limiting / Cloudflare blocks.")

st.subheader("2. Download")
if st.button("Download images", type="primary", disabled=not barcodes):
    progress = st.progress(0.0, text="Starting browser…")
    rows = []
    images = {}  # filename -> bytes
    used_names = set()

    with make_browser() as browser:
        for i, code in enumerate(barcodes, start=1):
            progress.progress(i / len(barcodes), text=f"[{i}/{len(barcodes)}] {code}")
            result = fetch_image(browser, code, delay=delay)
            icon = {"ok": "✅", "not_found": "❌", "error": "⚠️"}.get(result.status, "?")
            rows.append({"Barcode": code, "Status": f"{icon} {result.status}", "Detail": result.message})
            if result.status == "ok" and result.image_bytes:
                name = f"{code}{result.extension}"
                # Guard against duplicate barcodes overwriting each other.
                n = 2
                while name in used_names:
                    name = f"{code}_{n}{result.extension}"
                    n += 1
                used_names.add(name)
                images[name] = result.image_bytes

    progress.progress(1.0, text="Done.")
    st.subheader("3. Results")
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    ok = sum(1 for r in rows if r["Status"].startswith("✅"))
    st.success(f"{ok} of {len(barcodes)} image(s) downloaded.")

    if images:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in images.items():
                zf.writestr(name, data)
        st.download_button(
            "⬇️ Download all as ZIP",
            data=zip_buf.getvalue(),
            file_name="barcode_images.zip",
            mime="application/zip",
        )
    else:
        st.warning("No images to download.")
```

- [ ] **Step 2: Smoke-test the app manually**

Run: `streamlit run app.py`
Then in the browser: paste `197737257521` on its own line, click **Download images**.
Expected: progress bar runs, results table shows `✅ ok` for that barcode, and a **Download all as ZIP** button appears. Download the ZIP and confirm it contains `197737257521.jpg` with the glasses image.

- [ ] **Step 3: Test the real xlsx input**

In the app, upload `C:\Users\blank\Desktop\OLD PC\BG Old\Glasses Imports\260615\260615.xlsx`.
Expected: the info line reads "117 barcode(s) ready." Click Download images and confirm it processes the list and produces a ZIP.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: Streamlit UI with progress, results table, ZIP download"
```

---

## Task 5: Launcher and docs

**Files:**
- Create: `run.bat`
- Create: `README.md`

- [ ] **Step 1: Write the Windows launcher**

```bat
@echo off
REM Launch the Barcode Image Downloader and open it in the browser.
cd /d "%~dp0"
streamlit run app.py
```

- [ ] **Step 2: Write the README**

````markdown
# Barcode Image Downloader

Local Streamlit app that downloads the main product image for a list of
barcodes from barcodelookup.com.

## One-time setup

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## Run

Double-click `run.bat`, or from a terminal:

```bash
streamlit run app.py
```

The app opens in your browser. Paste barcodes (one per line) or upload an
`.xlsx` / `.csv` / `.txt`. For spreadsheets it auto-detects the column named
**Barcode**. Click **Download images**, then **Download all as ZIP**.

## Make a desktop shortcut

1. Right-click `run.bat` → **Show more options** → **Send to** → **Desktop
   (create shortcut)**.
2. On the Desktop, rename the shortcut to "Barcode Image Downloader".
3. (Optional) Right-click the shortcut → **Properties** → **Change Icon** to
   pick a nicer icon.

Now double-clicking the shortcut launches the app.

## Notes

- Runs locally on purpose: a real browser on your own IP passes the site's
  Cloudflare protection. Cloud hosting (e.g. Streamlit Cloud) gets blocked.
- Only the main/biggest image is downloaded (not gallery thumbnails).
- Barcodes that don't exist or have no image are marked ❌ and skipped; the run
  continues.
````

- [ ] **Step 3: Verify the launcher works**

Double-click `run.bat` (or run it from a terminal).
Expected: the Streamlit app starts and opens in the browser, same as Task 4.

- [ ] **Step 4: Commit**

```bash
git add run.bat README.md
git commit -m "docs: launcher and README with desktop shortcut instructions"
```

---

## Notes on testing strategy

- `barcode_parser.py` is pure and fully unit-tested (Task 2) — this is where the
  fiddly real-world logic lives (nbsp, numeric coercion, column detection), so
  it gets the most rigorous coverage.
- `fetcher.py` depends on the live site behind Cloudflare, so it is verified
  with an opt-in live integration test (`RUN_LIVE=1`) plus the manual selector
  confirmation in Step 3a. It cannot be meaningfully unit-tested without the
  real page.
- `app.py` is thin glue verified by manual smoke tests (Task 4 Steps 2–3),
  including the real 117-barcode xlsx.
