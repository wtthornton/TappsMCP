"""TAP-1796: failure-priority ordering must follow per-call weights.

Before the fix, _CATEGORY_WEIGHTS was frozen at module import from ScoringWeights
defaults. With custom weights in .tapps-mcp.yaml (e.g. security=0.10,
performance=0.30), gate output still ordered failures as if security were 0.27
and performance were 0.08 — the "Fix these in order of priority" hint
misdirected the agent.
"""

from __future__ import annotations

from tapps_mcp.gates.evaluator import evaluate_gate
from tapps_mcp.gates.models import GateThresholds
from tapps_mcp.scoring.models import CategoryScore, ScoreResult


def _make_score_with_custom_weights() -> ScoreResult:
    """Performance is weighted higher than security in this score result.

    Both categories fail their minimums; the gate must order Performance first
    because its weight is 0.30 vs security's 0.10.
    """
    cats = {
        "security": CategoryScore(name="security", score=6.0, weight=0.10),
        "maintainability": CategoryScore(name="maintainability", score=9.0, weight=0.10),
        "complexity": CategoryScore(name="complexity", score=2.0, weight=0.10),
        "test_coverage": CategoryScore(name="test_coverage", score=9.0, weight=0.10),
        "performance": CategoryScore(name="performance", score=4.0, weight=0.30),
        "structure": CategoryScore(name="structure", score=8.0, weight=0.15),
        "devex": CategoryScore(name="devex", score=8.0, weight=0.15),
    }
    return ScoreResult(
        file_path="test.py",
        categories=cats,
        overall_score=70.0,
        degraded=False,
        missing_tools=[],
    )


def test_failure_order_uses_configured_weights_not_defaults() -> None:
    score = _make_score_with_custom_weights()
    # Force both security_min and performance_min so both fail.
    thresholds = GateThresholds(
        overall_min=0.0,
        security_min=7.0,
        performance_min=7.0,
    )
    result = evaluate_gate(score, thresholds=thresholds)

    cats_in_order = [f.category for f in result.failures]
    assert "security" in cats_in_order
    assert "performance" in cats_in_order
    assert cats_in_order.index("performance") < cats_in_order.index("security"), (
        f"TAP-1796: performance (weight 0.30) must sort before security "
        f"(weight 0.10) given the custom weights, but got order: {cats_in_order}"
    )

    # Spot-check the recorded weights actually came from the score result.
    sec_failure = next(f for f in result.failures if f.category == "security")
    perf_failure = next(f for f in result.failures if f.category == "performance")
    assert sec_failure.weight == 0.10
    assert perf_failure.weight == 0.30


def test_overall_failure_still_sorts_first_regardless_of_category_weights() -> None:
    """The overall pseudo-category keeps weight 1.0 so it sorts above any category."""
    cats = {
        "security": CategoryScore(name="security", score=4.0, weight=0.50),
        "maintainability": CategoryScore(name="maintainability", score=9.0, weight=0.10),
        "complexity": CategoryScore(name="complexity", score=2.0, weight=0.10),
        "test_coverage": CategoryScore(name="test_coverage", score=9.0, weight=0.10),
        "performance": CategoryScore(name="performance", score=9.0, weight=0.10),
        "structure": CategoryScore(name="structure", score=8.0, weight=0.05),
        "devex": CategoryScore(name="devex", score=8.0, weight=0.05),
    }
    score = ScoreResult(
        file_path="t.py",
        categories=cats,
        overall_score=40.0,
        degraded=False,
        missing_tools=[],
    )
    thresholds = GateThresholds(overall_min=70.0, security_min=7.0)
    result = evaluate_gate(score, thresholds=thresholds)

    categories = [f.category for f in result.failures]
    assert categories[0] == "overall", (
        f"overall must sort first regardless of category weights; got {categories}"
    )


def test_default_weights_still_used_when_category_missing() -> None:
    """If a category is absent from the score result, fall back to the default weight."""
    cats = {
        "security": CategoryScore(name="security", score=4.0, weight=0.30),
        "maintainability": CategoryScore(name="maintainability", score=9.0, weight=0.10),
        "complexity": CategoryScore(name="complexity", score=2.0, weight=0.10),
        "test_coverage": CategoryScore(name="test_coverage", score=9.0, weight=0.10),
        "performance": CategoryScore(name="performance", score=9.0, weight=0.10),
        # No structure, no devex.
    }
    score = ScoreResult(
        file_path="t.py",
        categories=cats,
        overall_score=80.0,
        degraded=False,
        missing_tools=[],
    )
    thresholds = GateThresholds(overall_min=0.0, security_min=7.0)
    result = evaluate_gate(score, thresholds=thresholds)
    sec_failure = next(f for f in result.failures if f.category == "security")
    assert sec_failure.weight == 0.30
