# Benchmark row (NANC / KRUZ / SPY / QQQ) — design note

ROADMAP #2. Active feature. Flipped to `[~]` alongside this note in the commit that introduces it.

## Scope

**In scope.** A small, additive benchmark reference block that surfaces cumulative total-return numbers for NANC, KRUZ, SPY, and QQQ over the existing 180d and 365d windows. Primary surface is the leaderboard page (`leaderboard.html`, rendered by `build_leaderboard.py`); a compact secondary strip in the weekly report (`generate_report.py`) is in scope only if the wiring is a small add (decided at commit 3 time). Built on the existing `scoring/price_cache.py` seam — no new pricing infrastructure. Tests cover the return primitive and the rendered-row schema contract.

**Out of scope.** A mirror-PnL simulator for the curated follow list. The ROADMAP #2 prose originally said "comparing the curated follow list's mirror PnL against each benchmark," but code reality showed no mirror-PnL exists: the pipeline tracks per-trade alpha vs. SPY, not cumulative follow-list returns. Mirror-PnL simulation is ~30–50% of #5 (walk-forward backtest) done early, with material scope overlap. Deferred to #5, where it belongs per the bundled-with-#4 sequencing. Session 2 (2026-04-22) chose option (A) over option (B) in the design call before coding started — do not re-litigate.

