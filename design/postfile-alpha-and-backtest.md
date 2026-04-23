# Post-file alpha + walk-forward backtest

Shared design note for **ROADMAP #4** (post-file alpha recomputation) and **ROADMAP #5** (walk-forward backtest of the mirror strategy). Bundled because:

- Post-file alpha without an out-of-sample loop is a column change, not a viability test.
- Both features share fixtures, the same price-cache window, and a single schema cutover.

Plan approved at session 3 (2026-04-23). Complexity classified **large → ultrathink**. Fresh-session pickup: read this note, `design/project-framing.md`, and the last commit on the feature branch — no prior-session context required.

## Framing

Trade-date alpha answers *what did the member capture?* Post-file alpha answers *what could a follower capture?* `design/project-framing.md` makes the case that follower-facing rankings must be built on post-file alpha; this bundle is the feature that actually does the cutover. Trade-date alpha stays in the output as a diagnostic, not the headline.

The walk-forward backtest closes the loop from "the scoring pipeline ranks members" to "the strategy of following the ranked members produces alpha vs. benchmarks." Without it, the leaderboard is in-sample.

## Decisions settled

All Tom-approved at plan time; don't re-litigate without a new prompt.

1. **Entry rule.** Entry date = `max(txDate, published) + 2 business days`, then next-available-close fill via the existing `_next_close_at_or_after` forward-fill path. 2bd not 1 or 3: capitoltrades `pubDate` timestamps lag intra-day; a retail follower reading the morning digest can plausibly execute by next-day close + 1. Hard-coded, not parametrized.
2. **Horizons.** Unchanged — 5/20/60 business days. Only the entry point changes.
3. **Composite weights.** Unchanged in this bundle. The z-score weights map 1:1 from trade-date to post-file inputs. Re-tuning requires a validation window, which is exactly what #5 produces → **re-tuning is an explicit follow-up, out of scope here.**
4. **Trade-date alpha.** Stays in the xlsx under `_tradedate` suffix; dropped from the HTML leaderboard headline. `compute_trade_alpha` itself is untouched — the diagnostic path keeps working. `disclosure_drag_20d = mean_alpha_20d (post-file) - mean_alpha_20d_tradedate` becomes a visible column so the follower-cost of disclosure lag reads off the leaderboard directly.
5. **Backfill.** Full end-to-end recompute. No mixed-regime history.
6. **Exploratory dry run.** Commit 4 (composite cutover) stages on a single late-filer member first; before/after composite pastes into this note's "Dry run" section below. Forces a sanity check before the schema cutover commits land.
7. **Replay loop (walk-forward).** At rebalance date D, filter to trades with `published < D`, compute composite on that pre-D universe, pick top-K, buy every BUY from the cohort at `D+1 close`, exit at entry + 60 business days.
8. **Rebalance cadence.** Monthly at month-end. Weekly compounds noise; monthly matches the literature baseline and the NANC/KRUZ comparison surface. Parameter, not a structural commitment — reversible.
9. **Cohort rule.** Fixed K = 15. Matches the current `--top-n` default so the backtest evaluates the same follow list `default_follow_*.json` publishes.
10. **Exit rule.** Fixed horizon = 60 business days (matches `alpha_60d`). Trailing stops / sell-on-subsequent-disclosure belong to #6 (paper-trading log).
11. **Survivorship.** Include members during the window they were sitting. Dropping retired members would produce the standard survivorship bias trap; `design/project-framing.md` treats honest failure-mode visibility as compounding value.
12. **Baselines.** `naive_copy_everyone`, `NANC`, `SPY`. KRUZ/QQQ are already on the leaderboard's #2 benchmark block — no need to duplicate into the backtest surface. Three baselines is enough to answer the viability question.
13. **Compute.** On-demand only: `python scoring/backtest.py`. Not in CI — replay is expensive; correctness is covered by the synthetic-member unit test, determinism by the recorded output file.
14. **Backtest output format.** `scoring/output/backtest_<YYYYMMDD>.json`. JSON from day one: new artifact, no prior consumer, matches the `default_follow_*.json` convention.
15. **Leaderboard output format.** Stays xlsx for this bundle. `build_leaderboard.py` reads columns by name, so the rename-via-suffix cutover is backward-compatible without renderer changes. Swapping xlsx → JSON is orthogonal to this bundle and tracked as its own ROADMAP follow-up.

