"""
Schema-contract tests for the recorded capitoltrades fixture.

`tests/fixtures/capitoltrades_page_sample.json` is the on-disk shape that
downstream scoring code (`scoring.score_members`, `scoring.factors`) sees
after `fetch_trades` has normalized the scraper's raw RSC rows. These
tests pin the contract between fetch and scoring:

  * Envelope keys — `fetched_at`, `window_days`, `data`.
  * Per-member keys — bioguideId, trades, tradeCount, and the biographic
    block score_members reads for attribution.
  * Per-trade keys — the 13 columns scoring iterates over.
  * Type domain of `type` — downstream filters BUY vs SELL explicitly.
  * ISO date parseability of `txDate` and `published` — alpha math and
    lag-days calculations parse these via `date.fromisoformat`.

What these tests deliberately do *not* pin: specific tickers, specific
prices, specific trade counts, specific members. When `fetch_trades` is
re-recorded (ROADMAP item #4), fixture data will change; these tests
must still pass as long as the schema contract holds.
"""

from __future__ import annotations

from datetime import date


# ─── Envelope ──────────────────────────────────────────────────

def test_envelope_keys_present(capitoltrades_page_sample):
    env = capitoltrades_page_sample
    for key in ("fetched_at", "window_days", "data"):
        assert key in env, f"envelope missing required key {key!r}"


def test_envelope_window_days_is_positive_int(capitoltrades_page_sample):
    w = capitoltrades_page_sample["window_days"]
    assert isinstance(w, int) and w > 0


# ─── Member block ──────────────────────────────────────────────

REQUIRED_MEMBER_KEYS = {
    "bioguideId",
    "fullName",
    "firstName",
    "lastName",
    "chamber",
    "state",
    "party",
    "tradeCount",
    "trades",
}


def test_member_block_keys_present(capitoltrades_page_sample):
    member = capitoltrades_page_sample["data"]
    missing = REQUIRED_MEMBER_KEYS - set(member.keys())
    assert not missing, f"member block missing required keys: {missing}"


def test_tradecount_matches_trades_length(capitoltrades_page_sample):
    # Header says N trades; payload must actually contain N. If fetch_trades
    # ever paginates wrong, this mismatch is the cheapest symptom to catch.
    member = capitoltrades_page_sample["data"]
    assert member["tradeCount"] == len(member["trades"])


def test_member_bioguide_id_is_string(capitoltrades_page_sample):
    bid = capitoltrades_page_sample["data"]["bioguideId"]
    assert isinstance(bid, str) and bid


# ─── Per-trade schema ─────────────────────────────────────────

REQUIRED_TRADE_KEYS = {
    "txId",
    "company",
    "ticker",
    "sector",
    "txDate",
    "published",
    "filedAfterDays",
    "type",
    "typeExtended",
    "value",
    "price",
    "owner",
    "comment",
}


def test_every_trade_has_required_keys(capitoltrades_page_sample):
    trades = capitoltrades_page_sample["data"]["trades"]
    assert trades, "fixture contains no trades to validate"
    for i, t in enumerate(trades):
        missing = REQUIRED_TRADE_KEYS - set(t.keys())
        assert not missing, f"trade[{i}] missing keys: {missing}"


def test_type_values_are_buy_or_sell(capitoltrades_page_sample):
    # Downstream `scoring.score_members` filters trades by
    # `t["type"] == "BUY"` directly; a drift into lowercase or unexpected
    # tags (e.g. "EXCHANGE") would silently zero a member's trade count.
    trades = capitoltrades_page_sample["data"]["trades"]
    for i, t in enumerate(trades):
        assert t["type"] in {"BUY", "SELL"}, (
            f"trade[{i}] has unexpected type {t['type']!r}"
        )


def test_tx_date_is_iso_parseable(capitoltrades_page_sample):
    # `compute_trade_alpha` does `date.fromisoformat(trade["txDate"])`; any
    # format drift (timestamp suffix, timezone) would break alpha wholesale.
    trades = capitoltrades_page_sample["data"]["trades"]
    for i, t in enumerate(trades):
        try:
            date.fromisoformat(t["txDate"])
        except (TypeError, ValueError) as e:
            raise AssertionError(
                f"trade[{i}].txDate {t['txDate']!r} not ISO parseable: {e}"
            )


def test_published_is_iso_parseable(capitoltrades_page_sample):
    # Lag-days math and post-file alpha parse `published` the same way.
    trades = capitoltrades_page_sample["data"]["trades"]
    for i, t in enumerate(trades):
        try:
            date.fromisoformat(t["published"])
        except (TypeError, ValueError) as e:
            raise AssertionError(
                f"trade[{i}].published {t['published']!r} not ISO parseable: {e}"
            )


def test_ticker_is_nonempty_string(capitoltrades_page_sample):
    # `normalize_ticker` is exercised in its own file; here we just pin
    # that the raw column reaches scoring as a usable string.
    trades = capitoltrades_page_sample["data"]["trades"]
    for i, t in enumerate(trades):
        assert isinstance(t["ticker"], str) and t["ticker"], (
            f"trade[{i}] has empty/non-string ticker {t['ticker']!r}"
        )


def test_owner_is_string(capitoltrades_page_sample):
    # Owner categories (self/spouse/child/joint/dependent) are not
    # enumerated here — the fixture's a 10-row slice and new owner tags
    # could appear in re-records. Pin the type only.
    trades = capitoltrades_page_sample["data"]["trades"]
    for i, t in enumerate(trades):
        assert isinstance(t["owner"], str), (
            f"trade[{i}] has non-string owner {t['owner']!r}"
        )


def test_integer_fields_are_ints(capitoltrades_page_sample):
    # `txId`, `value`, `filedAfterDays` are integer-typed in the scraper's
    # normalized output. Python's JSON decoder will hand back `int` or
    # `float` depending on literal form; downstream `filedAfterDays >= 0`
    # comparisons assume int.
    trades = capitoltrades_page_sample["data"]["trades"]
    for i, t in enumerate(trades):
        for key in ("txId", "value", "filedAfterDays"):
            assert isinstance(t[key], int), (
                f"trade[{i}].{key} is {type(t[key]).__name__}, expected int"
            )
