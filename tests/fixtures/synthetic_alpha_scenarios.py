"""
Hand-crafted alpha-math scenarios for `test_alpha_math.py`.

Separate from the recorded yfinance fixtures (`prices/*.csv`) because
these scenarios target edge cases — holiday gaps, splits, missing price
days — that real data rarely stages cleanly. Decoupling them from the
recorded fixtures also means yfinance re-records don't invalidate
edge-case assertions.

Each scenario is a `dict` that `test_alpha_math.py` consumes via
`pytest.mark.parametrize`. Every scenario carries:

  * `trade_date` + `publication_date`        — the two date anchors
  * `ticker_prices` + `benchmark_prices`     — sparse (date, close) pairs
  * `horizon_bdays`                          — forward hold length
  * `expected_alpha_approx`                  — trade-date alpha
                                               (historically the only
                                               key; retained as the
                                               trade-date reference)
  * `expected_alpha_post_file_approx`        — post-file alpha, per
                                               ROADMAP #4's design note:
                                               entry =
                                               max(txDate, published)
                                               + 2 business days, then
                                               `_next_close_at_or_after`
                                               forward-fill.

Scenario 3 (POSTFILE_DIVERGENCE) additionally keeps
`expected_alpha_trade_date_approx` as a legacy alias from when post-file
alpha was prototyped in ROADMAP #2. Both keys carry the same value.

All prices are `(date, close)` tuples in ascending-date order. Dates
are business days except where a scenario deliberately spans a holiday
gap (Good Friday, Juneteenth, Memorial Day, Presidents Day).
"""

from __future__ import annotations

from datetime import date


# ─── Scenario 1: clean 5-day hold, no gaps ───────────────────────────
#
# Member buys at 100 on 2024-03-04; the stock closes at 105 five
# business days later (trade-date window). Publication lands 2024-03-18
# (Mon); post-file entry = 2024-03-18 + 2 bdays = 2024-03-20 (Wed). The
# price retraces to 100 by 3/20 and rallies back to 105 by the 5-bday
# post-file exit (2024-03-27), so both trade-date and post-file alpha
# come out to +5% — the scenario validates the mechanic, not a gap.
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
        (date(2024, 3, 11), 105.0),  # D+5 business day (trade-date exit)
        (date(2024, 3, 12), 104.0),
        (date(2024, 3, 13), 103.0),
        (date(2024, 3, 14), 102.0),
        (date(2024, 3, 15), 101.0),
        (date(2024, 3, 18), 100.0),  # publication date
        (date(2024, 3, 19), 100.0),
        (date(2024, 3, 20), 100.0),  # post-file entry (pub + 2 bdays)
        (date(2024, 3, 21), 101.0),
        (date(2024, 3, 22), 102.0),
        (date(2024, 3, 25), 103.0),
        (date(2024, 3, 26), 104.0),
        (date(2024, 3, 27), 105.0),  # post-file exit (entry + 5 bdays)
    ],
    "benchmark_prices": [
        (date(2024, 3, 4), 500.0),
        (date(2024, 3, 5), 500.0),
        (date(2024, 3, 6), 500.0),
        (date(2024, 3, 7), 500.0),
        (date(2024, 3, 8), 500.0),
        (date(2024, 3, 11), 500.0),
        (date(2024, 3, 12), 500.0),
        (date(2024, 3, 13), 500.0),
        (date(2024, 3, 14), 500.0),
        (date(2024, 3, 15), 500.0),
        (date(2024, 3, 18), 500.0),
        (date(2024, 3, 19), 500.0),
        (date(2024, 3, 20), 500.0),
        (date(2024, 3, 21), 500.0),
        (date(2024, 3, 22), 500.0),
        (date(2024, 3, 25), 500.0),
        (date(2024, 3, 26), 500.0),
        (date(2024, 3, 27), 500.0),
    ],
    "horizon_bdays": 5,
    "expected_alpha_approx": 0.05,            # trade-date: +5%
    "expected_alpha_post_file_approx": 0.05,  # post-file: +5%
}


