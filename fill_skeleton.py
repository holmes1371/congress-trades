#!/usr/bin/env python3
"""
fill_skeleton.py — apply agent-authored prose to an analysis skeleton.

The agent writes a small fills.json containing only the prose strings, keyed
by stable IDs emitted by build_skeleton.py. This script performs all
mechanical substitution, validation, and output.

fills.json schema (all keys optional):
{
  "title":           "<optional replacement title>",
  "summary_alerts":  { "<alert_id>": "<prose>", ... },
  "ranked_ideas":    { "<TICKER>_<ACTION>": "<rationale>", ... },
  "members":         { "<Member Name>": "<2-3 sentence observation>", ... },
  "inactive_default":"<observation used for any member with no entry above>"
}

Legacy list form is explicitly rejected for summary_alerts and ranked_ideas
because positional zipping was the source of header/prose misalignment bugs.

Usage:
  python3 fill_skeleton.py \
      --skeleton analysis_skeleton/analysis_skeleton_<slug>.json \
      --fills    fills.json \
      --out      analysis/analysis_<slug>.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_INACTIVE = (
    "No disclosed trades during this window. Absence of activity does not rule out "
    "prior holdings; it simply indicates no new disclosures to analyze."
)

# Matches legacy (bare) placeholders and new keyed placeholders.
PLACEHOLDER_RE = re.compile(r"\[\[FILL:[^\]]+\]\]")
KEYED_ALERT_RE = re.compile(r"\[\[FILL:alert:([^:\]]+):[^\]]*\]\]")
KEYED_IDEA_RE  = re.compile(r"\[\[FILL:idea:([^:\]]+):[^\]]*\]\]")
MEMBER_FILL_RE = re.compile(
    r"\[\[FILL: 2-3 sentence observation about ([^']+?)'s pattern[^\]]+\]\]"
)


class FillError(Exception):
    pass


def _validate_alerts(skeleton_alerts, fills_alerts):
    if not isinstance(fills_alerts, dict):
        raise FillError(
            "fills['summary_alerts'] must be a dict keyed by alert id "
            "(e.g. 'consensus_sell_T'), not a list. Positional lists are "
            "rejected to prevent header/prose misalignment."
        )
    skeleton_ids = [a.get("id") for a in skeleton_alerts if a.get("id")]
    skeleton_set = set(skeleton_ids)
    fill_set = set(fills_alerts.keys())

    missing = skeleton_set - fill_set
    extras  = fill_set - skeleton_set
    if missing:
        raise FillError(f"fills missing prose for alert ids: {sorted(missing)}")
    if extras:
        raise FillError(
            f"fills contains prose for alert ids not in skeleton "
            f"(hallucinated?): {sorted(extras)}"
        )

    # Ticker-echo check: if the skeleton alert carries a ticker, the prose
    # must mention it somewhere. Cheap and catches the exact bug that
    # motivated this refactor.
    for a in skeleton_alerts:
        aid = a.get("id")
        tkr = a.get("ticker")
        if not aid or not tkr:
            continue
        prose = fills_alerts.get(aid, "")
        # word-boundary match on the ticker (uppercase)
        if not re.search(rf"\b{re.escape(tkr)}\b", prose):
            raise FillError(
                f"alert '{aid}' prose does not mention its ticker '{tkr}'. "
                f"Prose: {prose[:120]!r}"
            )


def _validate_ideas(skeleton_rows_html, fills_ideas):
    if not isinstance(fills_ideas, dict):
        raise FillError(
            "fills['ranked_ideas'] must be a dict keyed by 'TICKER_ACTION' "
            "(e.g. 'AAPL_SELL'), not a list."
        )
    needed = set(KEYED_IDEA_RE.findall(skeleton_rows_html))
    provided = set(fills_ideas.keys())
    missing = needed - provided
    extras  = provided - needed
    if missing:
        raise FillError(f"fills missing rationale for ideas: {sorted(missing)}")
    if extras:
        raise FillError(f"fills contains rationales for non-existent ideas: {sorted(extras)}")

    # Ticker-echo check for rationales too.
    for key, prose in fills_ideas.items():
        ticker = key.split("_", 1)[0]
        if not re.search(rf"\b{re.escape(ticker)}\b", prose):
            raise FillError(
                f"ranked idea '{key}' rationale does not mention its ticker "
                f"'{ticker}'. Rationale: {prose[:120]!r}"
            )


def apply_fills(skeleton: dict, fills: dict) -> dict:
    out = dict(skeleton)

    if fills.get("title"):
        out["title"] = fills["title"]

    # ---- Summary alerts (keyed) ----
    skeleton_alerts = out.get("summary_alerts", [])
    fills_alerts = fills.get("summary_alerts", {})
    _validate_alerts(skeleton_alerts, fills_alerts)

    for alert in skeleton_alerts:
        aid = alert.get("id")
        if not aid:
            continue
        prose = fills_alerts.get(aid, "")
        def _sub_for(_m, _p=prose):
            return _p
        alert["html"] = KEYED_ALERT_RE.sub(_sub_for, alert["html"], count=1)

    # ---- Ranked ideas (keyed) ----
    fills_ideas = fills.get("ranked_ideas", {})
    if "ranked_ideas_rows" in out:
        _validate_ideas(out["ranked_ideas_rows"], fills_ideas)
        def _idea_sub(m):
            return fills_ideas[m.group(1)]
        out["ranked_ideas_rows"] = KEYED_IDEA_RE.sub(_idea_sub, out["ranked_ideas_rows"])

    # ---- Member observations (unchanged — already keyed by name) ----
    members_prose = fills.get("members", {})
    inactive = fills.get("inactive_default", DEFAULT_INACTIVE)

    def member_sub(m):
        name = m.group(1).strip()
        return members_prose.get(name, inactive)

    if "member_sections" in out:
        out["member_sections"] = MEMBER_FILL_RE.sub(member_sub, out["member_sections"])

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skeleton", required=True)
    ap.add_argument("--fills", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    skeleton = json.loads(Path(args.skeleton).read_text())
    fills = json.loads(Path(args.fills).read_text())

    try:
        filled = apply_fills(skeleton, fills)
    except FillError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    # Validate: no placeholders should remain anywhere in the serialized output
    leftover = PLACEHOLDER_RE.findall(json.dumps(filled))
    if leftover:
        print(f"WARNING: {len(leftover)} unfilled placeholder(s) remain:", file=sys.stderr)
        for l in leftover[:10]:
            print(f"  {l}", file=sys.stderr)
        sys.exit(3)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(filled, indent=2))
    print(f"Filled analysis written → {args.out}")


if __name__ == "__main__":
    main()
