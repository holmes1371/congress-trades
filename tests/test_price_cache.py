"""
Tests for `scoring.price_cache.get_prices`.

Strategy per the design note: mock the yfinance seam
(`price_cache._bulk_download`), keep the cache-read/write/merge logic
real. Each test uses a per-test `tmp_path` as `CACHE_DIR` via
monkeypatch, so no test ever writes into the committed
`scoring/cache/prices/` directory.

The four behaviors covered:

  1. Full cache hit — no `_bulk_download` call.
  2. Cache miss — empty cache, `_bulk_download` returns data, cache
     is populated, result contains the fetched rows.
  3. Partial coverage — cache exists but the requested window extends
     past the cached end; should trigger a refetch.
  4. Corrupt cache file — `_load_cached` swallows the read error and
     treats the cache as empty, so the request still succeeds.

The design note's "concurrent access" case is deliberately dropped
— `_save_cache` writes non-atomically and there's no locking in the
module, so there is nothing meaningful to assert without first adding
the locking. Surfaced in `design/pytest-ci-suite.md`'s Test plan
table; revisit if #5/#6 introduce real concurrency.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from scoring import price_cache


def _make_prices_df(ticker_dates: list[tuple[date, float]]) -> pd.DataFrame:
    """Build a price_cache-shaped DataFrame from (date, close) tuples."""
    df = pd.DataFrame(
        [{"close": c, "volume": 1_000_000} for _, c in ticker_dates],
        index=pd.to_datetime([d for d, _ in ticker_dates]),
    )
    df.index.name = "date"
    return df


def test_full_cache_hit_skips_bulk_download(monkeypatch, tmp_path):
    """Cache fully covers [start, end] → no fetch."""
    monkeypatch.setattr(price_cache, "CACHE_DIR", tmp_path)

    # Pre-populate cache: AAPL spanning a year that fully covers the
    # query window below.
    cached = _make_prices_df([
        (date(2025, 1, 3), 180.0),
        (date(2025, 6, 2), 200.0),
        (date(2025, 12, 31), 220.0),
    ])
    price_cache._save_cache("AAPL", cached)

    def _explode(*a, **k):
        pytest.fail("_bulk_download should not have been called on full cache hit")

    monkeypatch.setattr(price_cache, "_bulk_download", _explode)

    # Also clamp "today" so _needs_fetch doesn't see the cache as stale
    # against a real wall-clock end-date.
    class _FrozenDate(date):
        @classmethod
        def today(cls):
            return date(2026, 1, 15)
    monkeypatch.setattr(price_cache, "date", _FrozenDate)

    result = price_cache.get_prices(
        ["AAPL"], start=date(2025, 6, 1), end=date(2025, 6, 30)
    )
    assert "AAPL" in result
    assert not result["AAPL"].empty


def test_cache_miss_calls_bulk_download_and_populates(monkeypatch, tmp_path):
    """Empty cache → one fetch, returned rows end up in cache."""
    monkeypatch.setattr(price_cache, "CACHE_DIR", tmp_path)

    fetched = _make_prices_df([
        (date(2025, 6, 2), 200.0),
        (date(2025, 6, 3), 201.0),
        (date(2025, 6, 4), 202.0),
    ])
    calls = []

    def _fake_bulk(tickers, start, end):
        calls.append((tuple(tickers), start, end))
        return {"AAPL": fetched}

    monkeypatch.setattr(price_cache, "_bulk_download", _fake_bulk)

    result = price_cache.get_prices(
        ["AAPL"], start=date(2025, 6, 1), end=date(2025, 6, 10)
    )
    assert len(calls) == 1
    assert "AAPL" in result
    # Cache file was written with the fetched rows.
    reloaded = price_cache._load_cached("AAPL")
    assert len(reloaded) == 3


def test_partial_coverage_triggers_refetch(monkeypatch, tmp_path):
    """Cache exists but end is too early → refetch fills the gap."""
    monkeypatch.setattr(price_cache, "CACHE_DIR", tmp_path)

    cached = _make_prices_df([
        (date(2025, 6, 2), 200.0),
        (date(2025, 6, 3), 201.0),
    ])
    price_cache._save_cache("AAPL", cached)

    fresh = _make_prices_df([
        (date(2025, 6, 4), 202.0),
        (date(2025, 6, 5), 203.0),
    ])
    calls = []

    def _fake_bulk(tickers, start, end):
        calls.append((tuple(tickers), start, end))
        return {"AAPL": fresh}

    monkeypatch.setattr(price_cache, "_bulk_download", _fake_bulk)

    class _FrozenDate(date):
        @classmethod
        def today(cls):
            return date(2025, 6, 10)
    monkeypatch.setattr(price_cache, "date", _FrozenDate)

    result = price_cache.get_prices(
        ["AAPL"], start=date(2025, 6, 1), end=date(2025, 6, 5)
    )
    assert len(calls) == 1, "refetch should have been triggered"
    # Merged cache now covers both the original and fresh rows.
    reloaded = price_cache._load_cached("AAPL")
    assert len(reloaded) == 4
    # Returned frame is sliced to [start, end] only.
    assert "AAPL" in result
    assert len(result["AAPL"]) == 4  # 6/2, 6/3, 6/4, 6/5 all inside window


# ── _bulk_download empty-column regression (ROADMAP #10) ──

class _FakeYF:
    """Minimal yfinance stand-in. Each instance returns a fixed frame
    from download(); the monkeypatch swap lets us exercise
    _bulk_download's post-fetch handling without a network call."""

    def __init__(self, frame: pd.DataFrame):
        self._frame = frame

    def download(self, **kwargs) -> pd.DataFrame:
        return self._frame


