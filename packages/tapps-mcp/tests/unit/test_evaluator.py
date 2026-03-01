"""Tests for gates.evaluator — quality gate evaluation."""

from tapps_mcp.gates.evaluator import evaluate_gate, thresholds_for_preset
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
        "security": CategoryScore(name="security", score=security, weight=0.2),
        "maintainability": CategoryScore(
            name="maintainability", score=maintainability, weight=0.15
        ),
        "complexity": CategoryScore(name="complexity", score=complexity, weight=0.2),
        "test_coverage": CategoryScore(name="test_coverage", score=test_coverage, weight=0.1),
        "performance": CategoryScore(name="performance", score=performance, weight=0.15),
        "structure": CategoryScore(name="structure", score=7.0, weight=0.1),
        "devex": CategoryScore(name="devex", score=6.0, weight=0.1),
    }
    return ScoreResult(
        file_path="test.py",
        categories=cats,
        overall_score=overall,
        degraded=degraded,
        missing_tools=missing_tools or [],
    )


class TestThresholdsForPreset:
    def test_standard(self):
        t = thresholds_for_preset("standard")
        assert t.overall_min == 70.0

    def test_strict(self):
        t = thresholds_for_preset("strict")
        assert t.overall_min == 80.0

    def test_framework(self):
        t = thresholds_for_preset("framework")
        assert t.overall_min == 75.0

    def test_unknown_falls_back_to_standard(self):
        t = thresholds_for_preset("nonexistent")
        assert t.overall_min == 70.0


class TestEvaluateGate:
    def test_passing_standard(self):
        score = _make_score(overall=85.0)
        result = evaluate_gate(score, preset="standard")
        assert result.passed is True
        assert result.failures == []
        assert result.preset == "standard"

    def test_failing_overall(self):
        score = _make_score(overall=60.0)
        result = evaluate_gate(score, preset="standard")
        assert result.passed is False
        assert any(f.category == "overall" for f in result.failures)

    def test_failing_security(self):
        thresholds = GateThresholds(overall_min=0.0, security_min=8.0)
        score = _make_score(overall=80.0, security=5.0)
        result = evaluate_gate(score, thresholds=thresholds)
        assert result.passed is False
        assert any(f.category == "security" for f in result.failures)

    def test_failing_maintainability(self):
        thresholds = GateThresholds(overall_min=0.0, maintainability_min=8.0)
        score = _make_score(overall=80.0, maintainability=5.0)
        result = evaluate_gate(score, thresholds=thresholds)
        assert result.passed is False
        assert any(f.category == "maintainability" for f in result.failures)

    def test_failing_complexity(self):
        thresholds = GateThresholds(overall_min=0.0, complexity_max=5.0)
        score = _make_score(overall=80.0, complexity=7.0)
        result = evaluate_gate(score, thresholds=thresholds)
        assert result.passed is False
        assert any(f.category == "complexity" for f in result.failures)

    def test_failing_test_coverage(self):
        thresholds = GateThresholds(overall_min=0.0, test_coverage_min=8.0)
        score = _make_score(overall=80.0, test_coverage=3.0)
        result = evaluate_gate(score, thresholds=thresholds)
        assert result.passed is False
        assert any(f.category == "test_coverage" for f in result.failures)

    def test_failing_performance(self):
        thresholds = GateThresholds(overall_min=0.0, performance_min=9.0)
        score = _make_score(overall=80.0, performance=6.0)
        result = evaluate_gate(score, thresholds=thresholds)
        assert result.passed is False
        assert any(f.category == "performance" for f in result.failures)

    def test_multiple_failures(self):
        thresholds = GateThresholds(overall_min=90.0, security_min=9.5)
        score = _make_score(overall=70.0, security=5.0)
        result = evaluate_gate(score, thresholds=thresholds)
        assert result.passed is False
        assert len(result.failures) == 2

    def test_explicit_thresholds_override_preset(self):
        thresholds = GateThresholds(overall_min=50.0)
        score = _make_score(overall=55.0)
        result = evaluate_gate(score, preset="strict", thresholds=thresholds)
        # Should pass because explicit thresholds (50) used instead of strict (80)
        assert result.passed is True

    def test_degraded_warning(self):
        score = _make_score(overall=80.0, degraded=True, missing_tools=["bandit"])
        result = evaluate_gate(score, preset="standard")
        assert result.passed is True
        assert len(result.warnings) == 1
        assert "bandit" in result.warnings[0]

    def test_scores_dict_populated(self):
        score = _make_score(overall=80.0)
        result = evaluate_gate(score, preset="standard")
        assert "overall" in result.scores
        assert "security" in result.scores
        assert result.scores["overall"] == 80.0

    def test_zero_threshold_not_checked(self):
        # security_min=0.0 means security gate is not active
        thresholds = GateThresholds(overall_min=0.0, security_min=0.0)
        score = _make_score(overall=0.0, security=0.0)
        result = evaluate_gate(score, thresholds=thresholds)
        assert result.passed is True

    def test_complexity_at_max_not_failing(self):
        # complexity_max=10.0 (the max) means gate inactive
        thresholds = GateThresholds(overall_min=0.0, complexity_max=10.0)
        score = _make_score(overall=80.0, complexity=10.0)
        result = evaluate_gate(score, thresholds=thresholds)
        assert result.passed is True
