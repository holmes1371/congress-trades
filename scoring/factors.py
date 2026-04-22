"""
factors.py — per-trade alpha, per-member factor aggregation, composite scoring
==============================================================================

All mechanical. No agent interpretation.

Factor families (see project discussion for full rationale):

  1. Return quality
       mean_alpha_20d    — mean market-adjusted 20-day return (BUY trades only)
       hit_rate          — share of BUY trades with positive 20d alpha
       sharpe_alpha      — mean / stdev of 20d alphas

  2. Copyability
       mean_lag_days     — mean disclosure lag; inverted for scoring
       liq_pass_rate     — share of trades in tickers with >$10M ADV

  3. Signal strength
       trade_count       — total trade count in window; inverted-U in scoring
       concentration     — Herfindahl index on tickers (higher = more conviction)
       buy_sell_balance  — 1 - |buys - sells| / total (higher = more balanced)

Composite weights (must sum to 1.0):

  mean_alpha_20d_z     0.25
  hit_rate_z           0.15
  sharpe_alpha_z       0.15
  neg_lag_z            0.20
  liq_pass_rate_z      0.10
  trade_count_u_z      0.10
  concentration_z      0.05

Dual window: every factor is computed on both a 180d and 365d filtered
slice of the member's trades; the composite is computed separately for
each window, and a rank divergence flag is added.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

# ── Constants ──────────────────────────────────────────────
MIN_TRADES_QUALIFY     = 10        # total trades in 365d window to be scored
MIN_BUYS_FOR_ALPHA     = 5         # min buy trades to produce alpha factors
LIQUIDITY_ADV_FLOOR    = 10_000_000  # $10M average daily $-volume
ALPHA_HORIZONS         = [5, 20, 60]  # business days forward
TRADE_COUNT_SWEET_SPOT = 25        # peak of the inverted-U
TRADE_COUNT_HALF_WIDTH = 25        # score → 0 at ±HALF_WIDTH from peak

COMPOSITE_WEIGHTS = {
    "mean_alpha_20d_z":   0.25,
    "hit_rate_z":         0.15,
    "sharpe_alpha_z":     0.15,
    "neg_lag_z":          0.20,
    "liq_pass_rate_z":    0.10,
    "trade_count_u_z":    0.10,
    "concentration_z":    0.05,
}


# ── Per-trade alpha ─────────────────────────────────────────

def _next_close_at_or_after(prices: pd.DataFrame, target: date) -> float | None:
    """Return the close on the first trading day >= target, or None."""
    if prices is None or prices.empty:
        return None
    mask = prices.index.date >= target
    forward = prices.loc[mask]
    if forward.empty:
        return None
    return float(forward["close"].iloc[0])


def _close_n_bdays_later(prices: pd.DataFrame, entry_idx_date: date, n: int) -> float | None:
    """Close n business days after entry_idx_date on the prices frame."""
    if prices is None or prices.empty:
        return None
    # Locate entry_idx_date row
    idx = prices.index.searchsorted(pd.Timestamp(entry_idx_date))
    target_idx = idx + n
    if target_idx >= len(prices):
        return None
    return float(prices["close"].iloc[target_idx])


def compute_trade_alpha(
    trade: dict,
    stock_prices: pd.DataFrame,
    spy_prices: pd.DataFrame,
) -> dict[str, float | None]:
    """
    Compute alpha_5d / alpha_20d / alpha_60d for a single BUY trade.
    Returns None for any horizon that can't be computed.

    Only BUYs are scored — sells are not predictive alpha signals.
    """
    result: dict[str, float | None] = {f"alpha_{h}d": None for h in ALPHA_HORIZONS}
    if not trade or (trade.get("type") or "").upper() != "BUY":
        return result

    tx_date_str = trade.get("txDate")
    if not tx_date_str:
        return result
    try:
        tx_date = date.fromisoformat(tx_date_str)
    except Exception:
        return result

    # Entry: first trading day >= tx_date
    entry_stock = _next_close_at_or_after(stock_prices, tx_date)
    entry_spy = _next_close_at_or_after(spy_prices, tx_date)
    if entry_stock is None or entry_spy is None:
        return result

    # Find the actual entry date index on each frame (for n-bday lookups)
    stock_entry_idx = stock_prices.index[stock_prices.index.date >= tx_date][0]
    spy_entry_idx = spy_prices.index[spy_prices.index.date >= tx_date][0]

    for h in ALPHA_HORIZONS:
        exit_stock = _close_n_bdays_later(stock_prices, stock_entry_idx.date(), h)
        exit_spy = _close_n_bdays_later(spy_prices, spy_entry_idx.date(), h)
        if exit_stock is None or exit_spy is None:
            continue
        if entry_stock <= 0 or entry_spy <= 0:
            continue
        stock_ret = exit_stock / entry_stock - 1.0
        spy_ret = exit_spy / entry_spy - 1.0
        result[f"alpha_{h}d"] = stock_ret - spy_ret
    return result


def compute_ticker_adv(prices: pd.DataFrame) -> float:
    """Average daily dollar volume over the cached window."""
    if prices is None or prices.empty:
        return 0.0
    if "volume" not in prices.columns or "close" not in prices.columns:
        return 0.0
    dollar_vol = (prices["close"] * prices["volume"]).dropna()
    if dollar_vol.empty:
        return 0.0
    return float(dollar_vol.mean())


# ── Per-member factor aggregation ──────────────────────────

def aggregate_member_factors(
    trades: list[dict],
    ticker_adv: dict[str, float],
    drop_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """
    Given a list of trades (already enriched with alpha_*d keys for BUYs)
    and a ticker → ADV map, compute all factor values for one member over
    one window.

    Returns a dict of scalar factor values. None where insufficient data.

    `drop_counts`, if provided, should carry the per-filter drop totals
    from `score_members.py::apply_filters` (keys: "etf_drops",
    "options_drops"). These flow straight through to the output for
    leaderboard visibility; they are NOT scoring inputs in #3. Per-trade
    `non_self_filing` / `late_filing` boolean tags are read off each
    trade dict and aggregated into `non_self_share` / `late_share`.
    """
    drop_counts = drop_counts or {}
    etf_drops = int(drop_counts.get("etf_drops", 0))
    options_drops = int(drop_counts.get("options_drops", 0))

    total_trades = len(trades)
    if total_trades == 0:
        return {
            "trade_count":      0,
            "buy_count":        0,
            "sell_count":       0,
            "mean_alpha_20d":   None,
            "median_alpha_20d": None,
            "hit_rate":         None,
            "sharpe_alpha":     None,
            "mean_lag_days":    None,
            "liq_pass_rate":    None,
            "concentration":    None,
            "buy_sell_balance": None,
            "non_self_count":   0,
            "non_self_share":   None,
            "late_count":       0,
            "late_share":       None,
            "etf_drops":        etf_drops,
            "options_drops":    options_drops,
        }

    buys = [t for t in trades if (t.get("type") or "").upper() == "BUY"]
    sells = [t for t in trades if (t.get("type") or "").upper() == "SELL"]

    # Return-quality factors (on BUYs only)
    alpha_20d = [t.get("alpha_20d") for t in buys if t.get("alpha_20d") is not None]
    mean_alpha = float(np.mean(alpha_20d)) if len(alpha_20d) >= MIN_BUYS_FOR_ALPHA else None
    median_alpha = float(np.median(alpha_20d)) if len(alpha_20d) >= MIN_BUYS_FOR_ALPHA else None
    hit_rate = (
        float(np.mean([1.0 if a > 0 else 0.0 for a in alpha_20d]))
        if len(alpha_20d) >= MIN_BUYS_FOR_ALPHA else None
    )
    if len(alpha_20d) >= MIN_BUYS_FOR_ALPHA:
        sd = float(np.std(alpha_20d, ddof=1)) if len(alpha_20d) > 1 else 0.0
        sharpe = float(np.mean(alpha_20d) / sd) if sd > 0 else None
    else:
        sharpe = None

    # Disclosure lag (all trades)
    lags = [t.get("filedAfterDays") for t in trades if isinstance(t.get("filedAfterDays"), (int, float))]
    mean_lag = float(np.mean(lags)) if lags else None

    # Liquidity pass rate
    liq_flags = []
    for t in trades:
        tkr = (t.get("ticker") or "").upper()
        if not tkr:
            continue
        adv = ticker_adv.get(tkr, 0.0)
        liq_flags.append(1.0 if adv >= LIQUIDITY_ADV_FLOOR else 0.0)
    liq_pass_rate = float(np.mean(liq_flags)) if liq_flags else None

    # Concentration (Herfindahl on ticker shares)
    ticker_counts: dict[str, int] = {}
    for t in trades:
        tkr = (t.get("ticker") or "").upper()
        if not tkr:
            continue
        ticker_counts[tkr] = ticker_counts.get(tkr, 0) + 1
    if ticker_counts:
        total = sum(ticker_counts.values())
        shares = [c / total for c in ticker_counts.values()]
        concentration = float(sum(s * s for s in shares))
    else:
        concentration = None

    # Buy/sell balance
    total_bs = len(buys) + len(sells)
    if total_bs > 0:
        bs_balance = 1.0 - abs(len(buys) - len(sells)) / total_bs
    else:
        bs_balance = None

    # Signal-quality tag aggregation (ROADMAP #3).
    # Tags are attached per-trade by `score_members.py::apply_filters`.
    # Shares are computed over the post-filter trade set (denominator =
    # kept trades), so they answer "of the trades we scored, what
    # fraction were non-self / late."
    non_self_count = sum(1 for t in trades if t.get("non_self_filing"))
    late_count = sum(1 for t in trades if t.get("late_filing"))
    non_self_share = non_self_count / total_trades
    late_share = late_count / total_trades

    return {
        "trade_count":      total_trades,
        "buy_count":        len(buys),
        "sell_count":       len(sells),
        "mean_alpha_20d":   mean_alpha,
        "median_alpha_20d": median_alpha,
        "hit_rate":         hit_rate,
        "sharpe_alpha":     sharpe,
        "mean_lag_days":    mean_lag,
        "liq_pass_rate":    liq_pass_rate,
        "concentration":    concentration,
        "buy_sell_balance": bs_balance,
        "non_self_count":   non_self_count,
        "non_self_share":   non_self_share,
        "late_count":       late_count,
        "late_share":       late_share,
        "etf_drops":        etf_drops,
        "options_drops":    options_drops,
    }


# ── Composite scoring ──────────────────────────────────────

def _trade_count_score(n: int) -> float:
    """
    Inverted-U: peaks at TRADE_COUNT_SWEET_SPOT, falls linearly to 0 at
    ±TRADE_COUNT_HALF_WIDTH from peak, floored at 0.
    """
    if n <= 0:
        return 0.0
    dist = abs(n - TRADE_COUNT_SWEET_SPOT)
    raw = 1.0 - dist / TRADE_COUNT_HALF_WIDTH
    return max(0.0, raw)


def _zscore(series: pd.Series) -> pd.Series:
    """NaN-safe z-score: NaN rows stay NaN."""
    mu = series.mean(skipna=True)
    sd = series.std(skipna=True, ddof=1)
    if sd is None or sd == 0 or math.isnan(sd):
        return pd.Series(0.0, index=series.index)
    return (series - mu) / sd


def compute_composite(factors_df: pd.DataFrame) -> pd.DataFrame:
    """
    Given a DataFrame where each row is a member-window with factor columns,
    add z-score columns and a final `composite` column.

    Expected input columns (any of which may be NaN):
        trade_count, mean_alpha_20d, hit_rate, sharpe_alpha,
        mean_lag_days, liq_pass_rate, concentration

    Returns a copy with the same index plus z-score and composite columns.
    """
    df = factors_df.copy()

    # Derived raw inputs
    df["neg_lag"] = -df["mean_lag_days"]
    df["trade_count_u"] = df["trade_count"].apply(
        lambda n: _trade_count_score(int(n)) if pd.notna(n) else 0.0
    )

    # Z-score each
    df["mean_alpha_20d_z"] = _zscore(df["mean_alpha_20d"])
    df["hit_rate_z"]       = _zscore(df["hit_rate"])
    df["sharpe_alpha_z"]   = _zscore(df["sharpe_alpha"])
    df["neg_lag_z"]        = _zscore(df["neg_lag"])
    df["liq_pass_rate_z"]  = _zscore(df["liq_pass_rate"])
    df["trade_count_u_z"]  = _zscore(df["trade_count_u"])
    df["concentration_z"]  = _zscore(df["concentration"])

    # Composite: weighted sum, treating NaN z-scores as 0 (no signal → neutral)
    composite = pd.Series(0.0, index=df.index)
    for col, w in COMPOSITE_WEIGHTS.items():
        composite = composite.add(df[col].fillna(0.0) * w, fill_value=0.0)
    df["composite"] = composite
    return df
