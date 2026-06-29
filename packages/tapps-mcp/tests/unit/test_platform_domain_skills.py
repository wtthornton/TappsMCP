"""Tests for domain/flow skill templates."""

from __future__ import annotations

from tapps_mcp.pipeline.platform_domain_skills import CLAUDE_DOMAIN_SKILLS, CURSOR_DOMAIN_SKILLS
from tapps_mcp.pipeline.platform_skills import CLAUDE_SKILLS, CURSOR_SKILLS


class TestPlatformDomainSkills:
    def test_merged_into_platform_skills(self) -> None:
        for key in CLAUDE_DOMAIN_SKILLS:
            assert key in CLAUDE_SKILLS
        for key in CURSOR_DOMAIN_SKILLS:
            assert key in CURSOR_SKILLS

    def test_descriptions_have_use_when(self) -> None:
        for body in CLAUDE_DOMAIN_SKILLS.values():
            assert "Use when" in body

    def test_domain_testing_mentions_playbook_tool(self) -> None:
        assert "tapps_domain_playbook" in CLAUDE_DOMAIN_SKILLS["tapps-domain-testing"]
