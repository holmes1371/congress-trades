"""
update_reference_data.py — Refresh local Congress reference files
=================================================================
Downloads the latest legislator and committee data from the
unitedstates/congress-legislators project and overwrites the three
reference JSON files this project depends on:

    legislators-current.json         → member_bioguide.json
    committees-current.json          → committees-current.json
    committee-membership-current.json → committee_membership_current.json

Each existing file is backed up to reference_backups/ before being
overwritten, so a bad upstream update can be rolled back.

Usage
-----
    python3 update_reference_data.py
    python3 update_reference_data.py --no-backup     # skip backup step
    python3 update_reference_data.py --dry-run       # show what would change
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).parent
BACKUP_DIR = ROOT / "reference_backups"

BASE_URL = "https://unitedstates.github.io/congress-legislators"

# (remote filename, local destination filename, human-friendly label)
TARGETS: list[tuple[str, str, str]] = [
    ("legislators-current.json",          "member_bioguide.json",            "Legislators"),
    ("committees-current.json",           "committees-current.json",         "Committees"),
    ("committee-membership-current.json", "committee_membership_current.json","Committee membership"),
]

USER_AGENT = "congressional-trade-analysis/1.0 (reference-data-updater)"


def _download(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=60) as r:
        return r.read()


def _validate_json(raw: bytes) -> tuple[bool, str, int]:
    """Return (ok, kind, top_level_count). Refuses to overwrite on bad JSON."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return False, f"invalid JSON: {e}", 0
    if isinstance(data, list):
        return True, "list", len(data)
    if isinstance(data, dict):
        return True, "dict", len(data)
    return False, f"unexpected top-level type: {type(data).__name__}", 0


def _backup(local_path: Path, ts: str) -> Path | None:
    if not local_path.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"{local_path.stem}_{ts}{local_path.suffix}"
    shutil.copy2(local_path, backup_path)
    return backup_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh local Congress reference data")
    parser.add_argument("--no-backup", action="store_true",
                        help="Skip backing up existing files before overwriting")
    parser.add_argument("--dry-run", action="store_true",
                        help="Download and validate but do not overwrite local files")
    args = parser.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"Refreshing reference data from {BASE_URL}\n")

    failures = 0
    for remote_name, local_name, label in TARGETS:
        url = f"{BASE_URL}/{remote_name}"
        local_path = ROOT / local_name
        print(f"  {label}")
        print(f"    {url}")
        try:
            raw = _download(url)
        except Exception as exc:
            print(f"    ✗ download failed: {exc}\n")
            failures += 1
            continue

        ok, kind, count = _validate_json(raw)
        if not ok:
            print(f"    ✗ {kind} — refusing to overwrite {local_name}\n")
            failures += 1
            continue

        size_kb = len(raw) / 1024
        print(f"    ✓ {size_kb:,.1f} KB, top-level {kind} with {count} entries")

        if args.dry_run:
            print("    (dry-run, not written)\n")
            continue

        if not args.no_backup:
            backup_path = _backup(local_path, ts)
            if backup_path:
                print(f"    backup → {backup_path.relative_to(ROOT)}")

        local_path.write_bytes(raw)
        print(f"    written → {local_name}\n")

    if failures:
        print(f"Completed with {failures} failure(s).")
        sys.exit(1)
    print("All reference files up to date.")


if __name__ == "__main__":
    main()
