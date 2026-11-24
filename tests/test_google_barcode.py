from fetcher import google_barcode_query, google_barcode_url


def test_strips_one_leading_zero():
    assert google_barcode_query("0888392486735") == "888392486735"


def test_keeps_barcode_without_leading_zero():
    assert google_barcode_query("8056597585402") == "8056597585402"


def test_strips_only_the_first_zero_and_whitespace():
    assert google_barcode_query(" 00123 ") == "0123"


def test_url_is_a_google_web_search():
    assert google_barcode_url("0888392486735") == \
        "https://www.google.com/search?q=888392486735"
