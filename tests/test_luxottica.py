from luxottica import normalize, model_key, match_model, match_color

INDEX = [
    {"partNumber": "0MU 01YV", "brand": "MU", "image": "http://img/mu01yv", "norm": "MU01YV"},
    {"partNumber": "0PO0649", "brand": "PO", "image": "http://img/po0649", "norm": "PO0649"},
    {"partNumber": "0OO9431", "brand": "OO", "image": "http://img/oo9431", "norm": "OO9431"},
]


def test_normalize_strips_and_uppercases():
    assert normalize("0MU 01YV") == "0MU01YV"
    assert normalize("12w1o1 ") == "12W1O1"
    assert normalize(None) == ""


def test_model_key_drops_single_leading_zero():
    assert model_key("0MU 01YV") == "MU01YV"
    assert model_key("0PO0649") == "PO0649"


def test_match_model_finds_miu_miu_and_color_guess():
    m = match_model("Miu Miu MU 01YV 12W1O1", INDEX)
    assert m is not None
    assert m["partNumber"] == "0MU 01YV"
    assert m["colorGuess"] == "12W1O1"


def test_match_model_persol():
    m = match_model("Persol PO0649 95/31", INDEX)
    assert m["partNumber"] == "0PO0649"


def test_match_model_longest_wins():
    idx = INDEX + [{"partNumber": "0MU 01", "brand": "MU", "image": "x", "norm": "MU01"}]
    m = match_model("Miu Miu MU 01YV 12W1O1", idx)
    assert m["partNumber"] == "0MU 01YV"  # MU01YV beats MU01


def test_match_model_no_match_returns_none():
    assert match_model("Hugo Boss BOSS 1949 FWM", INDEX) is None


def test_match_color_exact_and_miss():
    variants = [
        {"colorCode": "12W1O1", "partNumber": "0MU 01YV_12W1O1", "image": "http://i/a"},
        {"colorCode": "14L1O1", "partNumber": "0MU 01YV_14L1O1", "image": "http://i/b"},
    ]
    assert match_color(variants, "12W1O1")["image"] == "http://i/a"
    assert match_color(variants, "99Z9Z9") is None


import os
import pytest

live = pytest.mark.skipif(os.environ.get("RUN_LIVE") != "1",
                          reason="set RUN_LIVE=1 (needs the saved EL session)")


@live
def test_logged_in_and_index_and_variants():
    import luxottica
    with luxottica.open_context(headless=True) as ctx:
        assert luxottica.is_logged_in(ctx), "EL session not logged in — run luxottica.login() first"
        index = luxottica.build_catalog_index(ctx)
        assert len(index) > 1000
        assert all("norm" in m and m["image"] for m in index[:5])
        variants = luxottica.get_variants(ctx, "0MU 01YV")
        codes = [v["colorCode"] for v in variants]
        assert "12W1O1" in codes
        assert all(v["image"].startswith("http") for v in variants)
