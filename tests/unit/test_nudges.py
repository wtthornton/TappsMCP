"""Tests for the nudge engine (next-step guidance system)."""

from __future__ import annotations

from typing import Any

import pytest

from tapps_mcp.common.nudges import (
    _MAX_NUDGES,
    compute_next_steps,
    compute_pipeline_progress,
)
from tapps_mcp.tools.checklist import CallTracker


@pytest.fixture(autouse=True)
def _reset_tracker() -> None:  # type: ignore[misc]
    """Reset CallTracker before every test."""
    CallTracker.reset()


# ---------------------------------------------------------------------------
# compute_next_steps
# ---------------------------------------------------------------------------


class TestComputeNextSteps:
    """Tests for compute_next_steps()."""

    def test_server_info_nudges_project_profile(self) -> None:
        CallTracker.record("tapps_server_info")
        steps = compute_next_steps("tapps_server_info")
        assert any("tapps_project_profile" in s for s in steps)

    def test_server_info_no_nudge_when_profile_called(self) -> None:
        CallTracker.record("tapps_server_info")
        CallTracker.record("tapps_project_profile")
        steps = compute_next_steps("tapps_server_info")
        assert not any("tapps_project_profile" in s for s in steps)

    def test_server_info_no_nudge_when_session_start_called(self) -> None:
        CallTracker.record("tapps_server_info")
        CallTracker.record("tapps_session_start")
        steps = compute_next_steps("tapps_server_info")
        assert not any("tapps_project_profile" in s for s in steps)

    def test_score_file_nudges_quality_gate(self) -> None:
        CallTracker.record("tapps_score_file")
        steps = compute_next_steps("tapps_score_file")
        assert any("tapps_quality_gate" in s for s in steps)

    def test_score_file_no_gate_nudge_when_already_called(self) -> None:
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_quality_gate")
        steps = compute_next_steps("tapps_score_file")
        assert not any("tapps_quality_gate" in s for s in steps)

    def test_score_file_security_nudge_when_issues(self) -> None:
        CallTracker.record("tapps_score_file")
        steps = compute_next_steps(
            "tapps_score_file",
            {"security_issue_count": 3},
        )
        assert any("tapps_security_scan" in s for s in steps)

    def test_score_file_no_security_nudge_when_zero_issues(self) -> None:
        CallTracker.record("tapps_score_file")
        steps = compute_next_steps(
            "tapps_score_file",
            {"security_issue_count": 0},
        )
        assert not any("WARNING" in s for s in steps)

    def test_quality_gate_failed_nudge(self) -> None:
        CallTracker.record("tapps_quality_gate")
        steps = compute_next_steps(
            "tapps_quality_gate",
            {"gate_passed": False},
        )
        assert any("FAILED" in s for s in steps)

    def test_quality_gate_passed_nudges_checklist(self) -> None:
        CallTracker.record("tapps_quality_gate")
        steps = compute_next_steps(
            "tapps_quality_gate",
            {"gate_passed": True},
        )
        assert any("tapps_checklist" in s for s in steps)

    def test_quality_gate_passed_no_checklist_nudge_when_called(self) -> None:
        CallTracker.record("tapps_quality_gate")
        CallTracker.record("tapps_checklist")
        steps = compute_next_steps(
            "tapps_quality_gate",
            {"gate_passed": True},
        )
        assert not any("tapps_checklist" in s for s in steps)

    def test_max_nudges_enforced(self) -> None:
        # With nothing called, score_file should generate gate nudge + lookup reminder
        CallTracker.record("tapps_score_file")
        steps = compute_next_steps("tapps_score_file")
        assert len(steps) <= _MAX_NUDGES

    def test_global_lookup_nudge_for_non_discover_tool(self) -> None:
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_quality_gate")
        steps = compute_next_steps("tapps_score_file")
        assert any("tapps_lookup_docs" in s for s in steps)

    def test_no_global_lookup_nudge_for_discover_tool(self) -> None:
        CallTracker.record("tapps_server_info")
        steps = compute_next_steps("tapps_server_info")
        assert not any("REMINDER" in s for s in steps)

    def test_no_global_lookup_nudge_when_already_called(self) -> None:
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_lookup_docs")
        steps = compute_next_steps("tapps_score_file")
        assert not any("REMINDER" in s for s in steps)

    def test_no_global_lookup_nudge_for_lookup_tool(self) -> None:
        CallTracker.record("tapps_lookup_docs")
        steps = compute_next_steps("tapps_lookup_docs")
        assert not any("REMINDER" in s for s in steps)

    def test_empty_tracker_returns_steps(self) -> None:
        steps = compute_next_steps("tapps_score_file")
        assert len(steps) > 0

    def test_unknown_tool_returns_global_nudges_only(self) -> None:
        steps = compute_next_steps("tapps_nonexistent_tool")
        # Should still get the global lookup reminder
        assert any("tapps_lookup_docs" in s for s in steps)

    def test_checklist_incomplete_nudge(self) -> None:
        CallTracker.record("tapps_checklist")
        steps = compute_next_steps("tapps_checklist", {"complete": False})
        assert any("incomplete" in s.lower() for s in steps)

    def test_session_start_nudges_lookup(self) -> None:
        CallTracker.record("tapps_session_start")
        steps = compute_next_steps("tapps_session_start")
        assert any("tapps_lookup_docs" in s for s in steps)


