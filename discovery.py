# discovery.py — one-off: learn how the EssilorLuxottica catalogue works.
# Opens a real Edge window using a dedicated profile (so your main Edge is
# untouched). You log in once; it then dumps the page + network structure to
# ./discovery_output/ for analysis. Safe to re-run.
import json
import pathlib
import sys
import time

from playwright.sync_api import sync_playwright

PLP_URL = "https://my.essilorluxottica.com/myl-hu/cs-CZ/plp/frames"
PROFILE_DIR = str(pathlib.Path(__file__).parent / "el_profile")
OUT = pathlib.Path(__file__).parent / "discovery_output"
OUT.mkdir(exist_ok=True)

# Network calls that look like data APIs (not images/fonts/css).
API_HINTS = ("search", "product", "plp", "catalog", "frame", "/api", "graphql", "query", "sku", "model")

calls = []          # (method, url, status, content_type)
json_bodies = []    # (url, parsed-or-text snippet)


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR,
            channel="msedge",
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            no_viewport=True,
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(resp):
            try:
                ct = resp.headers.get("content-type", "")
                url = resp.url
                calls.append((resp.request.method, url, resp.status, ct))
                if "application/json" in ct and any(h in url.lower() for h in API_HINTS):
                    try:
                        body = resp.json()
                        json_bodies.append((url, body))
                    except Exception:
                        pass
            except Exception:
                pass

        page.on("response", on_response)

        print("Opening the catalogue. Log in if prompted, then leave it on the frames listing.")
        try:
            page.goto(PLP_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print("initial goto note:", str(e)[:120])

        # Wait until logged in: no password field present AND some product content.
        # Every check is wrapped — the page navigates during login and any single
        # call can throw "execution context destroyed"; we must NOT crash on that.
        logged_in = False
        for _ in range(120):  # up to ~10 min, patient for manual login
            time.sleep(5)
            try:
                has_pw = page.query_selector("input[type=password]") is not None
                text = page.inner_text("body")[:5000]
                cur = page.url
            except Exception as e:
                print(f"  (page busy/navigating: {str(e)[:60]})")
                continue
            looks_listing = any(k in text for k in ("ZOBRAZIT", "Značky", "Arnette", "Doporučená"))
            print(f"  waiting… password_field={has_pw} listing_markers={looks_listing} url={cur[:70]}")
            if not has_pw and looks_listing:
                logged_in = True
                break
        if not logged_in:
            print("Did not detect a logged-in listing in time; dumping whatever loaded anyway.")

        time.sleep(4)  # let listing API calls settle

        # 1) Save the PLP HTML
        try:
            (OUT / "plp.html").write_text(page.content(), encoding="utf-8")
        except Exception as e:
            print("plp.html capture failed:", str(e)[:80])

        # 2) Dump candidate product/model cards (text + image)
        try:
            cards = page.evaluate(
                """() => {
                    const imgs = Array.from(document.images)
                        .filter(i => i.naturalWidth > 80 && i.src.startsWith('http'))
                        .slice(0, 40)
                        .map(i => ({src: i.src, alt: (i.alt||'').slice(0,60),
                                    w: i.naturalWidth, h: i.naturalHeight,
                                    cls: i.className.slice(0,60)}));
                    return imgs;
                }"""
            )
            (OUT / "images.json").write_text(json.dumps(cards, indent=2), encoding="utf-8")
        except Exception as e:
            print("images.json capture failed:", str(e)[:80])

        # 3) Try clicking the first "show all colours" button to reveal variants.
        try:
            btn = page.get_by_text("ZOBRAZIT", exact=False).first
            btn.click(timeout=5000)
            time.sleep(4)
            (OUT / "model_expanded.html").write_text(page.content(), encoding="utf-8")
        except Exception as e:
            (OUT / "model_expanded.html").write_text(f"could not expand: {e}", encoding="utf-8")

        # 4) Save all network calls + any JSON bodies that look like data APIs
        (OUT / "network_calls.txt").write_text(
            "\n".join(f"{m}\t{s}\t{ct[:40]}\t{u}" for (m, u, s, ct) in calls),
            encoding="utf-8",
        )
        for n, (url, body) in enumerate(json_bodies[:20]):
            (OUT / f"api_{n}.json").write_text(
                json.dumps({"url": url, "body": body}, indent=2)[:200000],
                encoding="utf-8",
            )

        print(f"DONE. Wrote {len(calls)} network calls, {len(json_bodies)} JSON API bodies to {OUT}")
        ctx.close()


if __name__ == "__main__":
    main()
