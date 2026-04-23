# Auto paper-trading log

Design note for **ROADMAP #6** — an append-only ledger that records
what a follower would have done at every pipeline run, and tracks the
resulting PnL as positions close. Plan approved session 3
(2026-04-23). Complexity classified **medium → think hard**.

Fresh-session pickup: read this note + `design/postfile-alpha-and-backtest.md`
(which pins the post-file composite this feature consumes) + the last
commit on the feature branch. No prior-session context required.

## Framing

The #5 backtest is the retrospective mechanic: pick cohort → buy at
D+1 close → hold 60 bdays → record PnL. The paper-trading log is the
**prospective** version of the same mechanic, run incrementally as
new disclosures arrive. The key difference is persistence: each
pipeline run opens new positions, marks open positions to market, and
closes positions whose horizon came due — writing to an append-only
ledger that builds a live track record over 6–12 months.

Because the mechanic matches #5, this bundle reuses `scoring/backtest.py`
primitives rather than re-implementing them: `_close_at_or_after`,
`_close_n_positions_later`, `_select_cohort`. The live log is exactly
the continuation of the recorded backtest.

## Decisions settled

All Tom-approved at plan time. Don't re-litigate without a new prompt.

1. **Entry rule.** Buy at **next pipeline-run close** for every BUY
   from a cohort member whose `published` date has fallen since the
   last run. Matches #5's D+1 close semantics and what a follower
   reading the morning digest could execute. Under today's weekly
   cadence the "next run" is next week; once #11 (daily cadence)
   lands it becomes next-day. The rule is invariant under cadence —
   the ledger records what a follower *could* do given the pipeline's
   current cadence, not a hypothetical faster one.
2. **Exit rule.** Fixed horizon = **60 business days**, matching #5.
   Trailing stops / sell-on-subsequent-disclosure belong to later
   scope expansion (#7 territory — they need a cost model). v1
   stays tight.
3. **Cohort selection.** **Top-K = 15** by composite, computed the
   same way as `default_follow_*.json`. Reuses
   `scoring/backtest.py::_select_cohort` directly. **Cohort is
   snapshotted at the moment the BUY enters the log** — subsequent
   rank changes don't retroactively close positions. A member losing
   cohort status tomorrow doesn't cancel today's executed trade.
4. **Storage format.** **CSV at `scoring/paper_log/positions.csv`**.
   Simplest, pandas-readable, diff-friendly in git (each append is a
   visible commit diff). Parquet would be binary; sqlite overkill for
   an append-only ledger. Schema below.
5. **Position sizing.** **Equal-weight** across signals. Matches #5's
   backtest baseline; disclosed-value-weighted is #7 territory (bundled
   with position-sizing overlays).
6. **Surface.** **New HTML page `site/paper_log.html`**, rendered by a
   new `build_paper_log.py` paralleling `build_leaderboard.py`. Three
   sections: open positions (days held + mark-to-market PnL),
   recently-closed (last 30 days + realized PnL), lifetime summary
   (total return, hit rate, alpha_vs_spy). Landing-page nav in
   `build_site.py` gets a link alongside "Member Leaderboard." No
   Cowork artifact in v1 — #13 remains gated on prerequisites.
7. **Retraction handling.** Each pipeline run compares open log
   positions against the member's current capitoltrades trades by
   `tx_id`. If a logged position's `tx_id` no longer appears, mark
   `status=retracted` **but keep the row** with its existing entry
   price and mark-to-market as of the retraction date. Deletion would
   destroy track-record fidelity — "we acted on this signal at the
   time" is a real data point. Retracted positions stop accruing PnL
   and drop from the "open" view but appear in a small "retracted"
   section of the HTML page.
8. **Pipeline wiring.** Paper-log update runs **after**
   `score_members.py` finishes (so the composite and cohort are
   current) but **before** `build_site.py` (so the page regenerates
   with fresh data). New entry point
   `scoring/paper_log.py::main()` called from `run_pipeline.py`.
   Idempotent: re-running on the same day is a no-op except for
   mark-to-market updates.
9. **No historical backfill.** Log starts empty from commit 1.
   Backfilling from historical signals would reproduce #5 under a
   different name and dilute the "prospective track record"
   property. An explicit choice — worth re-opening only if Tom
   decides the track-record-vs-reproduction trade-off shifts.

## CSV schema

`scoring/paper_log/positions.csv` — one row per position, append-only
except for mark-to-market / close / retraction updates on existing
rows.

