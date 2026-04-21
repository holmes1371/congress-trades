# Pytest suite + CI workflow — design note

ROADMAP #1. Active feature. Flipped to `[~]` alongside this note in the commit that introduces it.

## Scope

**In scope.** A `tests/` directory with a pytest suite covering the stable primitives in the codebase (ticker normalization, record-level trade parse, price-cache read contract, alpha math, composite math, transaction classification, end-to-end parse of one capitoltrades record set). Money-range parsing and a dedicated date parser were in the original plan but were dropped from v1 after a code-reality check — neither exists as a standalone primitive in current code; see "Batch 1 amendment" under Test plan. Shared fixtures under `tests/fixtures/` designed for compounding reuse across ROADMAP items #2–#11. A `requirements-dev.txt` declaring dev dependencies (`pytest`, `responses`). A GitHub Actions workflow at `.github/workflows/tests.yml` running pytest on every push, on Python 3.11. Two "extend tests with the feature" clauses appended to `ROADMAP.md`'s "For future agents" section in the final commit of this feature.

**Out of scope.** Coverage reporting, linting (ruff / black / mypy), matrix builds, integration tests against live capitoltrades or live yfinance, pull-request triggers on the workflow (Tom works on `main` directly; see "Batch 4 amendment" under Commit plan), branch protection rules (dropped alongside the PR path — same amendment), and any snapshot tests pinning current composite weights, ranking output, or leaderboard shape (see "Guiding principle").

## Guiding principle

Test the **primitives**, not the **assembly**.

The #2–#11 backlog churns the assembly: composite weights (#2), ranking basis (#2), leaderboard columns (#4), report surfaces (#3, #10), default-follow output (#2). It does not churn the primitives those assemblies are built from — ticker normalization, money-range parsing, date parsing, the pure math of alpha given prices and dates, the price-cache read contract, transaction-type classification.

Tests covering the primitives survive every refactor in the backlog. Tests covering the current assembly would be deleted in the first commit of #2. Writing them now is waste.

## Stable-vs-churning surface map

**Stable (covered in v1):**

| Surface | Likely location | Why stable |
|---|---|---|
| Ticker normalization | `fetch_trades.py`, `scoring/` `normalize_ticker()` | Input-cleaning behavior; foreign-suffix rejection rule is settled |
| Disclosed-range money parse | `fetch_trades.py` / `compute_analysis.py` | #7 range-weighted sizing consumes the same parser |
| Date parsing (trade date, publication date) | `fetch_trades.py` | #2 uses publication date but does not redefine the parse |
| Price-cache read contract | `scoring/price_cache.py` | Every #2/#5/#6/#7 reads through this seam |
| Alpha math as a pure function of `(prices, entry_date, horizon)` | `scoring/factors.py` | #2 adds new entry-date values; the math itself is unchanged |
| Composite math (z-score + weighted sum) parameterized over weights | `scoring/factors.py` | Operation is stable; weight tuple may change |
| Transaction-type classification (buy/sell/exchange) | `fetch_trades.py` | #4 adds tags, does not redefine types |
| Single record-parse pass over a capitoltrades fixture | `fetch_trades.py` | Confirms schema contract; no assertion on derived scoring |

