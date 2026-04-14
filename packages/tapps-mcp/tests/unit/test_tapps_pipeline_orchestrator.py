"""Tests for the tapps_pipeline one-call orchestrator (STORY-101.2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from tapps_mcp.server_pipeline_tools import tapps_pipeline


@pytest.fixture
def py_file(tmp_path: Path) -> Path:
    p = tmp_path / "sample.py"
    p.write_text('"""sample."""\n\ndef add(a: int, b: int) -> int:\n    return a + b\n')
    return p


def _ok(data: dict[str, Any], tool: str = "tapps_quick_check") -> dict[str, Any]:
    return {"tool": tool, "success": True, "elapsed_ms": 1, "data": data}


def _fail(data: dict[str, Any], tool: str = "tapps_quick_check") -> dict[str, Any]:
    return {"tool": tool, "success": False, "elapsed_ms": 1, "data": data}


@pytest.mark.asyncio
async def test_pipeline_requires_file_paths() -> None:
    resp = await tapps_pipeline(file_paths="")
    assert resp["success"] is False
    assert resp["error"]["code"] == "NO_FILE_PATHS"


@pytest.mark.asyncio
async def test_pipeline_happy_path(py_file: Path) -> None:
    """All stages pass → pipeline_passed True, 4 stages present."""
    with (
        patch(
            "tapps_mcp.server_helpers.ensure_session_initialized",
            AsyncMock(return_value=None),
        ),
        patch(
            "tapps_mcp.server_scoring_tools.tapps_quick_check",
            AsyncMock(return_value=_ok({"batch": {"passed_count": 1, "failed_count": 0}})),
        ),
        patch(
            "tapps_mcp.server_pipeline_tools.tapps_validate_changed",
            AsyncMock(return_value=_ok(
                {"all_passed": True, "passed_count": 1, "failed_count": 0},
                tool="tapps_validate_changed",
            )),
        ),
        patch(
            "tapps_mcp.server.tapps_checklist",
            AsyncMock(return_value=_ok({"missing": [], "compact_summary": "ok"}, tool="tapps_checklist")),
        ),
    ):
        resp = await tapps_pipeline(file_paths=str(py_file), task_type="feature")

    assert resp["success"] is True
    data = resp["data"]
    assert data["pipeline_passed"] is True
    assert data["short_circuit"] is None
    stage_names = [s["name"] for s in data["stages"]]
    assert stage_names == ["session_start", "quick_check", "validate_changed", "checklist"]
    assert all(s["success"] for s in data["stages"])


@pytest.mark.asyncio
async def test_pipeline_short_circuits_on_security_floor(py_file: Path) -> None:
    """Security floor failure skips validate_changed and fails the pipeline."""
    with (
        patch(
            "tapps_mcp.server_helpers.ensure_session_initialized",
            AsyncMock(return_value=None),
        ),
        patch(
            "tapps_mcp.server_scoring_tools.tapps_quick_check",
            AsyncMock(return_value=_ok({"security_floor_failed": True, "score": 30})),
        ),
        patch(
            "tapps_mcp.server_pipeline_tools.tapps_validate_changed",
            AsyncMock(return_value=_ok({"all_passed": True}, tool="tapps_validate_changed")),
        ),
        patch(
            "tapps_mcp.server.tapps_checklist",
            AsyncMock(return_value=_ok({"missing": []}, tool="tapps_checklist")),
        ) as cl,
    ):
        resp = await tapps_pipeline(file_paths=str(py_file))

    data = resp["data"]
    assert data["pipeline_passed"] is False
    assert data["short_circuit"] == "security_floor_failed"
    vc_stage = next(s for s in data["stages"] if s["name"] == "validate_changed")
    assert vc_stage["success"] is False
    assert "security_floor_failed" in vc_stage["summary"]
    # Checklist still runs after short-circuit (for reporting).
    cl.assert_awaited_once()


@pytest.mark.asyncio
async def test_pipeline_skip_session_start(py_file: Path) -> None:
    """skip_session_start=True omits the session_start stage entirely."""
    with (
        patch(
            "tapps_mcp.server_scoring_tools.tapps_quick_check",
            AsyncMock(return_value=_ok({"batch": {"passed_count": 1, "failed_count": 0}})),
        ),
        patch(
            "tapps_mcp.server_pipeline_tools.tapps_validate_changed",
            AsyncMock(return_value=_ok({"all_passed": True}, tool="tapps_validate_changed")),
        ),
        patch(
            "tapps_mcp.server.tapps_checklist",
            AsyncMock(return_value=_ok({"missing": []}, tool="tapps_checklist")),
        ),
    ):
        resp = await tapps_pipeline(file_paths=str(py_file), skip_session_start=True)

    stage_names = [s["name"] for s in resp["data"]["stages"]]
    assert "session_start" not in stage_names


@pytest.mark.asyncio
async def test_pipeline_fails_when_validate_fails(py_file: Path) -> None:
    """validate_changed failure propagates to pipeline_passed=False."""
    with (
        patch(
            "tapps_mcp.server_helpers.ensure_session_initialized",
            AsyncMock(return_value=None),
        ),
        patch(
            "tapps_mcp.server_scoring_tools.tapps_quick_check",
            AsyncMock(return_value=_ok({"batch": {"passed_count": 1, "failed_count": 0}})),
        ),
        patch(
            "tapps_mcp.server_pipeline_tools.tapps_validate_changed",
            AsyncMock(return_value=_ok(
                {"all_passed": False, "passed_count": 0, "failed_count": 1},
                tool="tapps_validate_changed",
            )),
        ),
        patch(
            "tapps_mcp.server.tapps_checklist",
            AsyncMock(return_value=_ok({"missing": []}, tool="tapps_checklist")),
        ),
    ):
        resp = await tapps_pipeline(file_paths=str(py_file))

    assert resp["data"]["pipeline_passed"] is False
    vc_stage = next(s for s in resp["data"]["stages"] if s["name"] == "validate_changed")
    assert vc_stage["success"] is False
