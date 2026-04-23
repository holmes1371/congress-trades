# Congress Trades — Completed Items

Archive for closed items from `ROADMAP.md`. When Tom signs off a `[~]` item, the next session:

1. Flips the ROADMAP entry to `[x]` and records the closing commit SHA.
2. Moves the full prose of the item (scope, decisions, rationale, commit trail, any visual-QA notes) into this file under the item's current ROADMAP number.
3. Leaves a one-line stub in `ROADMAP.md` at that number: `N\. [x] <Title> — <SHA> — see COMPLETED.md`.

Numbers here mirror `ROADMAP.md`'s priority ordering — when the active backlog renumbers, the archive entries renumber in the same commit so the stubs keep resolving. Past references that predate a renumber can be resolved via the renumber commit in git history. When touching territory that overlaps a completed item, read its full entry here before re-deriving decisions.

## Closed items

### 1. [x] Pytest suite + CI workflow — 3022a38

Closed 2026-04-21 after Tom confirmed the first green pytest run on GitHub Actions.

**Goal.** Stand up a pytest suite over the stable primitives of the congress-trades pipeline and wire it into CI, without pinning any of the assembly-level surfaces (composite weights, ranking output, leaderboard columns) that ROADMAP items #2–#13 are expected to rewrite. Get the "add tests with the feature" discipline into the session standing order so the suite stays load-bearing as the backlog progresses.

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
2. **Ship tests with the feature, not after.** New primitive (parser, adapter, pure-math function, schema transform, cache seam) → pytest coverage for it in the same commit. Assembly-level code expected to be rewritten by #2–#13 is deliberately skipped per the Guiding Principle; if skipping, say so in the commit message.
3. `scoring/factors.py` is coupled hard to `test_alpha_math.py` / `test_composite_math.py` — any change to that file extends those tests in the same commit. Other modules with existing test coverage extend their fixtures in step with the change, not after.

**Infra notes for future sessions.**

- Fixture re-recording: `tests/fixtures/_record.py` regenerates capitoltrades and yfinance fixtures. Not run in CI.
- conftest injects both repo root and `scoring/` onto `sys.path` because `scoring/score_members.py` uses a sibling import (`from price_cache import get_prices`) that works as a script but not as a package member. If any scoring module moves to absolute imports, that sys.path hack can come out.
- The three "Batch N amendment" paragraphs in `design/pytest-ci-suite.md` are the best entry point for understanding why particular cases are shaped the way they are — read those before editing a batch's test file.

### 2. [x] NANC / KRUZ / SPY / QQQ benchmark row — 6a5b0eb

Closed 2026-04-22 after Tom confirmed the rendered leaderboard page carried the benchmark block above the 365-day table, with the four values spot-checked against Yahoo Finance.

**Goal.** Surface cumulative total-return numbers for four reference instruments (NANC, KRUZ, SPY, QQQ) over the existing 180d and 365d windows, so the value-add question — "is the curated follow list beating these?" — becomes visible rather than implicit. Framing anchor: `design/project-framing.md`'s central-hazard + four-benchmark list.

**Design call (option A over B).** The ROADMAP prose originally described "a cumulative-PnL row comparing the curated follow list's mirror PnL against each benchmark." Code reality on first read showed no mirror-PnL anywhere in the pipeline — per-trade alpha vs. SPY is the only cumulative metric, and no "follow-list mirror PnL" aggregate is computed. Building a simulator here would have duplicated 30–50% of #5 (walk-forward backtest) early, with material scope overlap. Session-2 chose option A (benchmark reference row only; simulator deferred to #5) in the design call before coding started. Full rationale in `design/benchmark-row.md`'s Scope + Locked decisions.

**Commit trail.**

