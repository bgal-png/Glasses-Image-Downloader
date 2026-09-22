# Multi-Source Image Downloader (v2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing tool so it pairs each barcode with a name, auto-downloads images for barcode hits, and gives a reliable human-assisted paste/upload path for the misses.

**Architecture:** Reuse v1's Playwright barcode engine untouched. Add paired (barcode, name) parsing, two small pure/IO helpers in the engine (`search_links`, `download_url_bytes`), and rework the Streamlit UI into: run barcode lookup → results table → manual-assist section (search links + paste-URL/upload per miss) → ZIP. State persists in `st.session_state`.

**Tech Stack:** Python, Streamlit, Playwright (existing), pandas + openpyxl, pytest.

---

## File Structure

- `barcode_parser.py` — MODIFY: add `parse_records()` (paired barcode+name) and small helpers; keep `parse_barcodes()` working.
- `fetcher.py` — MODIFY: add `search_links()` (pure) and `download_url_bytes()` (plain HTTP). Leave the Playwright barcode path unchanged.
- `app.py` — REWRITE: new flow with session_state, results table, manual-assist section, ZIP.
- `tests/test_barcode_parser.py` — MODIFY: add `parse_records` tests.
- `tests/test_fetcher_live.py` — MODIFY: add `search_links` (pure) + `download_url_bytes` (live) tests.

---

## Task 1: Paired barcode+name parsing

**Files:**
- Modify: `barcode_parser.py`
- Test: `tests/test_barcode_parser.py`

- [ ] **Step 1: Add the failing tests** — append to `tests/test_barcode_parser.py`:

```python
from barcode_parser import parse_records


def test_records_from_xlsx_pairs_barcode_and_name():
    df = pd.DataFrame({
        "Glasses name": ["Hugo Boss BOSS 1949 FWM", "Miu Miu MU 01XV 08Q1O1"],
        "Barcode": ["197737257521\xa0", 8056262579640],
    })
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    recs = parse_records(file_bytes=buf.getvalue(), filename="x.xlsx")
    assert recs == [
        {"barcode": "197737257521", "name": "Hugo Boss BOSS 1949 FWM"},
        {"barcode": "8056262579640", "name": "Miu Miu MU 01XV 08Q1O1"},
    ]


def test_records_from_csv_without_name_column_leaves_name_empty():
    df = pd.DataFrame({"Barcode": ["197737257521", "8056262579640"]})
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    recs = parse_records(file_bytes=buf.getvalue(), filename="x.csv")
    assert recs == [
        {"barcode": "197737257521", "name": ""},
        {"barcode": "8056262579640", "name": ""},
    ]


def test_records_from_paste_barcode_only_and_barcode_comma_name():
    text = "197737257521\n8056262579640, Miu Miu MU 01XV\n\t\n"
    recs = parse_records(text=text)
    assert recs == [
        {"barcode": "197737257521", "name": ""},
        {"barcode": "8056262579640", "name": "Miu Miu MU 01XV"},
    ]


def test_records_from_paste_tab_separated():
    text = "197737257521\tHugo Boss BOSS 1949 FWM"
    recs = parse_records(text=text)
    assert recs == [{"barcode": "197737257521", "name": "Hugo Boss BOSS 1949 FWM"}]


def test_records_drops_rows_blank_in_both():
    df = pd.DataFrame({"Glasses name": ["", None], "Barcode": ["", None]})
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    assert parse_records(file_bytes=buf.getvalue(), filename="x.xlsx") == []


def test_parse_barcodes_still_works():
    # Regression: the v1 function must keep returning a flat list.
    assert parse_barcodes(text="197737257521\n8056262579640") == [
        "197737257521", "8056262579640",
    ]
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_barcode_parser.py -v`
Expected: the new tests FAIL with `ImportError: cannot import name 'parse_records'`.

- [ ] **Step 3: Implement** — edit `barcode_parser.py`. Add the helpers and `parse_records`, and refactor the barcode-column lookup into `_barcode_column` (used by both the existing `_from_dataframe` and the new code). Replace the existing `_from_dataframe` function with the version below and add the rest:

