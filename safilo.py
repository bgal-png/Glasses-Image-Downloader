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


# --- Network (needs a live Safilo login; session cannot persist, so matching
# runs by searching the site per name within one live session) ---
import time
import urllib.parse
import pathlib
from contextlib import contextmanager

from playwright.sync_api import sync_playwright

from fetcher import _proactor_loop_policy

BASE = "https://www.youandsafilo.com"
def _data_dir():
    r"""Same reasoning as luxottica._data_dir: a frozen build's __file__ lives in
    PyInstaller's temp dir, so the Safilo profile must go to %LOCALAPPDATA%."""
    import os as _os
    import sys as _sys
    if getattr(_sys, "frozen", False):
        base = _os.environ.get("LOCALAPPDATA") or _os.path.expanduser("~")
        path = _os.path.join(base, "GlassesImageDownloader")
    else:
        path = _os.path.dirname(_os.path.abspath(__file__))
    _os.makedirs(path, exist_ok=True)
    return path


SAFILO_PROFILE_DIR = str(pathlib.Path(_data_dir()) / "safilo_profile")
FRAMES_CATEGORY = "0ZG7T000000PB0fWAG"


def _clear_profile_lock():
    """Remove stale Chromium singleton locks so a leftover browser can't block
    the next launch (a recurring failure with this persistent profile)."""
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        try:
            (pathlib.Path(SAFILO_PROFILE_DIR) / name).unlink()
        except Exception:
            pass


@contextmanager
def open_context(headless=True):
    _clear_profile_lock()
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


def _logged_in_page(ctx):
    """Return ANY open page that is on youandsafilo and NOT the login page.

    Safilo's login can land the catalogue in a different tab than the one we
    navigated, so we scan every page in the context, not just the first.
    """
    for pg in ctx.pages:
        try:
            u = pg.url or ""
            if "youandsafilo.com" in u and "/login" not in u and "about:blank" not in u:
                return pg
        except Exception:
            pass
    return None


def _page(ctx):
    return _logged_in_page(ctx) or (ctx.pages[0] if ctx.pages else ctx.new_page())


def _category_url(cat_id):
    return f"{BASE}/cs/category/rootother/x/{cat_id}"


def _search_url(name):
    return f"{BASE}/cs/global-search/{urllib.parse.quote(name)}"


def is_logged_in(ctx):
    """True if any open page is on youandsafilo and NOT the login page."""
    return _logged_in_page(ctx) is not None


