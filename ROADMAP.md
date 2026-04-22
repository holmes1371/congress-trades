# Congress Trades — QoL Roadmap

Authoritative backlog for quality-of-life improvements to the congress-trades pipeline (repo: `holmes1371/congress-trades`, live site: `holmes1371.github.io/congress-trades`). Edit in place; commit changes alongside code.

Always load the karpathy-guidelines skill before starting anything here.

Read `design/project-framing.md` at the start of every session before proposing features or strategy claims. It's the standing frame — what this project is (a research platform, not a trading product), the central hazard (STOCK Act disclosure lag), the right benchmarks (NANC/KRUZ/SPY/QQQ), and what this project is not — that keeps backlog items honest. It is not re-litigated per session.

Closed `[x]` items are archived in `COMPLETED.md` with their full post-mortem prose. One-line stubs remain below at their current numbers. When items reprioritize, blocks renumber together and in-repo cross-references update in the same commit; past references in commit messages resolve via the renumber commit in git history.

## Last session summary

This section holds **exactly one block** — the current/most-recent session — and it MUST be short. The next agent needs a cold pickup, not a recap.

Strict rules for writing it:

1. **≤5 bullets, ≤1 sentence each where possible.** Trim ruthlessly. If a bullet needs a paragraph, the real content belongs in a design note or `COMPLETED.md`; link it.
2. **Only what is open, in-flight, or just-filed.** Do NOT restate design decisions, rationale, or commit-by-commit walkthroughs for closed items — those live in `COMPLETED.md`; the next agent can read them if needed.
3. **No standing guidance here.** Session rituals, soft-delete convention, commit discipline — all of that lives in "For future agents" below. Do not duplicate.
4. **No cross-session carry-overs.** If something is still broken session-to-session, file it as a numbered ROADMAP item instead of repeating it here.
5. **Replace in place.** Do not append a new block and archive the old one below.

**2026-04-22 (session 2)**

- #2 closed: `[~]` → `[x]` at `6a5b0eb` after Tom confirmed the rendered leaderboard carried the benchmark block + the four values spot-checked against Yahoo. Full post-mortem + commit trail moved to `COMPLETED.md #2`; one-line stub left at ROADMAP #2 per convention.
- Side edit this commit: `COMPLETED.md` preface was still carrying the pre-session-2 "original numbers are stable — never renumber" line, which became stale when session 2 adopted priority-order renumbering. Preface text now matches the current convention.
- Next: #3 (signal-quality filters — ETFs, options, spouse, late filings). Plan-and-wait on the design note before coding; the `[~]` flip goes in #3's first artifact per convention. Standing follow-ons #10 (price_cache bug) and #12 (weekly-report strip) remain queued at their slotted positions.

## For future agents

Read this file at the start of any session where Tom mentions "congress-trades", "the QoL list", "the roadmap", or asks about the next feature. The prioritization below is settled — do not re-debate it without prompting. Work items in order unless Tom explicitly says otherwise.

Session discipline:

