# Design notes

Per-feature design notes for the congress-trades pipeline. One Markdown file per non-trivial feature — `design/{feature-name}.md` — capturing the scope, the decisions already made, and the test fixtures needed, so a fresh session can pick up mid-feature from the note plus the last commit without re-litigating choices.

## When to write one

Any backlog item that is more than a one-file surgical edit. The design note usually lands as its own commit *before* the implementation commits, so the plan is reviewable in isolation and the `[ ] → [~]` flip on the ROADMAP item is tied to a concrete artifact.

Triggers:

- Multi-file change.
- New module or subsystem.
- Non-obvious design choice with live options to rule out.
- Anything that reshapes the extracted schema, the scoring weights, the site render, or the GitHub Actions workflows.

## What to include

- **Scope** — what's in, what's explicitly out, and (if bundled) how the pieces relate.
- **Locked decisions** — numbered list of choices already made, each with a one-line rationale so the next agent knows why not to revisit them.
- **Sketches** — CSS/HTML/Python/JSON stubs if the note is pre-implementation; these set the shape without committing to line-exact code.
- **Test plan** — which test files and new cases the change will add or extend. Target test count after the change if the suite is non-trivial.
- **Non-goals** — what tempting extensions are deliberately out of scope, so future reviewers don't ask "why didn't you add X".
- **Responsibility table** — a `| Concern | Owner | Notes |` table at the bottom mapping each moving part to the file/function that owns it (and to "None / ephemeral" for things explicitly not persisted). This enforces the standing order that deterministic work lives in Python.
- **Commit plan** — the sequence of commits the feature will produce, and at which step the ROADMAP flip to `[~]` happens.

## Existing notes

Standing references (read as needed, not re-litigated per session):

- `project-framing.md` — what this project is, the central hazard (disclosure lag), the right benchmarks (NANC/KRUZ/SPY/QQQ), and what the project is not. Read at the start of any session.
- `soft-delete-convention.md` — convention for discarding files on this FUSE mount, plus the pre-op `.git/*.lock` sweep and corrupt-index recovery ritual.

Active feature notes (paired with an in-flight `[~]` item in `ROADMAP.md`):

- `cost-tax-sizing-overlays.md` — ROADMAP #7. Scope, 9 locked decisions, and five-commit plan for the cost / tax / sizing overlay bundle. New `scoring/costs.py` pure-math module (tiered slippage bps, gain-only tax haircut, equal vs. range sizing); reporting-layer only — paper-log CSV and backtest per-trade rows stay gross. Backtest JSON's `summary.strategy` gains `*_net` fields + `overlays` config; paper-log lifetime summary gains `Gross | Net` columns. Defaults: tiered slippage, tax 0.2975 (federal short-term 24% + VA 5.75%), equal-weight sizing.

Closed feature notes (retained as historical context; matching ROADMAP item lives in `COMPLETED.md`):

- `paper-log.md` — ROADMAP #6. Scope, 9 locked decisions, CSV schema, and five-commit plan for the auto paper-trading log. New `scoring/paper_log.py` module with `PaperLog` class (open/close/mark-to-market/retraction); persistent CSV ledger at `scoring/paper_log/positions.csv`; new `build_paper_log.py` rendering a three-section `site/paper_log.html`; pipeline wiring between `score_members` and `build_site`. Reuses `scoring/backtest.py` primitives (`close_at_or_after`, `close_n_positions_later`, `select_cohort`) so the live log is the continuation of #5's retrospective backtest. Closed `baefa44`.

- `pytest-ci-suite.md` — ROADMAP #1. Scope, fixtures, and commit plan for the pytest suite + `.github/workflows/tests.yml`. Six-commit sequence; tests target stable primitives, not the churning assemblies that #2–#14 will rewrite. Closed `3022a38`.
- `benchmark-row.md` — ROADMAP #2. Scope and commit plan for the NANC/KRUZ/SPY/QQQ benchmark reference block on the leaderboard page (primary) and the weekly report (secondary, deferred to #13). Four-commit sequence; option (A) — reference row only, not a follow-list mirror-PnL comparison. Closed `6a5b0eb`.
- `signal-quality-filters.md` — ROADMAP #3. Scope, 10 locked decisions, and five-commit plan for the four signal-quality filters (broad-market ETF drop, options drop, non-self-owner tag, late-filing tag). `scoring/filters.py` as a new module with four pure functions composed in `score_members.py`; factor aggregation extended with six new columns; leaderboard surface gains four new columns in both 180d and 365d tables. Closed `ae1f56a`.
- `postfile-alpha-and-backtest.md` — ROADMAP #4 + #5 (bundled). Scope, decisions, schema cutover, dry-run results, and backtest output for the post-file alpha recomputation + walk-forward backtest bundle. Six-commit sequence; composite re-pointed from trade-date to post-file alpha under the same column names; new `scoring/backtest.py` module + recorded run at `scoring/output/backtest_20260423.json`. Closed `829c345` / `9851bd0`.
