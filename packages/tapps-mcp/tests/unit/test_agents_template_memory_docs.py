"""Tests for Memory Systems section in AGENTS.md templates (Epic 34.6)."""

from __future__ import annotations

import pytest

from tapps_mcp.prompts.prompt_loader import load_agents_template, load_platform_rules


class TestMemorySystemsSection:
    """Verify each AGENTS.md template includes memory documentation."""

    @pytest.mark.parametrize("level", ["high", "medium", "low"])
    def test_template_contains_memory_systems_section(self, level: str) -> None:
        """Each engagement-level template must have a '## Memory systems' heading."""
        content = load_agents_template(engagement_level=level)
        assert "## Memory systems" in content

    def test_high_template_contains_required(self) -> None:
        """High engagement template must use REQUIRED language."""
        content = load_agents_template(engagement_level="high")
        assert "REQUIRED" in content.split("## Memory systems")[1].split("##")[0]

    def test_low_template_contains_consider(self) -> None:
        """Low engagement template must use 'Consider' language."""
        content = load_agents_template(engagement_level="low")
        assert "Consider" in content.split("## Memory systems")[1].split("##")[0]

    @pytest.mark.parametrize("level", ["high", "medium", "low"])
    def test_template_mentions_both_memory_systems(self, level: str) -> None:
        """Each template must mention both tapps_memory and MEMORY.md."""
        content = load_agents_template(engagement_level=level)
        memory_section = content.split("## Memory systems")[1].split("##")[0]
        assert "tapps_memory" in memory_section
        assert "MEMORY.md" in memory_section

    @pytest.mark.parametrize("level", ["high", "medium", "low"])
    def test_template_documents_cross_session_handoff(self, level: str) -> None:
        """Each AGENTS.md template must teach the cross-session handoff pattern.

        Sessions often need to pass tokens, IDs, or short payloads to a later
        session in the same project. The correct path is `tapps_memory(action="save",
        scope="project", ...)`, not stdout. If this guidance disappears from a
        template the next time someone refactors it, agents will fall back to
        printing secrets to stdout — drift catch.
        """
        content = load_agents_template(engagement_level=level)
        assert "Cross-session handoff" in content, (
            f"AGENTS.md template ({level}) is missing the 'Cross-session handoff' "
            "guidance. See packages/tapps-mcp/src/tapps_mcp/prompts/agents_template*.md."
        )
        # Ensure it actually points at the save action with project scope, not just
        # mentioning the phrase in passing.
        assert 'tapps_memory(action="save"' in content
        assert "project" in content.split("Cross-session handoff")[1].split("##")[0]

    @pytest.mark.parametrize("platform", ["claude", "cursor"])
    @pytest.mark.parametrize("level", ["high", "medium", "low"])
    def test_platform_rules_document_cross_session_handoff(
        self, platform: str, level: str
    ) -> None:
        """Each platform-rules template (CLAUDE.md / .cursorrules) must document
        the cross-session handoff pattern. Same drift-catch as the AGENTS.md test."""
        content = load_platform_rules(platform=platform, engagement_level=level)
        assert "Cross-session handoff" in content, (
            f"platform_{platform}_{level}.md is missing 'Cross-session handoff' "
            "guidance. See packages/tapps-mcp/src/tapps_mcp/prompts/platform_*.md."
        )
        assert 'tapps_memory(action="save"' in content
