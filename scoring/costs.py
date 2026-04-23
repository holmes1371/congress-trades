"""
costs.py — cost / tax / sizing overlays (ROADMAP #7)
====================================================

Pure-math overlay layer on top of the gross per-trade PnL produced
by `scoring/backtest.py::walk_forward` and `scoring/paper_log.py`.
See `design/cost-tax-sizing-overlays.md` for scope, locked decisions,
and responsibility table.

No I/O. No dependencies on paper_log / backtest. Callers pass in
gross pnl_pct values and overlay config; this module returns the
net-of-overlay values.
"""

from __future__ import annotations

import statistics
import warnings


SLIPPAGE_BPS_TIERS: dict[str, float] = {
    "large": 5.0,   # ADV >= $100M / day
    "mid":   25.0,  # $10M <= ADV < $100M
    "small": 75.0,  # ADV < $10M (also the fallback for missing/None ADV)
}
ADV_LARGE_THRESHOLD: float = 100_000_000.0
ADV_MID_THRESHOLD:   float = 10_000_000.0

# Default combined short-term rate: federal 24% + VA state 5.75%.
DEFAULT_TAX_RATE: float = 0.2975


def classify_tier(adv: float | None) -> str:
    """Return 'large' | 'mid' | 'small' by ADV. None / non-positive
    → 'small' (conservative — assume highest cost when we don't know)."""
    if adv is None or adv <= 0:
        return "small"
    if adv >= ADV_LARGE_THRESHOLD:
        return "large"
    if adv >= ADV_MID_THRESHOLD:
        return "mid"
    return "small"


def slippage_bps_for_ticker(
    ticker: str,
    ticker_adv: dict[str, float],
    *,
    mode: str = "tiered",
) -> float:
    """Round-trip slippage in basis points for `ticker`.

    mode='off'           → 0.0
    mode='tiered'        → SLIPPAGE_BPS_TIERS[classify_tier(adv)]
    mode='flat_bps:<N>'  → float(N) — user-specified flat bps for every trade.
    """
    if mode == "off":
        return 0.0
    if mode == "tiered":
        adv = ticker_adv.get(ticker)
        return SLIPPAGE_BPS_TIERS[classify_tier(adv)]
    if mode.startswith("flat_bps:"):
        raw = mode.split(":", 1)[1]
        try:
            return float(raw)
        except ValueError:
            raise ValueError(f"slippage mode {mode!r}: could not parse bps value {raw!r}")
    raise ValueError(f"unknown slippage mode: {mode!r}")


def apply_slippage(pnl_pct: float, bps: float) -> float:
    """Round-trip haircut: subtract bps/10000 from pnl_pct. Paid in
    both directions (no gain/loss branch)."""
    return pnl_pct - bps / 10_000.0


def apply_tax(pnl_pct: float, rate: float) -> float:
    """Gain-only haircut. Losses flow through unchanged."""
    if rate < 0 or rate >= 1:
        raise ValueError(f"tax rate must be in [0, 1), got {rate!r}")
    if pnl_pct <= 0:
        return pnl_pct
    return pnl_pct * (1.0 - rate)


def apply_sizing(trades: list[dict], mode: str = "equal") -> float:
    """Portfolio-level mean of each trade's `pnl_pct`.

    mode='equal'  → arithmetic mean.
    mode='range'  → value-weighted by t['value']. Trades with missing
                    or zero 'value' fall back to the per-run median of
                    the present values; if every 'value' is missing,
                    degrades to equal-weight with a warning.

    Empty `trades` returns 0.0 — the ledger-empty case in both
    consumers.
    """
    if not trades:
        return 0.0
    if mode == "equal":
        return sum(t["pnl_pct"] for t in trades) / len(trades)
    if mode != "range":
        raise ValueError(f"unknown sizing mode: {mode!r}")

    # range mode
    present = [float(t["value"]) for t in trades if t.get("value")]
    if not present:
        warnings.warn(
            "apply_sizing(range): no trades have a 'value' field; "
            "falling back to equal-weight.",
            stacklevel=2,
        )
        return sum(t["pnl_pct"] for t in trades) / len(trades)

    fallback = float(statistics.median(present))
    weighted_sum = 0.0
    total_weight = 0.0
    for t in trades:
        v = t.get("value")
        w = float(v) if v else fallback
        weighted_sum += w * t["pnl_pct"]
        total_weight += w
    return weighted_sum / total_weight
