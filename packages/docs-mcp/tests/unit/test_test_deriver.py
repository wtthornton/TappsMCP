"""Tests for docs_mcp.generators.test_deriver -- Test name derivation from ACs.

Covers derive_test_names and _criterion_to_test_name: prefix stripping,
snake_case conversion, truncation, deduplication, and special characters.
"""

from __future__ import annotations

from docs_mcp.generators.test_deriver import _criterion_to_test_name, derive_test_names


# ---------------------------------------------------------------------------
# derive_test_names
# ---------------------------------------------------------------------------


class TestDeriveTestNames:
    """Tests for derive_test_names."""

    def test_derive_from_simple_ac(self) -> None:
        result = derive_test_names(["User can log in"])
        assert result == ["test_user_can_log_in"]

    def test_derive_strips_ac_prefix(self) -> None:
        result = derive_test_names(["AC1: Validates email format"])
        assert result == ["test_validates_email_format"]

    def test_derive_strips_numbered_prefix(self) -> None:
        result = derive_test_names(["1. Feature works"])
        assert result == ["test_feature_works"]

    def test_derive_strips_checkbox(self) -> None:
        result = derive_test_names(["- [ ] Settings page loads"])
        assert result == ["test_settings_page_loads"]

    def test_derive_truncates_long_names(self) -> None:
        long_ac = "This is an extremely long acceptance criterion that should be truncated"
        result = derive_test_names([long_ac])
        assert len(result) == 1
        assert len(result[0]) <= 60

    def test_derive_deduplicates(self) -> None:
        result = derive_test_names(["Foo works", "Foo works"])
        assert result[0] == "test_foo_works"
        assert result[1] == "test_foo_works_2"

    def test_derive_empty_list(self) -> None:
        result = derive_test_names([])
        assert result == []

    def test_derive_multiple_acs(self) -> None:
        result = derive_test_names(["Login works", "Logout works", "Profile loads"])
        assert len(result) == 3

    def test_derive_special_chars_removed(self) -> None:
        result = derive_test_names(["Feature (v2)!"])
        assert len(result) == 1
        assert "(" not in result[0]
        assert ")" not in result[0]
        assert "!" not in result[0]


# ---------------------------------------------------------------------------
# _criterion_to_test_name
# ---------------------------------------------------------------------------


class TestCriterionToTestName:
    """Tests for _criterion_to_test_name."""

    def test_criterion_to_name_empty(self) -> None:
        assert _criterion_to_test_name("") == ""

    def test_no_trailing_underscore(self) -> None:
        # Build an AC long enough to trigger truncation at an underscore boundary.
        long_ac = "a " * 40  # produces "a_a_a_..." which may truncate at "_"
        name = _criterion_to_test_name(long_ac)
        if name:
            assert not name.endswith("_")
