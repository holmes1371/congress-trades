#!/usr/bin/env python3
"""
build_paper_log.py — Render scoring/paper_log/positions.csv as a
styled HTML page for the static site (ROADMAP #6).

Reads the CSV ledger and produces site/paper_log.html with four
sections: a lifetime summary card, an open-positions table, a
recently-closed table (last 30 days), and — if any exist — a
retracted-positions table.

Follows build_leaderboard.py's layout conventions (dark theme, ET
timestamps, breadcrumb nav) so the two pages feel like siblings.

Usage:
    python3 build_paper_log.py               # writes site/paper_log.html
    python3 build_paper_log.py --out docs/   # custom output dir
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


PROJ = Path(__file__).resolve().parent
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))

from fetch_trades import load_bioguide_directory
from scoring.paper_log import LOG_PATH, PaperLog


DISPLAY_TZ = ZoneInfo("America/New_York")
RECENTLY_CLOSED_WINDOW_DAYS = 30


# ── Formatters ─────────────────────────────────────────────


def fmt_pct(val) -> str:
    if val in (None, "", "nan"):
        return "—"
    try:
        return f"{float(val) * 100:.2f}%"
    except (ValueError, TypeError):
        return "—"


def fmt_signed_pct(val) -> str:
    if val in (None, "", "nan"):
        return "—"
    try:
        f = float(val)
        return f"{'+' if f >= 0 else ''}{f * 100:.2f}%"
    except (ValueError, TypeError):
        return "—"


def fmt_money(val) -> str:
    if val in (None, "", "nan"):
        return "—"
    try:
        return f"${float(val):,.2f}"
    except (ValueError, TypeError):
        return "—"


def pnl_class(pnl_pct) -> str:
    try:
        f = float(pnl_pct)
    except (ValueError, TypeError):
        return ""
    return "green" if f > 0 else ("red" if f < 0 else "")


def days_held(row: dict, today: date) -> int:
    try:
        entry = date.fromisoformat(row.get("entry_date", ""))
    except ValueError:
        return 0
    ref = today
    if row.get("status") == "closed" and row.get("exit_date"):
        try:
            ref = date.fromisoformat(row["exit_date"])
        except ValueError:
            pass
    return max(0, (ref - entry).days)


# ── Name resolution ────────────────────────────────────────


def build_name_lookup() -> dict[str, str]:
    """bioguide → full name. Falls back to bioguide if
    `member_bioguide.json` isn't loadable or a bioguide isn't found
    at render time."""
    directory = load_bioguide_directory()
    return {bid: entry.get("fullName", bid) for bid, entry in directory.items()}


def display_name(row: dict, name_lookup: dict[str, str]) -> str:
    bid = row.get("bioguide", "")
    return name_lookup.get(bid, bid)


# ── Table builders ─────────────────────────────────────────


def build_open_rows(log: PaperLog, today: date, name_lookup: dict[str, str]) -> str:
    rows = sorted(log.open_rows(), key=lambda r: r.get("entry_date", ""), reverse=True)
    if not rows:
        return (
            '<tr><td colspan="6" class="empty-row">'
            'No open positions yet. The log accumulates from the first '
            'pipeline run after this feature lands.'
            '</td></tr>'
        )
    html = []
    for r in rows:
        html.append(
            f"<tr>"
            f"<td>{r.get('entry_date','')}</td>"
            f"<td>{days_held(r, today)}d</td>"
            f"<td>{display_name(r, name_lookup)}</td>"
            f"<td class='ticker'>{r.get('ticker','')}</td>"
            f"<td>{fmt_money(r.get('entry_close'))}</td>"
            f"<td class='{pnl_class(r.get('pnl_pct'))}'>{fmt_signed_pct(r.get('pnl_pct'))}</td>"
            f"</tr>"
        )
    return "\n      ".join(html)


def build_closed_rows(
    log: PaperLog, today: date, name_lookup: dict[str, str],
    days_window: int = RECENTLY_CLOSED_WINDOW_DAYS,
) -> str:
    cutoff = today - timedelta(days=days_window)
    eligible = []
    for r in log.closed_rows():
        try:
            exit_d = date.fromisoformat(r.get("exit_date", ""))
        except ValueError:
            continue
        if exit_d >= cutoff:
            eligible.append(r)
    eligible.sort(key=lambda r: r.get("exit_date", ""), reverse=True)
    if not eligible:
        return (
            '<tr><td colspan="8" class="empty-row">'
            'No closed positions in the last 30 days.'
            '</td></tr>'
        )
    html = []
    for r in eligible:
        html.append(
            f"<tr>"
            f"<td>{r.get('exit_date','')}</td>"
            f"<td>{days_held(r, today)}d</td>"
            f"<td>{display_name(r, name_lookup)}</td>"
            f"<td class='ticker'>{r.get('ticker','')}</td>"
            f"<td>{fmt_money(r.get('entry_close'))}</td>"
            f"<td>{fmt_money(r.get('exit_close'))}</td>"
            f"<td class='{pnl_class(r.get('pnl_pct'))}'>{fmt_signed_pct(r.get('pnl_pct'))}</td>"
            f"<td class='{pnl_class(r.get('alpha_vs_spy'))}'>{fmt_signed_pct(r.get('alpha_vs_spy'))}</td>"
            f"</tr>"
        )
    return "\n      ".join(html)


def build_retracted_rows(log: PaperLog, name_lookup: dict[str, str]) -> str:
    retracted = [r for r in log.rows if r.get("status") == "retracted"]
    retracted.sort(key=lambda r: r.get("retracted_at", ""), reverse=True)
    html = []
    for r in retracted:
        html.append(
            f"<tr>"
            f"<td>{r.get('retracted_at','')}</td>"
            f"<td>{display_name(r, name_lookup)}</td>"
            f"<td class='ticker'>{r.get('ticker','')}</td>"
            f"<td>{r.get('signal_date','')}</td>"
            f"<td>{fmt_money(r.get('entry_close'))}</td>"
            f"</tr>"
        )
    return "\n      ".join(html)


# ── Lifetime summary ───────────────────────────────────────


def lifetime_summary(log: PaperLog) -> dict:
    closed = log.closed_rows()
    if not closed:
        return {
            "n_closed": 0, "mean_return": None, "mean_alpha_vs_spy": None,
            "hit_rate": None, "n_open": len(log.open_rows()),
            "n_retracted": sum(1 for r in log.rows if r.get("status") == "retracted"),
        }
    returns = [float(r["pnl_pct"]) for r in closed if r.get("pnl_pct") not in (None, "", "nan")]
    alphas = [float(r["alpha_vs_spy"]) for r in closed if r.get("alpha_vs_spy") not in (None, "", "nan")]
    hit = sum(1 for a in alphas if a > 0) / len(alphas) if alphas else None
    return {
        "n_closed":          len(closed),
        "n_open":            len(log.open_rows()),
        "n_retracted":       sum(1 for r in log.rows if r.get("status") == "retracted"),
        "mean_return":       sum(returns) / len(returns) if returns else None,
        "mean_alpha_vs_spy": sum(alphas) / len(alphas) if alphas else None,
        "hit_rate":          hit,
    }


def build_summary_card(log: PaperLog) -> str:
    s = lifetime_summary(log)
    return (
        '<div class="weights-card">'
        '<h3>Lifetime Summary</h3>'
        '<ul>'
        f'<li><strong>Open positions:</strong> {s["n_open"]}</li>'
        f'<li><strong>Closed positions:</strong> {s["n_closed"]}</li>'
        f'<li><strong>Retracted:</strong> {s["n_retracted"]}</li>'
        f'<li><strong>Mean per-trade return:</strong> {fmt_signed_pct(s["mean_return"])}</li>'
        f'<li><strong>Mean per-trade &alpha; vs SPY:</strong> {fmt_signed_pct(s["mean_alpha_vs_spy"])}</li>'
        f'<li><strong>Hit rate (&alpha; &gt; 0):</strong> {fmt_pct(s["hit_rate"])}</li>'
        '</ul>'
        '</div>'
    )


# ── Page template ──────────────────────────────────────────


PAGE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Auto Paper-Trading Log — Congressional Trade Intelligence</title>
<style>
  :root {{
    --bg: #0f1117; --surface: #1a1d27; --surface2: #22263a;
    --accent: #4f8ef7; --green: #22c55e; --red: #ef4444;
    --yellow: #f59e0b; --text: #e2e8f0; --muted: #64748b;
    --border: #2e3450;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: var(--bg); color: var(--text);
    padding: 32px 24px; max-width: 1200px; margin: 0 auto;
  }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  h1 {{ font-size: 1.6rem; font-weight: 700; color: var(--accent); margin-bottom: 4px; }}
  .breadcrumb {{ font-size: 0.82rem; color: var(--muted); margin-bottom: 24px; }}
  .subtitle {{ font-size: 0.88rem; color: var(--muted); margin-bottom: 28px; line-height: 1.6; }}
  .section-title {{
    font-size: 1.05rem; font-weight: 700; color: var(--accent);
    margin: 28px 0 14px; padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
  }}
  .table-wrap {{ width: 100%; overflow-x: auto; margin-bottom: 28px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  th {{
    text-align: left; padding: 8px 10px;
    background: var(--surface2); color: var(--muted);
    font-weight: 600; font-size: 0.73rem;
    text-transform: uppercase; letter-spacing: 0.04em;
  }}
  td {{ padding: 7px 10px; border-bottom: 1px solid var(--border); vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover {{ background: rgba(79,142,247,0.04); }}
  .ticker {{ font-family: 'SFMono-Regular', Consolas, monospace; font-weight: 600; }}
  .green {{ color: var(--green); }}
  .red {{ color: var(--red); }}
  .empty-row {{ color: var(--muted); font-style: italic; text-align: center; padding: 20px; }}
  .weights-card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 18px; margin-bottom: 28px;
    font-size: 0.84rem;
  }}
  .weights-card h3 {{ font-size: 0.85rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 10px; }}
  .weights-card ul {{ list-style: none; display: flex; flex-wrap: wrap; gap: 12px 24px; }}
  .weights-card li {{ color: var(--text); }}
  .weights-card strong {{ color: var(--accent); }}
  .footer {{
    font-size: 0.75rem; color: var(--muted); margin-top: 32px;
    padding: 14px; background: var(--surface); border-radius: 8px; line-height: 1.6;
  }}
</style>
</head>
<body>

<p class="breadcrumb"><a href="index.html">&larr; Back to Reports</a> &nbsp;&middot;&nbsp; <a href="leaderboard.html">Member Leaderboard</a></p>
<h1>Auto Paper-Trading Log</h1>
<p class="subtitle">
  Prospective track record — every BUY from a top-15 composite cohort member is entered at the
  next available close on or after <code>today + 1 calendar day</code> and held for 60 business days.
  Entry / exit / mark-to-market are mechanical; cohort selection snapshots when the signal first
  enters the log (see <a href="leaderboard.html">Member Leaderboard</a> for the composite that
  drives selection). Data as of {data_date}.
</p>

{summary_card}

<div class="section-title">Open Positions</div>
<div class="table-wrap"><table>
  <thead><tr>
    <th>Entry Date</th><th>Days Held</th><th>Member</th><th>Ticker</th>
    <th>Entry</th><th>PnL</th>
  </tr></thead>
  <tbody>
    {open_rows}
  </tbody>
</table></div>

<div class="section-title">Recently Closed (last 30 days)</div>
<div class="table-wrap"><table>
  <thead><tr>
    <th>Exit Date</th><th>Days Held</th><th>Member</th><th>Ticker</th>
    <th>Entry</th><th>Exit</th><th>Return</th><th>&alpha; vs SPY</th>
  </tr></thead>
  <tbody>
    {closed_rows}
  </tbody>
</table></div>

{retracted_section}

<div class="footer">
  Paper-trading log is prospective-only — it accumulates from the first pipeline run after the
  feature landed, not backfilled from historical signals. PnL is gross of transaction costs and
  taxes; a cost overlay is tracked as ROADMAP #7. This is for informational purposes only and
  does not constitute investment advice.
  <br>Last built: {build_time}
</div>

</body>
</html>
"""


