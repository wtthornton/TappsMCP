"""Tests for docs_mcp.generators.invest_assessor -- INVEST checklist assessment.

Covers assess_invest auto-assessment of Independent, Negotiable, Valuable,
Estimable, Small, and Testable from StoryConfig signals.
"""

from __future__ import annotations

from docs_mcp.generators.invest_assessor import assess_invest
from docs_mcp.generators.stories import StoryConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**kwargs: object) -> StoryConfig:
    """Build a StoryConfig with sensible defaults, overriding with kwargs."""
    defaults: dict[str, object] = {
        "title": "Test Story",
        "dependencies": [],
        "so_that": "",
        "points": 0,
        "size": "",
        "acceptance_criteria": [],
        "test_cases": [],
    }
    defaults.update(kwargs)
    return StoryConfig(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Independent
# ---------------------------------------------------------------------------


class TestIndependent:
    """Tests for the Independent criterion."""

    def test_independent_no_deps(self) -> None:
        config = _make_config(dependencies=[])
        result = assess_invest(config)
        assert result["Independent"] is True

    def test_independent_has_deps(self) -> None:
        config = _make_config(dependencies=["Story 1"])
        result = assess_invest(config)
        assert result["Independent"] is False


# ---------------------------------------------------------------------------
# Negotiable
# ---------------------------------------------------------------------------


class TestNegotiable:
    """Tests for the Negotiable criterion."""

    def test_negotiable_always_false(self) -> None:
        config = _make_config()
        result = assess_invest(config)
        assert result["Negotiable"] is False


# ---------------------------------------------------------------------------
# Valuable
# ---------------------------------------------------------------------------


class TestValuable:
    """Tests for the Valuable criterion."""

    def test_valuable_with_so_that(self) -> None:
        config = _make_config(so_that="saves time")
        result = assess_invest(config)
        assert result["Valuable"] is True

    def test_valuable_empty_so_that(self) -> None:
        config = _make_config(so_that="")
        result = assess_invest(config)
        assert result["Valuable"] is False


# ---------------------------------------------------------------------------
# Estimable
# ---------------------------------------------------------------------------


class TestEstimable:
    """Tests for the Estimable criterion."""

    def test_estimable_with_points(self) -> None:
        config = _make_config(points=3)
        result = assess_invest(config)
        assert result["Estimable"] is True

    def test_estimable_with_size(self) -> None:
        config = _make_config(size="M")
        result = assess_invest(config)
        assert result["Estimable"] is True

    def test_estimable_no_sizing(self) -> None:
        config = _make_config(points=0, size="")
        result = assess_invest(config)
        assert result["Estimable"] is False


# ---------------------------------------------------------------------------
# Small
# ---------------------------------------------------------------------------


class TestSmall:
    """Tests for the Small criterion."""

    def test_small_with_small_points(self) -> None:
        config = _make_config(points=3)
        result = assess_invest(config)
        assert result["Small"] is True

    def test_small_with_large_points(self) -> None:
        config = _make_config(points=13)
        result = assess_invest(config)
        assert result["Small"] is False

    def test_small_with_size_s(self) -> None:
        config = _make_config(size="S")
        result = assess_invest(config)
        assert result["Small"] is True

    def test_small_with_size_xl(self) -> None:
        config = _make_config(size="XL")
        result = assess_invest(config)
        assert result["Small"] is False


# ---------------------------------------------------------------------------
# Testable
# ---------------------------------------------------------------------------


class TestTestable:
    """Tests for the Testable criterion."""

    def test_testable_with_acs(self) -> None:
        config = _make_config(acceptance_criteria=["AC1"])
        result = assess_invest(config)
        assert result["Testable"] is True

    def test_testable_with_test_cases(self) -> None:
        config = _make_config(test_cases=["test1"])
        result = assess_invest(config)
        assert result["Testable"] is True

    def test_testable_empty(self) -> None:
        config = _make_config(acceptance_criteria=[], test_cases=[])
        result = assess_invest(config)
        assert result["Testable"] is False
