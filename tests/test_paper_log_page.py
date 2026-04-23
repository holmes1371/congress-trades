"""
Schema-contract tests for `build_paper_log` (ROADMAP #6).

Covers four seams:

  1. Row builders (`build_open_rows`, `build_closed_rows`,
     `build_retracted_rows`) — cell shapes, em-dash fallbacks, empty
     states, green/red PnL classes.
  2. Summary card (`build_summary_card`) — every metric row present;
     em-dash when no closed positions yet.
  3. `render_page` end-to-end — page title, section titles, breadcrumb
     nav to leaderboard + index, footer timestamp in ET.
  4. `lifetime_summary` arithmetic — averages, hit rate.

No test exercises the CLI (argparse, file I/O path resolution) — that's
the realm of commit 5 (pipeline wiring) and is covered there.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from build_paper_log import (
    build_closed_rows,
    build_open_rows,
    build_retracted_rows,
    build_retracted_section,
    build_summary_card,
    lifetime_summary,
    render_page,
)
from scoring.paper_log import PaperLog


_NOW = datetime(2024, 1, 15, 12, 0, 0)
_TODAY = date(2024, 3, 15)
_NAME_LOOKUP = {"M0": "Alice Anderson", "M1": "Bob Brown"}


# ── Helpers ────────────────────────────────────────────────


def _log_with_rows(tmp_path, rows):
    log = PaperLog(tmp_path / "log.csv")
    log.rows = rows
    return log


def _open_row(**overrides):
    defaults = {
        "position_id":      "M0-1",
        "bioguide":         "M0",
        "tx_id":            "1",
        "ticker":           "AAPL",
        "signal_date":      "2024-01-02",
        "open_date":        "2024-01-05",
        "entry_date":       "2024-01-08",
        "entry_close":      "150.0000",
        "target_exit_date": "2024-04-01",
        "exit_date":        "",
        "exit_close":       "",
        "status":           "open",
        "pnl_abs":          "8.0000",
        "pnl_pct":          "0.053333",   # +5.33%
        "alpha_vs_spy":     "",
        "retracted_at":     "",
        "last_updated":     "2024-03-15T12:00:00",
    }
    defaults.update(overrides)
    return defaults


def _closed_row(**overrides):
    defaults = {
        "position_id":      "M1-2",
        "bioguide":         "M1",
        "tx_id":            "2",
        "ticker":           "NVDA",
        "signal_date":      "2023-12-01",
        "open_date":        "2023-12-04",
        "entry_date":       "2023-12-05",
        "entry_close":      "500.0000",
        "target_exit_date": "2024-03-01",
        "exit_date":        "2024-03-01",
        "exit_close":       "550.0000",
        "status":           "closed",
        "pnl_abs":          "50.0000",
        "pnl_pct":          "0.100000",   # +10%
        "alpha_vs_spy":     "0.080000",   # +8% alpha
        "retracted_at":     "",
        "last_updated":     "2024-03-01T12:00:00",
    }
    defaults.update(overrides)
    return defaults


def _retracted_row(**overrides):
    defaults = {
        "position_id":      "M0-99",
        "bioguide":         "M0",
        "tx_id":            "99",
        "ticker":           "RETRACTED",
        "signal_date":      "2024-02-01",
        "open_date":        "2024-02-03",
        "entry_date":       "2024-02-05",
        "entry_close":      "100.0000",
        "target_exit_date": "2024-05-01",
        "exit_date":        "",
        "exit_close":       "",
        "status":           "retracted",
        "pnl_abs":          "-2.0000",
        "pnl_pct":          "-0.020000",
        "alpha_vs_spy":     "",
        "retracted_at":     "2024-03-10",
        "last_updated":     "2024-03-10T12:00:00",
    }
    defaults.update(overrides)
    return defaults


# ── Open-positions row builder ─────────────────────────────


def test_build_open_rows_emits_cells_with_expected_shapes(tmp_path):
    log = _log_with_rows(tmp_path, [_open_row()])
    html = build_open_rows(log, _TODAY, _NAME_LOOKUP)
    assert "Alice Anderson" in html              # fullName resolved via lookup
    assert "AAPL" in html
    assert "$150.00" in html                      # fmt_money on entry_close
    assert "+5.33%" in html                       # fmt_signed_pct on pnl_pct
    assert "class='green'" in html                # positive PnL → green class
    # Days held: 2024-01-08 → 2024-03-15 = 67 calendar days
    assert ">67d<" in html


def test_build_open_rows_empty_state(tmp_path):
    log = _log_with_rows(tmp_path, [])
    html = build_open_rows(log, _TODAY, _NAME_LOOKUP)
    assert "No open positions" in html
    assert 'colspan="6"' in html                  # matches header count


def test_build_open_rows_falls_back_to_bioguide_when_name_missing(tmp_path):
    log = _log_with_rows(tmp_path, [_open_row(bioguide="UNKNOWN")])
    html = build_open_rows(log, _TODAY, _NAME_LOOKUP)
    # UNKNOWN is not in _NAME_LOOKUP → display_name returns the bioguide.
    assert "UNKNOWN" in html


def test_build_open_rows_negative_pnl_gets_red_class(tmp_path):
    log = _log_with_rows(tmp_path, [_open_row(pnl_pct="-0.025000", pnl_abs="-3.7500")])
    html = build_open_rows(log, _TODAY, _NAME_LOOKUP)
    assert "-2.50%" in html
    assert "class='red'" in html


# ── Closed-positions row builder ───────────────────────────


def test_build_closed_rows_renders_eight_cells(tmp_path):
    log = _log_with_rows(tmp_path, [_closed_row()])
    html = build_closed_rows(log, _TODAY, _NAME_LOOKUP)
    assert "Bob Brown" in html
    assert "NVDA" in html
    assert "$500.00" in html and "$550.00" in html
    assert "+10.00%" in html                      # return
    assert "+8.00%" in html                       # alpha_vs_spy


def test_build_closed_rows_filters_to_recent_window(tmp_path):
    old = _closed_row(exit_date="2023-01-01")     # way outside 30-day window
    recent = _closed_row(
        position_id="M1-5", tx_id="5",
        bioguide="M1", ticker="MSFT",
        exit_date="2024-03-10", pnl_pct="0.050000",
    )
    log = _log_with_rows(tmp_path, [old, recent])
    html = build_closed_rows(log, _TODAY, _NAME_LOOKUP, days_window=30)
    assert "MSFT" in html                         # within window
    # Old row excluded — the NVDA ticker from _closed_row(old)
    # should NOT appear. Assert by looking for its exit_date explicitly.
    assert "2023-01-01" not in html


def test_build_closed_rows_empty_state(tmp_path):
    log = _log_with_rows(tmp_path, [])
    html = build_closed_rows(log, _TODAY, _NAME_LOOKUP)
    assert "No closed positions" in html
    assert 'colspan="8"' in html                  # matches header count


# ── Retracted-section wrapper ──────────────────────────────


def test_build_retracted_section_empty_when_no_retractions(tmp_path):
    log = _log_with_rows(tmp_path, [_open_row(), _closed_row()])
    assert build_retracted_section(log, _NAME_LOOKUP) == ""


def test_build_retracted_section_renders_when_rows_present(tmp_path):
    log = _log_with_rows(tmp_path, [_retracted_row()])
    html = build_retracted_section(log, _NAME_LOOKUP)
    assert "Retracted Disclosures" in html
    assert "RETRACTED" in html                    # ticker
    assert "2024-03-10" in html                   # retracted_at


# ── Lifetime summary ───────────────────────────────────────


def test_lifetime_summary_on_empty_log(tmp_path):
    log = _log_with_rows(tmp_path, [])
    s = lifetime_summary(log)
    assert s["n_closed"] == 0
    assert s["n_open"] == 0
    assert s["n_retracted"] == 0
    assert s["mean_return"] is None
    assert s["mean_alpha_vs_spy"] is None
    assert s["hit_rate"] is None


def test_lifetime_summary_aggregates_closed(tmp_path):
    log = _log_with_rows(tmp_path, [
        _closed_row(position_id="A", tx_id="1", pnl_pct="0.100000", alpha_vs_spy="0.080000"),
        _closed_row(position_id="B", tx_id="2", pnl_pct="0.020000", alpha_vs_spy="-0.010000"),
        _closed_row(position_id="C", tx_id="3", pnl_pct="0.060000", alpha_vs_spy="0.040000"),
    ])
    s = lifetime_summary(log)
    assert s["n_closed"] == 3
    assert s["mean_return"] == pytest.approx(0.06, abs=1e-6)    # (0.1 + 0.02 + 0.06) / 3
    assert s["mean_alpha_vs_spy"] == pytest.approx(0.0366666, abs=1e-5)  # (0.08 - 0.01 + 0.04) / 3
    assert s["hit_rate"] == pytest.approx(2 / 3, abs=1e-6)       # 2 of 3 alphas > 0


def test_build_summary_card_lists_every_metric(tmp_path):
    log = _log_with_rows(tmp_path, [
        _open_row(),
        _closed_row(pnl_pct="0.100000", alpha_vs_spy="0.080000"),
    ])
    html = build_summary_card(log)
    assert "Open positions" in html
    assert "Closed positions" in html
    assert "Retracted" in html
    assert "Mean per-trade return" in html
    assert "Mean per-trade &alpha; vs SPY" in html
    assert "Hit rate" in html
    # Concrete values surface.
    assert "Open positions:</strong> 1</li>" in html  # n_open == 1
    assert "Closed positions:</strong> 1</li>" in html
    assert "+10.00%" in html                      # mean_return


# ── render_page integration ────────────────────────────────


def test_render_page_includes_section_titles(tmp_path):
    log = _log_with_rows(tmp_path, [_open_row(), _closed_row()])
    html = render_page(log, _TODAY, _NAME_LOOKUP)
    assert "Auto Paper-Trading Log" in html       # <h1>
    assert "Open Positions" in html               # section-title
    assert "Recently Closed" in html              # section-title


def test_render_page_breadcrumb_links_to_index_and_leaderboard(tmp_path):
    log = _log_with_rows(tmp_path, [])
    html = render_page(log, _TODAY, _NAME_LOOKUP)
    assert 'href="index.html"' in html
    assert 'href="leaderboard.html"' in html


def test_render_page_footer_includes_et_timestamp(tmp_path):
    log = _log_with_rows(tmp_path, [])
    html = render_page(log, _TODAY, _NAME_LOOKUP)
    assert "Last built:" in html
    assert "ET" in html.split("Last built:")[1][:100]


def test_render_page_hides_retracted_section_when_empty(tmp_path):
    log = _log_with_rows(tmp_path, [_open_row()])
    html = render_page(log, _TODAY, _NAME_LOOKUP)
    assert "Retracted Disclosures" not in html


def test_render_page_shows_retracted_section_when_rows_present(tmp_path):
    log = _log_with_rows(tmp_path, [_open_row(), _retracted_row()])
    html = render_page(log, _TODAY, _NAME_LOOKUP)
    assert "Retracted Disclosures" in html


def test_render_page_data_date_matches_today(tmp_path):
    log = _log_with_rows(tmp_path, [])
    html = render_page(log, _TODAY, _NAME_LOOKUP)
    assert "Mar 15, 2024" in html                 # fmt of _TODAY
