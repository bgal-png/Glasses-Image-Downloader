# tests/test_barcode_parser.py
import io
import pandas as pd
from barcode_parser import clean_barcode, parse_barcodes
from barcode_parser import parse_records


def test_clean_strips_nbsp_and_whitespace():
    assert clean_barcode("197737241643\xa0") == "197737241643"
    assert clean_barcode("  8056262579640 ") == "8056262579640"


def test_clean_coerces_numeric_without_dot_zero():
    assert clean_barcode(197737257521) == "197737257521"
    assert clean_barcode(197737257521.0) == "197737257521"


def test_clean_returns_none_for_blank():
    assert clean_barcode("") is None
    assert clean_barcode("   ") is None
    assert clean_barcode(None) is None


def test_parse_pasted_text_one_per_line():
    text = "197737257521\n8056262579640\n\n  8056262600115  \n"
    assert parse_barcodes(text=text) == [
        "197737257521",
        "8056262579640",
        "8056262600115",
    ]


def test_parse_txt_file():
    data = "197737257521\n8056262579640\n".encode("utf-8")
    assert parse_barcodes(file_bytes=data, filename="list.txt") == [
        "197737257521",
        "8056262579640",
    ]


def test_parse_csv_uses_barcode_column_case_insensitive():
    df = pd.DataFrame({"Name": ["a", "b"], "BARCODE": [197737257521, "8056262579640\xa0"]})
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    result = parse_barcodes(file_bytes=buf.getvalue(), filename="x.csv")
    assert result == ["197737257521", "8056262579640"]


def test_records_from_xlsx_pairs_barcode_and_name():
    df = pd.DataFrame({
        "Glasses name": ["Hugo Boss BOSS 1949 FWM", "Miu Miu MU 01XV 08Q1O1"],
        "Barcode": ["197737257521\xa0", 8056262579640],
    })
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    recs = parse_records(file_bytes=buf.getvalue(), filename="x.xlsx")
    assert recs == [
        {"barcode": "197737257521", "name": "Hugo Boss BOSS 1949 FWM"},
        {"barcode": "8056262579640", "name": "Miu Miu MU 01XV 08Q1O1"},
    ]


def test_records_from_csv_without_name_column_leaves_name_empty():
    df = pd.DataFrame({"Barcode": ["197737257521", "8056262579640"]})
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    recs = parse_records(file_bytes=buf.getvalue(), filename="x.csv")
    assert recs == [
        {"barcode": "197737257521", "name": ""},
        {"barcode": "8056262579640", "name": ""},
    ]


def test_records_from_paste_barcode_only_and_barcode_comma_name():
    text = "197737257521\n8056262579640, Miu Miu MU 01XV\n\t\n"
    recs = parse_records(text=text)
    assert recs == [
        {"barcode": "197737257521", "name": ""},
        {"barcode": "8056262579640", "name": "Miu Miu MU 01XV"},
    ]


def test_records_from_paste_tab_separated():
    text = "197737257521\tHugo Boss BOSS 1949 FWM"
    recs = parse_records(text=text)
    assert recs == [{"barcode": "197737257521", "name": "Hugo Boss BOSS 1949 FWM"}]


def test_records_drops_rows_blank_in_both():
    df = pd.DataFrame({"Glasses name": ["", None], "Barcode": ["", None]})
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    assert parse_records(file_bytes=buf.getvalue(), filename="x.xlsx") == []


def test_parse_barcodes_still_works():
    assert parse_barcodes(text="197737257521\n8056262579640") == [
        "197737257521", "8056262579640",
    ]


def test_parse_xlsx_uses_barcode_column():
    df = pd.DataFrame({
        "Glasses name": [None, None],
        "Barcode": ["197737241643\xa0", 197737257521],
    })
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    result = parse_barcodes(file_bytes=buf.getvalue(), filename="260615.xlsx")
    assert result == ["197737241643", "197737257521"]


def test_parse_csv_falls_back_to_first_column_when_no_barcode_header():
    df = pd.DataFrame({"codes": ["197737257521", "8056262579640"]})
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    result = parse_barcodes(file_bytes=buf.getvalue(), filename="x.csv")
    assert result == ["197737257521", "8056262579640"]
