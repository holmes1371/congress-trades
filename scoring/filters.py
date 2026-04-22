"""
filters.py — signal-quality filters over normalized trade records
=================================================================

Four pure functions applied in `scoring/score_members.py` between ticker
normalization and alpha attachment. ETF + options trades drop from the
scoring / signal-generation universe; non-self-owner + late-filed trades
stay in but are tagged so downstream aggregation can surface the share.

See `design/signal-quality-filters.md` for the full rationale, including
the drop-vs-tag decision per filter.
"""

from __future__ import annotations


# Broad-market US equity ETFs. A member buying SPY is not an informed
# signal — index exposure carries no member-specific information content.
#
# NOT in this list on purpose:
#   - NANC, KRUZ: niche congressional-tracking ETFs. A member buying
#     NANC is a signal about Congress's own consensus; keep scoreable.
#   - Sector ETFs (XLE, XLF, XLK, etc.): may carry member-informed
#     signal — e.g. an Energy Committee member buying XLE. Out of scope
#     for a broad-market filter; revisit if noise persists post-#3.
BROAD_MARKET_ETFS = frozenset({
    "SPY", "VOO", "IVV", "VTI", "VEA", "VXUS", "VWO",
    "AGG", "BND", "QQQ", "IWM", "DIA", "SCHB", "ITOT",
})


def is_broad_market_etf(ticker: str | None) -> bool:
    """True if `ticker` is a broad-market ETF that should drop from scoring."""
    if not ticker:
        return False
    return ticker.upper() in BROAD_MARKET_ETFS


def is_options_trade(trade: dict) -> bool:
    """True if the trade is options or anything outside plain stock BUY/SELL.

    Safe default: `type` outside {BUY, SELL} OR `typeExtended` non-empty.
    The committed capitoltrades fixture has `typeExtended: null` on all
    plain stock records, so a non-empty value is a strong options
    indicator in practice. Commit 2 of #3 verifies this against a real
    `scoring/cache/trades/` sample and tightens the predicate if the
    safe default over-drops (e.g. corporate-action metadata in
    `typeExtended`).
    """
    t = (trade.get("type") or "").upper()
    ext = trade.get("typeExtended") or ""
    return t not in {"BUY", "SELL"} or bool(ext)


def is_non_self_owner(owner: str | None) -> bool:
    """True if the trade was filed for a non-self owner (spouse, child, etc).

    The ROADMAP treats spouse vs. member as a signal-quality variable;
    this tag carries that distinction without dropping the trade.
    Observed values include 'spouse', 'child'; production data also has
    'dependent' and 'joint'. All non-self categories tag identically.
    """
    if not owner:
        return False
    return owner.strip().lower() != "self"


def is_late_filing(filed_after_days: int | None) -> bool:
    """True if the trade was filed at day 40+ (STOCK Act deadline is 45).

    Persistent late filing is itself a signal-quality variable worth
    surfacing rather than swallowing. The 40-day threshold captures
    "approaching the deadline" without tagging every borderline-41-day
    filing as noise.
    """
    return bool(filed_after_days and filed_after_days >= 40)
