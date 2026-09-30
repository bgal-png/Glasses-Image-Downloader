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


import json
import os
import pathlib
import sys
import time
import urllib.parse
from contextlib import contextmanager

from playwright.sync_api import sync_playwright

from fetcher import _proactor_loop_policy  # reuse Windows event-loop fix

BASE = "https://my.essilorluxottica.com"


def _data_dir():
    r"""Where the login profile and catalogue index live.

    When frozen, __file__ sits inside PyInstaller's temp extraction dir, which
    Windows wipes on exit — the login and the ~4700-model index would be thrown
    away on every launch (re-login + a multi-minute rebuild each run). Keep them
    in %LOCALAPPDATA%\GlassesImageDownloader like the rest of the family.
    """
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        path = os.path.join(base, "GlassesImageDownloader")
    else:
        path = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(path, exist_ok=True)
    return path


EL_PROFILE_DIR = str(pathlib.Path(_data_dir()) / "el_profile")
INDEX_CACHE = pathlib.Path(_data_dir()) / "el_catalog_index.json"
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


# A Luxottica style code as it appears in a product name: 2-3 letters then
# digits, sometimes a trailing letter — "BE1398", "EA3285U", "RB2140", "OO9431".
_MODEL_TOKEN = re.compile(r"^[A-Z]{2,3}\d{3,5}[A-Z0-9]{0,3}$")


def probe_model(ctx, name):
    """Resolve a name straight against the catalogue: (partNumber, colorGuess, variants).

    The indexed listing covers only one catalogue category, so plenty of real
    models (e.g. 0BE1398, 0EA1183) are missing from it — but the variants
    endpoint answers for ANY partNumber. So when the index misses, take the
    style code out of the name, try "0<CODE>", and keep it if it has variants.
    Returns (None, "", []) when nothing resolves.
    """
    tokens = (name or "").split()
    for i, token in enumerate(tokens):
        code = token.upper().strip(",.;")
        if not _MODEL_TOKEN.match(code):
            continue
        for candidate in ("0" + code, code):
            variants = get_variants(ctx, candidate)
            if variants:
                colour = normalize(tokens[i + 1]) if i + 1 < len(tokens) else ""
                return candidate, colour, variants
        break  # first style-code-looking token is the model; don't keep hunting
    return None, "", []


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


# --- Optional auto-login using credentials in the OS keyring (Windows Vault) ---
import keyring

EL_KEYRING_SERVICE = "glasses-image-downloader-el"


def get_credentials():
    """Return (username, password) from the OS keyring, or None."""
    try:
        u = keyring.get_password(EL_KEYRING_SERVICE, "username")
        p = keyring.get_password(EL_KEYRING_SERVICE, "password")
        return (u, p) if u and p else None
    except Exception:
        return None


def has_credentials():
    return get_credentials() is not None


def set_credentials(username, password):
    keyring.set_password(EL_KEYRING_SERVICE, "username", username)
    keyring.set_password(EL_KEYRING_SERVICE, "password", password)


def clear_credentials():
    for k in ("username", "password"):
        try:
            keyring.delete_password(EL_KEYRING_SERVICE, k)
        except Exception:
            pass


def _auto_login(ctx, username, password):
    """Drive the Azure AD B2C login (username step -> password step). Returns bool.

    Uses generic selectors so it survives id changes: #signInName then CONTINUE,
    then any input[type=password] + its submit. Falls back (returns False) on
    anything unexpected (MFA, captcha, changed flow) so the caller can go manual.
    """
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        page.goto(BASE + PLP_PATH, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("#signInName", timeout=25000)
        page.fill("#signInName", username)
        btn = page.query_selector("#continue") or page.query_selector("button[type=submit]")
        if btn:
            btn.click()
        page.wait_for_selector("input[type=password]", timeout=25000)
        page.fill("input[type=password]", password)
        btn = page.query_selector("#continue") or page.query_selector("button[type=submit]")
        if btn:
            btn.click()
        page.wait_for_url("**my.essilorluxottica.com/**", timeout=45000)
        page.wait_for_timeout(3000)
        return is_logged_in(ctx)
    except Exception:
        return False


def ensure_logged_in(ctx):
    """True if already logged in, or if auto-login with stored credentials works."""
    if is_logged_in(ctx):
        return True
    creds = get_credentials()
    return bool(creds and _auto_login(ctx, creds[0], creds[1]))
