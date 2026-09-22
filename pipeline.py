# pipeline.py — Qt-free orchestration shared by the desktop app.
#
# Each run_* function drives one image source over the frames that still need an
# image and returns a dict keyed by row index:
#   {idx: {"image": bytes, "ext": str}}        -> a downloaded image
#   {idx: {"candidates": [{"label","image_url"}]}}  -> ambiguous, user must pick
# A returned {"_needs_login": True} means the source could not authenticate.
#
# It builds on the same core modules the Streamlit app uses (fetcher, luxottica,
# alpina, safilo) — no Qt, no Streamlit, so it is testable headlessly.
from __future__ import annotations

import os
import re

from fetcher import make_browser, fetch_image, download_url_bytes
import luxottica
import alpina
import safilo


def _names_todo(records, images):
    """Row indices that have a name and no image yet."""
    return [i for i in range(len(records)) if records[i].get("name") and i not in images]


def run_barcode(records, todo, delay=1.5, progress=None):
    """barcodelookup.com by barcode (headless Edge)."""
    out = {}
    bc_todo = [i for i in todo if records[i].get("barcode")]
    with make_browser() as browser:
        for n, i in enumerate(bc_todo):
            if progress:
                progress((n + 1) / max(len(bc_todo), 1), f"Barcode {n + 1}/{len(bc_todo)}")
            r = fetch_image(browser, records[i]["barcode"], delay=delay)
            if r.status == "ok" and r.image_bytes:
                out[i] = {"image": r.image_bytes, "ext": r.extension}
    return out


def run_alpina(records, todo, progress=None):
    """alpina-sports.com (public, headless Edge)."""
    out = {}
    todo = [i for i in todo if records[i].get("name")]
    for n, i in enumerate(todo):
        if progress:
            progress((n + 1) / max(len(todo), 1), f"Alpina {n + 1}/{len(todo)}")
        r = alpina.resolve(records[i]["name"])
        if r["status"] == "ok":
            out[i] = {"image": r["image"], "ext": r["ext"]}
        elif r["status"] == "choose":
            out[i] = {"candidates": r["candidates"]}
    return out


def run_luxottica(records, todo, progress=None):
    """EssilorLuxottica (headless; auto-login if credentials are stored)."""
    out = {}
    todo = [i for i in todo if records[i].get("name")]
    with luxottica.open_context(headless=True) as ctx:
        if not luxottica.ensure_logged_in(ctx):
            return {"_needs_login": True}
        if progress:
            progress(0.0, "Loading EssilorLuxottica catalogue…")
        index = luxottica.load_or_build_index(
            ctx,
            progress=lambda c, t: progress and progress(
                min(c / t, 1.0) if t else 0.0, f"Catalogue {c}/{t or '?'}"),
        )
        for n, i in enumerate(todo):
            if progress:
                progress((n + 1) / max(len(todo), 1), f"EssilorLuxottica {n + 1}/{len(todo)}")
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
                    out[i] = {"image": dl[0], "ext": dl[1]}
            else:
                out[i] = {"candidates": [
                    {"label": v.get("colorCode") or m["partNumber"], "image_url": v["image"]}
                    for v in variants
                ]}
    return out


def run_safilo(records, todo, progress=None):
    """Safilo (youandsafilo.com) — opens a VISIBLE window; user logs in once."""
    out = {}
    todo = [i for i in todo if records[i].get("name")]
    with safilo.open_context(headless=False) as ctx:
        if not (safilo.is_logged_in(ctx) or safilo.login_in_context(ctx)):
            return {"_needs_login": True}
        for n, i in enumerate(todo):
            if progress:
                progress((n + 1) / max(len(todo), 1), f"Safilo {n + 1}/{len(todo)}")
            dl = safilo.resolve_image(ctx, records[i]["name"])
            if dl:
                out[i] = {"image": dl[0], "ext": dl[1]}
    return out


RUNNERS = {
    "barcode": run_barcode,
    "luxottica": run_luxottica,
    "alpina": run_alpina,
    "safilo": run_safilo,
}


def safe_name(text):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", text or "").strip("_")
    return cleaned or "image"


def save_images(records, images, out_dir):
    """Write each stored image as <barcode or name>.<ext> into out_dir.

    Returns the list of filenames written.
    """
    os.makedirs(out_dir, exist_ok=True)
    written = []
    used = set()
    for i, data in images.items():
        base = records[i].get("barcode") or safe_name(records[i].get("name", ""))
        fname = f"{base}{data['ext']}"
        n = 2
        while fname in used:
            fname = f"{base}_{n}{data['ext']}"
            n += 1
        used.add(fname)
        with open(os.path.join(out_dir, fname), "wb") as handle:
            handle.write(data["bytes"])
        written.append(fname)
    return written