def login_in_context(ctx, timeout=300):
    """Poll a VISIBLE context until ANY tab is off the login page (logged in)."""
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        page.goto(_category_url(FRAMES_CATEGORY), wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(4)
        if _logged_in_page(ctx) is not None:
            return True
    return False


# Product tiles: each card is <a href="/cs/product/{modelCode}"> containing the
# image (modelCode+colorCode in the DAM URL) and a .plp--product__name element.
# textContent (not innerText) is used so off-screen tiles still yield their name.
_SCRAPE_JS = r"""() => {
    const out = [];
    for (const a of Array.from(document.querySelectorAll('a[href*="/cs/product/"]'))) {
        const img = a.querySelector('img[src*="getimagenofb"]');
        if (!img) continue;
        const m = img.src.match(/modelCode=([^&]+)&colorCode=([^&]+)/);
        if (!m) continue;
        const nameEl = a.querySelector('.plp--product__name, .field-item');
        const name = nameEl ? (nameEl.getAttribute('title') || nameEl.textContent || '') : '';
        out.push({modelText: name.replace(/\s+/g, ' ').trim().slice(0, 80),
                  modelCode: decodeURIComponent(m[1]), colorCode: decodeURIComponent(m[2])});
    }
    return out;
}"""


def _scrape_tiles(page):
    tiles = page.evaluate(_SCRAPE_JS)
    out, seen = [], set()
    for t in tiles:
        key = (t["modelCode"], t["colorCode"])
        if t["modelCode"] and key not in seen:
            seen.add(key)
            out.append({**t, "norm": normalize(t["modelText"])})
    return out


def _search_query(name):
    """Reduce a full name to the Safilo MODEL DESIGNATION for the site search.

    The catalogue names models by an all-caps code + number (e.g. "BOSS 1949",
    "MARC 496", "ETRO 0087"), NOT by the marketing brand name — and searching the
    marketing name returns nothing (Safilo splits "Hugo Boss" into "BOSS"/"HUGO",
    so "Hugo Boss BOSS 1949" -> 0 results). We take the first all-caps alpha token
    followed by a token containing a digit. Examples:
      "Hugo Boss BOSS 1949 FWM"            -> "BOSS 1949"
      "Marc Jacobs MARC 496/SHINY 807/IR"  -> "MARC 496"
      "ETRO 0087"                          -> "ETRO 0087"
    Falls back to tokens up to the first digit-bearing token.
    """
    head = (name or "").split("/")[0]
    tokens = head.split()
    for i in range(len(tokens) - 1):
        t, nxt = tokens[i], tokens[i + 1]
        if len(t) >= 2 and t.isupper() and t.isalpha() and any(c.isdigit() for c in nxt):
            return f"{t} {nxt}"
    out = []
    for t in tokens:
        out.append(t)
        if any(c.isdigit() for c in t):
            break
    return " ".join(out) if out else head.strip()


_SEARCH_BOX_SELECTORS = [
    "input[placeholder*='ledat']", "input[type=search]",
    "input[aria-label*='ledat']", "input[name*='search']", "input[type=text]",
]


def _find_search_box(page):
    for sel in _SEARCH_BOX_SELECTORS:
        try:
            el = page.query_selector(sel)
            if el:
                return el
        except Exception:
            pass
    return None


def search_products(ctx, name, timeout_ms=15000):
    """Search the site for `name` (trimmed) via the search box and return tiles.

    Direct navigation to /cs/global-search/... does NOT populate the SPA results,
    so we type into the site's own search box (what actually triggers a search),
    then poll until product tiles render.
    """
    page = _page(ctx)
    url = page.url or ""
    if "youandsafilo.com" not in url or "/login" in url:
        try:
            page.goto(_category_url(FRAMES_CATEGORY), wait_until="domcontentloaded", timeout=60000)
        except Exception:
            return []
        page.wait_for_timeout(3000)
    box = _find_search_box(page)
    if not box:
        return []
    try:
        box.click()
        box.fill(_search_query(name))
        box.press("Enter")
    except Exception:
        return []
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        page.wait_for_timeout(1500)
        if "/login" in page.url:
            return []
        tiles = _scrape_tiles(page)
        if tiles:
            return tiles
    return _scrape_tiles(page)


def resolve_image(ctx, name):
    """Search `name`, match a model, and download its official image bytes.

    IMPORTANT: the color codes in the user's names (e.g. 807, FWM) are NOT the
    codes Safilo's image API uses (which returns HTTP 410 for them). The valid
    color codes come from the catalogue tiles, so we download using the matched
    model's tile colorCode(s), not the name's color. Returns (bytes, ext) or None.
    """
    from fetcher import download_url_bytes
    tiles = search_products(ctx, name)
    if not tiles:
        return None
    m = match(name, tiles)
    if not m:
        return None
    model = m["modelCode"]
    colors = []
    for t in tiles:  # colors for the matched model first
        if t["modelCode"] == model and t["colorCode"] and t["colorCode"] not in colors:
            colors.append(t["colorCode"])
    for t in tiles:  # then any other tile color, as a last resort
        if t["colorCode"] and t["colorCode"] not in colors:
            colors.append(t["colorCode"])
    for c in colors:
        dl = download_url_bytes(image_url(model, c))
        if dl and len(dl[0]) > 2000:
            return dl
    return None
