"""
Hand-crafted alpha-math scenarios for `test_alpha_math.py`.

Separate from the recorded yfinance fixtures (`prices/*.csv`) because
these scenarios target edge cases — holiday gaps, splits, missing price
days — that real data rarely stages cleanly. Decoupling them from the
recorded fixtures also means yfinance re-records don't invalidate
edge-case assertions.

Each scenario is a `dict` that `test_alpha_math.py` will consume via
`pytest.mark.parametrize`. Exact key names / shapes will settle when
the test file is written in pytest commit 4/6; this file seeds the
content so the test author has concrete edge cases to parametrize over
rather than inventing them at test-writing time.

All prices are `(date, close)` tuples in ascending-date order. Dates
are business days except where a scenario deliberately spans a holiday
gap.
"""

from __future__ import annotations

from datetime import date


# ─── Scenario 1: clean 5-day hold, no gaps ───────────────────────────
#
# Member buys at 100 on 2024-03-04; the stock closes at 105 five
# business days later. Alpha over SPY (flat at 500) is +5%.
CLEAN_5D_BUY = {
    "name": "clean_5d_buy_flat_benchmark",
    "trade_date": date(2024, 3, 4),
    "publication_date": date(2024, 3, 18),  # +14 calendar days
    "ticker_prices": [
        (date(2024, 3, 4), 100.0),
        (date(2024, 3, 5), 101.0),
        (date(2024, 3, 6), 102.0),
        (date(2024, 3, 7), 103.0),
        (date(2024, 3, 8), 104.0),
        (date(2024, 3, 11), 105.0),  # D+5 business day
    ],
    "benchmark_prices": [
        (date(2024, 3, 4), 500.0),
        (date(2024, 3, 5), 500.0),
        (date(2024, 3, 6), 500.0),
        (date(2024, 3, 7), 500.0),
        (date(2024, 3, 8), 500.0),
        (date(2024, 3, 11), 500.0),
    ],
    "horizon_bdays": 5,
    "expected_alpha_approx": 0.05,  # +5% ticker move, 0% benchmark move
}


# ─── Scenario 2: Good Friday holiday gap ─────────────────────────────
#
# Member buys Wednesday before a Good Friday close. 5 business days
# later skips over Friday and the weekend. Tests that the alpha math
# counts business days, not calendar days.
HOLIDAY_GAP_5D_BUY = {
    "name": "holiday_gap_good_friday",
    "trade_date": date(2024, 3, 27),  # Wed before Good Friday 2024
    "publication_date": date(2024, 4, 10),
    "ticker_prices": [
        (date(2024, 3, 27), 200.0),
        (date(2024, 3, 28), 202.0),
        # 2024-03-29 is Good Friday — NYSE closed, no entry
        (date(2024, 4, 1), 204.0),
        (date(2024, 4, 2), 206.0),
        (date(2024, 4, 3), 208.0),
        (date(2024, 4, 4), 210.0),  # D+5 business day
    ],
    "benchmark_prices": [
        (date(2024, 3, 27), 500.0),
        (date(2024, 3, 28), 500.0),
        (date(2024, 4, 1), 500.0),
        (date(2024, 4, 2), 500.0),
        (date(2024, 4, 3), 500.0),
        (date(2024, 4, 4), 500.0),
    ],
    "horizon_bdays": 5,
    "expected_alpha_approx": 0.05,  # +5% ticker, 0% benchmark
}


# ─── Scenario 3: post-file entry materially different from trade-date ─
#
# Member trades on 2024-01-03 at 100. Publishes on 2024-02-15
# (well past the disclosure median). By publication the stock has
# already rallied to 120 — trade-date alpha is strong but post-file
# alpha is flat. Used to validate that #2's post-file alpha column
# computes from publication, not trade date.
POSTFILE_DIVERGENCE = {
    "name": "postfile_entry_misses_runup",
    "trade_date": date(2024, 1, 3),
    "publication_date": date(2024, 2, 15),
    "ticker_prices": [
        (date(2024, 1, 3), 100.0),
        (date(2024, 2, 15), 120.0),
        (date(2024, 2, 16), 121.0),
        (date(2024, 2, 20), 120.5),  # post-presidents-day
        (date(2024, 2, 21), 121.0),
        (date(2024, 2, 22), 120.5),
        (date(2024, 2, 23), 120.0),  # D+5 business day from pub
    ],
    "benchmark_prices": [
        (date(2024, 1, 3), 500.0),
        (date(2024, 2, 15), 500.0),
        (date(2024, 2, 16), 500.0),
        (date(2024, 2, 20), 500.0),
        (date(2024, 2, 21), 500.0),
        (date(2024, 2, 22), 500.0),
        (date(2024, 2, 23), 500.0),
    ],
    "horizon_bdays": 5,
    "expected_alpha_trade_date_approx": 0.20,     # 100 → 120
    "expected_alpha_post_file_approx": 0.0,       # 120 → 120
}


# ─── Scenario 4: 2-for-1 split between entry and exit ────────────────
#
# yfinance typically adjusts splits, but this scenario verifies the
# math assumes split-adjusted input and does not double-count. Both
# ticker and benchmark series are already split-adjusted.
SPLIT_ADJUSTED_HOLD = {
    "name": "split_adjusted_no_double_count",
    "trade_date": date(2024, 6, 3),
    "publication_date": date(2024, 6, 17),
    "ticker_prices": [
        (date(2024, 6, 3), 50.0),   # pre-split price would be 100
        (date(2024, 6, 4), 50.5),
        (date(2024, 6, 5), 51.0),
        (date(2024, 6, 6), 51.5),
        (date(2024, 6, 7), 52.0),
        (date(2024, 6, 10), 52.5),  # D+5 bday
    ],
    "benchmark_prices": [
        (date(2024, 6, 3), 500.0),
        (date(2024, 6, 4), 500.0),
        (date(2024, 6, 5), 500.0),
        (date(2024, 6, 6), 500.0),
        (date(2024, 6, 7), 500.0),
        (date(2024, 6, 10), 500.0),
    ],
    "horizon_bdays": 5,
    "expected_alpha_approx": 0.05,
}


# ─── Scenario 5: missing price day inside the horizon window ─────────
#
# A single business day has no data (illiquid ticker, data-provider gap).
# Exercises the forward-fill / skip-day behavior that
# `_next_close_at_or_after` in scoring/factors.py is responsible for.
MISSING_DAY_INSIDE_HORIZON = {
    "name": "missing_day_forward_fills",
    "trade_date": date(2024, 5, 6),
    "publication_date": date(2024, 5, 20),
    "ticker_prices": [
        (date(2024, 5, 6), 75.0),
        (date(2024, 5, 7), 76.0),
        # 2024-05-08 missing entirely
        (date(2024, 5, 9), 77.0),
        (date(2024, 5, 10), 78.0),
        (date(2024, 5, 13), 78.75),  # D+5 bday (counting real days)
    ],
    "benchmark_prices": [
        (date(2024, 5, 6), 500.0),
        (date(2024, 5, 7), 500.0),
        (date(2024, 5, 8), 500.0),
        (date(2024, 5, 9), 500.0),
        (date(2024, 5, 10), 500.0),
        (date(2024, 5, 13), 500.0),
    ],
    "horizon_bdays": 5,
    "expected_alpha_approx": 0.05,  # 75 → 78.75 is +5%
}


ALL_SCENARIOS = [
    CLEAN_5D_BUY,
    HOLIDAY_GAP_5D_BUY,
    POSTFILE_DIVERGENCE,
    SPLIT_ADJUSTED_HOLD,
    MISSING_DAY_INSIDE_HORIZON,
]
