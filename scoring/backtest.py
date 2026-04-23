"""
backtest.py — walk-forward backtest of the mirror strategy
==========================================================

ROADMAP #5, bundled with #4 under
`design/postfile-alpha-and-backtest.md`.

The question the scoring pipeline answers is "which members rank
highest by the post-file composite?" The question this module answers
is "does following the top-K ranked members actually produce alpha vs.
benchmarks?" — which is a different question and the one the
project-framing note treats as the viability test.

## Replay semantics

At each rebalance date D (business month-end by default):

1. Filter every member's trades to those with `published < D`
   (causal — no lookahead from future publications).
2. Aggregate factors on the trailing 365-day window ending at D and
   compute the composite across the member universe that qualifies.
3. Pick the top-K members by composite → the cohort.
4. Every BUY with `published` in (prev_rebalance_date, D] from a
   cohort member executes at `D+1` close.
5. Each executed position holds for `exit_bdays` positions on the
   ticker's price frame, then closes.

Per-trade alpha_vs_spy = stock_return − spy_return over the entry →
exit span, same mechanic as `compute_trade_alpha_postfile` — just
anchored on a strategy-driven entry date rather than a
publication-driven one.

## Known simplification

The composite at D uses the post-file alphas already attached to
trades (by `attach_alphas`), which themselves were computed with price
data extending up to the present. Strictly, a causal backtest would
recompute each trade's alpha using only prices available at D. The
mild forward-looking bias this introduces is small (only trades
published within the last `exit_bdays` at D have unresolved horizons),
and fixing it is deferred — it would require re-running the alpha
computation per rebalance, which doubles the cost. Filed as a
potential follow-up rather than a blocker for the first backtest.

## Compute

On-demand only — `python scoring/backtest.py`. Not CI-wired. The
synthetic-member fixture in `tests/fixtures/backtest_synthetic_member.py`
covers correctness via deterministic unit tests; real-world runs are
for Tom to inspect.

Output: `scoring/output/backtest_<YYYYMMDD>.json` with the shape
pinned by the design note.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from factors import (
    MIN_TRADES_QUALIFY,
    aggregate_member_factors,
    compute_composite,
    compute_ticker_adv,
)


OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ── Calendar ───────────────────────────────────────────────


def _last_bday_of_month(year: int, month: int) -> date:
    """Last Mon–Fri of the given calendar month. No holiday adjustment
    — matches the fixture's pandas-bdate-range convention."""
    if month == 12:
        first_next = date(year + 1, 1, 1)
    else:
        first_next = date(year, month + 1, 1)
    d = first_next - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def monthly_rebalance_dates(start: date, end: date) -> list[date]:
    """Last business day of each month in [start, end]."""
    out: list[date] = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        d = _last_bday_of_month(y, m)
        if start <= d <= end:
            out.append(d)
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return out


# ── Price-frame helpers ────────────────────────────────────


def close_at_or_after(prices: pd.DataFrame, target: date) -> tuple[date, float] | None:
    """First (trading_day, close) on or after `target`, or None."""
    if prices is None or prices.empty:
        return None
    mask = prices.index.date >= target
    forward = prices.loc[mask]
    if forward.empty:
        return None
    idx = forward.index[0]
    return idx.date(), float(forward["close"].iloc[0])


def close_n_positions_later(
    prices: pd.DataFrame, entry_day: date, n: int
) -> tuple[date, float] | None:
    """(trading_day, close) `n` rows after the row for `entry_day`, or None."""
    if prices is None or prices.empty:
        return None
    idx = prices.index.searchsorted(pd.Timestamp(entry_day))
    target_idx = idx + n
    if target_idx >= len(prices):
        return None
    return prices.index[target_idx].date(), float(prices["close"].iloc[target_idx])