# ─── Scenario 2: Good Friday holiday gap ─────────────────────────────
#
# Member buys Wednesday before a Good Friday close. Trade-date exit
# five business days later skips Good Friday (2024-03-29) and the
# weekend. Publication lands 2024-04-10 (Wed); post-file entry =
# 2024-04-10 + 2 bdays = 2024-04-12 (Fri), +5 bdays exit = 2024-04-19.
# Tests that the alpha math counts business days, not calendar days,
# across a holiday on both windows.
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
        (date(2024, 4, 4), 210.0),   # trade-date D+5 exit
        (date(2024, 4, 5), 210.0),
        (date(2024, 4, 8), 210.0),
        (date(2024, 4, 9), 210.0),
        (date(2024, 4, 10), 210.0),  # publication date
        (date(2024, 4, 11), 210.0),
        (date(2024, 4, 12), 210.0),  # post-file entry (pub + 2 bdays)
        (date(2024, 4, 15), 212.1),
        (date(2024, 4, 16), 214.2),
        (date(2024, 4, 17), 216.3),
        (date(2024, 4, 18), 218.4),
        (date(2024, 4, 19), 220.5),  # post-file exit (entry + 5 bdays)
    ],
    "benchmark_prices": [
        (date(2024, 3, 27), 500.0),
        (date(2024, 3, 28), 500.0),
        (date(2024, 4, 1), 500.0),
        (date(2024, 4, 2), 500.0),
        (date(2024, 4, 3), 500.0),
        (date(2024, 4, 4), 500.0),
        (date(2024, 4, 5), 500.0),
        (date(2024, 4, 8), 500.0),
        (date(2024, 4, 9), 500.0),
        (date(2024, 4, 10), 500.0),
        (date(2024, 4, 11), 500.0),
        (date(2024, 4, 12), 500.0),
        (date(2024, 4, 15), 500.0),
        (date(2024, 4, 16), 500.0),
        (date(2024, 4, 17), 500.0),
        (date(2024, 4, 18), 500.0),
        (date(2024, 4, 19), 500.0),
    ],
    "horizon_bdays": 5,
    "expected_alpha_approx": 0.05,            # trade-date: +5%
    "expected_alpha_post_file_approx": 0.05,  # post-file:  +5%
}


# ─── Scenario 3: post-file entry materially different from trade-date ─
#
# Member trades on 2024-01-03 at 100. Publishes on 2024-02-15
# (well past the disclosure median). By publication the stock has
# already rallied to 120 — trade-date alpha is strong but post-file
# alpha is flat. Validates that `compute_trade_alpha_postfile` enters
# at max(txDate, published) + 2 business days (forward-filling across
# Presidents Day 2024-02-19 to 2024-02-20), not from trade date.
POSTFILE_DIVERGENCE = {
    "name": "postfile_entry_misses_runup",
    "trade_date": date(2024, 1, 3),
    "publication_date": date(2024, 2, 15),
    "ticker_prices": [
        (date(2024, 1, 3), 100.0),
        (date(2024, 2, 15), 120.0),
        (date(2024, 2, 16), 121.0),
        (date(2024, 2, 20), 120.5),  # post-presidents-day; post-file entry
        (date(2024, 2, 21), 121.0),
        (date(2024, 2, 22), 120.5),  # trade-date D+5 exit (by index)
        (date(2024, 2, 23), 120.0),
        (date(2024, 2, 26), 120.0),
        (date(2024, 2, 27), 120.5),  # post-file exit (entry + 5 bdays)
    ],
    "benchmark_prices": [
        (date(2024, 1, 3), 500.0),
        (date(2024, 2, 15), 500.0),
        (date(2024, 2, 16), 500.0),
        (date(2024, 2, 20), 500.0),
        (date(2024, 2, 21), 500.0),
        (date(2024, 2, 22), 500.0),
        (date(2024, 2, 23), 500.0),
        (date(2024, 2, 26), 500.0),
        (date(2024, 2, 27), 500.0),
    ],
    "horizon_bdays": 5,
    "expected_alpha_approx": 0.205,                # trade-date: 100→120.5 (5 positions fwd)
    "expected_alpha_trade_date_approx": 0.205,     # legacy alias
    "expected_alpha_post_file_approx": 0.0,        # post-file: 120.5→120.5
}


# ─── Scenario 4: 2-for-1 split between entry and exit ────────────────
#
# yfinance typically adjusts splits, but this scenario verifies the
# math assumes split-adjusted input and does not double-count. Both
# ticker and benchmark series are already split-adjusted.
#
# Publication 2024-06-17 (Mon); post-file entry = 6/17 + 2 bdays =
# 2024-06-19. Juneteenth 2024-06-19 is a NYSE holiday, so the entry
# forward-fills to 2024-06-20 (Thu). +5 bdays exit lands on 2024-06-27.
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
        (date(2024, 6, 10), 52.5),  # trade-date D+5 exit
        (date(2024, 6, 11), 53.0),
        (date(2024, 6, 12), 53.5),
        (date(2024, 6, 13), 54.0),
        (date(2024, 6, 14), 54.5),
        (date(2024, 6, 17), 55.0),  # publication
        (date(2024, 6, 18), 55.0),
        # 2024-06-19 is Juneteenth — NYSE closed, entry forward-fills
        (date(2024, 6, 20), 55.0),  # post-file entry (forward-filled)
        (date(2024, 6, 21), 55.55),
        (date(2024, 6, 24), 56.1),
        (date(2024, 6, 25), 56.65),
        (date(2024, 6, 26), 57.2),
        (date(2024, 6, 27), 57.75),  # post-file exit (entry + 5 bdays)
    ],
    "benchmark_prices": [
        (date(2024, 6, 3), 500.0),
        (date(2024, 6, 4), 500.0),
        (date(2024, 6, 5), 500.0),
        (date(2024, 6, 6), 500.0),
        (date(2024, 6, 7), 500.0),
        (date(2024, 6, 10), 500.0),
        (date(2024, 6, 11), 500.0),
        (date(2024, 6, 12), 500.0),
        (date(2024, 6, 13), 500.0),
        (date(2024, 6, 14), 500.0),
        (date(2024, 6, 17), 500.0),
        (date(2024, 6, 18), 500.0),
        (date(2024, 6, 20), 500.0),
        (date(2024, 6, 21), 500.0),
        (date(2024, 6, 24), 500.0),
        (date(2024, 6, 25), 500.0),
        (date(2024, 6, 26), 500.0),
        (date(2024, 6, 27), 500.0),
    ],
    "horizon_bdays": 5,
    "expected_alpha_approx": 0.05,
    "expected_alpha_post_file_approx": 0.05,
}


