# Cost / tax / sizing overlays

Design note for **ROADMAP #7** — a single overlay layer that sits on
top of the gross per-trade PnL produced by
`scoring/backtest.py::walk_forward` and
`scoring/paper_log.py::PaperLog`, giving a net-of-costs view without
rewriting either engine. Plan approved session 3 (2026-04-23).
Complexity classified **medium → think hard**.

Fresh-session pickup: read this note + `design/paper-log.md` +
`design/postfile-alpha-and-backtest.md` + the last commit on the feature
branch. No prior-session context required.

## Framing

`paper_log.py` and `backtest.py` already compute per-trade gross PnL as
`exit/entry - 1`. #7 does **not** rewrite that surface — stored rows
stay gross; the overlays live in a new pure-math module
`scoring/costs.py` that the backtest summary and the paper-log HTML
render consume on-the-fly.

Three overlays, one module:

1. **Slippage** — round-trip basis-point haircut on each trade's
   `pnl_pct`, keyed to ADV tier so small-caps bear higher cost than
   large-caps.
2. **Tax drag** — gain-only haircut on realized PnL at a combined
   federal-short-term + VA state rate. Losses unaffected in v1.
3. **Sizing** — equal-weight (status quo) vs. range-weighted using the
   capitoltrades `value` field as a weak conviction proxy. Affects
   portfolio-level aggregate stats only; per-trade rows keep their
   equal-weight interpretation.

The three share the same seam: they read gross per-trade rows (dicts
for the backtest, CSV rows for the paper log), return net-of-overlay
aggregates. No schema change to `scoring/paper_log/positions.csv`.

## Locked decisions

All Tom-approved at plan time (2026-04-23). Don't re-litigate without
a new prompt.

1. **Slippage model.** Static tiered-bps table keyed to ADV. Tiers and
   defaults:
   - `large` (ADV ≥ $100M/day) → **5 bps** round-trip.
   - `mid`   ($10M ≤ ADV < $100M) → **25 bps** round-trip.
   - `small` (ADV < $10M) → **75 bps** round-trip.
   Applied as `pnl_pct_net = pnl_pct - bps/10000`. CLI:
   `--slippage-mode {off, tiered, flat_bps:<N>}`, default `tiered`.
   Rationale: yfinance-derived spread proxies
   (`(high-low)/close`) are noisy and overstate real execution cost;
   a static tier table is honest, simple, and overridable. ADV is
   already computed at pipeline-run time as `ticker_adv` in
   `scoring/factors.py::compute_ticker_adv` — no new data source.
2. **Tax rate.** One `--tax-rate` CLI flag, default **0.2975**
   (federal short-term 24% + VA state 5.75%, since Tom lives in
   Virginia). Gain-only adjustment: `pnl_pct_net = pnl_pct * (1 - rate)`
   if `pnl_pct > 0`, unchanged otherwise. Loss harvesting is a v2
   question — the paper log's 60-bday horizon means every realized
   gain is short-term, so the rate doesn't branch.
