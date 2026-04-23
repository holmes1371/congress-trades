"""
Deterministic fixture for the walk-forward backtest unit test
(ROADMAP #5, under the shared design note `design/postfile-alpha-and-backtest.md`).

Purpose: provide a synthetic member + paired price series so
`tests/test_backtest.py` (commit 6/6) can exercise the full replay
loop — monthly rebalance, top-K cohort selection, D+1 entry,
60-business-day horizon exit — without yfinance and with exact,
hand-computable expected outputs.

Exports:

  * SYNTH_MEMBER            — member dict matching
                              `fetch_trades.fetch_member_trades`'s
                              return shape (bioguideId, fullName,
                              party, chamber, state, trades, tradeCount).
  * SYNTH_PRICES            — dict[date, float], the price ladder.
  * SPY_PRICES, NANC_PRICES — dict[date, float], flat benchmark series.
  * make_prices_frame()     — wrap any of the above dicts into the
                              pd.DataFrame shape
                              `price_cache.get_prices()` returns
                              (DatetimeIndex, columns 'close' + 'volume').
  * FIXTURE_START, FIXTURE_END — calendar anchors for the price table.
  * TRADE_DATES             — the 24 monthly trade dates, exposed so
                              the test can cross-check without
                              re-computing.

Design choices:

  * **Calendar.** `pd.bdate_range(FIXTURE_START, FIXTURE_END)` —
    pandas Mon-Fri, no holidays. Matches `pd.offsets.BDay` arithmetic
    so the backtest's "+ BDay(2)" entry-buffer and "+ BDay(60)"
    exit-horizon arithmetic agree with the fixture's own index without
    needing a holiday calendar.
  * **SYNTH price ladder.** Start at 100.00 on the first fixture bday,
    += 0.10 on each subsequent bday. Every trade's 60-bday hold
    returns exactly +6.00 in absolute $; per-trade % return shrinks
    over time as the denominator grows. Hand-computable.
  * **SPY / NANC flat.** SPY at 500, NANC at 50. Market-adjusted
    return == stock return; strategy-vs-NANC alpha == strategy return.
    Keeps the test's expected-summary arithmetic trivial.
  * **Trade schedule.** 24 BUYs, first business day of each month from
    2022-01 through 2023-12. Every trade is 100 shares of "SYNTH",
    filedAfterDays=30, owner='self', typeExtended=None — so the
    signal-quality filters (ROADMAP #3) pass them all through and the
    member always qualifies for the cohort.
  * **Price table span.** 2021-12-01 through 2024-06-30. Covers the
    first trade's trailing-window prices, the last trade's +30cd
    publication lag, and that trade's post-file entry + 60 bday
    exit window.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd


FIXTURE_START = date(2021, 12, 1)
FIXTURE_END = date(2024, 6, 30)

_FIXTURE_BDAYS: list[date] = [
    d.date() for d in pd.bdate_range(FIXTURE_START, FIXTURE_END)
]

# SYNTH ladder: $100.00 on the first bday, += $0.10 each subsequent bday.
SYNTH_PRICES: dict[date, float] = {
    d: round(100.00 + 0.10 * i, 2) for i, d in enumerate(_FIXTURE_BDAYS)
}

# Flat benchmarks.
SPY_PRICES: dict[date, float] = {d: 500.0 for d in _FIXTURE_BDAYS}
NANC_PRICES: dict[date, float] = {d: 50.0 for d in _FIXTURE_BDAYS}


def _first_bday_of_month(year: int, month: int) -> date:
    """First Mon–Fri of the given calendar month. Matches the fixture's
    no-holiday Mon–Fri calendar."""
    d = date(year, month, 1)
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d += timedelta(days=1)
    return d


TRADE_DATES: list[date] = [
    _first_bday_of_month(y, m)
    for y in (2022, 2023)
    for m in range(1, 13)
]


def _make_trade(d: date, idx: int) -> dict:
    """Synthesize a single BUY trade on date `d`. Shape mirrors what
    `fetch_trades._normalise_trade` emits, but only the fields the
    scoring pipeline reads are populated. `idx` seeds a stable, unique
    `txId` — capitoltrades supplies integer txIds in production, and
    ROADMAP #6's paper log uses (bioguide, txId) as the identity key
    for retraction detection."""
    close = SYNTH_PRICES[d]
    return {
        "txId":           20_000_000_000 + idx,
        "ticker":         "SYNTH",
        "type":           "BUY",
        "typeExtended":   None,
        "txDate":         d.isoformat(),
        "published":      (d + timedelta(days=30)).isoformat(),
        "filedAfterDays": 30,
        "value":          int(100 * close),
        "price":          close,
        "size":           100,
        "owner":          "self",
        "sector":         "Technology",
    }


SYNTH_MEMBER: dict = {
    "bioguideId": "SYNTH0",
    "fullName":   "Synth Member",
    "party":      "Independent",
    "chamber":    "House",
    "state":      "XX",
    "trades":     [_make_trade(d, i) for i, d in enumerate(TRADE_DATES)],
    "tradeCount": len(TRADE_DATES),
}


def make_prices_frame(
    price_map: dict[date, float], volume: float = 1_000_000_000
) -> pd.DataFrame:
    """Wrap a {date: close} dict in the shape `price_cache.get_prices`
    returns: DatetimeIndex over the provided dates, columns 'close'
    and 'volume'.

    `volume` defaults to $1B at the lowest SYNTH close (≈$100) → ADV
    well over the $10M LIQUIDITY_ADV_FLOOR, so the liquidity filter
    doesn't silently null the synthetic trades out.
    """
    idx = pd.DatetimeIndex(sorted(price_map.keys()))
    closes = [price_map[d.date()] for d in idx]
    return pd.DataFrame(
        {"close": closes, "volume": [volume] * len(closes)}, index=idx
    )
