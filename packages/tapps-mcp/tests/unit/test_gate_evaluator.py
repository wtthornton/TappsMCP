"""Tests for Epic 37.5 — Gate failure weighting with security floor."""

from __future__ import annotations

from tapps_mcp.gates.evaluator import (
    _DEFAULT_CATEGORY_WEIGHTS,
    _SECURITY_FLOOR_INDIVIDUAL,
    evaluate_gate,
)
from tapps_mcp.gates.models import GateThresholds
from tapps_mcp.scoring.models import CategoryScore, ScoreResult


def _make_score(
    overall: float = 80.0,
    security: float = 9.0,
    maintainability: float = 7.0,
    complexity: float = 3.0,
    test_coverage: float = 5.0,
    performance: float = 8.0,
    degraded: bool = False,
    missing_tools: list[str] | None = None,
) -> ScoreResult:
    """Helper to create a ScoreResult for testing."""
    cats = {
        "security": CategoryScore(name="security", score=security, weight=0.27),
        "maintainability": CategoryScore(
            name="maintainability", score=maintainability, weight=0.24
        ),
        "complexity": CategoryScore(name="complexity", score=complexity, weight=0.18),
        "test_coverage": CategoryScore(name="test_coverage", score=test_coverage, weight=0.13),
        "performance": CategoryScore(name="performance", score=performance, weight=0.08),
        "structure": CategoryScore(name="structure", score=7.0, weight=0.05),
        "devex": CategoryScore(name="devex", score=6.0, weight=0.05),
    }
    return ScoreResult(
        file_path="test.py",
        categories=cats,
        overall_score=overall,
        degraded=degraded,
        missing_tools=missing_tools or [],
    )


class TestFailureWeighting:
    """Epic 37.5: failures are ordered by scoring weight (highest first)."""

    def test_failures_ordered_by_weight(self) -> None:
        """Verify failures are returned in weight-descending order."""
        # Trigger failures in security (0.27), maintainability (0.24), performance (0.08)
        thresholds = GateThresholds(
            overall_min=0.0,
            security_min=9.0,
            maintainability_min=9.0,
            performance_min=9.0,
        )
        score = _make_score(
            overall=80.0,
            security=5.0,
            maintainability=5.0,
            performance=5.0,
        )
        result = evaluate_gate(score, thresholds=thresholds)

        assert result.passed is False
        assert len(result.failures) >= 3

        # Failures should be sorted by weight descending
        weights = [f.weight for f in result.failures]
        assert weights == sorted(weights, reverse=True), (
            f"Failures not in weight-descending order: {weights}"
        )

        # First failure should be the highest-weight category
        assert result.failures[0].category == "security"
        assert result.failures[0].weight == _DEFAULT_CATEGORY_WEIGHTS["security"]

    def test_critical_security_floor(self) -> None:
        """Security score below 50 (5.0 on 0-10) fails gate even if overall passes."""
        # Standard preset: security_min=0.0 so normally no security gate
        score = _make_score(overall=85.0, security=4.5)
        result = evaluate_gate(score, preset="standard")

        assert result.passed is False
        security_failures = [f for f in result.failures if f.category == "security"]
        assert len(security_failures) == 1
        assert "CRITICAL" in security_failures[0].message
        assert "minimum threshold (50)" in security_failures[0].message

    def test_security_at_boundary(self) -> None:
        """Security score exactly at floor (5.0 on 0-10 scale) passes."""
        score = _make_score(overall=85.0, security=_SECURITY_FLOOR_INDIVIDUAL)
        result = evaluate_gate(score, preset="standard")

        # No security floor violation at exactly 5.0
        security_failures = [f for f in result.failures if f.category == "security"]
        assert len(security_failures) == 0
        assert result.passed is True

    def test_gate_failure_message_format(self) -> None:
        """Verify priority fix suggestion is included when multiple failures."""
        thresholds = GateThresholds(
            overall_min=90.0,
            security_min=9.0,
        )
        score = _make_score(overall=70.0, security=5.0)
        result = evaluate_gate(score, thresholds=thresholds)

        assert result.passed is False
        assert len(result.failures) >= 2
        assert any("highest-weight categories first" in w for w in result.warnings), (
            f"Priority suggestion missing from warnings: {result.warnings}"
        )

    def test_overall_pass_but_security_floor_fail(self) -> None:
        """Overall=85 but security=4.0 fails due to security floor."""
        score = _make_score(overall=85.0, security=4.0)
        # Use standard preset (overall_min=70, security_min=0)
        result = evaluate_gate(score, preset="standard")

        assert result.passed is False
        assert any(f.category == "security" for f in result.failures)
        # Overall score is fine — only security floor triggers
        assert not any(f.category == "overall" for f in result.failures)

    def test_no_change_when_passing(self) -> None:
        """All passing categories still returns pass — no regressions."""
        score = _make_score(overall=85.0, security=9.0, maintainability=8.0)
        result = evaluate_gate(score, preset="standard")

        assert result.passed is True
        assert result.failures == []
        # No priority suggestion when passing
        assert not any("highest-weight" in w for w in result.warnings)


class TestGateFailureWeight:
    """Verify the weight field on GateFailure is populated correctly."""

    def test_failure_carries_category_weight(self) -> None:
        """Each failure's weight matches its category scoring weight."""
        thresholds = GateThresholds(
            overall_min=0.0,
            security_min=9.0,
            maintainability_min=9.0,
        )
        score = _make_score(security=5.0, maintainability=5.0)
        result = evaluate_gate(score, thresholds=thresholds)

        for failure in result.failures:
            expected_weight = _DEFAULT_CATEGORY_WEIGHTS.get(failure.category, 0.0)
            assert failure.weight == expected_weight, (
                f"{failure.category} weight {failure.weight} != {expected_weight}"
            )

    def test_overall_failure_weight_is_one(self) -> None:
        """Overall failures get weight=1.0 so they sort first."""
        score = _make_score(overall=50.0, security=4.0)
        thresholds = GateThresholds(overall_min=70.0)
        result = evaluate_gate(score, thresholds=thresholds)

        overall_failures = [f for f in result.failures if f.category == "overall"]
        assert len(overall_failures) == 1
        assert overall_failures[0].weight == 1.0
        # Overall should be first in the sorted list
        assert result.failures[0].category == "overall"

    def test_security_floor_does_not_duplicate(self) -> None:
        """When security already fails via threshold, floor doesn't add a second failure."""
        thresholds = GateThresholds(overall_min=0.0, security_min=8.0)
        score = _make_score(security=3.0)  # Below both threshold and floor
        result = evaluate_gate(score, thresholds=thresholds)

        security_failures = [f for f in result.failures if f.category == "security"]
        assert len(security_failures) == 1  # Only one, not duplicated

    def test_single_failure_no_priority_suggestion(self) -> None:
        """A single failure should NOT include the priority suggestion."""
        thresholds = GateThresholds(overall_min=90.0)
        score = _make_score(overall=80.0, security=9.0)
        result = evaluate_gate(score, thresholds=thresholds)

        assert result.passed is False
        assert len(result.failures) == 1
        assert not any("highest-weight" in w for w in result.warnings)
