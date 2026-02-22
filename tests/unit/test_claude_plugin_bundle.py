"""Tests for Claude Code plugin bundle generation (Story 12.9).

Verifies that generate_claude_plugin_bundle() creates a complete plugin
directory structure with plugin.json, agents, skills, hooks, .mcp.json,
and README.md.
"""

from __future__ import annotations

import json
import re
import stat

from tapps_mcp.pipeline.platform_generators import (
    generate_claude_plugin_bundle,
)


class TestPluginStructure:
    """Tests for the plugin directory layout."""

    def test_plugin_json_exists(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        assert (tmp_path / ".claude-plugin" / "plugin.json").exists()

    def test_plugin_json_valid(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        data = json.loads(
            (tmp_path / ".claude-plugin" / "plugin.json").read_text()
        )
        assert "name" in data
        assert "version" in data
        assert "description" in data

    def test_plugin_json_name(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        data = json.loads(
            (tmp_path / ".claude-plugin" / "plugin.json").read_text()
        )
        assert data["name"] == "tapps-mcp"

    def test_plugin_json_version_semver(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path, version="1.2.3")
        data = json.loads(
            (tmp_path / ".claude-plugin" / "plugin.json").read_text()
        )
        assert re.match(r"^\d+\.\d+\.\d+", data["version"])

    def test_agents_exist(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        agents_dir = tmp_path / "agents"
        assert (agents_dir / "tapps-reviewer.md").exists()
        assert (agents_dir / "tapps-researcher.md").exists()
        assert (agents_dir / "tapps-validator.md").exists()

    def test_agent_has_name_frontmatter(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        content = (tmp_path / "agents" / "tapps-reviewer.md").read_text()
        assert "name:" in content

    def test_skills_exist(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        assert (tmp_path / "skills" / "tapps-score" / "SKILL.md").exists()
        assert (tmp_path / "skills" / "tapps-gate" / "SKILL.md").exists()
        assert (tmp_path / "skills" / "tapps-validate" / "SKILL.md").exists()

    def test_hooks_json_exists(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        hooks_json = tmp_path / "hooks" / "hooks.json"
        assert hooks_json.exists()
        data = json.loads(hooks_json.read_text())
        assert "hooks" in data

    def test_hook_scripts_exist(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        assert (tmp_path / "hooks" / "tapps-stop.sh").exists()

    def test_mcp_json_exists(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        mcp_file = tmp_path / ".mcp.json"
        assert mcp_file.exists()
        data = json.loads(mcp_file.read_text())
        assert "mcpServers" in data
        assert "tapps-mcp" in data["mcpServers"]

    def test_readme_exists(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        readme = tmp_path / "README.md"
        assert readme.exists()
        assert len(readme.read_text()) > 0

    def test_result_dict(self, tmp_path):
        result = generate_claude_plugin_bundle(tmp_path)
        assert "files_created" in result
        assert len(result["files_created"]) > 0
        assert ".claude-plugin/plugin.json" in result["files_created"]
        assert "README.md" in result["files_created"]
