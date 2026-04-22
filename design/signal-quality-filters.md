# Signal-quality filters — design note

ROADMAP #3. Active feature. Flipped to `[~]` alongside this note in the commit that introduces it.

## Scope

**In scope.** Four independent filters over normalized trade records, composed in `scoring/score_members.py` between ticker normalization and alpha attachment:

1. **Broad-market ETF filter** — drops trades on a hardcoded short list of broad-market ETFs (SPY, VOO, IVV, VTI, VEA, VXUS, VWO, AGG, BND, QQQ, IWM, DIA, SCHB, ITOT) from the scoring and signal-generation universe. A member buying SPY is not an informed signal.
2. **Options filter** — drops trades that aren't plain-stock equity buys/sells from the mirror universe. Options carry a different risk profile and retail followers can't reliably copy them.
3. **Non-self owner tag** — attaches a `non_self_filing` boolean to every trade where `owner` is anything other than `"self"`. Does NOT drop the trade; the empirical signal isn't thrown away, just marked. Aggregated per-member as `non_self_share`.
4. **Late filing tag** — attaches a `late_filing` boolean where `filedAfterDays >= 40` (STOCK Act deadline is 45). Does NOT drop; aggregated as `late_share`.

Artifacts: `scoring/filters.py` as a new module with four pure functions; `scoring/score_members.py` wires them in; `scoring/factors.py::aggregate_member_factors` emits new share / drop-count columns; `build_leaderboard.py` renders the new columns. Tests: `tests/test_filters.py` for the primitives; `tests/test_composite_math.py` extended for the new factor columns (discharges the `scoring/factors.py`-extends-its-tests rule); a new schema-contract test pins the rendered leaderboard columns.

**Out of scope.** Backfill of historical trades — filters apply going forward and recompute on the next `score_members.py` run. Dropping spouse / late trades (tagging preserves the signal with different weighting downstream). Corporate actions, splits, dividends (not in the four filters). `fetch_trades.py` integration — filters are a scoring concern. Retiring the existing `normalize_ticker` foreign-ticker filter. Filter-awareness in the #2 benchmark returns (benchmarks pull their own prices). Re-tuning composite weights around tagged trades — that's #4's job.

## Guiding principle

Filter when information content is zero (broad-market ETFs); classify when it's different (options, non-self, late). The ROADMAP prose is explicit that "treating all transactions equivalently inflates noise." The fix isn't to throw everything away — it's to make the categorization visible so downstream scoring (and #4's post-file alpha re-fit) can weight them appropriately.

## Locked decisions

1. **Single `scoring/filters.py` module with four pure functions.** `is_broad_market_etf(ticker)`, `is_options_trade(trade)`, `is_non_self_owner(owner)`, `is_late_filing(filed_after_days)`. Pure so they're trivially testable; composition lives in `score_members.py`.
2. **Drop-vs-tag per filter.** ETF → drop; options → drop; non-self owner → tag; late → tag. Ordered so drops fire before tags (no sense tagging a dropped trade). ROADMAP prose backs each choice.
3. **ETF list hardcoded.** `BROAD_MARKET_ETFS` is a module-level `frozenset` of 14 broad-market funds (US only, no sector ETFs). NANC and KRUZ are niche congressional-tracking ETFs — deliberately NOT in the list; a member buying them remains a scoreable signal. Additions are one-line PRs; a dynamic provider adds a dep without clear benefit for a short stable list.
4. **Late-filing threshold: 40 days.** Matches the ROADMAP prose. STOCK Act allows up to 45; 40+ captures "approaching the deadline" without tagging every 41-day filing as late.
5. **Owner detection is self-vs-not-self.** `is_non_self_owner(owner)` returns `True` for any value other than `"self"` (case-insensitive). Observed values in the capitoltrades fixture include `"spouse"` and `"child"`; production data likely also has `"dependent"` and `"joint"`. All non-self categories aggregate to a single `non_self_share` — per-owner-type columns would be surface bloat without adding signal.
6. **Options detection: safe default + commit-2 verification.** The committed fixture has `typeExtended: null` on all 10 stock records. Options likely carry `typeExtended` non-empty (e.g. `"call_purchase"`, `"put_sale"`) and/or `type` outside `{BUY, SELL}`. Safe default for v1: `is_options_trade(trade) = type.upper() not in {"BUY", "SELL"} or bool(typeExtended)`. Commit-2 prep step: scan any local `scoring/cache/trades/` for distinct `type` / `typeExtended` values before pipeline wiring; tighten the predicate if real data shows the safe default over-drops (e.g. `typeExtended` carrying stock-dividend or split metadata).
7. **Composition order in `score_members.py`.** (i) `normalize_ticker` (existing); (ii) drop ETFs; (iii) drop options; (iv) tag non-self; (v) tag late; (vi) alpha attach + factor aggregation. Drops operate on the trade list (filter-out); tags attach booleans to trade dicts in place.
8. **Factor schema extensions.** `aggregate_member_factors` output gains: `non_self_count`, `non_self_share`, `late_count`, `late_share`, `etf_drops`, `options_drops`. Shares are computed over the post-filter trade set (denominator = kept trades). Composite weights are NOT changed in #3 — visibility first, weight re-tuning is #4's concern.
9. **Transition-period display.** Leaderboard xlsx keeps existing columns (`trade_count`, `buy_count`, `sell_count`, `composite`, the alpha / hit / sharpe / lag / liq columns) and adds the new filter columns at the end. `build_leaderboard.py` renders both sets. After Tom confirms the reshuffle directionality, a follow-up PR can decide whether to retire any of the old columns — explicitly not a #3 concern.
10. **Test-fixture strategy.** Filter-primitive tests use small inline trade / owner / ticker literals (deterministic, no fixture file). Factor-aggregation tests in `test_composite_math.py` build synthetic member data inline — same pattern as the existing factor tests.

