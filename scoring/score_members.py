"""
score_members.py — rank every Congress member by followability
==============================================================

Pure-Python pipeline. No agent interpretation at runtime.

Pipeline:
    1. Load member_bioguide.json → full roster (assumed current).
    2. For each member, fetch 365d of trades via fetch_trades.fetch_member_trades.
       Results are cached per-member at scoring/cache/trades/<bioguide>.json
       with a fetched_at timestamp, so reruns within the refresh window skip
       the HTTP hit and the script is fully resume-capable on crash.
    3. Collect unique tickers across all trades (+ SPY) and bulk-fetch daily
       closes + volumes via scoring.price_cache (CSV-backed).
    4. For every BUY trade, compute 5d/20d/60d market-adjusted alpha vs SPY.
    5. For each member, aggregate factor values on both a 180d and 365d slice.
    6. Z-score across the member universe, compute composite scores.
    7. Write:
         scoring/output/leaderboard_<YYYYMMDD>.xlsx
         scoring/output/default_follow_<YYYYMMDD>.json

Invocation:
    python3 scoring/score_members.py                    # full run
    python3 scoring/score_members.py --limit 5          # first 5 members (dry run)
    python3 scoring/score_members.py --refresh          # ignore trade cache
    python3 scoring/score_members.py --top-n 20         # recommend top 20
    python3 scoring/score_members.py --min-trades 8     # override qualify floor
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

# Ensure sibling project modules (fetch_trades) are importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from fetch_trades import fetch_member_trades, load_bioguide_directory
from price_cache import get_prices
from factors import (
    ALPHA_HORIZONS,
    COMPOSITE_WEIGHTS,
    MIN_TRADES_QUALIFY,
    aggregate_member_factors,
    compute_composite,
    compute_trade_alpha,
    compute_ticker_adv,
)
from filters import (
    is_broad_market_etf,
    is_late_filing,
    is_non_self_owner,
    is_options_trade,
)

TRADE_CACHE_DIR = Path(__file__).parent / "cache" / "trades"
OUTPUT_DIR = Path(__file__).parent / "output"
TRADE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TRADE_CACHE_TTL_DAYS = 30  # reuse cached trades if fetched within N days


# ── Ticker normalization ───────────────────────────────────

def apply_filters(trades: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Apply the four signal-quality filters to a member's trades.

    ETF and options trades drop from the scoring universe. Non-self-owner
    and late-filing trades keep their slot but get a boolean tag attached
    (`non_self_filing`, `late_filing`) for downstream aggregation.

    Returns (kept_trades, drop_counts). drop_counts is a dict with
    `etf_drops` and `options_drops` integer keys. See
    `design/signal-quality-filters.md` for the per-filter rationale.
    """
    kept: list[dict] = []
    drops = {"etf_drops": 0, "options_drops": 0}
    for t in trades:
        if is_broad_market_etf(t.get("ticker")):
            drops["etf_drops"] += 1
            continue
        if is_options_trade(t):
            drops["options_drops"] += 1
            continue
        t["non_self_filing"] = is_non_self_owner(t.get("owner"))
        t["late_filing"] = is_late_filing(t.get("filedAfterDays"))
        kept.append(t)
    return kept, drops


def normalize_ticker(raw: str | None) -> str | None:
    """
    Capitoltrades returns tickers like 'STT:US', 'GSK:LN', 'BMW:GR'. yfinance
    wants bare US symbols; foreign-market mapping is messy and those trades
    aren't meaningfully copyable by a US retail follower. Strategy:
        'AAPL:US' → 'AAPL'
        'AAPL'    → 'AAPL'
        'GSK:LN'  → None   (foreign, drop)
        '' or None → None
    Also drops obvious non-equity placeholders ('N/A', '--', etc.).
    """
    if not raw or not isinstance(raw, str):
        return None
    t = raw.strip().upper()
    if not t or t in {"N/A", "--", "NONE"}:
        return None
    if ":" in t:
        base, _, suffix = t.partition(":")
        if suffix != "US":
            return None
        t = base
    if not t or not t.replace(".", "").replace("-", "").isalnum():
        return None
    return t


# ── Trade fetch with per-member checkpoint ─────────────────

def _trade_cache_path(bioguide: str) -> Path:
    return TRADE_CACHE_DIR / f"{bioguide}.json"


def _load_trade_cache(bioguide: str, ttl_days: int) -> dict | None:
    path = _trade_cache_path(bioguide)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            blob = json.load(f)
    except Exception:
        return None
    fetched = blob.get("fetched_at")
    if not fetched:
        return None
    try:
        fetched_dt = datetime.fromisoformat(fetched)
    except Exception:
        return None
    if datetime.now() - fetched_dt > timedelta(days=ttl_days):
        return None
    return blob


