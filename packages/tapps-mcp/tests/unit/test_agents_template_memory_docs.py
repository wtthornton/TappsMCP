"""Tests for Memory Systems section in AGENTS.md templates (Epic 34.6)."""

from __future__ import annotations

import pytest

from tapps_mcp.prompts.prompt_loader import load_agents_template


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
