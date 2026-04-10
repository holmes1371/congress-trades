#!/usr/bin/env python3
"""
auto_fill.py — Call Claude API to generate fills.json from pipeline digest.

Reads the stdout digest produced by run_pipeline.py (passed as a text file or
stdin) and asks Claude to write prose fills in the exact schema expected by
fill_skeleton.py.  Designed for headless CI runs (GitHub Actions).

Usage:
    python3 run_pipeline.py > digest.txt
    python3 auto_fill.py --digest digest.txt --out fills.json

    # or pipe directly
    python3 run_pipeline.py | python3 auto_fill.py --out fills.json

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
congressional stock-trading report. You will receive the stdout digest \
produced by the analysis pipeline (member tables, consensus signals, \
ranked ideas, placeholder counts). Your job is to author fills.json — \
a JSON object with prose strings that will be injected into the report \
skeleton by fill_skeleton.py.

Rules:
- Output ONLY valid JSON — no markdown fences, no commentary.
- Follow the fills.json schema exactly:
  {
    "summary_alerts": { "<alert_id>": "prose mentioning the ticker in the id", ... },
    "ranked_ideas":   { "<TICKER_ACTION>": "1-line rationale mentioning the ticker", ... },
    "members":        { "<Full Name>": "2-3 sentence observation", ... },
    "inactive_default": "boilerplate for members with no trades"
  }
- Every key in summary_alerts and ranked_ideas must match an ID from the \
  digest. Every ticker named in an ID must appear in its prose.
- Keep tone academically neutral. No investment advice or recommendations.
- Lean on context the scripts can't know: committee jurisdictions, member \
  backgrounds, sector implications of policy exposure.
- Do NOT include a "title" key unless the digest indicates a committee run \
  (in which case retitle to reflect the committee).
"""

USER_TEMPLATE = """\
Here is the pipeline digest. Write fills.json for this run.

--- DIGEST START ---
{digest}
--- DIGEST END ---

Output only the JSON object.
"""


def parse_args():
    p = argparse.ArgumentParser(description="Generate fills.json via Claude API")
    p.add_argument("--digest", type=str, default=None,
                   help="Path to digest text file (default: read stdin)")
    p.add_argument("--out", type=str, default="fills.json",
                   help="Output path for fills.json")
    p.add_argument("--model", type=str, default="claude-sonnet-4-20250514",
                   help="Claude model to use")
    p.add_argument("--max-tokens", type=int, default=4096,
                   help="Max tokens for response")
    return p.parse_args()


def read_digest(path):
    if path:
        with open(path, "r") as f:
            return f.read()
    if not sys.stdin.isatty():
        return sys.stdin.read()
    sys.exit("ERROR: No digest provided. Pass --digest <file> or pipe stdin.")


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

    client = anthropic.Anthropic(api_key=api_key)

    print(f"Calling {args.model} to generate fills...", file=sys.stderr)
    response = client.messages.create(
        model=args.model,
        max_tokens=args.max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": USER_TEMPLATE.format(digest=digest)}],
    )

    raw = response.content[0].text
    try:
        fills = extract_json(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse JSON from API response: {e}", file=sys.stderr)
        print("Raw response:", raw[:2000], file=sys.stderr)
        sys.exit(1)

    # Basic validation
    expected_keys = {"summary_alerts", "ranked_ideas", "members", "inactive_default"}
    got_keys = set(fills.keys()) - {"title"}
    missing = expected_keys - got_keys
    if missing:
        print(f"WARNING: Missing top-level keys: {missing}", file=sys.stderr)

    with open(args.out, "w") as f:
        json.dump(fills, f, indent=2)

    print(f"Wrote {args.out} ({len(json.dumps(fills))} bytes)", file=sys.stderr)


if __name__ == "__main__":
    main()
