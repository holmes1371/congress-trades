"""
Schema-contract tests for `build_site.INDEX_HTML` — the landing page's
navigation bar.

Narrow scope: just the nav-link surface. Anything else on the landing
page (archive table, latest-report card, RSS block) is exercised by
the live build step in `.github/workflows/*.yml` rather than here.

ROADMAP #6 adds a Paper-Trading Log nav link; this file pins that
link plus the existing leaderboard and RSS links so a future edit to
the nav row doesn't silently drop any of them.
"""

from __future__ import annotations

from build_site import INDEX_HTML


def test_index_nav_has_leaderboard_link():
    assert 'href="leaderboard.html"' in INDEX_HTML
    assert "Member Leaderboard" in INDEX_HTML


def test_index_nav_has_paper_log_link():
    # ROADMAP #6: paper-trading log is a first-class nav destination
    # alongside the member leaderboard.
    assert 'href="paper_log.html"' in INDEX_HTML
    assert "Paper-Trading Log" in INDEX_HTML


def test_index_nav_has_rss_link():
    assert 'href="rss.xml"' in INDEX_HTML
    assert "RSS Feed" in INDEX_HTML
