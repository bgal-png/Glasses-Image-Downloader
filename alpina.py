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


def model_matches(name, tiles):
    """Eyewear tiles whose model core matches the name's model, longest first.

    Alpina tile titles carry suffixes the user's name lacks ("RAM 2.0 Q-LITE" vs
    "RAM 2.0…") and sometimes the user is more specific ("DEFEY 2" vs tile
    "DEFEY"), with color words sitting between model and suffix — so a plain
    substring of the full name is unreliable. Instead compare the MODEL cores:
    the tile matches when the search-query model and the tile norm are prefixes of
    one another.
    """
    q = normalize(search_query(name))
    if not q:
        return []
    out = [t for t in tiles
           if t["norm"] and (q.startswith(t["norm"]) or t["norm"].startswith(q))]
    out.sort(key=lambda t: len(t["norm"]), reverse=True)
    return out


def match_model(name, tiles):
    """Best eyewear tile for the name's model (longest core match), or None."""
    ms = model_matches(name, tiles)
    return ms[0] if ms else None


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


def _find_hires(src, html):
    """Return the 1200x1200 URL for the same image as `src`.

    CloudFront uses a DIFFERENT path-hash prefix per size, so the 1200 URL can't
    be built by swapping the size on the 600 URL (that 403s). But the page HTML
    contains the real 1200 URL; find it by matching the image's filename stem
    (article + hash, without the size suffix). Falls back to `src`.
    """
    if not src:
        return src
    base = src.rsplit("/", 1)[-1]
    m = re.match(r"(.+?)(?:_\d+x\d+(?:@2x)?)?\.(?:jpg|jpeg|png|webp)$", base)
    stem = m.group(1) if m else None
    if not stem:
        return src
    mm = re.search(r'https://[^"\' ]+/' + re.escape(stem) + r'_1200x1200\.jpg', html or "")
    return mm.group(0) if mm else src


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
        # The main product photo is the largest CloudFront product image on the
        # page. Image naming varies (A<code>_Main… vs plain numeric), so pick by
        # size rather than by a name marker, excluding site chrome.
        return pg.evaluate(
            """() => {
                const bad = /kategorie|banner|logo|icon|inspiration|technolog|protektoren|payment|zahlung/i;
                let best = null, area = 0;
                for (const im of Array.from(document.images)) {
                    if (!im.src.includes('cloudfront.net/media/image/')) continue;
                    if (bad.test(im.src)) continue;
                    const a = im.naturalWidth * im.naturalHeight;
                    if (a > area) { area = a; best = im.src; }
                }
                return best;
            }""")

    results = []
    with _proactor_loop_policy():
        with sync_playwright() as p:
            # Use the system Edge (msedge channel) so the packaged .exe needs no
            # bundled/downloaded Chromium — Windows always has Edge.
            b = p.chromium.launch(headless=True, channel="msedge")
            try:
                pg = b.new_page()
                pg.goto(url, wait_until="domcontentloaded", timeout=45000)
                pg.wait_for_timeout(2500)
                titles = [r.get_attribute("title") or ""
                          for r in pg.query_selector_all('input.option--input[name^="group"]')]
                frames = {}
                for t in titles:
                    f = normalize(t.split("/")[0])
                    if f and f not in frames:
                        frames[f] = t
                if not frames:  # no variant selector: use the default image
                    img = _main(pg)
                    if img:
                        results.append({"colorText": "", "image": _find_hires(img, pg.content())})
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
                            results.append({"colorText": t, "image": _find_hires(img, pg.content())})
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
    matches = model_matches(name, tiles)
    if not matches:
        return {"status": "none"}
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
