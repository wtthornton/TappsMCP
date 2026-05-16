"""TAP-1799: ToolRanking.avg_token_cost must keep its sign.

Previously the field had `ge=0` and the aggregator clamped to `max(..., 0)`.
A token-saving tool (with-tool run consumed fewer tokens than without-tool)
recorded `avg_token_cost=0`, indistinguishable from a no-effect tool, and
ChecklistCalibrator never got the cost-favorable signal.
"""

from __future__ import annotations

from tapps_mcp.benchmark.tool_evaluator import (
    ToolCondition,
    ToolImpactEvaluator,
    ToolImpactResult,
    ToolRanking,
)


def _result(task_id: str, condition: ToolCondition, tokens: int, resolved: bool = True) -> ToolImpactResult:
    return ToolImpactResult(
        task_id=task_id,
        condition=condition,
        tool_name="tapps_memory",
        resolved=resolved,
        token_usage=tokens,
    )


def test_ranking_model_accepts_negative_token_cost() -> None:
    """The model field constraint must allow negative values now."""
    ranking = ToolRanking(
        tool_name="tapps_memory",
        impact_score=0.5,
        tasks_helped=3,
        tasks_hurt=0,
        tasks_neutral=1,
        avg_token_cost=-150,
        pass_at_k=0.75,
    )
    assert ranking.avg_token_cost == -150


def test_compute_ranking_preserves_negative_token_delta() -> None:
    """Aggregator reports negative avg_token_cost when the tool saves tokens."""
    evaluator = ToolImpactEvaluator(tasks=[])
    # With the tool, both tasks consume 100 tokens. Without, both consume 300.
    # Per-pair delta = 100 - 300 = -200 (tool saved tokens). avg = -200.
    results = [
        _result("t1", ToolCondition.ALL_TOOLS, tokens=100),
        _result("t1", ToolCondition.ALL_MINUS_ONE, tokens=300),
        _result("t2", ToolCondition.ALL_TOOLS, tokens=100),
        _result("t2", ToolCondition.ALL_MINUS_ONE, tokens=300),
    ]

    rankings = evaluator.compute_ranking(results)

    assert len(rankings) == 1
    assert rankings[0].avg_token_cost == -200, (
        "TAP-1799: token-saving tool must record a negative avg_token_cost; "
        f"got {rankings[0].avg_token_cost}"
    )


def test_compute_ranking_keeps_positive_when_tool_costs_tokens() -> None:
    """Sanity: a token-adding tool still records a positive delta."""
    evaluator = ToolImpactEvaluator(tasks=[])
    results = [
        _result("t1", ToolCondition.ALL_TOOLS, tokens=500),
        _result("t1", ToolCondition.ALL_MINUS_ONE, tokens=100),
    ]

    rankings = evaluator.compute_ranking(results)
    assert rankings[0].avg_token_cost == 400
