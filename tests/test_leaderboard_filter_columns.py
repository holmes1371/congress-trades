"""
Schema-contract tests for the leaderboard filter + post-file columns.

Covers three seams:

1. `build_table_rows` — the per-row HTML. Filter cells from ROADMAP #3
   (non_self_share, late_share, etf_drops, options_drops) and the
   post-file disclosure-drag cell from ROADMAP #4
   (disclosure_drag_20d). Em-dash fallback for missing values on
   pre-#3 / pre-#4 xlsx files.
2. `PAGE_TEMPLATE.format(...)` — column headers appear in both the
   365d and 180d table sections: four ROADMAP #3 filter headers plus
   the ROADMAP #4 "Drag 20d" header.
3. Footer text — references post-file alpha explicitly, so a reader
   understands the composite's entry rule without opening the code.

No xlsx parsing, no live scoring run — pure string assertions on
rendered HTML. Inputs are canned row dicts; the rendered shape is
what future refactors must preserve.
"""

from __future__ import annotations

from build_leaderboard import PAGE_TEMPLATE, build_table_rows


_FULL_ROW = {
    "rank_long": 1,
    "fullName": "Jane Doe",
    "party": "Democrat",
    "chamber": "Senate",
    "state": "NY",
    "composite": 0.456,
    "trade_count": 20,
    "buy_count": 15,
    "sell_count": 5,
    "mean_alpha_20d": 0.03,             # post-file primary (ROADMAP #4)
    "hit_rate": 0.60,
    "sharpe_alpha": 1.2,
    "disclosure_drag_20d": -0.018,      # post-file − trade-date mean α
    "mean_lag_days": 12.5,
    "liq_pass_rate": 0.85,
    "non_self_share": 0.25,
    "late_share": 0.10,
    "etf_drops": 3,
    "options_drops": 1,
    "divergence_flag": "",
}


# ── build_table_rows contract ──


def test_row_renders_four_filter_cells_with_expected_shapes():
    html = build_table_rows([_FULL_ROW])
    assert "25.0%" in html   # non_self_share via fmt_pct
    assert "10.0%" in html   # late_share via fmt_pct
    assert ">3<" in html     # etf_drops cell
    assert ">1<" in html     # options_drops cell


def test_row_renders_em_dash_for_none_shares():
    row = {**_FULL_ROW, "non_self_share": None, "late_share": None}
    html = build_table_rows([row])
    # At minimum two em-dashes (one per None share cell); others may
    # appear if upstream alpha/hit/etc are also None, but this row
    # has those populated.
    assert html.count("—") >= 2


def test_row_handles_missing_filter_columns_pre_roadmap_3_xlsx():
    """Pre-#3 xlsx files won't carry the new columns at all; row still
    renders cleanly — shares fall back to '—' via fmt_pct(None), drop
    counts fall back to 0."""
    row = {k: v for k, v in _FULL_ROW.items()
           if k not in {"non_self_share", "late_share", "etf_drops", "options_drops"}}
    html = build_table_rows([row])
    assert "Jane Doe" in html       # row rendered at all
    assert html.count("—") >= 2     # missing shares fall back to em-dash
    assert ">0<" in html            # missing drop counts fall back to 0


def test_row_renders_disclosure_drag_cell():
    """disclosure_drag_20d (ROADMAP #4) renders as fmt_pct in its own cell."""
    html = build_table_rows([_FULL_ROW])
    assert "-1.8%" in html   # disclosure_drag_20d = -0.018 via fmt_pct


def test_row_handles_missing_disclosure_drag_pre_roadmap_4_xlsx():
    """Pre-#4 xlsx files won't carry disclosure_drag_20d; row still
    renders cleanly — the drag cell falls back to '—'."""
    row = {k: v for k, v in _FULL_ROW.items() if k != "disclosure_drag_20d"}
    html = build_table_rows([row])
    assert "Jane Doe" in html
    # Em-dash count rises by at least 1 vs the full-row case because the
    # drag cell now falls back; assert the row renders without error and
    # that no raw 'None' leaks into the HTML.
    assert "None" not in html


# ── PAGE_TEMPLATE integration ──


_MINIMAL_FORMAT_KWARGS = {
    "data_date": "Jan 1, 2026",
    "weights_html": "<ul></ul>",
    "benchmark_block": "",
    "long_rows": "",
    "short_rows": "",
    "build_time": "Jan 1, 2026 at 12:00 PM",
}


def test_page_headers_include_four_filter_columns_twice():
    """Both 365d and 180d table sections must carry the four new headers."""
    html = PAGE_TEMPLATE.format(**_MINIMAL_FORMAT_KWARGS)
    # One occurrence per window = 2 total. Substrings are specific enough
    # to not collide with tooltip text or other page content.
    assert html.count("Non-self") == 2
    assert html.count(">Late<") == 2
    assert html.count("ETF drops") == 2
    assert html.count("Opt drops") == 2


def test_page_headers_include_drag_column_twice():
    """ROADMAP #4: disclosure drag header appears in both 365d and 180d sections."""
    html = PAGE_TEMPLATE.format(**_MINIMAL_FORMAT_KWARGS)
    assert html.count(">Drag 20d<") == 2


def test_footer_documents_post_file_entry_rule():
    """Footer text must reference post-file semantics so a reader
    understands what Mean α 20d means without opening the code."""
    html = PAGE_TEMPLATE.format(**_MINIMAL_FORMAT_KWARGS)
    assert "post-file" in html
    assert "disclosure lag" in html.lower()