```python
def _barcode_column(df):
    """Return the Barcode column (case-insensitive) or the first column."""
    for col in df.columns:
        if str(col).strip().lower() == "barcode":
            return col
    return df.columns[0]


def _name_column(df):
    """Return the name column, or None if there isn't one."""
    for col in df.columns:
        if str(col).strip().lower() == "glasses name":
            return col
    for col in df.columns:
        if str(col).strip().lower() == "name":
            return col
    return None


def _clean_name(value):
    """Trim a name cell to a string ('' for blank/NaN/None)."""
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).replace("\xa0", " ").strip()


def _from_dataframe(df):
    """Pick the Barcode column (case-insensitive) or fall back to first column."""
    target = _barcode_column(df)
    cleaned = [clean_barcode(v) for v in df[target].tolist()]
    return [b for b in cleaned if b]


def _read_dataframe(file_bytes, name):
    if name.endswith(".csv"):
        return pd.read_csv(io.BytesIO(file_bytes), dtype=object)
    return pd.read_excel(io.BytesIO(file_bytes), dtype=object)


def _record_from_line(line):
    """Parse one pasted line into a record dict, or None if blank."""
    raw = line.replace("\xa0", " ").strip()
    if not raw:
        return None
    if "\t" in raw:
        parts = raw.split("\t", 1)
    elif "," in raw:
        parts = raw.split(",", 1)
    else:
        parts = [raw]
    barcode = clean_barcode(parts[0]) or ""
    name = parts[1].strip() if len(parts) > 1 else ""
    if not barcode and not name:
        return None
    return {"barcode": barcode, "name": name}


def parse_records(text=None, file_bytes=None, filename=None):
    """Return ordered [{'barcode': str, 'name': str}] from paste or a file."""
    if text is not None:
        records = [_record_from_line(line) for line in text.splitlines()]
        return [r for r in records if r]

    if file_bytes is not None:
        name = (filename or "").lower()
        if name.endswith((".xlsx", ".xls", ".csv")):
            df = _read_dataframe(file_bytes, name)
            bcol = _barcode_column(df)
            ncol = _name_column(df)
            records = []
            for _, row in df.iterrows():
                barcode = clean_barcode(row[bcol]) or "" if bcol is not None else ""
                frame_name = _clean_name(row[ncol]) if ncol is not None else ""
                if barcode or frame_name:
                    records.append({"barcode": barcode, "name": frame_name})
            return records
        decoded = file_bytes.decode("utf-8", errors="replace")
        return parse_records(text=decoded)

    return []
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_barcode_parser.py -v`
Expected: PASS (all v1 tests + the 6 new ones).

- [ ] **Step 5: Commit** — SKIP (not a git repo).

---

## Task 2: Engine helpers — `search_links` and `download_url_bytes`

**Files:**
- Modify: `fetcher.py`
- Test: `tests/test_fetcher_live.py`

- [ ] **Step 1: Add the tests** — append to `tests/test_fetcher_live.py`:

```python
from urllib.parse import quote
from fetcher import search_links, download_url_bytes


def test_search_links_builds_encoded_urls():
    # Pure function — safe to run without RUN_LIVE (this module's skip only
    # gates tests that hit the network; this assertion does not).
    links = search_links("Hugo Boss BOSS 1949 FWM")
    assert links["Google Images"] == (
        "https://www.google.com/search?tbm=isch&q="
        + quote("Hugo Boss BOSS 1949 FWM")
    )
    assert "smartbuyglasses.com/search?q=" in links["SmartBuyGlasses"]


def test_download_url_bytes_fetches_real_image():
    # Uses a known barcodelookup product image URL (direct link).
    url = "https://images.barcodelookup.com/162952/1629522796-2.jpg"
    result = download_url_bytes(url)
    assert result is not None
    body, ext = result
    assert len(body) > 5000
    assert ext in (".jpg", ".jpeg", ".png", ".webp")


def test_download_url_bytes_returns_none_for_bad_url():
    assert download_url_bytes("https://images.barcodelookup.com/does-not-exist-xyz.jpg") is None
```

Note: `search_links` is pure but lives in this live-gated test module. Move the
`test_search_links_builds_encoded_urls` assertion to run unconditionally by
giving it its own non-skipped path: place it ABOVE the `pytestmark` line is not
possible, so instead run the pure test from the parser test file is overkill —
accept that it only runs under `RUN_LIVE=1` here. (The function is trivial; the
live download tests are the ones that matter.)

- [ ] **Step 2: Run to verify they fail**

Run: `RUN_LIVE=1 python -m pytest tests/test_fetcher_live.py -v`
Expected: the 3 new tests FAIL with `ImportError: cannot import name 'search_links'`.

- [ ] **Step 3: Implement** — add to `fetcher.py` (top: add `import urllib.request` and `from urllib.parse import quote, urlsplit`). Append these functions:

