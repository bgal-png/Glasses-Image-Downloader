import hashlib

import pytest

import edel


@pytest.fixture(autouse=True)
def _clean_state():
    """resolve() learns placeholders and a preferred path; keep tests isolated."""
    edel.reset()
    yield
    edel.reset()


# --- Turning a product name into the shop's file name ---

def test_slug_hyphenates_spaces_and_slashes():
    assert edel.name_slug("Ray-Ban RB3793 001/31") == "Ray-Ban-RB3793-001-31"


def test_slug_handles_a_model_code_containing_slashes():
    """Polaroid writes the code itself with slashes — the old parser gave up here."""
    assert edel.name_slug("Polaroid PLD 4199/S/X 8CQ/XW") == (
        "Polaroid-PLD-4199-S-X-8CQ-XW")


def test_slug_spells_out_an_ampersand_brand():
    assert edel.name_slug("Dolce & Gabbana DG3430 3148") == (
        "Dolce-and-Gabbana-DG3430-3148")


def test_slug_keeps_a_multi_word_brand():
    assert edel.name_slug("Emporio Armani EA3285U 5017") == (
        "Emporio-Armani-EA3285U-5017")


def test_slug_collapses_repeated_separators_and_trims():
    assert edel.name_slug("  Oakley  OX8207 //820701  ") == "Oakley-OX8207-820701"


def test_slug_is_empty_for_an_empty_name():
    assert edel.name_slug("") == ""
    assert edel.name_slug(None) == ""


# --- Building the URL ---

def test_candidate_urls_cover_both_product_paths():
    """Optical frames live under .../Prescription/, sunglasses under .../Sunglasses/."""
    urls = edel.candidate_urls("Ray-Ban RB3793 001/31")
    assert any("eoProductsGlassesSunglasses" in u for u in urls)
    assert any("eoProductsGlassesPrescription" in u for u in urls)


def test_candidate_url_is_the_2000px_nobg_jpg():
    assert edel.candidate_urls("Ray-Ban RB3793 001/31")[0] == (
        "https://img.edel-optics.com/eoProductsGlassesSunglasses/2000/nobg/"
        "Ray-Ban-RB3793-001-31.jpg")


def test_candidate_urls_are_empty_for_an_empty_name():
    assert edel.candidate_urls("   ") == []


# --- Telling a real photo from the "not stocked" placeholder ---

def test_placeholder_bytes_are_rejected():
    fake = b"\xff\xd8" + b"x" * 12000
    assert edel.is_placeholder(fake, {hashlib.md5(fake).hexdigest()})


def test_a_real_photo_is_accepted():
    assert not edel.is_placeholder(b"\xff\xd8" + b"y" * 40000, {"deadbeef"})


def test_tiny_or_empty_responses_count_as_missing():
    assert edel.is_placeholder(b"", set())
    assert edel.is_placeholder(b"\xff\xd8" + b"z" * 100, set())


def test_resolve_tries_the_second_path_when_the_first_is_a_placeholder():
    placeholder = b"\xff\xd8" + b"p" * 8000
    photo = b"\xff\xd8" + b"q" * 40000
    seen = []

    def fake(url):
        seen.append(url)
        return photo if "Prescription" in url else placeholder

    data, ext = edel.resolve("Dolce & Gabbana DG3430 3148", fetch=fake)
    assert data == photo and ext == ".jpg"
    assert any("Sunglasses" in u for u in seen), "should have tried sunglasses first"


def test_resolve_gives_up_when_every_candidate_is_a_placeholder():
    assert edel.resolve("Ray-Ban RB9999 123",
                        fetch=lambda u: b"\xff\xd8" + b"p" * 8000) is None


# --- The CDN serves WebP from a .jpg path and mislabels it image/jpeg ---

def test_webp_bytes_are_recognised():
    assert edel.is_webp(b"RIFF\x80\xa2\x00\x00WEBP" + b"x" * 50)
    assert not edel.is_webp(b"\xff\xd8\xff\xe0" + b"x" * 50)


def test_to_jpeg_leaves_a_jpeg_alone():
    jpeg = b"\xff\xd8\xff\xe0" + b"x" * 50
    assert edel.to_jpeg(jpeg) is jpeg


def test_to_jpeg_converts_a_real_webp():
    pytest.importorskip("PIL")
    import io

    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), (10, 120, 200)).save(buffer, format="WEBP")
    out = edel.to_jpeg(buffer.getvalue())
    assert out[:2] == b"\xff\xd8"
    assert Image.open(io.BytesIO(out)).size == (40, 30)


def test_to_jpeg_keeps_unreadable_bytes_rather_than_losing_them():
    broken = b"RIFF\x00\x00\x00\x00WEBPnot-actually-an-image"
    assert edel.to_jpeg(broken) == broken


@pytest.mark.live
def test_live_fetch_of_a_sunglass():
    got = edel.resolve("Ray-Ban RB3793 001/31")
    assert got is not None
    data, ext = got
    assert ext == ".jpg" and len(data) > 20000 and data[:2] == b"\xff\xd8"


@pytest.mark.live
def test_live_fetch_of_an_optical_frame_on_the_other_path():
    """Optical frames sit under .../Prescription/ and the brand spells out "&"."""
    got = edel.resolve("Dolce & Gabbana DG3430 3148")
    assert got is not None and got[0][:2] == b"\xff\xd8"


@pytest.mark.live
def test_live_fetch_of_a_slashed_model_code():
    got = edel.resolve("Polaroid PLD 4199/S/X 8CQ/XW")
    assert got is not None and got[0][:2] == b"\xff\xd8"
