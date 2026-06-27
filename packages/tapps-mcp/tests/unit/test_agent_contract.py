"""Agent contract consistency — shared hints, skills, and templates."""

from __future__ import annotations

from tapps_mcp.pipeline.agent_contract import (
    POST_EDIT_IMPORT_LOOKUP_BASH,
    POST_EDIT_IMPORT_LOOKUP_MSG,
    STOP_FINISH_REMINDER,
    SUBAGENT_START_TOOLS_LINE,
    finish_task_checklist_and_doc_gaps,
    render_agents_template,
    tapps_mcp_tool_count,
)
from tapps_mcp.pipeline.platform_hook_templates import CLAUDE_HOOK_SCRIPTS, CURSOR_HOOK_SCRIPTS
from tapps_mcp.pipeline.platform_rules import CURSOR_RULE_TEMPLATES
from tapps_mcp.pipeline.platform_skills import (
    CLAUDE_SKILLS,
    CURSOR_SKILLS,
    _FINISH_TASK_CHECKLIST_AND_DOC_GAPS_CLAUDE,
    _FINISH_TASK_CHECKLIST_AND_DOC_GAPS_CURSOR,
)
from tapps_mcp.prompts.prompt_loader import load_agents_template
from tapps_mcp.server import ALL_TOOL_NAMES


class TestAgentContractConstants:
    def test_tool_count_matches_server_catalog(self) -> None:
        assert tapps_mcp_tool_count() == len(ALL_TOOL_NAMES)

    def test_post_edit_lookup_messages_unified(self) -> None:
        assert "before editing" in POST_EDIT_IMPORT_LOOKUP_MSG
        assert "code that uses those APIs" in POST_EDIT_IMPORT_LOOKUP_MSG
        assert "before editing" in POST_EDIT_IMPORT_LOOKUP_BASH
        assert "code that uses those APIs" in POST_EDIT_IMPORT_LOOKUP_BASH
        assert "before declaring complete" not in POST_EDIT_IMPORT_LOOKUP_BASH
        assert "before writing more code" not in POST_EDIT_IMPORT_LOOKUP_BASH

    def test_finish_task_blocks_reference_adr_0021(self) -> None:
        cursor_block = finish_task_checklist_and_doc_gaps(claude_nlt_prefix=False)
        assert "ADR-0021" in cursor_block
        assert "lookup-docs-events" in cursor_block or ".lookup-docs-events" in cursor_block


class TestGeneratedSurfacesIncludeSharedStrings:
    def test_cursor_pipeline_rule_uses_cli_memory(self) -> None:
        body = CURSOR_RULE_TEMPLATES["tapps-pipeline.mdc"]
        assert "tapps_memory(action=" not in body
        assert "uv run tapps-mcp memory search" in body
        assert "/tapps-finish-task" in body

    def test_claude_post_edit_hook_uses_contract_lookup_msg(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS["tapps-post-edit.sh"]
        assert POST_EDIT_IMPORT_LOOKUP_BASH in script

    def test_cursor_after_edit_hook_uses_contract_lookup_msg(self) -> None:
        script = CURSOR_HOOK_SCRIPTS["tapps-after-edit.sh"]
        assert POST_EDIT_IMPORT_LOOKUP_BASH in script

    def test_stop_hook_finish_reminder(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS["tapps-stop.sh"]
        assert STOP_FINISH_REMINDER in script

    def test_subagent_start_uses_contract_memory_story(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS["tapps-subagent-start.sh"]
        assert SUBAGENT_START_TOOLS_LINE in script
        assert "mcp__tapps-mcp__tapps_memory" not in script

    def test_finish_task_skills_use_shared_blocks(self) -> None:
        assert _FINISH_TASK_CHECKLIST_AND_DOC_GAPS_CURSOR in CURSOR_SKILLS["tapps-finish-task"]
        assert _FINISH_TASK_CHECKLIST_AND_DOC_GAPS_CLAUDE in CLAUDE_SKILLS["tapps-finish-task"]

    def test_agents_template_renders_tool_count(self) -> None:
        content = load_agents_template(engagement_level="medium")
        assert "{{TAPPS_MCP_TOOL_COUNT}}" not in content
        assert str(tapps_mcp_tool_count()) in content

    def test_render_agents_template_substitutes_placeholder(self) -> None:
        raw = "Tools: {{TAPPS_MCP_TOOL_COUNT}}\n{{MEMORY_SYSTEMS_BULLET}}\n{{MEMORY_ACTIONS_ACCESS_NOTE}}"
        rendered = render_agents_template(raw)
        assert "{{TAPPS_MCP_TOOL_COUNT}}" not in rendered
        assert "{{MEMORY_SYSTEMS_BULLET}}" not in rendered
        assert "nlt-memory" in rendered
        assert str(tapps_mcp_tool_count()) in rendered

    def test_memory_skill_documents_nlt_memory_facade(self) -> None:
        assert "nlt-memory" in CLAUDE_SKILLS["tapps-memory"]
        assert "TAP-3895" in CLAUDE_SKILLS["tapps-memory"]
        assert "mcp__tapps-mcp__tapps_memory" not in CLAUDE_SKILLS["tapps-memory"].lower()