3. **Sizing modes.** `--sizing-mode {equal, range}`, default `equal`.
   - `equal` → each trade contributes `1/N` of the portfolio return
     (matches #5 backtest today).
   - `range` → weight each trade by `t["value"]` (capitoltrades'
     pre-bucketed disclosed midpoint) and divide by the sum; trades
     with missing / zero `value` fall back to the per-run median.
   Affects only aggregate stats (`summary.strategy.total_return`,
   `alpha_vs_spy`, `hit_rate`, `sharpe`); the per-trade row in the
   backtest JSON and the paper-log CSV is untouched.
4. **Scope of the overlays.** Strategy PnL only — both
   `walk_forward`'s summary and the paper-log HTML's lifetime-summary
   section. Explicitly **NOT** the composite at ranking time. Net-of-costs
   composite scoring is a meaningful v2 question but materially changes
   what the composite measures; filed as an explicit out-of-scope
   follow-up below.
5. **Where the overlays compute.** Reporting-layer only — stored
   columns remain gross. The CSV schema from #6 doesn't change; the
   backtest JSON schema gains net-of-costs fields under
   `summary.strategy` alongside gross.
6. **State tax default.** VA (5.75%) because Tom lives there. If the
   follower lives elsewhere, `--tax-rate` is the single knob to
   override. Not per-member, not per-trade, not user-configurable per
   state name — one composite rate, documented in the CLI help text.
7. **Applying slippage at entry and exit.** One round-trip haircut
   per trade rather than two single-leg haircuts. Simpler, and the
   tier-bps numbers above already correspond to round-trip cost, not
   per-leg spread.
8. **Slippage on the benchmark.** The strategy pays slippage; SPY /
   NANC benchmarks do **not** — they're reference instruments, not
   executed trades in the replay. `alpha_vs_spy_net` compares the
   strategy's net return to the benchmark's gross. Rationale: a
   follower buying SPY pays the same slippage; keeping the benchmark
   gross keeps the alpha-vs-benchmark comparison anchored on the
   strategy's cost differential, not on double-counted drag.
9. **No overlay applied to paper-log `pnl_abs` / `pnl_pct`.** The CSV
   row keeps its gross mark-to-market semantics — each row is a single
   position, and the overlays are portfolio-level concepts (tax drag
   depends on realized vs. unrealized; sizing redistributes weight
   across trades). The HTML render computes the net view at display
   time from the same gross rows. Round-trip slippage is the one
   overlay that *could* have been per-row (it's a pure function of
   `pnl_pct`), but landing it alongside tax / sizing in a single
   display-time compute keeps the overlays consistently off the
   persistence layer.

## `scoring/costs.py` shape

Pure-math module. No I/O. No coupling to `paper_log.py` or
`backtest.py`. All primitives deterministic, table-driven.

```python
# Tier table — adjustable without code changes elsewhere.
SLIPPAGE_BPS_TIERS = {
    "large": 5.0,   # ADV >= $100M / day
    "mid":   25.0,  # $10M <= ADV < $100M
    "small": 75.0,  # ADV < $10M
}
ADV_LARGE_THRESHOLD = 100_000_000.0
ADV_MID_THRESHOLD   = 10_000_000.0

# Default composite short-term rate: federal 24% + VA 5.75%.
DEFAULT_TAX_RATE = 0.2975

def classify_tier(adv: float) -> str:
    """Return 'large' | 'mid' | 'small' by ADV. Unknown/None → 'small'
    (conservative — assume highest cost when we don't know)."""

def slippage_bps_for_ticker(ticker: str, ticker_adv: dict[str, float],
                            *, mode: str = "tiered") -> float:
    """Resolve the per-trade round-trip bps cost.
    mode='off'           → 0.0
    mode='tiered'        → SLIPPAGE_BPS_TIERS[classify_tier(adv)]
    mode='flat_bps:<N>'  → N (parsed from the string)
    """

def apply_slippage(pnl_pct: float, bps: float) -> float:
    """Round-trip haircut: pnl_pct - bps / 10000.0. No gain/loss branch
    — slippage is paid in both directions."""

def apply_tax(pnl_pct: float, rate: float) -> float:
    """Gain-only haircut: pnl_pct * (1 - rate) if pnl_pct > 0 else pnl_pct.
    rate in [0, 1); validated."""

def apply_sizing(trades: list[dict], mode: str = "equal") -> float:
    """Return the portfolio-level mean of `pnl_pct`. Modes:
    equal → arithmetic mean.
    range → value-weighted: sum(t['value'] * t['pnl_pct']) / sum(t['value']).
            Trades with missing / zero 'value' fall back to the
            per-run median of the present values; if every value is
            missing, degrades to equal-weight and emits a single warning
            (not an exception)."""
```

## Hook-in points

### `scoring/backtest.py::walk_forward` (commit 3)

Add CLI flags to `main()`: `--slippage-mode`, `--tax-rate`,
`--sizing-mode`. Thread them through to `walk_forward` as keyword
arguments (default: slippage `tiered`, tax 0.2975, sizing `equal`).

Per-trade dicts in `rebalance_log` stay as-is (gross). Summary stats
gain five net-of-overlay fields under `summary.strategy`:

- `total_return_net`
- `alpha_vs_spy_net`
- `alpha_vs_nanc_net`
- `alpha_vs_naive_copy_everyone_net`
- `hit_rate_net` (based on `alpha_vs_spy_net` sign)

Also: `summary.strategy.overlays` capturing the config under which the
net stats were computed:

```json
"overlays": {
  "slippage_mode": "tiered",
  "tax_rate": 0.2975,
  "sizing_mode": "equal",
  "slippage_bps_by_ticker": { "AAPL": 5.0, "NVDA": 5.0, ... }
}
```

No change to `rebalances[].trades[]` — per-trade rows remain gross so
a future consumer can re-compute net stats at any rate without re-running
the replay.

### `scoring/paper_log.py::main()` + `build_paper_log.py` (commit 4)

Paper-log CLI gains the same three flags. `paper_log.main()` passes
them to `PaperLog.walk(...)` via a new `overlays: dict | None = None`
kwarg — the walk loop doesn't apply overlays (ledger stays gross) but
stashes the config so the HTML renderer can read it off the saved run.

`build_paper_log.py`'s lifetime-summary section gets a second column
showing the net-of-overlay view alongside the existing gross metrics.
Schema-contract test in `tests/test_paper_log_page.py` pins the new
headers (`Gross`, `Net`) and at least one assertion that the net total
is less than the gross total when slippage is on and the lifetime PnL
is positive.

### Pipeline wiring (commit 5)

`update-leaderboard.yml` and `update-report.yml` invoke `paper_log.py`
today. Extend their CLI calls with explicit defaults:

```yaml
python scoring/paper_log.py --slippage-mode tiered --tax-rate 0.2975 --sizing-mode equal
```

Explicit-over-implicit: if the module defaults ever drift, the
workflow's numbers don't silently change.

## Fixture plan

- **Reuse** `tests/fixtures/backtest_synthetic_member.py` from #5 — the
  synthetic BUYs and deterministic price ladder give known-return
  inputs for the portfolio-level overlay math.
- **Synthetic ADV dict** in `tests/test_costs.py` for tier-classification
  cases — no file fixture needed; in-memory `{"LARGE": 2e8, "MID":
  5e7, "SMALL": 1e6}` covers the boundary cases.
- **No yfinance re-record.** The overlays read ADV from the in-memory
  `ticker_adv` dict already computed by `compute_ticker_adv`; they
  never touch the price-cache directly.

## Test plan

New file `tests/test_costs.py` — ~30 parametrized cases:

- `classify_tier` boundaries: ADV at $100M, just under, just over;
  $10M, just under, just over; None → small.
- `slippage_bps_for_ticker` with each mode, including `flat_bps:15`
  parse, `off` returns 0, missing-ticker → small tier.
- `apply_slippage` arithmetic: positive pnl, negative pnl, zero bps
  no-op, round-trip identity (1 - 1/1 = 0 minus 5bps = -0.0005).
- `apply_tax` gain-only: positive haircut, negative untouched, zero
  unchanged, rate=0 no-op, rate=1 zeros out gains.
- `apply_sizing` modes: equal on a known list, range on weighted list
  with present values, range with all values missing → equal fallback,
  range with partial missing → median fallback.
- Defensive: negative rate raises `ValueError`; malformed `flat_bps:`
  string raises `ValueError`.

Extended `tests/test_backtest.py` — 4–6 cases covering:

- Summary gains net-of-overlay fields under `summary.strategy`.
- `alpha_vs_spy_net < alpha_vs_spy` when slippage > 0 and the
  strategy's gross alpha is positive.
- `total_return_net == total_return` when all three overlays are
  configured to no-op.
- `summary.strategy.overlays` captures the config faithfully.

Extended `tests/test_paper_log_page.py` — 2–3 schema-contract cases:

- Lifetime-summary section renders `Gross` and `Net` column headers.
- Net total < Gross total when slippage is on and the lifetime PnL is
  positive.
- Em-dash fallback when lifetime PnL is unset.

Target pytest count after commit 5: current + ~35–40 cases.

## Commit sequence (5 commits)

1. **Design note + ROADMAP flip.** This file + `design/README.md`
   listing + `[~]` flip on #7 in `ROADMAP.md`. No production code.
2. **`scoring/costs.py` + `tests/test_costs.py`.** Pure-math module,
   full unit tests, no integration.
3. **Hook into `scoring/backtest.py`.** CLI flags;
   `summary.strategy.*_net`; `summary.strategy.overlays`. Extend
   `tests/test_backtest.py`. No change to per-trade rows.
4. **Hook into paper log.** CLI flags on `scoring/paper_log.py`;
   `build_paper_log.py` lifetime-summary gains `Gross | Net`
   columns; schema-contract tests.
5. **Pipeline wiring.** `update-leaderboard.yml` +
   `update-report.yml` pass explicit defaults to `paper_log.py`. No
   behavior change on the committed pages (defaults match module
   defaults) — the flags exist so a future tweak doesn't need to
   re-derive them from the module's internals.

Each commit leaves pytest green and the worktree buildable. Commits
3–5 can each slip to a new session if interrupted; commits 1–2 are
self-sufficient (design note + a pure-math module with no callers).

## Out of scope / follow-ups

- **Net-of-costs composite scoring.** Composite still ranks on gross
  alpha; overlays apply to strategy PnL only. The v2 question is
  whether follower-ranking should account for who's tradeable net of
  costs — meaningful but changes what the composite measures. File a
  follow-up item if Tom wants to pursue it.
- **Loss harvesting credit against tax drag.** Losses flow through
  unadjusted in v1. Proper harvesting credits would offset realized
  losses against the same-year realized gains before applying the
  rate; for a paper-trading log this is plausibly in-scope for v2.
- **Yfinance-derived dynamic spread proxies.** The tier table can be
  superseded later by `(high-low)/close` averaged over an entry-day
  window, or by a dedicated bid-ask data source. Tier table stays as
  the default even then (the dynamic path would be an opt-in mode).
- **Trailing stops / sell-on-subsequent-disclosure exits.** ROADMAP
  called these out as "#7-adjacent." Left fully parked — they need a
  design note of their own and would expand this bundle beyond the
  cost / tax / sizing scope.
- **Federal rate segmentation.** Holding periods are always < 1 year
  by the 60-bday horizon rule, so short-term rate applies uniformly.
  If a future variant (#6 follow-up) introduces >1-year holds, the
  tax helper needs a per-trade holding-period branch.
- **Per-state lookup table.** Single VA default is pragmatic; a
  lookup of `{"VA": 0.0575, "NY": 0.0882, ...}` would be cheap to add
  but premature — the follower-audience today is Tom.

## Responsibility table

| Concern | Owner | Notes |
|---|---|---|
| Slippage tier thresholds + bps | `scoring/costs.py` module constants | Plain-table edit; no runtime config. |
| Tax default (29.75%) | `scoring/costs.py::DEFAULT_TAX_RATE` | Documented as federal 24% + VA 5.75%. |
| Slippage mode resolution | `scoring/costs.py::slippage_bps_for_ticker` | Parses `flat_bps:<N>` strings. |
| Gross per-trade PnL | `scoring/paper_log.py::PaperLog`, `scoring/backtest.py::walk_forward` | Unchanged by #7. |
| Net-of-overlay aggregates | `scoring/costs.py::apply_*` invoked from `walk_forward` summary + `build_paper_log.py` render | Reporting layer. |
| Paper-log CSV schema | `scoring/paper_log.py::CSV_HEADERS` | Unchanged by #7. |
| Backtest JSON schema | `scoring/backtest.py::walk_forward` return | Gains `summary.strategy.*_net` and `summary.strategy.overlays`. |
| Pipeline defaults | `.github/workflows/update-leaderboard.yml` + `.../update-report.yml` | Explicit flags so defaults don't drift silently. |
| Net-of-costs composite | None / deferred | Explicit out-of-scope v2 item. |