def _total_return(prices: pd.DataFrame, start: date, end: date) -> float | None:
    """Cumulative close-to-close return over [start, end], forward-filled
    at both ends. Returns None if the span can't be resolved."""
    s = close_at_or_after(prices, start)
    e = close_at_or_after(prices, end)
    if s is None or e is None:
        return None
    if s[1] <= 0:
        return None
    return e[1] / s[1] - 1.0


# ── Cohort selection ───────────────────────────────────────


def _trades_before(trades: list[dict], cutoff: date) -> list[dict]:
    """Filter to trades with `published < cutoff`. Trades missing a
    parseable `published` drop out — they can't contribute to a causal
    composite."""
    out = []
    for t in trades:
        pub = t.get("published")
        if not pub:
            continue
        try:
            if date.fromisoformat(pub) < cutoff:
                out.append(t)
        except ValueError:
            continue
    return out


def select_cohort(
    members_data: dict[str, dict],
    ticker_adv: dict[str, float],
    rebalance_date: date,
    window_days: int,
    min_trades: int,
    K: int,
) -> list[str]:
    """Rank members by composite computed on the trailing `window_days`
    of pre-`rebalance_date` trades; return the top-K bioguide IDs."""
    window_start = rebalance_date - timedelta(days=window_days)
    rows = []
    for bid, m in members_data.items():
        pre = _trades_before(m.get("trades", []) or [], rebalance_date)
        # Apply the trailing window on top of the causal filter.
        windowed = [
            t for t in pre
            if t.get("txDate") and date.fromisoformat(t["txDate"]) >= window_start
        ]
        factors = aggregate_member_factors(
            windowed, ticker_adv,
            drop_counts={
                "etf_drops": m.get("etf_drops", 0),
                "options_drops": m.get("options_drops", 0),
            },
        )
        rows.append({"bioguideId": bid, **factors})
    df = pd.DataFrame(rows)
    q = df[df["trade_count"] >= min_trades].copy()
    if q.empty:
        return []
    scored = compute_composite(q).sort_values("composite", ascending=False).reset_index(drop=True)
    return scored["bioguideId"].head(K).tolist()


# ── Main replay loop ────────────────────────────────────────