- Invoke the `karpathy-guidelines` skill via the Skill tool at the start of every session that touches code. Reading `reference/guidelines.md` directly does not count — the skill-load step is what anchors the discipline for the rest of the session.
- git commits need the `-c user.name=... -c user.email=...` flags since there's no default identity in this workspace.
- Before starting a non-trivial feature, write a short design note to `design/{feature-name}.md` capturing the scope, the decisions already made, and the test fixtures needed. A fresh session should be able to pick up mid-feature from that note plus the last commit, without re-litigating choices.
- Commit at every natural boundary, not just at feature completion. Half-finished work behind a clear commit message is recoverable; a dirty worktree is not.
- **Flip `[ ]` → `[~]` as soon as Tom approves the plan for a backlog item — before the design note, before any code.** The status flag is there to tell the next agent what's actually in flight; flipping only at session end means a mid-session interruption leaves the item falsely marked "not started" even though a design note and half the commits exist. Record the flip in whichever commit introduces the first artifact for the item (usually the design note); if the plan is approved but no commit has landed yet, include the flip alongside the first real change so it doesn't need its own throwaway commit.
- End each session by updating this file — mark in-progress items, note any deviations or follow-ups — and commit the update. **Do not flip an item to `[x]` without explicit user signoff.** When the final code commit for an item lands, leave the item in `[~]`, record the SHA, and summarize what's pending manual verification. Tom pushes, tests manually, and either confirms the close (then the next session flips it to `[x]` with the SHA preserved) or returns feedback to address. Closing on your own reads as premature.
- **Update the "Last session summary" block between each commit during a multi-commit feature, not just at session end.** The block should always reflect what *just* landed and what's next, so a mid-feature handoff — mid-session or across agents — has a clean pickup point. The block is single-slot: replace in place, do not append. Older sessions' context lives in commit messages, `COMPLETED.md`, and `design/*.md`.
- **Closed items live in `COMPLETED.md`, not here.** When Tom signs off a `[~]` item, the next session moves its full prose into `COMPLETED.md` and leaves a one-line stub at its current item number in this file. **Numbers follow priority order, not historical identity.** When the backlog is reprioritized, physically move the blocks *and* renumber so top-to-bottom matches 1, 2, 3, …; update all in-repo cross-references (this file, `design/*.md`, `COMPLETED.md`) in the same commit; record the old→new map in the session summary and commit message so past references remain resolvable via git history. When touching territory that overlaps a completed item, read its full entry in `COMPLETED.md` before re-deriving decisions.
- Honor the standing order: deterministic work lives in Python scripts; the agent does only judgment and interpretation. If a feature tempts you to move mechanical work into agent-handled text, push back.
- Tests live in `tests/` and run on every push via `.github/workflows/tests.yml`. Do not mark a feature done with tests failing; check the commit's test run before calling a feature closed.
- **Ship tests with the feature, not after.** When a commit adds a new primitive (parser, adapter, pure-math function, schema transform, cache seam), the same commit adds pytest coverage for it. Assembly-level code that ROADMAP #2–#13 is expected to rewrite is deliberately skipped per `design/pytest-ci-suite.md`'s "Guiding principle" — if you skip, say so in the commit message so a reviewer sees the trade-off, not a miss.
- Any change to `scoring/factors.py` must extend `tests/test_alpha_math.py` or `tests/test_composite_math.py` in the same commit. Other modules with existing test coverage extend their fixtures in step with the change, not after.

Status legend:

- `[ ]` not started
- `[~]` in progress — include a note with what is done and what remains
- `[x]` done — include the commit SHA
- `[-]` descoped / on hold — full prose preserved in "Descoped / on hold" at the bottom for possible future revival

## Backlog (priority order)

### 1. [x] Pytest suite + CI workflow — 3022a38 — see COMPLETED.md

### 2. [x] NANC / KRUZ / SPY / QQQ benchmark row — 6a5b0eb — see COMPLETED.md

### 3. [ ] Signal-quality filters (ETFs, options, spouse, late filings)

A non-trivial fraction of disclosed transactions are ETF rebalances in managed accounts, options rolls, corporate actions, and spouse-directed trades. Treating all transactions equivalently inflates noise in both the scoring and signal-generation layers. Sequenced before #4 so the post-file alpha reshuffle runs on a filter-clean universe rather than a polluted one. Bundled because they share the same fixtures and the same place in the pipeline:

- Exclude broad-market ETFs (SPY, VOO, QQQ, IVV, etc.) from scoring and signal generation. A member buying SPY is not an informed signal.
- Separate options trades into their own stream rather than mixing them into the mirror universe. Their risk profile differs from spot equities and most retail followers cannot copy them.
- Tag spouse-filed vs. member-filed transactions as separate signals. The empirical evidence treats these differently.
- Tag late filings (filed at day 40+). Persistent late-filing is itself a signal-quality variable worth surfacing rather than swallowing.

Design-note questions:

