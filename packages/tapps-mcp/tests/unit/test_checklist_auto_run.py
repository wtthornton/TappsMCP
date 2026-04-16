"""Tests for tapps_checklist auto_run functionality."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.tools.checklist import CallTracker, ChecklistResult

# Patch target for CallTracker.evaluate — it's imported locally inside
# tapps_checklist from tapps_mcp.tools.checklist, so we patch at source.
_EVALUATE_TARGET = "tapps_mcp.tools.checklist.CallTracker.evaluate"
_VC_TARGET = "tapps_mcp.server_pipeline_tools.tapps_validate_changed"
_SETTINGS_TARGET = "tapps_mcp.server.load_settings"


@pytest.fixture(autouse=True)
def _reset_tracker() -> None:  # type: ignore[misc]
    """Reset CallTracker before every test."""
    CallTracker.reset()


def _make_result(
    missing_required: list[str] | None = None,
    complete: bool = False,
    called: list[str] | None = None,
) -> ChecklistResult:
    return ChecklistResult(
        task_type="feature",
        called=called or [],
        missing_required=missing_required or [],
        missing_recommended=[],
        missing_optional=[],
        missing_required_hints=[],
        missing_recommended_hints=[],
        missing_optional_hints=[],
        complete=complete,
        total_calls=len(called) if called else 0,
    )


def _mock_vc_result(success: bool = True) -> dict[str, Any]:
    return {
        "tool": "tapps_validate_changed",
        "success": success,
        "elapsed_ms": 100,
        "data": {
            "files_validated": 2,
            "all_gates_passed": success,
        },
    }


@pytest.mark.asyncio
async def test_auto_run_false_no_extra_calls() -> None:
    """auto_run=False should not call tapps_validate_changed even with missing tools."""
    result = _make_result(missing_required=["tapps_score_file"])

    with (
        patch(_EVALUATE_TARGET, return_value=result),
        patch(_VC_TARGET, new_callable=AsyncMock) as mock_vc,
    ):
        from tapps_mcp.server import tapps_checklist

        resp = await tapps_checklist(task_type="feature", auto_run=False)

    mock_vc.assert_not_called()
    assert "auto_run_results" not in resp.get("data", {})


@pytest.mark.asyncio
async def test_auto_run_true_runs_validate_when_score_missing() -> None:
    """auto_run=True should call tapps_validate_changed when score_file is missing."""
    first_result = _make_result(missing_required=["tapps_score_file"])
    second_result = _make_result(complete=True, called=["tapps_validate_changed"])

    call_count = 0

    def evaluate_side_effect(task_type: str = "review", **_kw: Any) -> ChecklistResult:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return first_result
        return second_result

    mock_settings = MagicMock()
    mock_settings.quality_preset = "standard"
    mock_settings.project_root = Path.cwd()
    mock_settings.checklist_require_success = False
    mock_settings.checklist_strict_unknown_task_types = False

    with (
        patch(_EVALUATE_TARGET, side_effect=evaluate_side_effect),
        patch(_VC_TARGET, new_callable=AsyncMock, return_value=_mock_vc_result()) as mock_vc,
        patch(_SETTINGS_TARGET, return_value=mock_settings),
    ):
        from tapps_mcp.server import tapps_checklist

        resp = await tapps_checklist(task_type="feature", auto_run=True)

    mock_vc.assert_called_once()
    data = resp.get("data", {})
    assert "auto_run_results" in data
    assert data["auto_run_results"]["validate_changed"]["success"] is True
    assert data["auto_run_results"]["validate_changed"]["files_validated"] == 2


@pytest.mark.asyncio
async def test_auto_run_true_all_tools_called_no_action() -> None:
    """auto_run=True with no missing required tools should not call validate."""
    result = _make_result(complete=True, called=["tapps_score_file", "tapps_quality_gate"])

    with (
        patch(_EVALUATE_TARGET, return_value=result),
        patch(_VC_TARGET, new_callable=AsyncMock) as mock_vc,
    ):
        from tapps_mcp.server import tapps_checklist

        resp = await tapps_checklist(task_type="feature", auto_run=True)

    mock_vc.assert_not_called()
    assert "auto_run_results" not in resp.get("data", {})


@pytest.mark.asyncio
async def test_auto_run_validate_failure_graceful() -> None:
    """auto_run=True should handle tapps_validate_changed failure gracefully."""
    result = _make_result(missing_required=["tapps_quality_gate"])

    mock_settings = MagicMock()
    mock_settings.quality_preset = "standard"
    mock_settings.project_root = Path.cwd()
    mock_settings.checklist_require_success = False
    mock_settings.checklist_strict_unknown_task_types = False

    with (
        patch(_EVALUATE_TARGET, return_value=result),
        patch(
            _VC_TARGET,
            new_callable=AsyncMock,
            side_effect=RuntimeError("git not found"),
        ),
        patch(_SETTINGS_TARGET, return_value=mock_settings),
    ):
        from tapps_mcp.server import tapps_checklist

        resp = await tapps_checklist(task_type="feature", auto_run=True)

    assert resp["success"] is True
    data = resp.get("data", {})
    assert "auto_run_results" in data
    vc_res = data["auto_run_results"]["validate_changed"]
    assert vc_res["success"] is False
    assert "git not found" in vc_res["error"]


@pytest.mark.asyncio
async def test_auto_run_re_evaluates_after_running() -> None:
    """auto_run=True should re-evaluate checklist after running validations."""
    first_result = _make_result(missing_required=["tapps_score_file"], complete=False)
    second_result = _make_result(complete=True, called=["tapps_validate_changed"])

    call_count = 0

    def evaluate_side_effect(task_type: str = "review", **_kw: Any) -> ChecklistResult:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return first_result
        return second_result

    mock_settings = MagicMock()
    mock_settings.quality_preset = "standard"
    mock_settings.project_root = Path.cwd()
    mock_settings.checklist_require_success = False
    mock_settings.checklist_strict_unknown_task_types = False

    with (
        patch(_EVALUATE_TARGET, side_effect=evaluate_side_effect),
        patch(_VC_TARGET, new_callable=AsyncMock, return_value=_mock_vc_result()),
        patch(_SETTINGS_TARGET, return_value=mock_settings),
    ):
        from tapps_mcp.server import tapps_checklist

        resp = await tapps_checklist(task_type="feature", auto_run=True)

    data = resp.get("data", {})
    assert data["complete"] is True
    assert call_count == 2
