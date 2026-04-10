"""
generate_report.py — Congressional Trade Report Builder
========================================================
Reads an analysis JSON file (built by the agent on top of analysis_skeleton.json)
and wraps it in the styled HTML report shell.

Usage:
    python generate_report.py analysis.json
    python generate_report.py analysis.json --out custom/path.html
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

CSS = """
  :root {
    --bg: #0f1117; --surface: #1a1d27; --surface2: #22263a;
    --accent: #4f8ef7; --green: #22c55e; --red: #ef4444;
    --yellow: #f59e0b; --text: #e2e8f0; --muted: #64748b;
    --border: #2e3450;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); padding: 24px; max-width: 1400px; margin: 0 auto; }
  h1  { font-size: 1.6rem; font-weight: 700; color: var(--accent); }
  h2  { font-size: 1.15rem; font-weight: 600; color: var(--text); margin-bottom: 12px; }
  h3  { font-size: 0.85rem; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; }
  .header { display: flex; align-items: baseline; gap: 16px; margin-bottom: 6px; }
  .meta   { font-size: 0.8rem; color: var(--muted); margin-bottom: 28px; }
  .grid   { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .grid-3 { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin-bottom: 24px; }
  .card   { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 18px; }
  .card.highlight { border-color: var(--accent); }
  .card.warn      { border-color: var(--red); }
  .badge { display: inline-block; font-size: 0.7rem; font-weight: 700; padding: 2px 8px; border-radius: 99px; text-transform: uppercase; letter-spacing: 0.04em; }
  .badge.buy     { background: rgba(34,197,94,0.15);  color: var(--green); }
  .badge.sell    { background: rgba(239,68,68,0.15);  color: var(--red); }
  .badge.dem     { background: rgba(59,130,246,0.15); color: #60a5fa; }
  .badge.rep     { background: rgba(239,68,68,0.15);  color: #f87171; }
  .badge.bullish { background: rgba(34,197,94,0.15);  color: var(--green); }
  .badge.bearish { background: rgba(239,68,68,0.15);  color: var(--red); }
  .badge.mixed   { background: rgba(245,158,11,0.15); color: var(--yellow); }
  .badge.neutral { background: rgba(100,116,139,0.15);color: var(--muted); }
  .stat-row { display: flex; justify-content: space-between; align-items: center; padding: 5px 0; border-bottom: 1px solid var(--border); font-size: 0.84rem; }
  .stat-row:last-child { border-bottom: none; }
  .stat-label { color: var(--muted); }
  .stat-val   { font-weight: 600; }
  .green  { color: var(--green); }
  .red    { color: var(--red); }
  .yellow { color: var(--yellow); }
  .ticker { display: inline-block; background: var(--surface2); border: 1px solid var(--border); border-radius: 6px; padding: 3px 9px; font-size: 0.78rem; font-weight: 700; }
  .ticker.buy-t    { border-color: rgba(34,197,94,0.45); color: var(--green); }
  .ticker.sell-t   { border-color: rgba(239,68,68,0.45); color: var(--red); }
  .ticker.con      { border-color: var(--accent); color: var(--accent); background: rgba(79,142,247,0.08); }
  .ticker.con-sell { border-color: rgba(239,68,68,0.6); color: var(--red); background: rgba(239,68,68,0.08); }
  .trade-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
  .trade-table th { text-align: left; padding: 6px 10px; background: var(--surface2); color: var(--muted); font-weight: 600; font-size: 0.73rem; text-transform: uppercase; }
  .trade-table td { padding: 6px 10px; border-bottom: 1px solid var(--border); vertical-align: middle; }
  .trade-table tr:last-child td { border-bottom: none; }
  .section-title { font-size: 1.0rem; font-weight: 700; color: var(--accent); margin: 28px 0 14px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
  .alert { background: rgba(79,142,247,0.08); border: 1px solid rgba(79,142,247,0.3); border-radius: 8px; padding: 14px 16px; font-size: 0.85rem; margin-bottom: 14px; line-height: 1.65; }
  .alert.red-alert { background: rgba(239,68,68,0.08); border-color: rgba(239,68,68,0.3); }
  .alert.yellow-alert { background: rgba(245,158,11,0.08); border-color: rgba(245,158,11,0.3); }
  .alert.gray-alert { background: rgba(100,116,139,0.08); border-color: rgba(100,116,139,0.3); }
  .alert strong { color: var(--accent); }
  .alert.red-alert strong { color: #f87171; }
  .alert.yellow-alert strong { color: var(--yellow); }
  .alert.gray-alert strong { color: var(--muted); }
  .obs     { font-size: 0.84rem; line-height: 1.7; color: var(--text); }
  .disclaimer { font-size: 0.75rem; color: var(--muted); margin-top: 32px; padding: 14px; background: var(--surface); border-radius: 8px; line-height: 1.6; }
  .rank-num { font-size: 1.0rem; font-weight: 800; color: var(--muted); width: 24px; }
  .star { color: var(--yellow); }
  .table-wrap { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }
@media (max-width: 720px) {
  body { padding: 14px; }
  h1 { font-size: 1.3rem; }
  h2 { font-size: 1.0rem; }
  .header { flex-wrap: wrap; gap: 6px; }
  .meta { margin-bottom: 18px; }
  .grid, .grid-3 { grid-template-columns: 1fr; gap: 12px; margin-bottom: 16px; }
  .card { padding: 14px; }
  .section-title { font-size: 0.95rem; margin: 20px 0 10px; }
  .alert { font-size: 0.8rem; padding: 12px; }
  .trade-table { display: block; width: 100%; overflow-x: auto; white-space: nowrap; font-size: 0.75rem; }
  .trade-table th, .trade-table td { padding: 5px 8px; }
  .stat-row { font-size: 0.78rem; }
  .member-header { gap: 6px; }
  .disclaimer { font-size: 0.7rem; padding: 12px; }
}
"""

OVERVIEW_HEADERS = """
<thead><tr>
  <th>Member</th><th>Party</th><th>Chamber</th>
  <th>Total Trades</th><th>Public Equity</th>
  <th>Buys</th><th>Sells</th>
  <th>Est. Buy Vol</th><th>Est. Sell Vol</th>
  <th>Last Trade</th><th>Bias</th>
</tr></thead>
"""

RANKED_HEADERS = """
<thead><tr>
  <th>#</th><th>Ticker</th><th>Action</th>
  <th>Strength</th><th>Members</th><th>Rationale</th>
</tr></thead>
"""

DEFAULT_DISCLAIMER = (
    "This report is generated from public disclosure data available on capitoltrades.com. "
    "Congressional stock trades are reported under the STOCK Act and reflect trades by members "
    "and their immediate families. This is not investment advice. Trade signals represent "
    "pattern observations only and carry no guarantee of future performance. "
    "Always conduct independent research before making investment decisions."
)


def build_html(a: dict) -> str:
    alerts_html = ""
    for alert in a.get("summary_alerts", []):
        t = alert.get("type", "blue")
        cls = {"red": "red-alert", "yellow": "yellow-alert", "gray": "gray-alert"}.get(t, "")
        alerts_html += f'<div class="alert {cls}">{alert["html"]}</div>\n'

    sector_block = ""
    if a.get("sector_html"):
        sector_block = f'<div class="section-title">🔄 Sector Rotation</div>\n{a["sector_html"]}'

    disclaimer = a.get("disclaimer") or DEFAULT_DISCLAIMER

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{a.get('title', 'Congressional Trade Analysis')} — {a.get('date', '')}</title>
<style>{CSS}</style>
</head>
<body>

<div class="header"><h1>🏛 {a.get('title', 'Congressional Trade Analysis')}</h1></div>
<p class="meta">
  Window: {a.get('window', '')} &nbsp;|&nbsp;
  Source: {a.get('source', 'Capitol Trades')} &nbsp;|&nbsp;
  Generated: {a.get('date', '')} &nbsp;|&nbsp;
  Members: {a.get('members', '')}
</p>

<div class="section-title">⚡ Executive Summary — Headline Signals</div>
{alerts_html}

<div class="section-title">📊 Member Overview</div>
<div class="card" style="margin-bottom:24px">
  <table class="trade-table">
    {OVERVIEW_HEADERS}
    <tbody>{a.get('overview_table_rows', '')}</tbody>
  </table>
</div>

<div class="section-title">📋 Ranked Trade Ideas</div>
<div class="card" style="margin-bottom:24px">
  <table class="trade-table">
    {RANKED_HEADERS}
    <tbody>{a.get('ranked_ideas_rows', '')}</tbody>
  </table>
</div>

{sector_block}

<div class="section-title">👤 Member Deep Dives</div>
{a.get('member_sections', '')}

<p class="disclaimer">{disclaimer}</p>
</body>
</html>
"""


NO_CHANGES_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Congressional Trade Analysis — No New Trades</title>
<style>{css}</style></head><body>
<div class="header"><h1>🏛 Congressional Trade Intelligence Report</h1></div>
<p class="meta">Generated: {now} &nbsp;|&nbsp; Source: Capitol Trades</p>
<div class="section-title">No New Activity</div>
<div class="card">
  <p class="obs">No new congressional trades have been disclosed since <strong>{last_date}</strong>.
  The most recent fetch returned no transactions outside the existing dataset, so no analysis was generated.</p>
  {prior_link}
</div>
<p class="disclaimer">{disclaimer}</p>
</body></html>
"""


def _lineage_dir(reports_root: Path, slug: str) -> Path:
    """Return the subfolder that holds reports for a given lineage.

    - slug="" (default politician list) → reports/default/
    - slug=<committee>                  → reports/<slug>/
    """
    sub = slug if slug else "default"
    return reports_root / sub


def _find_last_full_report(reports_root: Path, slug: str = "") -> Path | None:
    """Most recent full (non-stub) report in this lineage's subfolder.

    Each lineage now lives in its own subfolder, so isolation is structural:
    no regex needed — just list the subfolder and skip no-changes stubs.
    """
    lineage = _lineage_dir(reports_root, slug)
    if not lineage.exists():
        return None
    candidates = sorted(
        (p for p in lineage.glob("report_*.html") if "no_changes" not in p.name),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("analysis_json", nargs="?", help="Path to the analysis JSON file")
    parser.add_argument("--out", default=None,
                        help="Full output HTML path. If omitted, auto-saves to reports/report_<ts>.html")
    parser.add_argument("--no-changes", dest="no_changes", default=None,
                        help="Emit a stub 'no new trades' report; argument is the last-disclosed date.")
    parser.add_argument("--slug", default="",
                        help="Configuration slug for no-changes stub naming and prior-report lookup "
                             "(e.g. 'house_committee_on_oversight_and_government_reform'). "
                             "Empty = default politician-list lineage.")
    args = parser.parse_args()

    # ── No-changes stub mode ─────────────────────────────────
    if args.no_changes is not None:
        project_root = Path(__file__).parent
        reports_root = project_root / "reports"
        lineage_dir  = _lineage_dir(reports_root, args.slug)
        lineage_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug_part = f"_{args.slug}" if args.slug else ""
        if args.out:
            out_path = Path(args.out).resolve()
        else:
            out_path = lineage_dir / f"report{slug_part}_{ts}_no_changes.html"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        prior = _find_last_full_report(reports_root, slug=args.slug)
        if prior:
            prior_link = (
                f'<p class="obs" style="margin-top:14px">'
                f'📄 Most recent full analysis: <a href="{prior.name}" style="color:var(--accent)">{prior.name}</a>'
                f'</p>'
            )
        else:
            prior_link = ""
        html = NO_CHANGES_HTML.format(
            css=CSS,
            now=datetime.now().strftime("%b %d, %Y %H:%M"),
            last_date=args.no_changes,
            disclaimer=DEFAULT_DISCLAIMER,
            prior_link=prior_link,
        )
        out_path.write_text(html, encoding="utf-8")
        print(f"No-changes report → {out_path}")
        return

    if not args.analysis_json:
        parser.error("analysis_json is required unless --no-changes is given")

    analysis_path = Path(args.analysis_json).resolve()
    if not analysis_path.exists():
        print(f"ERROR: analysis JSON not found: {analysis_path}", file=sys.stderr)
        sys.exit(1)

    with open(analysis_path, encoding="utf-8") as f:
        analysis = json.load(f)

    raw = json.dumps(analysis)
    if "[[FILL:" in raw:
        n = raw.count("[[FILL:")
        print(
            f"ERROR: {n} unfilled [[FILL: ...]] placeholder(s) remain in "
            f"{analysis_path.name}. The agent must fill every [[FILL: ...]] "
            f"marker before generate_report.py is invoked. Refusing to write report.",
            file=sys.stderr,
        )
        sys.exit(2)

    html = build_html(analysis)

    project_root = Path(__file__).parent
    reports_root = project_root / "reports"
    archive_dir  = project_root / "analysis"
    archive_dir.mkdir(exist_ok=True)

    # Derive a committee slug from the analysis filename, if any. The slug is
    # whatever follows "analysis_" in the stem (e.g.
    # "analysis_house_committee_on_armed_services" → "house_committee_on_armed_services").
    stem = analysis_path.stem
    slug = ""
    if stem.startswith("analysis_") and stem != "analysis":
        slug = stem[len("analysis_"):]
    slug_part = f"_{slug}" if slug else ""

    lineage_dir = _lineage_dir(reports_root, slug)
    lineage_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.out:
        out_path = Path(args.out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_path = lineage_dir / f"report{slug_part}_{ts}.html"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    archive_path = archive_dir / f"analysis{slug_part}_{ts}.json"
    shutil.copy(analysis_path, archive_path)

    print(f"Report   → {out_path}")
    print(f"Archived → {archive_path}")


if __name__ == "__main__":
    main()
