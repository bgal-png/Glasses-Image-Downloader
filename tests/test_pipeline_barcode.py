from contextlib import contextmanager

import pipeline
from fetcher import FetchResult


@contextmanager
def _fake_browser():
    yield object()


def _run(monkeypatch, found_for, barcode):
    tried = []

    def fake_fetch(browser, code, delay=1.5):
        tried.append(code)
        if code in found_for:
            return FetchResult(code, "ok", image_bytes=b"x" * 2000,
                               extension=".jpg", message="ok")
        return FetchResult(code, "not_found", message="bad barcode page")

    monkeypatch.setattr(pipeline, "make_browser", _fake_browser)
    monkeypatch.setattr(pipeline, "fetch_image", fake_fetch)
    out = pipeline.run_barcode([{"barcode": barcode}], [0], delay=0)
    return out, tried


def test_retries_without_leading_zero_on_miss(monkeypatch):
    out, tried = _run(monkeypatch, {"888392486735"}, "0888392486735")
    assert tried == ["0888392486735", "888392486735"]
    assert 0 in out


def test_no_retry_when_found_as_is(monkeypatch):
    out, tried = _run(monkeypatch, {"0888392486735"}, "0888392486735")
    assert tried == ["0888392486735"]
    assert 0 in out


def test_no_retry_without_leading_zero(monkeypatch):
    out, tried = _run(monkeypatch, set(), "8056597585402")
    assert tried == ["8056597585402"]
    assert out == {}
