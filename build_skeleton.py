"""
build_skeleton.py — Analysis Skeleton Builder
==============================================
Reads computed_stats.json and produces analysis_skeleton.json with every
mechanical field pre-built. The agent only needs to fill in 4 prose fields:

  • summary_alerts[].html         — narrative around each headline signal
  • member_sections .obs blocks   — 2-3 sentence per-member observation
  • ranked_ideas_rows rationales  — 1-line "why this matters" for each idea
  • (optional) custom title       — defaults to "Congressional Trade Intelligence Report"

Prose placeholders are wrapped in `[[FILL: ...]]` so they're easy to grep.

Usage:
    python build_skeleton.py
    python build_skeleton.py --in computed_stats.json --out analysis_skeleton.json
"""

import argparse
import json
from datetime import date
from pathlib import Path


# ── chamber/state lookup is in member_stats already; no extra config needed ──


# ── Formatting helpers ────────────────────────────────────────────────────────

def _party_short(party: str) -> str:
    return "D" if party.startswith("Democrat") else "R"


def _party_class(party: str) -> str:
    return "dem" if party.startswith("Democrat") else "rep"


def _bias_class(bias: str) -> str:
    b = bias.lower()
    if "bull" in b: return "bullish"
    if "bear" in b: return "bearish"
    return "mixed"


def _fmt_window(meta: dict) -> str:
    """'Jan 7 – Apr 7, 2026 (60 days)' style string from source metadata."""
    try:
        start = date.fromisoformat(meta["cutoff_date"])
        end   = date.fromisoformat(meta["generated"])
        if start.year == end.year:
            return f"{start.strftime('%b %-d')} – {end.strftime('%b %-d, %Y')} ({meta['window_days']} days)"
        return f"{start.strftime('%b %-d, %Y')} – {end.strftime('%b %-d, %Y')} ({meta['window_days']} days)"
    except (KeyError, ValueError):
        return f"{meta.get('window_days','?')} days"


