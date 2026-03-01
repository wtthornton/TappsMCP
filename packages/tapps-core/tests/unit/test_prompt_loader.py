"""Tests for the base prompt loader (tapps-core).

Only the core pipeline prompt tests are included here.
MCP-specific tests (agents templates, platform rules, frozen exe fallback)
remain in the tapps-mcp package.
"""

from __future__ import annotations

import pytest

from tapps_core.prompts.prompt_loader import (
    ENGAGEMENT_LEVELS,
    list_stages,
    load_handoff_template,
    load_overview,
    load_runlog_template,
    load_stage_prompt,
)


class TestListStages:
    def test_returns_five_stages(self) -> None:
        stages = list_stages()
        assert len(stages) == 5

    def test_stage_order(self) -> None:
        stages = list_stages()
        assert stages == ["discover", "research", "develop", "validate", "verify"]


class TestLoadStagePrompt:
    @pytest.mark.parametrize("stage", ["discover", "research", "develop", "validate", "verify"])
    def test_loads_each_stage(self, stage: str) -> None:
        content = load_stage_prompt(stage)
        assert isinstance(content, str)
        assert len(content) > 100

    @pytest.mark.parametrize("stage", ["discover", "research", "develop", "validate", "verify"])
    def test_stage_contains_required_sections(self, stage: str) -> None:
        content = load_stage_prompt(stage)
        assert "## Objective" in content
        assert "## Allowed Tools" in content
        assert "## Constraints" in content
        assert "## Exit Criteria" in content

    def test_invalid_stage_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid stage"):
            load_stage_prompt("invalid")

    def test_empty_stage_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid stage"):
            load_stage_prompt("")


class TestLoadOverview:
    def test_returns_content(self) -> None:
        content = load_overview()
        assert isinstance(content, str)
        assert len(content) > 100

    def test_contains_all_stages(self) -> None:
        content = load_overview()
        for stage in ["Discover", "Research", "Develop", "Validate", "Verify"]:
            assert stage in content

    def test_contains_tool_names(self) -> None:
        content = load_overview()
        assert "tapps_server_info" in content
        assert "tapps_checklist" in content


class TestLoadTemplates:
    def test_handoff_template(self) -> None:
        content = load_handoff_template()
        assert "TAPPS Handoff" in content
        assert "Stage: Discover" in content

    def test_runlog_template(self) -> None:
        content = load_runlog_template()
        assert "TAPPS Run Log" in content


class TestEngagementLevels:
    def test_engagement_levels_constant(self) -> None:
        assert ENGAGEMENT_LEVELS == ("high", "medium", "low")
