"""Golden-string consistency across agent_contract, usage gaps, hooks, and skills."""

from __future__ import annotations

from tapps_mcp.pipeline.agent_contract import (
    CHECKLIST_SKIPPED_REC,
    LOOKUP_GAP_RETRO_NOTE,
    MEMORY_RECALL_SESSION_START,
    POST_EDIT_IMPORT_LOOKUP_BASH,
    SESSION_START_CHECKLIST_GAP_HINT,
    STOP_FINISH_REMINDER,
    STOP_GAP_FOLLOWUP_DEFAULT,
    SUBAGENT_START_INTRO,
    SUBAGENT_START_TOOLS_LINE,
    VALIDATION_QUICK_VS_BATCH,
)
from tapps_mcp.pipeline.platform_hook_templates import CLAUDE_HOOK_SCRIPTS
from tapps_mcp.pipeline.platform_rules import CURSOR_RULE_TEMPLATES
from tapps_mcp.pipeline.platform_skills import CLAUDE_SKILLS, CURSOR_SKILLS
from tapps_mcp.tools.usage import compute_gaps, format_session_start_gap_hint, format_stop_gap_followup
from tapps_mcp.pipeline.agent_contract import lookup_gap_recommendation


class TestUsageGapStringsMatchContract:
    def test_checklist_skipped_recommendation(self, tmp_path) -> None:
        metrics = tmp_path / ".tapps-mcp"
        metrics.mkdir(parents=True)
        (metrics / "loop-metrics.jsonl").write_text(
            '{"ts":1,"files_edited":["src/a.py"],"gate_skipped_files":["src/a.py"],'
            '"lookup_docs_called":false,"checklist_called":false,"tools_used":[]}\n',
            encoding="utf-8",
        )
        report = compute_gaps(tmp_path, called_tools={"tapps_session_start"})
        assert "checklist_skipped" in report["gaps"]
        assert CHECKLIST_SKIPPED_REC in report["recommendations"]

    def test_session_start_checklist_hint(self, tmp_path) -> None:
        metrics = tmp_path / ".tapps-mcp"
        metrics.mkdir(parents=True)
        (metrics / ".completion-gate-violations.jsonl").write_text(
            '{"ts":1,"mode":"warn","reasons":["CHECKLIST_MISSING"],"files_edited":["a.py"]}\n',
            encoding="utf-8",
        )
        hint = format_session_start_gap_hint(tmp_path)
        assert hint == SESSION_START_CHECKLIST_GAP_HINT

    def test_stop_followup_surfaces_validation_remediation(self, tmp_path) -> None:
        metrics = tmp_path / ".tapps-mcp"
        metrics.mkdir(parents=True)
        (metrics / "loop-metrics.jsonl").write_text(
            '{"ts":1,"files_edited":["src/a.py"],"gate_skipped_files":["src/a.py"],'
            '"lookup_docs_called":false,"checklist_called":false,"tools_used":[]}\n',
            encoding="utf-8",
        )
        followup = format_stop_gap_followup(tmp_path, called_tools=set(), mode="warn")
        assert followup is not None
        assert "TappsMCP pipeline gaps" in followup
        assert "tapps_validate_changed" in followup

    def test_stop_gap_followup_default_constant(self) -> None:
        assert "tapps-finish-task" in STOP_GAP_FOLLOWUP_DEFAULT

    def test_lookup_gap_recommendation_retro_note(self) -> None:
        rec = lookup_gap_recommendation(["fastapi"], generic=False)
        assert LOOKUP_GAP_RETRO_NOTE in rec


class TestGeneratedSurfacesEchoContract:
    def test_claude_stop_hook_finish_reminder(self) -> None:
        assert STOP_FINISH_REMINDER in CLAUDE_HOOK_SCRIPTS["tapps-stop.sh"]

    def test_claude_post_edit_lookup_phrasing(self) -> None:
        assert POST_EDIT_IMPORT_LOOKUP_BASH in CLAUDE_HOOK_SCRIPTS["tapps-post-edit.sh"]
        assert "before using those APIs" in POST_EDIT_IMPORT_LOOKUP_BASH

    def test_subagent_start_no_legacy_tapps_memory_mcp(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS["tapps-subagent-start.sh"]
        assert SUBAGENT_START_INTRO in script
        assert SUBAGENT_START_TOOLS_LINE in script
        assert "mcp__tapps-mcp__tapps_memory" not in script
        assert "nlt-memory" in script

    def test_cursor_pipeline_memory_and_validation(self) -> None:
        body = CURSOR_RULE_TEMPLATES["tapps-pipeline.mdc"]
        assert MEMORY_RECALL_SESSION_START in body
        assert "/tapps-finish-task" in body

    def test_finish_task_skill_has_adr_0021_and_checklist(self) -> None:
        for skills in (CURSOR_SKILLS, CLAUDE_SKILLS):
            body = skills["tapps-finish-task"]
            assert "ADR-0021" in body
            assert "usage_gaps" in body
            assert "tapps_checklist" in body

    def test_validation_semantics_in_contract(self) -> None:
        assert "tapps_quick_check" in VALIDATION_QUICK_VS_BATCH
        assert "tapps_validate_changed" in VALIDATION_QUICK_VS_BATCH
