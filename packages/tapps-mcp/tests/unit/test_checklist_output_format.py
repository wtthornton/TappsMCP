"""Tests for tapps_checklist output_format parameter (Story 74.2)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tapps_mcp.tools.checklist import CallTracker, ChecklistHint, ChecklistResult

_EVALUATE_TARGET = "tapps_mcp.tools.checklist.CallTracker.evaluate"


@pytest.fixture(autouse=True)
def _reset_tracker() -> None:  # type: ignore[misc]
    """Reset CallTracker before every test."""
    CallTracker.reset()


def _make_result(
    task_type: str = "review",
    missing_required: list[str] | None = None,
    missing_recommended: list[str] | None = None,
    missing_optional: list[str] | None = None,
    complete: bool = False,
    called: list[str] | None = None,
    missing_required_hints: list[ChecklistHint] | None = None,
    missing_recommended_hints: list[ChecklistHint] | None = None,
) -> ChecklistResult:
    return ChecklistResult(
        task_type=task_type,
        called=called or [],
        missing_required=missing_required or [],
        missing_recommended=missing_recommended or [],
        missing_optional=missing_optional or [],
        missing_required_hints=missing_required_hints or [],
        missing_recommended_hints=missing_recommended_hints or [],
        missing_optional_hints=[],
        complete=complete,
        total_calls=len(called) if called else 0,
    )


@pytest.mark.asyncio
async def test_checklist_default_markdown() -> None:
    """Default output_format='markdown' returns full model_dump data (backward compat)."""
    from tapps_mcp.server import tapps_checklist

    result = _make_result(
        called=["tapps_checklist", "tapps_score_file", "tapps_quality_gate"],
        missing_required=[],
        complete=True,
    )

    with patch(_EVALUATE_TARGET, return_value=result):
        resp = await tapps_checklist("review")

    assert resp["success"] is True
    data = resp["data"]
    assert "task_type" in data
    assert "called" in data
    assert "missing_required" in data
    assert "missing_recommended" in data
    assert "missing_optional" in data
    assert "complete" in data
    assert "total_calls" in data
    assert "required_called" not in data
    assert "summary" not in data


@pytest.mark.asyncio
async def test_checklist_json_format() -> None:
    """output_format='json' returns structured counts."""
    from tapps_mcp.server import tapps_checklist

    result = _make_result(
        task_type="feature",
        called=["tapps_checklist", "tapps_score_file"],
        missing_required=["tapps_security_scan"],
        missing_recommended=["tapps_dead_code"],
        missing_optional=["tapps_dependency_scan"],
        complete=False,
    )

    with patch(_EVALUATE_TARGET, return_value=result):
        resp = await tapps_checklist("feature", output_format="json")

    assert resp["success"] is True
    data = resp["data"]
    assert data["task_type"] == "feature"
    assert data["complete"] is False
    assert data["required_missing"] == ["tapps_security_scan"]
    assert data["recommended_missing"] == ["tapps_dead_code"]
    assert data["optional_missing"] == ["tapps_dependency_scan"]
    assert "required_called" in data
    assert "recommended_called" in data
    assert "optional_called" in data
    assert "priority_actions" in data
    assert data["priority_actions"] == ["tapps_security_scan"]
    assert data["total_calls"] == 2


@pytest.mark.asyncio
async def test_checklist_compact_format() -> None:
    """output_format='compact' returns short summary string."""
    from tapps_mcp.server import tapps_checklist

    result = _make_result(
        task_type="review",
        called=["tapps_checklist", "tapps_score_file", "tapps_quality_gate"],
        missing_required=[],
        missing_recommended=["tapps_dead_code"],
        complete=True,
    )

    with patch(_EVALUATE_TARGET, return_value=result):
        resp = await tapps_checklist("review", output_format="compact")

    assert resp["success"] is True
    data = resp["data"]
    assert "summary" in data
    assert "complete=True" in data["summary"]
    assert "Checklist review:" in data["summary"]
    assert "tapps_dead_code" in data["summary"]
    assert data["complete"] is True
    assert data["task_type"] == "review"
    assert data["total_calls"] == 3


@pytest.mark.asyncio
async def test_checklist_compact_with_missing_required() -> None:
    """Compact format includes missing required tools in summary."""
    from tapps_mcp.server import tapps_checklist

    result = _make_result(
        task_type="feature",
        called=["tapps_checklist"],
        missing_required=["tapps_score_file", "tapps_quality_gate"],
        complete=False,
    )

    with patch(_EVALUATE_TARGET, return_value=result):
        resp = await tapps_checklist("feature", output_format="compact")

    data = resp["data"]
    assert "complete=False" in data["summary"]
    assert "2 required missing" in data["summary"]
    assert "tapps_score_file" in data["summary"]
    assert "tapps_quality_gate" in data["summary"]


@pytest.mark.asyncio
async def test_checklist_invalid_format() -> None:
    """Invalid output_format returns error response."""
    from tapps_mcp.server import tapps_checklist

    resp = await tapps_checklist("review", output_format="xml")

    assert resp["success"] is False
    assert "invalid_format" in resp["error"]["code"]
    assert "xml" in resp["error"]["message"]


@pytest.mark.asyncio
async def test_checklist_json_priority_actions_capped() -> None:
    """JSON priority_actions contains at most 3 items."""
    from tapps_mcp.server import tapps_checklist

    result = _make_result(
        task_type="feature",
        called=["tapps_checklist"],
        missing_required=[
            "tapps_score_file",
            "tapps_quality_gate",
            "tapps_security_scan",
            "tapps_validate_changed",
        ],
        complete=False,
    )

    with patch(_EVALUATE_TARGET, return_value=result):
        resp = await tapps_checklist("feature", output_format="json")

    data = resp["data"]
    assert len(data["priority_actions"]) == 3


@pytest.mark.asyncio
async def test_checklist_json_complete_no_priority_actions() -> None:
    """JSON priority_actions is empty when checklist is complete."""
    from tapps_mcp.server import tapps_checklist

    result = _make_result(
        called=["tapps_checklist", "tapps_score_file", "tapps_quality_gate"],
        missing_required=[],
        complete=True,
    )

    with patch(_EVALUATE_TARGET, return_value=result):
        resp = await tapps_checklist("review", output_format="json")

    data = resp["data"]
    assert data["priority_actions"] == []
    assert data["complete"] is True


@pytest.mark.asyncio
async def test_checklist_json_next_steps() -> None:
    """JSON output includes next_steps from missing required/recommended hints."""
    from tapps_mcp.server import tapps_checklist

    result = _make_result(
        task_type="feature",
        called=["tapps_checklist"],
        missing_required=["tapps_score_file", "tapps_quality_gate"],
        missing_recommended=["tapps_security_scan"],
        complete=False,
        missing_required_hints=[
            ChecklistHint(tool="tapps_score_file", reason="Score the file for quality."),
            ChecklistHint(tool="tapps_quality_gate", reason="Call before declaring done."),
        ],
        missing_recommended_hints=[
            ChecklistHint(tool="tapps_security_scan", reason="Run security scan."),
        ],
    )

    with patch(_EVALUATE_TARGET, return_value=result):
        resp = await tapps_checklist("feature", output_format="json")

    assert resp["success"] is True
    data = resp["data"]
    assert "next_steps" in data
    assert data["next_steps"] == [
        "Score the file for quality.",
        "Call before declaring done.",
        "Run security scan.",
    ]


@pytest.mark.asyncio
async def test_checklist_json_full_data() -> None:
    """JSON output includes full ChecklistResult for consumers that need it."""
    from tapps_mcp.server import tapps_checklist

    result = _make_result(
        task_type="bugfix",
        called=["tapps_checklist", "tapps_score_file"],
        missing_required=[],
        complete=True,
    )

    with patch(_EVALUATE_TARGET, return_value=result):
        resp = await tapps_checklist("bugfix", output_format="json")

    assert resp["success"] is True
    data = resp["data"]
    assert "full" in data
    full = data["full"]
    assert full["task_type"] == "bugfix"
    assert full["complete"] is True
    assert "tapps_checklist" in full["called"]
    assert "tapps_score_file" in full["called"]
    assert full["missing_required"] == []
    assert "missing_recommended" in full
    assert "total_calls" in full


@pytest.mark.asyncio
async def test_checklist_compact_next_steps_and_full() -> None:
    """Compact output includes next_steps and full result."""
    from tapps_mcp.server import tapps_checklist

    result = _make_result(
        task_type="feature",
        called=["tapps_checklist"],
        missing_required=["tapps_quality_gate"],
        complete=False,
        missing_required_hints=[
            ChecklistHint(tool="tapps_quality_gate", reason="Call quality gate before done."),
        ],
    )

    with patch(_EVALUATE_TARGET, return_value=result):
        resp = await tapps_checklist("feature", output_format="compact")

    assert resp["success"] is True
    data = resp["data"]
    assert "next_steps" in data
    assert data["next_steps"] == ["Call quality gate before done."]
    assert "full" in data
    assert data["full"]["task_type"] == "feature"
    assert data["full"]["missing_required"] == ["tapps_quality_gate"]