- `0254ef0` — benchmark 1/4: `design/benchmark-row.md` + `[~]` flip on #2. Bundled the first backlog renumber of session 2 (old-#2 post-file alpha → #4; old-#3 benchmarks → #2; old-#4 filters → #3; old-#5 paper log → #6; old-#6 walk-forward → #5) and the cross-ref migration in `design/pytest-ci-suite.md`. Replaced the "original numbers are stable — never renumber" convention with "numbers follow priority order; renumber together on reprioritize; update cross-references in the same commit."
- `3493a7e` — benchmark 2/4: `scoring/benchmarks.py` (`benchmark_cumulative_return` + `all_benchmark_returns` over the `scoring.price_cache` seam), `tests/test_benchmarks.py` (11 parametrized cases — math, empty/single-row/NaN frames, `price_frame=` injection, ticker-missing, fetch-when-no-frame, `all_benchmark_returns` shape), `tests/fixtures/prices/{NANC,KRUZ,QQQ}.csv` (synthetic fixtures matching `SPY.csv`'s 271-day range with designed total returns +20% / −5% / +15% for exact-value assertions).
- `2bd1f28` — benchmark 3/4: wired into `build_leaderboard.py` — new `build_benchmark_block(long_returns, short_returns)` helper rendered as a `.weights-card`-styled card with a 4×2 table (ticker × window), `{benchmark_block}` placeholder between the composite-weights card and the 365-day section, and "Benchmark returns above are gross of expense ratios and slippage" appended to the footer. Import shift in `scoring/benchmarks.py` from sibling-style (`from price_cache import get_prices`) to package-style (`from scoring.price_cache import get_prices`) so callers at repo root can resolve it.
- `6a5b0eb` — benchmark 4/4: `tests/test_leaderboard_benchmark_block.py` (7 schema-contract cases) over two seams — `build_benchmark_block`'s HTML (all four tickers, `fmt_pct` shape, em-dash for `None`, window headers, card class reuse) and `PAGE_TEMPLATE.format(...)` (footer footnote present; benchmark placeholder sits above the 365-day section).

Final state: 95 pytest cases green locally. Leaderboard renders the benchmark block with live yfinance data on rebuild.

**Scope adjustments from the ROADMAP prose.**

- *Primary surface.* ROADMAP said "in the weekly report"; the block landed on `leaderboard.html` because that's where the 180d/365d windows already exist and where "follow the top-K" lives. The weekly report has no cumulative-PnL concept today — adding the block there requires skeleton-fill plumbing. Filed as #12 (weekly-report benchmark strip).
- *Mirror-PnL comparison.* Deferred to #5 per the option-A design call. The card title reflects the reality: "Benchmark Reference — Cumulative Return," not "Follow-list PnL vs. Benchmarks."
- *Fixture strategy.* Design note defaulted to recording via `_record.py`; NANC/KRUZ/QQQ weren't present in the sandbox's `scoring/cache/prices/`, so synthetic CSVs were generated instead — primitive math is identical for real or synthetic, and real data only starts mattering when #5 uses the same fixtures for backtest replay.
- *Sandbox render QA.* Blocked by a pre-existing `scoring/price_cache.py` bug (single-ticker `_bulk_download` branch builds a `pd.DataFrame` from scalar `pd.NA` values when yfinance returns an empty `Close` column). Filed as #10. Tom did the live render-and-spot-check on push; confirmation landed in this session.

**Standing follow-ons filed during #2** (both in `546063d`, sequenced to land before they can bite):

- *#10* — Fix `price_cache.py` single-ticker fallback on empty yfinance response. Before #11 (daily cadence) amplifies exposure.
- *#12* — Weekly-report benchmark strip. Depends on #10; extends the #2 block into the weekly report's meta area.

**Infra notes for future sessions.**

- `scoring/benchmarks.py` uses package-style imports (`from scoring.price_cache import get_prices`). `score_members.py` still uses sibling-style because it's invoked as a script; new modules in `scoring/` should prefer package-style unless there's a direct-invocation use case.
- Synthetic benchmark fixtures have designed returns baked in; `test_all_benchmark_returns_covers_four_tickers` asserts exact values. If `_record.py` later pulls real NANC/KRUZ/QQQ data, that assertion needs relaxing to sign-only or fixture-specific anchors.
- The leaderboard benchmark block is schema-contract tested, not snapshot-tested — visual tweaks (CSS, cell ordering, ticker additions) that preserve the asserted shape don't break the test.

### 3. [x] Signal-quality filters (ETFs, options, spouse, late filings) — ae1f56a

Closed 2026-04-22 after Tom confirmed the reshuffle direction (ETF-heavy members dropped in rank as expected) and that the four new leaderboard columns (Non-self / Late / ETF drops / Opt drops) render cleanly on `leaderboard.html`.

**Goal.** Stop treating all disclosed transactions as equivalent signals. ETF rebalances and options trades lack information content for retail followers and should drop from scoring; non-self-owner and late-filed trades carry different empirical properties and should be tagged rather than thrown away. Framing: filter when information content is zero; classify when it's different.

**Guiding principle.** Four independent filters over normalized trade records, composed in `scoring/score_members.py` between ticker normalization and alpha attachment. ETF + options → drop from the scoring universe. Non-self owner + late filing → attach a boolean tag per trade; aggregated per-member as shares. Drop counts thread through `aggregate_member_factors` without influencing composite scores — visibility first, weight re-tuning is #4's concern.

**Commit trail.**

- `b22cd02` — filters 1/5: `design/signal-quality-filters.md` + `[~]` flip + design/README.md listing. Locked 10 decisions covering module shape, drop-vs-tag per filter, ETF list contents, late-filing threshold, composition order, factor schema extensions, and test fixture strategy.
- `fbd4b82` — filters 2/5: `scoring/filters.py` with four pure functions (`is_broad_market_etf`, `is_options_trade`, `is_non_self_owner`, `is_late_filing`). `BROAD_MARKET_ETFS = frozenset(14 tickers)` — US broad-market only; NANC / KRUZ intentionally excluded as niche congressional-tracking signals; sector ETFs excluded because they may carry member-informed signal. `tests/test_filters.py` with 45 parametrized cases.
- `8bcb1a6` — filters 3/5: pipeline mutation. `apply_filters` helper in `score_members.py` runs after `normalize_ticker`; drops attach as `m["etf_drops"]` / `m["options_drops"]` on each member dict, tags attach per-trade. `aggregate_member_factors` extended with six output fields (`non_self_count / _share`, `late_count / _share`, `etf_drops`, `options_drops`); `drop_counts` kwarg added with `None` default for backward compatibility. `tests/test_composite_math.py` gains 5 aggregation-side cases — discharges the `scoring/factors.py`-extends-its-tests rule.
- `69dc685` — filters 4/5: leaderboard surface. `display_cols` in `score_members.py` gains four entries (shares + drop counts; per-category counts retained in the factor dict but omitted from xlsx to avoid column bloat). `build_leaderboard.py` renders four new cells per row with `fmt_pct` for shares and integers for drop counts; pre-#3 xlsx files stay backward-compatible via `d.get(...) -> None` → `"—"` fallback. Both 365d and 180d table headers gain columns with tooltip text.
- `ae1f56a` — filters 5/5: `tests/test_leaderboard_filter_columns.py` (4 schema-contract cases) pinning the rendered HTML shape.

Final state: 149 pytest cases green locally. `score_members.py` reports drop totals on each run; `leaderboard.html` carries the four new filter columns alongside the existing ones (transition-period display).

**Scope adjustments from the ROADMAP prose.**

- *Drop-vs-tag per filter.* The ROADMAP described the bundle but didn't prescribe each filter's disposition. Session-3 design call (recorded in `design/signal-quality-filters.md` locked decision 2) committed: ETF + options → drop; non-self + late → tag. Matches "treating all transactions equivalently inflates noise" without discarding the spouse/late signal — tagged trades still score, just with visible categorization.
- *Options encoding verification.* Design note flagged a commit-2 pre-step of scanning `scoring/cache/trades/` for distinct `type` / `typeExtended` values, but the sandbox had no local cache. Safe default shipped: `type.upper() not in {BUY, SELL}` OR `typeExtended` non-empty. If Tom's real run shows `options_drops` implausibly high across the board, the safe default is over-dropping (e.g. `typeExtended` carrying non-options metadata) and `is_options_trade` should tighten — file a follow-on commit at that point.
- *ETF list scope.* Broad-market US only (14 funds). NANC / KRUZ deliberately excluded because a member buying those ETFs signals a bet on Congress's own consensus, which is scoreable information. Sector ETFs (XLE, XLF, XLK, etc.) also excluded because they may carry member-informed signal — e.g. an Energy Committee member buying XLE. Additions are one-line PRs.
- *Per-category counts in xlsx.* Considered adding `spouse_count` / `child_count` / `joint_count` etc. as separate columns. Ruled out — the single `non_self_share` is the actionable surface for followability scoring; per-owner-type breakdown can be added later if research warrants it.
- *Drop counts per window.* Drops are computed globally (across the full 365d fetched window) and appear identically on both 180d and 365d leaderboard tables. Informational, not scoring inputs, so per-window attribution wasn't worth the plumbing for v1.

**Standing follow-ons.** None new from #3. The earlier-filed #10 (price_cache single-ticker bug — surfaced during #2) and #12 (weekly-report strip — deferred from #2 commit 3) remain queued at their slotted positions.

**Infra notes for future sessions.**

- `apply_filters` mutates each member's `trades` list in place — replaces it with the kept subset and attaches drop counts as member-dict keys. Downstream code (alpha attach, factor aggregation) sees only kept trades. When #4 / #5 land, they read filtered trades by default; if a feature needs unfiltered trades, it'll need to re-fetch or plumb an "unfiltered" path through.
- `aggregate_member_factors` gained a `drop_counts` kwarg with `None` default for backward compatibility. Tests that construct synthetic trade lists don't need to pass drop_counts.
- The xlsx column order inserts filter columns between the pre-z-score factor cluster and the z-score cluster. `build_leaderboard.py` reads by column name, not position, so xlsx-writer reordering doesn't break rendering; but analyst readability depends on the current grouping.
- `test_leaderboard_filter_columns.py` is schema-contract, not snapshot. CSS / tooltip tweaks that preserve column labels and cell shapes are safe. Adding a fifth filter column would need the test's per-header `count == 2` assertions extended.

### 4. [x] Post-file alpha recomputation (bundled with #5) — 829c345

Closed 2026-04-23 after Tom confirmed the reshuffle rendered correctly on `leaderboard.html` and the recorded backtest JSON looked sane.

**Goal.** Reframe the composite from trade-date alpha (what the member captured) to post-file alpha (what a follower can capture), per `design/project-framing.md`'s central hazard: the STOCK Act's 45-day disclosure window means the two metrics diverge materially, and follower-facing rankings must be built on the latter. Bundled with #5 because post-file alpha without an out-of-sample loop is a column change, not a viability test.

**Guiding principle.** Re-point the unsuffixed alpha column names (`alpha_*d`, `mean_alpha_20d`, `hit_rate`, `sharpe_alpha`) to carry post-file semantics so `aggregate_member_factors` and `compute_composite` pick them up without a name change; preserve trade-date alpha under `_tradedate`-suffixed diagnostic columns; expose the gap as a first-class `disclosure_drag_20d` column so the follower-cost of disclosure lag reads off the leaderboard directly. Minimizes consumer churn — `build_leaderboard.py` needs no code change at the schema seam because it reads by column name.

**Shared design note.** `design/postfile-alpha-and-backtest.md` covers both #4 and #5 — entry rule (`max(txDate, published) + BDay(2)`, forward-filled), horizons unchanged (5/20/60), weights unchanged (re-tuning deferred since it needs #5's validation surface), full backfill, trade-date retained as diagnostic, single schema cutover rather than two.

**Commit trail (shared with #5).**

- `7e33876` — postfile+backtest 1/6: design note + `[~]` flip on #4 and #5.
- `5cfe2c8` — postfile+backtest 2/6: fixture extension. Every scenario in `synthetic_alpha_scenarios.py` gains `expected_alpha_post_file_approx`; price series extended through `publication_date + BDay(2) + horizon`. Scenario 3's legacy `expected_alpha_trade_date_approx` key preserved as an alias. `backtest_synthetic_member.py` added (24 monthly BUYs on SYNTH, deterministic price ladder +$0.10/bday, SPY flat, pd.bdate_range calendar — used by #5's unit test).
- `3ad35d3` — postfile+backtest 3/6: `compute_trade_alpha_postfile` primitive in `scoring/factors.py` alongside the existing `compute_trade_alpha`; `ENTRY_BUFFER_BDAYS = 2` constant. `tests/test_alpha_math.py` extended with 10 cases — 5 parametrized scenarios on the post-file path + 5 property tests (missing / malformed `published`, missing `txDate`, non-BUY, `max(tx, pub)` anchor). Same-commit test coverage per the `scoring/factors.py` discipline (ROADMAP line 47).
- `22f244f` — postfile+backtest 4/6: composite cutover. `aggregate_member_factors` gains a shared `_alpha_quartet(buys, key)` helper and emits both post-file (primary unsuffixed columns) and trade-date (`_tradedate`-suffixed diagnostics) factor quartets, plus `disclosure_drag_20d = mean_alpha_20d (post-file) - mean_alpha_20d_tradedate`. `attach_alphas` dual-computes — post-file lands at `alpha_{h}d` (primary), trade-date at `alpha_{h}d_tradedate` (diagnostic). `test_composite_math.py` extended with 5 new aggregation tests. Dry-run section of the design note filled in (538 members → 59 qualified → 30% top-30 churn; Fleischmann featured as the adverse-mover exemplar).
- `829c345` — postfile+backtest 5/6: leaderboard xlsx + HTML. `display_cols` in `score_members.py` extended with the five new diagnostic columns. `build_leaderboard.py` renders a new `disclosure_drag_20d` cell (fmt_pct) and header (`Drag 20d`) with a tooltip explaining the sign convention; the existing `Mean α 20d` header gains a tooltip clarifying post-file entry; footer rewritten to reference post-file semantics so a reader understands what the composite measures without opening the code. `test_leaderboard_filter_columns.py` extended with 4 schema-contract cases (drag cell, pre-#4 backward compat, drag header count, footer references post-file).

Final state: 168 pytest cases green locally after commit 5; 179 after #5's commit 6 lands.

**Dry-run result.** 59 qualified members (post-#3 filters + 365d ≥10 trades). 30% top-30 composition churn pre vs. post cutover; median |rank shift| = 3, max = 53; 22/59 members shift > 10 places. Top disclosure-drag members (David Taylor, Valerie Hoyle, Shelley Moore Capito, Katie Britt, Nancy Pelosi) all have negative drag — the expected sign for informed trades losing runup to filing lag. Charles Fleischmann featured as the archetypal adverse rank mover: trade-date α₂₀ = +1.8% → post-file α₂₀ = -0.8%; composite +0.713 (rank 5) → -0.394 (rank 50). Magnitude flagged in the commit 4 message as larger than "a handful of places" but aligned with the bundle's explicit purpose — not re-tuned. Full table in the design note's "Dry run" section.

**Scope adjustments from the ROADMAP prose.**

- *Entry buffer choice.* ROADMAP listed "1, 2, or 3 bdays" as open. Plan locked in 2 bdays and hard-coded it rather than exposing a `--entry-buffer` flag; capitoltrades timestamps lag intra-day and 2bd is what a retail follower reading the morning digest can plausibly execute.
- *Composite weight re-tuning.* ROADMAP listed "reuse existing weights or re-tune" as open. Plan deferred re-tuning — re-tuning needs a validation window, which is what #5 produces; folding it into this bundle would have been a self-reference. Filed as an explicit out-of-scope follow-up in the design note.
- *Trade-date column disposition.* ROADMAP listed three options (secondary column / separate view / hidden). Plan kept trade-date in the xlsx under `_tradedate` suffix and dropped the headline on `leaderboard.html`; surfaced `disclosure_drag_20d` (not the raw trade-date values) as the user-visible diagnostic. Raw `_tradedate` columns remain available for xlsx consumers who want them.
- *Format of the leaderboard xlsx.* Tom flagged xlsx as machine-only during plan. Kept xlsx for this bundle (build_leaderboard.py reads by column name, so rename-via-suffix was backward-compatible without renderer changes) but filed the xlsx → JSON interchange migration as #14.

**Standing follow-ons.** Filed in `a0f09ae` (session wrap):

- *#14* — Leaderboard xlsx → JSON interchange migration. Pure refactor; surfaced in session 3 plan; kept out of the bundle to bound blast radius.
- *Composite weight re-tuning* (not filed as a numbered item yet). Noted in the design note's Out-of-scope section; will file when Tom wants to act on #5's validation surface.
- *NANC price-cache seed* (not filed as a numbered item). The committed CSV cache doesn't include NANC, so the #5 backtest's `alpha_vs_nanc` came out as None; a one-off yfinance fetch to seed `scoring/cache/prices/NANC.csv` would fill it.

**Infra notes for future sessions.**

- The unsuffixed alpha column names (`alpha_5d`, `mean_alpha_20d`, `hit_rate`, `sharpe_alpha`) carry post-file semantics across the entire pipeline now — not just at the composite. Any new consumer that reads them gets follower-facing alpha by default. Trade-date values live under `_tradedate` suffix everywhere.
- `attach_alphas` dual-computes on every BUY. Members with no publication date on a trade get `alpha_{h}d = None` (post-file) but may still have `alpha_{h}d_tradedate` populated — the aggregator's `_alpha_quartet` handles this asymmetrically (each quartet short-circuits on its own key's None-count).
- `_alpha_quartet(buys, key)` is the factor-math primitive. If a new alpha variant lands in the future (e.g. entry-buffer sensitivity), it plugs in by passing a different key and adding a `_buffer3bd` suffix to the factor dict — no structural change needed.
- `ENTRY_BUFFER_BDAYS = 2` is module-scoped in `scoring/factors.py`. Changing it is a one-line edit but requires re-running against the full cache to see the effect — don't ship that without a re-record dry run.

### 5. [x] Walk-forward backtest of the mirror strategy (bundled with #4) — 9851bd0

Closed 2026-04-23 alongside #4 after Tom confirmed the recorded `scoring/output/backtest_20260423.json` looked plausible.

**Goal.** Close the gap between "the scoring pipeline ranks members" and "the strategy of following them produces alpha vs. benchmarks." Without a walk-forward loop, the leaderboard is in-sample — a member who rode a single 2024 move ranks high without that ranking carrying predictive content. Bundled with #4 because post-file alpha and the backtest share fixtures, a schema cutover, and a design note.

**Guiding principle.** Monthly rebalance, fixed top-K = 15, 60-bday horizon exit, include-while-sitting survivorship, three baselines (naive_copy_everyone, NANC, SPY). On-demand only — replay is expensive; correctness comes from the synthetic-member unit test and the committed sample JSON output. The composite at each rebalance date D is computed on trades with `published < D`, so cohort selection is causal.

**Shared design note.** Same as #4 — `design/postfile-alpha-and-backtest.md`.

**Commit trail (shared with #4).** Commits 1/6–5/6 are above in #4's entry. The #5-specific landing is:

- `9851bd0` — postfile+backtest 6/6: `scoring/backtest.py` (new module) — `monthly_rebalance_dates`, `_trades_before` causal filter, `_select_cohort` (re-aggregates factors + composite at every rebalance D), `walk_forward` (main replay loop: iterate rebalances, execute BUYs from the cohort at D+1 close, 60-bday horizon exit), and a `main()` CLI that loads the cached universe via `fetch_all_members` → `apply_filters` → `attach_alphas` → `walk_forward` → writes `scoring/output/backtest_<YYYYMMDD>.json`. 11 unit tests in `tests/test_backtest.py` — 4 calendar / filter helpers + 7 full-replay assertions on the synthetic-member fixture (shape, 24 trades execute, every trade positive-alpha on the rising ladder, strategy ≡ naive with one member, flat benchmarks → zero total return, first trade's entry date pinned to Mar 1 2022, null-path when no qualifiers). Recorded run against the main-worktree cached universe committed as `scoring/output/backtest_20260423.json`.

Final state: 179 pytest cases green locally. Recorded run shape: 12 monthly rebalances, 465 strategy trades, strategy alpha_vs_spy = **-1.56%** per trade, strategy alpha_vs_naive_copy_everyone = +0.52%. Honest "not yet viable" finding — exactly the output the project-framing note expects the platform to be able to produce.

**Scope adjustments from the ROADMAP prose.**

- *Rebalance cadence.* ROADMAP listed "weekly / monthly / event-driven" as open. Plan locked monthly — matches literature convention, comparable against NANC/KRUZ baselines, parameter not structural so reversible.
- *Cohort size rule.* ROADMAP listed "threshold vs. fixed K" as open. Plan locked fixed K = 15 to match the existing `--top-n` default so the backtest evaluates the same follow list `default_follow_*.json` publishes.
- *Compute budget.* Plan locked "on-demand only, not CI-wired." Full-universe replay is too expensive for CI; determinism is covered by the synthetic-member unit test and the committed sample output.
- *Shared fixtures with #6.* ROADMAP bundled fixture sharing with #6 (paper-trading log). Unused in this bundle — #6 doesn't exist yet. When it lands, it can read the same `alpha_*d` / `alpha_*d_tradedate` columns.
- *Causality caveat documented, not fixed.* The composite at D uses alphas pre-attached to trades, which themselves used price data extending past D. A strictly causal backtest would recompute alphas per rebalance with only then-available prices. The forward-looking bias is small (only trades published within the last 60 bdays at D have unresolved horizons) and fixing it doubles the compute. Filed as a deferred follow-up in the module docstring rather than as a blocker.
- *NANC benchmark unavailable.* Committed CSV cache lacks NANC, so `alpha_vs_nanc` came out as None on the recorded run. Filed above as an infra follow-on.

**Standing follow-ons.** None new from #5 beyond #4's (xlsx → JSON migration #14, composite weight re-tuning, NANC seed). The backtest primitive is positioned so #6 (paper-trading log) can reuse `_close_at_or_after`, `_close_n_positions_later`, and `_total_return` without re-implementation.

**Infra notes for future sessions.**

- `walk_forward` takes `members_data` and `price_frames` pre-prepared (normalized tickers, apply_filters run, attach_alphas run). Callers that re-use it in-process should follow `main()`'s preparation order; the synthetic-member test fixture does this in its module-level setup.
- Rebalance calendar uses `pd.bdate_range` semantics (Mon-Fri, no holidays) — same convention as the synthetic fixture. Real yfinance data has holiday gaps; `_close_at_or_after` forward-fills at the entry, so holiday-boundary trades don't skip execution, but exits use positional indexing which is immune to holidays by construction.
- Summary stats: `strategy.total_return` is equal-weight per-trade mean return (not time-weighted cumulative); `SPY.total_return` is close-to-close cumulative over the span. The meaningful comparison is `alpha_vs_spy` (per-trade). Don't compare `total_return` values directly across the two series.
- `naive_copy_everyone` executes the same entry / exit mechanic as the strategy, just without the top-K cohort filter. So `alpha_vs_naive_copy_everyone` isolates the *cohort-selection* contribution — small positive (~+0.5%) on the recorded run suggests the composite ranks non-trivially but not strongly enough to beat SPY after the disclosure-lag confound is removed.
- Recorded backtest output is committed (`scoring/output/backtest_20260423.json`). Future runs write to `scoring/output/backtest_<YYYYMMDD>.json`; the committed sample is a reference snapshot, not a live artifact.

### 6. [x] Auto paper-trading log — baefa44

Closed 2026-04-23 after Tom confirmed the paper-log page renders correctly, the ledger CSV advances cleanly across workflow runs, and the landing-page nav link resolves.

**Goal.** Stand up an append-only, prospective ledger that records what a follower would have done at every pipeline run and tracks the resulting PnL as positions close. The walk-forward backtest from #5 is retrospective; #6 is the same mechanic run forward — starts empty, accumulates a real out-of-sample track record over 6–12 months. Positioned right after the #4/#5 schema cutover so the log starts accumulating on the post-file composite, not the pre-cutover trade-date one.

**Guiding principle.** The live log is the continuation of the recorded backtest, not a parallel implementation — reuse `scoring/backtest.py` primitives (`close_at_or_after`, `close_n_positions_later`, `select_cohort`) rather than duplicating them, promoting helpers from underscore-prefixed to public in commit 2 so the paper log imports from a stable surface. Gross PnL only in v1; transaction costs / tax drag / sizing variants are #7 territory, plug into the existing schema without rewriting it.

**Design note.** `design/paper-log.md` — complexity classified medium → think hard. Locked nine decisions before coding: entry at first close ≥ open_date + 1, fixed 60-bday exit, top-K=15 cohort snapshotted at entry, CSV at `scoring/paper_log/positions.csv`, equal-weight sizing, new `site/paper_log.html` page, retraction keeps the row with `status=retracted`, pipeline wiring between `score_members.py` and `build_site.py`, no historical backfill.

**Commit trail.**

- `3530a14` — paperlog 1/5: design note + `[~]` flip on #6.
- `ae1cf23` — paperlog 2/5: `scoring/paper_log.py` `PaperLog` core (open/close/mark-to-market, `walk_from` loop driver, CSV I/O); empty `scoring/paper_log/positions.csv` with header-only row; 14 unit tests in `tests/test_paper_log.py` pinning each operation against the synthetic-member fixture. Promoted `close_at_or_after`, `close_n_positions_later`, `select_cohort` from underscore-prefixed to public in `scoring/backtest.py` so paper_log imports from a stable surface.
- `ca0cddb` — paperlog 3/5: retraction detection. Extended synthetic fixture with a retracted-trade member; added `_detect_retractions` / `_apply_retraction` to `paper_log.py`; 5 property tests covering row preservation, status flip to `retracted`, `retracted_at` population, and PnL-update short-circuit.
- `008b963` — paperlog 4/5: `build_paper_log.py` HTML render paralleling `build_leaderboard.py` — three sections (open positions with days-held + mark-to-market PnL, recently-closed last 30d, lifetime summary with total return / hit rate / alpha_vs_spy). 18 schema-contract tests in `tests/test_paper_log_page.py`.
- `baefa44` — paperlog 5/5: pipeline wiring + landing-page nav link. `update-leaderboard.yml` gained ledger-advance → auto-commit of the CSV (so state survives across runs) → paper-log page render. `update-report.yml` also rebuilds the page daily so Pages carries the current ledger between monthly leaderboard rebuilds. `build_site.py` nav row gained the "Paper-Trading Log" link alongside "Member Leaderboard". (Intermediate `fad9d55` was the first 5/5 attempt before workflow iteration; `baefa44` is the landing SHA.)

Final state: pytest suite green with paper-log coverage added; landing page carries the paper-log link; the ledger CSV exists as a header-only seed ready to start accumulating positions on the next pipeline run.

**Scope adjustments from the ROADMAP prose.**

- *Entry rule.* ROADMAP listed "next-day open / next-day close / hold until nightly pipeline" as open. Plan locked first close ≥ `open_date + 1 calendar day` — matches #5's D+1 close semantics exactly, invariant under cadence change (#11 nightly doesn't require re-deriving the mechanic), and "the next close a follower reading the morning digest can execute against" is the most defensible retail-follower assumption.
- *Exit rule.* ROADMAP listed "fixed horizon / trailing stop / sell-on-subsequent-disclosure / configurable modes." Plan locked fixed 60 bdays to match #5. Trailing stops and event-driven exits moved to #7-adjacent scope — they need a cost model to evaluate meaningfully.
- *Storage format.* ROADMAP listed "CSV / parquet / sqlite." Plan locked CSV at `scoring/paper_log/positions.csv` for diff-friendliness. Each pipeline run's append shows as a visible commit diff; parquet is binary; sqlite overkill for append-only. Auto-commit of the CSV from the workflow is how state persists across GHA runs.
- *Surface.* ROADMAP listed "weekly report / separate page / Cowork artifact." Plan locked a new `site/paper_log.html` page. Cowork artifact stays gated on #13.
- *Retraction handling.* ROADMAP flagged this as an open question. Plan locked "keep the row, flip status to `retracted`, freeze PnL, stop advancing." Deletion would destroy track-record fidelity — "we acted on this signal at the time" is a real data point even if the underlying disclosure later vanishes.
- *Position sizing.* Equal-weight across signals in v1. Range-weighted sizing folded explicitly into #7's overlay bundle, not re-litigated here.

**Standing follow-ons.** None new from #6. #7 picks up the cost/tax/sizing overlays that this bundle deferred. #13 (live Cowork artifact) will read the same CSV when it lands.

**Infra notes for future sessions.**

- `scoring/paper_log.py::PaperLog.walk_from(start, end, today)` takes `today` as an explicit parameter so tests pass synthetic dates and the CLI passes `date.today()`. Don't monkey-patch `date.today()` in tests.
- `(bioguide, tx_id)` is the identity key for retraction detection. capitoltrades `txId` is stable per disclosure; an edit that re-publishes with a new txId would double-log and surface as a visible duplicate row — preferred over silent corruption.
- The pipeline wiring is order-sensitive: paper-log advance runs *after* `score_members.py` (composite + cohort must be current) and *before* `build_site.py` (page must render with fresh data). `update-leaderboard.yml` and `update-report.yml` both respect this ordering; if a new workflow adds pipeline steps, preserve the sequence.
- CSV auto-commit in the workflow uses a `[skip ci]` message suffix so the commit doesn't retrigger the same workflow. Removing that suffix creates an infinite loop.
- The synthetic-member fixture (`tests/fixtures/backtest_synthetic_member.py`) is shared with #5; extending it with a retracted-trade member in paperlog 3/5 adds coverage for both features. Don't fork the fixture — if a future feature needs a third synthetic member, extend in place.
- `build_paper_log.py`'s render is schema-contract tested, not snapshot-tested. CSS tweaks and cell-ordering changes that preserve the asserted shape don't break the test.