## Sketches

**`scoring/filters.py`** (directional, not line-exact):

```python
"""filters.py — signal-quality filters over normalized trade records."""

from __future__ import annotations


BROAD_MARKET_ETFS = frozenset({
    "SPY", "VOO", "IVV", "VTI", "VEA", "VXUS", "VWO",
    "AGG", "BND", "QQQ", "IWM", "DIA", "SCHB", "ITOT",
})


def is_broad_market_etf(ticker: str | None) -> bool:
    if not ticker:
        return False
    return ticker.upper() in BROAD_MARKET_ETFS


def is_options_trade(trade: dict) -> bool:
    """Safe default: non-BUY/SELL type or non-empty typeExtended. Verified
    against real cache data in commit 2 and tightened if it over-drops."""
    t = (trade.get("type") or "").upper()
    ext = trade.get("typeExtended") or ""
    return t not in {"BUY", "SELL"} or bool(ext)


def is_non_self_owner(owner: str | None) -> bool:
    if not owner:
        return False
    return owner.strip().lower() != "self"


def is_late_filing(filed_after_days: int | None) -> bool:
    return bool(filed_after_days and filed_after_days >= 40)
```

**`scoring/score_members.py` wire-in** (new helper, called from the per-member loop after `normalize_ticker`):

```python
def apply_filters(trades: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Drop ETFs + options; tag non-self + late. Returns (kept, drop_counts)."""
    kept = []
    drops = {"etf_drops": 0, "options_drops": 0}
    for t in trades:
        if is_broad_market_etf(t.get("ticker")):
            drops["etf_drops"] += 1
            continue
        if is_options_trade(t):
            drops["options_drops"] += 1
            continue
        t["non_self_filing"] = is_non_self_owner(t.get("owner"))
        t["late_filing"] = is_late_filing(t.get("filedAfterDays"))
        kept.append(t)
    return kept, drops
```

**`scoring/factors.py::aggregate_member_factors`** gains six output fields per locked decision 8. Drop counts are threaded through from `apply_filters` (not computable from `trades` after filtering, since the dropped records are gone).

**`build_leaderboard.py`**: `build_table_rows` extended with `non_self_share`, `late_share`, `etf_drops`, `options_drops` columns; table headers updated in both 180d and 365d sections.

## Test plan

