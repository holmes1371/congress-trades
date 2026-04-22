"""
Tests for `scoring.filters` — the four signal-quality filter primitives.

Each filter is a small pure function; tests assert the membership /
predicate contract with inline literals (no fixtures needed).

See `design/signal-quality-filters.md` for the drop-vs-tag rationale
per filter; these tests don't encode that decision — they only assert
what each primitive returns.
"""

from __future__ import annotations

import pytest

from scoring import filters


# ── is_broad_market_etf ──


@pytest.mark.parametrize(
    "ticker, expected",
    [
        ("SPY", True),
        ("VOO", True),
        ("IVV", True),
        ("VTI", True),
        ("QQQ", True),
        ("BND", True),
        ("JPM", False),
        ("NVDA", False),
        ("NANC", False),  # niche congressional-tracking ETF, scoreable
        ("KRUZ", False),  # same
        ("XLE", False),   # sector ETF, out of scope for broad-market filter
        ("spy", True),    # case-insensitive
        ("Voo", True),    # case-insensitive
        ("", False),
        (None, False),
    ],
)
def test_is_broad_market_etf(ticker, expected):
    assert filters.is_broad_market_etf(ticker) is expected


# ── is_options_trade ──


@pytest.mark.parametrize(
    "trade, expected",
    [
        ({"type": "BUY", "typeExtended": None}, False),
        ({"type": "SELL", "typeExtended": None}, False),
        ({"type": "buy", "typeExtended": None}, False),  # case
        ({"type": "BUY", "typeExtended": ""}, False),    # empty string treated as null
        ({"type": "EXCHANGE", "typeExtended": None}, True),
        ({"type": "RECEIVE", "typeExtended": None}, True),
        ({"type": "BUY", "typeExtended": "call_purchase"}, True),
        ({"type": "SELL", "typeExtended": "put_sale"}, True),
        ({"type": "", "typeExtended": None}, True),      # defensive: unknown → drop
        ({}, True),                                        # missing keys → drop
    ],
)
def test_is_options_trade(trade, expected):
    assert filters.is_options_trade(trade) is expected


# ── is_non_self_owner ──


@pytest.mark.parametrize(
    "owner, expected",
    [
        ("self", False),
        ("Self", False),
        ("SELF", False),
        ("  self  ", False),  # whitespace
        ("spouse", True),
        ("child", True),
        ("joint", True),
        ("dependent", True),
        ("Spouse", True),
        ("", False),
        (None, False),
    ],
)
def test_is_non_self_owner(owner, expected):
    assert filters.is_non_self_owner(owner) is expected


# ── is_late_filing ──


@pytest.mark.parametrize(
    "filed_after_days, expected",
    [
        (0, False),
        (1, False),
        (20, False),
        (39, False),
        (40, True),
        (41, True),
        (45, True),
        (60, True),
        (None, False),
    ],
)
def test_is_late_filing(filed_after_days, expected):
    assert filters.is_late_filing(filed_after_days) is expected
