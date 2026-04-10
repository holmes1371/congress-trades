"""
compute_analysis.py — Congressional Trade Pre-Analysis
=======================================================
Reads trade_data.json and computes all the mechanical statistics so Claude
only needs to interpret a compact summary rather than process hundreds of
raw trade records.

Outputs computed_stats.json in the project folder.

Usage:
    python compute_analysis.py
    python compute_analysis.py --in my_trade_data.json --out my_stats.json
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path


# ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ──
# HELPERS
# ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ──

def _bias_label(pct_buys: float) -> str:
    if pct_buys >= 80: return "Strongly Bullish"
    if pct_buys >= 60: return "Bullish"
    if pct_buys >= 40: return "Mixed"
    return "Bearish"


def _fmt(value: float) -> str:
    """Human-readable dollar amount."""
    if value >= 1_000_000:
        return f"~${value/1_000_000:.2f}M"
    if value >= 1_000:
        return f"~${value/1_000:.0f}K"
    return f"~${value:.0f}"


# ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ──
# PER-MEMBER STATS
# ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ──

def compute_member_stats(members: dict) -> dict:
    stats = {}
    for name, m in members.items():
        trades  = m["trades"]
        eq      = [t for t in trades if t.get("ticker")]
        buys    = [t for t in eq if t["type"] == "BUY"]
        sells   = [t for t in eq if t["type"] == "SELL"]
        buy_vol = sum(t["value"] or 0 for t in buys)
        sel_vol = sum(t["value"] or 0 for t in sells)
        pct     = len(buys) / max(len(eq), 1) * 100

        # Ticker aggregation
        tk_buys  = defaultdict(lambda: {"count": 0, "value": 0, "dates": []})
        tk_sells = defaultdict(lambda: {"count": 0, "value": 0, "dates": []})
        for t in buys:
            tk = t["ticker"].replace(":US", "")
            tk_buys[tk]["count"] += 1
            tk_buys[tk]["value"] += t["value"] or 0
            tk_buys[tk]["dates"].append(t["txDate"])
        for t in sells:
            tk = t["ticker"].replace(":US", "")
            tk_sells[tk]["count"] += 1
            tk_sells[tk]["value"] += t["value"] or 0
            tk_sells[tk]["dates"].append(t["txDate"])

        top_buys = sorted(
            [{"ticker": tk, **v} for tk, v in tk_buys.items()],
            key=lambda x: (-x["count"], -x["value"])
        )[:12]
        top_sells = sorted(
            [{"ticker": tk, **v} for tk, v in tk_sells.items()],
            key=lambda x: (-x["count"], -x["value"])
        )[:8]

        # Sector breakdown
        sectors = defaultdict(lambda: {"buy": 0, "sell": 0})
        for t in eq:
            sec = t.get("sector") or "unknown"
            key = "buy" if t["type"] == "BUY" else "sell"
            sectors[sec][key] += t["value"] or 0
        sector_list = sorted(
            [{"sector": s, **v} for s, v in sectors.items()],
            key=lambda x: -x["buy"]
        )

        # Filing lag
        lags = [t["filedAfterDays"] for t in trades if t.get("filedAfterDays") is not None]
        avg_lag = round(sum(lags) / len(lags)) if lags else None

        # Most recent trade date
        dates = sorted([t["txDate"] for t in eq if t.get("txDate")], reverse=True)

        stats[name] = {
            "party":           m.get("party", ""),
            "chamber":         m.get("chamber", ""),
            "state":           m.get("state", ""),
            "bioguideId":      m.get("bioguideId", ""),
            "total_trades":    len(trades),
            "equity_trades":   len(eq),
            "buys":            len(buys),
            "sells":           len(sells),
            "buy_vol":         buy_vol,
            "sell_vol":        sel_vol,
            "buy_vol_fmt":     _fmt(buy_vol),
            "sell_vol_fmt":    _fmt(sel_vol),
            "pct_buys":        round(pct, 1),
            "bias":            _bias_label(pct),
            "avg_filing_lag":  avg_lag,
            "most_recent_trade": dates[0] if dates else None,
            "top_buy_tickers":  top_buys,
            "top_sell_tickers": top_sells,
            "sector_breakdown": sector_list,
        }
    return stats


# ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ──
# CROSS-MEMBER CONSENSUS
# ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ──

def compute_consensus(members: dict, member_stats: dict) -> dict:
    # Build ticker→member buy/sell maps
    tk_buyers  = defaultdict(list)  # ticker → [{name, party, count, value, dates}]
    tk_sellers = defaultdict(list)

    for name, m in members.items():
        party = member_stats[name]["party"]
        tk_buys  = defaultdict(lambda: {"count": 0, "value": 0, "dates": []})
        tk_sells = defaultdict(lambda: {"count": 0, "value": 0, "dates": []})
        for t in m["trades"]:
            if not t.get("ticker"): continue
            tk = t["ticker"].replace(":US", "")
            if t["type"] == "BUY":
                tk_buys[tk]["count"] += 1
                tk_buys[tk]["value"] += t["value"] or 0
                tk_buys[tk]["dates"].append(t["txDate"])
            else:
                tk_sells[tk]["count"] += 1
                tk_sells[tk]["value"] += t["value"] or 0
                tk_sells[tk]["dates"].append(t["txDate"])

        for tk, v in tk_buys.items():
            tk_buyers[tk].append({"name": name, "party": party, **v})
        for tk, v in tk_sells.items():
            tk_sellers[tk].append({"name": name, "party": party, **v})

    def _is_cross_party(entries):
        parties = {e["party"] for e in entries}
        return len(parties) > 1

    # Consensus buys (2+ members)
    consensus_buys = []
    for tk, buyers in tk_buyers.items():
        if len(buyers) < 2: continue
        cross = _is_cross_party(buyers)
        total_val = sum(b["value"] for b in buyers)
        total_cnt = sum(b["count"] for b in buyers)
        consensus_buys.append({
            "ticker":       tk,
            "cross_party":  cross,
            "member_count": len(buyers),
            "total_count":  total_cnt,
            "total_value":  total_val,
            "total_value_fmt": _fmt(total_val),
            "members":      sorted(buyers, key=lambda x: -x["value"]),
        })
    # Sort: cross-party first, then member count, then value
    consensus_buys.sort(key=lambda x: (-x["cross_party"], -x["member_count"], -x["total_value"]))

    # Consensus sells (2+ members)
    consensus_sells = []
    for tk, sellers in tk_sellers.items():
        if len(sellers) < 2: continue
        cross = _is_cross_party(sellers)
        total_val = sum(s["value"] for s in sellers)
        total_cnt = sum(s["count"] for s in sellers)
        consensus_sells.append({
            "ticker":       tk,
            "cross_party":  cross,
            "member_count": len(sellers),
            "total_count":  total_cnt,
            "total_value":  total_val,
            "total_value_fmt": _fmt(total_val),
            "members":      sorted(sellers, key=lambda x: -x["value"]),
        })
    consensus_sells.sort(key=lambda x: (-x["cross_party"], -x["member_count"], -x["total_value"]))

    # Mixed signals (same ticker bought by some, sold by others)
    all_tickers = set(tk_buyers.keys()) & set(tk_sellers.keys())
    mixed = []
    for tk in sorted(all_tickers):
        buyers  = [e["name"].split()[-1] for e in tk_buyers[tk]]
        sellers = [e["name"].split()[-1] for e in tk_sellers[tk]]
        buyer_parties  = {e["party"][0] for e in tk_buyers[tk]}
        seller_parties = {e["party"][0] for e in tk_sellers[tk]}
        mixed.append({
            "ticker":          tk,
            "buyers":          buyers,
            "buyer_parties":   list(buyer_parties),
            "sellers":         sellers,
            "seller_parties":  list(seller_parties),
            "cross_party_conflict": bool(buyer_parties & seller_parties),
        })

    return {
        "buys":  consensus_buys,
        "sells": consensus_sells,
        "mixed": mixed,
    }


# ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ──
# CONVICTION PATTERNS
# ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ──

def compute_conviction_patterns(members: dict, member_stats: dict) -> list:
    """
    Surfaces single-member high-conviction signals:
      - Repeated buys of the same ticker (3+ trades)
      - Large single positions ($150K+)
      - Repeated sells (unwinding)
    """
    patterns = []

    for name, m in members.items():
        party = member_stats[name]["party"]

        tk_buys  = defaultdict(lambda: {"count": 0, "value": 0, "dates": [], "prices": []})
        tk_sells = defaultdict(lambda: {"count": 0, "value": 0, "dates": []})

        for t in m["trades"]:
            if not t.get("ticker"): continue
            tk = t["ticker"].replace(":US", "")
            if t["type"] == "BUY":
                tk_buys[tk]["count"]  += 1
                tk_buys[tk]["value"]  += t["value"] or 0
                tk_buys[tk]["dates"].append(t["txDate"])
                if t.get("price"):
                    tk_buys[tk]["prices"].append(t["price"])
            else:
                tk_sells[tk]["count"] += 1
                tk_sells[tk]["value"] += t["value"] or 0
                tk_sells[tk]["dates"].append(t["txDate"])

        # Repeated buys (3+)
        for tk, v in tk_buys.items():
            if v["count"] >= 3:
                patterns.append({
                    "type":        "repeated_buy",
                    "member":      name,
                    "party":       party,
                    "ticker":      tk,
                    "count":       v["count"],
                    "total_value": v["value"],
                    "value_fmt":   _fmt(v["value"]),
                    "dates":       sorted(v["dates"]),
                    "avg_price":   round(sum(v["prices"]) / len(v["prices"]), 2) if v["prices"] else None,
                })

        # Large single positions (one trade ≥ $150K, buy or sell)
        for t in m["trades"]:
            if (t.get("value") or 0) >= 150_000 and t.get("ticker"):
                tk = t["ticker"].replace(":US", "")
                # Only flag if not already caught by repeated_buy
                already = any(
                    p["ticker"] == tk and p["member"] == name and p["type"] == "repeated_buy"
                    for p in patterns
                )
                if not already:
                    patterns.append({
                        "type":        "large_position",
                        "member":      name,
                        "party":       party,
                        "ticker":      tk,
                        "trade_type":  t["type"],
                        "value":       t["value"],
                        "value_fmt":   _fmt(t["value"]),
                        "txDate":      t["txDate"],
                        "price":       t.get("price"),
                    })

        # Repeated sells (3+)
        for tk, v in tk_sells.items():
            if v["count"] >= 3:
                patterns.append({
                    "type":        "repeated_sell",
                    "member":      name,
                    "party":       party,
                    "ticker":      tk,
                    "count":       v["count"],
                    "total_value": v["value"],
                    "value_fmt":   _fmt(v["value"]),
                    "dates":       sorted(v["dates"]),
                })

    # Sort by total value descending
    patterns.sort(key=lambda x: -(x.get("total_value") or x.get("value") or 0))
    return patterns


# ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ──
# SECTOR TOTALS
# ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ──

def compute_sector_totals(members: dict) -> list:
    totals = defaultdict(lambda: {"buy": 0, "sell": 0, "members_buying": set(), "members_selling": set()})
    for name, m in members.items():
        for t in m["trades"]:
            if not t.get("ticker") or not t.get("sector"): continue
            sec = t["sector"]
            val = t["value"] or 0
            if t["type"] == "BUY":
                totals[sec]["buy"] += val
                totals[sec]["members_buying"].add(name.split()[-1])
            else:
                totals[sec]["sell"] += val
                totals[sec]["members_selling"].add(name.split()[-1])

    result = []
    for sec, v in totals.items():
        net = v["buy"] - v["sell"]
        result.append({
            "sector":            sec,
            "buy_vol":           v["buy"],
            "sell_vol":          v["sell"],
            "net":               net,
            "buy_vol_fmt":       _fmt(v["buy"]),
            "sell_vol_fmt":      _fmt(v["sell"]),
            "net_fmt":           _fmt(abs(net)),
            "net_direction":     "Accumulating" if net > 0 else "Distributing",
            "members_buying":    sorted(v["members_buying"]),
            "members_selling":   sorted(v["members_selling"]),
        })

    return sorted(result, key=lambda x: -x["buy_vol"])


# ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ──
# RECENT TRADES
# ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ──

def compute_recent_trades(members: dict, top_n: int = 25) -> list:
    """Most recent trades by txDate across all members."""
    all_trades = []
    for name, m in members.items():
        for t in m["trades"]:
            if t.get("ticker") and t.get("txDate"):
                all_trades.append({
                    "member":  name,
                    "party":   m.get("party", ""),
                    **{k: t[k] for k in ["ticker", "type", "txDate", "published", "value", "price", "sector", "filedAfterDays"]},
                })
    all_trades.sort(key=lambda x: x["txDate"], reverse=True)
    return all_trades[:top_n]


# ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ──
# CHANGE DETECTION
# ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ──

def _extract_tx_ids(data: dict) -> set:
    """Return the set of all txIds present in a trade_data dict."""
    return {
        t["txId"]
        for m in data["members"].values()
        for t in m["trades"]
        if t.get("txId")
    }


def detect_changes(in_path: Path) -> tuple[bool, str]:
    """
    Compare the current trade_data.json against the most recent previous snapshot
    in the data/ archive folder.

    fetch_trades.py writes a timestamped copy into data/ at the same time it
    writes the current file, so data/ always contains at least the current run.
    We look at the second-most-recent snapshot (the previous run) and compare
    txId sets.

    Returns:
        (has_changes, last_change_date)
        has_changes     — True if new txIds exist; False = short-circuit
        last_change_date — human-readable date of the previous run (MM-DD-YYYY),
                           empty string if comparison was not possible
    """
    # data/ now lives next to the script regardless of where the input file lives.
    data_dir = Path(__file__).parent / "data"
    if not data_dir.exists():
        return True, ""  # No archive folder yet — first run, treat as new

    # Match the same prefix as the current input so committee runs only compare
    # against earlier runs of the same committee.
    prefix = in_path.stem  # e.g. "trade_data_house_committee_on_armed_services"
    snapshots = sorted(data_dir.glob(f"{prefix}_*.json"))
    if len(snapshots) < 2:
        return True, ""  # Only one snapshot (this run) — nothing to compare

    # snapshots[-1] = current run's archived copy
    # snapshots[-2] = previous run (the one we compare against)
    prev_snapshot = snapshots[-2]

    with open(in_path, encoding="utf-8") as f:
        current_data = json.load(f)
    current_ids = _extract_tx_ids(current_data)

    with open(prev_snapshot, encoding="utf-8") as f:
        prev_data = json.load(f)
    prev_ids = _extract_tx_ids(prev_data)

    new_ids = current_ids - prev_ids
    if new_ids:
        return True, ""  # New trades found — run full analysis

    # No new trades — scan ALL snapshots (newest first) to find the most
    # recent one that actually contains trade records, then pull the max
    # published (disclosure) date from those records.
    last_date = "unknown"
    for snap in reversed(snapshots):
        try:
            with open(snap, encoding="utf-8") as f:
                snap_data = json.load(f)
            pub_dates = [
                t["published"]
                for m in snap_data["members"].values()
                for t in m["trades"]
                if t.get("published")
            ]
            if pub_dates:
                latest = max(pub_dates)      # ISO string e.g. "2026-04-06"
                try:
                    d = date.fromisoformat(latest[:10])
                    last_date = d.strftime("%m-%d-%Y")
                except ValueError:
                    last_date = latest
                break
        except (OSError, json.JSONDecodeError, KeyError):
            continue

    return False, last_date


# ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ──
# MAIN
# ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ──

def main():
    parser = argparse.ArgumentParser(description="Pre-compute congressional trade statistics")
    parser.add_argument("--in",  dest="infile",  default="data/trade_data.json",
                        help="Input trade data JSON (default: data/trade_data.json)")
    parser.add_argument("--out", dest="outfile", default="computed_stats/computed_stats.json",
                        help="Output stats JSON (default: computed_stats/computed_stats.json)")
    args = parser.parse_args()

    in_path  = Path(__file__).parent / args.infile
    out_path = Path(__file__).parent / args.outfile
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Reading {in_path}…")
    with open(in_path, encoding="utf-8") as f:
        data = json.load(f)

    # ── Change detection ──────────────────────────────────────
    has_changes, last_date = detect_changes(in_path)
    if not has_changes:
        print(f"NO_CHANGES:{last_date}")
        print(f"No new trades disclosed since {last_date}.")
        # Auto-generate the stub "no changes" report so the agent doesn't have to.
        import subprocess
        gen = Path(__file__).parent / "generate_report.py"
        # Derive the configuration slug from the input filename so the stub
        # report and its "prior report" link stay scoped to this lineage
        # (default list vs. specific committee).
        stem = in_path.stem  # e.g. "trade_data_house_committee_on_oversight_and_government_reform"
        slug = ""
        if stem.startswith("trade_data_") and stem != "trade_data":
            slug = stem[len("trade_data_"):]
        try:
            cmd = ["python3", str(gen), "--no-changes", last_date or "unknown"]
            if slug:
                cmd += ["--slug", slug]
            subprocess.run(cmd, check=False)
        except Exception as e:
            print(f"(could not auto-generate no-changes report: {e})")
        sys.exit(0)
    # ─────────────────────────────────────────────────────────

    members  = data["members"]
    metadata = data["metadata"]

    print(f"Computing stats for {len(members)} member(s)…")

    member_stats      = compute_member_stats(members)
    consensus         = compute_consensus(members, member_stats)
    conviction        = compute_conviction_patterns(members, member_stats)
    sector_totals     = compute_sector_totals(members)
    recent_trades     = compute_recent_trades(members)

    total_trades  = sum(s["total_trades"]  for s in member_stats.values())
    total_buy_vol = sum(s["buy_vol"]       for s in member_stats.values())
    total_sel_vol = sum(s["sell_vol"]      for s in member_stats.values())

    output = {
        "computed_at": datetime.now().isoformat(timespec="seconds"),
        "source_metadata": metadata,
        "summary": {
            "members":              len(members),
            "total_trades":         total_trades,
            "total_buy_volume":     total_buy_vol,
            "total_sell_volume":    total_sel_vol,
            "total_buy_vol_fmt":    _fmt(total_buy_vol),
            "total_sell_vol_fmt":   _fmt(total_sel_vol),
            "consensus_buy_signals":  len(consensus["buys"]),
            "cross_party_buys":       sum(1 for c in consensus["buys"]  if c["cross_party"]),
            "consensus_sell_signals": len(consensus["sells"]),
            "cross_party_sells":      sum(1 for c in consensus["sells"] if c["cross_party"]),
            "conviction_patterns":    len(conviction),
        },
        "member_stats":    member_stats,
        "consensus":       consensus,
        "conviction":      conviction,
        "sector_totals":   sector_totals,
        "recent_trades":   recent_trades,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Timestamped archive copy alongside the current file in computed_stats/
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = out_path.parent / f"{out_path.stem}_{ts}.json"
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Archived → {archive_path}")

    # Print digest
    print(f"\n{'─'*60}")
    print(f"{'Member':<28} {'Bias':<18} {'Buys':>5} {'Sells':>5} {'Buy Vol':>10}")
    print(f"{'─'*60}")
    for name, s in member_stats.items():
        print(f"{name:<28} {s['bias']:<18} {s['buys']:>5} {s['sells']:>5} {s['buy_vol_fmt']:>10}")
    print(f"{'─'*60}")
    print(f"\nConsensus buys:  {len(consensus['buys'])}  "
          f"(cross-party: {sum(1 for c in consensus['buys'] if c['cross_party'])})")
    print(f"Consensus sells: {len(consensus['sells'])}  "
          f"(cross-party: {sum(1 for c in consensus['sells'] if c['cross_party'])})")
    print(f"Conviction patterns: {len(conviction)}")
    print(f"\nTop cross-party consensus BUYS:")
    for c in [x for x in consensus["buys"] if x["cross_party"]][:5]:
        names = ", ".join(f"{m['name'].split()[-1]}({m['party'][0]})" for m in c["members"])
        print(f"  {c['ticker']:<8} {c['member_count']} members  {c['total_value_fmt']:>8}  [{names}]")
    print(f"\nTop cross-party consensus SELLS:")
    for c in [x for x in consensus["sells"] if x["cross_party"]][:5]:
        names = ", ".join(f"{m['name'].split()[-1]}({m['party'][0]})" for m in c["members"])
        print(f"  {c['ticker']:<8} {c['member_count']} members  {c['total_value_fmt']:>8}  [{names}]")
    print(f"\nStats written → {out_path}")


if __name__ == "__main__":
    main()
