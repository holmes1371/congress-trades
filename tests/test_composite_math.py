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
