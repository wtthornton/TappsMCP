"""Tests for docs_mcp.server_gen_helpers._split_csv (TAP-6495)."""

from __future__ import annotations

from docs_mcp.server_gen_helpers import _split_csv


class TestSplitCsv:
    def test_empty_string_returns_empty_list(self) -> None:
        assert _split_csv("") == []

    def test_single_line_still_splits_on_commas(self) -> None:
        assert _split_csv("Epic 0, Epic 4") == ["Epic 0", "Epic 4"]

    def test_newline_separated_items_are_not_split_on_internal_commas(self) -> None:
        """TAP-6495: an internal comma must not fragment a newline item."""
        value = "a, b, which X owns\nc"
        assert _split_csv(value) == ["a, b, which X owns", "c"]

    def test_non_goals_entry_with_internal_comma_survives_round_trip(self) -> None:
        value = "Support for offline mode, including caching\nMobile app support"
        assert _split_csv(value) == [
            "Support for offline mode, including caching",
            "Mobile app support",
        ]

    def test_blank_lines_are_dropped(self) -> None:
        assert _split_csv("a\n\nb\n") == ["a", "b"]
