"""Tests for the orchestration-prompt skill body (TAP-6854 hardening cluster).

Split out of ``test_platform_skills.py`` rather than appended to it: that module
already sits at the maintainability-index gate floor, so growing it regresses its
ratchet instead of testing anything new.
"""

from __future__ import annotations

import pytest

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


class TestFieldRulesTwelve:
    """TAP-6858 — twelve field rules absent from the method, verified by grep."""

    def _field_rules_section(self) -> str:
        body = CLAUDE_SKILLS["orchestration-prompt"]
        section = body.split("## Field rules", 1)[1]
        return section.split("\n## Rulings", 1)[0]

    @pytest.mark.parametrize(
        "marker",
        [
            "known-bad and a known-positive",
            "Green-by-citation is distinct from green-by-suppression",
            "verifier's control is the pre-change tree",
            "reports the PR's own CI by name and state",
            "measured number is a floor until the instrument is proven",
            "Prove freshness per deployed layer and diff config per key hash",
            "blast-radius preflight before any state-touching verify step",
            "separates queried-and-got-zero from the-query-failed",
            "Round-2 fix prompts gate on the delta and also sweep siblings by symbol",
            "disposition disjunction with",
            "Agreement among artifacts is not corroboration",
            "structural limits are the author's problem",
        ],
    )
    def test_each_field_rule_present(self, marker: str) -> None:
        section = self._field_rules_section()
        assert marker in section, f"missing field rule marker {marker!r}"

    def test_field_rules_are_a_numbered_list_of_twelve(self) -> None:
        section = self._field_rules_section()
        for n in range(1, 13):
            assert f"\n{n}. " in section or section.startswith(f"{n}. ")


class TestVerifierTierAuthorityAndRulings:
    """TAP-6859 — the proof-shape table is authoritative; eight rulings pin edge cases."""

    def test_no_restatement_of_losing_verifier_tier_formulation(self) -> None:
        body = CLAUDE_SKILLS["orchestration-prompt"]
        assert "inherit the runner at high effort" not in body

    def test_authority_statement_present(self) -> None:
        body = CLAUDE_SKILLS["orchestration-prompt"]
        assert "This table is authoritative" in body
        assert "pin explicitly, for a named reason" in body
        assert "never" in body.split("This table is authoritative", 1)[1][:300]

    def _rulings_section(self) -> str:
        body = CLAUDE_SKILLS["orchestration-prompt"]
        section = body.split("## Rulings", 1)[1]
        return section.split("\n## Guardrails", 1)[0]

    @pytest.mark.parametrize(
        "marker",
        [
            "may author a narrow fix and stay on as re-verifier",
            "data-loss carve-out",
            "Shared quota is a coupling the independence test",
            "Billing topology",
            "Content-diff freshness",
            "Cheap-tier transcription",
            "one named artifact handover to the operator",
            "reserved for the coordination-versus-execution distinction",
        ],
    )
    def test_each_ruling_present(self, marker: str) -> None:
        section = self._rulings_section()
        assert marker in section, f"missing ruling marker {marker!r}"

    def test_eight_rulings_numbered(self) -> None:
        section = self._rulings_section()
        for n in range(1, 9):
            assert f"\n{n}. " in section
