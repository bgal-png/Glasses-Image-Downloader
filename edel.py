# edel.py — build edel-optics image URLs straight from a product name.
#
# Unlike every other source here this one needs no browser and no login: the
# shop serves each frame from a predictable path, so a row in the import file
# is enough to construct the exact picture a human would right-click.
#
#   https://img.edel-optics.com/eoProductsGlassesSunglasses/2000/nobg/
#       Ray-Ban-RB3793-001-31.jpg
#
# A product the shop does not stock is NOT a 404 — it answers 200 with one
# shared ~12 kB placeholder, so the response has to be recognised by content.
import hashlib

from luxottica import model_candidates  # same model-code reader as the EL source

IMAGE = ("https://img.edel-optics.com/{segment}/2000/nobg/"
         "{brand}-{model}-{colour}.jpg")

# The shop keeps sunglasses and optical frames on separate CDN paths, and a
# name does not reliably say which it is (a model number hints, but "BE2443"
# style codes are not a rule we can trust), so both are tried.
SEGMENTS = ("eoProductsGlassesSunglasses", "eoProductsGlassesPrescription")

# Anything smaller than this is a placeholder or an error page, never a photo.
MIN_PHOTO_BYTES = 20000

# Checksums of the "no picture" images, learned on first contact: the first
# response that is too small to be a photo teaches us its hash, so a second
# placeholder variant costs one wasted row rather than a wrong image.
_PLACEHOLDERS = set()


def name_parts(name):
    """Split "Emporio Armani EA3285U 5017" into (brand, model, colour).

    Returns None when the name has no recognisable model code. The brand is
    whatever precedes the code, hyphen-joined the way the shop writes it; the
    colour is the last token with "/" turned into "-" ("001/31" -> "001-31").
    """
    tokens = (name or "").split()
    # A name copied from the EL catalogue can carry its leading zero (0RB3793);
    # the shop never does, and the code reader does not recognise that shape.
    plain = " ".join(t[1:] if len(t) > 3 and t[0] == "0" and t[1:2].isalpha() else t
                     for t in tokens)
    candidates = model_candidates(plain)
    if not candidates:
        return None
    model = candidates[0][0].lstrip("0")   # the catalogue's 0RB3793 is RB3793 here
    tokens = plain.split()
    upper = [t.upper().strip(",.;") for t in tokens]
    if model not in upper:
        return None
    at = upper.index(model)
    if at == 0 or at == len(tokens) - 1:
        return None                        # no brand in front, or no colour after
    return "-".join(tokens[:at]), model, tokens[-1].replace("/", "-")


def image_url(brand, model, colour, segment=SEGMENTS[0]):
    return IMAGE.format(segment=segment, brand=brand, model=model, colour=colour)


def brand_variants(brand):
    """Spellings the shop might use — it writes "&" as "and"."""
    out = [brand]
    spelled = brand.replace("-&-", "-and-").replace("&", "and")
    if spelled != brand:
        out.append(spelled)
    return out


def candidate_urls(name):
    """Every URL worth trying for a product name, most likely first."""
    parts = name_parts(name)
    if not parts:
        return []
    brand, model, colour = parts
    return [image_url(b, model, colour, segment)
            for segment in SEGMENTS
            for b in brand_variants(brand)]


def url_for_name(name):
    """The first candidate image URL, or None if the name can't be read."""
    urls = candidate_urls(name)
    return urls[0] if urls else None


def is_placeholder(data, known=None):
    """True when the response is the shop's "not stocked" image rather than a photo."""
    if not data or len(data) < MIN_PHOTO_BYTES:
        return True
    pool = _PLACEHOLDERS if known is None else known
    return hashlib.md5(data).hexdigest() in pool


def is_webp(data):
    """The CDN serves WebP from a .jpg path and still labels it image/jpeg, so
    the bytes are the only honest answer about the format."""
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def to_jpeg(data):
    """Convert WebP to JPEG so every source in the app yields the same format.

    Returns the original bytes when they are already JPEG, or if Pillow cannot
    read them — a WebP named .jpg is better than nothing.
    """
    if not is_webp(data):
        return data
    try:
        import io

        from PIL import Image
        image = Image.open(io.BytesIO(data))
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=92)
        return buffer.getvalue()
    except Exception:
        return data


def resolve(name, fetch=None):
    """Return (bytes, ".jpg") for a product name, or None when not stocked.

    Tries each candidate path/brand spelling until one answers with a real
    photo. A batch is usually all one product type, so the path that last
    worked is tried first and most rows cost a single request.
    """
    global _preferred
    urls = candidate_urls(name)
    if not urls:
        return None
    if _preferred:
        urls.sort(key=lambda u: _preferred not in u)
    download = fetch or _download
    for url in urls:
        data = download(url)
        if not data:
            continue
        if len(data) < MIN_PHOTO_BYTES:
            # Too small to be a photo: remember it so the rest of the run is cheap.
            _PLACEHOLDERS.add(hashlib.md5(data).hexdigest())
            continue
        if hashlib.md5(data).hexdigest() in _PLACEHOLDERS:
            continue
        _preferred = next((s for s in SEGMENTS if s in url), _preferred)
        return to_jpeg(data), ".jpg"
    return None


# The CDN path that last returned a real photo, tried first for the next row.
_preferred = ""


def reset():
    """Forget the learned placeholders and preferred path (used by tests)."""
    global _preferred
    _PLACEHOLDERS.clear()
    _preferred = ""


def _download(url, timeout=25):
    import urllib.request
    request = urllib.request.Request(url)
    request.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except Exception:
        return b""
