"""Tests for recommended_workflows in tapps_session_start (TAP-3929)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.tools.session_start_helpers import build_recommended_workflows


class TestBuildRecommendedWorkflows:
    def test_developer_bundle_lists_finish_task_and_linear_read(self, tmp_path: Path) -> None:
        result = build_recommended_workflows(
            tmp_path,
            engagement_level="medium",
            mcp_bundle="developer",
        )
        names = [entry["skill"] for entry in result["workflows"]]
        assert "tapps-finish-task" in names
        assert "linear-read" in names
        finish = next(w for w in result["workflows"] if w["skill"] == "tapps-finish-task")
        assert finish["slash"] == "/tapps-finish-task"
        assert finish["when"]
        assert "SKILL" not in finish["when"]

    def test_low_engagement_filters_to_core_workflows(self, tmp_path: Path) -> None:
        result = build_recommended_workflows(
            tmp_path,
            engagement_level="low",
            mcp_bundle="developer",
        )
        names = {entry["skill"] for entry in result["workflows"]}
        assert "tapps-finish-task" in names
        assert "linear-read" not in names

    def test_no_workflow_marked_user_invocable_only(self, tmp_path: Path) -> None:
        """Every generated skill is model-invocable, so no workflow tells the
        agent to hand the slash command back to the user."""
        result = build_recommended_workflows(
            tmp_path,
            engagement_level="medium",
            mcp_bundle="full",
        )
        handoff = next(w for w in result["workflows"] if w["skill"] == "tapps-handoff-session")
        assert "user-only" not in handoff["when"]
        for workflow in result["workflows"]:
            assert "user_invocable_only" not in workflow
