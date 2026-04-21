# Congress Trades — Completed Items

Archive for closed items from `ROADMAP.md`. When Tom signs off a `[~]` item, the next session:

1. Flips the ROADMAP entry to `[x]` and records the closing commit SHA.
2. Moves the full prose of the item (scope, decisions, rationale, commit trail, any visual-QA notes) into this file under its original number.
3. Leaves a one-line stub in `ROADMAP.md` at that number so past session summaries and commit messages still resolve: e.g. `1\. [x] <Title> — <SHA> — see COMPLETED.md`.

Original numbers are stable — never renumber. When touching territory that overlaps a completed item, read its full entry here before re-deriving decisions.

## Closed items

### 1. [x] Pytest suite + CI workflow — 3022a38

Closed 2026-04-21 after Tom confirmed the first green pytest run on GitHub Actions.

**Goal.** Stand up a pytest suite over the stable primitives of the congress-trades pipeline and wire it into CI, without pinning any of the assembly-level surfaces (composite weights, ranking output, leaderboard columns) that ROADMAP items #2–#11 are expected to rewrite. Get the "add tests with the feature" discipline into the session standing order so the suite stays load-bearing as the backlog progresses.

**Guiding principle.** Test the primitives, not the assembly. Covered in v1: ticker normalization, trade-dict `_normalise_trade`, price-cache read contract, alpha math, composite math, schema contract of the recorded capitoltrades fixture. Deliberately skipped: current composite weights, default-follow list output, leaderboard/report HTML shape, `score_members.py` defaults. Full rationale in `design/pytest-ci-suite.md` (Guiding principle + Stable-vs-churning surface map).

**Commit trail.**

- `c571481` — pytest 1/6: design note + `[~]` flip on #1.
- `6b7ea0b` — pytest 2/6: scaffolding (`tests/conftest.py`, `requirements-dev.txt`, `tests/fixtures/`, `tests/fixtures/_record.py`).
- `897dbd1` — pytest 3/6: batch 1 — `test_ticker_normalization.py` (23 cases), `test_fetch_trades_normalise.py` (6 cases).
- `b6861d5` — pytest 4/6: batch 2 — `test_price_cache.py` (4), `test_alpha_math.py` (10), `test_composite_math.py` (22).
- `49d3690` — pytest 5/6: batch 3 — `test_fetch_trades_parse.py` (12, schema-contract over the recorded fixture).
- `3022a38` — pytest 6/6: `.github/workflows/tests.yml` (Python 3.11, `on: push` only) + the three "For future agents" bullets (tests-run-on-push, ship-tests-with-the-feature, factors.py-extends-its-tests).

Final state: 77 pytest cases green locally and on GHA.

**Amendments to the original plan** (all documented in `design/pytest-ci-suite.md`):

- *Batch 1.* Original plan had three batch-1 files; `test_money_range_parse.py` and `test_date_parse.py` were dropped because the primitives they would have targeted don't exist — the capitoltrades payload delivers `value` as an already-parsed int, and date parsing is stdlib `date.fromisoformat`. The one non-trivial date transformation (`pubDate[:10]` truncation) was folded into `test_fetch_trades_normalise.py`.
- *Batch 2.* Price-cache "concurrent access" case dropped (no locking in code to assert against). Synthetic alpha Scenario 5 was renamed from `missing_day_forward_fills` to `entry_day_missing_forward_fills` and reshaped to test the entry-side forward-fill `_next_close_at_or_after` actually implements (the original had imagined an exit-side forward-fill that `_close_n_bdays_later` doesn't do — it counts DataFrame index positions, not calendar business days). Composite-weight parametrization is implemented via `monkeypatch.setattr(factors, "COMPOSITE_WEIGHTS", ...)` because `compute_composite` reads weights from module scope; each parametrize case isolates one z-column under 100% weight and asserts the composite equals that column.
- *Batch 3.* `test_transaction_classification.py` was dropped — no standalone classification primitive in code (BUY/SELL filtering is inline at call sites; options/corp-actions/exchange types don't exist in the pipeline). The BUY/SELL domain constraint is instead pinned at the schema-contract level in `test_fetch_trades_parse.py`.
- *Batch 4.* CI workflow simplified from `on: push (branches: [main]) + on: pull_request` to plain `on: push`, and the branch-protection checklist was removed. Tom pushes directly to `main`; a PR gate and status-check merge requirement don't match the actual workflow.

**Standing-order additions.** Three bullets added to ROADMAP's "For future agents" section:

1. Tests run on every push; don't close a feature with red tests — check the commit's test run before calling it done.
2. **Ship tests with the feature, not after.** New primitive (parser, adapter, pure-math function, schema transform, cache seam) → pytest coverage for it in the same commit. Assembly-level code expected to be rewritten by #2–#11 is deliberately skipped per the Guiding Principle; if skipping, say so in the commit message.
3. `scoring/factors.py` is coupled hard to `test_alpha_math.py` / `test_composite_math.py` — any change to that file extends those tests in the same commit. Other modules with existing test coverage extend their fixtures in step with the change, not after.

**Infra notes for future sessions.**

- Fixture re-recording: `tests/fixtures/_record.py` regenerates capitoltrades and yfinance fixtures. Not run in CI.
- conftest injects both repo root and `scoring/` onto `sys.path` because `scoring/score_members.py` uses a sibling import (`from price_cache import get_prices`) that works as a script but not as a package member. If any scoring module moves to absolute imports, that sys.path hack can come out.
- The three "Batch N amendment" paragraphs in `design/pytest-ci-suite.md` are the best entry point for understanding why particular cases are shaped the way they are — read those before editing a batch's test file.
