# Congress Trades — QoL Roadmap

Authoritative backlog for quality-of-life improvements to the congress-trades pipeline (repo: `holmes1371/congress-trades`, live site: `holmes1371.github.io/congress-trades`). Edit in place; commit changes alongside code.

Always load the karpathy-guidelines skill before starting anything here.

Closed `[x]` items are archived in `COMPLETED.md` with their full post-mortem prose. Stubs below preserve the original numbering so past session summaries and commit messages still resolve.

## Last session summary

This section holds **exactly one block** — the current/most-recent session — and it MUST be short. The next agent needs a cold pickup, not a recap.

Strict rules for writing it:

1. **≤5 bullets, ≤1 sentence each where possible.** Trim ruthlessly. If a bullet needs a paragraph, the real content belongs in a design note or `COMPLETED.md`; link it.
2. **Only what is open, in-flight, or just-filed.** Do NOT restate design decisions, rationale, or commit-by-commit walkthroughs for closed items — those live in `COMPLETED.md`; the next agent can read them if needed.
3. **No standing guidance here.** Session rituals, soft-delete convention, commit discipline — all of that lives in "For future agents" below. Do not duplicate.
4. **No cross-session carry-overs.** If something is still broken session-to-session, file it as a numbered ROADMAP item instead of repeating it here.
5. **Replace in place.** Do not append a new block and archive the old one below.

**2026-04-21 (session 1)**

- Scaffolded the multi-session handoff framework: `ROADMAP.md`, `COMPLETED.md`, `design/README.md`, `design/soft-delete-convention.md` (commit 4ff0e14). Modeled on the kids-schedule-github setup.
- Filed #1 — pytest suite + CI workflow (commit d7c2c33). `[ ]` not started; design-note questions in the item body cover which module anchors the extend-tests-in-step clause, HTTP mocking approach, and Python version pin.
- Refined the soft-delete convention after hitting `.git/HEAD.lock` and `.git/objects/maintenance.lock` mid-session: lock-cleanup is a per-op preflight `find .git -name "*.lock"` sweep, not post-crash recovery. ROADMAP bullet + design note updated.
- Nothing else in flight.

## For future agents

Read this file at the start of any session where Tom mentions "congress-trades", "the QoL list", "the roadmap", or asks about the next feature. The prioritization below is settled — do not re-debate it without prompting. Work items in order unless Tom explicitly says otherwise.

Session discipline:

- Invoke the `karpathy-guidelines` skill via the Skill tool at the start of every session that touches code. Reading `reference/guidelines.md` directly does not count — the skill-load step is what anchors the discipline for the rest of the session.
- git commits need the `-c user.name=... -c user.email=...` flags since there's no default identity in this workspace.
- **Soft-delete convention, not `rm`.** The FUSE mount this repo lives on refuses `unlink` but permits `rename`. `rm` fails with `Operation not permitted` even under `dangerouslyDisableSandbox`; `mv` works. Discard files with `mkdir -p .to_delete && mv <file> .to_delete/<tag>-$(date +%Y%m%d-%H%M%S)`. **Every git command on this mount also leaves one or more `.git/*.lock` files behind** (observed: `index.lock`, `HEAD.lock`, `objects/maintenance.lock`) which block the next git command — so run a pre-op sweep before every git call: `for lock in $(find .git -name "*.lock" -type f); do mv "$lock" ".to_delete/$(basename "$lock")-$(date +%Y%m%d-%H%M%S)"; done`. Lock-cleanup is a preflight, not a post-crash fix. The `.to_delete/` folder isn't tracked (no `.gitkeep`); agents create it on demand and Tom empties it manually from Windows periodically. Full convention + corrupt-index recovery ritual at `design/soft-delete-convention.md`. Unlink warnings on a successful git commit (`warning: unable to unlink '.git/index.lock': Operation not permitted`) are cosmetic; the commit landed, the lock will be swept by the next op.
- Before starting a non-trivial feature, write a short design note to `design/{feature-name}.md` capturing the scope, the decisions already made, and the test fixtures needed. A fresh session should be able to pick up mid-feature from that note plus the last commit, without re-litigating choices.
- Commit at every natural boundary, not just at feature completion. Half-finished work behind a clear commit message is recoverable; a dirty worktree is not.
- Use the built-in TodoWrite tool before starting each commit, and keep it current as you work. Tom watches the todo widget to see where you are in the plan; a stale or absent list means he can't track progress. At the start of every new commit, add/refresh todos for that commit's sub-tasks and mark one `in_progress`.
- **Flip `[ ]` → `[~]` as soon as Tom approves the plan for a backlog item — before the design note, before any code.** The status flag is there to tell the next agent what's actually in flight; flipping only at session end means a mid-session interruption leaves the item falsely marked "not started" even though a design note and half the commits exist. Record the flip in whichever commit introduces the first artifact for the item (usually the design note); if the plan is approved but no commit has landed yet, include the flip alongside the first real change so it doesn't need its own throwaway commit.
- End each session by updating this file — mark in-progress items, note any deviations or follow-ups — and commit the update. **Do not flip an item to `[x]` without explicit user signoff.** When the final code commit for an item lands, leave the item in `[~]`, record the SHA, and summarize what's pending manual verification. Tom pushes, tests manually, and either confirms the close (then the next session flips it to `[x]` with the SHA preserved) or returns feedback to address. Closing on your own reads as premature.
- **Update the "Last session summary" block between each commit during a multi-commit feature, not just at session end.** The block should always reflect what *just* landed and what's next, so a mid-feature handoff — mid-session or across agents — has a clean pickup point. The block is single-slot: replace in place, do not append. Older sessions' context lives in commit messages, `COMPLETED.md`, and `design/*.md`.
- **Closed items live in `COMPLETED.md`, not here.** When Tom signs off a `[~]` item, the next session moves its full prose into `COMPLETED.md` and leaves a one-line stub at the original item number in this file. Original numbers are stable — never renumber. When touching territory that overlaps a completed item, read its full entry in `COMPLETED.md` before re-deriving decisions.
- Honor the standing order: deterministic work lives in Python scripts; the agent does only judgment and interpretation. If a feature tempts you to move mechanical work into agent-handled text, push back.

