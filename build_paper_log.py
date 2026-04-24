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
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


PROJ = Path(__file__).resolve().parent
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))

from fetch_trades import load_bioguide_directory
from scoring.paper_log import LOG_PATH, OVERLAYS_PATH, PaperLog
from scoring.costs import (
    SLIPPAGE_BPS_TIERS,
    apply_slippage,
    apply_tax,
)


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


def _net_pnl_for_row(row: dict, overlays: dict) -> float | None:
    """Apply the overlays' slippage + tax haircut to a single closed
    row's gross pnl_pct. Returns None on a malformed row (non-numeric
    pnl_pct)."""
    try:
        gross = float(row["pnl_pct"])
    except (ValueError, TypeError, KeyError):
        return None
    ticker = row.get("ticker", "")
    # Fallback to the small-cap tier bps when the ticker isn't in the
    # sidecar — matches classify_tier(None) → 'small', conservative.
    bps = overlays.get("slippage_bps_by_ticker", {}).get(ticker, SLIPPAGE_BPS_TIERS["small"])
    return apply_tax(apply_slippage(gross, bps), overlays.get("tax_rate", 0.0))


def lifetime_summary(log: PaperLog, overlays: dict | None = None) -> dict:
    closed = log.closed_rows()
    base = {
        "n_open":            len(log.open_rows()),
        "n_retracted":       sum(1 for r in log.rows if r.get("status") == "retracted"),
        "overlays":          overlays,
    }
    if not closed:
        return {
            **base,
            "n_closed": 0, "mean_return": None, "mean_alpha_vs_spy": None,
            "hit_rate": None,
            "mean_return_net": None, "mean_alpha_vs_spy_net": None,
            "hit_rate_net": None,
        }
    returns = [float(r["pnl_pct"]) for r in closed if r.get("pnl_pct") not in (None, "", "nan")]
    alphas = [float(r["alpha_vs_spy"]) for r in closed if r.get("alpha_vs_spy") not in (None, "", "nan")]
    hit = sum(1 for a in alphas if a > 0) / len(alphas) if alphas else None

    # Net-of-overlay aggregates. When overlays is None, net fields are
    # None — the render shows em-dash. When present, apply per-ticker
    # slippage + gain-only tax to each row's pnl_pct (and to the same
    # row's alpha by subtracting the implied SPY return: spy_return =
    # gross_pnl - gross_alpha, so net_alpha = net_pnl - spy_return).
    mean_return_net: float | None = None
    mean_alpha_vs_spy_net: float | None = None
    hit_rate_net: float | None = None
    if overlays is not None:
        net_returns: list[float] = []
        net_alphas: list[float] = []
        for r in closed:
            net_pnl = _net_pnl_for_row(r, overlays)
            if net_pnl is None:
                continue
            net_returns.append(net_pnl)
            try:
                gross_pnl = float(r["pnl_pct"])
                gross_alpha = float(r["alpha_vs_spy"])
            except (ValueError, TypeError, KeyError):
                continue
            spy_return = gross_pnl - gross_alpha  # benchmark stays gross
            net_alphas.append(net_pnl - spy_return)
        if net_returns:
            mean_return_net = sum(net_returns) / len(net_returns)
        if net_alphas:
            mean_alpha_vs_spy_net = sum(net_alphas) / len(net_alphas)
            hit_rate_net = sum(1 for a in net_alphas if a > 0) / len(net_alphas)

    return {
        **base,
        "n_closed":              len(closed),
        "mean_return":           sum(returns) / len(returns) if returns else None,
        "mean_alpha_vs_spy":     sum(alphas) / len(alphas) if alphas else None,
        "hit_rate":              hit,
        "mean_return_net":       mean_return_net,
        "mean_alpha_vs_spy_net": mean_alpha_vs_spy_net,
        "hit_rate_net":          hit_rate_net,
    }


def build_summary_card(log: PaperLog, overlays: dict | None = None) -> str:
    s = lifetime_summary(log, overlays=overlays)
    overlay_footer = ""
    if overlays is not None:
        overlay_footer = (
            '<p class="overlay-config">'
            f'Net applies: slippage <code>{overlays.get("slippage_mode", "?")}</code>, '
            f'tax <code>{overlays.get("tax_rate", 0.0):.4f}</code>, '
            f'sizing <code>{overlays.get("sizing_mode", "?")}</code>.'
            '</p>'
        )
    return (
        '<div class="weights-card">'
        '<h3>Lifetime Summary</h3>'
        '<ul>'
        f'<li><strong>Open positions:</strong> {s["n_open"]}</li>'
        f'<li><strong>Closed positions:</strong> {s["n_closed"]}</li>'
        f'<li><strong>Retracted:</strong> {s["n_retracted"]}</li>'
        f'<li><strong>Mean per-trade return:</strong> '
        f'Gross {fmt_signed_pct(s["mean_return"])} '
        f'&middot; Net {fmt_signed_pct(s["mean_return_net"])}</li>'
        f'<li><strong>Mean per-trade &alpha; vs SPY:</strong> '
        f'Gross {fmt_signed_pct(s["mean_alpha_vs_spy"])} '
        f'&middot; Net {fmt_signed_pct(s["mean_alpha_vs_spy_net"])}</li>'
        f'<li><strong>Hit rate (&alpha; &gt; 0):</strong> '
        f'Gross {fmt_pct(s["hit_rate"])} '
        f'&middot; Net {fmt_pct(s["hit_rate_net"])}</li>'
        '</ul>'
        f'{overlay_footer}'
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
  .overlay-config {{ font-size: 0.75rem; color: var(--muted); margin-top: 10px; }}
  .overlay-config code {{ color: var(--text); background: var(--surface2); padding: 1px 5px; border-radius: 3px; }}
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
  feature landed, not backfilled from historical signals. Per-row PnL is gross; the lifetime
  summary above shows Gross and Net (after slippage + gain-only short-term tax) side by side.
  This is for informational purposes only and does not constitute investment advice.
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


def render_page(
    log: PaperLog, today: date, name_lookup: dict[str, str],
    *, overlays: dict | None = None,
) -> str:
    """Render the full HTML page. Separated from `main()` so tests can
    call it directly with a constructed PaperLog and a fixed today."""
    return PAGE_TEMPLATE.format(
        data_date=today.strftime("%b %d, %Y"),
        summary_card=build_summary_card(log, overlays=overlays),
        open_rows=build_open_rows(log, today, name_lookup),
        closed_rows=build_closed_rows(log, today, name_lookup),
        retracted_section=build_retracted_section(log, name_lookup),
        build_time=(
            datetime.now(timezone.utc)
            .astimezone(DISPLAY_TZ)
            .strftime("%b %d, %Y at %I:%M %p ET")
        ),
    )


def load_overlays(log_path: Path) -> dict | None:
    """Read scoring/paper_log/overlays.json alongside the ledger.
    Returns None when absent — the renderer falls back to gross-only
    output so the page builds cleanly before the first `paper_log.py`
    run writes a sidecar."""
    sidecar = log_path.parent / OVERLAYS_PATH.name
    if not sidecar.exists():
        return None
    return json.loads(sidecar.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site", help="Output directory")
    ap.add_argument("--log-path", default=str(LOG_PATH),
                    help="Path to positions.csv ledger")
    args = ap.parse_args()

    log_path = Path(args.log_path)
    log = PaperLog(log_path)
    overlays = load_overlays(log_path)
    name_lookup = build_name_lookup()
    today = date.today()

    html = render_page(log, today, name_lookup, overlays=overlays)

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