def build_retracted_section(log: PaperLog, name_lookup: dict[str, str]) -> str:
    """Only emit the retracted-positions block if there are any — keeps
    the page clean during the common case where no disclosures have
    been corrected."""
    retracted = [r for r in log.rows if r.get("status") == "retracted"]
    if not retracted:
        return ""
    rows_html = build_retracted_rows(log, name_lookup)
    return (
        '<div class="section-title">Retracted Disclosures</div>'
        '<div class="table-wrap"><table>'
        '<thead><tr>'
        '<th>Retracted Date</th><th>Member</th><th>Ticker</th>'
        '<th>Signal Date</th><th>Entry</th>'
        '</tr></thead><tbody>'
        f'{rows_html}'
        '</tbody></table></div>'
    )


# ── Main ───────────────────────────────────────────────────


def render_page(log: PaperLog, today: date, name_lookup: dict[str, str]) -> str:
    """Render the full HTML page. Separated from `main()` so tests can
    call it directly with a constructed PaperLog and a fixed today."""
    return PAGE_TEMPLATE.format(
        data_date=today.strftime("%b %d, %Y"),
        summary_card=build_summary_card(log),
        open_rows=build_open_rows(log, today, name_lookup),
        closed_rows=build_closed_rows(log, today, name_lookup),
        retracted_section=build_retracted_section(log, name_lookup),
        build_time=(
            datetime.now(timezone.utc)
            .astimezone(DISPLAY_TZ)
            .strftime("%b %d, %Y at %I:%M %p ET")
        ),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site", help="Output directory")
    ap.add_argument("--log-path", default=str(LOG_PATH),
                    help="Path to positions.csv ledger")
    args = ap.parse_args()

    log = PaperLog(Path(args.log_path))
    name_lookup = build_name_lookup()
    today = date.today()

    html = render_page(log, today, name_lookup)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "paper_log.html"
    out_path.write_text(html, encoding="utf-8")

    s = lifetime_summary(log)
    print(f"built {out_path} "
          f"(open={s['n_open']}, closed={s['n_closed']}, "
          f"retracted={s['n_retracted']})")


if __name__ == "__main__":
    main()
