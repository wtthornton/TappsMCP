"""Emitted-body assertions for the orchestration-prompt skill: research preflight and workspace scope fence (TAP-6855, TAP-6856).

Split per topic rather than appended to ``test_platform_skills.py``: that module
already sits at the maintainability-index gate floor, and a single combined module
for this cluster reaches it too.
"""

from __future__ import annotations

from tapps_mcp.pipeline.platform_skills import CLAUDE_SKILLS



class TestResearchPreflightSection0c:
    """TAP-6855 — a research pass must run before the Goal (§1) is pinned."""

    def test_section_0c_present_between_0b_and_1(self) -> None:
        body = CLAUDE_SKILLS["orchestration-prompt"]
        assert "### 0c." in body
        pos_0b = body.index("### 0b.")
        pos_0c = body.index("### 0c.")
        pos_1 = body.index("### 1. Pin the Goal")
        assert pos_0b < pos_0c < pos_1

    def test_route_order_and_unverified_marking(self) -> None:
        body = CLAUDE_SKILLS["orchestration-prompt"]
        section = body.split("### 0c.", 1)[1].split("\n### 1.", 1)[0]
        assert "`tapps_lookup_docs`" in section
        assert "`tapps_research`" in section
        assert "raw web" in section
        assert "`UNVERIFIED`" in section

    def test_dispatched_to_explore_subagents_never_read_directly(self) -> None:
        body = CLAUDE_SKILLS["orchestration-prompt"]
        section = body.split("### 0c.", 1)[1].split("\n### 1.", 1)[0]
        assert "`Explore`" in section
        assert "never read search results" in section

    def test_return_schema_names_exactly_four_fields(self) -> None:
        body = CLAUDE_SKILLS["orchestration-prompt"]
        section = body.split("### 0c.", 1)[1].split("\n### 1.", 1)[0]
        for field in ("`claim`", "`source`", "`confidence`", "`contradicts`"):
            assert field in section, f"missing {field!r} in section 0c return schema"

    def test_contradicts_adjudicated_in_writing_with_reopen_trigger(self) -> None:
        body = CLAUDE_SKILLS["orchestration-prompt"]
        section = body.split("### 0c.", 1)[1].split("\n### 1.", 1)[0]
        assert "adjudicated in writing" in section
        assert "reopen trigger" in section
        assert "never silently dropped" in section

    def test_nonverified_findings_flow_into_unverified_assumptions(self) -> None:
        body = CLAUDE_SKILLS["orchestration-prompt"]
        section = body.split("### 0c.", 1)[1].split("\n### 1.", 1)[0]
        assert "`## Unverified" in section

    def test_names_session_start_as_prerequisite(self) -> None:
        body = CLAUDE_SKILLS["orchestration-prompt"]
        section = body.split("### 0c.", 1)[1].split("\n### 1.", 1)[0]
        assert "`tapps_session_start()`" in section
        assert "PreToolUse hook" in section

class TestWorkspaceScopeFence:
    """TAP-6856 — a fleet-registry row is not an in-scope target by itself."""

    def _scope_bullet(self, body: str) -> str:
        section = body.split("- **Scope**", 1)[1]
        return section.split("\n- **Budget**", 1)[0]

    def test_workspace_dir_list_is_the_scope_fence(self) -> None:
        body = CLAUDE_SKILLS["orchestration-prompt"]
        bullet = self._scope_bullet(body)
        assert "workspace directory list is the scope" in bullet
        assert "not an in-scope target by itself" in bullet

    def test_naming_a_repo_is_inert_boundary_is_a_path_argument(self) -> None:
        body = CLAUDE_SKILLS["orchestration-prompt"]
        bullet = self._scope_bullet(body)
        assert "Naming a repo" in bullet
        assert "is inert" in bullet
        assert "path argument" in bullet

    def test_audit_method_greps_path_arguments_not_repo_names(self) -> None:
        body = CLAUDE_SKILLS["orchestration-prompt"]
        bullet = self._scope_bullet(body)
        assert "grepping the transcript for path" in bullet
        assert "never for repo names" in bullet

    def test_fanout_briefs_name_paths_and_report_paths_read(self) -> None:
        body = CLAUDE_SKILLS["orchestration-prompt"]
        bullet = self._scope_bullet(body)
        assert "fan-out brief names the permitted paths" in bullet
        assert "paths it actually read" in bullet

    def test_out_of_scope_work_is_hard_stop_not_silent_skip(self) -> None:
        body = CLAUDE_SKILLS["orchestration-prompt"]
        bullet = self._scope_bullet(body)
        assert "hard-stop to surface immediately" in bullet
        assert "never a\n  silent skip" in bullet or "never a silent skip" in bullet

    def test_workspace_manifest_instruction_distinguishes_registry_from_scope(self) -> None:
        body = CLAUDE_SKILLS["orchestration-prompt"]
        output = body.split("## Output", 1)[1].split("\n## ", 1)[0]
        assert "registry, not a" in output
        assert "scope grant" in output
