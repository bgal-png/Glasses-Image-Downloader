# tests/test_fetcher_live.py
import asyncio
import os
import sys
import threading

import pytest
from urllib.parse import quote

from fetcher import make_browser, fetch_image, search_links, download_url_bytes

# This test hits the real site + Cloudflare. Run explicitly with:
#   RUN_LIVE=1 pytest tests/test_fetcher_live.py -v -s
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE") != "1",
    reason="set RUN_LIVE=1 to run live network tests",
)


def test_fetch_known_barcode_returns_image():
    with make_browser() as browser:
        result = fetch_image(browser, "197737257521", delay=0.0)
    assert result.status == "ok", result.message
    assert result.image_bytes is not None
    assert len(result.image_bytes) > 5000  # a real product image, not a 1px pixel
    assert result.extension in (".jpg", ".jpeg", ".png", ".webp")


def test_fetch_nonexistent_barcode_is_not_found():
    # 000000000000 is actually a real registered product on the site; use a
    # genuinely-unregistered code, which the site serves as a "Bad Barcode" page.
    with make_browser() as browser:
        result = fetch_image(browser, "999999999999", delay=0.0)
    assert result.status in ("not_found", "error"), result.message
    assert result.image_bytes is None


@pytest.mark.skipif(sys.platform != "win32", reason="Streamlit/Tornado loop issue is Windows-specific")
def test_fetch_works_under_streamlit_like_conditions():
    # Regression guard: Streamlit runs the script in a worker thread, and on
    # Windows Tornado installs a SelectorEventLoop policy, which cannot spawn the
    # subprocess Playwright needs (NotImplementedError). make_browser() must
    # tolerate this. Reproduce it: selector policy + non-main thread.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    captured = {}

    def work():
        try:
            with make_browser() as browser:
                captured["result"] = fetch_image(browser, "197737257521", delay=0.0)
        except Exception as exc:  # noqa: BLE001 - we assert on it below
            captured["error"] = exc

    thread = threading.Thread(target=work)
    thread.start()
    thread.join()

    assert "error" not in captured, f"fetch crashed in worker thread: {captured.get('error')!r}"
    assert captured["result"].status == "ok"
    assert captured["result"].image_bytes is not None
    # The selector policy must be restored after the session (no leakage).
    assert isinstance(asyncio.get_event_loop_policy(), asyncio.WindowsSelectorEventLoopPolicy)


def test_search_links_builds_encoded_urls():
    links = search_links("Hugo Boss BOSS 1949 FWM")
    assert links["Google Images"] == (
        "https://www.google.com/search?tbm=isch&q="
        + quote("Hugo Boss BOSS 1949 FWM")
    )
    assert "smartbuyglasses.com/search?q=" in links["SmartBuyGlasses"]


def test_download_url_bytes_fetches_real_image():
    url = "https://images.barcodelookup.com/162952/1629522796-2.jpg"
    result = download_url_bytes(url)
    assert result is not None
    body, ext = result
    assert len(body) > 5000
    assert ext in (".jpg", ".jpeg", ".png", ".webp")


def test_download_url_bytes_returns_none_for_bad_url():
    assert download_url_bytes("https://images.barcodelookup.com/does-not-exist-xyz.jpg") is None