**Churning (deliberately skipped in v1):** current composite weights and resulting member ranks (#2 rebalances), default-follow list output (#2 flips the ranking basis), leaderboard / report HTML shape (#3 adds a row; #10 may retire the weekly report), and scoring defaults in `score_members.py` (the defaults are exactly what shifts).

## Locked decisions

1. **Python 3.11.** Matches `update-leaderboard.yml` and `update-report.yml`. No matrix.
2. **`pytest` only for v1.** No coverage, no lint, no mypy.
3. **capitoltrades mocking: `responses` library.** Fixtures stay as human-readable JSON, which future sessions can diff; the pattern extends cleanly into #8–#10 without retroactive rewrites.
4. **yfinance mocking: mock at the `scoring/price_cache.py` adapter, not at yfinance itself.** yfinance has broken its schema multiple times historically; the cache layer is the seam we control.
5. **Fixture source for capitoltrades: a live-recorded page, trimmed to ~10 records.** Faithful to the real schema; data is public, so no scrubbing.
6. **Price-cache fixture: a real yfinance snapshot, committed once.** ~10 tickers × ~2 years of daily closes.
7. **Synthetic alpha scenarios are hand-crafted, separate from the recorded fixture.** Used for edge cases (holiday gaps, splits, missing price days); decoupled from recorded historical data so yfinance re-records don't invalidate edge-case assertions.
8. **Primary "extend tests with the feature" anchor: `scoring/factors.py`.** Any change to this file must extend `tests/test_alpha_math.py` or `tests/test_composite_math.py` in the same commit. Other covered modules follow a softer fixture-extension rule.
9. **Workflow triggers on push only, no pull-request path, no branch protection.** Tom works directly on `main`; a PR gate and status-check merge requirement don't match the actual workflow. Tests still run on every push so regressions are visible in the commit UI. If the contribution model ever changes (a second committer, a staging branch), revisit in that PR.

## Test plan

Seven modules under `tests/`, target ~45 cases total:

| File | Cases (rough) | Coverage |
|---|---|---|
| `test_ticker_normalization.py` | ~20 (parametrized) | `TICKER:US` → `TICKER`, dots, foreign-suffix rejection, empty/null edges, placeholder strings, case/whitespace |
| `test_fetch_trades_normalise.py` | ~6 | `_normalise_trade`: `pubDate[:10]` truncation, missing `pubDate`, missing `issuer` block, `txType` uppercasing, missing `txType` |
| `test_price_cache.py` | ~4 | hit, miss, partial coverage, corrupt-file fallback; mocks yfinance adapter. "Concurrent access" dropped — see "Batch 2 amendment" |
| `test_alpha_math.py` | ~10 | parametrized over entry dates (trade-date, post-file) and horizons (5d/20d/60d); holiday gap; synthetic edge cases |
| `test_composite_math.py` | ~5 | z-score, weighted sum, NaN handling, partial-input behavior; parametrized over weight tuples so no current choice is pinned |
| `test_transaction_classification.py` | dropped | See "Batch 3 amendment" — no standalone classification primitive to test |
| `test_fetch_trades_parse.py` | ~12 | schema contract over the recorded fixture: envelope, member block, per-trade required keys, `type` domain, ISO date parseability, integer-field types |

**Batch 1 amendment (pytest 3/6):** the original plan had three batch-1 files —
`test_ticker_normalization.py`, `test_money_range_parse.py`, `test_date_parse.py`.
A code-reality check before writing them showed:

- **Money-range parsing.** The capitoltrades payload delivers `value` as an
  already-parsed integer (e.g. `175000`), not a range string like
  `"$15,001–$50,000"`. No parser exists in the current pipeline, so there is no
  primitive to test. If #7's range-weighted sizing introduces one, that's when
  the file gets written.
- **Date parsing.** There is no dedicated date-parse function either —
  `fetch_trades.py` calls stdlib `date.fromisoformat()` directly. The one
  non-trivial transformation is `pubDate[:10]` truncation inside
  `_normalise_trade`, which is folded into `test_fetch_trades_normalise.py`
  alongside the other missing/nullable-field behaviors in that function.

Net: three files → two files, ~20 cases → ~26 cases. The table above reflects
the amended shape.

**Batch 2 amendment (pytest 4/6).** Two deviations from the original plan
worth recording:

- `test_price_cache.py` — the "concurrent access" case named in the original
  plan was dropped. `_save_cache` writes the CSV non-atomically and the module
  has no locking; there is nothing to assert without first adding the locking,
  and adding locking is out of scope here. If #5 (paper-trading log) or #10
  (nightly cadence) introduces real concurrency on this seam, file the locking
  work and add the test then.
- `tests/fixtures/synthetic_alpha_scenarios.py` — Scenario 5 was renamed from
  `missing_day_forward_fills` to `entry_day_missing_forward_fills` and
  reshaped. The original imagined an *exit-side* forward-fill on the price
  series, but `factors._close_n_bdays_later` looks up exits by integer index
  into the DataFrame — there is no exit-side forward-fill to test. The
  renamed scenario exercises the *entry-side* forward-fill that
  `_next_close_at_or_after` actually implements (trade falls on a date with
  no row → entry resolves to the next available close).
- `compute_composite` weight parametrization — the original plan said
  "parametrize over weight tuples." `compute_composite` reads
  `COMPOSITE_WEIGHTS` from module scope rather than taking weights as a
  parameter, so parametrization is implemented as
  `monkeypatch.setattr(factors, "COMPOSITE_WEIGHTS", isolated)`. Each
  parametrize case isolates a single z-column under 100% weight and asserts
  the composite equals that column. This satisfies the no-pinning contract
  without forcing a refactor of `compute_composite`.

**Batch 3 amendment (pytest 5/6).** The original plan had two files in this
batch; one was dropped after a code-reality check:

- `test_transaction_classification.py` — dropped. There is no standalone
  transaction-classification function in the codebase to target as a
  primitive. `scoring/score_members.py` filters on `t["type"] == "BUY"`
  inline at several call sites; `fetch_trades._normalise_trade` just
  uppercases whatever `txType` the scraper emits (already covered by
  `test_fetch_trades_normalise.py::test_tx_type_uppercased`). The
  "exchange / options rolls / corporate actions" cases the original plan
  envisioned do not exist in code — the pipeline simply does not classify
  these types. If ROADMAP #4 (fetch-trades rewrite) introduces a
  classification helper, that's when this file gets written. For now the
  type-domain constraint ("every trade's `type` is `BUY` or `SELL`") is
  pinned at the schema-contract level in `test_fetch_trades_parse.py`,
  which is the appropriate seam given the current code.
- `test_fetch_trades_parse.py` — written as schema-contract tests over the
  recorded fixture, not an end-to-end scraper replay. The fixture on disk
  is already the post-`_normalise_trade` shape (that's what downstream
  scoring consumes), so mocking the HTTP layer with `responses` and
  running `fetch_page` against it would re-exercise code already covered
  by `test_fetch_trades_normalise.py` without adding signal. Instead,
  the 12 cases pin what the scoring pipeline actually depends on:
  envelope keys, member block keys, `tradeCount` vs `len(trades)` parity,
  per-trade required keys, `type ∈ {BUY, SELL}`, `txDate` and `published`
  ISO-parseability, integer-field types. When #4 re-records the fixture
  with fresh data, these tests must still pass as long as the schema
  contract holds.

## Fixtures

Under `tests/fixtures/`:

- `capitoltrades_page_sample.json` — one recorded capitoltrades API page, trimmed to 10 records. Reused by #2/#4/#5/#6/#8/#9.
- `price_cache_sample.csv` — ~10 tickers × ~2 years of yfinance daily closes. Reused by #2/#5/#6/#7.
- `member_bioguide_sample.json` — ~5 members, both parties, committee-assignment fields present. Reused by #8/#9 plus baseline tests.
- `synthetic_alpha_scenarios.py` — hand-crafted `(trade_date, publication_date, price_series, expected_alpha)` tuples for edge cases. Python module (not JSON) because the tuples are most readable as Python literals. Reused by #2 and #6 directly.

**Not included.** A committee-jurisdiction fixture — #8's responsibility; curating it now means it goes stale before use.

## Fixture-recording helper

`tests/fixtures/_record.py` — a one-shot script that regenerates the capitoltrades and yfinance fixtures deterministically. Leading underscore keeps it out of pytest discovery. Not run in CI; intended for periodic human-initiated refresh when the underlying APIs drift. Keeps fixture generation reproducible rather than an in-commit hand-edit.

**Known risk for commit 2/6:** the agent sandbox's network allowlist may not include `capitoltrades.com` or `query1.finance.yahoo.com`. If the recorder can't run from the sandbox, alternatives in priority order: run the recorder from a GitHub Actions manual `workflow_dispatch` job and commit the output via a PR; pre-record locally on a dev machine (not Tom's preferred path); or use the existing `fetch_trades.py` plumbing which already works in GHA — pointing the recorder at it rather than hitting the API fresh. Decided at commit 2/6 time based on what actually works.

## HTTP and yfinance mocking (illustrative)

capitoltrades via `responses`:

```python
@`1responses.activate
def test_fetch_trades_parse(capitoltrades_page_sample):
    responses.add(
        responses.GET,
        "https://bff.capitoltrades.com/trades",
        json=capitoltrades_page_sample,
        status=200,
    )
    result = fetch_trades.fetch_page(politician_id="K000389")
    assert len(result) == 10
```

yfinance via `monkeypatch` on the price-cache adapter:

```python
def test_price_cache_hit(monkeypatch, tmp_path, price_cache_sample):
    # Pre-populate cache; confirm no yfinance call occurs.
    monkeypatch.setattr(price_cache, "_yf_download",
                        lambda *a, **k: pytest.fail("yfinance should not be called"))
    result = price_cache.get_prices(["AAPL"], start="2024-01-01",
                                    end="2024-12-31", cache_dir=tmp_path)
    assert "AAPL" in result
```

Exact signatures will shift based on what is in the code at commit-write time; these are directional, not binding.

## CI workflow (`.github/workflows/tests.yml`)

```yaml
name: Tests

on: push

jobs:
  pytest:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: '3.11'
          cache: 'pip'
      - run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      - run: pytest
```

`on: push` is unfiltered — runs on every push to any branch. The
original sketch had `on: push: branches: [main]` paired with an
`on: pull_request:` block; both the branch filter and the PR trigger
were dropped at commit 6/6. See "Batch 4 amendment" under Commit plan.

## "Extend tests with the feature" clauses (lands in commit 6/6)

Two bullets appended to `ROADMAP.md`'s "For future agents" section:

- Tests live in `tests/` and run on every push via `.github/workflows/tests.yml`. Do not mark a feature done with tests failing; check the commit's test run before calling a feature closed.
- Any change to `scoring/factors.py` must extend `tests/test_alpha_math.py` or `tests/test_composite_math.py` in the same commit. Other modules with existing test coverage extend their fixtures in step with the change, not after.

## Responsibility table

| Concern | Owner | Notes |
|---|---|---|
| Fixture recording (live capitoltrades page, yfinance snapshot) | Script (`tests/fixtures/_record.py`, one-shot) | Not run in CI; regenerable on demand |
| Fixture loading | Script (`tests/conftest.py`) | Session-scoped fixtures mapping filename → parsed object |
| capitoltrades HTTP mocking | Script (`responses` library) | No agent judgment at test-run time |
| yfinance mocking | Script (`monkeypatch` against price-cache adapter) | No agent judgment at test-run time |
| Alpha math assertions | Script (parametrized pytest cases) | Uses both recorded and synthetic fixtures |
| Composite math assertions | Script (parametrized pytest cases) | Weight tuples passed as parameters, not hardcoded |
| Deciding what to cover and what to defer | Agent (this design note) | Stable-vs-churning judgment lives here, not in code |
| `[~] → [x]` flip on ROADMAP #1 | User | After first green check on the pytest workflow is seen |

## Commit plan

1. **This commit.** `design/pytest-ci-suite.md` + `design/README.md` listing update + ROADMAP `[ ] → [~]` flip on #1 + session-summary update.
2. **Scaffolding.** `requirements-dev.txt`, `tests/conftest.py`, `tests/fixtures/` with all four fixture files, and `tests/fixtures/_record.py`.
3. **Tests batch 1** (pure-function, no network). `test_ticker_normalization.py`, `test_fetch_trades_normalise.py` (folds the money-range / date-parse coverage the original plan had as separate files — see "Batch 1 amendment" under Test plan for why).
4. **Tests batch 2** (needs fixtures). `test_price_cache.py`, `test_alpha_math.py`, `test_composite_math.py`.
5. **Tests batch 3** (schema contract). `test_fetch_trades_parse.py` — schema-contract tests over the recorded fixture. `test_transaction_classification.py` was dropped; see "Batch 3 amendment" for why.
6. **CI + ROADMAP.** `.github/workflows/tests.yml` + the two "For future agents" bullets. Leaves ROADMAP #1 in `[~]`; user flips to `[x]` after seeing the first green check.

**Batch 4 amendment (pytest 6/6).** The workflow trigger was simplified
from `on: push (branches: [main]) + on: pull_request (branches: [main])`
to plain `on: push`, and the branch-protection checklist that was
originally planned as a post-commit-6/6 manual step was removed
entirely. Rationale: Tom pushes directly to `main` — there is no PR
gate to hang a required-status-check on, and a branch protection rule
requiring PRs would get in his way rather than protect anything. The
workflow still runs on every push, so a red test is visible in the
commit UI. If the contribution model changes later (a second
committer, a staging branch), the PR trigger and branch protection
can be added in that PR; they are not load-bearing for v1.

Each commit stands alone — mid-feature handoff picks up from this note plus the last SHA without re-litigating scope