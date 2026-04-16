"""Tests for handoff rendering and parsing."""

from datetime import datetime

from tapps_mcp.pipeline.handoff import (
    parse_handoff,
    render_handoff,
    render_runlog_entry,
)
from tapps_mcp.pipeline.models import (
    HandoffState,
    PipelineStage,
    RunlogEntry,
    StageResult,
)


class TestRenderHandoff:
    def test_minimal(self):
        state = HandoffState(
            current_stage=PipelineStage.DISCOVER,
            objective="Test task",
        )
        md = render_handoff(state)
        assert "# TAPPS Handoff" in md
        assert "**Objective:** Test task" in md

    def test_with_stage_results(self):
        state = HandoffState(
            current_stage=PipelineStage.DEVELOP,
            objective="Add feature",
            stage_results=[
                StageResult(
                    stage=PipelineStage.DISCOVER,
                    completed_at=datetime(2026, 1, 15, 10, 0, 0),
                    tools_called=["tapps_server_info", "tapps_project_profile"],
                    findings=["Python project", "pytest detected"],
                    decisions=["Use standard preset"],
                ),
            ],
        )
        md = render_handoff(state)
        assert "## Stage: Discover" in md
        assert "tapps_server_info, tapps_project_profile" in md
        assert "- Python project" in md
        assert "- Use standard preset" in md

    def test_renders_all_sections(self):
        state = HandoffState(
            current_stage=PipelineStage.VALIDATE,
            objective="Fix bug",
            stage_results=[
                StageResult(
                    stage=PipelineStage.DEVELOP,
                    completed_at=datetime(2026, 1, 15, 11, 0, 0),
                    tools_called=["tapps_score_file"],
                    findings=["Score 82"],
                    files_in_scope=["src/auth.py"],
                    open_questions=["Need to review tests?"],
                ),
            ],
        )
        md = render_handoff(state)
        assert "**Files in scope:**" in md
        assert "- src/auth.py" in md
        assert "**Open questions:**" in md
        assert "- Need to review tests?" in md


class TestRenderRunlogEntry:
    def test_format(self):
        entry = RunlogEntry(
            timestamp=datetime(2026, 1, 15, 10, 0, 0),
            stage=PipelineStage.DISCOVER,
            action="tapps_server_info",
            details="v0.1.0 running",
        )
        line = render_runlog_entry(entry)
        assert "[2026-01-15T10:00:00]" in line
        assert "[discover]" in line
        assert "tapps_server_info" in line
        assert "v0.1.0 running" in line


class TestParseHandoff:
    def test_round_trip(self):
        original = HandoffState(
            current_stage=PipelineStage.DEVELOP,
            objective="Add login feature",
            stage_results=[
                StageResult(
                    stage=PipelineStage.DISCOVER,
                    completed_at=datetime(2026, 1, 15, 10, 0, 0),
                    tools_called=["tapps_server_info"],
                    findings=["Python FastAPI project"],
                    decisions=["Use strict preset"],
                ),
                StageResult(
                    stage=PipelineStage.RESEARCH,
                    completed_at=datetime(2026, 1, 15, 10, 5, 0),
                    tools_called=["tapps_lookup_docs", "tapps_dependency_scan"],
                    findings=["FastAPI uses Depends() for DI"],
                    decisions=["Use JWT auth"],
                ),
            ],
        )
        md = render_handoff(original)
        parsed = parse_handoff(md)

        assert parsed.objective == "Add login feature"
        assert len(parsed.stage_results) == 2
        assert parsed.stage_results[0].stage == PipelineStage.DISCOVER
        assert parsed.stage_results[1].stage == PipelineStage.RESEARCH
        assert "Python FastAPI project" in parsed.stage_results[0].findings
        assert "Use JWT auth" in parsed.stage_results[1].decisions

    def test_parses_objective(self):
        md = "# TAPPS Handoff\n\n**Objective:** Fix authentication bug\n"
        parsed = parse_handoff(md)
        assert parsed.objective == "Fix authentication bug"

    def test_empty_content(self):
        parsed = parse_handoff("")
        assert parsed.objective == ""
        assert parsed.stage_results == []

    def test_parses_tools_called(self):
        md = """# TAPPS Handoff

**Objective:** Test

## Stage: Discover

**Completed:** 2026-01-15T10:00:00
**Tools called:** tapps_server_info, tapps_project_profile

**Findings:**
- Found stuff

---
"""
        parsed = parse_handoff(md)
        assert len(parsed.stage_results) == 1
        result = parsed.stage_results[0]
        assert "tapps_server_info" in result.tools_called
        assert "tapps_project_profile" in result.tools_called
