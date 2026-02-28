"""Tests for Cursor plugin bundle generation (Story 12.10).

Verifies that generate_cursor_plugin_bundle() creates a complete plugin
directory structure with plugin.json (7 required fields), agents, skills,
hooks, rules, mcp.json, logo.png, README.md, and LICENSE.
"""

from __future__ import annotations

import json
import re

from tapps_mcp.pipeline.platform_generators import (
    generate_cursor_plugin_bundle,
)


class TestPluginStructure:
    """Tests for the Cursor plugin directory layout."""

    def test_plugin_json_exists(self, tmp_path):
        generate_cursor_plugin_bundle(tmp_path)
        assert (tmp_path / ".cursor-plugin" / "plugin.json").exists()

    def test_plugin_json_has_all_required_fields(self, tmp_path):
        generate_cursor_plugin_bundle(tmp_path)
        data = json.loads((tmp_path / ".cursor-plugin" / "plugin.json").read_text())
        required = [
            "name",
            "displayName",
            "author",
            "description",
            "keywords",
            "license",
            "version",
        ]
        for field in required:
            assert field in data, f"Missing required field: {field}"

    def test_plugin_json_name_kebab_case(self, tmp_path):
        generate_cursor_plugin_bundle(tmp_path)
        data = json.loads((tmp_path / ".cursor-plugin" / "plugin.json").read_text())
        assert data["name"] == "tapps-mcp-plugin"
        assert re.match(r"^[a-z][a-z0-9-]+$", data["name"])

    def test_plugin_json_display_name(self, tmp_path):
        generate_cursor_plugin_bundle(tmp_path)
        data = json.loads((tmp_path / ".cursor-plugin" / "plugin.json").read_text())
        assert data["displayName"] == "TappsMCP Quality Tools"

    def test_plugin_json_author(self, tmp_path):
        generate_cursor_plugin_bundle(tmp_path)
        data = json.loads((tmp_path / ".cursor-plugin" / "plugin.json").read_text())
        assert data["author"] == "TappsMCP Team"

    def test_plugin_json_keywords(self, tmp_path):
        generate_cursor_plugin_bundle(tmp_path)
        data = json.loads((tmp_path / ".cursor-plugin" / "plugin.json").read_text())
        assert isinstance(data["keywords"], list)
        assert len(data["keywords"]) >= 3
        assert "code-quality" in data["keywords"]
        assert "security" in data["keywords"]
        assert "scoring" in data["keywords"]

    def test_plugin_json_license(self, tmp_path):
        generate_cursor_plugin_bundle(tmp_path)
        data = json.loads((tmp_path / ".cursor-plugin" / "plugin.json").read_text())
        assert data["license"] == "MIT"

    def test_plugin_json_version_semver(self, tmp_path):
        generate_cursor_plugin_bundle(tmp_path, version="2.0.0")
        data = json.loads((tmp_path / ".cursor-plugin" / "plugin.json").read_text())
        assert re.match(r"^\d+\.\d+\.\d+", data["version"])

    def test_mcp_json_exists(self, tmp_path):
        generate_cursor_plugin_bundle(tmp_path)
        mcp_file = tmp_path / "mcp.json"
        assert mcp_file.exists()
        data = json.loads(mcp_file.read_text())
        assert "mcpServers" in data
        assert "tapps-mcp" in data["mcpServers"]
        assert "command" in data["mcpServers"]["tapps-mcp"]

    def test_mcp_json_has_project_root_env(self, tmp_path):
        generate_cursor_plugin_bundle(tmp_path)
        data = json.loads((tmp_path / "mcp.json").read_text())
        env = data["mcpServers"]["tapps-mcp"]["env"]
        assert "TAPPS_MCP_PROJECT_ROOT" in env

    def test_agents_exist(self, tmp_path):
        generate_cursor_plugin_bundle(tmp_path)
        agents_dir = tmp_path / "agents"
        assert (agents_dir / "tapps-reviewer.md").exists()
        assert (agents_dir / "tapps-researcher.md").exists()
        assert (agents_dir / "tapps-validator.md").exists()

    def test_agent_uses_yaml_list_tools(self, tmp_path):
        """Cursor agents must use YAML array for tools, not string."""
        generate_cursor_plugin_bundle(tmp_path)
        content = (tmp_path / "agents" / "tapps-reviewer.md").read_text()
        assert "tools:\n" in content
        assert "  - code_search" in content

    def test_skills_exist(self, tmp_path):
        generate_cursor_plugin_bundle(tmp_path)
        assert (tmp_path / "skills" / "tapps-score" / "SKILL.md").exists()
        assert (tmp_path / "skills" / "tapps-gate" / "SKILL.md").exists()
        assert (tmp_path / "skills" / "tapps-validate" / "SKILL.md").exists()
        assert (tmp_path / "skills" / "tapps-review-pipeline" / "SKILL.md").exists()
        assert (tmp_path / "skills" / "tapps-research" / "SKILL.md").exists()
        assert (tmp_path / "skills" / "tapps-security" / "SKILL.md").exists()
        assert (tmp_path / "skills" / "tapps-memory" / "SKILL.md").exists()

    def test_skills_have_name_frontmatter(self, tmp_path):
        generate_cursor_plugin_bundle(tmp_path)
        content = (tmp_path / "skills" / "tapps-score" / "SKILL.md").read_text()
        assert "name:" in content

    def test_hooks_json_exists(self, tmp_path):
        generate_cursor_plugin_bundle(tmp_path)
        hooks_json = tmp_path / "hooks" / "hooks.json"
        assert hooks_json.exists()
        data = json.loads(hooks_json.read_text())
        assert "hooks" in data

    def test_hooks_json_has_cursor_events(self, tmp_path):
        generate_cursor_plugin_bundle(tmp_path)
        data = json.loads((tmp_path / "hooks" / "hooks.json").read_text())
        assert data["version"] == 1
        assert isinstance(data["hooks"], dict)
        assert "beforeMCPExecution" in data["hooks"] or "stop" in data["hooks"]

    def test_rules_exist(self, tmp_path):
        generate_cursor_plugin_bundle(tmp_path)
        rules_dir = tmp_path / "rules"
        assert (rules_dir / "tapps-pipeline.mdc").exists()

    def test_pipeline_rule_has_always_apply(self, tmp_path):
        generate_cursor_plugin_bundle(tmp_path)
        content = (tmp_path / "rules" / "tapps-pipeline.mdc").read_text()
        assert "alwaysApply: true" in content

    def test_logo_exists(self, tmp_path):
        generate_cursor_plugin_bundle(tmp_path)
        assert (tmp_path / "logo.png").exists()

    def test_readme_exists(self, tmp_path):
        generate_cursor_plugin_bundle(tmp_path)
        readme = tmp_path / "README.md"
        assert readme.exists()
        assert len(readme.read_text()) > 0

    def test_license_exists(self, tmp_path):
        generate_cursor_plugin_bundle(tmp_path)
        assert (tmp_path / "LICENSE").exists()

    def test_result_dict(self, tmp_path):
        result = generate_cursor_plugin_bundle(tmp_path)
        assert "files_created" in result
        assert ".cursor-plugin/plugin.json" in result["files_created"]
        assert "README.md" in result["files_created"]
        assert "LICENSE" in result["files_created"]
