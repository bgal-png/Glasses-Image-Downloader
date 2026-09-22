# discovery_safilo2.py — second Safilo pass: log in, then drive the site's own
# search so the page makes an AUTHENTICATED /search/products call, and capture
# that response + the rendered product tiles (real image URLs). ASCII-only prints.
import json
import pathlib
import time

from playwright.sync_api import sync_playwright

CATEGORY_URL = "https://www.youandsafilo.com/cs/category/rootother/br%C3%BDle/0ZG7T000000PB0fWAG"
PROFILE_DIR = str(pathlib.Path(__file__).parent / "safilo_profile")
OUT = pathlib.Path(__file__).parent / "discovery_safilo_out2"
OUT.mkdir(exist_ok=True)

SEARCH_TERMS = ["BOSS 1569", "Marc Jacobs MARC 496", "Carrera"]
search_calls = []


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, channel="msedge", headless=False,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            no_viewport=True,
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_resp(r):
            if "search/products" in r.url and r.request.method == "GET":
                try:
                    search_calls.append({"url": r.url, "status": r.status, "body": r.json()})
                except Exception:
                    search_calls.append({"url": r.url, "status": r.status, "body": None})
        page.on("response", on_resp)

        print("Opening Safilo. Log in, then leave it on the frames category.")
        try:
            page.goto(CATEGORY_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print("goto note:", str(e)[:100])

        logged_in = False
        for _ in range(120):
            time.sleep(5)
            try:
                has_pw = page.query_selector("input[type=password]") is not None
                url = page.url
                imgs = page.evaluate("() => document.images.length")
            except Exception:
                continue
            on_cat = "/category/" in url and "youandsafilo.com" in url
            print("  waiting login... pw=%s on_category=%s imgs=%s" % (has_pw, on_cat, imgs))
            if not has_pw and on_cat and imgs > 10:
                logged_in = True
                break
        if not logged_in:
            print("Login not confirmed; dumping anyway.")
            (OUT / "notes.txt").write_text("login not confirmed", encoding="utf-8")

        time.sleep(4)

        # Find the search box.
        box = None
        for sel in ["input[type=search]", "input[placeholder*=ledat]", "input[placeholder*=earch]",
                    "input[name*=search]", "input[aria-label*=ledat]", "input[type=text]"]:
            try:
                box = page.query_selector(sel)
                if box:
                    print("search box via", sel)
                    break
            except Exception:
                pass

        for term in SEARCH_TERMS:
            try:
                if box:
                    box.click()
                    box.fill(term)
                    box.press("Enter")
                    page.wait_for_timeout(8000)
                    print("searched:", term, "-> url", page.url[:80])
            except Exception as e:
                print("search failed for", term, str(e)[:80])
            # re-grab box (page may have navigated)
            try:
                box = (page.query_selector("input[type=search]")
                       or page.query_selector("input[type=text]"))
            except Exception:
                box = None

        # Scrape rendered product tiles + real image srcs (safilo CDNs).
        try:
            tiles = page.evaluate(
                """() => {
                    const imgs = Array.from(document.images)
                        .filter(i => i.src && i.naturalWidth > 60)
                        .map(i => ({src: i.src, alt: (i.alt||'').slice(0,80), w: i.naturalWidth}));
                    return imgs.slice(0, 60);
                }"""
            )
            (OUT / "tile_images.json").write_text(json.dumps(tiles, indent=2), encoding="utf-8")
        except Exception as e:
            print("tile scrape failed:", str(e)[:80])

        try:
            (OUT / "after_search.html").write_text(page.content(), encoding="utf-8")
        except Exception:
            pass
        (OUT / "search_calls.json").write_text(json.dumps(search_calls, indent=2)[:800000], encoding="utf-8")
        print("DONE. search/products calls captured:", len(search_calls))
        ctx.close()


if __name__ == "__main__":
    main()
