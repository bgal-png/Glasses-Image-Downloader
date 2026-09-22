# discovery2.py — second pass using the saved session (no login needed).
# Captures the product-listing JSON, a model's color-variants JSON, and the
# search call (by typing a model name into the site search), so we learn the
# exact endpoints + fields for matching by name.
import json
import pathlib
import time

from playwright.sync_api import sync_playwright

PLP_URL = "https://my.essilorluxottica.com/myl-hu/cs-CZ/plp/frames"
PROFILE_DIR = str(pathlib.Path(__file__).parent / "el_profile")
OUT = pathlib.Path(__file__).parent / "discovery_output2"
OUT.mkdir(exist_ok=True)

# Endpoints we care about (product data, not config/labels/analytics).
WANT = ("categories/", "/contents/", "partnumber", "variants", "search", "products/")
SKIP = ("labels", "prices", "availability", "inventory", "google-analytics", "page-footer",
        "menu", "notification", "precart", "documents", "tutorial", "logo", "privileges")

saved = []


def interesting(url):
    u = url.lower()
    if any(s in u for s in SKIP):
        return False
    return any(w in u for w in WANT)


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, channel="msedge", headless=True,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1440, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(resp):
            try:
                ct = resp.headers.get("content-type", "")
                if "application/json" in ct and interesting(resp.url):
                    try:
                        saved.append((resp.url, resp.json()))
                    except Exception:
                        pass
            except Exception:
                pass
        page.on("response", on_response)

        # 1) Load the listing (captures categories/contents product data).
        page.goto(PLP_URL, wait_until="domcontentloaded", timeout=60000)
        for _ in range(24):
            time.sleep(5)
            try:
                if any(k in page.inner_text("body")[:5000] for k in ("ZOBRAZIT", "Doporučená", "Arnette")):
                    break
            except Exception:
                continue
        print("listing loaded; calls so far:", len(saved), "logged_in_url:", page.url[:70])
        time.sleep(3)

        # 2) Try a search by model name to discover the search endpoint.
        for sel in ["input[type=search]", "input[placeholder*='ledat']", "input[aria-label*='ledat']",
                    "header input", "input[type=text]"]:
            try:
                box = page.query_selector(sel)
                if box:
                    box.click(); box.fill("0MU 01XV"); box.press("Enter")
                    print("searched via", sel)
                    time.sleep(6)
                    break
            except Exception as e:
                print("search attempt failed for", sel, str(e)[:50])

        # 3) Expand the first model to capture the variants endpoint.
        try:
            page.goto(PLP_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(6)
            btn = page.get_by_text("ZOBRAZIT", exact=False).first
            btn.click(timeout=6000)
            time.sleep(6)
        except Exception as e:
            print("variant expand failed:", str(e)[:80])

        # Save everything captured.
        seen = set()
        n = 0
        for url, body in saved:
            key = url.split("?")[0]
            tag = key.split("/fo-bff/")[-1].replace("/", "_")[:60]
            fname = f"{n:02d}_{tag}.json"
            (OUT / fname).write_text(json.dumps({"url": url, "body": body}, indent=2)[:300000], encoding="utf-8")
            n += 1
        print(f"DONE. saved {n} product-related JSON bodies to {OUT}")
        ctx.close()


if __name__ == "__main__":
    main()
