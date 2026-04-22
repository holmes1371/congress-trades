"""
benchmarks.py — cumulative total return for reference benchmarks
================================================================

First-close-to-last-close total return over a window, for the four
reference instruments in `design/project-framing.md` (NANC, KRUZ, SPY,
QQQ). Thin layer on top of `scoring/price_cache.py` — no pricing
infrastructure of its own, no agent judgment.

Used by `build_leaderboard.py` to render a benchmark reference block
above the 180d/365d rankings. Returns are gross of expense ratios and
slippage; the follow list is also reported gross, so the comparison is
consistent. Net-of-fees is ROADMAP #7's overlay.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from price_cache import get_prices


BENCHMARK_TICKERS: tuple[str, ...] = ("NANC", "KRUZ", "SPY", "QQQ")


def benchmark_cumulative_return(
    ticker: str,
    window_start: date,
    window_end: date,
    price_frame: pd.DataFrame | None = None,
) -> float | None:
    """
    First-close-to-last-close total return over [window_start, window_end].

    Uses `price_frame` if supplied (avoiding a network call); otherwise
    fetches through `price_cache.get_prices`. Returns `None` when no
    cached/available data covers the window — matches the `get_prices`
    convention of dropping tickers with no data rather than raising.

    `auto_adjust=True` in `price_cache._bulk_download` means closes are
    split-and-dividend-adjusted, so total return is just
    `last_close / first_close - 1` with no extra dividend handling.
    """
    if price_frame is None:
        frames = get_prices([ticker], window_start, window_end)
        price_frame = frames.get(ticker)
    if price_frame is None or price_frame.empty:
        return None
    closes = price_frame["close"].dropna()
    if closes.empty:
        return None
    return float(closes.iloc[-1] / closes.iloc[0] - 1.0)


def all_benchmark_returns(
    window_start: date,
    window_end: date,
) -> dict[str, float | None]:
    """Return `{ticker: cumulative_return_or_None}` for every benchmark."""
    frames = get_prices(list(BENCHMARK_TICKERS), window_start, window_end)
    return {
        t: benchmark_cumulative_return(t, window_start, window_end, frames.get(t))
        for t in BENCHMARK_TICKERS
    }
