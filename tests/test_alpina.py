from alpina import search_query, match_model, match_color, _color_words, _hires

TILES = [
    {"title": "DEFEY", "url": "https://www.alpina-sports.com/de/de/eyewear/sportbrillen/defey/", "norm": "DEFEY"},
    {"title": "DEFEY HR", "url": "https://www.alpina-sports.com/de/de/eyewear/sportbrillen/defey-hr/", "norm": "DEFEYHR"},
]


def test_search_query_model_extraction():
    assert search_query("Alpina DEFEY 2 black matt") == "DEFEY 2"
    assert search_query("Alpina MITZO II Cars") == "MITZO II"
    assert search_query("Alpina RAM 2.0 black matt Q-LITE yello") == "RAM 2.0"
    assert search_query("Alpina TWIST 7 M sand matt Q-LITE purp") == "TWIST 7"
    assert search_query("Alpina TURBO PRO YOUTH white matt") == "TURBO PRO YOUTH"
    assert search_query("Alpina EYEWEAR STRAP STYLE black") == "EYEWEAR STRAP STYLE"


def test_match_model_substring_longest():
    m = match_model("Alpina DEFEY 2 black matt", TILES)
    assert m["norm"] == "DEFEY"        # DEFEYHR is not a substring of the name
    assert "defey/" in m["url"]


def test_match_model_none():
    assert match_model("Alpina TWIST 7 M sand matt", TILES) is None


def test_color_words_after_model():
    assert _color_words("Alpina DEFEY 2 black matt") == "BLACKMATT"
    assert _color_words("Alpina TURBO PRO YOUTH white matt") == "WHITEMATT"


def test_match_color_frame_color():
    variants = [
        {"colorText": "black matt / mirror blue", "image": "http://i/a"},
        {"colorText": "moon-grey matt / mirror bronce", "image": "http://i/b"},
    ]
    assert match_color(variants, "Alpina DEFEY 2 black matt")["image"] == "http://i/a"
    assert match_color(variants, "Alpina DEFEY 2 pink glow") is None


def test_hires_swaps_size():
    assert _hires("https://x/A1_Main_600x600.jpg") == "https://x/A1_Main_1200x1200.jpg"
    assert _hires("https://x/A1_Main_600x600@2x.jpg") == "https://x/A1_Main_1200x1200.jpg"


import os
import pytest

live = pytest.mark.skipif(os.environ.get("RUN_LIVE") != "1", reason="set RUN_LIVE=1 (public HTTP)")


@live
def test_search_returns_eyewear_tiles():
    import alpina
    tiles = alpina.search("Alpina DEFEY 2 black matt")
    assert len(tiles) >= 1
    assert all("/eyewear/" in t["url"] or "/skibrillen/" in t["url"] for t in tiles)


@live
def test_product_variants_and_resolve():
    import alpina
    tiles = alpina.search("Alpina DEFEY 2 black matt")
    m = alpina.match_model("Alpina DEFEY 2 black matt", tiles)
    assert m is not None
    variants = alpina.product_variants(m["url"])
    assert len(variants) >= 1
    assert all(v["image"].startswith("http") and "1200x1200" in v["image"] for v in variants)
    r = alpina.resolve("Alpina DEFEY 2 black matt")
    assert r["status"] in ("ok", "choose")
    if r["status"] == "ok":
        assert len(r["image"]) > 3000
    else:
        assert r["candidates"] and r["candidates"][0]["image_url"].startswith("http")