| column | type | semantics |
|---|---|---|
| `position_id` | string (UUID4) | stable per position; survives status changes |
| `bioguide` | string | member who disclosed |
| `tx_id` | int | capitoltrades txId — identity key for retraction detection |
| `ticker` | string | normalized ticker (post-`normalize_ticker`) |
| `signal_date` | ISO date | `trade["published"]` |
| `open_date` | ISO date | pipeline-run date when we observed the signal |
| `entry_date` | ISO date | first trading day ≥ open_date + 1 (forward-filled) |
| `entry_close` | float | filled at position open |
| `target_exit_date` | ISO date | entry_date + 60 bdays (predictive) |
| `exit_date` | ISO date \| "" | populated when closed |
| `exit_close` | float \| "" | populated when closed |
| `status` | enum | `open` / `closed` / `retracted` |
| `pnl_abs` | float | realized on close; mark-to-market on open |
| `pnl_pct` | float | realized on close; mark-to-market on open |
| `alpha_vs_spy` | float \| "" | populated on close |
| `retracted_at` | ISO date \| "" | date the disclosure disappeared, if applicable |
| `last_updated` | ISO datetime | wall-clock; changes every mark-to-market refresh |

**Identity key.** `(bioguide, tx_id)` — capitoltrades' `txId` is a
stable integer per disclosure. If a member re-publishes the same
trade with a new txId (edit), we'd double-log; considered acceptable
because real edits are rare and a duplicate row is visible noise, not
silent corruption.

## Fixture plan

- **Reuse** `tests/fixtures/backtest_synthetic_member.py` from #5
  (24 monthly BUYs on SYNTH, deterministic ladder). The paper log's
  open/close operations trace the same price data.
- **Add** a second synthetic member with a retracted trade (same
  structure but one trade vanishes between simulated pipeline runs),
  so retraction handling has coverage. Extend
  `backtest_synthetic_member.py` in the same commit that introduces
  the retraction logic.
- **Time injection.** `PaperLog.walk_from(start, end, today)` takes
  an explicit `today` parameter — CLI passes `today=date.today()`,
  tests pass synthetic dates. No monkey-patching of `date.today()` in
  tests.

## Commit sequence (5 commits)

1. **Design note + ROADMAP flip.** This file. #6 flips `[ ]` → `[~]`.
   No production-code change.
2. **Core module + empty ledger.** `scoring/paper_log.py` — `PaperLog`
   class with open/close/mark-to-market operations, `walk_from`
   loop driver, CSV I/O. Empty `scoring/paper_log/positions.csv`
   seeded with header-only row. `tests/test_paper_log.py` — unit tests
   pinning each operation against the synthetic fixture.
3. **Retraction handling + tests.** Extend the synthetic fixture with
   a retracted-trade member; `_detect_retractions` / `_apply_retraction`
   in `paper_log.py`; property tests for: retraction preserves the
   row, marks status, sets retracted_at, stops PnL updates.
4. **HTML render + schema-contract test.** `build_paper_log.py`
   parallel to `build_leaderboard.py`; three sections (open /
   recently-closed / lifetime summary); `tests/test_paper_log_page.py`
   pinning the rendered HTML structure (section headers, row cell
   shapes, em-dash fallbacks on unpopulated fields).
5. **Pipeline wiring + landing-page link.** `run_pipeline.py` calls
   `paper_log.main()` after `score_members` and before `build_site`;
   `build_site.py` nav row adds a link to `paper_log.html`;
   `test_leaderboard_filter_columns.py` or a new
   `test_site_index.py` asserts the link is present.

Each commit leaves `pytest` green and the worktree buildable. Commits
3–5 can each slip to a new session if interrupted; commits 1–2 are
self-sufficient (design note + a working but unwired core module).

## Relationship to #5 (reuse surface)

`scoring/paper_log.py` imports from `scoring/backtest.py`:

- `_close_at_or_after(prices, target)` — entry-day resolution.
- `_close_n_positions_later(prices, entry_day, n)` — target-exit
  resolution. Also used for mark-to-market when the current date is
  less than `n` positions from entry.
- `_select_cohort(members_data, ticker_adv, D, window_days, min_trades, K)`
  — cohort selection at pipeline-run time.
- `monthly_rebalance_dates(start, end)` — unused by the paper log
  itself (which runs whenever the pipeline fires, not on a monthly
  grid), but shares the same `pd.bdate_range` calendar convention so
  the test fixtures align.

If those primitives need refactoring later (e.g. to absorb a holiday
calendar), the paper log inherits the change for free. If `backtest.py`
grows module-private variants that diverge from what the paper log
needs, promote a shared helper to a neutral location rather than
duplicating — file the refactor as its own item.

## Out of scope / follow-ups

- **Transaction costs / slippage.** ROADMAP #7 territory. The paper
  log records gross PnL; a cost overlay plugs into the same rows
  later without schema change.
- **Trailing stops / event-driven exits.** #7-adjacent. The exit-date
  field is populated from the 60-bday rule today; adding rule variants
  means extending the `status` enum and the exit logic but doesn't
  rewrite the schema.
- **Cowork artifact surface.** #13 — live-refreshing view of the
  same ledger. When #13 lands, it reads the same CSV the HTML page
  reads; no separate data pipeline.
- **Position sizing by disclosed value range.** #7 territory (position
  sizing overlays). Equal-weight is the v1 baseline.
- **Multi-account tracking.** One ledger, one "strategy." Future
  variants (e.g. 180d-window cohort in a separate ledger) would live
  in parallel `paper_log/positions_<variant>.csv` files and replicate
  the render logic with a variant-aware header.
