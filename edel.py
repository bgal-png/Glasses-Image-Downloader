# edel.py — build edel-optics image URLs straight from a product name.
#
# Unlike every other source here this one needs no browser and no login: the
# shop names each picture after the product itself, so a row in the import
# file is enough to construct the exact image a human would right-click.
#
#   "Ray-Ban RB3793 001/31"        -> Ray-Ban-RB3793-001-31.jpg
#   "Polaroid PLD 4199/S/X 8CQ/XW" -> Polaroid-PLD-4199-S-X-8CQ-XW.jpg
#
# The rule is the whole name with every separator hyphenated — NOT a parsed
# brand/model/colour. An earlier version pulled out a single-token model code
# and silently found nothing for every brand whose code carries slashes or a
# space (all of Polaroid, for one).
#
# Two things the shop does that have to be handled:
#   * a product it does not stock answers 200 with a shared ~12 kB placeholder
#     rather than a 404, so responses are judged by content, not status;
#   * the CDN serves WebP while labelling it image/jpeg, so the bytes are
#     sniffed and converted.
import hashlib
import re

IMAGE = "https://img.edel-optics.com/{segment}/2000/nobg/{slug}.jpg"

# Sunglasses and optical frames sit on separate CDN paths and a name does not
# reliably say which, so both are tried.
SEGMENTS = ("eoProductsGlassesSunglasses", "eoProductsGlassesPrescription")

# Anything smaller than this is a placeholder or an error page, never a photo.
MIN_PHOTO_BYTES = 20000

_SEPARATORS = re.compile(r"[\s/]+")

# Checksums of the "no picture" images, learned on first contact: the first
# response too small to be a photo teaches us its hash, so a second placeholder
# variant costs one wasted row rather than a wrong image.
_PLACEHOLDERS = set()

# The CDN path that last returned a real photo, tried first for the next row.
_preferred = ""


def name_slug(name):
    """Turn a product name into the shop's file name.

    Spaces and slashes become hyphens; "&" is spelled out, the way the shop
    writes it ("Dolce & Gabbana" -> "Dolce-and-Gabbana").
    """
    text = (name or "").replace("&", "and")
    return re.sub(r"-{2,}", "-", _SEPARATORS.sub("-", text.strip())).strip("-")


def image_url(slug, segment=SEGMENTS[0]):
    return IMAGE.format(segment=segment, slug=slug)


def candidate_urls(name):
    """Every URL worth trying for a product name, most likely first."""
    slug = name_slug(name)
    if not slug:
        return []
    return [image_url(slug, segment) for segment in SEGMENTS]


def url_for_name(name):
    """The first candidate image URL, or None for an empty name."""
    urls = candidate_urls(name)
    return urls[0] if urls else None


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


def is_placeholder(data, known=None):
    """True when the response is the shop's "not stocked" image, not a photo."""
    if not data or len(data) < MIN_PHOTO_BYTES:
        return True
    pool = _PLACEHOLDERS if known is None else known
    return hashlib.md5(data).hexdigest() in pool


def resolve(name, fetch=None):
    """Return (bytes, ".jpg") for a product name, or None when not stocked.

    Tries each CDN path until one answers with a real photo. A batch is usually
    all one product type, so the path that last worked is tried first and most
    rows cost a single request.
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
            _PLACEHOLDERS.add(hashlib.md5(data).hexdigest())
            continue
        if hashlib.md5(data).hexdigest() in _PLACEHOLDERS:
            continue
        _preferred = next((s for s in SEGMENTS if s in url), _preferred)
        return to_jpeg(data), ".jpg"
    return None


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