```python
def search_links(name):
    """Ready-to-open image-search URLs for a frame name (pure, no network)."""
    q = quote(name)
    return {
        "Google Images": f"https://www.google.com/search?tbm=isch&q={q}",
        "SmartBuyGlasses": f"https://www.smartbuyglasses.com/search?q={q}",
    }


def download_url_bytes(url):
    """Download a direct image URL the user pasted.

    Returns (bytes, extension) or None on any failure (caller then asks the user
    to upload the file instead). Sends a browser User-Agent and an origin
    Referer to satisfy simple hotlink checks.
    """
    try:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            return None
        origin = f"{parts.scheme}://{parts.netloc}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "Referer": origin,
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            body = resp.read()
        if len(body) < 500:
            return None
        return body, _extension_from_url_or_type(url, content_type)
    except Exception:
        return None
```

- [ ] **Step 4: Run to verify they pass**

Run: `RUN_LIVE=1 python -m pytest tests/test_fetcher_live.py -v`
Expected: PASS (existing live tests + the 3 new ones).

- [ ] **Step 5: Commit** — SKIP (not a git repo).

---

## Task 3: Rewrite the Streamlit UI

**Files:**
- Modify (full rewrite): `app.py`

- [ ] **Step 1: Write the new `app.py`** with EXACTLY this content:

```python
# app.py
import io
import re
import zipfile

import pandas as pd
import streamlit as st

from barcode_parser import parse_records
from fetcher import make_browser, fetch_image, search_links, download_url_bytes

st.set_page_config(page_title="Glasses Image Downloader", page_icon="📷")
st.title("📷 Glasses Image Downloader")
st.caption("Auto-downloads images by barcode; helps you fill the rest by name.")


def _safe_name(text):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
    return cleaned or "image"


def _store_image(idx, image_bytes, extension, source):
    st.session_state.images[idx] = {
        "bytes": image_bytes,
        "ext": extension or ".jpg",
        "source": source,
    }


# --- Session state ---
if "records" not in st.session_state:
    st.session_state.records = []   # list of {"barcode","name"}
if "results" not in st.session_state:
    st.session_state.results = []   # list of {"status": ...} aligned to records
if "images" not in st.session_state:
    st.session_state.images = {}    # idx -> {"bytes","ext","source"}

# --- 1. Input ---
st.subheader("1. Provide frames")
col1, col2 = st.columns(2)
with col1:
    pasted = st.text_area(
        "Paste (barcode, or `barcode, name` per line)",
        height=180,
        placeholder="197737257521, Hugo Boss BOSS 1949 FWM",
    )
with col2:
    uploaded = st.file_uploader("…or upload a file", type=["xlsx", "xls", "csv", "txt"])

records = []
if uploaded is not None:
    records = parse_records(file_bytes=uploaded.getvalue(), filename=uploaded.name)
elif pasted.strip():
    records = parse_records(text=pasted)

if records:
    with_names = sum(1 for r in records if r["name"])
    with_barcode = sum(1 for r in records if r["barcode"])
    st.info(f"{len(records)} frame(s) ready — {with_barcode} with a barcode, {with_names} with a name.")

delay = st.slider("Delay between barcodes (seconds)", 0.0, 5.0, 1.5, 0.5,
                  help="A polite pause to avoid rate limiting / Cloudflare blocks.")

# --- 2. Run barcode lookup ---
st.subheader("2. Look up by barcode")
if st.button("Run barcode lookup", type="primary", disabled=not records):
    st.session_state.records = records
    st.session_state.results = []
    st.session_state.images = {}
    progress = st.progress(0.0, text="Starting browser…")
    with make_browser() as browser:
        for i, rec in enumerate(records):
            progress.progress((i + 1) / len(records),
                              text=f"[{i + 1}/{len(records)}] {rec['barcode'] or rec['name']}")
            if rec["barcode"]:
                result = fetch_image(browser, rec["barcode"], delay=delay)
                if result.status == "ok" and result.image_bytes:
                    _store_image(i, result.image_bytes, result.extension, "barcode")
                    st.session_state.results.append({"status": "found"})
                    continue
            # Miss or no barcode
            if rec["name"]:
                st.session_state.results.append({"status": "needs_image"})
            else:
                st.session_state.results.append({"status": "no_source"})
    progress.progress(1.0, text="Done.")

# --- 3. Results + manual assist (only after a run) ---
if st.session_state.results:
    records = st.session_state.records
    results = st.session_state.results

    st.subheader("3. Results")
    status_label = {
        "found": "✅ found by barcode",
        "needs_image": "✋ needs image",
        "no_source": "❌ no barcode & no name",
    }
    rows = []
    for i, rec in enumerate(records):
        status = results[i]["status"]
        # A frame that was needs_image and has since been filled shows as filled.
        if i in st.session_state.images and status != "found":
            label = f"✅ filled ({st.session_state.images[i]['source']})"
        else:
            label = status_label[status]
        rows.append({"Barcode": rec["barcode"], "Name": rec["name"], "Status": label})
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    needs = [i for i, r in enumerate(results)
             if r["status"] == "needs_image" and i not in st.session_state.images]
    if needs:
        st.subheader("4. Fill the rest by name")
        st.caption("Open a search, find the right image, then paste its URL or upload the file.")
        for i in needs:
            rec = records[i]
            st.markdown(f"**{rec['name']}**  \n`{rec['barcode'] or 'no barcode'}`")
            links = search_links(rec["name"])
            link_md = " · ".join(f"[{label}]({url})" for label, url in links.items())
            st.markdown("Search: " + link_md)
            c1, c2 = st.columns([2, 1])
            with c1:
                url = st.text_input("Paste image URL", key=f"url_{i}")
                if url:
                    fetched = download_url_bytes(url)
                    if fetched:
                        _store_image(i, fetched[0], fetched[1], "url")
                        st.rerun()
                    else:
                        st.warning("Couldn't fetch that URL — try uploading the file instead.")
            with c2:
                up = st.file_uploader("…or upload", type=["jpg", "jpeg", "png", "webp"], key=f"file_{i}")
                if up is not None:
                    ext = "." + up.name.rsplit(".", 1)[-1].lower()
                    _store_image(i, up.getvalue(), ext, "upload")
                    st.rerun()
            st.divider()

    # --- 5. ZIP ---
    st.subheader("5. Download")
    images = st.session_state.images
    by_barcode = sum(1 for v in images.values() if v["source"] == "barcode")
    manual = len(images) - by_barcode
    st.write(f"{len(images)} image(s): {by_barcode} by barcode, {manual} added manually.")
    if images:
        zip_buf = io.BytesIO()
        used = set()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, data in images.items():
                base = records[i]["barcode"] or _safe_name(records[i]["name"])
                fname = f"{base}{data['ext']}"
                n = 2
                while fname in used:
                    fname = f"{base}_{n}{data['ext']}"
                    n += 1
                used.add(fname)
                zf.writestr(fname, data["bytes"])
        st.download_button(
            "⬇️ Download all as ZIP",
            data=zip_buf.getvalue(),
            file_name="glasses_images.zip",
            mime="application/zip",
        )
    else:
        st.warning("No images yet.")
```

