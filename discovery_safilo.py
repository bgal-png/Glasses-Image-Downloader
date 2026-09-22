# discovery_safilo.py — one-off: learn how the youandsafilo.com catalogue works.
# Opens a real Edge window (dedicated profile), you log in once, then it dumps
# the page + network structure to ./discovery_safilo_out/ for analysis.
import json
import pathlib
import time

from playwright.sync_api import sync_playwright

FRAMES_URL = "https://www.youandsafilo.com/cs/category/rootother/br%C3%BDle/0ZG7T000000PB0fWAG"
PROFILE_DIR = str(pathlib.Path(__file__).parent / "safilo_profile")
OUT = pathlib.Path(__file__).parent / "discovery_safilo_out"
OUT.mkdir(exist_ok=True)

# JSON calls that look like product/catalogue data (not analytics/assets).
WANT = ("product", "category", "search", "catalog", "item", "sku", "tile", "grid",
        "commerce", "graphql", "/services/", "webruntime", "api")
SKIP = ("google", "analytics", "gtm", "doubleclick", "cookie", "consent", "font",
        "adobe", "cdn-cgi", "telemetry", "beacon")

saved = []
all_calls = []


def interesting(url):
    u = url.lower()
    if any(s in u for s in SKIP):
        return False
    return any(w in u for w in WANT)


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, channel="msedge", headless=False,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            no_viewport=True,
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(resp):
            try:
                ct = resp.headers.get("content-type", "")
                url = resp.url
                all_calls.append((resp.request.method, resp.status, ct[:40], url))
                if "application/json" in ct and interesting(url):
                    try:
                        saved.append((url, resp.json()))
                    except Exception:
                        pass
            except Exception:
                pass
        page.on("response", on_response)

        print("Opening Safilo. Log in if prompted, then leave it on the frames category.")
        try:
            page.goto(FRAMES_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print("initial goto note:", str(e)[:120])

        logged_in = False
        for _ in range(120):  # up to ~10 min for manual login
            time.sleep(5)
            try:
                has_pw = page.query_selector("input[type=password]") is not None
                url = page.url
                imgs = page.evaluate("() => document.images.length")
            except Exception as e:
                print("  (page busy:", str(e)[:50], ")")
                continue
            on_category = "/category/" in url and "youandsafilo.com" in url
            print(f"  waiting… pw={has_pw} on_category={on_category} imgs={imgs} url={url[:70]}")
            if not has_pw and on_category and imgs > 10:
                logged_in = True
                break
        if not logged_in:
            print("Did not confirm a logged-in category page; dumping whatever loaded.")

        time.sleep(5)  # let product tiles + their API settle

        try:
            (OUT / "frames.html").write_text(page.content(), encoding="utf-8")
        except Exception as e:
            print("html dump failed:", str(e)[:80])

        try:
            cards = page.evaluate(
                """() => Array.from(document.images)
                    .filter(i => i.naturalWidth > 80 && i.src.startsWith('http'))
                    .slice(0, 40)
                    .map(i => ({src: i.src, alt: (i.alt||'').slice(0,60),
                                w: i.naturalWidth, cls: i.className.slice(0,50)}))"""
            )
            (OUT / "images.json").write_text(json.dumps(cards, indent=2), encoding="utf-8")
        except Exception as e:
            print("images dump failed:", str(e)[:80])

        (OUT / "network_calls.txt").write_text(
            "\n".join(f"{m}\t{s}\t{ct}\t{u}" for (m, s, ct, u) in all_calls), encoding="utf-8")
        for n, (url, body) in enumerate(saved[:40]):
            tag = url.split("?")[0].split("/")[-1][:40] or f"body{n}"
            (OUT / f"{n:02d}_{tag}.json").write_text(
                json.dumps({"url": url, "body": body}, indent=2)[:300000], encoding="utf-8")

        print(f"DONE. {len(all_calls)} calls, {len(saved)} product-ish JSON bodies → {OUT}")
        ctx.close()


if __name__ == "__main__":
    main()