| File | Cases (rough) | Coverage |
|---|---|---|
| `tests/test_filters.py` (new) | ~16 | Parametrized: `is_broad_market_etf` (SPY → true, JPM → false, case-insensitive, empty/None → false). `is_options_trade` (BUY → false, EXCHANGE → true, typeExtended non-empty → true, missing keys → false/safe). `is_non_self_owner` (self/Self/SELF → false, spouse/child/joint/dependent → true, None/empty → false). `is_late_filing` (0/20/39 → false, 40/45/60 → true, None → false). |
| `tests/test_composite_math.py` (extended) | +~4 | `aggregate_member_factors` extended coverage: given a small trade list with known mix, asserts correct `non_self_count / _share`, `late_count / _share`, and drop counts threaded through. Discharges the factors.py-extends-its-tests rule. |
| `tests/test_leaderboard_filter_columns.py` (new, commit 5) | ~4 | Schema-contract test over the rendered leaderboard HTML: new column headers present, new `fmt_pct`/integer cell shapes present, column ordering preserved. |

No fixture file additions needed — all tests use inline literals.

## Non-goals

- Dropping spouse / non-self trades (tagging preserves the signal).
- Filtering corporate actions, dividends, splits (not in the four named filters).
- A sector-ETF filter (only broad-market — sector ETFs like XLE / XLF may carry member-informed signal).
- Dynamic ETF list (hardcoded; stable short list).
- Retroactive recomputation of historical scores (next `score_members.py` run re-derives).
- Re-tuning composite weights for tagged trades — #4's job.
- Updating `compute_analysis.py` / `build_skeleton.py` / the weekly report. The weekly report consumes raw trade data and doesn't need filter awareness in v1.
- Per-owner-type columns (`spouse_share`, `child_share`, etc.). Single `non_self_share` is sufficient.

## Responsibility table

| Concern | Owner | Notes |
|---|---|---|
| Filter primitives (pure functions) | Script (`scoring/filters.py`, new) | Four functions, no state |
| Composing filters over a trade list (drops + tags + counts) | Script (`scoring/score_members.py::apply_filters`, new helper) | Called from the per-member loop after `normalize_ticker` |
| Aggregating filter outputs into member-level columns | Script (`scoring/factors.py::aggregate_member_factors`, extended) | Six new fields; factors.py-rule triggers `test_composite_math.py` extension |
| Broad-market ETF list | Static `frozenset` in `scoring/filters.py` | One-line PRs for additions |
| Leaderboard xlsx columns | Script (`scoring/score_members.py` xlsx writer, extended) | New columns appended to `display_cols`; transition-period preserves existing columns |
| Leaderboard HTML rendering | Script (`build_leaderboard.py`, extended) | New column headers + cells in both 180d and 365d tables |
| Options-encoding verification | Agent (commit 2 prep) | Grep any local `scoring/cache/trades/` for distinct `type` / `typeExtended`; tighten if safe default over-drops |
| Deciding drop-vs-tag per filter | Agent (this design note) | Locked; do not re-litigate |
| `[~] → [x]` flip on ROADMAP #3 | User | After reshuffle directionality confirmed and leaderboard renders with new columns |

## Commit plan

1. **This commit.** `design/signal-quality-filters.md` + `design/README.md` listing update + ROADMAP `[ ] → [~]` flip on #3 + session-summary refresh. No code.
2. **Filter primitives + tests.** `scoring/filters.py` (four pure functions) + `tests/test_filters.py` (~16 parametrized cases). Pre-commit prep: scan any `scoring/cache/trades/` locally for distinct `type` / `typeExtended` values and tighten `is_options_trade` if the safe default over-drops. Discharges "ship tests with the feature" for the new primitives.
3. **Wire into `score_members.py`; extend `aggregate_member_factors`.** New `apply_filters` helper; factor aggregation gains six fields. Extends `tests/test_composite_math.py` with ~4 cases covering the aggregation side. Discharges the `scoring/factors.py`-extends-its-tests rule. Tom re-runs `score_members.py` locally after this commit to see the reshuffle — big QA checkpoint.
4. **Leaderboard surface.** xlsx column additions + `build_leaderboard.py` rendering updates. Transition-period display (old columns stay). Tom visually confirms new columns render cleanly on push.
5. **Schema-contract test + ETF list documentation.** `tests/test_leaderboard_filter_columns.py` pins the rendered HTML shape. ETF list gets a short comment block in `scoring/filters.py` explaining why NANC / KRUZ / sector ETFs are intentionally excluded. Leaves ROADMAP #3 in `[~]` — Tom signs off after the reshuffle directionality matches his intuition (ETF-heavy members drop; non-self-heavy members unchanged but tagged).

Each commit stands alone — mid-feature handoff picks up from this note plus the last SHA without re-litigating scope.
