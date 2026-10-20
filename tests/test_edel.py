import hashlib

import pytest

import edel


# --- Pulling brand / model / colour out of a product name ---

def test_parts_splits_a_plain_name():
    assert edel.name_parts("Ray-Ban RB3793 001/31") == ("Ray-Ban", "RB3793", "001-31")


def test_parts_keeps_a_multi_word_brand():
    assert edel.name_parts("Emporio Armani EA3285U 5017") == (
        "Emporio-Armani", "EA3285U", "5017")


def test_parts_drops_the_catalogue_leading_zero():
    """Luxottica writes 0RB3793; edel writes RB3793."""
    assert edel.name_parts("Ray-Ban 0RB3793 001/31")[1] == "RB3793"


def test_parts_returns_none_without_a_model_code():
    assert edel.name_parts("Some Brand Sunglasses") is None
    assert edel.name_parts("") is None


# --- Building the image URL ---

def test_image_url_is_the_2000px_nobg_jpg():
    assert edel.image_url("Ray-Ban", "RB3793", "001-31") == (
        "https://img.edel-optics.com/eoProductsGlassesSunglasses/2000/nobg/"
        "Ray-Ban-RB3793-001-31.jpg")


def test_url_for_name_round_trips():
    assert edel.url_for_name("Ray-Ban RB3793 002/71").endswith(
        "Ray-Ban-RB3793-002-71.jpg")


def test_url_for_name_is_none_when_unparsable():
    assert edel.url_for_name("No code here") is None


# --- Telling a real photo from the "not stocked" placeholder ---

def test_placeholder_bytes_are_rejected():
    """Every missing product returns one identical 12 kB image, not a 404."""
    fake = b"\xff\xd8" + b"x" * 12000
    assert edel.is_placeholder(fake, {hashlib.md5(fake).hexdigest()})


def test_a_real_photo_is_accepted():
    photo = b"\xff\xd8" + b"y" * 40000
    assert not edel.is_placeholder(photo, {"deadbeef"})


def test_tiny_or_empty_responses_count_as_missing():
    assert edel.is_placeholder(b"", set())
    assert edel.is_placeholder(b"\xff\xd8" + b"z" * 100, set())


@pytest.mark.live
def test_live_fetch_of_a_known_frame():
    got = edel.resolve("Ray-Ban RB3793 001/31")
    assert got is not None
    data, ext = got
    assert ext == ".jpg" and len(data) > 20000 and data[:2] == b"\xff\xd8"


@pytest.mark.live
def test_live_miss_returns_none():
    assert edel.resolve("Dolce & Gabbana DG3430 3148") is None


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
