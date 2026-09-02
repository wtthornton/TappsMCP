"""Tests for the orchestration-prompt skill body (TAP-6854 hardening cluster).

Split out of ``test_platform_skills.py`` rather than appended to it: that module
already sits at the maintainability-index gate floor, so growing it regresses its
ratchet instead of testing anything new.
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
