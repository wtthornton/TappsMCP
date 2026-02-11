"""Tests for the pipeline prompt loader."""

import pytest

from tapps_mcp.prompts.prompt_loader import (
    list_stages,
    load_handoff_template,
    load_overview,
    load_platform_rules,
    load_runlog_template,
    load_stage_prompt,
)


class TestListStages:
    def test_returns_five_stages(self):
        stages = list_stages()
        assert len(stages) == 5

    def test_stage_order(self):
        stages = list_stages()
        assert stages == ["discover", "research", "develop", "validate", "verify"]


class TestLoadStagePrompt:
    @pytest.mark.parametrize("stage", ["discover", "research", "develop", "validate", "verify"])
    def test_loads_each_stage(self, stage):
        content = load_stage_prompt(stage)
        assert isinstance(content, str)
        assert len(content) > 100

    @pytest.mark.parametrize("stage", ["discover", "research", "develop", "validate", "verify"])
    def test_stage_contains_required_sections(self, stage):
        content = load_stage_prompt(stage)
        assert "## Objective" in content
        assert "## Allowed Tools" in content
        assert "## Constraints" in content
        assert "## Exit Criteria" in content

    def test_invalid_stage_raises(self):
        with pytest.raises(ValueError, match="Invalid stage"):
            load_stage_prompt("invalid")

    def test_empty_stage_raises(self):
        with pytest.raises(ValueError, match="Invalid stage"):
            load_stage_prompt("")


class TestLoadOverview:
    def test_returns_content(self):
        content = load_overview()
        assert isinstance(content, str)
        assert len(content) > 100

    def test_contains_all_stages(self):
        content = load_overview()
        for stage in ["Discover", "Research", "Develop", "Validate", "Verify"]:
            assert stage in content

    def test_contains_tool_names(self):
        content = load_overview()
        assert "tapps_server_info" in content
        assert "tapps_checklist" in content


class TestLoadTemplates:
    def test_handoff_template(self):
        content = load_handoff_template()
        assert "TAPPS Handoff" in content
        assert "Stage: Discover" in content

    def test_runlog_template(self):
        content = load_runlog_template()
        assert "TAPPS Run Log" in content


class TestLoadPlatformRules:
    def test_claude_rules(self):
        content = load_platform_rules("claude")
        assert "TAPPS" in content
        assert "tapps_session_start" in content

    def test_cursor_rules(self):
        content = load_platform_rules("cursor")
        assert "TAPPS" in content
        assert "alwaysApply" in content

    def test_invalid_platform_raises(self):
        with pytest.raises(ValueError, match="Invalid platform"):
            load_platform_rules("vscode")
