"""
Tests for `scoring.costs` — cost / tax / sizing overlay primitives
(ROADMAP #7).

Pure-math module. Tests cover each primitive's contract in isolation:
tier classification boundaries, slippage-mode resolution including the
`flat_bps:<N>` parse, the gain-only tax haircut, and the two sizing
modes (equal, range) with their fallback paths.

No file fixtures — in-memory `ticker_adv` dicts and trade-list
literals cover every case.
"""

from __future__ import annotations

import pytest

from scoring import costs


# ── classify_tier ─────────────────────────────────────────────────

@pytest.mark.parametrize(
    "adv, tier",
    [
        (2e8, "large"),                        # well above $100M
        (costs.ADV_LARGE_THRESHOLD, "large"),  # at boundary → large
        (costs.ADV_LARGE_THRESHOLD - 1, "mid"),# just under $100M
        (5e7, "mid"),                          # between $10M and $100M
        (costs.ADV_MID_THRESHOLD, "mid"),      # at boundary → mid
        (costs.ADV_MID_THRESHOLD - 1, "small"),# just under $10M
        (1e6, "small"),                        # well below $10M
        (0.0, "small"),                        # zero → small
        (-5.0, "small"),                       # negative → small (defensive)
        (None, "small"),                       # None → small
    ],
)
def test_classify_tier(adv, tier):
    assert costs.classify_tier(adv) == tier


# ── slippage_bps_for_ticker ───────────────────────────────────────

def test_slippage_mode_off_returns_zero():
    assert costs.slippage_bps_for_ticker("AAPL", {"AAPL": 2e8}, mode="off") == 0.0


@pytest.mark.parametrize(
    "adv, expected_bps",
    [
        (2e8, 5.0),
        (5e7, 25.0),
        (1e6, 75.0),
    ],
)
def test_slippage_tiered_matches_adv_tier(adv, expected_bps):
    bps = costs.slippage_bps_for_ticker("X", {"X": adv}, mode="tiered")
    assert bps == expected_bps


def test_slippage_tiered_missing_ticker_defaults_small():
    # Missing from ticker_adv → None → small-cap tier (conservative).
    assert costs.slippage_bps_for_ticker("X", {}, mode="tiered") == 75.0


@pytest.mark.parametrize("raw, expected", [("15", 15.0), ("0", 0.0), ("100", 100.0), ("3.5", 3.5)])
def test_slippage_flat_bps_parses(raw, expected):
    assert costs.slippage_bps_for_ticker("X", {}, mode=f"flat_bps:{raw}") == expected


def test_slippage_flat_bps_malformed_raises():
    with pytest.raises(ValueError, match="could not parse"):
        costs.slippage_bps_for_ticker("X", {}, mode="flat_bps:abc")


def test_slippage_unknown_mode_raises():
    with pytest.raises(ValueError, match="unknown slippage mode"):
        costs.slippage_bps_for_ticker("X", {}, mode="garbage")


# ── apply_slippage ────────────────────────────────────────────────

@pytest.mark.parametrize(
    "pnl, bps, expected",
    [
        (0.10, 5.0,   0.10 - 0.0005),    # positive pnl, large-cap bps
        (-0.05, 25.0, -0.05 - 0.0025),   # negative pnl, still pays spread
        (0.00, 75.0,  -0.0075),          # zero pnl, small-cap haircut
        (0.10, 0.0,   0.10),             # no slippage → no-op
    ],
)
def test_apply_slippage_arithmetic(pnl, bps, expected):
    assert costs.apply_slippage(pnl, bps) == pytest.approx(expected)


# ── apply_tax ─────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "pnl, rate, expected",
    [
        (0.10, 0.25,  0.075),   # gain haircut
        (0.10, 0.0,   0.10),    # rate 0 → no-op
        (-0.05, 0.25, -0.05),   # loss untouched
        (0.0, 0.25,   0.0),     # zero pnl untouched
        (0.10, costs.DEFAULT_TAX_RATE, 0.10 * (1 - costs.DEFAULT_TAX_RATE)),
    ],
)
def test_apply_tax_gain_only(pnl, rate, expected):
    assert costs.apply_tax(pnl, rate) == pytest.approx(expected)


@pytest.mark.parametrize("rate", [-0.01, 1.0, 1.5])
def test_apply_tax_invalid_rate_raises(rate):
    with pytest.raises(ValueError, match="tax rate"):
        costs.apply_tax(0.1, rate)


# ── apply_sizing ──────────────────────────────────────────────────

def test_apply_sizing_equal_returns_mean():
    trades = [{"pnl_pct": 0.10, "value": 50_000}, {"pnl_pct": -0.02, "value": 10_000}]
    assert costs.apply_sizing(trades, mode="equal") == pytest.approx(0.04)


def test_apply_sizing_empty_returns_zero():
    assert costs.apply_sizing([], mode="equal") == 0.0
    assert costs.apply_sizing([], mode="range") == 0.0


def test_apply_sizing_range_weights_by_value():
    trades = [
        {"pnl_pct": 0.10, "value": 100_000},
        {"pnl_pct": -0.05, "value": 25_000},
    ]
    # (100k * 0.10 + 25k * -0.05) / 125k = (10_000 - 1_250) / 125_000 = 0.07
    assert costs.apply_sizing(trades, mode="range") == pytest.approx(0.07)


def test_apply_sizing_range_missing_value_uses_median_fallback():
    trades = [
        {"pnl_pct": 0.10, "value": 100_000},
        {"pnl_pct": -0.05, "value": 50_000},
        {"pnl_pct": 0.20},  # missing value → filled with median(100k, 50k) = 75k
    ]
    # numerator:   100k*0.10 + 50k*-0.05 + 75k*0.20 = 10_000 - 2_500 + 15_000 = 22_500
    # denominator: 100k + 50k + 75k = 225k
    # result:      22_500 / 225_000 = 0.10
    assert costs.apply_sizing(trades, mode="range") == pytest.approx(0.10)


def test_apply_sizing_range_all_missing_falls_back_to_equal_with_warning():
    trades = [{"pnl_pct": 0.10}, {"pnl_pct": 0.20}, {"pnl_pct": -0.06}]
    with pytest.warns(UserWarning, match="no trades have a 'value' field"):
        got = costs.apply_sizing(trades, mode="range")
    assert got == pytest.approx((0.10 + 0.20 - 0.06) / 3)


def test_apply_sizing_range_zero_value_treated_as_missing():
    # A zero `value` is equivalent to missing per the design note
    # (t.get("value") is falsy in both cases); the fallback median
    # applies. Pins the interpretation so a future refactor can't
    # silently divide by zero.
    trades = [
        {"pnl_pct": 0.10, "value": 100_000},
        {"pnl_pct": 0.20, "value": 0},  # falsy → fallback
    ]
    # median of present values {100k} = 100k; both trades weight at 100k → equal-weight mean
    assert costs.apply_sizing(trades, mode="range") == pytest.approx(0.15)


def test_apply_sizing_unknown_mode_raises():
    with pytest.raises(ValueError, match="unknown sizing mode"):
        costs.apply_sizing([{"pnl_pct": 0.1}], mode="garbage")
