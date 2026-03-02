"""Tests for distribution/plugin_builder.py — Claude Code plugin generation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tapps_mcp.distribution.plugin_builder import PluginBuilder


@pytest.fixture()
def plugin_dir(tmp_path: Path) -> Path:
    return tmp_path / "tapps-mcp-plugin"


class TestPluginManifest:
    def test_manifest_created(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        manifest_path = plugin_dir / ".claude-plugin" / "plugin.json"
        assert manifest_path.exists()

    def test_manifest_has_required_fields(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        manifest = json.loads(
            (plugin_dir / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        assert manifest["name"] == "tapps-mcp"
        assert "description" in manifest
        assert "version" in manifest
        assert manifest["license"] == "MIT"
        assert "author" in manifest

    def test_version_matches_package(self, plugin_dir: Path) -> None:
        from tapps_mcp import __version__

        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        manifest = json.loads(
            (plugin_dir / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        assert manifest["version"] == __version__


class TestPluginSkills:
    def test_skills_created(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        skills_dir = plugin_dir / "skills"
        assert skills_dir.exists()
        # Should have namespaced skill directories
        skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]
        assert len(skill_dirs) >= 4  # at least core skills

    def test_skills_are_namespaced(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        skills_dir = plugin_dir / "skills"
        for d in skills_dir.iterdir():
            if d.is_dir():
                assert d.name.startswith("tapps-mcp-"), f"{d.name} not namespaced"
                assert (d / "SKILL.md").exists()

    def test_skill_content_nonempty(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        for skill_dir in (plugin_dir / "skills").iterdir():
            if skill_dir.is_dir():
                content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
                assert len(content) > 50


class TestPluginAgents:
    def test_agents_created(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        agents_dir = plugin_dir / "agents"
        assert agents_dir.exists()
        agent_files = list(agents_dir.glob("*.md"))
        assert len(agent_files) == 4

    def test_agent_names(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        agents_dir = plugin_dir / "agents"
        names = {f.name for f in agents_dir.glob("*.md")}
        assert "tapps-reviewer.md" in names
        assert "tapps-researcher.md" in names
        assert "tapps-validator.md" in names
        assert "tapps-review-fixer.md" in names


class TestPluginHooks:
    def test_hooks_json_created(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        hooks_file = plugin_dir / "hooks" / "hooks.json"
        assert hooks_file.exists()

    def test_hooks_json_has_events(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        hooks = json.loads(
            (plugin_dir / "hooks" / "hooks.json").read_text(encoding="utf-8")
        )
        assert "SessionStart" in hooks
        assert "PostToolUse" in hooks


class TestPluginMCPConfig:
    def test_mcp_config_created(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        mcp_file = plugin_dir / ".mcp.json"
        assert mcp_file.exists()

    def test_mcp_config_references_tapps(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        mcp = json.loads(
            (plugin_dir / ".mcp.json").read_text(encoding="utf-8")
        )
        assert "tapps-mcp" in mcp["mcpServers"]
        assert mcp["mcpServers"]["tapps-mcp"]["command"] == "tapps-mcp"


class TestPluginRules:
    def test_rules_created(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        rules_file = plugin_dir / "rules" / "python-quality.md"
        assert rules_file.exists()

    def test_rules_contain_engagement_level(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir, engagement_level="high")
        builder.build()

        content = (plugin_dir / "rules" / "python-quality.md").read_text(
            encoding="utf-8"
        )
        assert "high" in content


class TestPluginSettings:
    def test_settings_created(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        settings_file = plugin_dir / "settings.json"
        assert settings_file.exists()

    def test_settings_has_permissions(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        settings = json.loads(
            (plugin_dir / "settings.json").read_text(encoding="utf-8")
        )
        assert "permissions" in settings
        assert "mcp__tapps-mcp__*" in settings["permissions"]["allow"]


class TestPluginResult:
    def test_result_has_version(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()
        assert "version" in builder.result

    def test_result_has_components(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()
        assert "components" in builder.result
        assert "manifest" in builder.result["components"]
        assert "skills" in builder.result["components"]
        assert "agents" in builder.result["components"]


class TestPluginDirectoryStructure:
    def test_complete_structure(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        assert (plugin_dir / ".claude-plugin" / "plugin.json").exists()
        assert (plugin_dir / "skills").is_dir()
        assert (plugin_dir / "agents").is_dir()
        assert (plugin_dir / "hooks" / "hooks.json").exists()
        assert (plugin_dir / "rules" / "python-quality.md").exists()
        assert (plugin_dir / ".mcp.json").exists()
        assert (plugin_dir / "settings.json").exists()