def _save_trade_cache(bioguide: str, data: dict, window_days: int) -> None:
    path = _trade_cache_path(bioguide)
    blob = {
        "fetched_at":  datetime.now().isoformat(timespec="seconds"),
        "window_days": window_days,
        "data":        data,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(blob, f, indent=2, ensure_ascii=False)


def fetch_all_members(
    bioguide_ids: list[str],
    directory: dict,
    window_days: int,
    refresh: bool,
) -> dict[str, dict]:
    """
    Fetch (or load from cache) trades for every bioguide ID.
    Returns {bioguide_id: fetch_member_trades result dict}.
    """
    cutoff = date.today() - timedelta(days=window_days)
    out: dict[str, dict] = {}
    total = len(bioguide_ids)

    for i, bid in enumerate(bioguide_ids, start=1):
        cache_hit = None if refresh else _load_trade_cache(bid, TRADE_CACHE_TTL_DAYS)
        if cache_hit and cache_hit.get("window_days", 0) >= window_days:
            out[bid] = cache_hit["data"]
            print(f"  [{i}/{total}] {bid}: cached ({cache_hit['data'].get('tradeCount', 0)} trades)", flush=True)
            continue

        try:
            # Silence fetch_trades' per-page prints by redirecting its stdout
            # prints are minor so we leave them on for now — visibility helps
            # when this takes an hour.
            data = fetch_member_trades(bid, cutoff, directory)
        except Exception as exc:
            print(f"  [{i}/{total}] {bid}: FETCH FAILED — {exc}", flush=True)
            continue

        _save_trade_cache(bid, data, window_days)
        out[bid] = data
        print(f"  [{i}/{total}] {bid}: fetched ({data.get('tradeCount', 0)} trades)", flush=True)
        time.sleep(0.25)  # mild additional politeness beyond fetch_trades' own

    return out


# ── Alpha attachment to trades ──────────────────────────────

def attach_alphas(
    members_data: dict[str, dict],
    price_frames: dict[str, pd.DataFrame],
    spy: pd.DataFrame,
) -> None:
    """In-place: annotate every BUY trade with alpha_5d/20d/60d."""
    for bid, m in members_data.items():
        for trade in m.get("trades", []) or []:
            if (trade.get("type") or "").upper() != "BUY":
                continue
            tkr = (trade.get("ticker") or "").upper()
            if not tkr:
                continue
            stock_px = price_frames.get(tkr)
            if stock_px is None or stock_px.empty:
                continue
            alphas = compute_trade_alpha(trade, stock_px, spy)
            trade.update(alphas)


# ── Dual-window factor aggregation ─────────────────────────

def window_trades(trades: list[dict], cutoff: date) -> list[dict]:
    out = []
    for t in trades:
        d = t.get("txDate")
        if not d:
            continue
        try:
            if date.fromisoformat(d) >= cutoff:
                out.append(t)
        except Exception:
            continue
    return out


def build_factor_table(
    members_data: dict[str, dict],
    ticker_adv: dict[str, float],
    window_days: int,
) -> pd.DataFrame:
    cutoff = date.today() - timedelta(days=window_days)
    rows = []
    for bid, m in members_data.items():
        trades = window_trades(m.get("trades", []) or [], cutoff)
        # Drop counts are set globally by apply_filters (across the full
        # fetched window, not per-window) so they appear identically on
        # both the 180d and 365d tables. They are informational, not
        # scoring inputs.
        drop_counts = {
            "etf_drops":     m.get("etf_drops", 0),
            "options_drops": m.get("options_drops", 0),
        }
        factors = aggregate_member_factors(trades, ticker_adv, drop_counts)
        rows.append({
            "bioguideId": bid,
            "fullName":   m.get("fullName", bid),
            "party":      m.get("party", ""),
            "chamber":    m.get("chamber", ""),
            "state":      m.get("state", ""),
            **factors,
        })
    df = pd.DataFrame(rows)
    return df


# ── Main ───────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Rank Congress members by followability.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Only score the first N members (for dry runs).")
    ap.add_argument("--window-days", type=int, default=365,
                    help="Long window in days (default 365).")
    ap.add_argument("--short-window-days", type=int, default=180,
                    help="Short window in days (default 180).")
    ap.add_argument("--min-trades", type=int, default=MIN_TRADES_QUALIFY,
                    help=f"Min trades in long window to qualify (default {MIN_TRADES_QUALIFY}).")
    ap.add_argument("--top-n", type=int, default=15,
                    help="Size of the recommended follow list (default 15).")
    ap.add_argument("--refresh", action="store_true",
                    help="Ignore trade cache and refetch all members.")
    ap.add_argument("--members", nargs="+", default=None,
                    help="Explicit bioguide IDs to score (overrides full roster).")
    args = ap.parse_args()

    print(f"=== score_members.py ===")
    print(f"long window: {args.window_days}d   short window: {args.short_window_days}d")
    print(f"min trades to qualify: {args.min_trades}   top-N: {args.top_n}")
    print(f"refresh: {args.refresh}")

    # 1. Roster
    directory = load_bioguide_directory()
    if not directory:
        print("ERROR: could not load member_bioguide.json", file=sys.stderr)
        sys.exit(1)
    if args.members:
        bioguide_ids = [b for b in args.members if b in directory]
        missing = set(args.members) - set(bioguide_ids)
        if missing:
            print(f"WARNING: unknown bioguide IDs dropped: {sorted(missing)}")
    else:
        bioguide_ids = sorted(directory.keys())
    if args.limit:
        bioguide_ids = bioguide_ids[: args.limit]
    print(f"\nRoster: {len(bioguide_ids)} members")

    # 2. Fetch trades
    print("\n--- Fetching trades ---")
    members_data = fetch_all_members(
        bioguide_ids, directory, args.window_days, args.refresh
    )
    print(f"\nGot trades for {len(members_data)} members")

    # 3. Normalize tickers, apply signal-quality filters, collect tickers.
    #    Filters run after ticker normalization (so is_broad_market_etf sees
    #    the normalized symbol) and before price-fetch (so we don't fetch
    #    prices for trades we're about to drop). See
    #    design/signal-quality-filters.md for drop-vs-tag rationale.
    unique_tickers: set[str] = set()
    total_etf_drops = 0
    total_options_drops = 0
    for m in members_data.values():
        trades = m.get("trades", []) or []
        for t in trades:
            t["ticker"] = normalize_ticker(t.get("ticker"))
        kept, drop_counts = apply_filters(trades)
        m["trades"] = kept
        m["etf_drops"] = drop_counts["etf_drops"]
        m["options_drops"] = drop_counts["options_drops"]
        total_etf_drops += drop_counts["etf_drops"]
        total_options_drops += drop_counts["options_drops"]
        for t in kept:
            if t["ticker"]:
                unique_tickers.add(t["ticker"])
    unique_tickers.add("SPY")
    if total_etf_drops or total_options_drops:
        print(f"\n--- Signal-quality filters ---")
        print(f"  Dropped {total_etf_drops} broad-market ETF trades, "
              f"{total_options_drops} options trades across all members.")
    print(f"\n--- Fetching prices ({len(unique_tickers)} unique tickers) ---")

    # Prices: need enough forward history for 60d alpha AFTER the earliest trade
    earliest_trade_date = date.today() - timedelta(days=args.window_days)
    price_start = earliest_trade_date - timedelta(days=14)
    price_end = date.today()
    price_frames = get_prices(sorted(unique_tickers), price_start, price_end)
    print(f"Got prices for {len(price_frames)} tickers")

    spy = price_frames.get("SPY")
    if spy is None or spy.empty:
        print("ERROR: SPY price data missing — cannot compute alpha.", file=sys.stderr)
        sys.exit(1)

    # 4. ADV per ticker + attach alphas
    ticker_adv = {t: compute_ticker_adv(df) for t, df in price_frames.items()}
    attach_alphas(members_data, price_frames, spy)

    # 5. Dual-window factor tables
    print("\n--- Aggregating factors (dual window) ---")
    long_df = build_factor_table(members_data, ticker_adv, args.window_days)
    short_df = build_factor_table(members_data, ticker_adv, args.short_window_days)

    # 6. Qualify filter on the LONG window, then score both
    qualified_ids = set(long_df.loc[long_df["trade_count"] >= args.min_trades, "bioguideId"])
    print(f"Qualified (>= {args.min_trades} trades in {args.window_days}d): {len(qualified_ids)}")

    long_q = long_df[long_df["bioguideId"].isin(qualified_ids)].copy()
    short_q = short_df[short_df["bioguideId"].isin(qualified_ids)].copy()

    long_scored = compute_composite(long_q).sort_values("composite", ascending=False).reset_index(drop=True)
    short_scored = compute_composite(short_q).sort_values("composite", ascending=False).reset_index(drop=True)

    long_scored["rank_long"] = long_scored.index + 1
    short_scored["rank_short"] = short_scored.index + 1

    # Merge rank divergence flag onto long table
    merged = long_scored.merge(
        short_scored[["bioguideId", "rank_short"]],
        on="bioguideId", how="left"
    )
    merged["rank_divergence"] = (merged["rank_long"] - merged["rank_short"]).abs()
    merged["divergence_flag"] = merged["rank_divergence"].apply(
        lambda d: "⚠" if pd.notna(d) and d >= 20 else ""
    )

    # 7. Write outputs
    stamp = date.today().strftime("%Y%m%d")
    leaderboard_path = OUTPUT_DIR / f"leaderboard_{stamp}.xlsx"
    follow_path = OUTPUT_DIR / f"default_follow_{stamp}.json"

    # Column order for the xlsx
    display_cols = [
        "rank_long", "rank_short", "divergence_flag",
        "fullName", "party", "chamber", "state",
        "composite",
        "trade_count", "buy_count", "sell_count",
        "mean_alpha_20d", "median_alpha_20d", "hit_rate", "sharpe_alpha",
        "mean_lag_days", "liq_pass_rate", "concentration", "buy_sell_balance",
        # Signal-quality filter visibility (ROADMAP #3). Shares carry the
        # information; per-category counts are omitted from the xlsx to
        # avoid column bloat — see aggregate_member_factors for the full
        # per-trade aggregates if needed.
        "non_self_share", "late_share", "etf_drops", "options_drops",
        "mean_alpha_20d_z", "hit_rate_z", "sharpe_alpha_z",
        "neg_lag_z", "liq_pass_rate_z", "trade_count_u_z", "concentration_z",
        "bioguideId",
    ]
    display_cols = [c for c in display_cols if c in merged.columns]
    out_long = merged[display_cols].copy()

    short_display = [c for c in display_cols if c in short_scored.columns and c != "rank_long" and c != "divergence_flag"]
    short_display = ["rank_short"] + [c for c in short_display if c != "rank_short"]
    out_short = short_scored[short_display].copy()

    # Write xlsx to a scratchpad path first, then copy into the mounted
    # output folder. Writing openpyxl directly through the cowork mount has
    # been observed to produce truncated files (EOCD record missing),
    # presumably a filesystem-sync timing issue on large multi-sheet writes.
    # Staging via the local scratchpad and shutil.copy avoids it entirely.
    import shutil
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        scratch_path = Path(tmp.name)
    try:
        with pd.ExcelWriter(scratch_path, engine="openpyxl") as xl:
            out_long.to_excel(xl, sheet_name="365d Leaderboard", index=False)
            out_short.to_excel(xl, sheet_name="180d Leaderboard", index=False)
            pd.DataFrame(
                [{"factor": k, "weight": v} for k, v in COMPOSITE_WEIGHTS.items()]
            ).to_excel(xl, sheet_name="Weights", index=False)
        # Sanity check the scratch file is a valid zip before copying
        import zipfile
        with zipfile.ZipFile(scratch_path) as _zf:
            _zf.namelist()  # will raise if truncated
        shutil.copy(scratch_path, leaderboard_path)
    finally:
        try:
            scratch_path.unlink()
        except Exception:
            pass

    # Default follow list: top-N from LONG window composite, excluding
    # anyone with a divergence flag (unstable ranking).
    stable = merged[merged["divergence_flag"] == ""]
    top = stable.head(args.top_n)
    follow_payload = {
        "generated":       date.today().isoformat(),
        "window_days":     args.window_days,
        "short_window_days": args.short_window_days,
        "min_trades":      args.min_trades,
        "top_n":           args.top_n,
        "recommended": [
            {
                "bioguideId": row.bioguideId,
                "fullName":   row.fullName,
                "party":      row.party,
                "chamber":    row.chamber,
                "state":      row.state,
                "composite":  round(float(row.composite), 4),
                "rank_long":  int(row.rank_long),
                "rank_short": int(row.rank_short) if pd.notna(row.rank_short) else None,
                "trade_count": int(row.trade_count),
            }
            for row in top.itertuples()
        ],
    }
    with open(follow_path, "w", encoding="utf-8") as f:
        json.dump(follow_payload, f, indent=2, ensure_ascii=False)

    print(f"\nWrote: {leaderboard_path}")
    print(f"Wrote: {follow_path}")
    print(f"\nTop {args.top_n}:")
    for r in follow_payload["recommended"]:
        print(f"  {r['rank_long']:>3}. {r['fullName']:<28} {r['party']:<12} {r['chamber']:<6} "
              f"composite={r['composite']:+.3f} trades={r['trade_count']}")


if __name__ == "__main__":
    main()
