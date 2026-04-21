"""
Tests for `scoring.factors.compute_trade_alpha`.

Two slices of coverage:

  1. Parametrized against the hand-crafted scenarios in
     `tests/fixtures/synthetic_alpha_scenarios.py`. Each scenario pins
     a `trade_date → exit_date` span with known prices and a known
     expected alpha vs a flat benchmark. This catches regressions in
     the core arithmetic (`entry`, `n-bday-later`, `stock_ret - spy_ret`)
     without having to hand-construct prices for every edge case.

  2. Direct property tests for the early-exit paths that the scenarios
     don't cover: non-BUY trades, missing or malformed `txDate`, zero
     entry price.

Note on horizons. `compute_trade_alpha` returns all three of
`alpha_{5,20,60}d` at once. The fixture declares `horizon_bdays` so
the tests can pick the matching column; for horizons the fixture's
price series doesn't extend to, the function returns `None` and the
test just skips the assertion for that horizon.

Note on post-file alpha. The POSTFILE_DIVERGENCE scenario ships with
both a `_trade_date` and a `_post_file` expectation. Only the
trade-date side is exercised here — the post-file column is #2's
deliverable and doesn't exist in `factors.py` yet. When #2 lands,
extend this file rather than writing a new one.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from scoring.factors import ALPHA_HORIZONS, compute_trade_alpha


def _prices_df(tuples: list[tuple[date, float]]) -> pd.DataFrame:
    df = pd.DataFrame(
        [{"close": c, "volume": 1_000_000} for _, c in tuples],
        index=pd.to_datetime([d for d, _ in tuples]),
    )
    df.index.name = "date"
    return df.sort_index()


@pytest.mark.parametrize(
    "scenario_name",
    [
        "clean_5d_buy_flat_benchmark",
        "holiday_gap_good_friday",
        "postfile_entry_misses_runup",
        "split_adjusted_no_double_count",
        "entry_day_missing_forward_fills",
    ],
)
def test_synthetic_scenario_trade_date_alpha(
    synthetic_alpha_scenarios, scenario_name
):
    scenario = next(s for s in synthetic_alpha_scenarios if s["name"] == scenario_name)
    stock = _prices_df(scenario["ticker_prices"])
    spy = _prices_df(scenario["benchmark_prices"])

    trade = {"type": "BUY", "txDate": scenario["trade_date"].isoformat()}
    out = compute_trade_alpha(trade, stock, spy)

    horizon = scenario["horizon_bdays"]
    assert horizon in ALPHA_HORIZONS, (
        f"scenario {scenario_name} has horizon {horizon} not in ALPHA_HORIZONS; "
        f"synthetic fixture drifted from code"
    )

    # Scenarios using the post-file key (only one so far) pin the
    # trade-date expectation separately.
    expected = scenario.get(
        "expected_alpha_trade_date_approx", scenario.get("expected_alpha_approx")
    )
    assert expected is not None, f"scenario {scenario_name} has no trade-date expectation"

    got = out[f"alpha_{horizon}d"]
    assert got is not None, f"alpha_{horizon}d should be computable for {scenario_name}"
    assert got == pytest.approx(expected, abs=0.01)


def test_non_buy_returns_all_none():
    stock = _prices_df([(date(2024, 3, 4), 100.0), (date(2024, 3, 11), 105.0)])
    spy = _prices_df([(date(2024, 3, 4), 500.0), (date(2024, 3, 11), 500.0)])
    trade = {"type": "SELL", "txDate": "2024-03-04"}
    out = compute_trade_alpha(trade, stock, spy)
    assert out == {f"alpha_{h}d": None for h in ALPHA_HORIZONS}


def test_missing_tx_date_returns_all_none():
    stock = _prices_df([(date(2024, 3, 4), 100.0)])
    spy = _prices_df([(date(2024, 3, 4), 500.0)])
    trade = {"type": "BUY", "txDate": None}
    out = compute_trade_alpha(trade, stock, spy)
    assert all(v is None for v in out.values())


def test_malformed_tx_date_returns_all_none():
    stock = _prices_df([(date(2024, 3, 4), 100.0)])
    spy = _prices_df([(date(2024, 3, 4), 500.0)])
    trade = {"type": "BUY", "txDate": "not-a-date"}
    out = compute_trade_alpha(trade, stock, spy)
    assert all(v is None for v in out.values())


def test_zero_entry_price_skips_horizon():
    # Entry price 0 short-circuits the horizon without blowing up the
    # division. Build a price series where entry is 0 and exit is real.
    stock = _prices_df([
        (date(2024, 3, 4), 0.0),
        (date(2024, 3, 5), 1.0),
        (date(2024, 3, 6), 2.0),
        (date(2024, 3, 7), 3.0),
        (date(2024, 3, 8), 4.0),
        (date(2024, 3, 11), 5.0),
    ])
    spy = _prices_df([
        (date(2024, 3, 4), 500.0),
        (date(2024, 3, 11), 500.0),
    ])
    trade = {"type": "BUY", "txDate": "2024-03-04"}
    out = compute_trade_alpha(trade, stock, spy)
    assert out["alpha_5d"] is None


def test_tx_date_before_price_history_returns_all_none():
    # Entry lookup fails → every horizon short-circuits.
    stock = _prices_df([(date(2024, 6, 1), 100.0), (date(2024, 6, 10), 105.0)])
    spy = _prices_df([(date(2024, 6, 1), 500.0), (date(2024, 6, 10), 500.0)])
    trade = {"type": "BUY", "txDate": "2024-06-15"}  # after last price
    out = compute_trade_alpha(trade, stock, spy)
    assert all(v is None for v in out.values())
