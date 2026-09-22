from safilo import normalize, match, image_url

INDEX = [
    {"modelText": "Hugo Boss BOSS 1949", "modelCode": "205918", "colorCode": "R80", "norm": "HUGOBOSSBOSS1949"},
    {"modelText": "Marc Jacobs MARC 496", "modelCode": "207993", "colorCode": "AOZ", "norm": "MARCJACOBSMARC496"},
]


def test_normalize():
    assert normalize("Marc Jacobs MARC 496/SHINY 807/IR") == "MARCJACOBSMARC496SHINY807IR"
    assert normalize(None) == ""


def test_image_url_builds_public_dam_url():
    url = image_url("207993", "807")
    assert url == ("https://safilo-pd-cdn002.safilo.com/damapi/damimage/public/"
                   "sfcc.getimagenofb?modelCode=207993&colorCode=807&detail=00&imagesize=medium")


def test_match_finds_model_and_color_from_name():
    m = match("Marc Jacobs MARC 496/SHINY 807/IR", INDEX)
    assert m["modelCode"] == "207993"
    assert m["colorCode"] == "807"  # color token from the name, not the index default


def test_match_uses_index_default_color_when_name_has_none():
    m = match("Hugo Boss BOSS 1949", INDEX)
    assert m["modelCode"] == "205918"
    assert m["colorCode"] == "R80"  # falls back to index default


def test_match_no_hit_returns_none():
    assert match("Oakley Holbrook", INDEX) is None


import os
import pytest

live = pytest.mark.skipif(os.environ.get("RUN_LIVE") != "1",
                          reason="set RUN_LIVE=1 (needs a live Safilo login)")


@live
def test_search_match_and_image_download():
    import safilo
    from fetcher import download_url_bytes
    name = "Marc Jacobs MARC 496"
    with safilo.open_context(headless=False) as ctx:
        assert safilo.is_logged_in(ctx) or safilo.login_in_context(ctx), "log in when the window opens"
        tiles = safilo.search_products(ctx, name)
        assert len(tiles) >= 1
        assert any(t["modelText"] for t in tiles), "tiles should carry model names"
        m = safilo.match(name, tiles)
        assert m is not None
        dl = download_url_bytes(safilo.image_url(m["modelCode"], m["colorCode"]))
        assert dl is not None and len(dl[0]) > 3000