def test_bulk_download_single_ticker_missing_close_returns_empty(monkeypatch):
    """yfinance returns a non-empty frame without a Close column
    (rate-limit fallback, delisted / unknown ticker). Pre-fix this
    crashed `pd.DataFrame({"close": pd.NA, "volume": pd.NA})` with
    'If using all scalar values, you must pass an index'. The guard
    drops the ticker instead."""
    # Shape yfinance sometimes returns: a frame that has rows (so
    # raw.empty is False) but no Close column.
    idx = pd.to_datetime(["2025-06-02", "2025-06-03"])
    bad = pd.DataFrame({"Adj Close": [100.0, 101.0]}, index=idx)
    monkeypatch.setattr(price_cache, "yf", _FakeYF(bad))

    out = price_cache._bulk_download(["MISSING"], date(2025, 6, 1), date(2025, 6, 10))
    assert out == {}


def test_bulk_download_single_ticker_missing_volume_still_builds_frame(monkeypatch):
    """Close present, Volume absent — keep the ticker with NaN volume
    rather than crashing. Mirrors the existing dropna(subset=['close'])
    contract downstream."""
    idx = pd.to_datetime(["2025-06-02", "2025-06-03"])
    good = pd.DataFrame({"Close": [200.0, 201.0]}, index=idx)
    monkeypatch.setattr(price_cache, "yf", _FakeYF(good))

    out = price_cache._bulk_download(["NOVOL"], date(2025, 6, 1), date(2025, 6, 10))
    assert "NOVOL" in out
    assert len(out["NOVOL"]) == 2
    assert out["NOVOL"]["close"].tolist() == [200.0, 201.0]
    assert out["NOVOL"]["volume"].isna().all()


def test_bulk_download_multi_ticker_skips_tickers_without_close(monkeypatch):
    """In a multi-ticker response, one ticker's sub-frame can lack a
    Close column while another's has full data. Skip the bad one,
    keep the good one — same guard as the single-ticker branch."""
    idx = pd.to_datetime(["2025-06-02", "2025-06-03"])
    aapl_cols = pd.DataFrame({"Close": [200.0, 201.0], "Volume": [1_000_000, 1_100_000]}, index=idx)
    # BADTKR has Adj Close only — no usable Close for our schema.
    bad_cols = pd.DataFrame({"Adj Close": [50.0, 51.0]}, index=idx)
    raw = pd.concat({"AAPL": aapl_cols, "BADTKR": bad_cols}, axis=1)
    monkeypatch.setattr(price_cache, "yf", _FakeYF(raw))

    out = price_cache._bulk_download(["AAPL", "BADTKR"], date(2025, 6, 1), date(2025, 6, 10))
    assert "AAPL" in out
    assert "BADTKR" not in out
    assert len(out["AAPL"]) == 2


def test_corrupt_cache_file_is_swallowed(monkeypatch, tmp_path):
    """Garbage CSV → _load_cached returns empty, refetch proceeds."""
    monkeypatch.setattr(price_cache, "CACHE_DIR", tmp_path)

    # Write a deliberately malformed cache file.
    (tmp_path / "AAPL.csv").write_text("this is not,,a valid,,csv\n\0\0\0")

    fetched = _make_prices_df([
        (date(2025, 6, 2), 200.0),
        (date(2025, 6, 3), 201.0),
    ])
    calls = []

    def _fake_bulk(tickers, start, end):
        calls.append(tuple(tickers))
        return {"AAPL": fetched}

    monkeypatch.setattr(price_cache, "_bulk_download", _fake_bulk)

    result = price_cache.get_prices(
        ["AAPL"], start=date(2025, 6, 1), end=date(2025, 6, 10)
    )
    # Refetch happened and result is populated — corrupt cache did not
    # cause a hard failure.
    assert len(calls) == 1
    assert "AAPL" in result