Also out: net-of-fees adjustment on benchmark returns (#7's job); "since-inception" columns for the follow list (complexity without v1 value); per-ETF expense-ratio handling (gross-of-fees with footnote matches the follow-list's gross reporting); intraday or within-day benchmarks (daily closes only); alternative benchmarks beyond the four named in the framing note (IWM, sector ETFs, etc.).

## Guiding principle

A reference row, not a comparison row. Until #4/#5 deliver a follow-list mirror-PnL number, the leaderboard benchmark block stands on its own: "Here is what each of the four reference instruments returned over 180d / 365d. When the reader scans the member rankings above, they now have anchors." When #5 lands, the benchmark block becomes the direct plot-against surface for the mirror-PnL line; no rewiring expected because the numbers are the same. That's what "sequenced first" in the ROADMAP buys — a stable reference line before #3 shrinks the universe and #4 reshuffles rankings.

## Locked decisions

1. **Option (A), not (B).** Reference row of benchmark cumulative returns; no follow-list mirror-PnL simulator in #2. Rationale: mirror-PnL belongs with #5; #2's "small, additive" framing in the ROADMAP matches (A). Session-2 design call.
2. **Price source: yfinance via `scoring/price_cache.py`.** Same seam every other price read uses. `auto_adjust=True` is already on (split-and-dividend-adjusted closes), so total-return math is `last_close / first_close - 1` with no extra dividend handling.
3. **Windows: reuse 180d and 365d.** Matches the existing leaderboard windows exactly. No "since-inception" column in v1.
4. **Placement: leaderboard page primary.** `build_leaderboard.py` gets a benchmark block above the 365d Leaderboard table, styled as a card to match the existing weights-card. The weekly-report strip (`generate_report.py`) is a candidate secondary surface; it lands in this feature only if the analysis-skeleton / fill-pipeline wiring is trivially small. If not, weekly-report follow-on lands separately. Decided at commit 3.
5. **Gross of fees with a one-line footnote.** Leaderboard footer gets: "Benchmark returns are gross of expense ratios and slippage." Follow list is also reported gross, so the comparison is consistent. Net-of-fees is #7's job.
6. **Total-return basis, close-to-close.** First close on-or-after `window_start`, last close on-or-before `window_end`. Tolerates weekends / holidays at window boundaries without special casing. Matches the existing alpha-math entry convention (`_next_close_at_or_after` in `scoring/factors.py`).
7. **New module: `scoring/benchmarks.py`.** Not folded into `scoring/factors.py` — it's not a factor and doesn't belong next to alpha math. A separate module makes wiring into both surfaces straightforward. The `scoring/factors.py`-specific "extend `test_alpha_math.py` or `test_composite_math.py` in the same commit" rule therefore does not apply.
8. **Missing-data convention: return `None`, do not raise.** Matches `price_cache.get_prices()`'s existing convention of dropping tickers with no data. The renderer displays `"—"` for `None`, consistent with `fmt_pct` in `build_leaderboard.py`.
9. **Fixture strategy.** Extend `tests/fixtures/prices/` with small CSVs for NANC, KRUZ, QQQ (SPY already exists). ~2 years of daily closes each — same span as the existing fixtures. Recorded via `tests/fixtures/_record.py`; same fixture serves #5 when it needs these series.

## Sketches

**`scoring/benchmarks.py`** (directional, not line-exact):

```python
from datetime import date
from price_cache import get_prices


BENCHMARK_TICKERS = ("NANC", "KRUZ", "SPY", "QQQ")


def benchmark_cumulative_return(
    ticker: str,
    window_start: date,
    window_end: date,
    price_frame=None,
) -> float | None:
    """First-close-to-last-close total return over [window_start, window_end].
    Returns None when no cached data covers the window."""
    if price_frame is None:
        frames = get_prices([ticker], window_start, window_end)
        price_frame = frames.get(ticker)
    if price_frame is None or price_frame.empty:
        return None
    closes = price_frame["close"].dropna()
    if closes.empty:
        return None
    return float(closes.iloc[-1] / closes.iloc[0] - 1.0)


def all_benchmark_returns(
    window_start: date,
    window_end: date,
) -> dict[str, float | None]:
    frames = get_prices(list(BENCHMARK_TICKERS), window_start, window_end)
    return {
        t: benchmark_cumulative_return(t, window_start, window_end, frames.get(t))
        for t in BENCHMARK_TICKERS
    }
```

**`build_leaderboard.py`** gets a `build_benchmark_block(returns_long, returns_short)` helper and a `{benchmark_block}` placeholder in `PAGE_TEMPLATE` above the 365d section. Styling matches the existing `weights-card`. The two window-dicts come from two `all_benchmark_returns` calls inside `main()`.

**Weekly-report strip** (commit 3 conditional): a compact four-cell `.benchmark-strip` near the meta line in `generate_report.py`'s `build_html`. Numbers flow through the analysis-skeleton / fill pipeline so the HTML wrap step stays render-only. Exact seam confirmed at commit 3 after re-reading `compute_analysis.py` and `build_skeleton.py`.

## Test plan

Two new test files plus a fixture extension.

| File | Cases (rough) | Coverage |
|---|---|---|
| `tests/test_benchmarks.py` | ~8 | Parametrized over the four tickers and both windows. Edge cases: `window_start` falls on a weekend (entry = next trading day); `window_end` past the latest cached close (use last available); ticker missing from cache (returns `None`, no exception); window entirely before any cached data (returns `None`); single-close window (returns `0.0`); `price_frame=` kwarg injection (no yfinance call). |
| `tests/test_leaderboard_benchmark_block.py` | ~3 | Schema-contract test over rendered `leaderboard.html`. Asserts: block exists; contains all four ticker labels; contains numeric-% shape strings in the `fmt_pct` format (e.g. `"+12.3%"` or `"—"` for missing); gross-of-fees footnote present. |

`tests/fixtures/prices/` gets `NANC.csv`, `KRUZ.csv`, `QQQ.csv` — each ~2 years × ~250 trading days. Recorded via `_record.py`.

**"Ship tests with the feature" discharge.** Primitive + tests ship together in commit 2. Schema-contract test ships with the leaderboard wiring in commit 4 (not 3) because the wiring itself is a visual-render change that benefits from human spot-check before the test is locked in.

## Non-goals

- Follow-list mirror PnL — deferred to #5.
- Net-of-fees / expense-ratio adjustments — deferred to #7.
- "Since-inception" columns for the follow list.
- Intraday benchmarks.
- Benchmarks beyond the four named in `design/project-framing.md`.
- Changes to `compute_analysis.py` or `scoring/factors.py` (benchmarks stand alone).
- A standalone benchmark page or route — the existing surfaces are enough.

## Responsibility table

| Concern | Owner | Notes |
|---|---|---|
| Pulling NANC/KRUZ/QQQ prices into the cache | Script (`scoring/price_cache.py`, unchanged) | New tickers flow through existing `get_prices` |
| Computing cumulative total return per ticker over a window | Script (`scoring/benchmarks.py`, new) | Pure function over a price frame; no yfinance call inside |
| Leaderboard benchmark block render | Script (`build_leaderboard.py`, extended) | `build_benchmark_block` + `{benchmark_block}` placeholder |
| Weekly-report benchmark strip render (if in scope at commit 3) | Script (`generate_report.py` + upstream fill step, extended) | Populated by the fill step; HTML wrap stays render-only |
| Fee-gross footnote copy | Static string in `build_leaderboard.py` footer | One-line note; no agent judgment |
| Deciding which benchmarks + windows to use | Agent (this design note, session-2 call) | Locked: four named benchmarks, 180d + 365d |
| Fixture recording for NANC/KRUZ/QQQ | Script (`tests/fixtures/_record.py`, unchanged) | Same one-shot recorder as the rest of the suite |
| `[~] → [x]` flip on ROADMAP #2 | User | After first rendered leaderboard lands and numbers spot-check cleanly against Yahoo Finance / NANC's own site |

## Commit plan

1. **This commit.** `design/benchmark-row.md` + `design/README.md` listing update + ROADMAP `[ ] → [~]` flip on #2 + session-summary refresh. Bundles the uncommitted doc edits from earlier in session 2 — ROADMAP reorder/renumber and `design/pytest-ci-suite.md` cross-ref migrations — so those don't sit in the worktree.
2. **Benchmark primitive + tests.** `scoring/benchmarks.py` with `benchmark_cumulative_return` and `all_benchmark_returns`. `tests/test_benchmarks.py` parametrized over the four tickers × two windows + edge cases. Fixture extension: `tests/fixtures/prices/{NANC,KRUZ,QQQ}.csv` via `_record.py`. Discharges "ship tests with the feature" for the new primitive.
3. **Wire into leaderboard (+ weekly-report strip if trivial).** `build_leaderboard.py` gets `build_benchmark_block` + the template placeholder + the fee footnote. If analysis-skeleton / fill-pipeline wiring for the weekly-report strip is a small add, include it in this commit; otherwise file a follow-on item and land this commit as leaderboard-only. Local render + visual spot-check on the leaderboard page before commit.
4. **Schema-contract test.** `tests/test_leaderboard_benchmark_block.py` asserting the block renders with the four ticker labels and the expected numeric shape. Leaves ROADMAP #2 in `[~]`; user pushes, runs manual QA (checkpoint A from session 2), and signs off when numbers eyeball clean against Yahoo / NANC's own site.

Each commit stands alone — mid-feature handoff picks up from this note plus the last SHA without re-litigating scope.
