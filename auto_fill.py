#!/usr/bin/env python3
"""
auto_fill.py — Call Claude API to generate fills.json from pipeline digest.

Reads the stdout digest produced by run_pipeline.py AND the skeleton JSON to
extract the exact required keys, then asks Claude to write prose fills in the
exact schema expected by fill_skeleton.py.

Usage:
    python3 run_pipeline.py > digest.txt
    python3 auto_fill.py --digest digest.txt --skeleton analysis_skeleton.json --out fills.json

Requires:  pip install anthropic
Env var:   ANTHROPIC_API_KEY
"""

import argparse
import json
import os
import sys
import re

try:
    import anthropic
except ImportError:
    sys.exit("ERROR: 'anthropic' package not installed. Run: pip install anthropic")


SYSTEM_PROMPT = """\
You are a financial-intelligence analyst writing concise prose for a \
congressional stock-trading report. You will receive:
1. The stdout digest from the analysis pipeline (member tables, consensus \
   signals, ranked ideas).
2. The EXACT keys you must use for summary_alerts and ranked_ideas.
3. The EXACT member names you must write observations for.

Your job is to output a single JSON object (fills.json) with prose strings.

CRITICAL RULES:
- Output ONLY valid JSON — no markdown fences, no commentary, no explanation.
- You MUST use every key listed in REQUIRED_ALERT_IDS for summary_alerts.
- You MUST use every key listed in REQUIRED_IDEA_IDS for ranked_ideas.
- You MUST include an entry for every name in REQUIRED_MEMBERS.
- TICKER MENTION RULE (THIS IS VALIDATED AND WILL REJECT YOUR OUTPUT IF \
  VIOLATED): Every ticker symbol embedded in a key MUST appear LITERALLY as \
  the ticker symbol in the prose. For example, if the key is \
  "consensus_buy_HD", the prose MUST contain the string "HD" (not just \
  "Home Depot"). If the key is "consensus_sell_AAPL", the prose MUST contain \
  "AAPL" (not just "Apple"). Always write the ticker symbol in parentheses \
  after the company name, e.g. "Home Depot (HD)" or "Alphabet (GOOGL)".
- Keep tone academically neutral. No investment advice or recommendations.
- Lean on context the scripts can't know: committee jurisdictions, member \
  backgrounds, sector implications of policy exposure.
- Do NOT include a "title" key unless the digest indicates a committee run.
"""

USER_TEMPLATE = """\
Here is the pipeline digest and required keys. Write fills.json.

--- DIGEST START ---
{digest}
--- DIGEST END ---

REQUIRED_ALERT_IDS (use these EXACTLY as keys in "summary_alerts"):
{alert_ids}

REQUIRED_IDEA_IDS (use these EXACTLY as keys in "ranked_ideas"):
{idea_ids}

REQUIRED_MEMBERS (use these EXACTLY as keys in "members"):
{member_names}

Output the JSON object with these four top-level keys:
  "summary_alerts": dict with every REQUIRED_ALERT_ID as a key
  "ranked_ideas": dict with every REQUIRED_IDEA_ID as a key
  "members": dict with every REQUIRED_MEMBER as a key
  "inactive_default": a single boilerplate string

Output ONLY the JSON. No other text.
"""


def parse_args():
    p = argparse.ArgumentParser(description="Generate fills.json via Claude API")
    p.add_argument("--digest", type=str, required=True,
                   help="Path to digest text file")
    p.add_argument("--skeleton", type=str, required=True,
                   help="Path to analysis_skeleton JSON (to extract required keys)")
    p.add_argument("--out", type=str, default="fills.json",
                   help="Output path for fills.json")
    p.add_argument("--model", type=str, default="claude-sonnet-4-20250514",
                   help="Claude model to use")
    p.add_argument("--max-tokens", type=int, default=4096,
                   help="Max tokens for response")
    return p.parse_args()


def read_digest(path):
    with open(path, "r") as f:
        return f.read()


def extract_required_keys(skeleton_path):
    """Parse the skeleton JSON to find exact alert IDs, idea IDs, and member names."""
    with open(skeleton_path, "r") as f:
        skeleton = json.load(f)

    # Alert IDs from summary_alerts list
    alert_ids = []
    for alert in skeleton.get("summary_alerts", []):
        if isinstance(alert, dict) and "id" in alert:
            alert_ids.append(alert["id"])

    # Idea IDs from ranked_ideas_rows HTML — pattern: [[FILL:idea:TICKER_ACTION:
    ideas_html = skeleton.get("ranked_ideas_rows", "")
    idea_ids = re.findall(r'\[\[FILL:idea:([A-Z0-9._]+_(?:BUY|SELL)):', ideas_html)

    # Member names from member_sections
    member_names = []
    for section in skeleton.get("member_sections", []):
        if isinstance(section, dict) and "name" in section:
            member_names.append(section["name"])

    return alert_ids, idea_ids, member_names


def extract_json(text):
    """Extract JSON from response, handling possible markdown fences."""
    text = text.strip()
    # Strip markdown fences if present
    m = re.match(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    return json.loads(text)


def main():
    args = parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY environment variable not set.")

    digest = read_digest(args.digest)
    if not digest.strip():
        sys.exit("ERROR: Digest is empty.")

    # Extract required keys from skeleton
    print(f"Reading skeleton: {args.skeleton}", file=sys.stderr)
    alert_ids, idea_ids, member_names = extract_required_keys(args.skeleton)
    print(f"  Alert IDs ({len(alert_ids)}): {alert_ids}", file=sys.stderr)
    print(f"  Idea IDs ({len(idea_ids)}): {idea_ids}", file=sys.stderr)
    print(f"  Members ({len(member_names)}): {member_names}", file=sys.stderr)

    if not alert_ids and not idea_ids and not member_names:
        sys.exit("ERROR: Could not extract any required keys from skeleton.")

    client = anthropic.Anthropic(api_key=api_key)

    user_msg = USER_TEMPLATE.format(
        digest=digest,
        alert_ids=json.dumps(alert_ids),
        idea_ids=json.dumps(idea_ids),
        member_names=json.dumps(member_names),
    )

    print(f"Calling {args.model} to generate fills...", file=sys.stderr)
    response = client.messages.create(
        model=args.model,
        max_tokens=args.max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = response.content[0].text
    try:
        fills = extract_json(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse JSON from API response: {e}", file=sys.stderr)
        print("Raw response:", raw[:2000], file=sys.stderr)
        sys.exit(1)

    # Validate all required keys are present
    ok = True
    for aid in alert_ids:
        if aid not in fills.get("summary_alerts", {}):
            print(f"WARNING: Missing alert key: {aid}", file=sys.stderr)
            ok = False
    for iid in idea_ids:
        if iid not in fills.get("ranked_ideas", {}):
            print(f"WARNING: Missing idea key: {iid}", file=sys.stderr)
            ok = False
    for name in member_names:
        if name not in fills.get("members", {}):
            print(f"WARNING: Missing member: {name}", file=sys.stderr)
            ok = False

    if not ok:
        print("WARNING: Some required keys are missing — fill_skeleton.py may reject this.", file=sys.stderr)

    with open(args.out, "w") as f:
        json.dump(fills, f, indent=2)

    print(f"Wrote {args.out} ({len(json.dumps(fills))} bytes)", file=sys.stderr)


if __name__ == "__main__":
    main()
