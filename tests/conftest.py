"""
Shared pytest fixtures for the congress-trades test suite.

All fixtures are session-scoped — fixture files are read once per test
run, not per test. Tests should treat the returned objects as read-only;
if a test needs to mutate a fixture, deep-copy it first.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

# Make the repo root importable so tests can `from scoring import ...`
# and `import fetch_trades` without a sys.path manipulation in every
# test file.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def capitoltrades_page_sample() -> dict:
    """One slimmed-down capitoltrades response blob (10 trades)."""
    with (FIXTURES / "capitoltrades_page_sample.json").open() as f:
        return json.load(f)


@pytest.fixture(scope="session")
def member_bioguide_sample() -> list:
    """Five bipartisan members trimmed from the full member_bioguide.json."""
    with (FIXTURES / "member_bioguide_sample.json").open() as f:
        return json.load(f)


@pytest.fixture(scope="session")
def price_cache_dir() -> Path:
    """Absolute path to the pre-populated ticker-CSV cache under fixtures/."""
    return FIXTURES / "prices"


@pytest.fixture(scope="session")
def price_cache_sample(price_cache_dir: Path) -> dict[str, pd.DataFrame]:
    """
    Mapping of ticker → DataFrame[close, volume] indexed by date.

    Parallels the shape `scoring.price_cache.get_prices` returns, so
    tests can use this as a drop-in replacement when monkeypatching
    network-bound paths.
    """
    out: dict[str, pd.DataFrame] = {}
    for csv_path in sorted(price_cache_dir.glob("*.csv")):
        ticker = csv_path.stem
        df = pd.read_csv(csv_path, parse_dates=["date"])
        df = df.set_index("date").sort_index()
        out[ticker] = df
    return out


@pytest.fixture(scope="session")
def synthetic_alpha_scenarios() -> list[dict]:
    """Hand-crafted alpha-math edge cases (holiday gaps, splits, missing days)."""
    from tests.fixtures import synthetic_alpha_scenarios as mod
    return mod.ALL_SCENARIOS
