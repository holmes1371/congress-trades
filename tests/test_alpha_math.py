"""
Tests for `scoring.factors.compute_trade_alpha` and
`scoring.factors.compute_trade_alpha_postfile`.

Three slices of coverage:

  1. Parametrized trade-date alpha against the hand-crafted scenarios
     in `tests/fixtures/synthetic_alpha_scenarios.py`. Each scenario
     pins a `trade_date → exit_date` span with known prices and a
     known expected alpha vs a flat benchmark.

  2. Parametrized post-file alpha against the same scenarios, using
     the `expected_alpha_post_file_approx` expectation and the
     extended price series that span through
     `publication_date + BDay(2)` entry + 5-bday exit. Entry rule
     (`max(txDate, published) + BDay(ENTRY_BUFFER_BDAYS)`) is pinned
     by ROADMAP #4's shared design note
     (`design/postfile-alpha-and-backtest.md`).

  3. Property tests for the early-exit paths that the scenarios don't
     cover: non-BUY trades, missing or malformed txDate / published,
     zero entry price, trade date before the price history.

Note on horizons. Both functions return all three of
`alpha_{5,20,60}d` (or `alpha_postfile_{5,20,60}d`) at once. The
fixture declares `horizon_bdays` so the tests can pick the matching
column; for horizons the fixture's price series doesn't extend to,
the function returns `None` and the test just skips the assertion for
that horizon.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from scoring.factors import (
    ALPHA_HORIZONS,
    compute_trade_alpha,
    compute_trade_alpha_postfile,
)


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


# ── Post-file alpha ──────────────────────────────────────────────


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
def test_synthetic_scenario_post_file_alpha(
    synthetic_alpha_scenarios, scenario_name
):
    scenario = next(s for s in synthetic_alpha_scenarios if s["name"] == scenario_name)
    stock = _prices_df(scenario["ticker_prices"])
    spy = _prices_df(scenario["benchmark_prices"])

    trade = {
        "type": "BUY",
        "txDate": scenario["trade_date"].isoformat(),
        "published": scenario["publication_date"].isoformat(),
    }
    out = compute_trade_alpha_postfile(trade, stock, spy)

    horizon = scenario["horizon_bdays"]
    assert horizon in ALPHA_HORIZONS, (
        f"scenario {scenario_name} has horizon {horizon} not in ALPHA_HORIZONS; "
        f"synthetic fixture drifted from code"
    )

    expected = scenario.get("expected_alpha_post_file_approx")
    assert expected is not None, (
        f"scenario {scenario_name} missing expected_alpha_post_file_approx"
    )

    got = out[f"alpha_postfile_{horizon}d"]
    assert got is not None, (
        f"alpha_postfile_{horizon}d should be computable for {scenario_name}"
    )
    assert got == pytest.approx(expected, abs=0.01)


def test_post_file_missing_published_returns_all_none():
    # Without a publication date we cannot characterize the follower
    # path; returning None beats silently falling back to txDate and
    # re-introducing the trade-date confound.
    stock = _prices_df([(date(2024, 3, 4), 100.0), (date(2024, 3, 20), 100.0)])
    spy = _prices_df([(date(2024, 3, 4), 500.0), (date(2024, 3, 20), 500.0)])
    trade = {"type": "BUY", "txDate": "2024-03-04"}
    out = compute_trade_alpha_postfile(trade, stock, spy)
    assert all(v is None for v in out.values())


def test_post_file_malformed_published_returns_all_none():
    stock = _prices_df([(date(2024, 3, 4), 100.0), (date(2024, 3, 20), 100.0)])
    spy = _prices_df([(date(2024, 3, 4), 500.0), (date(2024, 3, 20), 500.0)])
    trade = {"type": "BUY", "txDate": "2024-03-04", "published": "not-a-date"}
    out = compute_trade_alpha_postfile(trade, stock, spy)
    assert all(v is None for v in out.values())


def test_post_file_non_buy_returns_all_none():
    stock = _prices_df([(date(2024, 3, 4), 100.0), (date(2024, 3, 20), 100.0)])
    spy = _prices_df([(date(2024, 3, 4), 500.0), (date(2024, 3, 20), 500.0)])
    trade = {"type": "SELL", "txDate": "2024-03-04", "published": "2024-03-18"}
    out = compute_trade_alpha_postfile(trade, stock, spy)
    assert all(v is None for v in out.values())


def test_post_file_missing_tx_date_returns_all_none():
    stock = _prices_df([(date(2024, 3, 4), 100.0), (date(2024, 3, 20), 100.0)])
    spy = _prices_df([(date(2024, 3, 4), 500.0), (date(2024, 3, 20), 500.0)])
    trade = {"type": "BUY", "txDate": None, "published": "2024-03-18"}
    out = compute_trade_alpha_postfile(trade, stock, spy)
    assert all(v is None for v in out.values())


def test_post_file_anchor_is_max_of_tx_and_published():
    # When txDate > published (deterministic edge case), entry anchors
    # on txDate + BDay(2) via max(tx, pub). Synthetic: txDate 2024-03-18,
    # published 2024-01-01 → anchor = 2024-03-18 → target entry 2024-03-20.
    prices = [
        (date(2024, 3, 18), 100.0),
        (date(2024, 3, 19), 100.0),
        (date(2024, 3, 20), 100.0),  # entry (anchor + BDay(2))
        (date(2024, 3, 21), 101.0),
        (date(2024, 3, 22), 102.0),
        (date(2024, 3, 25), 103.0),
        (date(2024, 3, 26), 104.0),
        (date(2024, 3, 27), 105.0),  # exit (entry + 5 bdays)
    ]
    stock = _prices_df(prices)
    spy = _prices_df([(d, 500.0) for d, _ in prices])
    trade = {"type": "BUY", "txDate": "2024-03-18", "published": "2024-01-01"}
    out = compute_trade_alpha_postfile(trade, stock, spy)
    assert out["alpha_postfile_5d"] == pytest.approx(0.05, abs=0.001)
