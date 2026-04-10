"""
committee_lookup.py — Resolve committee names to bioguide ID lists
==================================================================
Mechanical helpers for turning a committee name (or thomas_id) into a list
of bioguide IDs that can be passed to fetch_trades.py.

Data sources (expected to live next to this file):
    committees-current.json          — committee metadata, including thomas_id
    committee_membership_current.json — { thomas_id: [ {bioguide, name, ...}, ... ] }

CLI usage
---------
    python committee_lookup.py "House Committee on Armed Services"
    python committee_lookup.py HSAS
    python committee_lookup.py --list                # list all committees
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
COMMITTEES_FILE  = ROOT / "committees-current.json"
MEMBERSHIP_FILE  = ROOT / "committee_membership_current.json"


def load_committees() -> list[dict]:
    if not COMMITTEES_FILE.exists():
        return []
    with open(COMMITTEES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_membership() -> dict:
    if not MEMBERSHIP_FILE.exists():
        return {}
    with open(MEMBERSHIP_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_committee(query: str, committees: list[dict] | None = None) -> dict:
    """
    Resolve a free-form committee query.

    Accepts:
        * an exact thomas_id (e.g. "HSAS")
        * an exact committee name
        * a case-insensitive substring of the committee name

    Returns a dict:
        {"thomas_id": str | None, "candidates": list[dict]}
    - thomas_id is set on a unique match.
    - candidates is non-empty when the query was ambiguous (multiple substring
      matches), so callers can surface them to the user.
    """
    if not query:
        return {"thomas_id": None, "candidates": []}
    committees = committees if committees is not None else load_committees()
    q = query.strip()
    q_lower = q.lower()

    # Exact thomas_id match
    for c in committees:
        if c.get("thomas_id", "").upper() == q.upper():
            return {"thomas_id": c["thomas_id"], "candidates": []}

    # Exact name match
    for c in committees:
        if c.get("name", "").lower() == q_lower:
            return {"thomas_id": c.get("thomas_id"), "candidates": []}

    # Substring name match
    matches = [c for c in committees if q_lower in c.get("name", "").lower()]
    if len(matches) == 1:
        return {"thomas_id": matches[0].get("thomas_id"), "candidates": []}
    return {"thomas_id": None, "candidates": matches}


def resolve_committee_thomas_id(query: str, committees: list[dict] | None = None) -> str | None:
    """Backwards-compatible thin wrapper around resolve_committee()."""
    return resolve_committee(query, committees).get("thomas_id")


def get_committee_members(thomas_id: str, membership: dict | None = None) -> list[dict]:
    """Return the raw membership records for a committee thomas_id."""
    membership = membership if membership is not None else load_membership()
    return membership.get(thomas_id, [])


def get_committee_bioguide_ids(query: str) -> list[str]:
    """
    High-level helper: take a committee name / thomas_id and return the
    bioguide IDs of every member on that committee. Returns [] if the
    committee can't be resolved.
    """
    committees = load_committees()
    membership = load_membership()
    thomas_id  = resolve_committee_thomas_id(query, committees)
    if not thomas_id:
        return []
    return [m["bioguide"] for m in get_committee_members(thomas_id, membership) if m.get("bioguide")]


def describe_committee(query: str) -> dict | None:
    """
    Return a summary dict for a resolved committee, or None if not unique.

    On ambiguity, the returned None is paired with no extra info — callers
    that need to surface candidate matches should call resolve_committee()
    directly so they can read the candidates list.
    """
    committees = load_committees()
    membership = load_membership()
    thomas_id  = resolve_committee_thomas_id(query, committees)
    if not thomas_id:
        return None
    info = next((c for c in committees if c.get("thomas_id") == thomas_id), {})
    members = get_committee_members(thomas_id, membership)
    return {
        "thomas_id":   thomas_id,
        "name":        info.get("name", ""),
        "type":        info.get("type", ""),
        "memberCount": len(members),
        "bioguideIds": [m["bioguide"] for m in members if m.get("bioguide")],
    }


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Resolve a committee to its bioguide member list")
    parser.add_argument("query", nargs="?", help="Committee name or thomas_id")
    parser.add_argument("--list", action="store_true", help="List all committees and exit")
    args = parser.parse_args()

    if args.list:
        for c in load_committees():
            print(f"  {c.get('thomas_id','????'):<6} {c.get('name','')}")
        return

    if not args.query:
        parser.print_help()
        sys.exit(1)

    summary = describe_committee(args.query)
    if not summary:
        print(f"No committee matched '{args.query}'.")
        sys.exit(2)

    print(f"{summary['name']}  ({summary['thomas_id']})")
    print(f"  type:    {summary['type']}")
    print(f"  members: {summary['memberCount']}")
    for bid in summary["bioguideIds"]:
        print(f"    {bid}")


if __name__ == "__main__":
    _cli()