def walk_forward(
    members_data: dict[str, dict],
    price_frames: dict[str, pd.DataFrame],
    spy: pd.DataFrame,
    *,
    nanc: pd.DataFrame | None = None,
    K: int = 15,
    exit_bdays: int = 60,
    window_days: int = 365,
    min_trades: int = MIN_TRADES_QUALIFY,
    ticker_adv: dict[str, float] | None = None,
    first_rebalance: date | None = None,
    last_rebalance: date | None = None,
) -> dict[str, Any]:
    """Run the walk-forward replay. Returns the JSON-ready dict
    shape specified in the design note."""
    if ticker_adv is None:
        ticker_adv = {t: compute_ticker_adv(df) for t, df in price_frames.items()}

    # Derive the rebalance date series from the publication-date range.
    pub_dates: set[date] = set()
    for m in members_data.values():
        for t in m.get("trades", []) or []:
            pub = t.get("published")
            if not pub:
                continue
            try:
                pub_dates.add(date.fromisoformat(pub))
            except ValueError:
                continue
    if not pub_dates:
        return {"rebalances": [], "summary": {}}

    start = first_rebalance or min(pub_dates)
    end = last_rebalance or max(pub_dates)
    rebalances = monthly_rebalance_dates(start, end)

    all_executed: list[dict] = []  # strategy trades, flat
    rebalance_log: list[dict] = []
    prev_rebalance = start - timedelta(days=1)

    for D in rebalances:
        cohort = select_cohort(
            members_data, ticker_adv, D, window_days, min_trades, K
        )
        executed_this_rebalance: list[dict] = []
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
                if not (prev_rebalance < pub_d <= D):
                    continue
                ticker = (t.get("ticker") or "").upper()
                if not ticker or ticker not in price_frames:
                    continue
                stock_px = price_frames[ticker]

                entry_target = D + timedelta(days=1)
                entry = close_at_or_after(stock_px, entry_target)
                entry_spy = close_at_or_after(spy, entry_target)
                if entry is None or entry_spy is None:
                    continue
                exit_ = close_n_positions_later(stock_px, entry[0], exit_bdays)
                exit_spy = close_n_positions_later(spy, entry_spy[0], exit_bdays)
                if exit_ is None or exit_spy is None:
                    continue
                if entry[1] <= 0 or entry_spy[1] <= 0:
                    continue

                stock_ret = exit_[1] / entry[1] - 1.0
                spy_ret = exit_spy[1] / entry_spy[1] - 1.0
                executed_this_rebalance.append({
                    "bioguide":     bid,
                    "ticker":       ticker,
                    "entry_date":   entry[0].isoformat(),
                    "entry_close":  entry[1],
                    "exit_date":    exit_[0].isoformat(),
                    "exit_close":   exit_[1],
                    "stock_return": stock_ret,
                    "alpha_vs_spy": stock_ret - spy_ret,
                })
        all_executed.extend(executed_this_rebalance)
        rebalance_log.append({
            "date":   D.isoformat(),
            "cohort": cohort,
            "trades": executed_this_rebalance,
        })
        prev_rebalance = D

    # ── Summary stats ────────────────────────────────────────
    if all_executed:
        returns = [r["stock_return"] for r in all_executed]
        alphas = [r["alpha_vs_spy"] for r in all_executed]
        strategy_total = sum(returns) / len(returns)    # equal-weight average
        strategy_alpha_spy = sum(alphas) / len(alphas)
        hit = sum(1 for a in alphas if a > 0) / len(alphas)
        sd = pd.Series(alphas).std(ddof=1) if len(alphas) > 1 else 0.0
        sharpe = float(strategy_alpha_spy / sd) if sd and sd > 0 else None
    else:
        strategy_total = 0.0
        strategy_alpha_spy = 0.0
        hit = None
        sharpe = None

    # Baseline: naive_copy_everyone — buy every BUY from every member,
    # same entry/exit mechanic. Shares the per-trade loop shape but no
    # cohort filter.
    naive_trades: list[dict] = []
    for bid, m in members_data.items():
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
            if not (start <= pub_d <= end):
                continue
            ticker = (t.get("ticker") or "").upper()
            if not ticker or ticker not in price_frames:
                continue
            # Execute at the first month-end >= pub_d + 1 bday, same as strategy.
            target_rebalance = next(
                (r for r in rebalances if r >= pub_d), None
            )
            if target_rebalance is None:
                continue
            stock_px = price_frames[ticker]
            entry = close_at_or_after(stock_px, target_rebalance + timedelta(days=1))
            entry_spy = close_at_or_after(spy, target_rebalance + timedelta(days=1))
            if entry is None or entry_spy is None:
                continue
            exit_ = close_n_positions_later(stock_px, entry[0], exit_bdays)
            exit_spy = close_n_positions_later(spy, entry_spy[0], exit_bdays)
            if exit_ is None or exit_spy is None or entry[1] <= 0:
                continue
            naive_trades.append({
                "stock_return": exit_[1] / entry[1] - 1.0,
                "alpha_vs_spy": (exit_[1] / entry[1] - 1.0) - (exit_spy[1] / entry_spy[1] - 1.0),
            })
    if naive_trades:
        naive_total = sum(r["stock_return"] for r in naive_trades) / len(naive_trades)
        naive_hit = sum(1 for r in naive_trades if r["alpha_vs_spy"] > 0) / len(naive_trades)
    else:
        naive_total = 0.0
        naive_hit = None

    # Benchmark baselines: SPY, NANC — cumulative return over the span.
    spy_total = _total_return(spy, start, end)
    nanc_total = _total_return(nanc, start, end) if nanc is not None else None

    alpha_vs_nanc = (
        strategy_total - nanc_total if nanc_total is not None else None
    )
    alpha_vs_naive = strategy_total - naive_total

    return {
        "generated": date.today().isoformat(),
        "params": {
            "cadence":         "monthly",
            "K":               K,
            "exit_bdays":      exit_bdays,
            "window_days":     window_days,
            "min_trades":      min_trades,
            "first_rebalance": rebalances[0].isoformat() if rebalances else None,
            "last_rebalance":  rebalances[-1].isoformat() if rebalances else None,
        },
        "rebalances": rebalance_log,
        "summary": {
            "strategy": {
                "total_return":                strategy_total,
                "alpha_vs_spy":                strategy_alpha_spy,
                "alpha_vs_nanc":               alpha_vs_nanc,
                "alpha_vs_naive_copy_everyone": alpha_vs_naive,
                "hit_rate":                    hit,
                "sharpe":                      sharpe,
                "n_rebalances":                len(rebalances),
                "n_trades":                    len(all_executed),
            },
            "naive_copy_everyone": {
                "total_return": naive_total,
                "hit_rate":     naive_hit,
                "n_trades":     len(naive_trades),
            },
            "NANC": {"total_return": nanc_total},
            "SPY":  {"total_return": spy_total},
        },
    }


