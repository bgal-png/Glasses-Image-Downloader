# safilo_build.py — open a visible Edge, wait for login, build + cache the Safilo
# catalogue index. Prints flush live so progress is visible. Run with RUN_LIVE=1.
import functools
import time

import safilo
from fetcher import download_url_bytes

print = functools.partial(print, flush=True)  # noqa: A001 - live output


def main():
    with safilo.open_context(headless=False) as ctx:
        page = safilo._page(ctx)
        # Land on the frames category (redirects to login if needed).
        try:
            page.goto(safilo._category_url(safilo.CATEGORIES["frames"]),
                      wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print("goto note:", str(e)[:100])

        print(">>> Log into youandsafilo.com in the Edge window, then wait…")
        logged = False
        for _ in range(120):  # up to 10 min
            time.sleep(5)
            try:
                url = page.url
                tiles = page.evaluate(
                    "() => Array.from(document.images).filter(i => i.src.includes('getimagenofb')).length")
            except Exception as e:
                print("  (page busy:", str(e)[:40], ")")
                continue
            on_login = "/login" in url
            print(f"  url_login={on_login} tiles={tiles} url={url[:60]}")
            # Logged in once we're off the login page and on youandsafilo.
            if not on_login and "youandsafilo.com" in url:
                logged = True
                break
        if not logged:
            print("Login not detected — stopping.")
            return

        print(">>> Logged in. Building catalogue index (scrolling both categories)…")

        def prog(n):
            print(f"  indexed {n} models…")

        # Throttle progress prints: wrap to only print every ~25 models.
        last = [0]

        def prog2(n):
            if n - last[0] >= 25:
                last[0] = n
                print(f"  indexed {n} models…")

        idx = safilo.build_index(ctx, progress=prog2)
        print("MODELS INDEXED:", len(idx))
        for e in idx[:8]:
            print("  text=[", e["modelText"][:45], "] model=", e["modelCode"], "color=", e["colorCode"])
        empty = sum(1 for e in idx if not e["modelText"])
        print("entries with EMPTY modelText:", empty, "/", len(idx))
        if idx:
            safilo.save_index(idx)
            print("saved index to safilo_catalog_index.json")
            dl = download_url_bytes(safilo.image_url(idx[0]["modelCode"], idx[0]["colorCode"]))
            print("sample image download bytes:", len(dl[0]) if dl else "FAILED")


if __name__ == "__main__":
    main()
