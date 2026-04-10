"""
run_pipeline.py — Congress Trades Pipeline Orchestrator (Steps 1–4)
====================================================================
Single entry point that runs the mechanical portion of the
congress-trades skill end-to-end with no agent involvement:

    Step 1  committee_lookup    (only if --committee supplied)
    Step 2  fetch_trades        (committee / explicit IDs / default list)
    Step 3  compute_analysis    (honors NO_CHANGES short-circuit)
    Step 4  build_skeleton      (emits analysis_skeleton_<slug>.json)

After this script exits successfully, the agent's only remaining job is
Step 5 (write fills.json + run fill_skeleton.py) and Step 6 (generate_report.py).

Exit codes
----------
    0   success — skeleton built, ready for fills
    2   no new trades — pipeline short-circuited at Step 3
    1   any other failure (resolution, fetch, compute, build)

Stdout contract
---------------
The script re-emits the digests printed by compute_analysis.py and
build_skeleton.py so the agent can author fills.json from stdout alone,
without ever opening any intermediate JSON file.

The final line on success is always:

    PIPELINE_READY: skeleton=<path> slug=<slug-or-default>

On the no-changes path the final line is:

    NO_CHANGES: <date>

Usage
-----
    # Default politician list
    python3 run_pipeline.py

    # Committee mode
    python3 run_pipeline.py --committee "House Committee on Armed Services"
    python3 run_pipeline.py --committee HSAS --days 60

    # Explicit bioguide IDs or member names
    python3 run_pipeline.py --members K000389 M001157
    python3 run_pipeline.py --members "Ro Khanna" "Dave McCormick"
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
PY = sys.executable


class PipelineError(RuntimeError):
    pass


class NoChanges(RuntimeError):
    def __init__(self, date_str: str):
        super().__init__(date_str)
        self.date_str = date_str


class CongressTradesPipeline:
    """Runs Steps 1–4 of the congress-trades skill in one shot."""

    def __init__(
        self,
        committee: str | None = None,
        members: list[str] | None = None,
        days: int = 60,
    ) -> None:
        self.committee = committee
        self.members = members or []
        self.days = days
        self.slug: str | None = None  # set after fetch
        self.compute_argv: list[str] | None = None  # parsed from fetch stdout
        self.build_argv: list[str] | None = None    # parsed from fetch stdout
        self.skeleton_path: Path | None = None      # parsed from build_argv

    # ── shell helper ────────────────────────────────────────────────
    def _run(self, argv: list[str]) -> str:
        """Run a child script, stream stdout to our stdout, return captured text."""
        print(f"\n$ {' '.join(argv)}", flush=True)
        proc = subprocess.Popen(
            argv,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        captured: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            captured.append(line)
        proc.wait()
        out = "".join(captured)
        if proc.returncode != 0:
            raise PipelineError(
                f"Command failed ({proc.returncode}): {' '.join(argv)}"
            )
        return out

    # ── Step 2: fetch ───────────────────────────────────────────────
    def step_fetch(self) -> None:
        argv = [PY, "fetch_trades.py", "--days", str(self.days)]
        if self.committee:
            argv += ["--committee", self.committee]
        elif self.members:
            argv += list(self.members)

        out = self._run(argv)

        # fetch_trades.py prints a "Next steps:" block with the exact
        # compute_analysis.py and build_skeleton.py commands (with the
        # right --in/--out paths for both default and committee runs).
        # Parse those lines instead of trying to reconstruct paths.
        for raw in out.splitlines():
            line = raw.strip()
            if line.startswith("python3 compute_analysis.py"):
                self.compute_argv = [PY] + line.split()[1:]
            elif line.startswith("python3 build_skeleton.py"):
                self.build_argv = [PY] + line.split()[1:]

        if not self.compute_argv or not self.build_argv:
            raise PipelineError(
                "fetch_trades.py did not print the expected 'Next steps' commands"
            )

        # Derive the skeleton path from the build command's --out arg
        if "--out" in self.build_argv:
            i = self.build_argv.index("--out")
            self.skeleton_path = ROOT / self.build_argv[i + 1]
        else:
            self.skeleton_path = ROOT / "analysis_skeleton" / "analysis_skeleton.json"

        # Capture slug (if any) from the skeleton filename for the final banner
        m = re.match(r"analysis_skeleton_(.+)\.json", self.skeleton_path.name)
        if m:
            self.slug = m.group(1)

    # ── Step 3: compute ─────────────────────────────────────────────
    def step_compute(self) -> None:
        assert self.compute_argv is not None
        out = self._run(self.compute_argv)

        # Honor the NO_CHANGES short-circuit
        for line in out.splitlines():
            if line.startswith("NO_CHANGES:"):
                date_str = line.split(":", 1)[1].strip()
                raise NoChanges(date_str)

    # ── Step 4: build skeleton ──────────────────────────────────────
    def step_build_skeleton(self) -> None:
        assert self.build_argv is not None
        self._run(self.build_argv)

        if self.skeleton_path is None or not self.skeleton_path.exists():
            raise PipelineError(
                f"build_skeleton.py did not produce expected skeleton: {self.skeleton_path}"
            )

    # ── Orchestrator ────────────────────────────────────────────────
    def run(self) -> Path:
        self.step_fetch()         # Steps 1 + 2 (committee_lookup is invoked inside fetch_trades.py)
        self.step_compute()       # Step 3
        self.step_build_skeleton()  # Step 4
        return self.skeleton_path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run Steps 1–4 of the congress-trades skill in one invocation.",
    )
    p.add_argument("--committee", help="Committee name, substring, or thomas_id")
    p.add_argument(
        "--members",
        nargs="+",
        help="Explicit bioguide IDs or member names (mutually exclusive with --committee)",
    )
    p.add_argument("--days", type=int, default=60, help="Lookback window (default 60)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.committee and args.members:
        print("error: --committee and --members are mutually exclusive", file=sys.stderr)
        return 1

    pipeline = CongressTradesPipeline(
        committee=args.committee,
        members=args.members,
        days=args.days,
    )

    try:
        skeleton = pipeline.run()
    except NoChanges as nc:
        print(f"\nNO_CHANGES: {nc.date_str}")
        return 2
    except PipelineError as e:
        print(f"\nPIPELINE_ERROR: {e}", file=sys.stderr)
        return 1

    slug = pipeline.slug or "default"
    print(f"\nPIPELINE_READY: skeleton={skeleton} slug={slug}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