# ─── Scenario 5: trade date missing from cache — entry forward-fills ──
#
# Original draft of this scenario tried to exercise an *exit-side*
# forward-fill, but `factors.py` doesn't implement one: it picks the
# exit by integer index into the price DataFrame, so a missing row
# doesn't behave as "skip forward one calendar day" — it behaves as
# "shift the target forward by one row." The behavior the code *does*
# implement is entry-side forward-fill via `_next_close_at_or_after`:
# if the trade date has no row, entry resolves to the first available
# close on or after that date. This scenario exercises that path on
# both the trade-date and post-file entries (publication 2024-05-22
# Wed → post-file entry target 2024-05-24 Fri, present in prices).
ENTRY_DAY_MISSING_FORWARD_FILLS = {
    "name": "entry_day_missing_forward_fills",
    "trade_date": date(2024, 5, 8),        # no row on this date
    "publication_date": date(2024, 5, 22),
    "ticker_prices": [
        (date(2024, 5, 7), 76.0),
        # 2024-05-08 missing entirely → trade-date entry forward-fills to 5/9
        (date(2024, 5, 9), 77.0),          # trade-date entry idx = 1
        (date(2024, 5, 10), 78.0),
        (date(2024, 5, 13), 79.0),
        (date(2024, 5, 14), 79.5),
        (date(2024, 5, 15), 80.0),
        (date(2024, 5, 16), 80.85),        # trade-date exit (idx 1 + 5 = 6)
        (date(2024, 5, 17), 81.5),
        (date(2024, 5, 20), 82.0),
        (date(2024, 5, 21), 82.5),
        (date(2024, 5, 22), 83.0),         # publication
        (date(2024, 5, 23), 84.0),
        (date(2024, 5, 24), 85.0),         # post-file entry (pub + 2 bdays)
        # 2024-05-27 Memorial Day — NYSE closed, exit indexing skips it
        (date(2024, 5, 28), 85.85),
        (date(2024, 5, 29), 86.7),
        (date(2024, 5, 30), 87.55),
        (date(2024, 5, 31), 88.4),
        (date(2024, 6, 3), 89.25),         # post-file exit (entry + 5 bdays)
    ],
    "benchmark_prices": [
        (date(2024, 5, 7), 500.0),
        (date(2024, 5, 9), 500.0),
        (date(2024, 5, 10), 500.0),
        (date(2024, 5, 13), 500.0),
        (date(2024, 5, 14), 500.0),
        (date(2024, 5, 15), 500.0),
        (date(2024, 5, 16), 500.0),
        (date(2024, 5, 17), 500.0),
        (date(2024, 5, 20), 500.0),
        (date(2024, 5, 21), 500.0),
        (date(2024, 5, 22), 500.0),
        (date(2024, 5, 23), 500.0),
        (date(2024, 5, 24), 500.0),
        (date(2024, 5, 28), 500.0),
        (date(2024, 5, 29), 500.0),
        (date(2024, 5, 30), 500.0),
        (date(2024, 5, 31), 500.0),
        (date(2024, 6, 3), 500.0),
    ],
    "horizon_bdays": 5,
    "expected_alpha_approx": 0.05,            # trade-date: 77 → 80.85 = +5.0%
    "expected_alpha_post_file_approx": 0.05,  # post-file:  85 → 89.25 = +5.0%
}


ALL_SCENARIOS = [
    CLEAN_5D_BUY,
    HOLIDAY_GAP_5D_BUY,
    POSTFILE_DIVERGENCE,
    SPLIT_ADJUSTED_HOLD,
    ENTRY_DAY_MISSING_FORWARD_FILLS,
]
