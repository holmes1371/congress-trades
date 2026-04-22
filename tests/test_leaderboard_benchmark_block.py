"""
Schema-contract tests for the leaderboard benchmark block.

Covers two seams:

1. `build_benchmark_block(long_returns, short_returns)` — the HTML the
   benchmark card emits: all four tickers, fmt_pct-shaped values,
   em-dash for None, both window headers, and the card class.
2. `PAGE_TEMPLATE.format(...)` — the placeholder integration into the
   full page plus the fee-gross footnote in the footer.

No yfinance call, no xlsx parse — pure string assertions on rendered
HTML. Inputs are canned; the rendered shape is what future refactors
must preserve.
"""

from __future__ import annotations

from build_leaderboard import PAGE_TEMPLATE, build_benchmark_block


# ── build_benchmark_block contract ──


_FULL_RETURNS = {"NANC": 0.20, "KRUZ": -0.05, "SPY": 0.10, "QQQ": 0.15}


def test_block_contains_all_four_tickers():
    html = build_benchmark_block(_FULL_RETURNS, _FULL_RETURNS)
    for ticker in ("NANC", "KRUZ", "SPY", "QQQ"):
        assert ticker in html, f"{ticker} missing from benchmark block"


def test_block_renders_fmt_pct_values():
    """fmt_pct turns 0.20 → '20.0%', -0.05 → '-5.0%', etc."""
    html = build_benchmark_block(_FULL_RETURNS, _FULL_RETURNS)
    for expected in ("20.0%", "-5.0%", "10.0%", "15.0%"):
        assert expected in html, f"{expected} missing from benchmark block"


def test_block_renders_em_dash_for_none():
    nones = {"NANC": None, "KRUZ": None, "SPY": None, "QQQ": None}
    html = build_benchmark_block(nones, nones)
    # 4 tickers × 2 windows = 8 em-dashes in the cells.
    assert html.count("—") >= 8


def test_block_has_window_headers():
    html = build_benchmark_block({}, {})
    assert "365d" in html
    assert "180d" in html


def test_block_reuses_weights_card_class():
    """Card reuses the existing .weights-card style (no new CSS required)."""
    html = build_benchmark_block({}, {})
    assert 'class="weights-card"' in html


# ── PAGE_TEMPLATE integration ──


_MINIMAL_FORMAT_KWARGS = {
    "data_date": "Jan 1, 2026",
    "weights_html": "<ul></ul>",
    "benchmark_block": "",
    "long_rows": "",
    "short_rows": "",
    "build_time": "Jan 1, 2026 at 12:00 PM",
}


def test_page_footer_has_fee_gross_footnote():
    html = PAGE_TEMPLATE.format(**_MINIMAL_FORMAT_KWARGS)
    assert "gross of expense ratios" in html.lower()


def test_benchmark_block_sits_above_365d_section():
    """Placeholder must render between the composite-weights card and
    the 365-Day Window section, so the block is the first thing a
    reader sees after scrolling past the weights."""
    marker = '<div class="weights-card"><h3>BENCH_MARKER</h3></div>'
    kwargs = {**_MINIMAL_FORMAT_KWARGS, "benchmark_block": marker}
    html = PAGE_TEMPLATE.format(**kwargs)
    assert "BENCH_MARKER" in html
    assert html.index("BENCH_MARKER") < html.index("365-Day Window"), (
        "benchmark block must render above the 365-Day Window section"
    )
