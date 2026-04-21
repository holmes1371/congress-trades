# Pytest suite + CI workflow — design note

ROADMAP #1. Active feature. Flipped to `[~]` alongside this note in the commit that introduces it.

## Scope

**In scope.** A `tests/` directory with a pytest suite covering the stable primitives in the codebase (ticker normalization, money-range parsing, date parsing, price-cache read contract, alpha math, composite math, transaction classification, end-to-end parse of one capitoltrades record set). Shared fixtures under `tests/fixtures/` designed for compounding reuse across ROADMAP items #2–#11. A `requirements-dev.txt` declaring dev dependencies (`pytest`, `responses`). A GitHub Actions workflow at `.github/workflows/tests.yml` running pytest on push-to-main and pull-requests-against-main, on Python 3.11. Two "extend tests with the feature" clauses appended to `ROADMAP.md`'s "For future agents" section in the final commit of this feature.

**Out of scope.** Coverage reporting, linting (ruff / black / mypy), matrix builds, integration tests against live capitoltrades or live yfinance, branch protection rules (a manual GitHub-UI step — checklist below), and any snapshot tests pinning current composite weights, ranking output, or leaderboard shape (see "Guiding principle").

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
9. **Branch protection is a manual GitHub-UI step**, not a workflow-file concern. Checklist below; user configures once.

## Test plan

Eight modules under `tests/`, target ~50 cases total:

| File | Cases (rough) | Coverage |
|---|---|---|
| `test_ticker_normalization.py` | ~8 | `TICKER:US` → `TICKER`, dots, foreign-suffix rejection, empty/null edges |
| `test_money_range_parse.py` | ~6 | `$15,001–$50,000` → `(15001, 50000)`; em-dash vs hyphen; `$1,000,000+`; malformed input |
| `test_date_parse.py` | ~6 | trade date, publication date, timezone handling, missing-field behavior |
| `test_price_cache.py` | ~5 | hit, miss, missing date range, concurrent access, corrupt-file fallback; mocks yfinance adapter |
| `test_alpha_math.py` | ~10 | parametrized over entry dates (trade-date, post-file) and horizons (5d/20d/60d); holiday gap; synthetic edge cases |
| `test_composite_math.py` | ~5 | z-score, weighted sum, NaN handling, partial-input behavior; parametrized over weight tuples so no current choice is pinned |
| `test_transaction_classification.py` | ~6 | buy, sell, exchange, options rolls, corporate actions, edge cases |
| `test_fetch_trades_parse.py` | ~3 | one end-to-end parse over the recorded fixture; record count, field presence; no assertion on derived scoring |

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
@responses.activate
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

## CI workflow sketch (`.github/workflows/tests.yml`)

```yaml
name: Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

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

## "Extend tests with the feature" clauses (lands in commit 6/6)

Two bullets appended to `ROADMAP.md`'s "For future agents" section:

- Tests live in `tests/` and run on every push + PR via `.github/workflows/tests.yml`. A red test check blocks merge once branch protection is configured. Do not mark a feature done with tests failing.
- Any change to `scoring/factors.py` must extend `tests/test_alpha_math.py` or `tests/test_composite_math.py` in the same commit. Other modules with existing test coverage extend their fixtures in step with the change, not after.

## Branch protection checklist (manual, post-commit-6/6)

After commit 6/6 lands and the first green check appears, user configures in the GitHub UI:

1. Settings → Branches → Add branch protection rule.
2. Branch name pattern: `main`.
3. Require a pull request before merging.
4. Require status checks to pass before merging.
5. Select `pytest` as a required status check.
6. Save.

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
| Branch protection configuration | User (GitHub UI) | Checklist above |
| `[~] → [x]` flip on ROADMAP #1 | User | After branch protection is configured and first green check seen |

## Commit plan

1. **This commit.** `design/pytest-ci-suite.md` + `design/README.md` listing update + ROADMAP `[ ] → [~]` flip on #1 + session-summary update.
2. **Scaffolding.** `requirements-dev.txt`, `tests/conftest.py`, `tests/fixtures/` with all four fixture files, and `tests/fixtures/_record.py`.
3. **Tests batch 1** (pure-function, no network). `test_ticker_normalization.py`, `test_money_range_parse.py`, `test_date_parse.py`.
4. **Tests batch 2** (needs fixtures). `test_price_cache.py`, `test_alpha_math.py`, `test_composite_math.py`.
5. **Tests batch 3** (schema contract). `test_transaction_classification.py`, `test_fetch_trades_parse.py`.
6. **CI + ROADMAP.** `.github/workflows/tests.yml` + the two "For future agents" bullets. Leaves ROADMAP #1 in `[~]`; user flips to `[x]` after seeing the first green check and configuring branch protection.

Each commit stands alone — mid-feature handoff picks up from this note plus the last SHA without re-litigating scope.
