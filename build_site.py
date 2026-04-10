#!/usr/bin/env python3
"""
build_site.py — Generate a static landing page for the congressional trading
reports site.  Scans reports/ for HTML files, builds an index with the latest
report prominently featured and an archive of past reports.  Also generates
an RSS feed (rss.xml) for subscribers.

Usage:
    python3 build_site.py                    # writes site/index.html + site/rss.xml
    python3 build_site.py --out docs/        # custom output dir (for GH Pages)

Output goes to site/ by default (or docs/ if your GH Pages is configured for
the docs/ folder).
"""

import argparse
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape


PROJ = Path(__file__).resolve().parent
REPORTS_DIR = PROJ / "reports"
SITE_URL = os.environ.get("SITE_URL", "https://holmes1371.github.io/congress-trades")


def find_reports():
    """Scan reports/ recursively for HTML files, return sorted list of dicts."""
    reports = []
    for html in REPORTS_DIR.rglob("report_*.html"):
        rel = html.relative_to(PROJ)
        # Extract lineage from parent folder name
        lineage = html.parent.name
        # Parse date from filename: report_[slug_]YYYYMMDD_HHMMSS.html
        m = re.search(r"(\d{8})_(\d{6})\.html$", html.name)
        if not m:
            continue
        date_str = m.group(1)
        time_str = m.group(2)
        dt = datetime.strptime(date_str + time_str, "%Y%m%d%H%M%S")
        size_kb = html.stat().st_size / 1024

        # Pretty lineage name
        pretty = lineage.replace("_", " ").title() if lineage != "default" else "Default Follow List"

        reports.append({
            "path": str(rel),
            "filename": html.name,
            "lineage": lineage,
            "pretty_lineage": pretty,
            "dt": dt,
            "date_display": dt.strftime("%b %d, %Y"),
            "time_display": dt.strftime("%I:%M %p"),
            "size_kb": f"{size_kb:.0f}",
        })

    reports.sort(key=lambda r: r["dt"], reverse=True)
    return reports


def build_archive_rows(reports):
    rows = []
    for r in reports:
        rows.append(
            f'<tr>'
            f'<td><a href="{r["path"]}">{r["date_display"]}</a></td>'
            f'<td>{r["time_display"]}</td>'
            f'<td><span class="lineage-tag">{r["pretty_lineage"]}</span></td>'
            f'<td>{r["size_kb"]} KB</td>'
            f'</tr>'
        )
    return "\n            ".join(rows)


