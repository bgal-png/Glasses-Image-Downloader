# app.py
import io
import re
import zipfile

import pandas as pd
import streamlit as st

from barcode_parser import parse_records
from fetcher import make_browser, fetch_image, search_links, download_url_bytes
import luxottica
import safilo
import alpina

st.set_page_config(page_title="Glasses Image Downloader", page_icon="📷")
st.title("📷 Glasses Image Downloader")
st.caption("Barcode + EssilorLuxottica matching, with manual fill/replace.")


def _safe_name(text):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
    return cleaned or "image"


def _store_image(idx, image_bytes, extension, source):
    st.session_state.images[idx] = {"bytes": image_bytes, "ext": extension or ".jpg", "source": source}


def _init_state(recs):
    """Commit a fresh set of frames; reset all per-run state."""
    st.session_state.records = recs
    st.session_state.results = [{"status": "needs_image" if r["name"] else "no_source"} for r in recs]
    st.session_state.images = {}
    st.session_state.applied = {}
    st.session_state.el_variants = {}
    st.session_state.alpina_variants = {}
    st.session_state.pop("redo_select", None)


for key, default in [("records", []), ("results", []), ("images", {}),
                     ("applied", {}), ("el_variants", {}), ("alpina_variants", {}), ("el_needs_login", False)]:
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

# --- 2. Get images (either source, in any order) ---
st.subheader("2. Get images")
st.caption("Use either or both: barcodes (any site) and/or EssilorLuxottica (official, Luxottica brands).")
ca, cb, cc, cd = st.columns(4)
with ca:
    do_barcode = st.button("Run barcode lookup", type="primary", disabled=not records)
    delay = st.slider("Delay between barcodes (seconds)", 0.0, 5.0, 1.5, 0.5)
with cb:
    do_el = st.button("Match via EssilorLuxottica", disabled=not records)
    st.caption("Ray-Ban, Oakley, Persol, Prada, Miu Miu, Versace…")
with cc:
    do_safilo = st.button("Match via Safilo", disabled=not records)
    st.caption("Hugo Boss, Marc Jacobs, Carrera, Kate Spade… (opens a login window)")
with cd:
    do_alpina = st.button("Match via Alpina", disabled=not records)
    st.caption("Alpina sunglasses & sports/ski glasses (public, no login)")

if do_barcode:
    _init_state(records)
    progress = st.progress(0.0, text="Starting browser…")
    with make_browser() as browser:
        for i, rec in enumerate(records):
            progress.progress((i + 1) / len(records), text=f"[{i+1}/{len(records)}] {rec['barcode'] or rec['name']}")
            if rec["barcode"]:
                result = fetch_image(browser, rec["barcode"], delay=delay)
                if result.status == "ok" and result.image_bytes:
                    _store_image(i, result.image_bytes, result.extension, "barcode")
                    st.session_state.results[i] = {"status": "found"}
    progress.progress(1.0, text="Done.")

if do_el:
    # Start a fresh run only if these frames aren't the committed set (so EL run
    # after a barcode run keeps the barcode images instead of wiping them).
    if st.session_state.records != records:
        _init_state(records)
    with luxottica.open_context(headless=True) as ctx:
        if not luxottica.ensure_logged_in(ctx):  # tries saved-credential auto-login
            st.session_state.el_needs_login = True
        else:
            st.session_state.el_needs_login = False
            prog = st.progress(0.0, text="Loading catalogue…")
            index = luxottica.load_or_build_index(
                ctx, progress=lambda n, t: prog.progress(min(n / t, 1.0) if t else 0.0,
                                                          text=f"Catalogue: {n}/{t or '?'}"))
            prog.progress(1.0, text=f"Catalogue ready ({len(index)} models). Matching…")
            recs = st.session_state.records
            todo = [i for i in range(len(recs)) if recs[i]["name"] and i not in st.session_state.images]
            for i in todo:
                m = luxottica.match_model(recs[i]["name"], index)
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

