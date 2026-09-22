# safilo_verify.py — log in once, then search the real Safilo names from the
# user's file, match, and download the official image. Confirms the whole
# search-per-name pipeline end to end. RUN_LIVE=1.
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
    out = pathlib.Path("safilo_verify_out")
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
            print("login not detected; stopping.")
            return
        print(">>> Logged in. Searching names…")
        for ni, name in enumerate(NAMES):
            tiles = safilo.search_products(ctx, name)
            if not tiles:
                # Diagnostic dump so this can be fixed offline without more logins.
                try:
                    pg = safilo._page(ctx)
                    (out / f"diag_{ni}_url.txt").write_text(pg.url, encoding="utf-8")
                    (out / f"diag_{ni}.html").write_text(pg.content(), encoding="utf-8")
                    pg.screenshot(path=str(out / f"diag_{ni}.png"), full_page=True)
                    counts = pg.evaluate(
                        """() => ({
                            productLinks: document.querySelectorAll('a[href*="/cs/product/"]').length,
                            damImages: Array.from(document.images).filter(i=>i.src.includes('getimagenofb')).length,
                            nameEls: document.querySelectorAll('.plp--product__name, .field-item').length,
                            searchCards: document.querySelectorAll('c-lex-search-card, .plp--product__item').length,
                            bodyLen: document.body.innerText.length,
                        })""")
                    print("  DIAGNOSTIC counts:", counts)
                except Exception as e:
                    print("  diag failed:", str(e)[:80])
            m = safilo.match(name, tiles)
            print(f"\nNAME: {name}")
            sample = ", ".join("%s(%s/%s)" % (t["modelText"], t["modelCode"], t["colorCode"])
                                for t in tiles[:3])
            print("  tiles: %d | sample: %s" % (len(tiles), sample))
            if not m:
                print("  MATCH: none")
                continue
            url = safilo.image_url(m["modelCode"], m["colorCode"])
            dl = download_url_bytes(url)
            print(f"  MATCH: model={m['modelCode']} color={m['colorCode']} ({m['modelText']})")
            print(f"  IMAGE: {'OK ' + str(len(dl[0])) + ' bytes' if dl else 'FAILED'} | {url}")
            if dl:
                (out / f"{m['modelCode']}_{m['colorCode']}{dl[1]}").write_bytes(dl[0])


if __name__ == "__main__":
    main()