def build_rss(reports, out_dir, max_items=20):
    """Generate an RSS 2.0 feed from the report list."""
    items = []
    for r in reports[:max_items]:
        url = f"{SITE_URL}/{r['path']}"
        pub_date = r["dt"].strftime("%a, %d %b %Y %H:%M:%S +0000")
        items.append(
            f"    <item>\n"
            f"      <title>{escape(r['pretty_lineage'])} — {escape(r['date_display'])}</title>\n"
            f"      <link>{escape(url)}</link>\n"
            f"      <guid>{escape(url)}</guid>\n"
            f"      <pubDate>{pub_date}</pubDate>\n"
            f"      <description>Congressional trade intelligence report for {escape(r['date_display'])} ({escape(r['pretty_lineage'])})</description>\n"
            f"    </item>"
        )

    rss = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Congressional Trade Intelligence</title>
    <link>{SITE_URL}</link>
    <description>Automated tracking and analysis of stock trades disclosed by members of Congress.</description>
    <language>en-us</language>
    <lastBuildDate>{datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")}</lastBuildDate>
    <atom:link href="{SITE_URL}/rss.xml" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>
"""
    rss_path = out_dir / "rss.xml"
    rss_path.write_text(rss)
    print(f"Built {rss_path} ({len(items)} items)")


INDEX_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Congressional Trade Intelligence</title>
<link rel="alternate" type="application/rss+xml" title="Congressional Trade Intelligence" href="rss.xml">
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
    padding: 32px 24px; max-width: 900px; margin: 0 auto;
  }}
  h1 {{
    font-size: 1.8rem; font-weight: 700; color: var(--accent);
    margin-bottom: 6px;
  }}
  .subtitle {{
    font-size: 0.9rem; color: var(--muted); margin-bottom: 32px;
    line-height: 1.6;
  }}
  .latest-card {{
    background: var(--surface);
    border: 2px solid var(--accent);
    border-radius: 12px; padding: 24px;
    margin-bottom: 36px;
  }}
  .latest-card h2 {{
    font-size: 1.1rem; color: var(--accent); margin-bottom: 8px;
  }}
  .latest-card .meta {{
    font-size: 0.82rem; color: var(--muted); margin-bottom: 16px;
  }}
  .latest-card a.btn {{
    display: inline-block; background: var(--accent);
    color: #fff; text-decoration: none;
    padding: 10px 24px; border-radius: 8px;
    font-weight: 600; font-size: 0.9rem;
    transition: opacity 0.15s;
  }}
  .latest-card a.btn:hover {{ opacity: 0.85; }}

  h3 {{
    font-size: 1.0rem; font-weight: 600; color: var(--text);
    margin-bottom: 14px;
  }}
  .archive-table {{
    width: 100%; border-collapse: collapse;
    font-size: 0.84rem; margin-bottom: 32px;
  }}
  .archive-table th {{
    text-align: left; padding: 8px 12px;
    background: var(--surface2); color: var(--muted);
    font-weight: 600; font-size: 0.75rem;
    text-transform: uppercase; letter-spacing: 0.04em;
  }}
  .archive-table td {{
    padding: 8px 12px; border-bottom: 1px solid var(--border);
    vertical-align: middle;
  }}
  .archive-table tr:last-child td {{ border-bottom: none; }}
  .archive-table a {{
    color: var(--accent); text-decoration: none;
  }}
  .archive-table a:hover {{ text-decoration: underline; }}
  .lineage-tag {{
    display: inline-block; font-size: 0.72rem; font-weight: 600;
    padding: 2px 8px; border-radius: 99px;
    background: rgba(79,142,247,0.12); color: var(--accent);
    text-transform: capitalize;
  }}
  .footer {{
    font-size: 0.75rem; color: var(--muted); padding-top: 20px;
    border-top: 1px solid var(--border); line-height: 1.6;
  }}

  @media (max-width: 600px) {{
    body {{ padding: 16px; }}
    h1 {{ font-size: 1.4rem; }}
    .latest-card {{ padding: 16px; }}
    .archive-table {{ font-size: 0.78rem; }}
    .archive-table th, .archive-table td {{ padding: 6px 8px; }}
  }}
</style>
</head>
<body>

<h1>Congressional Trade Intelligence</h1>
<p class="subtitle">
  Automated tracking and analysis of stock trades disclosed by members of
  Congress. Reports are generated from public filings on Capitol Trades and
  updated automatically.
  &nbsp;&middot;&nbsp; <a href="leaderboard.html">Member Leaderboard</a>
  &nbsp;&middot;&nbsp; <a href="rss.xml" style="color:var(--accent);">RSS Feed</a>
</p>

<div class="latest-card">
  <h2>Latest Report</h2>
  <p class="meta">{latest_date} &middot; {latest_lineage} &middot; {latest_size} KB</p>
  <a class="btn" href="{latest_path}">View Report &rarr;</a>
</div>

<h3>Report Archive</h3>
<div style="overflow-x:auto;">
  <table class="archive-table">
    <thead>
      <tr>
        <th>Date</th>
        <th>Time</th>
        <th>Lineage</th>
        <th>Size</th>
      </tr>
    </thead>
    <tbody>
      {archive_rows}
    </tbody>
  </table>
</div>

<div class="footer">
  Data sourced from public STOCK Act filings via
  <a href="https://www.capitoltrades.com" style="color:var(--accent);">Capitol Trades</a>.
  This site is for informational purposes only and does not constitute investment advice.
  <br>Last updated: {build_time}
</div>

</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="site", help="Output directory")
    args = parser.parse_args()

    reports = find_reports()
    if not reports:
        print("No reports found in reports/. Nothing to build.")
        return

    out_dir = PROJ / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    # Copy reports/ into output dir (preserving structure)
    out_reports = out_dir / "reports"
    if out_reports.exists():
        shutil.rmtree(out_reports)
    shutil.copytree(REPORTS_DIR, out_reports)

    latest = reports[0]

    html = INDEX_HTML.format(
        latest_date=latest["date_display"],
        latest_lineage=latest["pretty_lineage"],
        latest_size=latest["size_kb"],
        latest_path=latest["path"],
        archive_rows=build_archive_rows(reports),
        build_time=datetime.now().strftime("%b %d, %Y at %I:%M %p"),
    )

    index_path = out_dir / "index.html"
    index_path.write_text(html)
    print(f"Built {index_path} ({len(reports)} reports indexed)")

    # Generate RSS feed
    build_rss(reports, out_dir)


if __name__ == "__main__":
    main()