if do_safilo:
    # Safilo's session can't persist, so this searches the live site per name in
    # one visible-browser session (log in once when the window opens). WATCH THE
    # SAFILO EDGE WINDOW — this Streamlit page is frozen while it runs.
    if st.session_state.records != records:
        _init_state(records)
    recs = st.session_state.records
    todo = [i for i in range(len(recs)) if recs[i]["name"] and i not in st.session_state.images]
    st.warning("A Safilo Edge window is opening — **log in there**, then watch it "
               "search. This page stays frozen until it finishes.")
    matched = 0
    with st.spinner("Running Safilo… (log in and watch the Edge window)"):
        with safilo.open_context(headless=False) as ctx:
            if not safilo.login_in_context(ctx, timeout=300):
                st.session_state.safilo_msg = "Safilo login not detected — click 'Match via Safilo' and try again."
            else:
                for i in todo:
                    dl = safilo.resolve_image(ctx, recs[i]["name"])
                    if dl:
                        _store_image(i, dl[0], dl[1], "safilo")
                        matched += 1
                st.session_state.safilo_msg = f"Safilo finished — matched {matched} of {len(todo)} named frame(s)."
    st.rerun()

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

if st.session_state.get("safilo_msg"):
    st.info(st.session_state.pop("safilo_msg"))

if st.session_state.el_needs_login:
    st.warning("Your EssilorLuxottica session is expired or not set up.")
    if st.button("Log in to EssilorLuxottica"):
        with st.spinner("Opening a browser window — log in there…"):
            ok = luxottica.login()
        st.session_state.el_needs_login = not ok
        if ok:
            st.success("Logged in. Click 'Match via EssilorLuxottica' again.")

with st.expander("⚙️ EssilorLuxottica auto-login (optional)"):
    st.caption("Stored securely in Windows Credential Manager — no plaintext file. "
               "When set, the tool logs into EssilorLuxottica by itself if the session expires.")
    if luxottica.has_credentials():
        st.success("Auto-login credentials are saved.")
        if st.button("Clear saved credentials"):
            luxottica.clear_credentials()
            st.rerun()
    else:
        el_user = st.text_input("Username / email", key="el_user")
        el_pass = st.text_input("Password", type="password", key="el_pass")
        if st.button("Save credentials"):
            if el_user and el_pass:
                luxottica.set_credentials(el_user, el_pass)
                st.success("Saved to Windows Credential Manager.")
                st.rerun()
            else:
                st.warning("Enter both username and password first.")

if st.session_state.records:
    records = st.session_state.records
    results = st.session_state.results
    images = st.session_state.images

    # --- 3. Results table ---
    st.subheader("3. Results")

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

    # --- 4. EssilorLuxottica color pick ---
    el_pick = [i for i in st.session_state.el_variants if i not in images]
    if el_pick:
        st.subheader("4. Pick a color (EssilorLuxottica)")
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

    # --- 5. Pick frames to redo/replace ---
    imaged = [i for i in range(len(records)) if i in images]
    if imaged:
        st.subheader("5. Replace an image you don't like")
        st.multiselect("Frames to redo", options=imaged,
                       format_func=lambda i: f"{records[i]['barcode'] or '(no barcode)'} — {records[i]['name'] or '(no name)'}",
                       key="redo_select")
    redo = list(st.session_state.get("redo_select", []))

    # --- 6. Fill / replace by name (paste URL / upload) ---
    misses = [i for i, r in enumerate(results) if r["status"] == "needs_image" and i not in images]
    fill_list = sorted(set(misses) | set(redo))
    if fill_list:
        st.subheader("6. Fill / replace images")
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

    # --- 7. ZIP ---
    st.subheader("7. Download")
    by_barcode = sum(1 for v in images.values() if v["source"] == "barcode")
    el_count = sum(1 for v in images.values() if v["source"] == "luxottica")
    sf_count = sum(1 for v in images.values() if v["source"] == "safilo")
    al_count = sum(1 for v in images.values() if v["source"] == "alpina")
    manual = len(images) - by_barcode - el_count - sf_count - al_count
    st.write(f"{len(images)} image(s): {by_barcode} barcode, {el_count} EssilorLuxottica, "
             f"{sf_count} Safilo, {al_count} Alpina, {manual} manual.")
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