### Missing-data handling

- If `published` is empty or unparseable, post-file alpha returns `None` for that trade. Without a publication date we can't characterize the follower path; falling back to `txDate` would quietly inflate post-file alpha with trade-date capture, which is exactly the confound the bundle exists to eliminate.
- Trade-date alpha is unaffected — it still returns `None` only when `txDate` is missing.

## Schema cutover

### Per-trade dict (inside `members_data[bid]["trades"]`)

| Key | Before | After |
|---|---|---|
| `alpha_5d` / `alpha_20d` / `alpha_60d` | trade-date market-adjusted return | **post-file** market-adjusted return (primary) |
| `alpha_5d_tradedate` / `alpha_20d_tradedate` / `alpha_60d_tradedate` | — | trade-date market-adjusted return (diagnostic, additive) |

Rationale for keeping the unsuffixed names as post-file: `aggregate_member_factors` reads `alpha_20d` today; re-pointing that field to post-file makes the aggregator automatically consume the follower-relevant signal. Trade-date lives under a clearly-suffixed name so any accidental downstream reader fails in a legible way rather than silently producing stale-regime output.

### Per-member factor dict (output of `aggregate_member_factors`)

| Key | Before | After |
|---|---|---|
| `mean_alpha_20d`, `median_alpha_20d`, `hit_rate`, `sharpe_alpha` | trade-date | **post-file** |
| `mean_alpha_20d_tradedate`, `median_alpha_20d_tradedate`, `hit_rate_tradedate`, `sharpe_alpha_tradedate` | — | trade-date diagnostic (additive) |
| `disclosure_drag_20d` | — | `mean_alpha_20d (post-file) - mean_alpha_20d_tradedate` |

### Leaderboard xlsx (`scoring/output/leaderboard_*.xlsx`)

Primary columns (**unchanged names, post-file semantics**): `mean_alpha_20d`, `median_alpha_20d`, `hit_rate`, `sharpe_alpha`.
New diagnostic columns: `mean_alpha_20d_tradedate`, `median_alpha_20d_tradedate`, `hit_rate_tradedate`, `sharpe_alpha_tradedate`, `disclosure_drag_20d`.
Z-score / composite columns unchanged by name (they now feed from post-file).

`build_leaderboard.py` needs no code change — it reads by column name, and `mean_alpha_20d` keeps its header.

### Backtest JSON (`scoring/output/backtest_<YYYYMMDD>.json`)

```
{
  "generated": "YYYY-MM-DD",
  "params": {
    "cadence": "monthly",
    "K": 15,
    "exit_bdays": 60,
    "first_rebalance": "YYYY-MM-DD",
    "last_rebalance": "YYYY-MM-DD"
  },
  "rebalances": [
    {
      "date": "YYYY-MM-DD",
      "cohort": ["bioguide_1", "..."],
      "trades": [
        {
          "bioguide": "...", "ticker": "...",
          "entry_date": "...", "entry_close": N,
          "exit_date": "...",  "exit_close": N,
          "alpha_vs_spy": N
        }
      ]
    }
  ],
  "summary": {
    "strategy": {
      "total_return": N, "alpha_vs_spy": N, "alpha_vs_nanc": N,
      "alpha_vs_naive_copy_everyone": N, "hit_rate": N, "sharpe": N,
      "n_rebalances": N, "n_trades": N
    },
    "naive_copy_everyone": { "total_return": N, "hit_rate": N },
    "NANC": { "total_return": N },
    "SPY":  { "total_return": N }
  }
}
```

