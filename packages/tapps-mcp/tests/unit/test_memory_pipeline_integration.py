"""Tests for Task #16: Pipeline & Init Integration for memory system.

Verifies:
- default.yaml includes memory config
- Pipeline stage tools include tapps_memory
- AGENTS.md templates reference tapps_memory
- Platform rule templates reference tapps_memory
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tapps_mcp.pipeline.models import STAGE_TOOLS, PipelineStage
from tapps_mcp.prompts.prompt_loader import load_agents_template, load_platform_rules


class TestDefaultYamlMemoryConfig:
    """Verify default.yaml includes memory configuration."""

    def test_default_yaml_has_memory_section(self) -> None:
        default_yaml = (
            Path(__file__).resolve().parents[2] / "src" / "tapps_mcp" / "config" / "default.yaml"
        )
        data = yaml.safe_load(default_yaml.read_text(encoding="utf-8"))
        assert "memory" in data
        mem = data["memory"]
        assert mem["enabled"] is True
        assert mem["gc_enabled"] is True
        assert mem["contradiction_check_on_start"] is True
        assert mem["max_memories"] == 1500
        assert mem["inject_into_experts"] is True

    def test_default_yaml_has_capture_prompt_and_write_rules(self) -> None:
        """Verify default.yaml includes capture_prompt and write_rules (Epic 65.3)."""
        default_yaml = (
            Path(__file__).resolve().parents[2] / "src" / "tapps_mcp" / "config" / "default.yaml"
        )
        data = yaml.safe_load(default_yaml.read_text(encoding="utf-8"))
        mem = data["memory"]
        assert "capture_prompt" in mem
        assert "Store durable memories" in mem["capture_prompt"]
        assert "write_rules" in mem
        wr = mem["write_rules"]
        assert wr["block_sensitive_keywords"] == ["password", "secret", "api_key", "token"]
        assert wr["min_value_length"] == 10
        assert wr["max_value_length"] == 4096

    def test_default_yaml_has_decay_config(self) -> None:
        default_yaml = (
            Path(__file__).resolve().parents[2] / "src" / "tapps_mcp" / "config" / "default.yaml"
        )
        data = yaml.safe_load(default_yaml.read_text(encoding="utf-8"))
        decay = data["memory"]["decay"]
        assert decay["architectural_half_life_days"] == 180
        assert decay["pattern_half_life_days"] == 60
        assert decay["context_half_life_days"] == 14
        assert decay["confidence_floor"] == 0.1


class TestPipelineStageTools:
    """Verify tapps_memory is in the correct pipeline stages."""

    def test_discover_stage_includes_memory(self) -> None:
        tools = STAGE_TOOLS[PipelineStage.DISCOVER]
        assert "tapps_memory" in tools

    def test_verify_stage_includes_memory(self) -> None:
        tools = STAGE_TOOLS[PipelineStage.VERIFY]
        assert "tapps_memory" in tools

    def test_other_stages_unchanged(self) -> None:
        assert "tapps_memory" not in STAGE_TOOLS[PipelineStage.RESEARCH]
        assert "tapps_memory" not in STAGE_TOOLS[PipelineStage.DEVELOP]
        assert "tapps_memory" not in STAGE_TOOLS[PipelineStage.VALIDATE]


class TestAgentsTemplatesMemory:
    """Verify AGENTS.md templates reference tapps_memory."""

    def test_high_template_has_memory_tool(self) -> None:
        content = load_agents_template("high")
        assert "tapps_memory" in content

    def test_medium_template_has_memory_tool(self) -> None:
        content = load_agents_template("medium")
        assert "tapps_memory" in content

    def test_low_template_has_memory_tool(self) -> None:
        content = load_agents_template("low")
        assert "tapps_memory" in content

    def test_high_template_required_language(self) -> None:
        content = load_agents_template("high")
        assert "REQUIRED" in content

    def test_medium_template_recommended_language(self) -> None:
        content = load_agents_template("medium")
        assert "RECOMMENDED" in content

    def test_low_template_optional_language(self) -> None:
        content = load_agents_template("low")
        assert "OPTIONAL" in content


class TestPlatformRulesMemory:
    """Verify platform rule templates reference tapps_memory."""

    def test_claude_default_has_memory(self) -> None:
        content = load_platform_rules("claude")
        assert "tapps_memory" in content

    def test_claude_high_has_memory(self) -> None:
        content = load_platform_rules("claude", engagement_level="high")
        assert "tapps_memory" in content

    def test_claude_medium_has_memory(self) -> None:
        content = load_platform_rules("claude", engagement_level="medium")
        assert "tapps_memory" in content

    def test_claude_low_has_memory(self) -> None:
        content = load_platform_rules("claude", engagement_level="low")
        assert "tapps_memory" in content

    def test_cursor_default_has_memory(self) -> None:
        content = load_platform_rules("cursor")
        assert "tapps_memory" in content

    def test_cursor_high_has_memory(self) -> None:
        content = load_platform_rules("cursor", engagement_level="high")
        assert "tapps_memory" in content

    def test_cursor_medium_has_memory(self) -> None:
        content = load_platform_rules("cursor", engagement_level="medium")
        assert "tapps_memory" in content

    def test_cursor_low_has_memory(self) -> None:
        content = load_platform_rules("cursor", engagement_level="low")
        assert "tapps_memory" in content
