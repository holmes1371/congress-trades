"""
Tests for `scoring.benchmarks` — cumulative total return for the four
reference benchmarks (NANC, KRUZ, SPY, QQQ).

The primitive is deliberately thin: it slices the first and last close
out of a `price_cache`-shaped DataFrame and returns `last/first - 1`.
Window-boundary behavior (weekend starts, partial coverage, network
failure) is owned by `scoring.price_cache` and covered in
`test_price_cache.py`; these tests cover the primitive's own contract
(pure function of a price frame) plus the `get_prices` seam.

NANC/KRUZ/QQQ fixtures under `tests/fixtures/prices/` are synthetic —
geometric growth matching SPY's date range, designed total returns of
+20%, -5%, +15% respectively. Synthesizing (rather than recording) was
chosen in session 2 so the sandbox's yfinance-allowlist risk does not
gate the commit; the primitive math does not care whether the closes
are real or synthetic.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from scoring import benchmarks


def _make_prices_df(rows: list[tuple[date, float]]) -> pd.DataFrame:
    df = pd.DataFrame(
        [{"close": c, "volume": 1_000_000} for _, c in rows],
        index=pd.to_datetime([d for d, _ in rows]),
    )
    df.index.name = "date"
    return df


# ── Pure-function contract (price_frame= injection, no get_prices call) ──


@pytest.mark.parametrize(
    "first, last, expected",
    [
        (100.0, 120.0, 0.20),
        (100.0, 95.0, -0.05),
        (450.0, 517.5, 0.15),
        (100.0, 100.0, 0.0),  # flat window
    ],
)
def test_return_math_exact(first, last, expected):
    df = _make_prices_df([(date(2025, 1, 2), first), (date(2025, 12, 31), last)])
    result = benchmarks.benchmark_cumulative_return(
        "ANY", date(2025, 1, 1), date(2025, 12, 31), price_frame=df
    )
    assert result == pytest.approx(expected)


def test_single_row_frame_returns_zero():
    df = _make_prices_df([(date(2025, 6, 2), 200.0)])
    result = benchmarks.benchmark_cumulative_return(
        "ANY", date(2025, 6, 1), date(2025, 6, 30), price_frame=df
    )
    assert result == 0.0


def test_empty_frame_returns_none():
    empty = pd.DataFrame(columns=["close", "volume"])
    result = benchmarks.benchmark_cumulative_return(
        "ANY", date(2025, 6, 1), date(2025, 6, 30), price_frame=empty
    )
    assert result is None


def test_all_nan_closes_returns_none():
    df = _make_prices_df(
        [(date(2025, 6, 2), float("nan")), (date(2025, 6, 3), float("nan"))]
    )
    result = benchmarks.benchmark_cumulative_return(
        "ANY", date(2025, 6, 1), date(2025, 6, 30), price_frame=df
    )
    assert result is None


def test_price_frame_injection_skips_get_prices(monkeypatch):
    """Supplying `price_frame=` must bypass the network-bound fetch."""

    def _explode(*a, **k):
        pytest.fail("get_prices should not be called when price_frame is supplied")

    monkeypatch.setattr(benchmarks, "get_prices", _explode)

    df = _make_prices_df(
        [(date(2025, 1, 2), 100.0), (date(2025, 12, 31), 110.0)]
    )
    result = benchmarks.benchmark_cumulative_return(
        "ANY", date(2025, 1, 1), date(2025, 12, 31), price_frame=df
    )
    assert result == pytest.approx(0.10)


# ── get_prices seam ──


def test_ticker_missing_from_get_prices_returns_none(monkeypatch):
    """get_prices drops tickers with no data; primitive must not raise."""
    monkeypatch.setattr(benchmarks, "get_prices", lambda tickers, start, end: {})
    result = benchmarks.benchmark_cumulative_return(
        "GONE", date(2025, 6, 1), date(2025, 6, 30)
    )
    assert result is None


def test_fetches_through_get_prices_when_no_frame(monkeypatch):
    """No price_frame → one get_prices call with exactly that ticker."""
    calls: list = []
    df = _make_prices_df([(date(2025, 6, 2), 200.0), (date(2025, 6, 30), 210.0)])

    def _fake(tickers, start, end):
        calls.append((tuple(tickers), start, end))
        return {"SPY": df}

    monkeypatch.setattr(benchmarks, "get_prices", _fake)

    result = benchmarks.benchmark_cumulative_return(
        "SPY", date(2025, 6, 1), date(2025, 6, 30)
    )
    assert calls == [(("SPY",), date(2025, 6, 1), date(2025, 6, 30))]
    assert result == pytest.approx(210.0 / 200.0 - 1.0)


# ── all_benchmark_returns ──


def test_all_benchmark_returns_covers_four_tickers(monkeypatch, price_cache_sample):
    """One get_prices call; four results; synthetic fixture returns match
    the per-ticker totals designed into the fixture."""
    calls: list = []

    def _fake(tickers, start, end):
        calls.append(tuple(tickers))
        return {t: price_cache_sample[t] for t in tickers if t in price_cache_sample}

    monkeypatch.setattr(benchmarks, "get_prices", _fake)

    # Full fixture range — NANC designed for +20%, KRUZ -5%, QQQ +15%.
    # SPY is real fixture data; assert shape only so a fixture refresh
    # doesn't fragility-break this test.
    start = date(2025, 3, 11)
    end = date(2026, 4, 8)
    result = benchmarks.all_benchmark_returns(start, end)

    assert set(result) == {"NANC", "KRUZ", "SPY", "QQQ"}
    assert calls == [("NANC", "KRUZ", "SPY", "QQQ")]
    assert result["NANC"] == pytest.approx(0.20, abs=1e-4)
    assert result["KRUZ"] == pytest.approx(-0.05, abs=1e-4)
    assert result["QQQ"] == pytest.approx(0.15, abs=1e-4)
    assert isinstance(result["SPY"], float)