Status legend:

- `[ ]` not started
- `[~]` in progress — include a note with what is done and what remains
- `[x]` done — include the commit SHA
- `[-]` descoped / on hold — full prose preserved in "Descoped / on hold" at the bottom for possible future revival

## Backlog (priority order)

### 1. [ ] Pytest suite + CI workflow

No test suite exists in the repo yet. Stand one up, wire it into GitHub Actions so a red check blocks merge, and add the "extend tests with the feature, not after" discipline to "For future agents" once the scaffolding lands. Until that clause is in the ROADMAP, agents writing new features have no standing rule requiring test coverage — so this item is a prerequisite for the rest of the backlog to be trustworthy.

Sketch: add `tests/` with pytest + whatever fixtures the first-batch modules need (sample capitoltrades payloads, a trimmed `member_bioguide.json`, etc). Seed coverage with the pure-function-y modules first — `scoring/factors.py` (alpha math, composite weights, z-score) and the ticker/normalization helpers in `fetch_trades.py` are the highest-signal starting points; HTML renderers and HTTP-heavy paths follow in subsequent PRs. Add `requirements-dev.txt` (or extend `requirements.txt`) with pytest, and a `.github/workflows/tests.yml` that runs pytest on push + PR to `main` with a red-check-blocks-merge policy.

Once the suite is in place, fold these into "For future agents":

- "Tests live in `tests/` and run on every push + PR via `.github/workflows/tests.yml`. A red test check blocks merge; don't mark a feature done with tests failing."
- "Any feature that modifies [core module(s) to be chosen in the design note] must extend the pytest fixtures in step with the change, not after."

Design-note questions to resolve before coding:

- Which module(s) carry the "extend tests with the feature, not after" clause? The kids-schedule equivalent names one concrete file (`process_events.py`); candidates here are `fetch_trades.py`, `compute_analysis.py`, `scoring/factors.py`, or a broader module-agnostic rule ("any module under `tests/` coverage"). Confirm with Tom.
- HTTP mocking approach for capitoltrades — record-and-replay fixture payloads, vcrpy, or the `responses` library. Similar question for the scoring pipeline's yfinance calls (mock at the `price_cache` layer or at yfinance itself — the former is simpler and lets the cache logic stay real).
- Python version pin vs matrix build. The repo's existing runtime setup (if any pinned version) anchors the decision.
- Whether to add coverage reporting (codecov or similar) now or defer.
- Whether the CI workflow should also lint (`ruff` / `black --check`), or keep scope to pytest only for v1.

## Descoped / on hold

Items parked here aren't dead — they're off the active queue but preserved in case priorities shift. Revive by moving the full prose back under "Backlog" at the original number and flipping `[-]` → `[ ]`.

_(none yet)_