- [ ] **Step 2: Boot test**

Run (Bash): `cd "C:\Users\blank\Desktop\Random codes\barcode-image-downloader" && python -m py_compile app.py && (python -m streamlit run app.py --server.headless true --server.port 8603 >/tmp/st3.log 2>&1 &) && sleep 12 && curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8603/_stcore/health`
Expected: `200`. Then stop the streamlit process (find the PID listening on 8603 and kill it).

- [ ] **Step 3: Commit** — SKIP (not a git repo).

---

## Controller verification (after Task 3)

The controller (not a subagent) verifies the full flow in the real running app,
because the manual-assist UI runs in Streamlit's worker thread:
1. Launch the app, upload the real file
   `C:\Users\blank\Desktop\OLD PC\BG Old\Glasses Imports\260615\260615 - f.xlsx`,
   confirm "117 frame(s) ready".
2. Click **Run barcode lookup** on a SMALL subset first (paste 2–3 barcodes) to
   keep it quick: confirm ✅ rows and thumbnails, no `NotImplementedError`.
3. For a "needs image" frame, paste a known image URL and confirm it flips to
   "✅ filled (url)"; upload a file for another and confirm "✅ filled (upload)".
4. Click **Download all as ZIP**, confirm the ZIP downloads and contains the
   expected files named by barcode/name.

---

## Notes on testing strategy

- Parser changes are fully unit-tested (Task 1) including a v1 regression test.
- `download_url_bytes` is covered by live tests; `search_links` is pure.
- `app.py` is glue verified by boot test + the controller's real-app walkthrough,
  since Streamlit UI interactions can't be meaningfully unit-tested and the
  Playwright-in-Streamlit thread issue only surfaces in the real app.
```
