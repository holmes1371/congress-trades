"""
price_cache.py — yfinance price pull with local CSV cache
=========================================================

Provides daily close + volume history for a set of tickers over a given
date range, backed by a per-ticker CSV cache at scoring/cache/prices/.

Cache format (one file per ticker):
    scoring/cache/prices/<TICKER>.csv
    columns: date (YYYY-MM-DD), close, volume

Strategy:
    - On request, load existing cache for each ticker.
    - Determine which tickers need a fresh fetch (missing cache, or cache
      doesn't cover the requested [start, end] range).
    - Bulk-fetch those via yf.download(list_of_tickers, ...) in one call.
    - Merge new rows into cache, dedupe by date, rewrite CSV.
    - Return a dict {ticker: pandas.DataFrame indexed by date}.

This module does all mechanical price work. No agent interpretation.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

CACHE_DIR = Path(__file__).parent / "cache" / "prices"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# Windows reserved device names — the cowork mount is Windows-backed so
# any of these as a bare filename will fail to open. Suffix with '_' to
# sidestep the reservation while keeping the ticker readable.
_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *{f"COM{i}" for i in range(1, 10)},
    *{f"LPT{i}" for i in range(1, 10)},
}


def _cache_path(ticker: str) -> Path:
    # Replace characters that are illegal in filenames on some OSes.
    safe = ticker.replace("/", "_").replace("\\", "_").upper()
    if safe in _WIN_RESERVED:
        safe = f"{safe}_"
    return CACHE_DIR / f"{safe}.csv"


def _load_cached(ticker: str) -> pd.DataFrame:
    path = _cache_path(ticker)
    if not path.exists():
        return pd.DataFrame(columns=["close", "volume"])
    try:
        df = pd.read_csv(path, parse_dates=["date"])
        df = df.set_index("date").sort_index()
        return df
    except Exception as exc:
        print(f"  ! Could not read cache for {ticker}: {exc}", file=sys.stderr)
        return pd.DataFrame(columns=["close", "volume"])


def _save_cache(ticker: str, df: pd.DataFrame) -> None:
    path = _cache_path(ticker)
    out = df.copy()
    out.index.name = "date"
    out = out.reset_index()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out.to_csv(path, index=False)


def _needs_fetch(cached: pd.DataFrame, start: date, end: date) -> bool:
    """
    Returns True if the cached frame does NOT fully cover [start, end].
    We allow a small tolerance on the end side (2 business days) so we
    don't refetch just because the market hasn't closed yet today.
    """
    if cached.empty:
        return True
    cached_start = cached.index.min().date()
    cached_end = cached.index.max().date()
    if cached_start > start:
        return True
    # Require cache end to be at least min(end, today - 1) to avoid
    # redundant fetches for future dates.
    tolerable_end = min(end, date.today() - timedelta(days=1))
    if cached_end < tolerable_end:
        return True
    return False


def _bulk_download(tickers: list[str], start: date, end: date) -> dict[str, pd.DataFrame]:
    """
    One yf.download call for a list of tickers. Returns
    {ticker: DataFrame[close, volume] indexed by date}.
    """
    if not tickers:
        return {}

    # yfinance's end is exclusive, so bump by one day.
    fetch_end = end + timedelta(days=1)

    print(f"  price fetch: {len(tickers)} tickers, {start} → {end}", flush=True)
    try:
        raw = yf.download(
            tickers=tickers,
            start=start.isoformat(),
            end=fetch_end.isoformat(),
            progress=False,
            auto_adjust=True,
            group_by="ticker",
            threads=True,
        )
    except Exception as exc:
        print(f"  ! yfinance bulk download failed: {exc}", file=sys.stderr)
        return {}

    out: dict[str, pd.DataFrame] = {}
    if len(tickers) == 1:
        # Single-ticker result is NOT multi-index; synthesize one.
        # When yfinance returns a non-empty frame without a Close
        # column (rate-limit fallback, delisted / unknown ticker,
        # malformed response), drop the ticker rather than constructing
        # a DataFrame from scalar pd.NA values — matches the existing
        # "missing data skips the ticker" convention.
        t = tickers[0]
        if raw.empty or "Close" not in raw.columns:
            return {}
        close = raw["Close"]
        volume = raw["Volume"] if "Volume" in raw.columns else pd.Series(pd.NA, index=close.index)
        sub = pd.DataFrame({"close": close, "volume": volume})
        sub.index = pd.to_datetime(sub.index)
        sub.index.name = "date"
        sub = sub.dropna(subset=["close"])
        out[t] = sub
        return out

    # Multi-ticker: columns are a MultiIndex of (ticker, field). Same
    # guard as the single-ticker branch — no Close column means no
    # usable data, skip the ticker.
    for t in tickers:
        if t not in raw.columns.get_level_values(0):
            continue
        sub_raw = raw[t]
        if sub_raw.empty or "Close" not in sub_raw.columns:
            continue
        close = sub_raw["Close"]
        volume = sub_raw["Volume"] if "Volume" in sub_raw.columns else pd.Series(pd.NA, index=close.index)
        sub = pd.DataFrame({"close": close, "volume": volume})
        sub.index = pd.to_datetime(sub.index)
        sub.index.name = "date"
        sub = sub.dropna(subset=["close"])
        if not sub.empty:
            out[t] = sub
    return out


def get_prices(
    tickers: list[str],
    start: date,
    end: date,
) -> dict[str, pd.DataFrame]:
    """
    Return price history for each ticker over [start, end], using the
    local CSV cache and filling gaps from yfinance.

    The returned DataFrames are indexed by pandas Timestamp (date),
    with columns ['close', 'volume']. Business days only.
    """
    tickers = sorted({t for t in tickers if t and isinstance(t, str)})
    if not tickers:
        return {}

    to_fetch: list[str] = []
    cached_frames: dict[str, pd.DataFrame] = {}

    for t in tickers:
        cached = _load_cached(t)
        cached_frames[t] = cached
        if _needs_fetch(cached, start, end):
            to_fetch.append(t)

    if to_fetch:
        # Fetch a slightly wider window so future runs with small shifts
        # don't trigger extra refetches.
        fetch_start = start - timedelta(days=14)
        fetch_end = end + timedelta(days=2)
        fresh = _bulk_download(to_fetch, fetch_start, fetch_end)
        for t, df in fresh.items():
            existing = cached_frames.get(t, pd.DataFrame(columns=["close", "volume"]))
            if existing.empty:
                merged = df
            else:
                merged = pd.concat([existing, df])
            merged = merged[~merged.index.duplicated(keep="last")].sort_index()
            cached_frames[t] = merged
            _save_cache(t, merged)

    # Final slice to the exact requested window.
    out: dict[str, pd.DataFrame] = {}
    for t, df in cached_frames.items():
        if df.empty:
            continue
        mask = (df.index.date >= start) & (df.index.date <= end)
        sliced = df.loc[mask]
        if not sliced.empty:
            out[t] = sliced
    return out


if __name__ == "__main__":
    # Ad-hoc smoke test
    import json
    today = date.today()
    res = get_prices(["SPY", "NVDA", "AAPL"], today - timedelta(days=90), today)
    for t, df in res.items():
        print(f"{t}: {len(df)} rows, {df.index.min().date()} → {df.index.max().date()}, last close {df['close'].iloc[-1]:.2f}")
