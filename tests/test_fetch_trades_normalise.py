"""
Tests for `fetch_trades._normalise_trade`.

This is the seam where one raw RSC-parsed trade dict (the shape the
capitoltrades scraper extracts from the page chunks, *not* the BFF JSON
fixture in `tests/fixtures/`) is mapped onto the project's clean trade
schema. Two behaviors here are worth pinning:

  1. `pubDate[:10]` truncation — capitoltrades returns an ISO timestamp;
     downstream pipeline assumes a YYYY-MM-DD string.
  2. Missing-field tolerance — `issuer` is nested and may be absent on
     malformed rows, and `txType` is uppercased so callers can compare
     to "BUY"/"SELL" without re-normalizing.

These are the only non-trivial transformations in the function. The rest
is dict pass-through and is exercised end-to-end by the recorded fixture
in `test_fetch_trades_parse.py` (planned for pytest 5/6).
"""

from __future__ import annotations

from fetch_trades import _normalise_trade


def _full_raw() -> dict:
    """Reference 'happy-path' raw RSC trade. Each test mutates a copy."""
    return {
        "_txId": 20003795787,
        "issuer": {
            "issuerName": "JPMorgan Chase & Co",
            "issuerTicker": "JPM:US",
            "sector": "financials",
        },
        "txDate": "2026-02-19",
        "pubDate": "2026-03-12T14:30:00Z",
        "reportingGap": 18,
        "txType": "buy",
        "txTypeExtended": None,
        "value": 175000,
        "price": None,
        "owner": "child",
        "comment": None,
    }


def test_happy_path_full_record():
    out = _normalise_trade(_full_raw())
    assert out == {
        "txId": 20003795787,
        "company": "JPMorgan Chase & Co",
        "ticker": "JPM:US",
        "sector": "financials",
        "txDate": "2026-02-19",
        "published": "2026-03-12",
        "filedAfterDays": 18,
        "type": "BUY",
        "typeExtended": None,
        "value": 175000,
        "price": None,
        "owner": "child",
        "comment": None,
    }


def test_pub_date_truncates_to_ten_chars():
    raw = _full_raw()
    raw["pubDate"] = "2026-03-12T14:30:00Z"
    assert _normalise_trade(raw)["published"] == "2026-03-12"


def test_pub_date_missing_yields_empty_string():
    raw = _full_raw()
    del raw["pubDate"]
    # `.get("pubDate", "")[:10]` → "" — downstream date parsers must
    # tolerate empty strings on records the scraper couldn't fully attribute.
    assert _normalise_trade(raw)["published"] == ""


def test_missing_issuer_block_yields_none_fields():
    raw = _full_raw()
    del raw["issuer"]
    out = _normalise_trade(raw)
    assert out["company"] is None
    assert out["ticker"] is None
    assert out["sector"] is None


def test_tx_type_uppercased():
    raw = _full_raw()
    raw["txType"] = "sell"
    assert _normalise_trade(raw)["type"] == "SELL"


def test_tx_type_missing_yields_empty_string():
    # `(raw.get("txType") or "").upper()` defends against both missing
    # and explicit-None values; locking the empty-string contract here
    # so a future edit doesn't accidentally start emitting None.
    raw = _full_raw()
    raw["txType"] = None
    assert _normalise_trade(raw)["type"] == ""
