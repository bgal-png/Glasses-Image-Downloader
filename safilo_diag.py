# safilo_diag.py — fully-instrumented live run of the exact matching flow, so we
# can SEE where Safilo breaks. Login once; it logs every step for real names.
import functools
import pathlib
import time

import safilo
from fetcher import download_url_bytes

print = functools.partial(print, flush=True)  # noqa: A001

NAMES = [
    "Hugo Boss BOSS 1949 FWM",
    "Marc Jacobs MARC 496/SHINY 807/IR",
]


def main():
    out = pathlib.Path("safilo_diag_out")
    out.mkdir(exist_ok=True)
    with safilo.open_context(headless=False) as ctx:
        page = safilo._page(ctx)
        try:
            page.goto(safilo._category_url(safilo.FRAMES_CATEGORY),
                      wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass
        print(">>> Log into youandsafilo.com in the Edge window…")
        if not safilo.login_in_context(ctx):
            print("!! login not detected within timeout")
            return
        print(">>> Logged in. url now:", page.url[:70])

        for name in NAMES:
            print("\n=========================================")
            print("NAME:", name)
            q = safilo._search_query(name)
            print("  search query:", repr(q))
            tiles = safilo.search_products(ctx, name)
            print("  tiles found:", len(tiles))
            for t in tiles[:6]:
                print("     -", repr(t["modelText"]), "model=", t["modelCode"], "color=", t["colorCode"])
            print("  page url after search:", page.url[:70])
            if not tiles:
                # dump so we can see the results page state
                try:
                    page.screenshot(path=str(out / (q.replace(" ", "_") + ".png")), full_page=True)
                    (out / (q.replace(" ", "_") + ".html")).write_text(page.content(), encoding="utf-8")
                    print("  (saved screenshot + html for", q, ")")
                except Exception as e:
                    print("  dump failed:", str(e)[:60])
                continue
            m = safilo.match(name, tiles)
            print("  match:", m)
            if not m:
                print("  -> no model matched among tiles")
                continue
            model = m["modelCode"]
            colors = []
            for t in tiles:
                if t["modelCode"] == model and t["colorCode"] and t["colorCode"] not in colors:
                    colors.append(t["colorCode"])
            print("  candidate colors for model", model, ":", colors)
            saved = False
            for c in colors:
                url = safilo.image_url(model, c)
                dl = download_url_bytes(url)
                status = (str(len(dl[0])) + " bytes") if dl else "FAIL"
                print("     color", c, "->", status)
                if dl and len(dl[0]) > 2000:
                    (out / f"{model}_{c}{dl[1]}").write_bytes(dl[0])
                    saved = True
                    break
            print("  RESULT:", "image saved" if saved else "no image")


if __name__ == "__main__":
    main()
