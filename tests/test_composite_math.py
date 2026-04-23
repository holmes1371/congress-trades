"""
Tests for composite-score math in `scoring.factors`.

Three primitives to pin behavior on:

  * `_zscore`           — NaN-safe centering + standardization.
  * `_trade_count_score` — inverted-U on trade count.
  * `compute_composite`  — z-score each factor, weighted sum.

The design-note rule is "parametrize over weight tuples so no current
choice is pinned." Since `compute_composite` reads `COMPOSITE_WEIGHTS`
from module scope, we monkeypatch that constant to isolate which
z-column drives the composite. No test here asserts the current
production weights; only the structural invariants (weights sum to 1,
weights non-negative) — both of which #2 is free to re-tune without
breaking this file, as long as the weighted-sum *shape* holds.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from scoring import factors
from scoring.factors import (
    COMPOSITE_WEIGHTS,
    _trade_count_score,
    _zscore,
    compute_composite,
)


# ─── _zscore ──────────────────────────────────────────────────

def test_zscore_standard_input_is_centered_and_scaled():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    z = _zscore(s)
    # Mean 3, sample std = sqrt(10/4) = sqrt(2.5); z-scores symmetric.
    assert z.mean() == pytest.approx(0.0, abs=1e-12)
    assert z.std(ddof=1) == pytest.approx(1.0, abs=1e-12)
    assert z.iloc[0] < 0 < z.iloc[-1]


def test_zscore_constant_input_returns_zeros():
    s = pd.Series([5.0, 5.0, 5.0, 5.0])
    z = _zscore(s)
    assert (z == 0.0).all()


def test_zscore_single_value_returns_zeros():
    # ddof=1 requires n>=2; _zscore's NaN-std branch catches this.
    s = pd.Series([42.0])
    z = _zscore(s)
    assert (z == 0.0).all()


def test_zscore_mixed_nan_propagates_only_in_nan_rows():
    s = pd.Series([1.0, 2.0, 3.0, np.nan])
    z = _zscore(s)
    # First three rows carry real z-scores; last row stays NaN.
    assert z.iloc[:3].notna().all()
    assert math.isnan(z.iloc[3])


def test_zscore_all_nan_returns_zeros():
    # Actual behavior, per the `sd is None or nan or 0` guard in
    # _zscore. The module docstring reads "NaN rows stay NaN" but that
    # clause only fires when *some* non-NaN values drive mean/std.
    s = pd.Series([np.nan, np.nan, np.nan])
    z = _zscore(s)
    assert (z == 0.0).all()


# ─── _trade_count_score ──────────────────────────────────────

@pytest.mark.parametrize(
    "n, expected",
    [
        (0, 0.0),    # floored
        (-5, 0.0),   # negative n short-circuited
        (25, 1.0),   # sweet spot
        (15, 0.6),   # 10 off the peak → 1 - 10/25
        (50, 0.0),   # peak + half_width → zero
        (100, 0.0),  # past the fall-off, still floored at 0
    ],
)
def test_trade_count_score_inverted_u(n, expected):
    assert _trade_count_score(n) == pytest.approx(expected)


# ─── compute_composite structural invariants ────────────────

def test_weights_sum_to_one():
    # Structural: the composite is conceptually a weighted mean.
    # If #2 changes this (e.g. switches to sums of raw values), that's
    # a contract change worth surfacing through a failing test.
    assert sum(COMPOSITE_WEIGHTS.values()) == pytest.approx(1.0)


def test_weights_are_non_negative():
    assert all(w >= 0 for w in COMPOSITE_WEIGHTS.values())


# ─── compute_composite math ───────────────────────────────────

def _factors_frame(rows: list[dict]) -> pd.DataFrame:
    """Build a factors DataFrame with all required columns, defaulting
    missing keys to NaN so each test only sets what it cares about."""
    required_cols = [
        "trade_count",
        "mean_alpha_20d",
        "hit_rate",
        "sharpe_alpha",
        "mean_lag_days",
        "liq_pass_rate",
        "concentration",
    ]
    df = pd.DataFrame(rows)
    for col in required_cols:
        if col not in df.columns:
            df[col] = np.nan
    return df


def test_compute_composite_adds_expected_columns():
    df = _factors_frame([
        {"trade_count": 20, "mean_alpha_20d": 0.01, "hit_rate": 0.55,
         "sharpe_alpha": 0.8, "mean_lag_days": 15, "liq_pass_rate": 0.9,
         "concentration": 0.2},
        {"trade_count": 30, "mean_alpha_20d": 0.02, "hit_rate": 0.6,
         "sharpe_alpha": 1.0, "mean_lag_days": 20, "liq_pass_rate": 1.0,
         "concentration": 0.3},
    ])
    out = compute_composite(df)
    for c in (
        "mean_alpha_20d_z", "hit_rate_z", "sharpe_alpha_z", "neg_lag_z",
        "liq_pass_rate_z", "trade_count_u_z", "concentration_z", "composite",
    ):
        assert c in out.columns


def test_identical_inputs_yield_zero_composite():
    # When every member has identical factor values, every z-score is
    # 0 and the composite is 0 — independent of weights.
    df = _factors_frame([
        {"trade_count": 20, "mean_alpha_20d": 0.01, "hit_rate": 0.55,
         "sharpe_alpha": 0.8, "mean_lag_days": 15, "liq_pass_rate": 0.9,
         "concentration": 0.2},
    ] * 4)
    out = compute_composite(df)
    assert (out["composite"].abs() < 1e-12).all()


@pytest.mark.parametrize(
    "driver_column",
    [
        "mean_alpha_20d_z",
        "hit_rate_z",
        "sharpe_alpha_z",
        "neg_lag_z",
        "liq_pass_rate_z",
        "concentration_z",
    ],
)
def test_composite_equals_isolated_z_column_under_100pct_weight(
    monkeypatch, driver_column
):
    """Monkeypatch COMPOSITE_WEIGHTS so one z-column carries 100% of
    the weight. `compute_composite`'s output must then equal that
    z-column (modulo NaN → 0 fill)."""
    # All keys from the live weights map get zeroed except the driver.
    isolated = {k: 0.0 for k in COMPOSITE_WEIGHTS}
    isolated[driver_column] = 1.0
    monkeypatch.setattr(factors, "COMPOSITE_WEIGHTS", isolated)

    df = _factors_frame([
        {"trade_count": 10, "mean_alpha_20d": 0.00, "hit_rate": 0.40,
         "sharpe_alpha": 0.2, "mean_lag_days": 30, "liq_pass_rate": 0.5,
         "concentration": 0.10},
        {"trade_count": 25, "mean_alpha_20d": 0.02, "hit_rate": 0.55,
         "sharpe_alpha": 1.0, "mean_lag_days": 20, "liq_pass_rate": 0.8,
         "concentration": 0.25},
        {"trade_count": 40, "mean_alpha_20d": 0.04, "hit_rate": 0.70,
         "sharpe_alpha": 1.8, "mean_lag_days": 10, "liq_pass_rate": 1.0,
         "concentration": 0.40},
    ])
    out = compute_composite(df)
    expected = out[driver_column].fillna(0.0)
    assert (out["composite"] - expected).abs().max() < 1e-12


def test_composite_handles_all_nan_factor_column():
    # When a factor column is entirely NaN, its z-scores all become 0
    # (per `_zscore`'s all-NaN branch), so it contributes nothing to
    # the composite. Remaining columns still drive it.
    df = _factors_frame([
        {"trade_count": 10, "mean_alpha_20d": 0.01, "hit_rate": 0.40,
         "sharpe_alpha": 0.5, "mean_lag_days": 20, "liq_pass_rate": 0.8},
        {"trade_count": 20, "mean_alpha_20d": 0.03, "hit_rate": 0.60,
         "sharpe_alpha": 1.2, "mean_lag_days": 10, "liq_pass_rate": 1.0},
    ])
    # concentration intentionally left NaN for both rows.
    out = compute_composite(df)
    assert (out["concentration_z"] == 0.0).all()
    # Composite still computes finite values for both rows.
    assert out["composite"].notna().all()


# ─── aggregate_member_factors: signal-quality tag aggregation (ROADMAP #3) ──


def _stock_buy(
    ticker="AAPL",
    owner="self",
    filed_after=5,
    alpha_20d=0.01,
    alpha_20d_tradedate=None,
):
    """Minimal trade dict for aggregation tests. Caller can override per case.

    Post-#4 schema: both `alpha_20d` (post-file, primary) and
    `alpha_20d_tradedate` (trade-date, diagnostic) keys are populated.
    `alpha_20d_tradedate` defaults to matching `alpha_20d` so existing
    tests see a zero disclosure_drag_20d; callers exercising divergence
    pass an explicit value.
    """
    return {
        "ticker": ticker,
        "type": "BUY",
        "owner": owner,
        "filedAfterDays": filed_after,
        "txDate": "2025-06-02",
        "alpha_20d": alpha_20d,
        "alpha_20d_tradedate": (
            alpha_20d_tradedate if alpha_20d_tradedate is not None else alpha_20d
        ),
        # Tags that score_members.py::apply_filters would have attached:
        "non_self_filing": owner.lower() != "self" if owner else False,
        "late_filing": bool(filed_after and filed_after >= 40),
    }


def test_aggregate_empty_trades_carries_drop_counts():
    """Empty kept-trades still reports the filter-drop counts that led to it."""
    result = factors.aggregate_member_factors(
        [], ticker_adv={}, drop_counts={"etf_drops": 3, "options_drops": 1}
    )
    assert result["trade_count"] == 0
    assert result["non_self_count"] == 0
    assert result["non_self_share"] is None
    assert result["late_count"] == 0
    assert result["late_share"] is None
    assert result["etf_drops"] == 3
    assert result["options_drops"] == 1


def test_aggregate_non_self_share_matches_tag_count():
    trades = [
        _stock_buy(owner="self"),
        _stock_buy(owner="spouse"),
        _stock_buy(owner="child"),
        _stock_buy(owner="self"),
    ]
    result = factors.aggregate_member_factors(trades, ticker_adv={})
    assert result["trade_count"] == 4
    assert result["non_self_count"] == 2
    assert result["non_self_share"] == pytest.approx(0.5)


def test_aggregate_late_share_matches_tag_count():
    trades = [
        _stock_buy(filed_after=10),
        _stock_buy(filed_after=42),
        _stock_buy(filed_after=45),
        _stock_buy(filed_after=5),
    ]
    result = factors.aggregate_member_factors(trades, ticker_adv={})
    assert result["late_count"] == 2
    assert result["late_share"] == pytest.approx(0.5)


def test_aggregate_drop_counts_no_kwarg_defaults_to_zero():
    """Backward-compat: callers that omit `drop_counts` get zeros."""
    result = factors.aggregate_member_factors([_stock_buy()], ticker_adv={})
    assert result["etf_drops"] == 0
    assert result["options_drops"] == 0


def test_aggregate_drop_counts_pass_through_to_output():
    result = factors.aggregate_member_factors(
        [_stock_buy(), _stock_buy(owner="spouse")],
        ticker_adv={},
        drop_counts={"etf_drops": 7, "options_drops": 2},
    )
    assert result["etf_drops"] == 7
    assert result["options_drops"] == 2
    # Tag aggregation still correct alongside drop counts.
    assert result["non_self_count"] == 1
    assert result["non_self_share"] == pytest.approx(0.5)


# ── aggregate_member_factors: post-file vs trade-date alpha (ROADMAP #4) ──


def test_aggregate_post_file_and_tradedate_alpha_independent():
    # 5 BUYs with post-file alpha 0.02 and trade-date alpha 0.05 each →
    # both sets of factors computable; post-file mean = 0.02,
    # trade-date mean = 0.05, disclosure_drag = -0.03 (follower missed
    # 3 points of runup on average — expected sign for informed trades).
    trades = [
        _stock_buy(alpha_20d=0.02, alpha_20d_tradedate=0.05)
        for _ in range(5)
    ]
    result = factors.aggregate_member_factors(trades, ticker_adv={})
    assert result["mean_alpha_20d"] == pytest.approx(0.02)
    assert result["mean_alpha_20d_tradedate"] == pytest.approx(0.05)
    assert result["hit_rate"] == pytest.approx(1.0)           # all post-file positive
    assert result["hit_rate_tradedate"] == pytest.approx(1.0)  # all trade-date positive
    assert result["disclosure_drag_20d"] == pytest.approx(-0.03)


def test_aggregate_disclosure_drag_positive_when_postfile_beats_tradedate():
    # Mirror image: follower's post-file entry outperformed the member's
    # trade-date capture. Rare in practice; positive disclosure_drag_20d.
    trades = [
        _stock_buy(alpha_20d=0.08, alpha_20d_tradedate=0.03)
        for _ in range(5)
    ]
    result = factors.aggregate_member_factors(trades, ticker_adv={})
    assert result["disclosure_drag_20d"] == pytest.approx(0.05)


def test_aggregate_tradedate_factors_none_when_insufficient_buys():
    # Under MIN_BUYS_FOR_ALPHA = 5, neither quartet computes; both the
    # post-file and trade-date factor blocks are None; disclosure_drag
    # is None too.
    trades = [_stock_buy(alpha_20d=0.02, alpha_20d_tradedate=0.05)] * 3
    result = factors.aggregate_member_factors(trades, ticker_adv={})
    assert result["mean_alpha_20d"] is None
    assert result["mean_alpha_20d_tradedate"] is None
    assert result["sharpe_alpha_tradedate"] is None
    assert result["disclosure_drag_20d"] is None


def test_aggregate_disclosure_drag_none_when_tradedate_missing():
    # Post-file alpha present on all 5 BUYs; trade-date explicitly None
    # (simulates a member whose trades couldn't compute trade-date
    # alpha, e.g. price cache gap at the trade date). Post-file
    # factors compute; trade-date factors all None; drag None.
    trades = [
        _stock_buy(alpha_20d=0.04, alpha_20d_tradedate=None)
        for _ in range(5)
    ]
    # _stock_buy's default fallback means `alpha_20d_tradedate` = 0.04
    # when the caller passes None; override explicitly here so the
    # trade-date path legitimately has no data.
    for t in trades:
        t["alpha_20d_tradedate"] = None

    result = factors.aggregate_member_factors(trades, ticker_adv={})
    assert result["mean_alpha_20d"] == pytest.approx(0.04)
    assert result["mean_alpha_20d_tradedate"] is None
    assert result["disclosure_drag_20d"] is None


def test_aggregate_empty_trades_carries_new_postfile_keys():
    """Empty kept-trades still exposes the new _tradedate and
    disclosure_drag keys as None — downstream consumers (leaderboard
    builder) must not KeyError on members with no kept trades."""
    result = factors.aggregate_member_factors([], ticker_adv={})
    assert result["mean_alpha_20d_tradedate"] is None
    assert result["hit_rate_tradedate"] is None
    assert result["sharpe_alpha_tradedate"] is None
    assert result["disclosure_drag_20d"] is None