# ---------------------------------------------------------------------------
# compute_pipeline_progress
# ---------------------------------------------------------------------------


class TestComputePipelineProgress:
    """Tests for compute_pipeline_progress()."""

    def test_empty_tracker(self) -> None:
        progress = compute_pipeline_progress()
        assert progress["completed_stages"] == []
        assert progress["next_stage"] == "discover"
        assert progress["tools_called"] == []
        assert progress["total_calls"] == 0

    def test_discover_stage_completed(self) -> None:
        CallTracker.record("tapps_server_info")
        progress = compute_pipeline_progress()
        assert "discover" in progress["completed_stages"]
        assert progress["next_stage"] == "research"

    def test_multiple_stages_completed(self) -> None:
        CallTracker.record("tapps_server_info")
        CallTracker.record("tapps_lookup_docs")
        CallTracker.record("tapps_score_file")
        progress = compute_pipeline_progress()
        assert "discover" in progress["completed_stages"]
        assert "research" in progress["completed_stages"]
        assert "develop" in progress["completed_stages"]

    def test_all_stages_completed(self) -> None:
        CallTracker.record("tapps_server_info")
        CallTracker.record("tapps_lookup_docs")
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_quality_gate")
        CallTracker.record("tapps_checklist")
        progress = compute_pipeline_progress()
        assert len(progress["completed_stages"]) == 5
        assert progress["next_stage"] is None

    def test_tools_called_list(self) -> None:
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_quality_gate")
        progress = compute_pipeline_progress()
        assert "tapps_score_file" in progress["tools_called"]
        assert "tapps_quality_gate" in progress["tools_called"]

    def test_total_calls_counts_duplicates(self) -> None:
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_score_file")
        progress = compute_pipeline_progress()
        assert progress["total_calls"] == 3


# ---------------------------------------------------------------------------
# _with_nudges integration (server helper)
# ---------------------------------------------------------------------------


class TestWithNudges:
    """Test the _with_nudges server helper."""

    def test_injects_next_steps(self) -> None:
        from tapps_mcp.server import _with_nudges

        CallTracker.record("tapps_score_file")
        response: dict[str, Any] = {
            "success": True,
            "data": {"file_path": "test.py"},
        }
        result = _with_nudges("tapps_score_file", response)
        assert "next_steps" in result["data"]
        assert isinstance(result["data"]["next_steps"], list)

    def test_injects_pipeline_progress(self) -> None:
        from tapps_mcp.server import _with_nudges

        CallTracker.record("tapps_score_file")
        response: dict[str, Any] = {
            "success": True,
            "data": {"file_path": "test.py"},
        }
        result = _with_nudges("tapps_score_file", response)
        assert "pipeline_progress" in result["data"]

    def test_skips_error_responses(self) -> None:
        from tapps_mcp.server import _with_nudges

        response: dict[str, Any] = {
            "success": False,
            "error": {"code": "test", "message": "test"},
        }
        result = _with_nudges("tapps_score_file", response)
        assert "data" not in result or "next_steps" not in result.get("data", {})

    def test_passes_context_through(self) -> None:
        from tapps_mcp.server import _with_nudges

        CallTracker.record("tapps_quality_gate")
        response: dict[str, Any] = {
            "success": True,
            "data": {"passed": False},
        }
        result = _with_nudges(
            "tapps_quality_gate",
            response,
            {"gate_passed": False},
        )
        steps = result["data"].get("next_steps", [])
        assert any("FAILED" in s for s in steps)