A one-row summary (`alpha_vs_*`, `hit_rate`, `sharpe`, `n_trades`, `n_rebalances`) also lands in a new `Backtest` sheet of `leaderboard_*.xlsx` at score-time, but only if a backtest output exists on disk. This decouples commit 6 from commits 4–5 — the schema cutover doesn't depend on the backtest being wired up yet.

## Fixture plan

All under `tests/fixtures/`. No new `prices/*.csv` recordings — synthetic data covers both axes.

### `synthetic_alpha_scenarios.py` — extend in commit 2

Every scenario gains:
- `expected_alpha_post_file_approx` (currently only on `POSTFILE_DIVERGENCE`).
- Where the current ticker / benchmark price series don't span through `publication_date + entry_buffer + horizon`, extend them.

`test_alpha_math.py` parametrizes over both `compute_trade_alpha` and `compute_trade_alpha_postfile` against the same scenario list with the two `expected_alpha_*` keys.

### `backtest_synthetic_member.py` — new in commit 2

One synthetic member, 24 months of monthly BUYs on one ticker (`"SYNTH"`), with:
- Deterministic price track for `SYNTH` and `SPY` → known per-trade post-file alpha.
- Known `filedAfterDays` on every trade so post-file entry is derivable.
- Computable expected summary (strategy total return, per-rebalance cohort, per-trade PnL) so `test_backtest.py` asserts exact numbers, not approximate.

Module-level `SYNTH_MEMBER` dict + `SYNTH_PRICES` dict keyed by date → close. `test_backtest.py` loads it, runs the replay loop, asserts equality.

## Commit sequence

1. **Design note + ROADMAP flip** — this file. ROADMAP #4/#5: `[ ]` → `[~]`. No production-code change.
2. **Fixture extension** — `synthetic_alpha_scenarios.py` gains `expected_alpha_post_file_approx` for all scenarios; `backtest_synthetic_member.py` is new. No production-code change.
3. **`compute_trade_alpha_postfile`** — add alongside `compute_trade_alpha` in `factors.py`. `test_alpha_math.py` extended in the same commit per the ROADMAP discipline (`scoring/factors.py` changes ship with same-commit test coverage).
4. **Composite cutover + dry run** — `aggregate_member_factors` and `compute_composite` swap input alpha columns; per-member factor dict gains `_tradedate` diagnostics and `disclosure_drag_20d`. `test_composite_math.py` extended. Dry run on one late-filer member pastes into this note's "Dry run" section.
5. **Leaderboard xlsx + HTML** — `score_members.py` display column list updated; schema-contract test (`test_leaderboard_filter_columns.py`) extended. HTML renderer left unchanged by construction (reads by column name).
6. **Walk-forward backtest** — new `scoring/backtest.py`, new `tests/test_backtest.py` using the synthetic-member fixture. Record a run against the real post-#3 dataset as `scoring/output/backtest_<YYYYMMDD>.json` and extend `leaderboard_*.xlsx` with a `Backtest` summary sheet.

Each commit leaves `pytest` green and the worktree buildable. Commits 3–6 can each slip to a new session; commits 1–2 are self-sufficient design-and-fixture artifacts that don't introduce half-finished production state.

## Dry run (recorded at commit 4)

Ran the commit-4 composite cutover against the main-worktree trade cache
(538 members, pruned by post-#3 filters + the 365d / ≥10-trades qualify
floor → 59 qualified members). Prices loaded from the committed CSV
cache (1024 of 1063 tickers resolvable; the rest foreign or delisted,
no impact on the qualified universe). No yfinance calls.

### Rank-shift distribution across the qualified universe

| metric | value |
|---|---|
| qualified members | 59 |
| median absolute rank shift | 3 places |
| max absolute rank shift | 53 places |
| members shifting > 10 places | 22 / 59 |
| members shifting > 20 places | 14 / 59 |
| members shifting > 30 places | 7 / 59 |
| top-30 overlap (pre vs post) | 21 / 30 |