- Filter module shape. Is this one `filters.py` with four functions, or four separate hooks in the existing pipeline.
- Drop vs. flag-and-keep. Whether filtered-out transactions are removed or retained with a column marking the filter that fired.
- Source of truth for the broad-market ETF exclusion list. Hardcoded in the repo vs. pulled from a provider.
- Impact on existing leaderboard windows. Filters will shrink transaction counts; decide whether to show the filter-aware and filter-unaware counts side by side for a transition period.

### 4. [ ] Post-file alpha recomputation (bundled with #5)

Trade-date alpha is what the member captured; post-file alpha is what a follower can capture. The STOCK Act's 45-day disclosure window means the two diverge materially, and `design/project-framing.md` makes the case that follower-facing rankings must be built on post-file alpha. Rework `scoring/factors.py` so the composite is built on post-file alpha — `alpha_postfile_5d/20d/60d` measured from the later of publication date or trade date + a small entry buffer. Trade-date alpha drops from co-headline to a diagnostic column: still emitted so a member's capture can be characterized, not used to rank follow candidates. Bundle the walk-forward backtest (#5) into the same design note — post-file alpha without an out-of-sample loop is a column change, not a viability test — and plan a single schema cutover rather than two. Sequenced after #2 (stable benchmark reference in place before the reshuffle) and #3 (filter-clean universe before the composite is re-fit).

Design-note questions to resolve before coding:

- Entry buffer size. "+2 business days" is a reasonable starting point; worth confirming whether 1 or 3 is more defensible given how often capitoltrades files late in the trading day.
- Composite weights. Reuse the existing 5/20/60-day weights on the post-file side, or re-tune against a validation window.
- Backfill policy. Recompute history end-to-end, or only apply post-file alpha going forward and note the cutover in the leaderboard.
- Test fixtures. Need a trimmed price-cache sample plus a synthetic member with a known trade/publication date gap so the alpha math is unit-testable without live network. Same fixture set should cover the #5 walk-forward loop to avoid duplication.
- Expected reshuffle magnitude. Worth an exploratory dry run on a single member before committing to the schema change, so the composite change is sized honestly. Post-#3 the member universe will already have shrunk; do the dry run against the filtered dataset, not the raw one.
- Trade-date column deprecation. Whether trade-date alpha stays in the leaderboard UI as a secondary column, moves to a separate diagnostic view, or gets hidden by default.

### 5. [ ] Walk-forward backtest of the mirror strategy

The scoring pipeline ranks members; it does not backtest the strategy of *following* them. Those are different questions. A walk-forward loop closes the gap: at each historical date D, using only data filed before D, pick the top-K members by the composite, simulate buying every disclosed purchase from that cohort on D+1 at close, hold under a rule-based exit (same menu as the paper-trading log), track PnL, and compare against the benchmarks from #2 plus a naive "copy everyone" baseline. Without this loop the leaderboard is in-sample — a member who rode a large 2024 move ranks high without that ranking carrying predictive content. Bundled with #4: same design note, same schema cutover, same fixture set.

Design-note questions:

- Rebalance cadence. Weekly, monthly, or event-driven.
- Cohort size rule. Composite-score threshold vs. fixed K.
- Survivorship. Include members who have since left Congress during the period they were sitting.
- Compute budget. Full replay is expensive; decide whether the backtest runs in CI or only on demand.
- Shared fixtures with #6. Both the log and the backtest consume the same post-file alpha columns from #4; duplication is wasteful.

### 6. [ ] Auto paper-trading log

The only way to get an honest, out-of-sample read on the platform's viability is a paper-trading log that starts the moment any of this is considered live. Every time a signal fires, log the entry price, a rule-based exit, and track the live PnL. After 6–12 months the log becomes the user's own track record rather than a historical backtest. Positioned right after the #4/#5 schema cutover so the log starts accumulating as soon as the post-file composite stabilizes — there is no cost to starting it early and real cost to starting it late. Runs in parallel with #7 onward rather than blocking them.

Design-note questions:

- Entry rule. Next-day open, next-day close, or hold-out until the nightly pipeline runs.
- Exit rule. Fixed horizon (N days), trailing stop, sell-on-subsequent-disclosure, or all three as configurable modes.
- Storage format. CSV in-repo is simplest; parquet or sqlite become worthwhile once the log is large.
- Surface. Weekly report, separate page, or the live Cowork artifact in #13 — overlaps decided in the #13 design note rather than here.
- What happens to entries when the signal source is later retracted or corrected.

### 7. [ ] Transaction-cost, tax-drag, and position-sizing overlays

Signals without cost models overstate follower returns. Bundled because all three live in the same PnL-accounting layer and share fixtures:

- Slippage estimate per ticker: average spread × configurable fill factor (1× large cap, 2–3× small cap).
- After-tax view at short-term federal + state rates, toggleable, since congressional trades skew short-horizon and the headline alpha looks materially different on an after-tax basis.
- Position-sizing modes — equal-weight across signals versus range-weighted using the disclosed transaction range as a weak conviction proxy — selected explicitly rather than left implicit.

Design-note questions:

- Slippage data source. yfinance provides limited spread coverage; may need a cheaper proxy (bid-ask estimate from daily bars).
- Scope of the tax toggle. Paper-trading log (#6) only, walk-forward backtest (#5) only, or both.
- Default sizing mode for the curated follow list.
- Whether the state rate is user-configurable or hardcoded to a sensible default.

### 8. [ ] Committee-relevant consensus signals

Persistent congressional alpha in the academic literature tends to cluster in two places: trades clustered near relevant committee hearings, and trades where multiple members take the same side within a tight window. The project already has committee-mode analysis; the next step is to fuse it with consensus detection. Compute a composite signal where ≥2 members of a committee with jurisdiction over the ticker's sector trade the same direction within 30 days, and surface those at the top of the weekly report in their own section, separate from aggregate consensus.

Design-note questions:

- Committee-to-sector jurisdiction mapping. Curated table in the repo vs. pulled from an external source.
- Window size. 30 days is a starting point; 14 and 60 are defensible alternatives worth noting.
- Member threshold. 2 minimum, or higher for conviction.
- Interaction with signal-quality filters (#3). Spouse-filed and options-filed trades should likely be excluded from the consensus count.

### 9. [ ] Hearings correlation

Extends #8. The House Clerk and Senate publish hearing schedules. Correlating disclosed trade dates with hearings the member attended is high-signal and mechanically achievable from public data: a member buying a defense contractor the week before an HASC briefing is a different signal than the same purchase three months later. Adds a "hearings-proximal trade" tag to the signal layer and threads it into the composite where committee jurisdiction matches.

Design-note questions:

- Source selection for hearing schedules. House Clerk feed, Senate committee pages, or a dedicated scraper target.
- Attendance data. Public for most hearings, unreliable for classified sessions; confirm what is actually obtainable before committing to the feature surface.
- Proximity window. 7, 14, or 30 days.
- Failure mode when a member sits on multiple committees. Is the tag "any relevant hearing within window," or restricted to the committee whose jurisdiction matches the ticker.

### 10. [ ] Fix `price_cache.py` single-ticker fallback on empty yfinance response

When `scoring/price_cache.py::_bulk_download` is called with a single ticker and yfinance returns a frame with no `Close` / `Volume` columns (empty response, rate-limit fallback, delisted or unknown ticker, etc.), the single-ticker branch builds a `pd.DataFrame` from scalar `pd.NA` values (around line 128) and crashes with `ValueError: If using all scalar values, you must pass an index`. Surfaced during #2's local-render attempt in the sandbox: `get_prices([ticker], ...)` calls from `scoring/benchmarks.py::benchmark_cumulative_return`'s fallback path tripped the bug. Effect: the pipeline aborts rather than gracefully dropping the missing ticker; the nightly cadence in #11 amplifies exposure and the weekly-report strip in #12 is a new caller. Fix: detect the empty-column shape upstream of the DataFrame construction and return an empty dict for that ticker, matching the module's existing dropped-ticker convention. Ship a regression test alongside: a `responses`-mocked `_bulk_download` call returning an empty-column frame, asserting `get_prices` returns `{}` without raising.

Design-note questions:

- Whether the multi-ticker branch (lines 139-154) needs the same guard. It has a `"Close" in sub_raw.columns` check but then still builds a DataFrame with `pd.NA` for the Volume column — same hazard if Close exists but Volume is absent.
- Whether to persist a "no data" marker per ticker to avoid repeated yfinance hits on the same missing symbol. Favor not persisting — simple, and a missing ticker is rare enough that retry-on-every-query is cheap.
- Reproducibility of yfinance's exact empty-column shape in a regression test. May need to capture a live example once and codify the shape in a fixture.

### 11. [ ] Daily / on-disclosure cadence

Weekly cadence gives up several days of post-disclosure drift that the research suggests is capturable. A nightly run with a short "new signals since last run" digest tightens the loop. The existing no-changes short-circuit makes this cheap to operate. Paired with the live artifact in #13, this changes the platform from a weekly snapshot into something closer to an event-driven stream.

Design-note questions:

- Delivery channel. Email, Slack, or nothing beyond the live artifact.
- Alert-fatigue handling. Suppress the digest when nothing material has filed, or always send with an explicit "no new signals" line.
- Whether the weekly report persists as a digest-of-digests or is retired once the nightly stream is stable.
- CI vs. local run. The nightly cadence implies GitHub Actions on a schedule; cost and rate-limit implications for capitoltrades need sizing.

### 12. [ ] Weekly-report benchmark strip

Extend #2's benchmark reference block to the weekly report (`generate_report.py`) as a compact four-cell strip near the top meta area, so NANC/KRUZ/SPY/QQQ cumulative returns are visible every week rather than only on the monthly leaderboard rebuild. Deferred from #2's commit 3 because the wiring path — `compute_analysis.py` → `build_skeleton.py` → `fill_skeleton.py` → `generate_report.py` — is non-trivial, and the leaderboard surface already delivers the core value-add question. The strip adds cadence: weekly visibility for a reader who only looks at the latest report, not the monthly ranking page.

Design-note questions:

- Compute seam. Bake benchmarks into `analysis_skeleton.json` at `build_skeleton.py` time (paper trail, matches the fill-pipeline convention), or compute at `generate_report.py` render time (simpler, no skeleton plumbing).
- Window alignment. Match the leaderboard's 180d/365d anchors for continuity with #2, or use the weekly report's trade-window. Framing favors 180d/365d.
- Placement. Compact four-cell strip in the meta area directly below the title, or a full card below the Executive Summary section.
- Fallback when benchmark data is unavailable in a given CI run (empty price cache, yfinance unreachable). Show dashes, omit the strip, or fail-closed?
- Dependency on #10. The strip adds a new caller of `scoring.benchmarks.all_benchmark_returns`, which fans into single-ticker `get_prices` calls in fallback paths. #10 should land first so the strip-generation path isn't a crash vector.

### 13. [ ] Live Cowork artifact

An artifact (in the Cowork sense) that re-queries on open and shows open paper-trade positions, days held, and current PnL against the benchmarks from #2. More actionable than a static HTML report, and a natural home for the paper-trading log from #6. Placed last in priority order because it sits on top of #6 (log), #2 (benchmarks), and ideally #11 (cadence); building it earlier means re-wiring it as each prerequisite lands.

Design-note questions:

- Connector shape. Does the artifact query capitoltrades directly or read a committed JSON snapshot from the repo.
- State. In-memory only (Cowork artifact constraint) or persisted via a backing file in the mount.
- Default view on open. Leaderboard vs. open positions vs. benchmark row.
- Refresh rate. Every open, or cached for N minutes.

## Descoped / on hold

Items parked here aren't dead — they're off the active queue but preserved in case priorities shift. Revive by moving the full prose back under "Backlog" at the next available priority slot and flipping `[-]` → `[ ]`.

_(none yet)_