def _fmt_date(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%b %-d, %Y")
    except ValueError:
        return iso


# ── Strength stars ────────────────────────────────────────────────────────────

def _stars(member_count: int, cross_party: bool, total_value: int) -> tuple[str, str, str]:
    """Returns (star_html, label, color_class)."""
    if cross_party and member_count >= 3:
        return "★★★", "Very High", "green"
    if cross_party or member_count >= 3:
        return "★★☆", "High", "green"
    if member_count >= 2 or total_value >= 150_000:
        return "★★☆", "High", "green"
    return "★☆☆", "Moderate", "yellow"


def _conviction_stars(pattern: dict) -> tuple[str, str]:
    val = pattern.get("total_value") or pattern.get("value") or 0
    cnt = pattern.get("count") or 1
    if cnt >= 5 or val >= 500_000:
        return "★★★", "Very High"
    if cnt >= 3 or val >= 150_000:
        return "★★☆", "High"
    return "★☆☆", "Moderate"


# ── Builders ──────────────────────────────────────────────────────────────────

def _fmt_last_trade(iso_date: str | None) -> str:
    """ISO date (YYYY-MM-DD) → 'Apr 5, 2026'. Empty string on missing/invalid."""
    if not iso_date:
        return "—"
    try:
        d = date.fromisoformat(iso_date[:10])
    except ValueError:
        return iso_date
    return d.strftime("%b %-d, %Y") if hasattr(date, "strftime") else d.strftime("%b %d, %Y")


def build_overview_rows(member_stats: dict) -> str:
    rows = []
    # Order by total_trades desc
    ordered = sorted(member_stats.items(), key=lambda kv: kv[1]["total_trades"], reverse=True)
    for name, m in ordered:
        last_trade = _fmt_last_trade(m.get("most_recent_trade"))
        # data-sort carries the raw ISO string so the column sorts chronologically
        last_sort = (m.get("most_recent_trade") or "")[:10]
        rows.append(
            f'<tr>'
            f'<td><strong>{name}</strong></td>'
            f'<td><span class="badge {_party_class(m["party"])}">{_party_short(m["party"])}</span></td>'
            f'<td>{m["chamber"]} · {m["state"]}</td>'
            f'<td>{m["total_trades"]}</td>'
            f'<td>{m["equity_trades"]}</td>'
            f'<td class="green">{m["buys"]}</td>'
            f'<td class="red">{m["sells"]}</td>'
            f'<td class="green">{m["buy_vol_fmt"]}</td>'
            f'<td class="red">{m["sell_vol_fmt"]}</td>'
            f'<td data-sort="{last_sort}">{last_trade}</td>'
            f'<td><span class="badge {_bias_class(m["bias"])}">{m["bias"]}</span></td>'
            f'</tr>'
        )
    return "".join(rows)


def build_sector_html(sector_totals: list) -> str:
    cards = []
    # Sort by activity (buy + sell volume)
    ordered = sorted(sector_totals, key=lambda s: s["buy_vol"] + s["sell_vol"], reverse=True)[:9]
    for s in ordered:
        title = s["sector"].replace("-", " ").title()
        cards.append(
            f'<div class="card"><h3>{title}</h3>'
            f'<div class="stat-row"><span class="stat-label">Buy Volume</span><span class="stat-val green">{s["buy_vol_fmt"]}</span></div>'
            f'<div class="stat-row"><span class="stat-label">Sell Volume</span><span class="stat-val red">{s["sell_vol_fmt"]}</span></div>'
            f'<div class="stat-row"><span class="stat-label">Net Bias</span><span class="stat-val">{s["net_direction"]}</span></div>'
            f'</div>'
        )
    return f'<div class="grid-3">{"".join(cards)}</div>'


def build_member_sections(member_stats: dict) -> str:
    blocks = []
    ordered = sorted(member_stats.items(), key=lambda kv: kv[1]["total_trades"], reverse=True)
    for name, m in ordered:
        top_buys = m.get("top_buy_tickers") or []
        chips = " ".join(
            f'<span class="ticker buy-t">{t["ticker"]}</span>'
            for t in top_buys[:6]
        ) or '<span class="no-data">No disclosed buys</span>'

        top_sector = ""
        sb = m.get("sector_breakdown") or []
        if sb:
            # Pick the sector with the largest buy volume
            top = max(sb, key=lambda s: s.get("buy", 0))
            top_sector = top["sector"].replace("-", " ").title()

        blocks.append(
            f'<div class="section-title">👤 {name} — {_party_short(m["party"])} · {m["chamber"]} · {m["state"]}</div>'
            f'<div class="grid">'
            f'  <div class="card"><h3>Stats</h3>'
            f'    <div class="stat-row"><span class="stat-label">Public Trades</span><span class="stat-val">{m["total_trades"]}</span></div>'
            f'    <div class="stat-row"><span class="stat-label">Buy / Sell</span><span class="stat-val green">{m["buys"]}</span> / <span class="stat-val red">{m["sells"]}</span></div>'
            f'    <div class="stat-row"><span class="stat-label">Buy Volume</span><span class="stat-val green">{m["buy_vol_fmt"]}</span></div>'
            f'    <div class="stat-row"><span class="stat-label">Sell Volume</span><span class="stat-val red">{m["sell_vol_fmt"]}</span></div>'
            f'    <div class="stat-row"><span class="stat-label">Bias</span><span class="stat-val">{m["bias"]}</span></div>'
            f'    <div class="stat-row"><span class="stat-label">Top Sector</span><span class="stat-val">{top_sector or "—"}</span></div>'
            f'  </div>'
            f'  <div class="card"><h3>Top Buys</h3>{chips}</div>'
            f'  <div class="card" style="grid-column: 1/-1"><h3>Observation</h3>'
            f'    <p class="obs">[[FILL: 2-3 sentence observation about {name}\'s pattern — sector concentration, posture, what the activity implies]]</p>'
            f'  </div>'
            f'</div>'
        )
    return "".join(blocks)


def build_ranked_ideas(consensus: dict, conviction: list) -> str:
    """Top 10 ranked ideas, mechanically ordered. Rationale prose left for the agent."""
    ideas = []

    # Cross-party consensus first (buys then sells, sorted by member_count desc, then value)
    for c in consensus.get("buys", []):
        if c.get("cross_party"):
            ideas.append(("buy", c, "consensus"))
    for c in consensus.get("sells", []):
        if c.get("cross_party"):
            ideas.append(("sell", c, "consensus"))

    # Same-party consensus
    for c in consensus.get("buys", []):
        if not c.get("cross_party"):
            ideas.append(("buy", c, "consensus"))
    for c in consensus.get("sells", []):
        if not c.get("cross_party"):
            ideas.append(("sell", c, "consensus"))

    # Conviction patterns
    for p in conviction:
        ideas.append(("conviction", p, "conviction"))

    # Dedupe by (ticker, action), keep first occurrence
    seen = set()
    deduped = []
    for kind, item, source in ideas:
        ticker = item["ticker"]
        action = "BUY" if kind == "buy" or (kind == "conviction" and item.get("type") != "repeated_sell" and item.get("trade_type") != "SELL") else "SELL"
        key = (ticker, action)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((kind, item, source, action))
        if len(deduped) >= 10:
            break

    rows = []
    for rank, (kind, item, source, action) in enumerate(deduped, start=1):
        ticker = item["ticker"]

        if source == "consensus":
            mc = item["member_count"]
            xp = item.get("cross_party", False)
            val = item.get("total_value", 0)
            stars, label, color = _stars(mc, xp, val)
            ticker_cls = "con" if action == "BUY" else "con-sell"
            members = ", ".join(mem["name"].split()[-1] for mem in item["members"])
        else:  # conviction
            stars, label = _conviction_stars(item)
            color = "green" if action == "BUY" else "red"
            ticker_cls = "buy-t" if action == "BUY" else "sell-t"
            members = item["member"].split()[-1]

        action_cls = "buy" if action == "BUY" else "sell"

        rows.append(
            f'<tr>'
            f'<td><span class="rank-num">{rank}</span></td>'
            f'<td><span class="ticker {ticker_cls}">{ticker}</span></td>'
            f'<td><span class="badge {action_cls}">{action}</span></td>'
            f'<td class="{color}"><span class="star">{stars}</span> {label}</td>'
            f'<td>{members}</td>'
            f'<td>[[FILL:idea:{ticker}_{action}: 1-line rationale for {ticker} {action} — what the signal implies]]</td>'
            f'</tr>'
        )
    return "".join(rows)


def build_summary_alerts(consensus: dict, conviction: list) -> list:
    """Pre-build up to 7 headline alerts: top cross-party signals + top conviction."""
    alerts = []

    # Top 3 cross-party buys
    xp_buys = [c for c in consensus.get("buys", []) if c.get("cross_party")][:3]
    for c in xp_buys:
        members = " + ".join(f"{m['name'].split()[-1]} ({_party_short(m['party'])})" for m in c["members"])
        alerts.append({
            "id": f'consensus_buy_{c["ticker"]}',
            "ticker": c["ticker"],
            "type": "blue",
            "html": (
                f'<strong>CONSENSUS BUY — {c["ticker"]} ({members}, cross-party)</strong><br>'
                f'{c["member_count"]} members, combined disclosed value {c.get("total_value_fmt","")}. '
                f'[[FILL:alert:consensus_buy_{c["ticker"]}: 1-2 sentences on what this signal implies]]'
            ),
        })

    # Top 3 cross-party sells
    xp_sells = [c for c in consensus.get("sells", []) if c.get("cross_party")][:3]
    for c in xp_sells:
        members = " + ".join(f"{m['name'].split()[-1]} ({_party_short(m['party'])})" for m in c["members"])
        alerts.append({
            "id": f'consensus_sell_{c["ticker"]}',
            "ticker": c["ticker"],
            "type": "red",
            "html": (
                f'<strong>CONSENSUS SELL — {c["ticker"]} ({members}, cross-party)</strong><br>'
                f'{c["member_count"]} members, combined disclosed value {c.get("total_value_fmt","")}. '
                f'[[FILL:alert:consensus_sell_{c["ticker"]}: 1-2 sentences on what this signal implies]]'
            ),
        })

    # Top conviction pattern
    if conviction:
        p = conviction[0]
        val = p.get("value_fmt") or p.get("total_value_fmt") or ""
        cnt = p.get("count")
        cnt_str = f", {cnt} purchases" if cnt else ""
        last = p["member"].split()[-1]
        aid = f'conviction_{last}_{p["ticker"]}'
        alerts.append({
            "id": aid,
            "ticker": p["ticker"],
            "type": "yellow",
            "html": (
                f'<strong>CONVICTION — {p["member"]} {p["ticker"]} {val}{cnt_str}</strong><br>'
                f'[[FILL:alert:{aid}: 1-2 sentences on why this single-member pattern matters]]'
            ),
        })

    # Mechanical fallback: if neither consensus nor conviction produced any
    # alert, surface a neutral note so the executive summary makes clear that
    # the empty section reflects the data, not a computation failure.
    if not alerts:
        alerts.append({
            "id": "no_signals",
            "type": "gray",
            "html": (
                "<strong>NO SIGNALS DETECTED</strong><br>"
                "No two members on this committee disclosed trades in the same "
                "ticker during the window, and no single-member position met the "
                "conviction threshold. The empty signals section reflects the "
                "underlying data — it is not a computation error."
            ),
        })

    return alerts


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--in",  dest="infile",  default="computed_stats/computed_stats.json")
    parser.add_argument("--out", dest="outfile", default="analysis_skeleton/analysis_skeleton.json")
    args = parser.parse_args()

    in_path  = Path(__file__).parent / args.infile
    out_path = Path(__file__).parent / args.outfile
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(in_path, encoding="utf-8") as f:
        stats = json.load(f)

    meta          = stats["source_metadata"]
    member_stats  = stats["member_stats"]
    consensus     = stats["consensus"]
    conviction    = stats["conviction"]
    sector_totals = stats["sector_totals"]

    members_str = " · ".join(member_stats.keys())

    skeleton = {
        "title":   "Congressional Trade Intelligence Report",
        "date":    _fmt_date(meta["generated"]),
        "window":  _fmt_window(meta),
        "members": members_str,
        "source":  meta.get("source", "Capitol Trades"),

        "summary_alerts":      build_summary_alerts(consensus, conviction),
        "overview_table_rows": build_overview_rows(member_stats),
        "ranked_ideas_rows":   build_ranked_ideas(consensus, conviction),
        "member_sections":     build_member_sections(member_stats),
        "sector_html":         build_sector_html(sector_totals),
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(skeleton, f, indent=2, ensure_ascii=False)

    # Timestamped archive copy alongside the current file in analysis_skeleton/
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = out_path.parent / f"{out_path.stem}_{ts}.json"
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(skeleton, f, indent=2, ensure_ascii=False)
    print(f"Archived → {archive_path}")

    print(f"Skeleton written → {out_path}")
    print(f"  {len(skeleton['summary_alerts'])} summary alert shells")
    print(f"  {len(member_stats)} member sections")
    print(f"  Prose placeholders: search for [[FILL:")


if __name__ == "__main__":
    main()
