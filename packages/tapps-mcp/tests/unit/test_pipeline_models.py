"""Tests for pipeline data models."""

from datetime import datetime

import pytest

from tapps_mcp.pipeline.models import (
    STAGE_ORDER,
    STAGE_TOOLS,
    HandoffState,
    PipelineStage,
    RunlogEntry,
    StageResult,
)


class TestPipelineStage:
    def test_all_values(self):
        values = {s.value for s in PipelineStage}
        assert values == {"discover", "research", "develop", "validate", "verify"}

    def test_from_string(self):
        assert PipelineStage("discover") == PipelineStage.DISCOVER

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            PipelineStage("invalid")


class TestStageOrder:
    def test_five_stages(self):
        assert len(STAGE_ORDER) == 5

    def test_correct_order(self):
        assert STAGE_ORDER[0] == PipelineStage.DISCOVER
        assert STAGE_ORDER[-1] == PipelineStage.VERIFY


class TestStageTools:
    def test_all_stages_have_tools(self):
        for stage in PipelineStage:
            assert stage in STAGE_TOOLS
            assert len(STAGE_TOOLS[stage]) > 0

    def test_discover_tools(self):
        tools = STAGE_TOOLS[PipelineStage.DISCOVER]
        assert "tapps_server_info" in tools
        assert "tapps_session_start" in tools

    def test_verify_tools(self):
        tools = STAGE_TOOLS[PipelineStage.VERIFY]
        assert "tapps_checklist" in tools


class TestStageResult:
    def test_minimal(self):
        result = StageResult(
            stage=PipelineStage.DISCOVER,
            completed_at=datetime(2026, 1, 15, 10, 0, 0),
        )
        assert result.stage == PipelineStage.DISCOVER
        assert result.tools_called == []
        assert result.findings == []
        assert result.decisions == []
        assert result.files_in_scope == []
        assert result.open_questions == []

    def test_full(self):
        result = StageResult(
            stage=PipelineStage.VALIDATE,
            completed_at=datetime(2026, 1, 15, 10, 5, 0),
            tools_called=["tapps_score_file", "tapps_quality_gate"],
            findings=["Score: 85", "Gate passed"],
            decisions=["Accept warning on complexity"],
            files_in_scope=["src/main.py"],
            open_questions=["Review perf later?"],
        )
        assert len(result.tools_called) == 2
        assert len(result.findings) == 2


class TestHandoffState:
    def test_minimal(self):
        state = HandoffState(
            current_stage=PipelineStage.DISCOVER,
            objective="Add login feature",
        )
        assert state.current_stage == PipelineStage.DISCOVER
        assert state.objective == "Add login feature"
        assert state.stage_results == []
        assert state.next_stage_instructions == ""

    def test_with_results(self):
        state = HandoffState(
            current_stage=PipelineStage.DEVELOP,
            objective="Fix auth bug",
            stage_results=[
                StageResult(
                    stage=PipelineStage.DISCOVER,
                    completed_at=datetime(2026, 1, 15, 10, 0, 0),
                    tools_called=["tapps_server_info"],
                ),
            ],
            next_stage_instructions="Run full scoring on auth.py",
        )
        assert len(state.stage_results) == 1
        assert state.next_stage_instructions != ""


class TestRunlogEntry:
    def test_creation(self):
        entry = RunlogEntry(
            timestamp=datetime(2026, 1, 15, 10, 0, 0),
            stage=PipelineStage.DISCOVER,
            action="tapps_server_info",
            details="v0.1.0, ruff+mypy installed",
        )
        assert entry.stage == PipelineStage.DISCOVER
        assert entry.action == "tapps_server_info"