# ── CLI ────────────────────────────────────────────────────


def main():
    ap = argparse.ArgumentParser(description="Walk-forward backtest of the mirror strategy.")
    ap.add_argument("--K", type=int, default=15)
    ap.add_argument("--exit-bdays", type=int, default=60)
    ap.add_argument("--window-days", type=int, default=365)
    ap.add_argument("--min-trades", type=int, default=MIN_TRADES_QUALIFY)
    ap.add_argument("--members", nargs="+", default=None,
                    help="Explicit bioguide IDs to include (default: full cached universe).")
    ap.add_argument("--out", type=str, default=None,
                    help="Output JSON path (default: scoring/output/backtest_<YYYYMMDD>.json).")
    args = ap.parse_args()

    # Lazy imports of the score_members utilities so the module can be
    # unit-tested without the full CLI surface.
    from fetch_trades import load_bioguide_directory
    from price_cache import get_prices
    from score_members import (
        apply_filters, attach_alphas, fetch_all_members, normalize_ticker,
    )

    directory = load_bioguide_directory()
    if not directory:
        print("ERROR: could not load member_bioguide.json", file=sys.stderr)
        sys.exit(1)
    bioguide_ids = sorted(args.members) if args.members else sorted(directory.keys())

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
    unique_tickers |= {"SPY", "NANC"}

    today = date.today()
    earliest_trade = today - timedelta(days=args.window_days * 3)
    price_frames = get_prices(
        sorted(unique_tickers), earliest_trade - timedelta(days=14), today
    )
    spy = price_frames.get("SPY")
    nanc = price_frames.get("NANC")
    if spy is None or spy.empty:
        print("ERROR: SPY price data missing", file=sys.stderr)
        sys.exit(1)

    attach_alphas(members_data, price_frames, spy)

    result = walk_forward(
        members_data, price_frames, spy,
        nanc=nanc, K=args.K, exit_bdays=args.exit_bdays,
        window_days=args.window_days, min_trades=args.min_trades,
    )

    stamp = datetime.now().strftime("%Y%m%d")
    out_path = Path(args.out) if args.out else OUTPUT_DIR / f"backtest_{stamp}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)

    s = result["summary"]["strategy"]
    print(f"wrote {out_path}")
    print(f"rebalances={s['n_rebalances']}  trades={s['n_trades']}")
    print(f"strategy total_return = {s['total_return']:+.4f}")
    print(f"alpha_vs_spy          = {s['alpha_vs_spy']:+.4f}")
    if s['alpha_vs_nanc'] is not None:
        print(f"alpha_vs_nanc         = {s['alpha_vs_nanc']:+.4f}")
    print(f"alpha_vs_naive        = {s['alpha_vs_naive_copy_everyone']:+.4f}")


if __name__ == "__main__":
    main()
