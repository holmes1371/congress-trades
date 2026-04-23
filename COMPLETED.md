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
