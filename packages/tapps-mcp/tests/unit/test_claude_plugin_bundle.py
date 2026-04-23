"""Tests for Claude Code plugin bundle generation (Story 12.9).

Verifies that generate_claude_plugin_bundle() creates a complete plugin
directory structure with plugin.json, agents, skills, hooks, .mcp.json,
and README.md.
"""

from __future__ import annotations

import json
import re

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
        data = json.loads((tmp_path / ".claude-plugin" / "plugin.json").read_text())
        assert "name" in data
        assert "version" in data
        assert "description" in data

    def test_plugin_json_name(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        data = json.loads((tmp_path / ".claude-plugin" / "plugin.json").read_text())
        assert data["name"] == "tapps-mcp"

    def test_plugin_json_version_semver(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path, version="1.2.3")
        data = json.loads((tmp_path / ".claude-plugin" / "plugin.json").read_text())
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
        assert (tmp_path / "skills" / "tapps-review-pipeline" / "SKILL.md").exists()
        assert (tmp_path / "skills" / "tapps-research" / "SKILL.md").exists()
        assert (tmp_path / "skills" / "tapps-security" / "SKILL.md").exists()
        assert (tmp_path / "skills" / "tapps-memory" / "SKILL.md").exists()

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


class TestPluginManifestExtended:
    """TAP-958: plugin.json carries userConfig, metadata, and dependencies."""

    def _load(self, tmp_path, version="3.2.5"):
        generate_claude_plugin_bundle(tmp_path, version=version)
        return json.loads((tmp_path / ".claude-plugin" / "plugin.json").read_text())

    def test_metadata_fields_present(self, tmp_path):
        data = self._load(tmp_path)
        assert data["author"]
        assert data["license"] == "MIT"
        assert data["homepage"].startswith("https://")
        assert data["repository"].startswith("https://")

    def test_user_config_engagement_level(self, tmp_path):
        data = self._load(tmp_path)
        uc = data["userConfig"]
        assert "engagement_level" in uc
        field = uc["engagement_level"]
        assert field["type"] == "string"
        assert set(field["enum"]) == {"high", "medium", "low"}
        assert field["default"] in field["enum"]

    def test_user_config_memory_http_url(self, tmp_path):
        data = self._load(tmp_path)
        field = data["userConfig"]["memory_http_url"]
        assert field["type"] == "string"
        assert field["default"].startswith("http")

    def test_user_config_quality_preset(self, tmp_path):
        data = self._load(tmp_path)
        field = data["userConfig"]["quality_preset"]
        assert set(field["enum"]) == {"standard", "strict", "framework"}

    def test_dependencies_docs_mcp_semver(self, tmp_path):
        data = self._load(tmp_path, version="3.2.5")
        deps = data["dependencies"]
        assert "docs-mcp" in deps
        assert deps["docs-mcp"] == "^3.2.5"

    def test_mcp_json_substitutes_user_config(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        mcp_data = json.loads((tmp_path / ".mcp.json").read_text())
        env = mcp_data["mcpServers"]["tapps-mcp"]["env"]
        assert env["TAPPS_BRAIN_HTTP_URL"] == "${user_config.memory_http_url}"
        assert env["TAPPS_LLM_ENGAGEMENT_LEVEL"] == "${user_config.engagement_level}"
        assert env["TAPPS_QUALITY_PRESET"] == "${user_config.quality_preset}"


class TestPluginBinShims:
    """TAP-959: bin/ directory carries POSIX + Windows shim scripts so
    consuming projects can invoke `tapps-quick-lint` / `tapps-doctor-cli`
    directly from the Bash tool."""

    def test_posix_shims_exist(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        bin_dir = tmp_path / "bin"
        assert (bin_dir / "tapps-quick-lint").exists()
        assert (bin_dir / "tapps-doctor-cli").exists()

    def test_posix_shims_executable(self, tmp_path):
        import stat as stat_mod

        generate_claude_plugin_bundle(tmp_path)
        bin_dir = tmp_path / "bin"
        for name in ("tapps-quick-lint", "tapps-doctor-cli"):
            mode = (bin_dir / name).stat().st_mode
            assert mode & stat_mod.S_IXUSR, f"{name} not user-executable"
            assert mode & stat_mod.S_IXGRP, f"{name} not group-executable"

    def test_posix_shims_shebang(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        content = (tmp_path / "bin" / "tapps-quick-lint").read_text()
        assert content.startswith("#!/usr/bin/env bash"), content[:40]

    def test_posix_shims_delegate_to_tapps_mcp(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        content = (tmp_path / "bin" / "tapps-quick-lint").read_text()
        assert "tapps-mcp validate-changed --quick" in content
        assert "uvx tapps-mcp" in content  # fallback path

    def test_doctor_shim_delegates_to_doctor(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        content = (tmp_path / "bin" / "tapps-doctor-cli").read_text()
        assert "tapps-mcp doctor" in content

    def test_windows_cmd_shims_exist(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        bin_dir = tmp_path / "bin"
        assert (bin_dir / "tapps-quick-lint.cmd").exists()
        assert (bin_dir / "tapps-doctor-cli.cmd").exists()

    def test_windows_cmd_has_crlf_and_batch_header(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        # Read as bytes — Path.read_text normalizes CRLF to LF.
        raw = (tmp_path / "bin" / "tapps-quick-lint.cmd").read_bytes()
        assert raw.startswith(b"@echo off"), raw[:40]
        assert b"\r\n" in raw, "Windows .cmd should use CRLF line endings"


class TestPluginMonitors:
    """TAP-960: monitors/monitors.json emitted only when opted in."""

    def test_monitors_absent_by_default(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        assert not (tmp_path / "monitors").exists()

    def test_monitors_absent_when_disabled(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path, monitors_enabled=False)
        assert not (tmp_path / "monitors" / "monitors.json").exists()

    def test_monitors_emitted_when_enabled(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path, monitors_enabled=True)
        path = tmp_path / "monitors" / "monitors.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "monitors" in data
        names = {m["name"] for m in data["monitors"]}
        assert {"tapps-brain-health", "quality-gate-watch", "ralph-live-tail"} <= names

    def test_monitor_shape(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path, monitors_enabled=True)
        data = json.loads((tmp_path / "monitors" / "monitors.json").read_text())
        for m in data["monitors"]:
            assert m["when"] == "always"
            assert "command" in m
            assert "description" in m

    def test_monitor_uses_plugin_root_substitution(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path, monitors_enabled=True)
        data = json.loads((tmp_path / "monitors" / "monitors.json").read_text())
        subst_count = sum(1 for m in data["monitors"] if "${CLAUDE_PLUGIN_ROOT}" in m["command"])
        assert subst_count >= 2, "Expected at least 2 monitors to use plugin-root substitution"

    def test_files_created_includes_monitors_when_enabled(self, tmp_path):
        result = generate_claude_plugin_bundle(tmp_path, monitors_enabled=True)
        assert "monitors/monitors.json" in result["files_created"]


class TestHookIfMatchers:
    """TAP-955: every tool-event hook in emitted hooks.json carries `if:`."""

    _TOOL_EVENTS = (
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "PermissionRequest",
        "PermissionDenied",
    )

    def _hooks(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        return json.loads((tmp_path / "hooks" / "hooks.json").read_text())["hooks"]

    def test_every_tool_event_entry_has_if(self, tmp_path):
        hooks = self._hooks(tmp_path)
        for event in self._TOOL_EVENTS:
            for entry in hooks.get(event, []):
                assert "if" in entry, (
                    f"{event} entry missing `if:`: {entry}"
                )

    def test_post_edit_if_targets_python_files(self, tmp_path):
        hooks = self._hooks(tmp_path)
        post_edit = next(
            e for e in hooks["PostToolUse"]
            if any("tapps-post-edit" in h["command"] for h in e["hooks"])
        )
        for expr in ("Edit(**/*.py)", "Write(**/*.py)", "MultiEdit(**/*.py)"):
            assert expr in post_edit["if"], f"missing {expr} in {post_edit['if']}"

    def test_non_tool_events_do_not_carry_if(self, tmp_path):
        hooks = self._hooks(tmp_path)
        for event in ("SessionStart", "Stop", "SessionEnd", "PreCompact"):
            for entry in hooks.get(event, []):
                assert "if" not in entry, (
                    f"{event} should not carry `if:`, got {entry}"
                )

    def test_post_tool_use_failure_has_if(self, tmp_path):
        hooks = self._hooks(tmp_path)
        for entry in hooks["PostToolUseFailure"]:
            assert entry["if"] == "mcp__tapps-mcp__*"
