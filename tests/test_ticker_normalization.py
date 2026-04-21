"""
Tests for `scoring.score_members.normalize_ticker`.

The function is the gateway between capitoltrades' raw ticker strings
(`AAPL:US`, `GSK:LN`, `BMW:GR`, etc.) and yfinance's bare-symbol
expectations. Its rejection rules — foreign-market suffixes, placeholder
strings, non-equity garbage — are settled product behavior; this is a
stable primitive per the design note (`design/pytest-ci-suite.md`).
"""

from __future__ import annotations

import pytest

from scoring.score_members import normalize_ticker


@pytest.mark.parametrize(
    "raw, expected",
    [
        # ── happy paths ─────────────────────────────────────────────
        ("AAPL", "AAPL"),
        ("AAPL:US", "AAPL"),
        ("MSFT:US", "MSFT"),
        # ── foreign-market suffixes are rejected (not remapped) ────
        ("GSK:LN", None),
        ("BMW:GR", None),
        ("7203:JP", None),
        # ── empty / null / non-string ───────────────────────────────
        ("", None),
        (None, None),
        (123, None),
        ("   ", None),
        # ── placeholder values ──────────────────────────────────────
        ("N/A", None),
        ("n/a", None),
        ("--", None),
        ("NONE", None),
        ("none", None),
        # ── normalization (case + whitespace) ──────────────────────
        ("aapl", "AAPL"),
        ("  MSFT  ", "MSFT"),
        ("aapl:us", "AAPL"),
        # ── compound symbols (Berkshire B-share style) preserved ───
        ("BRK.B", "BRK.B"),
        ("BRK-B", "BRK-B"),
        ("BF.B:US", "BF.B"),
        # ── garbage that survives the suffix check is still rejected
        ("$$$", None),
        ("ABC@123", None),
    ],
)
def test_normalize_ticker(raw, expected):
    assert normalize_ticker(raw) == expected