Top-30 composition churn of ~30% is in the "larger than 10+" territory
the plan flagged as worth noting. This is the expected direction — the
cutover removes the disclosure-lag confound, so members whose
trade-date alpha was driven by pre-publication price moves (which a
follower can't capture) drop out, and members whose trades have
post-publication persistence rise. The magnitude validates that this
bundle is a *ranking change*, not just a column rename, and justifies
Tom's signoff on a six-commit migration rather than an inline tweak.

### Top disclosure-drag members (where a follower loses most to lag)

| member | post-file α₂₀ | trade-date α₂₀ | drag | mean lag (d) |
|---|---:|---:|---:|---:|
| David Taylor | -1.5% | +1.9% | -3.4pp | 13.7 |
| Valerie Hoyle | +1.0% | +4.3% | -3.2pp | 20.4 |
| Shelley Moore Capito | +1.7% | +4.8% | -3.1pp | 16.2 |
| Richard McCormick | -0.8% | +2.2% | -3.0pp | 28.9 |
| Katie Britt | -1.1% | +1.9% | -2.9pp | 153.0 |
| Nancy Pelosi | -3.7% | -1.9% | -1.8pp | 18.2 |

Every top-10 drag member's post-file alpha is lower than their
trade-date alpha — the expected sign for informed trades whose alpha
decays before a follower can act. Britt's 153-day mean lag is a
filter flag on its own (late_filing ≥ 40 days covers it); the
composite already dings her for it via `neg_lag_z`.

### Featured example — large adverse rank mover

**Charles Fleischmann** (TN-3, R, 38 trades in 365d, mean lag 24.7d):

| metric | pre-cutover | post-cutover |
|---|---:|---:|
| mean_alpha_20d | +1.8% (trade-date) | -0.8% (post-file) |
| composite | +0.713 | -0.394 |
| rank | 5 / 59 | 50 / 59 |

Fleischmann's trade-date alpha was positive (+1.8%) — his picks
captured market-adjusted gains in the 20 bdays after he traded. But by
the time the 24-day publication lag cleared plus a 2-bday follower
entry buffer, the runup was spent: post-file alpha is -0.8%. He drops
from the top 10% of qualified members to the bottom 20%. This is the
project-framing note's central hazard rendered numerically: trade-date
alpha is what he captured; post-file alpha is what a follower can
capture; the two are not the same number.

### Notes for downstream commits

- Commit 5 updates `leaderboard_*.xlsx` column names and the HTML
  renderer's headline metric to reflect the post-file semantics. The
  Fleischmann example above is the kind of story the HTML page should
  surface visibly (via `disclosure_drag_20d` column) so a reader
  understands why rankings differ from trade-date-era intuitions.
- Commit 6 wires the walk-forward backtest. The rank churn above is
  evidence the post-file composite is a materially different signal
  to backtest against; the fact that it reshuffles the universe means
  the #5 backtest is a real viability test, not a trivial replay of
  #4's sort order.

## Out of scope / follow-ups

- **Composite weight re-tuning.** Post-file alpha changes the signal distribution; current z-score weights are inherited from the trade-date regime. Once #5's walk-forward surface exists, a validation-window re-tune is defensible and should be filed as a new ROADMAP item.
- **Leaderboard xlsx → JSON migration.** xlsx is vestigially human-readable but is machine-only in practice — raised in session-3 planning. Tracked as a new ROADMAP item filed at session 3's end.
- **Entry-buffer sensitivity.** 2bd is the chosen default. If dry-run results at 1 or 3 business days would move the composite materially (say, >10% of members crossing a rank threshold), worth noting — but not re-opening unless the gap is large.
- **Paper-trading log (#6).** Consumes post-file alpha columns from this bundle; nothing new required here, just unblocked.
