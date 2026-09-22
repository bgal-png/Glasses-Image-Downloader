# Manual Override for Any Frame Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user pull any already-imaged frame into the manual-fill area and replace its image (paste-URL/upload), with the new image winning in the ZIP.

**Architecture:** UI-only change to `app.py`. Add a `st.multiselect` of frames that currently have an image; the fill section renders the union of (auto misses) + (selected redo frames); each fill entry shows a preview of the current image; storing a new image overwrites it. Engine and parser unchanged.

**Tech Stack:** Streamlit (existing).

---

## File Structure

- `app.py` — MODIFY (single task): session-state init, results label logic, new redo multiselect, fill-list construction, per-entry current-image preview.

No engine/parser/test files change (this is glue verified in the real app).

---

## Task 1: Add manual override to the app

**Files:**
- Modify (full rewrite): `app.py`

- [ ] **Step 1: Replace `app.py` entirely with EXACTLY this content**

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
st.caption("Auto-downloads images by barcode; helps you fill or replace the rest by name.")


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
    # Clear any previous redo selection so the widget starts fresh.
    st.session_state.pop("redo_select", None)
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
            if rec["name"]:
                st.session_state.results.append({"status": "needs_image"})
            else:
                st.session_state.results.append({"status": "no_source"})
    progress.progress(1.0, text="Done.")

# --- 3. Results + manual assist (only after a run) ---
if st.session_state.results:
    records = st.session_state.records
    results = st.session_state.results
    images = st.session_state.images

    st.subheader("3. Results")

    def _label(i):
        status = results[i]["status"]
        if i in images and images[i]["source"] != "barcode":
            return f"✅ {images[i]['source']} image"
        if status == "found":
            return "✅ found by barcode"
        return {"needs_image": "✋ needs image",
                "no_source": "❌ no barcode & no name"}[status]

    rows = [{"Barcode": records[i]["barcode"], "Name": records[i]["name"], "Status": _label(i)}
            for i in range(len(records))]
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    # --- Pick found/imaged frames to redo ---
    imaged = [i for i in range(len(records)) if i in images]
    if imaged:
        st.subheader("4. Replace an image you don't like")
        st.caption("Pick frames whose image you want to swap out, then fill them below.")
        st.multiselect(
            "Frames to redo",
            options=imaged,
            format_func=lambda i: f"{records[i]['barcode'] or '(no barcode)'} — {records[i]['name'] or '(no name)'}",
            key="redo_select",
        )
    redo = list(st.session_state.get("redo_select", []))

    # --- Fill / replace section: misses + chosen redo frames ---
    misses = [i for i, r in enumerate(results)
              if r["status"] == "needs_image" and i not in images]
    fill_list = sorted(set(misses) | set(redo))
    if fill_list:
        st.subheader("5. Fill / replace images")
        st.caption("Open a search, find the right image, then paste its URL or upload the file.")
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

    # --- 6. ZIP ---
    st.subheader("6. Download")
    by_barcode = sum(1 for v in images.values() if v["source"] == "barcode")
    manual = len(images) - by_barcode
    st.write(f"{len(images)} image(s): {by_barcode} by barcode, {manual} added/replaced manually.")
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

Run (Bash):
```
cd "C:\Users\blank\Desktop\Random codes\barcode-image-downloader" && python -m py_compile app.py && (python -m streamlit run app.py --server.headless true --server.port 8606 >/tmp/st6.log 2>&1 &) && sleep 12 && curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8606/_stcore/health && cat /tmp/st6.log
```
Expected: `200`, no Python traceback in the log. Then stop the process listening on 8606:
```
powershell.exe -Command "Get-NetTCPConnection -LocalPort 8606 -State Listen | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id \$_ -Force }"
```

- [ ] **Step 3: Commit** — SKIP (not a git repo).

---

## Controller verification (after Task 1)

The controller drives the real running app:
1. Paste `197737257521, Hugo Boss BOSS 1949 FWM` and run barcode lookup → summary shows "1 by barcode".
2. In the "Frames to redo" multiselect, select that frame → it appears in the fill section WITH a current-image preview.
3. Paste a different known image URL into its box → table label flips to "✅ url image" and the download summary shows "0 by barcode, 1 added/replaced manually".
4. Download the ZIP → it contains `197737257521.jpg` with the NEW image's byte size (different from the original auto-found size), confirming the override replaced it under the same filename.

---

## Notes

- `st.session_state.get("redo_select", [])` reads the multiselect's persisted
  value; the run-button handler pops it so a fresh run clears stale selections.
- Label logic: any frame with a non-"barcode" image source reads as
  "✅ {source} image" (covers both filled misses and replaced found frames);
  unchanged barcode hits read "✅ found by barcode".
- The override works because `_store_image` overwrites `images[idx]` in place, so
  the ZIP (which iterates `images`) always uses the latest bytes.
```
