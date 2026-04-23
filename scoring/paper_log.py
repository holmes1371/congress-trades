"""
paper_log.py — auto paper-trading log (ROADMAP #6)
===================================================

Append-only CSV ledger that records what a follower would have done
at every pipeline run, tracking PnL as positions close. The live
continuation of the #5 walk-forward backtest — same cohort selector,
same entry / exit mechanic, different tense.

## Ledger semantics

One row per position at `scoring/paper_log/positions.csv`.
Append-only except for mark-to-market / close / retraction updates
on existing rows. Identity key: `(bioguide, tx_id)`. Schema per
`design/paper-log.md` — see `CSV_HEADERS` below.

## Walk loop

Each pipeline run calls `PaperLog.walk(..., today=...)`:

1. **Close** every open position whose `target_exit_date <= today`
   using the next-available close on or after the target.
2. **Mark-to-market** remaining open positions with the latest close
   up to and including `today`.
3. **Compute cohort** as of `today` via
   `scoring.backtest.select_cohort` — top-K by composite on the
   trailing 365-day window.
4. **Open** a new position for every BUY from a cohort member whose
   `(bioguide, tx_id)` is not already in the ledger. Entry = first
   available close on or after `today + 1 calendar day`, matching
   the "D+1 close" convention from the #5 backtest. The +1 exists
   because the pipeline runs after market close — today's close is
   historical by run-time; the earliest close a follower can still
   execute against is the next trading day's.

Idempotent within a day: re-running with the same `today` opens no
new positions (has_trade returns True for everything already in the
ledger) and only refreshes mark-to-market rows.

## Persistence

CSV chosen for diff-friendliness in git — each pipeline run's
additions show up as a visible commit diff. The file lives under
version control; real-world runs append to it, tests construct
throwaway `PaperLog(path=tmp_path/"positions.csv")` instances.

## Retraction

Detection / handling lands in commit 3 under this ROADMAP item.
For this commit, the module provides the open / close / mark-to-market
surface; `status` enum accommodates `retracted` in advance, but
`walk` does not yet look for disappeared `tx_id`s.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from factors import MIN_TRADES_QUALIFY, compute_ticker_adv
from backtest import (
    close_at_or_after,
    close_n_positions_later,
    select_cohort,
)


LOG_DIR = Path(__file__).parent / "paper_log"
LOG_PATH = LOG_DIR / "positions.csv"

HORIZON_BDAYS = 60          # match #5 backtest exit rule
COHORT_K = 15               # match default_follow_*.json top-N
WINDOW_DAYS_DEFAULT = 365   # trailing window for composite at cohort-selection time


CSV_HEADERS = [
    "position_id", "bioguide", "tx_id", "ticker",
    "signal_date", "open_date", "entry_date", "entry_close",
    "target_exit_date", "exit_date", "exit_close",
    "status", "pnl_abs", "pnl_pct", "alpha_vs_spy",
    "retracted_at", "last_updated",
]


def _position_id(bioguide: str, tx_id: Any) -> str:
    """Deterministic identity key. Survives status changes; makes
    tests reproducible without a uuid.uuid4 factory seam."""
    return f"{bioguide}-{tx_id}"


def _fmt_float(x: float, decimals: int = 4) -> str:
    return f"{x:.{decimals}f}"


class PaperLog:
    """In-memory view over the CSV ledger at
    `scoring/paper_log/positions.csv`. Tests construct with a custom
    `path` to get a throwaway ledger."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else LOG_PATH
        self.rows: list[dict[str, str]] = self._load()

    # ── I/O ────────────────────────────────────────────────

    def _load(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
            for row in self.rows:
                writer.writerow({k: row.get(k, "") for k in CSV_HEADERS})

    # ── Queries ────────────────────────────────────────────

    def open_rows(self) -> list[dict[str, str]]:
        return [r for r in self.rows if r.get("status") == "open"]

    def closed_rows(self) -> list[dict[str, str]]:
        return [r for r in self.rows if r.get("status") == "closed"]

    def has_trade(self, bioguide: str, tx_id: Any) -> bool:
        return any(
            r["bioguide"] == bioguide and str(r["tx_id"]) == str(tx_id)
            for r in self.rows
        )

    def _find_by_id(self, position_id: str) -> dict[str, str] | None:
        for r in self.rows:
            if r.get("position_id") == position_id:
                return r
        return None

    # ── Mutations ──────────────────────────────────────────

    def open_position(
        self, *,
        bioguide: str, tx_id: Any, ticker: str,
        signal_date: date, open_date: date,
        entry_date: date, entry_close: float,
        target_exit_date: date,
        now: datetime | None = None,
    ) -> dict[str, str]:
        """Append a new open position. Caller is responsible for
        dedup — `has_trade` short-circuits in the walk loop."""
        now = now or datetime.utcnow()
        row: dict[str, str] = {
            "position_id":      _position_id(bioguide, tx_id),
            "bioguide":         bioguide,
            "tx_id":            str(tx_id),
            "ticker":           ticker,
            "signal_date":      signal_date.isoformat(),
            "open_date":        open_date.isoformat(),
            "entry_date":       entry_date.isoformat(),
            "entry_close":      _fmt_float(entry_close),
            "target_exit_date": target_exit_date.isoformat(),
            "exit_date":        "",
            "exit_close":       "",
            "status":           "open",
            "pnl_abs":          _fmt_float(0.0),
            "pnl_pct":          _fmt_float(0.0, 6),
            "alpha_vs_spy":     "",
            "retracted_at":     "",
            "last_updated":     now.isoformat(timespec="seconds"),
        }
        self.rows.append(row)
        return row

    def close_position(
        self, position_id: str, *,
        exit_date: date, exit_close: float,
        alpha_vs_spy: float,
        now: datetime | None = None,
    ) -> None:
        """Mark an open position closed. Realized PnL comes from
        entry_close → exit_close; alpha_vs_spy is passed in by the
        walk loop (which has SPY prices in scope)."""
        now = now or datetime.utcnow()
        row = self._find_by_id(position_id)
        if row is None or row.get("status") != "open":
            return
        entry_close = float(row["entry_close"])
        pnl_abs = exit_close - entry_close
        pnl_pct = (exit_close / entry_close - 1.0) if entry_close > 0 else 0.0
        row.update({
            "exit_date":    exit_date.isoformat(),
            "exit_close":   _fmt_float(exit_close),
            "status":       "closed",
            "pnl_abs":      _fmt_float(pnl_abs),
            "pnl_pct":      _fmt_float(pnl_pct, 6),
            "alpha_vs_spy": _fmt_float(alpha_vs_spy, 6),
            "last_updated": now.isoformat(timespec="seconds"),
        })

    def mark_to_market(
        self, price_frames: dict[str, pd.DataFrame], today: date,
        *, now: datetime | None = None,
    ) -> None:
        """Update pnl_abs / pnl_pct on every open position using the
        latest available close on or before `today`. Positions whose
        ticker has no price frame are left as-is."""
        now = now or datetime.utcnow()
        for row in self.rows:
            if row.get("status") != "open":
                continue
            df = price_frames.get(row["ticker"])
            if df is None or df.empty:
                continue
            sub = df.loc[df.index.date <= today]
            if sub.empty:
                continue
            mark = float(sub["close"].iloc[-1])
            entry = float(row["entry_close"])
            pnl_abs = mark - entry
            pnl_pct = (mark / entry - 1.0) if entry > 0 else 0.0
            row.update({
                "pnl_abs":      _fmt_float(pnl_abs),
                "pnl_pct":      _fmt_float(pnl_pct, 6),
                "last_updated": now.isoformat(timespec="seconds"),
            })

    # ── Composed pipeline-run step ─────────────────────────

    def walk(
        self, *,
        members_data: dict[str, dict],
        price_frames: dict[str, pd.DataFrame],
        spy: pd.DataFrame,
        today: date,
        K: int = COHORT_K,
        exit_bdays: int = HORIZON_BDAYS,
        window_days: int = WINDOW_DAYS_DEFAULT,
        min_trades: int = MIN_TRADES_QUALIFY,
        ticker_adv: dict[str, float] | None = None,
        now: datetime | None = None,
    ) -> None:
        """One pipeline-run's worth of log updates. See module docstring
        for the four-step sequence. Call `save()` separately — the walk
        mutates in-memory state and returns; persistence is the caller's
        choice so tests can inspect rows before writing."""
        if ticker_adv is None:
            ticker_adv = {t: compute_ticker_adv(df) for t, df in price_frames.items()}
        now = now or datetime.utcnow()

        # 1. Close positions whose horizon elapsed.
        for row in list(self.open_rows()):
            target = date.fromisoformat(row["target_exit_date"])
            if target > today:
                continue
            stock_px = price_frames.get(row["ticker"])
            if stock_px is None:
                continue
            exit_stock = close_at_or_after(stock_px, target)
            exit_spy = close_at_or_after(spy, target)
            entry_spy = close_at_or_after(spy, date.fromisoformat(row["entry_date"]))
            if exit_stock is None or exit_spy is None or entry_spy is None:
                continue
            entry_close = float(row["entry_close"])
            if entry_close <= 0 or entry_spy[1] <= 0:
                continue
            stock_ret = exit_stock[1] / entry_close - 1.0
            spy_ret = exit_spy[1] / entry_spy[1] - 1.0
            self.close_position(
                row["position_id"],
                exit_date=exit_stock[0],
                exit_close=exit_stock[1],
                alpha_vs_spy=stock_ret - spy_ret,
                now=now,
            )

        # 2. Mark-to-market remaining open positions.
        self.mark_to_market(price_frames, today, now=now)

        # 3. Cohort as of today.
        cohort = select_cohort(
            members_data, ticker_adv, today, window_days, min_trades, K
        )

        # 4. Open new positions for unseen cohort BUYs.
        for bid in cohort:
            m = members_data.get(bid)
            if m is None:
                continue
            for t in m.get("trades", []) or []:
                if (t.get("type") or "").upper() != "BUY":
                    continue
                pub = t.get("published")
                if not pub:
                    continue
                try:
                    pub_d = date.fromisoformat(pub)
                except ValueError:
                    continue
                if pub_d > today:
                    continue
                tx_id = t.get("txId")
                if tx_id is None:
                    continue
                if self.has_trade(bid, tx_id):
                    continue
                ticker = (t.get("ticker") or "").upper()
                if not ticker or ticker not in price_frames:
                    continue
                # Entry = first available close on or after today+1
                # calendar day (matches #5 backtest's D+1 close
                # convention; pipeline runs after market close so
                # today's close is unreachable to a follower reading
                # the next morning).
                entry = close_at_or_after(price_frames[ticker], today + timedelta(days=1))
                if entry is None:
                    continue
                target = close_n_positions_later(
                    price_frames[ticker], entry[0], exit_bdays
                )
                # If price data doesn't extend far enough, fall back to
                # pure bday math for target_exit_date. Position still
                # opens; the close step will fill actual exit when
                # prices catch up.
                if target is not None:
                    target_exit_date = target[0]
                else:
                    target_exit_date = (
                        pd.Timestamp(entry[0]) + pd.offsets.BDay(exit_bdays)
                    ).date()
                self.open_position(
                    bioguide=bid, tx_id=tx_id, ticker=ticker,
                    signal_date=pub_d, open_date=today,
                    entry_date=entry[0], entry_close=entry[1],
                    target_exit_date=target_exit_date,
                    now=now,
                )


# ── CLI ────────────────────────────────────────────────────


def main():
    ap = argparse.ArgumentParser(description="Advance the paper-trading log by one pipeline-run step.")
    ap.add_argument("--K", type=int, default=COHORT_K)
    ap.add_argument("--exit-bdays", type=int, default=HORIZON_BDAYS)
    ap.add_argument("--window-days", type=int, default=WINDOW_DAYS_DEFAULT)
    ap.add_argument("--min-trades", type=int, default=MIN_TRADES_QUALIFY)
    ap.add_argument("--log-path", type=str, default=str(LOG_PATH),
                    help="CSV ledger path (default: scoring/paper_log/positions.csv)")
    ap.add_argument("--today", type=str, default=None,
                    help="Override 'today' (YYYY-MM-DD). Default: current date.")
    args = ap.parse_args()

    # Lazy imports so the module can be unit-tested without the CLI
    # surface pulling in fetch_trades / price_cache.
    from fetch_trades import load_bioguide_directory
    from price_cache import get_prices
    from score_members import (
        apply_filters, attach_alphas, fetch_all_members, normalize_ticker,
    )

    today = date.fromisoformat(args.today) if args.today else date.today()

    directory = load_bioguide_directory()
    if not directory:
        print("ERROR: could not load member_bioguide.json", file=sys.stderr)
        sys.exit(1)
    bioguide_ids = sorted(directory.keys())

    members_data = fetch_all_members(
        bioguide_ids, directory, args.window_days, refresh=False
    )

    unique_tickers: set[str] = set()
    for m in members_data.values():
        trades = m.get("trades", []) or []
        for t in trades:
            t["ticker"] = normalize_ticker(t.get("ticker"))
        kept, drop_counts = apply_filters(trades)
        m["trades"] = kept
        m["etf_drops"] = drop_counts["etf_drops"]
        m["options_drops"] = drop_counts["options_drops"]
        for t in kept:
            if t["ticker"]:
                unique_tickers.add(t["ticker"])
    unique_tickers.add("SPY")

    earliest = today - timedelta(days=args.window_days * 2)
    price_frames = get_prices(sorted(unique_tickers), earliest, today)
    spy = price_frames.get("SPY")
    if spy is None or spy.empty:
        print("ERROR: SPY price data missing", file=sys.stderr)
        sys.exit(1)

    attach_alphas(members_data, price_frames, spy)

    log = PaperLog(Path(args.log_path))
    log.walk(
        members_data=members_data,
        price_frames=price_frames,
        spy=spy,
        today=today,
        K=args.K, exit_bdays=args.exit_bdays,
        window_days=args.window_days, min_trades=args.min_trades,
    )
    log.save()

    n_open = len(log.open_rows())
    n_closed = len(log.closed_rows())
    print(f"paper_log updated at {today.isoformat()}: {len(log.rows)} rows "
          f"({n_open} open, {n_closed} closed)")


if __name__ == "__main__":
    main()
