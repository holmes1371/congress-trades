"""
Unit + integration tests for `scoring.paper_log` — ROADMAP #6, under
`design/paper-log.md`.

Four slices:

  1. PaperLog I/O — load empty file, write round-trips, headers pinned.
  2. PaperLog mutations — open_position / close_position /
     mark_to_market / has_trade semantics against hand-crafted rows.
  3. Full `walk` integration on the synthetic-member fixture
     (`tests/fixtures/backtest_synthetic_member.py`). Tests drive the
     loop across multiple simulated pipeline-run dates with a fixed
     `now=` so the `last_updated` column is deterministic.
  4. Retraction handling — `make_retractor_member()` emits a single
     Feb-2022 BUY by default and `make_retractor_member(retracted=True)`
     drops it, simulating a capitoltrades disclosure correction between
     runs. Tests drive the full detect/apply/persist path.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from scoring.paper_log import CSV_HEADERS, PaperLog
from scoring.score_members import attach_alphas
from tests.fixtures.backtest_synthetic_member import (
    RETRACTOR_BIOGUIDE,
    RETRACTOR_TXID,
    SPY_PRICES,
    SYNTH_MEMBER,
    SYNTH_PRICES,
    TRADE_DATES,
    make_prices_frame,
    make_retractor_member,
)


_NOW = datetime(2024, 1, 15, 12, 0, 0)  # deterministic for last_updated assertions


# ── I/O ─────────────────────────────────────────────────────


def test_empty_log_has_no_rows(tmp_path):
    log = PaperLog(tmp_path / "empty.csv")
    assert log.rows == []
    assert log.open_rows() == []
    assert log.closed_rows() == []


def test_save_writes_headers_and_loads_back(tmp_path):
    log = PaperLog(tmp_path / "positions.csv")
    log.open_position(
        bioguide="TEST0", tx_id=12345, ticker="AAPL",
        signal_date=date(2024, 1, 2), open_date=date(2024, 1, 5),
        entry_date=date(2024, 1, 8), entry_close=150.25,
        target_exit_date=date(2024, 4, 1), now=_NOW,
    )
    log.save()

    reloaded = PaperLog(tmp_path / "positions.csv")
    assert len(reloaded.rows) == 1
    row = reloaded.rows[0]
    assert row["bioguide"] == "TEST0"
    assert row["tx_id"] == "12345"
    assert row["ticker"] == "AAPL"
    assert row["entry_close"] == "150.2500"
    assert row["status"] == "open"
    assert row["last_updated"] == "2024-01-15T12:00:00"
    assert set(row.keys()) == set(CSV_HEADERS)


def test_csv_header_row_matches_canonical_list(tmp_path):
    """The canonical CSV_HEADERS ordering is pinned — any schema
    change should reshape the fixture file intentionally, not by
    accident."""
    log = PaperLog(tmp_path / "positions.csv")
    log.save()
    first_line = (tmp_path / "positions.csv").read_text(encoding="utf-8").splitlines()[0]
    assert first_line == ",".join(CSV_HEADERS)


# ── Mutations ───────────────────────────────────────────────


def _sample_open(log, **overrides):
    defaults = dict(
        bioguide="M0", tx_id=1, ticker="AAPL",
        signal_date=date(2024, 1, 2), open_date=date(2024, 1, 5),
        entry_date=date(2024, 1, 8), entry_close=100.0,
        target_exit_date=date(2024, 4, 1), now=_NOW,
    )
    defaults.update(overrides)
    return log.open_position(**defaults)


def test_open_position_populates_all_fields(tmp_path):
    log = PaperLog(tmp_path / "log.csv")
    row = _sample_open(log)
    assert row["position_id"] == "M0-1"
    assert row["status"] == "open"
    assert row["pnl_abs"] == "0.0000"
    assert row["pnl_pct"] == "0.000000"
    assert row["exit_date"] == ""
    assert row["retracted_at"] == ""


def test_has_trade_identifies_logged_row(tmp_path):
    log = PaperLog(tmp_path / "log.csv")
    _sample_open(log, bioguide="M1", tx_id=42)
    assert log.has_trade("M1", 42)
    assert log.has_trade("M1", "42")  # string tx_id also matches
    assert not log.has_trade("M1", 99)
    assert not log.has_trade("M2", 42)


def test_close_position_transitions_to_closed_with_realized_pnl(tmp_path):
    log = PaperLog(tmp_path / "log.csv")
    row = _sample_open(log, entry_close=100.0)
    log.close_position(
        row["position_id"],
        exit_date=date(2024, 4, 1), exit_close=110.0,
        alpha_vs_spy=0.08, now=_NOW,
    )
    closed = log.rows[0]
    assert closed["status"] == "closed"
    assert closed["exit_close"] == "110.0000"
    assert closed["pnl_abs"] == "10.0000"
    assert closed["pnl_pct"] == "0.100000"
    assert closed["alpha_vs_spy"] == "0.080000"


def test_close_position_no_op_on_missing_or_already_closed(tmp_path):
    log = PaperLog(tmp_path / "log.csv")
    row = _sample_open(log)
    log.close_position(
        row["position_id"],
        exit_date=date(2024, 4, 1), exit_close=110.0,
        alpha_vs_spy=0.08, now=_NOW,
    )
    # Second close: no change.
    log.close_position(
        row["position_id"],
        exit_date=date(2024, 5, 1), exit_close=150.0,
        alpha_vs_spy=0.30, now=_NOW,
    )
    assert log.rows[0]["exit_date"] == "2024-04-01"
    # Missing position_id: silent no-op.
    log.close_position(
        "NOPE-999",
        exit_date=date(2024, 5, 1), exit_close=150.0,
        alpha_vs_spy=0.30, now=_NOW,
    )
    assert len(log.rows) == 1


def test_mark_to_market_updates_only_open_rows(tmp_path):
    log = PaperLog(tmp_path / "log.csv")
    open_row = _sample_open(log, bioguide="M0", tx_id=1, ticker="TKR", entry_close=100.0)
    closed_row = _sample_open(log, bioguide="M1", tx_id=2, ticker="TKR", entry_close=50.0)
    log.close_position(
        closed_row["position_id"],
        exit_date=date(2024, 3, 1), exit_close=55.0,
        alpha_vs_spy=0.10, now=_NOW,
    )

    prices = pd.DataFrame(
        {"close": [100.0, 105.0, 108.0], "volume": [1e9, 1e9, 1e9]},
        index=pd.DatetimeIndex([date(2024, 1, 8), date(2024, 2, 1), date(2024, 2, 15)]),
    )
    log.mark_to_market({"TKR": prices}, today=date(2024, 2, 15), now=_NOW)

    # Open row picks up mark-to-market from 2024-02-15 close.
    assert log.rows[0]["pnl_abs"] == "8.0000"
    assert log.rows[0]["pnl_pct"] == "0.080000"
    # Closed row left alone (retains realized PnL).
    assert log.rows[1]["status"] == "closed"
    assert log.rows[1]["pnl_abs"] == "5.0000"


def test_mark_to_market_skips_rows_with_no_price_data(tmp_path):
    log = PaperLog(tmp_path / "log.csv")
    _sample_open(log, ticker="MISSING")
    prices = pd.DataFrame(
        {"close": [100.0], "volume": [1e9]},
        index=pd.DatetimeIndex([date(2024, 1, 8)]),
    )
    log.mark_to_market({"OTHER": prices}, today=date(2024, 2, 15), now=_NOW)
    # Row untouched (pnl stayed at 0 — no price data to mark against).
    assert log.rows[0]["pnl_abs"] == "0.0000"


# ── Full walk integration on the synthetic fixture ─────────


@pytest.fixture(scope="module")
def synthetic_world() -> dict:
    """Shared setup: one synthetic member, price frames, post-file
    alphas attached. Matches the fixture test_backtest.py uses, so
    `walk` and `walk_forward` see identical inputs."""
    members_data = {SYNTH_MEMBER["bioguideId"]: {
        **SYNTH_MEMBER,
        "trades": [dict(t) for t in SYNTH_MEMBER["trades"]],
    }}
    for t in members_data[SYNTH_MEMBER["bioguideId"]]["trades"]:
        t["ticker"] = (t.get("ticker") or "").upper()
    price_frames = {
        "SYNTH": make_prices_frame(SYNTH_PRICES),
        "SPY":   make_prices_frame(SPY_PRICES),
    }
    attach_alphas(members_data, price_frames, price_frames["SPY"])
    return {
        "members_data": members_data,
        "price_frames": price_frames,
        "spy":          price_frames["SPY"],
    }


def _walk_at(log, world, today, min_trades=1):
    """Wrapper: invoke log.walk with the shared synthetic world and
    `min_trades=1` so the single synthetic member qualifies after
    their first pre-today publication."""
    log.walk(
        members_data=world["members_data"],
        price_frames=world["price_frames"],
        spy=world["spy"],
        today=today,
        min_trades=min_trades,
        now=_NOW,
    )


def test_walk_opens_first_synthetic_buy_after_its_publication(
    synthetic_world, tmp_path
):
    """Jan-3-2022 trade publishes Feb-2-2022. Walk at Feb-28-2022
    should see it and open a position on the next available close
    (Mar-1-2022 per the pd.bdate_range fixture calendar)."""
    log = PaperLog(tmp_path / "log.csv")
    _walk_at(log, synthetic_world, today=date(2022, 2, 28))
    assert len(log.open_rows()) == 1
    row = log.rows[0]
    assert row["bioguide"] == "SYNTH0"
    assert row["ticker"] == "SYNTH"
    assert row["signal_date"] == "2022-02-02"
    assert row["open_date"] == "2022-02-28"
    assert row["entry_date"] == "2022-03-01"


def test_walk_is_idempotent_same_day(synthetic_world, tmp_path):
    """Re-running walk with the same today must not duplicate open
    positions — has_trade short-circuits."""
    log = PaperLog(tmp_path / "log.csv")
    _walk_at(log, synthetic_world, today=date(2022, 2, 28))
    first_count = len(log.rows)
    _walk_at(log, synthetic_world, today=date(2022, 2, 28))
    assert len(log.rows) == first_count


def test_walk_closes_positions_whose_horizon_elapsed(
    synthetic_world, tmp_path
):
    """Walk through a date range where the first position's 60-bday
    horizon passes. Position should transition to 'closed' with
    realized PnL and an alpha_vs_spy populated (flat SPY → alpha
    equals stock return)."""
    log = PaperLog(tmp_path / "log.csv")
    _walk_at(log, synthetic_world, today=date(2022, 2, 28))
    first_row = log.rows[0]
    target_exit = date.fromisoformat(first_row["target_exit_date"])

    # Advance to a date well past target_exit.
    _walk_at(log, synthetic_world, today=target_exit)
    updated = log._find_by_id(first_row["position_id"])
    assert updated["status"] == "closed"
    # SPY flat → alpha_vs_spy equals raw stock return.
    assert float(updated["alpha_vs_spy"]) == pytest.approx(
        float(updated["pnl_pct"]), abs=1e-9
    )
    assert float(updated["pnl_abs"]) > 0   # rising ladder → positive PnL


def test_walk_accumulates_across_multiple_months(synthetic_world, tmp_path):
    """Simulate a year of monthly pipeline runs. Each run should open
    one new position (the month's previously-published BUY) and
    eventually close the earliest-opened ones as their 60-bday
    horizons elapse."""
    log = PaperLog(tmp_path / "log.csv")
    # Run on the last day of each month from Feb-2022 through Dec-2022.
    run_dates = [
        date(2022, 2, 28), date(2022, 3, 31), date(2022, 4, 29),
        date(2022, 5, 31), date(2022, 6, 30), date(2022, 7, 29),
        date(2022, 8, 31), date(2022, 9, 30), date(2022, 10, 31),
        date(2022, 11, 30), date(2022, 12, 30),
    ]
    for d in run_dates:
        _walk_at(log, synthetic_world, today=d)

    # 11 pipeline runs, 11 published trades visible (Jan-Nov 2022
    # each publish 30 days after the first bday of their month;
    # Dec-2022's publication is 2023-01-02 which hasn't happened yet).
    assert len(log.rows) == 11

    # Some of the earliest positions should have closed by now.
    assert len(log.closed_rows()) > 0
    # All open positions have entry_close > 0.
    for row in log.open_rows():
        assert float(row["entry_close"]) > 0

    # Every closed position had a positive return (rising ladder, flat SPY).
    for row in log.closed_rows():
        assert float(row["pnl_pct"]) > 0
        assert float(row["alpha_vs_spy"]) > 0


def _world_with_retractor(retracted: bool) -> dict:
    """Synthetic world carrying both SYNTH_MEMBER and a retractor
    member (with or without the retracted trade present). Share
    price frames / post-file alphas across the two members."""
    members_data = {
        SYNTH_MEMBER["bioguideId"]: {
            **SYNTH_MEMBER,
            "trades": [dict(t) for t in SYNTH_MEMBER["trades"]],
        },
    }
    for t in members_data[SYNTH_MEMBER["bioguideId"]]["trades"]:
        t["ticker"] = (t.get("ticker") or "").upper()

    retractor = make_retractor_member(retracted=retracted)
    retractor["trades"] = [dict(t) for t in retractor["trades"]]
    for t in retractor["trades"]:
        t["ticker"] = (t.get("ticker") or "").upper()
    members_data[RETRACTOR_BIOGUIDE] = retractor

    price_frames = {
        "SYNTH": make_prices_frame(SYNTH_PRICES),
        "SPY":   make_prices_frame(SPY_PRICES),
    }
    attach_alphas(members_data, price_frames, price_frames["SPY"])
    return {
        "members_data": members_data,
        "price_frames": price_frames,
        "spy":          price_frames["SPY"],
    }


def test_walk_detects_retraction_between_runs(tmp_path):
    """Run 1 sees RETRACTOR_TXID and opens the position. Between runs
    the trade vanishes from capitoltrades. Run 2 detects this and
    flips the row to status=retracted with retracted_at stamped."""
    log = PaperLog(tmp_path / "log.csv")
    # Run 1 at Mar 31 2022: Feb trade published Mar 3, opens here.
    _walk_at(log, _world_with_retractor(retracted=False), today=date(2022, 3, 31))
    row = next(r for r in log.rows if r["bioguide"] == RETRACTOR_BIOGUIDE)
    assert row["status"] == "open"

    # Run 2 at Apr 29 2022: retractor trade is gone; position retracts.
    _walk_at(log, _world_with_retractor(retracted=True), today=date(2022, 4, 29))
    row = next(r for r in log.rows if r["bioguide"] == RETRACTOR_BIOGUIDE)
    assert row["status"] == "retracted"
    assert row["retracted_at"] == "2022-04-29"
    # Row is still present — retraction is a status flip, not a delete.
    assert row["tx_id"] == str(RETRACTOR_TXID)
    assert row["entry_close"] != ""  # entry data preserved


def test_retracted_row_skipped_by_mark_to_market(tmp_path):
    """After retraction, subsequent pipeline runs must not bump the
    retracted row's pnl_abs/pnl_pct — it's frozen at the last mark."""
    log = PaperLog(tmp_path / "log.csv")
    _walk_at(log, _world_with_retractor(retracted=False), today=date(2022, 3, 31))
    # Capture pre-retraction pnl (may have been mark-to-marketed at this point).
    row_before = next(r for r in log.rows if r["bioguide"] == RETRACTOR_BIOGUIDE)
    pnl_before_retraction_open = row_before["pnl_abs"]

    _walk_at(log, _world_with_retractor(retracted=True), today=date(2022, 4, 29))
    row_after_retraction = next(r for r in log.rows if r["bioguide"] == RETRACTOR_BIOGUIDE)
    pnl_at_retraction = row_after_retraction["pnl_abs"]

    # Subsequent walk: pnl must not change (retracted rows skip mark_to_market).
    _walk_at(log, _world_with_retractor(retracted=True), today=date(2022, 5, 31))
    row_later = next(r for r in log.rows if r["bioguide"] == RETRACTOR_BIOGUIDE)
    assert row_later["status"] == "retracted"
    assert row_later["pnl_abs"] == pnl_at_retraction


def test_retraction_does_not_reopen_same_tx_id(tmp_path):
    """If the retracted trade reappears in capitoltrades on a later
    run (paranoid case), `has_trade` still matches the retracted row
    and the position does not re-open."""
    log = PaperLog(tmp_path / "log.csv")
    _walk_at(log, _world_with_retractor(retracted=False), today=date(2022, 3, 31))
    _walk_at(log, _world_with_retractor(retracted=True), today=date(2022, 4, 29))

    # Trade reappears after retraction.
    _walk_at(log, _world_with_retractor(retracted=False), today=date(2022, 5, 31))
    retractor_rows = [r for r in log.rows if r["bioguide"] == RETRACTOR_BIOGUIDE]
    assert len(retractor_rows) == 1  # no duplicate open
    assert retractor_rows[0]["status"] == "retracted"  # still retracted


def test_detect_retractions_skips_members_missing_from_data(tmp_path):
    """If a member drops out of members_data entirely (e.g. just
    not fetched this run), their open positions must not be marked
    retracted — absence-from-data isn't retraction."""
    log = PaperLog(tmp_path / "log.csv")
    # Open a position from the full world.
    _walk_at(log, _world_with_retractor(retracted=False), today=date(2022, 3, 31))
    row = next(r for r in log.rows if r["bioguide"] == RETRACTOR_BIOGUIDE)
    assert row["status"] == "open"

    # Build a world where the retractor member is entirely absent.
    world = _world_with_retractor(retracted=False)
    del world["members_data"][RETRACTOR_BIOGUIDE]

    retracted_ids = log.detect_retractions(world["members_data"])
    assert row["position_id"] not in retracted_ids


def test_apply_retraction_no_op_on_closed_position(tmp_path):
    """Once a position has closed with realized PnL, retraction must
    not rewrite it — close-first semantics."""
    log = PaperLog(tmp_path / "log.csv")
    row = _sample_open(log, bioguide="M0", tx_id=1, ticker="TKR", entry_close=100.0)
    log.close_position(
        row["position_id"],
        exit_date=date(2024, 3, 1), exit_close=110.0, alpha_vs_spy=0.10, now=_NOW,
    )
    log.apply_retraction(row["position_id"], retracted_at=date(2024, 3, 15), now=_NOW)
    assert log.rows[0]["status"] == "closed"
    assert log.rows[0]["retracted_at"] == ""


def test_walk_persists_across_reloads(synthetic_world, tmp_path):
    """Save + reload preserves every row and its status; second walk
    on the reloaded log does not re-open already-tracked trades."""
    path = tmp_path / "persist.csv"
    log = PaperLog(path)
    _walk_at(log, synthetic_world, today=date(2022, 2, 28))
    _walk_at(log, synthetic_world, today=date(2022, 3, 31))
    log.save()
    rows_before = len(log.rows)

    reloaded = PaperLog(path)
    assert len(reloaded.rows) == rows_before
    _walk_at(reloaded, synthetic_world, today=date(2022, 3, 31))  # same day
    assert len(reloaded.rows) == rows_before  # idempotent across save/reload
