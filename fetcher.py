# fetcher.py
import asyncio
import sys
import time
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout


@contextmanager
def _proactor_loop_policy():
    """Temporarily force a subprocess-capable event loop policy on Windows.

    Streamlit runs the script in a worker thread, and on Windows its server
    (Tornado) installs a SelectorEventLoop policy. A SelectorEventLoop cannot
    launch subprocesses, so Playwright — which calls asyncio.new_event_loop()
    and then spawns a Node driver process — fails with NotImplementedError.
    new_event_loop() obeys the global *policy*, not the thread's current loop,
    so we swap in WindowsProactorEventLoopPolicy for the duration of the
    Playwright session and restore the previous policy afterwards. The Proactor
    loop Playwright creates persists for the session even after we restore.
    """
    if sys.platform != "win32":
        yield
        return
    previous = asyncio.get_event_loop_policy()
    if not isinstance(previous, asyncio.WindowsProactorEventLoopPolicy):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    try:
        yield
    finally:
        asyncio.set_event_loop_policy(previous)

BASE_URL = "https://www.barcodelookup.com/"

# Primary selector for the big product image. Confirmed against the live page in
# Step 3a: the main photo lives in <div id="largeProductImage"><img ...></div>.
PRIMARY_IMAGE_SELECTOR = "#largeProductImage img"


@dataclass
class FetchResult:
    barcode: str
    status: str  # "ok" | "not_found" | "error"
    image_bytes: bytes | None = None
    extension: str = ""
    message: str = ""


@contextmanager
def make_browser():
    with _proactor_loop_policy():
        with sync_playwright() as p:
            # Use the system Edge (msedge channel) so the packaged .exe needs no
            # bundled/downloaded Chromium — Windows always has Edge.
            browser = p.chromium.launch(
                headless=True,
                channel="msedge",
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


# Product photos are served from this CDN host; site chrome (logos, ad banners)
# lives under barcodelookup.com/assets. The fallback must only ever pick a real
# product photo, never a logo/ad — confirmed against live pages in Step 3a.
PRODUCT_IMAGE_HOST = "images.barcodelookup.com"


def _find_main_image_url(page):
    """Return the URL of the biggest product image, or None."""
    # Primary: the known product-image container.
    el = page.query_selector(PRIMARY_IMAGE_SELECTOR)
    if el:
        src = el.get_attribute("src")
        if src:
            return src
    # Fallback: largest product-CDN <img> on the page by rendered area.
    # Restricted to PRODUCT_IMAGE_HOST so "Bad Barcode" pages (which still carry
    # logos/ad banners) do not yield a false positive.
    return page.evaluate(
        """(host) => {
            const imgs = Array.from(document.images);
            let best = null, bestArea = 0;
            for (const im of imgs) {
                const area = im.naturalWidth * im.naturalHeight;
                if (area > bestArea && im.src && im.src.includes(host)) {
                    bestArea = area; best = im.src;
                }
            }
            return bestArea > 10000 ? best : null;  // ignore tiny icons
        }""",
        PRODUCT_IMAGE_HOST,
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

        if resp is not None and resp.status == 404:
            return FetchResult(barcode, "not_found", message="page 404")

        # The real page (product OR "Bad Barcode") sits behind Cloudflare's
        # "Just a moment..." challenge. Wait for that to clear before reading the
        # title, otherwise we'd misread the challenge page. Confirmed live: the
        # challenge clears in a few seconds on a real browser/IP.
        try:
            page.wait_for_function(
                "() => !document.title.toLowerCase().includes('just a moment')",
                timeout=20000,
            )
        except PWTimeout:
            pass  # proceed with whatever loaded; checks below still apply

        # The site returns HTTP 200 with the title "Bad Barcode" for barcodes it
        # has no record of (confirmed live in Step 3a, e.g. 999999999999). Check
        # this BEFORE waiting on the image selector so missing barcodes return
        # fast instead of stalling on a doomed selector wait.
        if "bad barcode" in (page.title() or "").lower():
            return FetchResult(barcode, "not_found", message="bad barcode page")

        # Valid page: give the (possibly lazy-loaded) product image a moment.
        try:
            page.wait_for_selector(PRIMARY_IMAGE_SELECTOR, timeout=10000)
        except PWTimeout:
            pass  # fall through to the largest-image fallback

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
