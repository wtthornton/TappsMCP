"""TAP-1800: ChecklistCalibrator must use an absolute token budget, not the
broken `x / (x + 1000)` pseudo-ratio.

The previous formula crossed 0.15 at ~176 tokens, so any moderately chatty
tool failed the required-tier check regardless of impact. Now the cost test
is a direct token budget; token-saving tools (signed-negative
avg_token_cost from TAP-1799) always pass.
"""

from __future__ import annotations

from tapps_mcp.benchmark.call_patterns import CallPatternReport
from tapps_mcp.benchmark.checklist_calibrator import (
    _COST_THRESHOLD_TOKENS,
    ChecklistCalibrator,
)
from tapps_mcp.benchmark.tool_evaluator import ToolRanking


def _ranking(*, tool: str = "tapps_memory", impact: float = 0.05, tokens: int = 100) -> ToolRanking:
    return ToolRanking(
        tool_name=tool,
        impact_score=impact,
        tasks_helped=5,
        tasks_hurt=0,
        tasks_neutral=2,
        avg_token_cost=tokens,
        pass_at_k=0.7,
    )


def _empty_call_report() -> CallPatternReport:
    return CallPatternReport(
        patterns=[],
        avg_efficiency=0.0,
        most_overcalled=[],
        most_undercalled=[],
        common_sequences=[],
    )


def test_token_cost_below_budget_qualifies_for_required() -> None:
    calibrator = ChecklistCalibrator()
    ranking = _ranking(impact=0.05, tokens=_COST_THRESHOLD_TOKENS - 1)
    result = calibrator.calibrate_tiers([ranking], _empty_call_report(), "medium")
    assert result.classifications[0].recommended_tier == "required"


def test_token_cost_at_or_above_budget_drops_to_recommended() -> None:
    """High impact but expensive: the cost gate must prevent 'required'."""
    calibrator = ChecklistCalibrator()
    ranking = _ranking(impact=0.05, tokens=_COST_THRESHOLD_TOKENS + 1)
    result = calibrator.calibrate_tiers([ranking], _empty_call_report(), "medium")
    assert result.classifications[0].recommended_tier == "recommended"


def test_token_saving_tool_always_passes_cost_gate() -> None:
    """TAP-1799 made avg_token_cost signed. Negative values must qualify."""
    calibrator = ChecklistCalibrator()
    ranking = _ranking(impact=0.05, tokens=-200)
    result = calibrator.calibrate_tiers([ranking], _empty_call_report(), "medium")
    assert result.classifications[0].recommended_tier == "required"


def test_measured_cost_stores_token_count_not_ratio() -> None:
    """The exposed measured_cost field should be the token delta, not a 0-1 ratio."""
    calibrator = ChecklistCalibrator()
    ranking = _ranking(impact=0.05, tokens=350)
    result = calibrator.calibrate_tiers([ranking], _empty_call_report(), "medium")
    assert result.classifications[0].measured_cost == 350.0


def test_above_budget_chatty_but_low_impact_stays_optional() -> None:
    """Sanity: high cost + low impact still falls through to optional."""
    calibrator = ChecklistCalibrator()
    ranking = _ranking(impact=-0.05, tokens=_COST_THRESHOLD_TOKENS + 1)
    result = calibrator.calibrate_tiers([ranking], _empty_call_report(), "medium")
    assert result.classifications[0].recommended_tier == "optional"


def test_existing_calibrate_required_fixture_still_promotes_to_required() -> None:
    """Backward-compat against the existing TestChecklistCalibrator scenario:
    impact=0.05, tokens=100 must still classify as required."""
    calibrator = ChecklistCalibrator()
    ranking = _ranking(impact=0.05, tokens=100)
    result = calibrator.calibrate_tiers([ranking], _empty_call_report(), "medium")
    assert result.classifications[0].recommended_tier == "required"
