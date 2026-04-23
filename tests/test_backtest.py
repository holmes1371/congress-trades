"""
Unit tests for `scoring.backtest` — ROADMAP #5, under the shared
design note `design/postfile-alpha-and-backtest.md`.

Two slices of coverage:

  1. Calendar + filter helpers (`monthly_rebalance_dates`,
     `_trades_before`) — small, deterministic, cheap to exercise.

  2. Full `walk_forward` replay on the synthetic-member fixture
     (`tests/fixtures/backtest_synthetic_member.py`). The fixture is
     constructed so the expected outputs are hand-computable:
       * 1 synthetic member with 24 monthly BUYs at the first bday of
         each month (2022-01 through 2023-12).
       * SYNTH price ladder +$0.10 per bday, SPY flat at 500,
         NANC flat at 50.
       * Cohort selection with `min_trades=1` lets the member qualify
         after their first pre-D publication; `last_rebalance=2024-02-29`
         extends the rebalance series so every trade's publication
         falls inside an execution window.

Assertions verify the invariants the design note pins — n_trades,
structure of the JSON output, sign of alpha, equivalence of strategy
and naive-copy with a single-member universe — rather than snapshot
exact floats (which would over-couple the test to the synthetic price
arithmetic).
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from scoring.backtest import (
    _trades_before,
    monthly_rebalance_dates,
    walk_forward,
)
from scoring.score_members import attach_alphas
from tests.fixtures.backtest_synthetic_member import (
    NANC_PRICES,
    SPY_PRICES,
    SYNTH_MEMBER,
    SYNTH_PRICES,
    TRADE_DATES,
    make_prices_frame,
)


# ── Calendar helpers ────────────────────────────────────────


def test_monthly_rebalance_dates_are_month_end_bdays():
    dates = monthly_rebalance_dates(date(2022, 1, 1), date(2022, 12, 31))
    assert len(dates) == 12
    for d in dates:
        assert d.weekday() < 5, f"{d} is a weekend"
    # Month-end sanity: the next day should be in the following month
    # (or new year for December).
    for d in dates:
        # Walking forward any weekend days shouldn't cross into the
        # same month.
        m = d.month
        y = d.year
        # "Last bday of its month" property.
        import calendar
        last_dom = calendar.monthrange(y, m)[1]
        # d must be within the final 3 days of its month (covers weekend spillback).
        assert last_dom - d.day <= 3


def test_monthly_rebalance_dates_empty_on_short_span():
    # Span too short to contain any month-end.
    assert monthly_rebalance_dates(date(2022, 3, 2), date(2022, 3, 10)) == []


# ── Causal filter ───────────────────────────────────────────


def test_trades_before_strict_inequality():
    trades = [
        {"published": "2024-01-15"},
        {"published": "2024-01-31"},
        {"published": "2024-02-01"},  # equal to cutoff — excluded
        {"published": "2024-02-15"},
    ]
    pre = _trades_before(trades, date(2024, 2, 1))
    assert len(pre) == 2
    assert all(t["published"] < "2024-02-01" for t in pre)


def test_trades_before_drops_missing_or_malformed_published():
    trades = [
        {"published": "2024-01-15"},
        {"published": None},
        {"published": ""},
        {"published": "not-a-date"},
        {},
    ]
    pre = _trades_before(trades, date(2024, 6, 1))
    assert pre == [{"published": "2024-01-15"}]


# ── Full replay on synthetic fixture ───────────────────────


@pytest.fixture(scope="module")
def synthetic_world() -> dict:
    """Set up the synthetic universe: one member, price frames attached
    with post-file alphas, ready for walk_forward."""
    members_data = {SYNTH_MEMBER["bioguideId"]: dict(SYNTH_MEMBER)}
    # Normalize ticker on each trade (done in score_members.main() flow).
    for t in members_data[SYNTH_MEMBER["bioguideId"]]["trades"]:
        t["ticker"] = (t.get("ticker") or "").upper()
    price_frames = {
        "SYNTH": make_prices_frame(SYNTH_PRICES),
        "SPY":   make_prices_frame(SPY_PRICES),
        "NANC":  make_prices_frame(NANC_PRICES),
    }
    spy = price_frames["SPY"]
    attach_alphas(members_data, price_frames, spy)
    return {
        "members_data": members_data,
        "price_frames": price_frames,
        "spy":          spy,
        "nanc":         price_frames["NANC"],
    }


def test_walk_forward_returns_expected_shape(synthetic_world):
    result = walk_forward(
        synthetic_world["members_data"],
        synthetic_world["price_frames"],
        synthetic_world["spy"],
        nanc=synthetic_world["nanc"],
        K=15,
        exit_bdays=60,
        min_trades=1,
        last_rebalance=date(2024, 2, 29),
    )
    assert set(result.keys()) == {"generated", "params", "rebalances", "summary"}
    assert "strategy" in result["summary"]
    assert "naive_copy_everyone" in result["summary"]
    assert "SPY" in result["summary"]
    assert "NANC" in result["summary"]
    assert result["params"]["K"] == 15
    assert result["params"]["exit_bdays"] == 60


def test_walk_forward_executes_every_synthetic_trade(synthetic_world):
    """All 24 monthly BUYs should fall into exactly one execution window
    once last_rebalance is pushed out to 2024-02-29 — the Dec-2023
    trade's publication (Dec-31) needs a post-window rebalance to
    clear."""
    result = walk_forward(
        synthetic_world["members_data"],
        synthetic_world["price_frames"],
        synthetic_world["spy"],
        nanc=synthetic_world["nanc"],
        K=15,
        exit_bdays=60,
        min_trades=1,
        last_rebalance=date(2024, 2, 29),
    )
    assert result["summary"]["strategy"]["n_trades"] == len(TRADE_DATES)
    assert result["summary"]["strategy"]["n_trades"] == 24


def test_walk_forward_every_synthetic_trade_positive_alpha(synthetic_world):
    """SYNTH is a strictly-rising ladder; SPY flat; every 60-bday hold
    must produce positive alpha_vs_spy."""
    result = walk_forward(
        synthetic_world["members_data"],
        synthetic_world["price_frames"],
        synthetic_world["spy"],
        nanc=synthetic_world["nanc"],
        K=15,
        exit_bdays=60,
        min_trades=1,
        last_rebalance=date(2024, 2, 29),
    )
    all_trades = [
        tr for reb in result["rebalances"] for tr in reb["trades"]
    ]
    assert len(all_trades) == 24
    for tr in all_trades:
        assert tr["alpha_vs_spy"] > 0, (
            f"expected positive alpha on rising-ladder fixture, got {tr}"
        )
    assert result["summary"]["strategy"]["hit_rate"] == pytest.approx(1.0)


def test_walk_forward_single_member_strategy_equals_naive(synthetic_world):
    """With one member in the universe, cohort == every-member. The
    strategy trade set and the naive_copy_everyone trade set must match
    in count and alpha; alpha_vs_naive_copy_everyone ≈ 0."""
    result = walk_forward(
        synthetic_world["members_data"],
        synthetic_world["price_frames"],
        synthetic_world["spy"],
        nanc=synthetic_world["nanc"],
        K=15,
        exit_bdays=60,
        min_trades=1,
        last_rebalance=date(2024, 2, 29),
    )
    s = result["summary"]["strategy"]
    n = result["summary"]["naive_copy_everyone"]
    assert s["n_trades"] == n["n_trades"]
    assert s["alpha_vs_naive_copy_everyone"] == pytest.approx(0.0, abs=1e-12)


def test_walk_forward_benchmark_total_returns_match_flat_fixtures(synthetic_world):
    """SPY flat at 500 → total_return == 0. NANC flat at 50 → 0."""
    result = walk_forward(
        synthetic_world["members_data"],
        synthetic_world["price_frames"],
        synthetic_world["spy"],
        nanc=synthetic_world["nanc"],
        K=15,
        exit_bdays=60,
        min_trades=1,
        last_rebalance=date(2024, 2, 29),
    )
    assert result["summary"]["SPY"]["total_return"] == pytest.approx(0.0)
    assert result["summary"]["NANC"]["total_return"] == pytest.approx(0.0)


def test_walk_forward_first_trade_executes_on_first_bday_after_feb_end_2022(
    synthetic_world,
):
    """The Jan-3-2022 synthetic trade publishes 2022-02-02. The first
    monthly rebalance ≥ Feb 2 is Feb 28, 2022 (Mon, last bday of Feb).
    Entry = D + 1 business day forward-filled → Mar 1, 2022."""
    result = walk_forward(
        synthetic_world["members_data"],
        synthetic_world["price_frames"],
        synthetic_world["spy"],
        nanc=synthetic_world["nanc"],
        K=15,
        exit_bdays=60,
        min_trades=1,
        last_rebalance=date(2024, 2, 29),
    )
    first_rebalance = result["rebalances"][0]
    assert first_rebalance["date"] == "2022-02-28"
    assert len(first_rebalance["trades"]) == 1
    assert first_rebalance["trades"][0]["entry_date"] == "2022-03-01"


def test_walk_forward_no_qualifiers_returns_empty_cohort(synthetic_world):
    """With `min_trades` raised above the synthetic member's eventual
    trade count, no rebalance produces a qualified cohort; n_trades == 0,
    summary still populated with the null-path defaults."""
    result = walk_forward(
        synthetic_world["members_data"],
        synthetic_world["price_frames"],
        synthetic_world["spy"],
        nanc=synthetic_world["nanc"],
        K=15,
        exit_bdays=60,
        min_trades=999,
        last_rebalance=date(2024, 2, 29),
    )
    assert result["summary"]["strategy"]["n_trades"] == 0
    assert result["summary"]["strategy"]["hit_rate"] is None
    assert all(len(r["trades"]) == 0 for r in result["rebalances"])


# ── Overlays (ROADMAP #7) ───────────────────────────────────


def test_walk_forward_summary_gains_net_fields(synthetic_world):
    """summary.strategy gains net-of-overlay fields + an overlays dict;
    summary.naive_copy_everyone gains its own net total."""
    result = walk_forward(
        synthetic_world["members_data"],
        synthetic_world["price_frames"],
        synthetic_world["spy"],
        nanc=synthetic_world["nanc"],
        K=15, exit_bdays=60, min_trades=1,
        last_rebalance=date(2024, 2, 29),
    )
    s = result["summary"]["strategy"]
    for k in (
        "total_return_net", "alpha_vs_spy_net", "alpha_vs_nanc_net",
        "alpha_vs_naive_copy_everyone_net", "hit_rate_net", "overlays",
    ):
        assert k in s, f"missing net key {k!r} in summary.strategy"
    assert "total_return_net" in result["summary"]["naive_copy_everyone"]


def test_walk_forward_overlays_off_match_gross(synthetic_world):
    """slippage_mode='off' + tax_rate=0 → every *_net field equals its
    gross counterpart under equal-weight sizing."""
    result = walk_forward(
        synthetic_world["members_data"],
        synthetic_world["price_frames"],
        synthetic_world["spy"],
        nanc=synthetic_world["nanc"],
        K=15, exit_bdays=60, min_trades=1,
        last_rebalance=date(2024, 2, 29),
        slippage_mode="off", tax_rate=0.0, sizing_mode="equal",
    )
    s = result["summary"]["strategy"]
    assert s["total_return_net"] == pytest.approx(s["total_return"])
    assert s["alpha_vs_spy_net"] == pytest.approx(s["alpha_vs_spy"])
    assert s["alpha_vs_naive_copy_everyone_net"] == pytest.approx(
        s["alpha_vs_naive_copy_everyone"], abs=1e-12
    )
    assert s["hit_rate_net"] == pytest.approx(s["hit_rate"])


def test_walk_forward_flat_slippage_reduces_net_by_exact_bps(synthetic_world):
    """With flat_bps:100 (= 1% round-trip) and tax off, every trade's
    net stock return is gross - 0.01; the summary total reflects that
    exactly on the equal-weight fixture."""
    result = walk_forward(
        synthetic_world["members_data"],
        synthetic_world["price_frames"],
        synthetic_world["spy"],
        nanc=synthetic_world["nanc"],
        K=15, exit_bdays=60, min_trades=1,
        last_rebalance=date(2024, 2, 29),
        slippage_mode="flat_bps:100", tax_rate=0.0, sizing_mode="equal",
    )
    s = result["summary"]["strategy"]
    assert s["total_return_net"] == pytest.approx(s["total_return"] - 0.01)
    assert s["alpha_vs_spy_net"] == pytest.approx(s["alpha_vs_spy"] - 0.01)


def test_walk_forward_tax_haircut_on_all_gains(synthetic_world):
    """SYNTH ladder → every trade is a gain → tax haircut scales
    total_return_net by (1 - rate) when slippage is off."""
    rate = 0.5
    result = walk_forward(
        synthetic_world["members_data"],
        synthetic_world["price_frames"],
        synthetic_world["spy"],
        nanc=synthetic_world["nanc"],
        K=15, exit_bdays=60, min_trades=1,
        last_rebalance=date(2024, 2, 29),
        slippage_mode="off", tax_rate=rate, sizing_mode="equal",
    )
    s = result["summary"]["strategy"]
    assert s["total_return_net"] == pytest.approx(s["total_return"] * (1 - rate))


def test_walk_forward_overlays_config_captured(synthetic_world):
    """summary.strategy.overlays mirrors the kwargs passed in, and
    slippage_bps_by_ticker covers every ticker that executed."""
    result = walk_forward(
        synthetic_world["members_data"],
        synthetic_world["price_frames"],
        synthetic_world["spy"],
        nanc=synthetic_world["nanc"],
        K=15, exit_bdays=60, min_trades=1,
        last_rebalance=date(2024, 2, 29),
        slippage_mode="tiered", tax_rate=0.2975, sizing_mode="equal",
    )
    o = result["summary"]["strategy"]["overlays"]
    assert o["slippage_mode"] == "tiered"
    assert o["tax_rate"] == pytest.approx(0.2975)
    assert o["sizing_mode"] == "equal"
    executed_tickers = {
        tr["ticker"] for reb in result["rebalances"] for tr in reb["trades"]
    }
    assert set(o["slippage_bps_by_ticker"].keys()) == executed_tickers
