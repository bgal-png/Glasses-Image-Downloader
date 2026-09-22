# barcode_parser.py
import io
import pandas as pd


def clean_barcode(value):
    """Normalize one barcode cell/line to a digit string, or None if blank."""
    if value is None:
        return None
    # Numeric cells (int or float) -> integer string, no trailing .0
    if isinstance(value, float):
        if pd.isna(value):
            return None
        value = int(value)
    if isinstance(value, int):
        return str(value)
    # Strings: strip whitespace including non-breaking space
    text = str(value).replace("\xa0", " ").strip()
    if not text:
        return None
    return text


def _barcode_column(df):
    """Return the Barcode column (case-insensitive) or the first column."""
    for col in df.columns:
        if str(col).strip().lower() == "barcode":
            return col
    return df.columns[0]


def _name_column(df):
    """Return the name column, or None if there isn't one."""
    for col in df.columns:
        if str(col).strip().lower() == "glasses name":
            return col
    for col in df.columns:
        if str(col).strip().lower() == "name":
            return col
    return None


def _clean_name(value):
    """Trim a name cell to a string ('' for blank/NaN/None)."""
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).replace("\xa0", " ").strip()


def _from_dataframe(df):
    """Pick the Barcode column (case-insensitive) or fall back to first column."""
    target = _barcode_column(df)
    cleaned = [clean_barcode(v) for v in df[target].tolist()]
    return [b for b in cleaned if b]


def _read_dataframe(file_bytes, name):
    if name.endswith(".csv"):
        return pd.read_csv(io.BytesIO(file_bytes), dtype=object)
    return pd.read_excel(io.BytesIO(file_bytes), dtype=object)


def _record_from_line(line):
    """Parse one pasted line into a record dict, or None if blank."""
    raw = line.replace("\xa0", " ").strip()
    if not raw:
        return None
    if "\t" in raw:
        parts = raw.split("\t", 1)
    elif "," in raw:
        parts = raw.split(",", 1)
    else:
        parts = [raw]
    barcode = clean_barcode(parts[0]) or ""
    name = parts[1].strip() if len(parts) > 1 else ""
    if not barcode and not name:
        return None
    return {"barcode": barcode, "name": name}


def parse_records(text=None, file_bytes=None, filename=None):
    """Return ordered [{'barcode': str, 'name': str}] from paste or a file."""
    if text is not None:
        records = [_record_from_line(line) for line in text.splitlines()]
        return [r for r in records if r]

    if file_bytes is not None:
        name = (filename or "").lower()
        if name.endswith((".xlsx", ".xls", ".csv")):
            df = _read_dataframe(file_bytes, name)
            bcol = _barcode_column(df)
            ncol = _name_column(df)
            records = []
            for _, row in df.iterrows():
                barcode = clean_barcode(row[bcol]) or "" if bcol is not None else ""
                frame_name = _clean_name(row[ncol]) if ncol is not None else ""
                if barcode or frame_name:
                    records.append({"barcode": barcode, "name": frame_name})
            return records
        decoded = file_bytes.decode("utf-8", errors="replace")
        return parse_records(text=decoded)

    return []


def parse_barcodes(text=None, file_bytes=None, filename=None):
    """Return an ordered list of cleaned barcodes from pasted text or a file."""
    if text is not None:
        cleaned = [clean_barcode(line) for line in text.splitlines()]
        return [b for b in cleaned if b]

    if file_bytes is not None:
        name = (filename or "").lower()
        if name.endswith(".xlsx") or name.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(file_bytes), dtype=object)
            return _from_dataframe(df)
        if name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_bytes), dtype=object)
            return _from_dataframe(df)
        # Treat anything else (.txt or unknown) as one-per-line text
        decoded = file_bytes.decode("utf-8", errors="replace")
        cleaned = [clean_barcode(line) for line in decoded.splitlines()]
        return [b for b in cleaned if b]

    return []
