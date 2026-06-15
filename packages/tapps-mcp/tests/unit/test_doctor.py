"""Tests for the tapps-mcp doctor command."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from tapps_mcp.cli import main
from tapps_mcp.distribution.doctor import (
    CheckResult,
    _collect_checks,
    _parse_histogram_quantiles,
    _parse_version_tuple,
    _read_brain_floor_pin,
    _read_engagement_level,
    check_agents_md,
    check_binary_on_path,
    check_brain_probe_latency,
    check_brain_version_delta,
    check_claude_code_project,
    check_claude_code_user,
    check_claude_hook_scripts,
    check_claude_md,
    check_claude_settings,
    check_cursor_config,
    check_cursor_mcp_zombie_cleanup,
    check_cursor_rules,
    check_hooks,
    check_json_config,
    check_mcp_client_config,
    check_mcp_config_unresolved_project_root,
    check_mcp_tool_budget,
    check_nlt_partial_enablement,
    check_plaintext_secrets,
    check_scope_recommendation,
    check_stale_exe_backups,
    check_uv_path_mismatch,
    check_vscode_config,
    run_doctor,
    run_doctor_structured,
)

# ---------------------------------------------------------------------------
# CheckResult
# ---------------------------------------------------------------------------


class TestCheckResult:
    """Tests for the CheckResult data class."""

    def test_slots(self):
        r = CheckResult("test", True, "ok")
        assert r.name == "test"
        assert r.ok is True
        assert r.message == "ok"
        assert r.detail == ""

    def test_detail(self):
        r = CheckResult("test", False, "fail", "hint")
        assert r.detail == "hint"


# ---------------------------------------------------------------------------
# _read_engagement_level (Epic 18.8)
# ---------------------------------------------------------------------------


class TestReadEngagementLevel:
    """Tests for _read_engagement_level."""

    def test_no_file_returns_none(self, tmp_path):
        assert _read_engagement_level(tmp_path) is None

    @pytest.mark.parametrize(
        "level",
        ["high", "medium", "low"],
        ids=["high", "medium", "low"],
    )
    def test_valid_level(self, tmp_path, level):
        (tmp_path / ".tapps-mcp.yaml").write_text(f"llm_engagement_level: {level}\n")
        assert _read_engagement_level(tmp_path) == level

    def test_invalid_level_returns_none(self, tmp_path):
        (tmp_path / ".tapps-mcp.yaml").write_text("llm_engagement_level: strict\n")
        assert _read_engagement_level(tmp_path) is None

    def test_missing_key_returns_none(self, tmp_path):
        (tmp_path / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
        assert _read_engagement_level(tmp_path) is None


# ---------------------------------------------------------------------------
# Binary check
# ---------------------------------------------------------------------------


class TestCheckBinaryOnPath:
    """Tests for check_binary_on_path."""

    def test_found(self):
        with patch("tapps_mcp.distribution.doctor.shutil.which", return_value="/usr/bin/tapps-mcp"):
            result = check_binary_on_path()
        assert result.ok is True
        assert "PATH" in result.message

    def test_not_found(self):
        with patch("tapps_mcp.distribution.doctor.shutil.which", return_value=None):
            result = check_binary_on_path()
        assert result.ok is False
        assert "not found" in result.message


# ---------------------------------------------------------------------------
# JSON config checks
# ---------------------------------------------------------------------------


class TestCheckJsonConfig:
    """Tests for the generic JSON config checker."""

    def test_valid_config(self, tmp_path):
        config = {"mcpServers": {"tapps-mcp": {"command": "tapps-mcp"}}}
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        result = check_json_config(path, "mcpServers", "Test")
        assert result.ok is True

    def test_missing_file(self, tmp_path):
        result = check_json_config(tmp_path / "missing.json", "mcpServers", "Test")
        assert result.ok is False
        assert "Not found" in result.message

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not valid}", encoding="utf-8")
        result = check_json_config(path, "mcpServers", "Test")
        assert result.ok is False
        assert "Invalid JSON" in result.message

    def test_missing_tapps_entry(self, tmp_path):
        config = {"mcpServers": {"other": {"command": "other"}}}
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        result = check_json_config(path, "mcpServers", "Test")
        assert result.ok is False
        assert "tapps-mcp / nlt-build not in" in result.message

    def test_wrong_command(self, tmp_path):
        config = {"mcpServers": {"tapps-mcp": {"command": "wrong"}}}
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        result = check_json_config(path, "mcpServers", "Test")
        assert result.ok is False
        assert "Unexpected command" in result.message

    def test_uv_launcher_valid(self, tmp_path):
        config = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "uv",
                    "args": [
                        "--directory",
                        "C:\\cursor\\TappMCP",
                        "run",
                        "--no-sync",
                        "tapps-mcp",
                        "serve",
                    ],
                }
            }
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        result = check_json_config(path, "mcpServers", "Test")
        assert result.ok is True

    def test_uv_without_serve_invalid(self, tmp_path):
        config = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "uv",
                    "args": ["run", "tapps-mcp"],
                }
            }
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        result = check_json_config(path, "mcpServers", "Test")
        assert result.ok is False

    def test_empty_file(self, tmp_path):
        path = tmp_path / "empty.json"
        path.write_text("", encoding="utf-8")
        result = check_json_config(path, "mcpServers", "Test")
        assert result.ok is False

    def test_empty_servers_key(self, tmp_path):
        config = {"mcpServers": {}}
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        result = check_json_config(path, "mcpServers", "Test")
        assert result.ok is False

    def test_missing_servers_key(self, tmp_path):
        config = {"someOther": "value"}
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        result = check_json_config(path, "mcpServers", "Test")
        assert result.ok is False


# ---------------------------------------------------------------------------
# Host-specific config checks
# ---------------------------------------------------------------------------


class TestHostConfigChecks:
    """Tests for host-specific config check wrappers."""

    def test_claude_code_user_found(self, tmp_path):
        config = {"mcpServers": {"tapps-mcp": {"command": "tapps-mcp"}}}
        (tmp_path / ".claude.json").write_text(json.dumps(config), encoding="utf-8")
        result = check_claude_code_user(home=tmp_path)
        assert result.ok is True

    def test_claude_code_user_missing(self, tmp_path):
        result = check_claude_code_user(home=tmp_path)
        assert result.ok is False

    def test_claude_code_user_passes_when_project_mcp_configures(self, tmp_path):
        """Epic 80.9: ~/.claude.json optional when project .mcp.json has tapps-mcp."""
        consumer = tmp_path / "app"
        consumer.mkdir()
        cfg = {"mcpServers": {"tapps-mcp": {"command": "tapps-mcp", "args": ["serve"]}}}
        (consumer / ".mcp.json").write_text(json.dumps(cfg), encoding="utf-8")
        result = check_claude_code_user(home=tmp_path, project_root=consumer)
        assert result.ok is True
        assert "project" in result.message.lower()

    def test_claude_hook_scripts_missing_file(self, tmp_path):
        claude = tmp_path / ".claude"
        claude.mkdir()
        settings = {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "Edit",
                        "hooks": [
                            {"type": "command", "command": ".claude/hooks/tapps-post-edit.sh"},
                        ],
                    },
                ],
            },
        }
        (claude / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        result = check_claude_hook_scripts(tmp_path)
        assert result.ok is False
        assert "Missing" in result.message

    def test_claude_hook_scripts_present(self, tmp_path):
        hooks_dir = tmp_path / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "tapps-post-edit.sh").write_text("# ok", encoding="utf-8")
        claude = tmp_path / ".claude"
        settings = {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "Edit",
                        "hooks": [
                            {"type": "command", "command": ".claude/hooks/tapps-post-edit.sh"},
                        ],
                    },
                ],
            },
        }
        (claude / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        result = check_claude_hook_scripts(tmp_path)
        assert result.ok is True

    def test_claude_code_project_found(self, tmp_path):
        config = {"mcpServers": {"tapps-mcp": {"command": "tapps-mcp"}}}
        (tmp_path / ".mcp.json").write_text(json.dumps(config), encoding="utf-8")
        result = check_claude_code_project(tmp_path)
        assert result.ok is True

    def test_claude_code_project_missing(self, tmp_path):
        result = check_claude_code_project(tmp_path)
        assert result.ok is False

    def test_cursor_config_found(self, tmp_path):
        config = {"mcpServers": {"tapps-mcp": {"command": "tapps-mcp"}}}
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        (cursor_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
        result = check_cursor_config(tmp_path)
        assert result.ok is True

    def test_cursor_config_missing(self, tmp_path):
        result = check_cursor_config(tmp_path)
        assert result.ok is False

    def test_vscode_config_found(self, tmp_path):
        config = {"servers": {"tapps-mcp": {"command": "tapps-mcp"}}}
        vscode_dir = tmp_path / ".vscode"
        vscode_dir.mkdir()
        (vscode_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
        result = check_vscode_config(tmp_path)
        assert result.ok is True

    def test_vscode_config_missing(self, tmp_path):
        result = check_vscode_config(tmp_path)
        assert result.ok is False


# ---------------------------------------------------------------------------
# Platform rule checks
# ---------------------------------------------------------------------------


class TestPlatformRuleChecks:
    """Tests for CLAUDE.md and Cursor rules checks."""

    def test_claude_md_with_tapps(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# Rules\nUse TAPPS pipeline.\n")
        result = check_claude_md(tmp_path)
        assert result.ok is True

    def test_claude_md_without_tapps(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# Rules\nNo pipeline here.\n")
        result = check_claude_md(tmp_path)
        assert result.ok is False
        assert "no TAPPS reference" in result.message

    def test_claude_md_missing(self, tmp_path):
        result = check_claude_md(tmp_path)
        assert result.ok is False
        assert "not found" in result.message

    def test_cursor_rules_present(self, tmp_path):
        rules = tmp_path / ".cursor" / "rules" / "tapps-pipeline.md"
        rules.parent.mkdir(parents=True)
        rules.write_text("TAPPS rules")
        result = check_cursor_rules(tmp_path)
        assert result.ok is True

    def test_cursor_rules_missing(self, tmp_path):
        result = check_cursor_rules(tmp_path)
        assert result.ok is False


# ---------------------------------------------------------------------------
# run_doctor integration
# ---------------------------------------------------------------------------


class TestRunDoctor:
    """Integration tests for the doctor command."""

    def test_reports_failures(self, tmp_path, capsys):
        """Reports failures when nothing is configured."""
        with (
            patch("tapps_mcp.distribution.doctor.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.doctor.shutil.which", return_value=None),
        ):
            ok = run_doctor(project_root=str(tmp_path))
        assert ok is False
        captured = capsys.readouterr()
        assert "FAIL" in captured.out
        assert "issue(s) found" in captured.out

    def test_reports_passes(self, tmp_path, capsys):
        """Reports passes for configured items."""
        config = {"mcpServers": {"tapps-mcp": {"command": "tapps-mcp"}}}
        (tmp_path / ".claude.json").write_text(json.dumps(config), encoding="utf-8")
        (tmp_path / "CLAUDE.md").write_text("# TAPPS pipeline rules")
        with (
            patch("tapps_mcp.distribution.doctor.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.doctor.shutil.which", return_value="/usr/bin/tapps-mcp"),
        ):
            run_doctor(project_root=str(tmp_path))
        captured = capsys.readouterr()
        assert "PASS" in captured.out

    def test_includes_quality_tools(self, tmp_path, capsys):
        """Doctor report includes quality tool checks."""
        with (
            patch("tapps_mcp.distribution.doctor.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.doctor.shutil.which", return_value=None),
        ):
            run_doctor(project_root=str(tmp_path))
        captured = capsys.readouterr()
        assert "ruff" in captured.out.lower() or "Tool:" in captured.out


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestCliDoctor:
    """Tests for the CLI doctor command via Click's CliRunner."""

    def test_doctor_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["doctor", "--help"])
        assert result.exit_code == 0
        assert "Diagnose" in result.output

    def test_doctor_runs(self, tmp_path):
        runner = CliRunner()
        with (
            patch("tapps_mcp.distribution.doctor.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.doctor.shutil.which", return_value=None),
        ):
            result = runner.invoke(
                main,
                ["doctor", "--project-root", str(tmp_path)],
            )
        assert "Doctor Report" in result.output

    def test_doctor_exit_code_on_failure(self, tmp_path):
        """Doctor exits with code 1 when checks fail."""
        runner = CliRunner()
        with (
            patch("tapps_mcp.distribution.doctor.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.doctor.shutil.which", return_value=None),
        ):
            result = runner.invoke(
                main,
                ["doctor", "--project-root", str(tmp_path)],
            )
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# check_agents_md
# ---------------------------------------------------------------------------


class TestCheckAgentsMd:
    """Tests for check_agents_md diagnostic check."""

    def test_valid_up_to_date(self, tmp_path):
        """AGENTS.md with current version marker passes."""
        from tapps_mcp.prompts.prompt_loader import load_agents_template

        (tmp_path / "AGENTS.md").write_text(load_agents_template(), encoding="utf-8")
        result = check_agents_md(tmp_path)
        assert result.ok is True
        assert "matches" in result.message

    def test_missing_agents_md(self, tmp_path):
        """Missing AGENTS.md fails."""
        result = check_agents_md(tmp_path)
        assert result.ok is False
        assert "not found" in result.message

    def test_outdated_version_marker(self, tmp_path):
        """AGENTS.md with old version marker fails."""
        content = "<!-- tapps-agents-version: 0.0.1 -->\n# AGENTS\n\nOld content.\n"
        (tmp_path / "AGENTS.md").write_text(content, encoding="utf-8")
        result = check_agents_md(tmp_path)
        assert result.ok is False
        assert "outdated" in result.message
        assert "0.0.1" in result.message

    def test_no_version_marker(self, tmp_path):
        """AGENTS.md without version marker is outdated."""
        (tmp_path / "AGENTS.md").write_text("# AGENTS\n\nNo version marker.\n", encoding="utf-8")
        result = check_agents_md(tmp_path)
        assert result.ok is False
        assert "outdated" in result.message


# ---------------------------------------------------------------------------
# check_claude_settings
# ---------------------------------------------------------------------------


class TestCheckClaudeSettings:
    """Tests for check_claude_settings diagnostic check."""

    def test_correct_settings(self, tmp_path):
        """Settings with both permission entries passes."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        config = {"permissions": {"allow": ["mcp__tapps-mcp", "mcp__tapps-mcp__*"]}}
        (settings_dir / "settings.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
        result = check_claude_settings(tmp_path)
        assert result.ok is True
        assert "permission" in result.message.lower()

    def test_missing_settings(self, tmp_path):
        """Missing .claude/settings.json fails."""
        result = check_claude_settings(tmp_path)
        assert result.ok is False
        assert "not found" in result.message

    def test_settings_missing_wildcard(self, tmp_path):
        """Settings without the wildcard fails."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        config = {"permissions": {"allow": ["some_other_permission"]}}
        (settings_dir / "settings.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
        result = check_claude_settings(tmp_path)
        assert result.ok is False
        assert "Missing" in result.message or "missing" in result.message.lower()

    def test_settings_empty_json(self, tmp_path):
        """Empty JSON object in settings.json fails (no permissions key)."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        (settings_dir / "settings.json").write_text("{}", encoding="utf-8")
        result = check_claude_settings(tmp_path)
        assert result.ok is False

    def test_settings_invalid_json(self, tmp_path):
        """Invalid JSON in settings.json fails."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        (settings_dir / "settings.json").write_text("{bad json}", encoding="utf-8")
        result = check_claude_settings(tmp_path)
        assert result.ok is False
        assert "Invalid JSON" in result.message

    def test_settings_with_additional_permissions(self, tmp_path):
        """Settings with both entries among other permissions passes."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        config = {
            "permissions": {
                "allow": ["other_tool", "mcp__tapps-mcp", "mcp__tapps-mcp__*", "another"],
            },
        }
        (settings_dir / "settings.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
        result = check_claude_settings(tmp_path)
        assert result.ok is True

    def test_settings_missing_bare_entry(self, tmp_path):
        """Settings with only wildcard (no bare entry) fails."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        config = {"permissions": {"allow": ["mcp__tapps-mcp__*"]}}
        (settings_dir / "settings.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
        result = check_claude_settings(tmp_path)
        assert result.ok is False
        assert "mcp__tapps-mcp" in result.message

    def test_settings_with_unsupported_hook_key_fails(self, tmp_path):
        """Unsupported hook keys (e.g. PostCompact) cause check to fail."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        config = {
            "permissions": {"allow": ["mcp__tapps-mcp", "mcp__tapps-mcp__*"]},
            "hooks": {
                "PostCompact": [{"matcher": "*", "hooks": [{"type": "command", "command": "true"}]}]
            },
        }
        (settings_dir / "settings.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
        result = check_claude_settings(tmp_path)
        assert result.ok is False
        assert "PostCompact" in result.message
        assert "Unsupported" in result.message or "skip" in result.message.lower()


# ---------------------------------------------------------------------------
# check_hooks
# ---------------------------------------------------------------------------


class TestCheckHooks:
    """Tests for check_hooks diagnostic check."""

    def test_claude_hooks_with_session_start(self, tmp_path):
        """Claude hooks directory with session-start hook passes."""
        hooks_dir = tmp_path / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "tapps-session-start.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        result = check_hooks(tmp_path)
        assert result.ok is True
        assert "Claude Code" in result.message
        assert "session-start" in result.message

    def test_cursor_hooks_with_before_mcp(self, tmp_path):
        """Cursor hooks directory with before-mcp hook and valid hooks.json passes (Unix: .sh)."""
        hooks_dir = tmp_path / ".cursor" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "tapps-before-mcp.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        (hooks_dir / "tapps-after-edit.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        (tmp_path / ".cursor" / "hooks.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "hooks": {
                        "beforeMCPExecution": [{"command": ".cursor/hooks/tapps-before-mcp.sh"}],
                        "afterFileEdit": [{"command": ".cursor/hooks/tapps-after-edit.sh"}],
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        with patch("tapps_mcp.distribution.doctor.sys.platform", "linux"):
            result = check_hooks(tmp_path)
        assert result.ok is True
        assert "Cursor" in result.message

    def test_both_hooks_present(self, tmp_path):
        """Both Claude and Cursor hooks with session-start hooks and valid config passes (Unix: .sh)."""
        claude_hooks = tmp_path / ".claude" / "hooks"
        claude_hooks.mkdir(parents=True)
        (claude_hooks / "tapps-session-start.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        cursor_hooks = tmp_path / ".cursor" / "hooks"
        cursor_hooks.mkdir(parents=True)
        (cursor_hooks / "tapps-before-mcp.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        (tmp_path / ".cursor" / "hooks.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "hooks": {
                        "beforeMCPExecution": [{"command": ".cursor/hooks/tapps-before-mcp.sh"}],
                        "afterFileEdit": [{"command": ".cursor/hooks/tapps-after-edit.sh"}],
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        with patch("tapps_mcp.distribution.doctor.sys.platform", "linux"):
            result = check_hooks(tmp_path)
        assert result.ok is True
        assert "Claude Code" in result.message
        assert "Cursor" in result.message

    def test_no_hooks_directories(self, tmp_path):
        """No hooks directories at all fails."""
        result = check_hooks(tmp_path)
        assert result.ok is False
        assert "No TappsMCP hooks" in result.message

    def test_claude_hooks_missing_session_start(self, tmp_path):
        """Claude hooks without session-start hook fails."""
        hooks_dir = tmp_path / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "tapps-post-edit.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        result = check_hooks(tmp_path)
        assert result.ok is False
        assert "session-start hook missing" in result.message

    def test_claude_hooks_ps1_session_start_passes(self, tmp_path):
        """Claude hooks with PowerShell session-start passes."""
        hooks_dir = tmp_path / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "tapps-session-start.ps1").write_text("# ps1\n", encoding="utf-8")
        result = check_hooks(tmp_path)
        assert result.ok is True

    def test_cursor_hooks_missing_before_mcp(self, tmp_path):
        """Cursor hooks without before-mcp hook fails."""
        hooks_dir = tmp_path / ".cursor" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "tapps-after-edit.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        result = check_hooks(tmp_path)
        assert result.ok is False
        assert "session-start hook missing" in result.message

    def test_cursor_zombie_cleanup_passes_when_wired(self, tmp_path):
        """Cursor sessionStart with zombie cleanup before recall passes doctor."""
        hooks_dir = tmp_path / ".cursor" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "tapps-before-mcp.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        (hooks_dir / "tapps-mcp-zombie-cleanup.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        (hooks_dir / "tapps-memory-auto-recall.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        (tmp_path / ".cursor" / "hooks.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "hooks": {
                        "beforeMCPExecution": [{"command": ".cursor/hooks/tapps-before-mcp.sh"}],
                        "sessionStart": [
                            {"command": ".cursor/hooks/tapps-mcp-zombie-cleanup.sh"},
                            {"command": ".cursor/hooks/tapps-memory-auto-recall.sh"},
                        ],
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        with patch("tapps_mcp.distribution.doctor.sys.platform", "linux"):
            hooks_result = check_hooks(tmp_path)
            zombie_result = check_cursor_mcp_zombie_cleanup(tmp_path)
        assert hooks_result.ok is True
        assert "MCP zombie cleanup on sessionStart" in hooks_result.message
        assert zombie_result.ok is True

    def test_cursor_zombie_cleanup_fails_when_missing_script(self, tmp_path):
        """Missing zombie cleanup script fails when memory auto-recall is wired."""
        hooks_dir = tmp_path / ".cursor" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "tapps-before-mcp.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        (hooks_dir / "tapps-memory-auto-recall.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        (tmp_path / ".cursor" / "hooks.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "hooks": {
                        "beforeMCPExecution": [{"command": ".cursor/hooks/tapps-before-mcp.sh"}],
                        "sessionStart": [
                            {"command": ".cursor/hooks/tapps-memory-auto-recall.sh"},
                        ],
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        with patch("tapps_mcp.distribution.doctor.sys.platform", "linux"):
            result = check_cursor_mcp_zombie_cleanup(tmp_path)
        assert result.ok is False
        assert "missing" in result.message.lower()

    def test_hooks_dir_exists_but_no_tapps_files(self, tmp_path):
        """Hooks directory exists but has no tapps-* files fails."""
        hooks_dir = tmp_path / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "other-hook.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        result = check_hooks(tmp_path)
        assert result.ok is False

    def test_empty_hooks_directory(self, tmp_path):
        """Empty hooks directory fails."""
        hooks_dir = tmp_path / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True)
        result = check_hooks(tmp_path)
        assert result.ok is False

    def test_cursor_hooks_scripts_without_hooks_json_fails(self, tmp_path):
        """Cursor hook scripts present but .cursor/hooks.json missing fails."""
        hooks_dir = tmp_path / ".cursor" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "tapps-before-mcp.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        (hooks_dir / "tapps-after-edit.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        # No .cursor/hooks.json
        result = check_hooks(tmp_path)
        assert result.ok is False
        assert ".cursor/hooks.json missing" in result.message
        assert "upgrade" in result.detail.lower()

    def test_cursor_hooks_json_unknown_key_warns_not_fails(self, tmp_path):
        """Non-catalog hook keys are allowed; doctor reports a soft pass with warning."""
        hooks_dir = tmp_path / ".cursor" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "tapps-before-mcp.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        (hooks_dir / "tapps-after-edit.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        (tmp_path / ".cursor" / "hooks.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "hooks": {
                        "beforeMCPExecution": [{"command": ".cursor/hooks/tapps-before-mcp.sh"}],
                        "postCompact": [{"command": "echo x"}],
                        "preToolUse": [{"command": ".cursor/hooks/clv2-observe.sh pre"}],
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        with patch("tapps_mcp.distribution.doctor.sys.platform", "linux"):
            result = check_hooks(tmp_path)
        assert result.ok is True
        assert "postCompact" in result.message or "non-catalog" in result.message

    def test_cursor_hooks_windows_sh_fails(self, tmp_path):
        """On Windows, Cursor hooks configured as .sh fail (open in editor instead of running)."""
        hooks_dir = tmp_path / ".cursor" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "tapps-before-mcp.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        (hooks_dir / "tapps-after-edit.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        (tmp_path / ".cursor" / "hooks.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "hooks": {
                        "beforeMCPExecution": [{"command": ".cursor/hooks/tapps-before-mcp.sh"}],
                        "afterFileEdit": [{"command": ".cursor/hooks/tapps-after-edit.sh"}],
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        with patch("tapps_mcp.distribution.doctor.sys.platform", "win32"):
            result = check_hooks(tmp_path)
        assert result.ok is False
        assert "Windows" in result.message or ".sh" in result.message
        assert "upgrade" in result.detail.lower()


# ---------------------------------------------------------------------------
# check_stale_exe_backups
# ---------------------------------------------------------------------------


class TestCheckStaleExeBackups:
    """Tests for stale .old exe backup detection."""

    def test_not_frozen_passes(self):
        """Not applicable when not running as frozen exe."""
        with patch.object(sys, "frozen", False, create=True):
            result = check_stale_exe_backups()
        assert result.ok is True
        assert "not applicable" in result.message.lower()

    def test_no_stale_files(self, tmp_path):
        """Passes when no .old files exist."""
        exe = tmp_path / "tapps-mcp.exe"
        exe.write_bytes(b"\x00")
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", str(exe)),
        ):
            result = check_stale_exe_backups()
        assert result.ok is True

    def test_detects_stale_old_file(self, tmp_path):
        """Detects .old backup file."""
        exe = tmp_path / "tapps-mcp.exe"
        exe.write_bytes(b"\x00")
        (tmp_path / "tapps-mcp.exe.old").write_bytes(b"\x00")
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", str(exe)),
        ):
            result = check_stale_exe_backups()
        assert result.ok is False
        assert "tapps-mcp.exe.old" in result.message

    def test_detects_timestamped_stale_file(self, tmp_path):
        """Detects timestamped .old backup file."""
        exe = tmp_path / "tapps-mcp.exe"
        exe.write_bytes(b"\x00")
        (tmp_path / "tapps-mcp.exe.old.1708800000").write_bytes(b"\x00")
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", str(exe)),
        ):
            result = check_stale_exe_backups()
        assert result.ok is False


# ---------------------------------------------------------------------------
# Story 47.4: Scope recommendation check
# ---------------------------------------------------------------------------


class TestCheckScopeRecommendation:
    """Tests for check_scope_recommendation (Epic 47.4)."""

    def test_no_user_config_passes(self, tmp_path):
        """No ~/.claude.json means no warning."""
        result = check_scope_recommendation(tmp_path, home=tmp_path)
        assert result.ok is True
        assert "No user-scoped config" in result.message

    def test_user_config_without_tapps_passes(self, tmp_path):
        """~/.claude.json exists but has no tapps-mcp entry."""
        user_config = tmp_path / ".claude.json"
        user_config.write_text('{"mcpServers": {}}', encoding="utf-8")
        result = check_scope_recommendation(tmp_path, home=tmp_path)
        assert result.ok is True

    def test_user_config_with_tapps_warns(self, tmp_path):
        """~/.claude.json has tapps-mcp entry -- should warn."""
        user_config = tmp_path / ".claude.json"
        user_config.write_text(
            json.dumps({"mcpServers": {"tapps-mcp": {"command": "tapps-mcp"}}}),
            encoding="utf-8",
        )
        result = check_scope_recommendation(tmp_path, home=tmp_path)
        assert result.ok is False
        assert "user scope" in result.message
        assert "tapps-mcp init --scope project" in result.detail

    def test_both_scopes_warns_differently(self, tmp_path):
        """Both user and project config exist -- specific warning."""
        user_config = tmp_path / ".claude.json"
        user_config.write_text(
            json.dumps({"mcpServers": {"tapps-mcp": {"command": "tapps-mcp"}}}),
            encoding="utf-8",
        )
        project_config = tmp_path / ".mcp.json"
        project_config.write_text(
            json.dumps({"mcpServers": {"tapps-mcp": {"command": "tapps-mcp"}}}),
            encoding="utf-8",
        )
        result = check_scope_recommendation(tmp_path, home=tmp_path)
        assert result.ok is False
        assert "both" in result.message.lower()

    def test_invalid_json_passes(self, tmp_path):
        """Malformed ~/.claude.json is treated as non-issue."""
        user_config = tmp_path / ".claude.json"
        user_config.write_text("not json!", encoding="utf-8")
        result = check_scope_recommendation(tmp_path, home=tmp_path)
        assert result.ok is True


# ---------------------------------------------------------------------------
# check_mcp_client_config (Story 68.6)
# ---------------------------------------------------------------------------


class TestCheckMcpClientConfig:
    """Tests for the aggregate MCP client config discoverability check."""

    def test_config_found_in_cursor(self, tmp_path):
        """Passes when tapps-mcp is in .cursor/mcp.json."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config = {"mcpServers": {"tapps-mcp": {"command": "tapps-mcp"}}}
        (cursor_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
        result = check_mcp_client_config(tmp_path, home=tmp_path)
        assert result.ok is True
        assert "Cursor" in result.message

    def test_config_found_in_vscode(self, tmp_path):
        """Passes when tapps-mcp is in .vscode/mcp.json."""
        vscode_dir = tmp_path / ".vscode"
        vscode_dir.mkdir()
        config = {"servers": {"tapps-mcp": {"command": "tapps-mcp"}}}
        (vscode_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
        result = check_mcp_client_config(tmp_path, home=tmp_path)
        assert result.ok is True
        assert "VS Code" in result.message

    def test_config_found_in_claude_code_project(self, tmp_path):
        """Passes when tapps-mcp is in .mcp.json."""
        config = {"mcpServers": {"tapps-mcp": {"command": "tapps-mcp"}}}
        (tmp_path / ".mcp.json").write_text(json.dumps(config), encoding="utf-8")
        result = check_mcp_client_config(tmp_path, home=tmp_path)
        assert result.ok is True
        assert "Claude Code (project)" in result.message

    def test_config_found_in_claude_code_user(self, tmp_path):
        """Passes when tapps-mcp is in ~/.claude.json."""
        config = {"mcpServers": {"tapps-mcp": {"command": "tapps-mcp"}}}
        (tmp_path / ".claude.json").write_text(json.dumps(config), encoding="utf-8")
        result = check_mcp_client_config(tmp_path, home=tmp_path)
        assert result.ok is True
        assert "Claude Code (user)" in result.message

    def test_config_found_in_multiple(self, tmp_path):
        """Reports all clients when tapps-mcp is in multiple configs."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        cursor_config = {"mcpServers": {"tapps-mcp": {"command": "tapps-mcp"}}}
        (cursor_dir / "mcp.json").write_text(json.dumps(cursor_config), encoding="utf-8")
        project_config = {"mcpServers": {"tapps-mcp": {"command": "tapps-mcp"}}}
        (tmp_path / ".mcp.json").write_text(json.dumps(project_config), encoding="utf-8")
        result = check_mcp_client_config(tmp_path, home=tmp_path)
        assert result.ok is True
        assert "Cursor" in result.message
        assert "Claude Code (project)" in result.message

    def test_no_config_files(self, tmp_path):
        """Fails with suggestion when no config files exist."""
        result = check_mcp_client_config(tmp_path, home=tmp_path)
        assert result.ok is False
        assert "not found in any" in result.message
        assert ".cursor/mcp.json" in result.detail
        assert "uv" in result.detail

    def test_config_exists_without_tapps(self, tmp_path):
        """Fails with suggestion when config exists but lacks tapps-mcp."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config = {"mcpServers": {"other-server": {"command": "other"}}}
        (cursor_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
        result = check_mcp_client_config(tmp_path, home=tmp_path)
        assert result.ok is False
        assert "not found in any" in result.message
        assert "uv" in result.detail

    def test_included_in_collect_checks(self, tmp_path):
        """The aggregate check is included in _collect_checks."""
        checks = _collect_checks(tmp_path, quick=True)
        names = [c.name for c in checks]
        assert "MCP client config" in names


# ---------------------------------------------------------------------------
# TAP-2199: detect unresolved ${...} in TAPPS_MCP_PROJECT_ROOT env values
# ---------------------------------------------------------------------------


class TestCheckMcpConfigUnresolvedProjectRoot:
    """Probe surfaces broken consumer .mcp.json before tapps_upgrade self-heals."""

    def test_no_configs_passes(self, tmp_path):
        """No config files on disk = nothing broken to report."""
        result = check_mcp_config_unresolved_project_root(tmp_path)
        assert result.ok is True
        assert "no unresolved" in result.message

    def test_clean_absolute_path_passes(self, tmp_path):
        """A resolved absolute path is accepted."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "tapps-mcp",
                    "env": {"TAPPS_MCP_PROJECT_ROOT": str(tmp_path)},
                },
            },
        }
        (cursor_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
        result = check_mcp_config_unresolved_project_root(tmp_path)
        assert result.ok is True

    def test_dot_passes(self, tmp_path):
        """The Claude Code "." convention is accepted."""
        config = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "tapps-mcp",
                    "env": {"TAPPS_MCP_PROJECT_ROOT": "."},
                },
            },
        }
        (tmp_path / ".mcp.json").write_text(json.dumps(config), encoding="utf-8")
        result = check_mcp_config_unresolved_project_root(tmp_path)
        assert result.ok is True

    def test_workspacefolder_literal_fails(self, tmp_path):
        """Detects the TAP-2199 broken state in Cursor config."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "tapps-mcp",
                    "env": {"TAPPS_MCP_PROJECT_ROOT": "${workspaceFolder}"},
                },
            },
        }
        (cursor_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
        result = check_mcp_config_unresolved_project_root(tmp_path)
        assert result.ok is False
        assert "Cursor" in result.detail
        assert "${workspaceFolder}" in result.detail
        assert "tapps-mcp upgrade" in result.detail

    def test_docs_mcp_env_also_checked(self, tmp_path):
        """``DOCS_MCP_PROJECT_ROOT`` is checked alongside ``TAPPS_MCP_PROJECT_ROOT``."""
        vscode_dir = tmp_path / ".vscode"
        vscode_dir.mkdir()
        config = {
            "servers": {
                "docs-mcp": {
                    "command": "docsmcp",
                    "env": {"DOCS_MCP_PROJECT_ROOT": "${workspaceFolder}"},
                },
            },
        }
        (vscode_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
        result = check_mcp_config_unresolved_project_root(tmp_path)
        assert result.ok is False
        assert "DOCS_MCP_PROJECT_ROOT" in result.detail

    def test_other_env_keys_ignored(self, tmp_path):
        """Unresolved ${...} in OTHER env keys (auth tokens, API keys) is not flagged.
        Those are env-var substitutions consumed by the host launcher.
        """
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "tapps-mcp",
                    "env": {
                        "TAPPS_MCP_PROJECT_ROOT": str(tmp_path),
                        "TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN": "${TAPPS_BRAIN_AUTH_TOKEN}",
                        "TAPPS_MCP_CONTEXT7_API_KEY": "${TAPPS_MCP_CONTEXT7_API_KEY}",
                    },
                },
            },
        }
        (cursor_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
        result = check_mcp_config_unresolved_project_root(tmp_path)
        assert result.ok is True

    def test_multiple_broken_servers_reported(self, tmp_path):
        """Counts and reports broken env values across multiple servers/hosts."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "tapps-mcp",
                    "env": {"TAPPS_MCP_PROJECT_ROOT": "${workspaceFolder}"},
                },
                "docs-mcp": {
                    "command": "docsmcp",
                    "env": {"DOCS_MCP_PROJECT_ROOT": "${workspaceFolder}"},
                },
            },
        }
        (cursor_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
        result = check_mcp_config_unresolved_project_root(tmp_path)
        assert result.ok is False
        assert "2 env value" in result.message

    def test_malformed_json_does_not_raise(self, tmp_path):
        """Invalid JSON is silently ignored (other checks own that error)."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        (cursor_dir / "mcp.json").write_text("not json {", encoding="utf-8")
        result = check_mcp_config_unresolved_project_root(tmp_path)
        assert result.ok is True

    def test_included_in_collect_checks(self, tmp_path):
        """The TAP-2199 probe is wired into _collect_checks."""
        checks = _collect_checks(tmp_path, quick=True)
        names = [c.name for c in checks]
        assert "MCP env (TAP-2199)" in names
        assert "Memory pipeline (effective config)" in names


# ---------------------------------------------------------------------------
# Doctor Quick Mode (Epic 49.3)
# ---------------------------------------------------------------------------


class TestDoctorQuickMode:
    """Tests for doctor quick mode (Epic 49.3)."""

    def test_collect_checks_quick_skips_quality_tools(self, tmp_path):
        """Quick mode skips quality tool checks."""
        checks = _collect_checks(tmp_path, quick=True)
        names = [c.name for c in checks]
        # Should NOT contain individual tool names (prefixed with "Tool:")
        assert not any("Tool:" in n for n in names)
        # Should contain the skip placeholder
        assert "Quality tools" in names
        # The skip entry should pass and mention quick mode
        skip_check = next(c for c in checks if c.name == "Quality tools")
        assert skip_check.ok is True
        assert "quick mode" in skip_check.message.lower()

    def test_collect_checks_full_includes_quality_tools(self, tmp_path):
        """Full mode (default) includes quality tool checks."""
        with patch("tapps_mcp.tools.tool_detection.detect_installed_tools", return_value=[]):
            checks = _collect_checks(tmp_path, quick=False)
        names = [c.name for c in checks]
        # Should NOT contain the skip placeholder
        assert "Quality tools" not in names

    def test_run_doctor_structured_quick(self, tmp_path):
        """run_doctor_structured with quick=True includes quick_mode flag."""
        with patch("tapps_mcp.distribution.doctor._collect_checks") as mock_collect:
            mock_collect.return_value = [CheckResult("test", True, "ok")]
            result = run_doctor_structured(project_root=str(tmp_path), quick=True)
        assert result["quick_mode"] is True
        mock_collect.assert_called_once_with(tmp_path.resolve(), quick=True)

    def test_run_doctor_structured_default_not_quick(self, tmp_path):
        """run_doctor_structured defaults to quick_mode=False."""
        with patch("tapps_mcp.distribution.doctor._collect_checks") as mock_collect:
            mock_collect.return_value = [CheckResult("test", True, "ok")]
            result = run_doctor_structured(project_root=str(tmp_path))
        assert result["quick_mode"] is False

    def test_cli_doctor_quick_flag(self):
        """CLI doctor --quick flag works."""
        runner = CliRunner()
        with patch("tapps_mcp.distribution.doctor.run_doctor", return_value=True) as mock_run:
            result = runner.invoke(main, ["doctor", "--quick"])
        assert result.exit_code == 0
        mock_run.assert_called_once_with(project_root=".", quick=True)

    def test_cli_doctor_without_quick(self):
        """CLI doctor without --quick defaults to quick=False."""
        runner = CliRunner()
        with patch("tapps_mcp.distribution.doctor.run_doctor", return_value=True) as mock_run:
            result = runner.invoke(main, ["doctor"])
        assert result.exit_code == 0
        mock_run.assert_called_once_with(project_root=".", quick=False)


class TestCheckPlaintextSecrets:
    """Issue #80.3 — doctor flags plaintext secrets in MCP config files."""

    def test_clean_config_passes(self, tmp_path):
        (tmp_path / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "tapps-mcp": {
                            "command": "tapps-mcp",
                            "args": ["serve"],
                            "env": {"TAPPS_MCP_PROJECT_ROOT": "."},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        result = check_plaintext_secrets(tmp_path)
        assert result.ok is True

    def test_plaintext_api_key_fails(self, tmp_path):
        (tmp_path / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "tapps-mcp": {
                            "command": "tapps-mcp",
                            "args": ["serve"],
                            "env": {"CONTEXT7_API_KEY": "ctx7sk-plain"},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        result = check_plaintext_secrets(tmp_path)
        assert result.ok is False
        assert "CONTEXT7_API_KEY" in result.message

    def test_interpolated_value_passes(self, tmp_path):
        (tmp_path / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "tapps-mcp": {
                            "command": "tapps-mcp",
                            "args": ["serve"],
                            "env": {"CONTEXT7_API_KEY": "${CONTEXT7_API_KEY}"},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        result = check_plaintext_secrets(tmp_path)
        assert result.ok is True

    def test_no_config_passes(self, tmp_path):
        result = check_plaintext_secrets(tmp_path)
        assert result.ok is True


# ---------------------------------------------------------------------------
# check_uv_path_mismatch (Issue #77)
# ---------------------------------------------------------------------------


class TestCheckUvPathMismatch:
    """Tests for the uv PATH mismatch doctor check."""

    def test_passes_when_not_uv_project(self, tmp_path):
        """Non-uv projects should pass (check skipped)."""
        result = check_uv_path_mismatch(tmp_path)
        assert result.ok is True

    def test_passes_when_config_uses_uv_command(self, tmp_path):
        """uv-managed project with uv command in MCP config should pass."""
        # Create a uv project with tapps-mcp extra
        (tmp_path / "uv.lock").write_text("", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\n[project.optional-dependencies]\nmcp = ["tapps-mcp"]\n',
            encoding="utf-8",
        )
        # MCP config uses uv command
        (tmp_path / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "tapps-mcp": {
                            "command": "uv",
                            "args": ["run", "--extra", "mcp", "--no-sync", "tapps-mcp", "serve"],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        with patch(
            "tapps_mcp.distribution.setup_generator.shutil.which", return_value="/usr/bin/uv"
        ):
            result = check_uv_path_mismatch(tmp_path)
        assert result.ok is True

    def test_warns_when_config_uses_bare_tapps_mcp(self, tmp_path):
        """uv-managed project with bare tapps-mcp command should warn."""
        (tmp_path / "uv.lock").write_text("", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\n[project.optional-dependencies]\nmcp = ["tapps-mcp"]\n',
            encoding="utf-8",
        )
        # MCP config uses bare tapps-mcp command
        (tmp_path / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "tapps-mcp": {
                            "command": "tapps-mcp",
                            "args": ["serve"],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        with patch(
            "tapps_mcp.distribution.setup_generator.shutil.which", return_value="/usr/bin/uv"
        ):
            result = check_uv_path_mismatch(tmp_path)
        assert result.ok is False
        assert "bare" in result.message
        assert ".mcp.json" in result.message


# ---------------------------------------------------------------------------
# TAP-980 Phase A + TAP-977: new checks for linear-standards + skills
# ---------------------------------------------------------------------------


class TestCheckAgentsMdStampMatchesPackage:
    """TAP-982: strict stamp check for release gating."""

    def test_matching_stamp_passes(self, tmp_path):
        from tapps_mcp import __version__
        from tapps_mcp.distribution.doctor import check_agents_md_stamp_matches_package

        (tmp_path / "AGENTS.md").write_text(
            f"<!-- tapps-agents-version: {__version__} -->\n# AGENTS\n"
        )
        result = check_agents_md_stamp_matches_package(tmp_path)
        assert result.ok is True
        assert __version__ in result.message

    def test_missing_file_fails(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_agents_md_stamp_matches_package

        result = check_agents_md_stamp_matches_package(tmp_path)
        assert result.ok is False
        assert "not found" in result.message

    def test_wrong_stamp_fails_with_both_versions(self, tmp_path):
        from tapps_mcp import __version__
        from tapps_mcp.distribution.doctor import check_agents_md_stamp_matches_package

        (tmp_path / "AGENTS.md").write_text(
            "<!-- tapps-agents-version: 0.0.1 -->\n# AGENTS\n"
        )
        result = check_agents_md_stamp_matches_package(tmp_path)
        assert result.ok is False
        assert "0.0.1" in result.message
        assert __version__ in result.message
        assert "upgrade" in result.detail

    def test_wrong_stamp_with_skip_files_points_to_bump_stamps(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_agents_md_stamp_matches_package

        (tmp_path / ".tapps-mcp.yaml").write_text(
            "upgrade_skip_files:\n  - AGENTS.md\n", encoding="utf-8"
        )
        (tmp_path / "AGENTS.md").write_text(
            "<!-- tapps-agents-version: 0.0.1 -->\n# AGENTS\n"
        )
        result = check_agents_md_stamp_matches_package(tmp_path)
        assert result.ok is False
        assert "upgrade_skip_files" in result.message
        assert "bump-stamps" in result.detail

    def test_missing_stamp_fails(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_agents_md_stamp_matches_package

        (tmp_path / "AGENTS.md").write_text("# AGENTS (no stamp)\n")
        result = check_agents_md_stamp_matches_package(tmp_path)
        assert result.ok is False
        assert "<none>" in result.message


class TestCheckLinearStandardsRule:
    """check_linear_standards_rule covers .claude/rules/linear-standards.md."""

    def test_present_passes(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_linear_standards_rule

        (tmp_path / ".claude" / "rules").mkdir(parents=True)
        (tmp_path / ".claude" / "rules" / "linear-standards.md").write_text(
            "# Linear Standards\n"
        )
        result = check_linear_standards_rule(tmp_path)
        assert result.ok is True
        assert "linear-standards.md" in result.message

    def test_absent_fails_with_hint(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_linear_standards_rule

        result = check_linear_standards_rule(tmp_path)
        assert result.ok is False
        assert "not found" in result.message
        assert "upgrade" in result.detail


class TestCheckScopedRulesPresence:
    """TAP-978 scoped rules report presence + gating mechanism status."""

    def _make_python_repo(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

    def _make_infra_repo(self, tmp_path):
        (tmp_path / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")

    def _write_rule(self, tmp_path, filename):
        (tmp_path / ".claude" / "rules").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".claude" / "rules" / filename).write_text("# rule\n")

    def test_security_present_python_repo_passes(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_security_rule

        self._make_python_repo(tmp_path)
        self._write_rule(tmp_path, "security.md")
        result = check_security_rule(tmp_path)
        assert result.ok is True
        assert "Present" in result.message
        assert "python" in result.message.lower()

    def test_security_absent_python_repo_fails(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_security_rule

        self._make_python_repo(tmp_path)
        result = check_security_rule(tmp_path)
        assert result.ok is False
        assert "not found" in result.message
        assert "upgrade" in result.detail

    def test_security_absent_non_python_repo_passes_gate_label(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_security_rule

        result = check_security_rule(tmp_path)
        # Absent-but-gate-not-satisfied is OK — upgrade would skip anyway.
        assert result.ok is True
        assert "Absent" in result.message
        assert "would skip" in result.message

    def test_test_quality_present_python_repo_passes(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_test_quality_rule

        self._make_python_repo(tmp_path)
        self._write_rule(tmp_path, "test-quality.md")
        result = check_test_quality_rule(tmp_path)
        assert result.ok is True
        assert "Present" in result.message

    def test_test_quality_absent_python_repo_fails(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_test_quality_rule

        self._make_python_repo(tmp_path)
        result = check_test_quality_rule(tmp_path)
        assert result.ok is False
        assert "not found" in result.message

    def test_config_files_present_infra_repo_passes(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_config_files_rule

        self._make_infra_repo(tmp_path)
        self._write_rule(tmp_path, "config-files.md")
        result = check_config_files_rule(tmp_path)
        assert result.ok is True
        assert "infra" in result.message

    def test_config_files_absent_infra_repo_fails(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_config_files_rule

        self._make_infra_repo(tmp_path)
        result = check_config_files_rule(tmp_path)
        assert result.ok is False
        assert "not found" in result.message

    def test_config_files_absent_bare_repo_ok(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_config_files_rule

        result = check_config_files_rule(tmp_path)
        # No python or infra — gate fails, upgrade would skip, so absence is fine.
        assert result.ok is True
        assert "would skip" in result.message

    def test_config_files_present_but_gate_failed_warns(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_config_files_rule

        # No pyproject, no Dockerfile — gate fails — but rule is present.
        self._write_rule(tmp_path, "config-files.md")
        result = check_config_files_rule(tmp_path)
        # ok=True (rule will still load) but the detail explains gate state.
        assert result.ok is True
        assert "gate not satisfied" in result.message
        assert result.detail is not None


class TestCheckLinearIssueSkillCurrent:
    """check_linear_issue_skill_current gates on save_issue in allowed-tools."""

    def test_current_skill_passes(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_linear_issue_skill_current

        skill_dir = tmp_path / ".claude" / "skills" / "linear-issue"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: linear-issue\nallowed-tools: "
            "mcp__docs-mcp__docs_generate_story "
            "mcp__plugin_linear_linear__save_issue\n---\n"
        )
        result = check_linear_issue_skill_current(tmp_path)
        assert result.ok is True

    def test_stale_skill_fails(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_linear_issue_skill_current

        skill_dir = tmp_path / ".claude" / "skills" / "linear-issue"
        skill_dir.mkdir(parents=True)
        # Old version without save_issue in allowed-tools
        (skill_dir / "SKILL.md").write_text(
            "---\nname: linear-issue\nallowed-tools: "
            "mcp__docs-mcp__docs_generate_story\n---\n"
        )
        result = check_linear_issue_skill_current(tmp_path)
        assert result.ok is False
        assert "stale" in result.message.lower() or "missing" in result.message.lower()

    def test_absent_skill_fails(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_linear_issue_skill_current

        result = check_linear_issue_skill_current(tmp_path)
        assert result.ok is False
        assert "missing" in result.message.lower()

    def test_cursor_host_passes(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_linear_issue_skill_current

        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir(parents=True, exist_ok=True)
        (cursor_dir / "mcp.json").write_text('{"mcpServers": {}}', encoding="utf-8")
        skill_dir = tmp_path / ".cursor" / "skills" / "linear-issue"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: linear-issue\nmcp_tools:\n  - docs_validate_linear_issue\n---\n",
            encoding="utf-8",
        )
        result = check_linear_issue_skill_current(tmp_path)
        assert result.ok is True
        assert "cursor" in result.message


class TestCheckFinishTaskSkill:
    """check_finish_task_skill covers the composite tapps-finish-task skill."""

    _BODY = (
        "---\nname: tapps-finish-task\n---\n"
        "tapps_validate_changed\ntapps_checklist\ntapps-mcp memory save\n" * 5
    )

    def test_present_passes(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_finish_task_skill

        skill_dir = tmp_path / ".claude" / "skills" / "tapps-finish-task"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(self._BODY, encoding="utf-8")
        result = check_finish_task_skill(tmp_path)
        assert result.ok is True

    def test_cursor_host_passes(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_finish_task_skill

        skill_dir = tmp_path / ".cursor" / "skills" / "tapps-finish-task"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(self._BODY, encoding="utf-8")
        result = check_finish_task_skill(tmp_path)
        assert result.ok is True

    def test_stale_finish_task_with_tapps_memory_mcp_fails(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_finish_task_skill

        skill_dir = tmp_path / ".cursor" / "skills" / "tapps-finish-task"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: tapps-finish-task\n---\n"
            "tapps_validate_changed\ntapps_checklist\n"
            "mcp__tapps-mcp__tapps_memory(action=save)\n" * 3,
            encoding="utf-8",
        )
        result = check_finish_task_skill(tmp_path)
        assert result.ok is False
        assert "stale" in result.message.lower()

    def test_absent_fails_with_hint(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_finish_task_skill

        result = check_finish_task_skill(tmp_path)
        assert result.ok is False
        assert "Missing:" in result.message
        assert "upgrade" in result.detail


class TestCheckTappsMemorySkill:
    """check_tapps_memory_skill rejects stale tapps_memory MCP routing."""

    _BODY = (
        "---\nname: tapps-memory\n---\n"
        "tapps-mcp memory save\ntapps_session_notes\n" * 5
    )

    def test_present_passes(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_tapps_memory_skill

        skill_dir = tmp_path / ".cursor" / "skills" / "tapps-memory"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(self._BODY, encoding="utf-8")
        result = check_tapps_memory_skill(tmp_path)
        assert result.ok is True

    def test_stale_memory_skill_fails(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_tapps_memory_skill

        skill_dir = tmp_path / ".cursor" / "skills" / "tapps-memory"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: tapps-memory\n---\n"
            "mcp__tapps-mcp__tapps_memory(action=save)\n" * 5,
            encoding="utf-8",
        )
        result = check_tapps_memory_skill(tmp_path)
        assert result.ok is False
        assert "stale" in result.message.lower()


class TestCheckSessionHandoffSkills:
    """check_session_handoff_skills covers cross-chat transfer skills."""

    def _write_skill(self, base, name: str) -> None:
        skill_dir = base / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        body = f"---\nname: {name}\n---\n"
        if name == "tapps-handoff-session":
            body += "\nsession-handoff.md\ntapps_session_end\ntapps-mcp memory save\np0 gate\n" * 5
        elif name == "tapps-continue-session":
            body += "\nsession-handoff.md\ntapps_session_start\nmemory search\np0 fallback\n" * 5
        (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")

    def test_both_skills_on_claude_passes(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_session_handoff_skills

        base = tmp_path / ".claude" / "skills"
        self._write_skill(base, "tapps-handoff-session")
        self._write_skill(base, "tapps-continue-session")
        result = check_session_handoff_skills(tmp_path)
        assert result.ok is True
        assert "tapps-handoff-session" in result.message

    def test_missing_continue_fails(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_session_handoff_skills

        base = tmp_path / ".cursor" / "skills"
        self._write_skill(base, "tapps-handoff-session")
        result = check_session_handoff_skills(tmp_path)
        assert result.ok is False
        assert "tapps-continue-session" in result.message

    def test_stub_handoff_fails_content_check(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_session_handoff_skills

        base = tmp_path / ".cursor" / "skills"
        for name in ("tapps-handoff-session", "tapps-continue-session"):
            skill_dir = base / name
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("---\nname: stub\n---\n", encoding="utf-8")
        result = check_session_handoff_skills(tmp_path)
        assert result.ok is False
        assert "stale" in result.message.lower() or "stub" in result.message.lower()

    def test_stale_handoff_with_tapps_memory_mcp_fails(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_session_handoff_skills

        base = tmp_path / ".cursor" / "skills"
        for name in ("tapps-handoff-session", "tapps-continue-session"):
            skill_dir = base / name
            skill_dir.mkdir(parents=True)
            body = f"---\nname: {name}\n---\n"
            body += "session-handoff.md\n"
            if name == "tapps-handoff-session":
                body += "tapps_session_end\n"
                body += "mcp__tapps-mcp__tapps_memory(action=save)\n" * 3
            else:
                body += "tapps_session_start\n" * 5
            (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
        result = check_session_handoff_skills(tmp_path)
        assert result.ok is False
        assert "stale" in result.message.lower()

    def test_cursor_only_ignores_empty_claude_dir(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_session_handoff_skills

        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir(parents=True, exist_ok=True)
        (cursor_dir / "mcp.json").write_text('{"mcpServers": {}}', encoding="utf-8")
        (tmp_path / ".claude" / "skills" / "stale-placeholder").mkdir(parents=True)
        base = tmp_path / ".cursor" / "skills"
        self._write_skill(base, "tapps-handoff-session")
        self._write_skill(base, "tapps-continue-session")
        result = check_session_handoff_skills(tmp_path)
        assert result.ok is True


class TestCheckSessionHandoffSchema:
    def test_missing_handoff_passes(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_session_handoff_schema

        result = check_session_handoff_schema(tmp_path)
        assert result.ok is True
        assert "optional" in result.message.lower()

    def test_open_without_p0_fails(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_session_handoff_schema

        path = tmp_path / ".tapps-mcp" / "session-handoff.md"
        path.parent.mkdir(parents=True)
        path.write_text(
            "# Session handoff\n**Updated:** 2026-06-11T12:00:00Z\n\n"
            "## Open\n- unfinished\n\n## Next (P0)\n- none\n",
            encoding="utf-8",
        )
        result = check_session_handoff_schema(tmp_path)
        assert result.ok is False
        assert "p0" in result.message.lower()

    def test_valid_handoff_passes(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_session_handoff_schema

        path = tmp_path / ".tapps-mcp" / "session-handoff.md"
        path.parent.mkdir(parents=True)
        path.write_text(
            "# Session handoff\n**Updated:** 2026-06-11T12:00:00Z\n\n"
            "## Open\n- none\n\n## Next (P0)\n- ship wave 2\n",
            encoding="utf-8",
        )
        result = check_session_handoff_schema(tmp_path)
        assert result.ok is True


class TestCheckCacheGateBlockHint:
    def test_block_mode_ok(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_cache_gate_block_hint

        (tmp_path / ".tapps-mcp.yaml").write_text(
            "linear_enforce_cache_gate: block\n",
            encoding="utf-8",
        )
        result = check_cache_gate_block_hint(tmp_path)
        assert result.ok is True
        assert "block" in result.message

    def test_warn_high_violations_recommends_block(self, tmp_path):
        import time

        from tapps_mcp.distribution.doctor import check_cache_gate_block_hint

        hooks = tmp_path / ".claude" / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "tapps-pre-linear-list.sh").write_text('MODE="warn"\n', encoding="utf-8")
        log = tmp_path / ".tapps-mcp" / ".cache-gate-violations.jsonl"
        log.parent.mkdir(parents=True)
        now = time.time()
        lines = [
            json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "category": "gate_miss"})
            for _ in range(25)
        ]
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = check_cache_gate_block_hint(tmp_path)
        assert result.ok is True
        assert "block" in (result.detail or "").lower()


class TestCheckInstallGitHooksHint:
    def test_high_engagement_low_pass_rate_hints(self, tmp_path, monkeypatch):
        from tapps_mcp.distribution.doctor import check_install_git_hooks_hint

        monkeypatch.setenv("TAPPS_METRICS_STORAGE", "local")
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "llm_engagement_level: high\ninstall_git_hooks: false\n",
            encoding="utf-8",
        )
        metrics_dir = tmp_path / ".tapps-mcp" / "metrics"
        metrics_dir.mkdir(parents=True)
        metric = {
            "call_id": "a",
            "tool_name": "tapps_quality_gate",
            "status": "success",
            "duration_ms": 1.0,
            "started_at": "2026-06-11T00:00:00+00:00",
            "completed_at": "2026-06-11T00:00:01+00:00",
            "gate_passed": False,
        }
        from datetime import date

        day = date.today().isoformat()
        (metrics_dir / f"tool_calls_{day}.jsonl").write_text(
            json.dumps(metric) + "\n",
            encoding="utf-8",
        )
        result = check_install_git_hooks_hint(tmp_path)
        assert result.ok is True
        assert "install_git_hooks" in (result.detail or "")


class TestCheckDeprecatedWrapperSkills:
    def test_ok_when_deprecated_absent(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_deprecated_wrapper_skills
        from tapps_mcp.pipeline.platform_skills import generate_skills

        generate_skills(tmp_path, "cursor")
        result = check_deprecated_wrapper_skills(tmp_path)
        assert result.ok is True

    def test_fails_when_deprecated_present(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_deprecated_wrapper_skills

        skill_dir = tmp_path / ".cursor" / "skills" / "tapps-score"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: tapps-score\n---\n", encoding="utf-8")
        result = check_deprecated_wrapper_skills(tmp_path)
        assert result.ok is False
        assert "tapps-score" in result.message


class TestCheckPipelineEnforceRecommendations:
    def test_reports_skip_rate_and_git_hooks_snippet(self, tmp_path):
        import time

        from tapps_mcp.distribution.doctor import check_pipeline_enforce_recommendations

        (tmp_path / ".tapps-mcp.yaml").write_text(
            "llm_engagement_level: medium\ninstall_git_hooks: false\n",
            encoding="utf-8",
        )
        now = int(time.time())
        metrics = tmp_path / ".tapps-mcp" / "loop-metrics.jsonl"
        metrics.parent.mkdir(parents=True)
        rows = []
        for offset in range(8):
            compliant = offset >= 4
            rows.append(
                json.dumps(
                    {
                        "ts": now - offset * 100,
                        "mcp_calls": 1,
                        "tools_used": (
                            ["tapps_validate_changed"] if compliant else ["Edit"]
                        ),
                        "files_edited": ["packages/tapps-mcp/src/tapps_mcp/foo.py"],
                        "checklist_called": compliant,
                        "gate_skipped_files": [],
                    }
                )
            )
        metrics.write_text("\n".join(rows) + "\n", encoding="utf-8")

        result = check_pipeline_enforce_recommendations(tmp_path)
        assert result.ok is True
        assert "gate_skip_rate=50%" in result.message
        assert "install_git_hooks: true" in (result.detail or "")

    def test_cache_gate_violations_recommend_block(self, tmp_path):
        import time

        from tapps_mcp.distribution.doctor import check_pipeline_enforce_recommendations

        hooks = tmp_path / ".claude" / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "tapps-pre-linear-list.sh").write_text('MODE="warn"\n', encoding="utf-8")
        log = tmp_path / ".tapps-mcp" / ".cache-gate-violations.jsonl"
        log.parent.mkdir(parents=True)
        now = time.time()
        lines = [
            json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "category": "gate_miss"})
            for _ in range(22)
        ]
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = check_pipeline_enforce_recommendations(tmp_path)
        assert result.ok is True
        assert "linear_enforce_cache_gate: block" in (result.detail or "")


class TestCheckCursorLoopMetricsTelemetry:
    def test_warns_when_callmcptool_without_resolved_gate(self, tmp_path):
        import time

        from tapps_mcp.distribution.doctor import check_cursor_loop_metrics_telemetry

        metrics = tmp_path / ".tapps-mcp" / "loop-metrics.jsonl"
        metrics.parent.mkdir(parents=True)
        now = int(time.time())
        rows = [
            {
                "ts": now - 100,
                "tools_used": ["CallMcpTool", "Write"],
                "files_edited": ["src/a.py"],
                "gate_skipped_files": ["src/a.py"],
            }
        ]
        metrics.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        result = check_cursor_loop_metrics_telemetry(tmp_path)
        assert result.ok is False
        assert "callmcptool_unwrap=active" in result.message
        assert "CallMcpTool" in (result.detail or "")

    def test_passes_when_gate_tools_resolved(self, tmp_path):
        import time

        from tapps_mcp.distribution.doctor import check_cursor_loop_metrics_telemetry

        metrics = tmp_path / ".tapps-mcp" / "loop-metrics.jsonl"
        metrics.parent.mkdir(parents=True)
        now = int(time.time())
        rows = [
            {
                "ts": now - 100,
                "tools_used": ["tapps_validate_changed", "tapps_checklist"],
                "files_edited": ["src/a.py"],
            }
        ]
        metrics.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        result = check_cursor_loop_metrics_telemetry(tmp_path)
        assert result.ok is True
        assert "callmcptool_unwrap=active" in result.message


class TestCheckContinuousLearningV2Skill:
    def test_cursor_host_passes(self, tmp_path):
        from tapps_mcp.distribution.doctor import check_continuous_learning_v2_skill

        skill_dir = tmp_path / ".cursor" / "skills" / "continuous-learning-v2"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: continuous-learning-v2\n---\n")
        result = check_continuous_learning_v2_skill(tmp_path)
        assert result.ok is True
        assert "cursor" in result.message


# ---------------------------------------------------------------------------
# TAP-2115: REST /v1/tools/list probe with ETag cache + JSON-RPC fallback
# ---------------------------------------------------------------------------


class TestFetchExposedToolsRest:
    """``_fetch_exposed_tools_rest`` prefers cache-validated REST, falls back
    to JSON-RPC handshake on 404/transport errors (pre-TAP-1843 brain).
    """

    def setup_method(self) -> None:
        from tapps_mcp.distribution import doctor as _doctor_mod

        _doctor_mod._TOOLS_CATALOG_CACHE.clear()

    def _mock_response(self, status_code: int, body=None, etag: str = ""):
        from unittest.mock import MagicMock

        resp = MagicMock()
        resp.status_code = status_code
        resp.headers = {"ETag": etag} if etag else {}
        if body is not None:
            resp.json.return_value = body
        return resp

    def test_rest_200_populates_cache_and_returns_tools(self) -> None:
        from unittest.mock import MagicMock

        from tapps_mcp.distribution.doctor import (
            _TOOLS_CATALOG_CACHE,
            _fetch_exposed_tools_rest,
        )

        body = {"tools": [{"name": "memory_save"}, {"name": "memory_list"}]}
        response = self._mock_response(200, body=body, etag='W/"abc123"')
        httpx_mod = MagicMock()
        httpx_mod.get.return_value = response

        exposed, source = _fetch_exposed_tools_rest(
            "http://brain:8080", {"X-Brain-Profile": "operator"}, httpx_mod
        )
        assert exposed == {"memory_save", "memory_list"}
        assert source == "rest"
        # ETag cached for next call.
        cached = _TOOLS_CATALOG_CACHE[("http://brain:8080", "operator")]
        assert cached[0] == 'W/"abc123"'
        # If-None-Match was NOT sent on first call (no prior cache entry).
        assert "If-None-Match" not in httpx_mod.get.call_args.kwargs["headers"]

    def test_rest_304_short_circuits_to_cached_tools(self) -> None:
        from unittest.mock import MagicMock

        from tapps_mcp.distribution.doctor import (
            _TOOLS_CATALOG_CACHE,
            _fetch_exposed_tools_rest,
        )

        _TOOLS_CATALOG_CACHE[("http://brain:8080", "operator")] = (
            'W/"abc123"',
            frozenset({"memory_save", "memory_list"}),
        )
        response = self._mock_response(304)
        httpx_mod = MagicMock()
        httpx_mod.get.return_value = response

        exposed, source = _fetch_exposed_tools_rest(
            "http://brain:8080", {"X-Brain-Profile": "operator"}, httpx_mod
        )
        assert exposed == {"memory_save", "memory_list"}
        assert source == "rest-cached"
        assert httpx_mod.get.call_args.kwargs["headers"]["If-None-Match"] == 'W/"abc123"'

    def test_rest_404_raises_fallback_signal(self) -> None:
        from unittest.mock import MagicMock

        from tapps_mcp.distribution.doctor import (
            _fetch_exposed_tools_rest,
            _ProfileProbeFallbackError,
        )

        response = self._mock_response(404)
        httpx_mod = MagicMock()
        httpx_mod.get.return_value = response

        with pytest.raises(_ProfileProbeFallbackError):
            _fetch_exposed_tools_rest("http://brain:8080", {}, httpx_mod)

    def test_rest_500_raises_probe_error(self) -> None:
        from unittest.mock import MagicMock

        from tapps_mcp.distribution.doctor import (
            _fetch_exposed_tools_rest,
            _ProfileProbeError,
        )

        response = self._mock_response(500)
        httpx_mod = MagicMock()
        httpx_mod.get.return_value = response

        with pytest.raises(_ProfileProbeError):
            _fetch_exposed_tools_rest("http://brain:8080", {}, httpx_mod)


class TestFetchExposedTools:
    """``_fetch_exposed_tools`` dispatcher: REST happy path, JSON-RPC fallback
    on 404, JSON-RPC fallback on transport error.
    """

    def setup_method(self) -> None:
        from tapps_mcp.distribution import doctor as _doctor_mod

        _doctor_mod._TOOLS_CATALOG_CACHE.clear()

    def test_jsonrpc_fallback_on_404(self) -> None:
        """A 404 on /v1/tools/list ⇒ probe falls back to MCP handshake."""
        from unittest.mock import MagicMock

        from tapps_mcp.distribution.doctor import _fetch_exposed_tools

        rest_404 = MagicMock()
        rest_404.status_code = 404
        rest_404.headers = {}

        init_response = MagicMock()
        init_response.status_code = 200
        init_response.headers = {"mcp-session-id": "abc"}
        init_response.raise_for_status = MagicMock()

        list_response = MagicMock()
        list_response.status_code = 200
        list_response.raise_for_status = MagicMock()
        list_response.json.return_value = {
            "result": {"tools": [{"name": "memory_save"}, {"name": "memory_list"}]}
        }

        httpx_mod = MagicMock()
        httpx_mod.get.return_value = rest_404
        httpx_mod.post.side_effect = [init_response, list_response]

        exposed, source = _fetch_exposed_tools(
            "http://brain:8080",
            {"Authorization": "Bearer t"},
            httpx_mod,
            {"Accept": "application/json"},
        )
        assert exposed == {"memory_save", "memory_list"}
        assert source == "jsonrpc"
        # REST was tried first, then both POST legs of the JSON-RPC handshake.
        assert httpx_mod.get.call_count == 1
        assert httpx_mod.post.call_count == 2

    def test_rest_happy_path_skips_jsonrpc(self) -> None:
        """A 200 from REST means we never even attempt the JSON-RPC handshake."""
        from unittest.mock import MagicMock

        from tapps_mcp.distribution.doctor import _fetch_exposed_tools

        rest_response = MagicMock()
        rest_response.status_code = 200
        rest_response.headers = {"ETag": 'W/"v1"'}
        rest_response.json.return_value = {"tools": [{"name": "memory_save"}]}

        httpx_mod = MagicMock()
        httpx_mod.get.return_value = rest_response

        exposed, source = _fetch_exposed_tools(
            "http://brain:8080",
            {"X-Brain-Profile": "minimal"},
            httpx_mod,
            {"Accept": "application/json"},
        )
        assert exposed == {"memory_save"}
        assert source == "rest"
        httpx_mod.post.assert_not_called()


# ---------------------------------------------------------------------------
# Brain HTTP URL resolution for doctor checks
# ---------------------------------------------------------------------------


class TestBrainHttpUrlForChecks:
    """Doctor brain probes resolve URL from env first, then .tapps-mcp.yaml."""

    def test_prefers_env_over_yaml(self, tmp_path, monkeypatch) -> None:
        from tapps_mcp.distribution.doctor import _brain_http_url_for_checks

        monkeypatch.setenv("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", "http://env:8080")
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "memory:\n  brain_http_url: http://yaml:8080\n",
            encoding="utf-8",
        )
        assert _brain_http_url_for_checks(tmp_path) == "http://env:8080"

    def test_falls_back_to_yaml_when_env_unset(self, tmp_path, monkeypatch) -> None:
        from tapps_mcp.distribution.doctor import _brain_http_url_for_checks

        monkeypatch.delenv("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", raising=False)
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "memory:\n  brain_http_url: http://yaml:8080\n",
            encoding="utf-8",
        )
        assert _brain_http_url_for_checks(tmp_path) == "http://yaml:8080"


class TestStripBrainMcpEntries:
    """TAP-1888: strip direct tapps-brain MCP server keys from host configs."""

    def test_removes_tapps_brain_from_cursor_mcp_json(self, tmp_path) -> None:
        from tapps_mcp.distribution.doctor import strip_brain_mcp_entries

        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config = {
            "mcpServers": {
                "tapps-mcp": {"command": "uv", "args": ["run", "tapps-mcp", "serve"]},
                "tapps-brain": {"command": "uv", "args": ["run", "tapps-brain", "serve"]},
            }
        }
        (cursor_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")

        result = strip_brain_mcp_entries(tmp_path)
        assert ".cursor/mcp.json" in result["stripped"]
        updated = json.loads((cursor_dir / "mcp.json").read_text(encoding="utf-8"))
        assert "tapps-brain" not in updated["mcpServers"]
        assert "tapps-mcp" in updated["mcpServers"]

    def test_no_op_when_no_brain_entries(self, tmp_path) -> None:
        from tapps_mcp.distribution.doctor import strip_brain_mcp_entries

        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config = {"mcpServers": {"tapps-mcp": {"command": "uv"}}}
        (cursor_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")

        result = strip_brain_mcp_entries(tmp_path)
        assert result["stripped"] == []


class TestBrainAuthTokenForDoctor:
    """Doctor accepts TAPPS_BRAIN_AUTH_TOKEN for CLI direnv workflows."""

    def test_http_auth_passes_with_tapps_brain_auth_token_env(
        self, tmp_path, monkeypatch
    ) -> None:
        from tapps_mcp.distribution.doctor import check_brain_http_auth

        monkeypatch.setenv("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", "http://brain:8080")
        monkeypatch.setenv("TAPPS_BRAIN_AUTH_TOKEN", "tb_cli_token")
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "memory:\n  brain_project_id: myproj\n",
            encoding="utf-8",
        )
        with patch(
            "tapps_mcp.distribution.doctor._run_auth_probe",
            return_value=None,
        ):
            result = check_brain_http_auth(tmp_path)
        assert result.ok is True
        assert "bearer token" in result.message.lower()

    def test_http_auth_cli_hint_when_token_missing(self, tmp_path, monkeypatch) -> None:
        from tapps_mcp.distribution.doctor import check_brain_http_auth

        monkeypatch.setenv("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", "http://brain:8080")
        monkeypatch.delenv("TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("TAPPS_BRAIN_AUTH_TOKEN", raising=False)
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "memory:\n  brain_project_id: myproj\n",
            encoding="utf-8",
        )
        result = check_brain_http_auth(tmp_path)
        assert result.ok is False
        assert "memory save/get" in result.detail


class TestMemoryCliHttpMode:
    """Doctor advises HTTP-only consumers about memory CLI subcommand coverage."""

    def test_skipped_when_not_http_mode(self, tmp_path) -> None:
        from tapps_mcp.distribution.doctor import check_memory_cli_http_mode

        result = check_memory_cli_http_mode(tmp_path)
        assert result.ok is True
        assert "Not in HTTP-only mode" in result.message

    def test_warns_when_http_without_dsn(self, tmp_path, monkeypatch) -> None:
        from tapps_mcp.distribution.doctor import check_memory_cli_http_mode

        monkeypatch.setenv("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", "http://brain:8080")
        monkeypatch.delenv("TAPPS_BRAIN_DATABASE_URL", raising=False)
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "memory:\n  brain_http_url: http://brain:8080\n",
            encoding="utf-8",
        )
        result = check_memory_cli_http_mode(tmp_path)
        assert result.ok is True
        assert "save/get/recall/search" in result.message
        assert "TAPPS_BRAIN_DATABASE_URL" in result.detail

    def test_ok_when_http_and_dsn(self, tmp_path, monkeypatch) -> None:
        from tapps_mcp.distribution.doctor import check_memory_cli_http_mode

        monkeypatch.setenv("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", "http://brain:8080")
        monkeypatch.setenv("TAPPS_BRAIN_DATABASE_URL", "postgresql://local/brain")
        result = check_memory_cli_http_mode(tmp_path)
        assert result.ok is True
        assert "all memory CLI subcommands" in result.message


class TestBrainVersionFloor:
    """Doctor enforces the hard brain version floor."""

    def test_fails_when_running_brain_below_floor(self, tmp_path, monkeypatch) -> None:
        from tapps_mcp.distribution.doctor import check_brain_version_floor

        monkeypatch.setenv("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", "http://brain:8080")
        with patch(
            "tapps_core.brain_bridge.check_brain_version",
            return_value={
                "ok": False,
                "skipped": False,
                "degraded": False,
                "version": "3.20.0",
                "floor": "3.24.0",
                "errors": ["tapps-brain version 3.20.0 does not satisfy required range"],
            },
        ):
            result = check_brain_version_floor(tmp_path)
        assert result.ok is False
        assert "3.24.0" in (result.detail or "")

    def test_passes_when_running_brain_meets_floor(self, tmp_path, monkeypatch) -> None:
        from tapps_mcp.distribution.doctor import check_brain_version_floor

        monkeypatch.setenv("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", "http://brain:8080")
        with patch(
            "tapps_core.brain_bridge.check_brain_version",
            return_value={
                "ok": True,
                "skipped": False,
                "degraded": False,
                "version": "3.24.0",
                "floor": "3.24.0",
                "errors": [],
            },
        ):
            result = check_brain_version_floor(tmp_path)
        assert result.ok is True
        assert "3.24.0" in result.message


# ---------------------------------------------------------------------------
# TAP-2025: check_brain_version_delta
# ---------------------------------------------------------------------------


class TestParseVersionTuple:
    """Tests for _parse_version_tuple helper."""

    def test_full_version(self) -> None:
        assert _parse_version_tuple("3.18.0") == (3, 18, 0)

    def test_two_part_version(self) -> None:
        assert _parse_version_tuple("3.18") == (3, 18, 0)

    def test_parse_error_returns_zeros(self) -> None:
        assert _parse_version_tuple("not-a-version") == (0, 0, 0)


class TestReadBrainFloorPin:
    """Tests for _read_brain_floor_pin helper."""

    def test_reads_floor_from_metadata(self) -> None:
        with patch(
            "tapps_mcp.distribution.doctor._requires",
            return_value=["tapps-brain>=3.18.0,<4", "pydantic>=2"],
        ):
            result = _read_brain_floor_pin()
        assert result == "3.18.0"

    def test_returns_none_when_absent(self) -> None:
        with patch(
            "tapps_mcp.distribution.doctor._requires",
            return_value=["pydantic>=2"],
        ):
            result = _read_brain_floor_pin()
        assert result is None


class TestCheckBrainVersionDelta:
    """TAP-2025: check_brain_version_delta covers WARN, CRITICAL, and OK paths."""

    def _make_mock_response(self, brain_version: str) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"brain_version": brain_version}
        return resp

    def test_skip_when_not_http_mode(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Passes silently when TAPPS_MCP_MEMORY_BRAIN_HTTP_URL is unset."""
        with patch.dict("os.environ", {}, clear=True):
            result = check_brain_version_delta(tmp_path)
        assert result.ok is True
        assert "Not in HTTP mode" in result.message

    def test_ok_when_delta_within_two(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """running=3.20.0, floor=3.18.0 → delta=2, passes."""
        httpx_mod = MagicMock()
        httpx_mod.get.return_value = self._make_mock_response("3.20.0")

        with (
            patch.dict("os.environ", {"TAPPS_MCP_MEMORY_BRAIN_HTTP_URL": "http://brain:8080"}),
            patch("tapps_mcp.distribution.doctor.httpx", httpx_mod),
            patch("tapps_mcp.distribution.doctor._read_brain_floor_pin", return_value="3.18.0"),
        ):
            result = check_brain_version_delta(tmp_path)
        assert result.ok is True
        assert "3.20" in result.message
        assert "3.18" in result.message

    def test_warn_when_minor_delta_exceeds_two(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """running=3.18.0, floor=3.8.0 → delta=10, WARN (False)."""
        httpx_mod = MagicMock()
        httpx_mod.get.return_value = self._make_mock_response("3.18.0")

        with (
            patch.dict("os.environ", {"TAPPS_MCP_MEMORY_BRAIN_HTTP_URL": "http://brain:8080"}),
            patch("tapps_mcp.distribution.doctor.httpx", httpx_mod),
            patch("tapps_mcp.distribution.doctor._read_brain_floor_pin", return_value="3.8.0"),
        ):
            result = check_brain_version_delta(tmp_path)
        assert result.ok is False
        assert "WARN" in result.message
        assert "10" in result.message

    def test_critical_when_major_delta(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """running=4.0.0, floor=3.18.0 → major delta=1, CRITICAL (False)."""
        httpx_mod = MagicMock()
        httpx_mod.get.return_value = self._make_mock_response("4.0.0")

        with (
            patch.dict("os.environ", {"TAPPS_MCP_MEMORY_BRAIN_HTTP_URL": "http://brain:8080"}),
            patch("tapps_mcp.distribution.doctor.httpx", httpx_mod),
            patch("tapps_mcp.distribution.doctor._read_brain_floor_pin", return_value="3.18.0"),
        ):
            result = check_brain_version_delta(tmp_path)
        assert result.ok is False
        assert "CRITICAL" in result.message
        assert "4.0" in result.message

    def test_passes_when_floor_unresolvable(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Informational pass when importlib metadata unavailable."""
        httpx_mod = MagicMock()
        httpx_mod.get.return_value = self._make_mock_response("3.20.0")

        with (
            patch.dict("os.environ", {"TAPPS_MCP_MEMORY_BRAIN_HTTP_URL": "http://brain:8080"}),
            patch("tapps_mcp.distribution.doctor.httpx", httpx_mod),
            patch("tapps_mcp.distribution.doctor._read_brain_floor_pin", return_value=None),
        ):
            result = check_brain_version_delta(tmp_path)
        assert result.ok is True
        assert "3.20" in result.message


# ---------------------------------------------------------------------------
# TAP-2026 / TAP-1989: check_mcp_tool_budget
# ---------------------------------------------------------------------------


class TestCheckMcpToolBudget:
    """TAP-2026: per-server eager-tool budget WARN."""

    def _mcp_json(self, tmp_path, servers: dict) -> None:
        import json as _json
        (tmp_path / ".mcp.json").write_text(_json.dumps({"mcpServers": servers}))

    def test_skips_when_no_mcp_json(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Passes silently when no MCP config is present."""
        result = check_mcp_tool_budget(tmp_path)
        assert result.ok is True
        assert "No project MCP config" in result.message

    def test_ok_within_default_budget(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """tapps-quality (9 eager tools: 8 from TAP-1986 + tapps_usage added in v3.11.0) is within default budget of 20."""
        self._mcp_json(tmp_path, {"tapps-quality": {
            "command": "uv", "args": ["run", "tapps-mcp", "serve", "--mode", "quality"],
        }})
        result = check_mcp_tool_budget(tmp_path)
        assert result.ok is True
        assert "9" in result.message

    def test_warn_15_tools_at_budget_9(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """quality preset has 9 eager tools; budget=9 is exactly at limit (OK), budget=8 would WARN."""
        self._mcp_json(tmp_path, {"tapps-quality": {
            "command": "uv", "args": ["run", "tapps-mcp", "serve", "--mode", "quality"],
        }})
        (tmp_path / ".tapps-mcp.yaml").write_text("doctor_tool_budget_limit: 9\n")
        result = check_mcp_tool_budget(tmp_path)
        # 9 eager tools <= budget 9 → OK (no WARN)
        assert result.ok is True
        assert "9" in result.message

    def test_full_mode_warns_over_default_budget(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """tapps-mcp full has 9 eager tools, which is within default budget of 20."""
        self._mcp_json(tmp_path, {"tapps-mcp": {
            "command": "uv", "args": ["run", "tapps-mcp", "serve"],
        }})
        result = check_mcp_tool_budget(tmp_path)
        # 9 eager tools ≤ 20 → OK (no WARN)
        assert result.ok is True
        assert "9" in result.message

    def test_admin_mode_within_default_budget(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """tapps-admin has 1 eager tool (tapps_usage), well within budget."""
        self._mcp_json(tmp_path, {"tapps-admin": {
            "command": "uv", "args": ["run", "tapps-mcp", "serve", "--mode", "admin"],
        }})
        result = check_mcp_tool_budget(tmp_path)
        assert result.ok is True
        assert "1" in result.message

    def test_unknown_server_skipped(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Unknown servers (e.g. plain HTTP) are silently skipped."""
        self._mcp_json(tmp_path, {"my-custom-mcp": {
            "command": "node", "args": ["server.js"],
        }})
        result = check_mcp_tool_budget(tmp_path)
        assert result.ok is True
        assert "No recognized" in result.message


class TestCheckNltPartialEnablement:
    """Epic 109.5: partial-enablement WARN thresholds for nlt-* MCP servers."""

    def _cursor_mcp_json(self, tmp_path, servers: dict) -> None:
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir(parents=True, exist_ok=True)
        cursor_dir.joinpath("mcp.json").write_text(
            json.dumps({"mcpServers": servers}),
            encoding="utf-8",
        )

    def test_skips_when_no_nlt_servers(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        self._cursor_mcp_json(tmp_path, {"tapps-mcp": {"command": "tapps-mcp", "args": ["serve"]}})
        result = check_nlt_partial_enablement(tmp_path)
        assert result.ok is True
        assert "No nlt-*" in result.message

    def test_developer_bundle_within_targets(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        self._cursor_mcp_json(
            tmp_path,
            {
                "nlt-build": {"command": "tapps-mcp", "args": ["serve", "--profile", "nlt-build"]},
                "nlt-memory": {
                    "command": "tapps-mcp",
                    "args": ["serve", "--profile", "nlt-memory"],
                },
                "nlt-linear-issues": {
                    "command": "tapps-platform",
                    "args": ["serve", "--profile", "nlt-linear-issues"],
                },
            },
        )
        result = check_nlt_partial_enablement(tmp_path)
        assert result.ok is True
        assert "combined eager=18" in result.message
        assert "nlt-build: 9 eager / 18 total" in result.message
        assert "nlt-memory: 2 eager / 4 total" in result.message
        assert "nlt-linear-issues: 7 eager / 15 total" in result.message

    def test_all_six_servers_in_config_passes_when_inferred_full(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        self._cursor_mcp_json(
            tmp_path,
            {
                "nlt-build": {"command": "tapps-mcp", "args": ["serve", "--profile", "nlt-build"]},
                "nlt-memory": {
                    "command": "tapps-mcp",
                    "args": ["serve", "--profile", "nlt-memory"],
                },
                "nlt-setup": {
                    "command": "tapps-mcp",
                    "args": ["serve", "--profile", "nlt-setup"],
                },
                "nlt-linear-issues": {
                    "command": "tapps-platform",
                    "args": ["serve", "--profile", "nlt-linear-issues"],
                },
                "nlt-project-docs": {
                    "command": "docsmcp",
                    "args": ["serve", "--profile", "nlt-project-docs"],
                },
                "nlt-release-ship": {
                    "command": "tapps-platform",
                    "args": ["serve", "--profile", "nlt-release-ship"],
                },
            },
        )
        result = check_nlt_partial_enablement(tmp_path)
        assert result.ok is True
        assert "Intentional full bundle" in result.message

    def test_all_six_servers_passes_when_mcp_bundle_full(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        self._cursor_mcp_json(
            tmp_path,
            {
                "nlt-build": {"command": "tapps-mcp", "args": ["serve", "--profile", "nlt-build"]},
                "nlt-memory": {
                    "command": "tapps-mcp",
                    "args": ["serve", "--profile", "nlt-memory"],
                },
                "nlt-setup": {
                    "command": "tapps-mcp",
                    "args": ["serve", "--profile", "nlt-setup"],
                },
                "nlt-linear-issues": {
                    "command": "tapps-platform",
                    "args": ["serve", "--profile", "nlt-linear-issues"],
                },
                "nlt-project-docs": {
                    "command": "docsmcp",
                    "args": ["serve", "--profile", "nlt-project-docs"],
                },
                "nlt-release-ship": {
                    "command": "tapps-platform",
                    "args": ["serve", "--profile", "nlt-release-ship"],
                },
            },
        )
        (tmp_path / ".tapps-mcp.yaml").write_text("mcp_bundle: full\n", encoding="utf-8")
        result = check_nlt_partial_enablement(tmp_path)
        assert result.ok is True
        assert "Intentional full bundle" in result.message

    def test_warns_when_more_than_three_servers(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        self._cursor_mcp_json(
            tmp_path,
            {
                "nlt-build": {"command": "tapps-mcp", "args": ["serve", "--profile", "nlt-build"]},
                "nlt-setup": {
                    "command": "tapps-mcp",
                    "args": ["serve", "--profile", "nlt-setup"],
                },
                "nlt-linear-issues": {
                    "command": "tapps-platform",
                    "args": ["serve", "--profile", "nlt-linear-issues"],
                },
                "nlt-project-docs": {
                    "command": "docsmcp",
                    "args": ["serve", "--profile", "nlt-project-docs"],
                },
            },
        )
        result = check_nlt_partial_enablement(tmp_path)
        assert result.ok is False
        assert "4 nlt-* servers enabled" in result.message

    def test_warns_when_combined_eager_exceeds_twenty(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        self._cursor_mcp_json(
            tmp_path,
            {
                "nlt-build": {"command": "tapps-mcp", "args": ["serve", "--profile", "nlt-build"]},
                "nlt-setup": {
                    "command": "tapps-mcp",
                    "args": ["serve", "--profile", "nlt-setup"],
                },
                "nlt-linear-issues": {
                    "command": "tapps-platform",
                    "args": ["serve", "--profile", "nlt-linear-issues"],
                },
                "nlt-project-docs": {
                    "command": "docsmcp",
                    "args": ["serve", "--profile", "nlt-project-docs"],
                },
                "nlt-release-ship": {
                    "command": "tapps-platform",
                    "args": ["serve", "--profile", "nlt-release-ship"],
                },
            },
        )
        result = check_nlt_partial_enablement(tmp_path)
        assert result.ok is False
        assert "29 combined eager tools" in result.message
        assert "5 nlt-* servers enabled" in result.message
        assert "developer bundle" in (result.detail or "").lower()
        assert "mcp.json" in (result.detail or "")
        assert "recommended bundle" in (result.detail or "").lower()


_SAMPLE_PROBE_METRICS = """\
# HELP tapps_brain_mcp_probe_duration_seconds Probe duration
# TYPE tapps_brain_mcp_probe_duration_seconds histogram
tapps_brain_mcp_probe_duration_seconds_bucket{le="0.005"} 0
tapps_brain_mcp_probe_duration_seconds_bucket{le="0.01"} 0
tapps_brain_mcp_probe_duration_seconds_bucket{le="0.025"} 1
tapps_brain_mcp_probe_duration_seconds_bucket{le="0.05"} 3
tapps_brain_mcp_probe_duration_seconds_bucket{le="0.1"} 7
tapps_brain_mcp_probe_duration_seconds_bucket{le="0.25"} 9
tapps_brain_mcp_probe_duration_seconds_bucket{le="0.5"} 10
tapps_brain_mcp_probe_duration_seconds_bucket{le="+Inf"} 10
tapps_brain_mcp_probe_duration_seconds_sum 1.23
tapps_brain_mcp_probe_duration_seconds_count 10
"""


class TestParseHistogramQuantiles:
    """TAP-1931: Prometheus histogram_quantile parsing."""

    def test_parses_p50_p95_p99(self) -> None:
        q = _parse_histogram_quantiles(
            _SAMPLE_PROBE_METRICS,
            "tapps_brain_mcp_probe_duration_seconds",
            (0.5, 0.95, 0.99),
        )
        assert q is not None
        # Linear interpolation within the matched bucket (see issue AC).
        assert q[0.5] == pytest.approx(0.075)
        assert q[0.95] == pytest.approx(0.375)
        assert q[0.99] == pytest.approx(0.475)

    def test_missing_metric_returns_none(self) -> None:
        assert (
            _parse_histogram_quantiles("# nothing here\n", "absent_metric", (0.5,))
            is None
        )

    def test_zero_total_returns_none(self) -> None:
        body = (
            'absent_bucket{le="0.1"} 0\n'
            'tapps_brain_mcp_probe_duration_seconds_bucket{le="0.1"} 0\n'
            'tapps_brain_mcp_probe_duration_seconds_bucket{le="+Inf"} 0\n'
        )
        assert (
            _parse_histogram_quantiles(
                body, "tapps_brain_mcp_probe_duration_seconds", (0.5,)
            )
            is None
        )

    def test_aggregates_multi_series_by_le(self) -> None:
        # Two label series at the same le sum (PromQL sum by (le)).
        body = (
            'm_bucket{le="0.1",profile="coder"} 2\n'
            'm_bucket{le="0.1",profile="operator"} 3\n'
            'm_bucket{le="+Inf",profile="coder"} 2\n'
            'm_bucket{le="+Inf",profile="operator"} 3\n'
        )
        q = _parse_histogram_quantiles(body, "m", (0.5,))
        assert q is not None
        # total=5, rank=2.5 → within the le=0.1 bucket (cum 5): 0 + 0.1*2.5/5.
        assert q[0.5] == pytest.approx(0.05)


class TestCheckBrainProbeLatency:
    """TAP-1931: the doctor latency check."""

    def test_skip_when_not_http_mode(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        with patch.dict("os.environ", {}, clear=True):
            result = check_brain_probe_latency(tmp_path)
        assert result.ok is True
        assert "Not in HTTP mode" in result.message

    def test_reports_quantiles_on_success(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        resp = MagicMock()
        resp.status_code = 200
        resp.text = _SAMPLE_PROBE_METRICS
        httpx_mod = MagicMock()
        httpx_mod.get.return_value = resp
        with (
            patch.dict("os.environ", {"TAPPS_MCP_MEMORY_BRAIN_HTTP_URL": "http://brain:8080"}),
            patch("tapps_mcp.distribution.doctor.httpx", httpx_mod),
        ):
            result = check_brain_probe_latency(tmp_path)
        assert result.ok is True
        assert "mcp_probe_duration" in result.message
        assert "p50: 0.075s" in result.message
        assert "p95: 0.375s" in result.message
        assert "p99: 0.475s" in result.message

    def test_unavailable_on_connection_error(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        httpx_mod = MagicMock()
        httpx_mod.get.side_effect = RuntimeError("connection refused")
        with (
            patch.dict("os.environ", {"TAPPS_MCP_MEMORY_BRAIN_HTTP_URL": "http://brain:8080"}),
            patch("tapps_mcp.distribution.doctor.httpx", httpx_mod),
        ):
            result = check_brain_probe_latency(tmp_path)
        # Telemetry gaps must not fail the doctor run.
        assert result.ok is True
        assert "unavailable" in result.message

    def test_unavailable_on_404(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        resp = MagicMock()
        resp.status_code = 404
        httpx_mod = MagicMock()
        httpx_mod.get.return_value = resp
        with (
            patch.dict("os.environ", {"TAPPS_MCP_MEMORY_BRAIN_HTTP_URL": "http://brain:8080"}),
            patch("tapps_mcp.distribution.doctor.httpx", httpx_mod),
        ):
            result = check_brain_probe_latency(tmp_path)
        assert result.ok is True
        assert "unavailable" in result.message
        assert "404" in result.message

    def test_unavailable_when_metric_absent(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "# some other metrics\nother_metric 1\n"
        httpx_mod = MagicMock()
        httpx_mod.get.return_value = resp
        with (
            patch.dict("os.environ", {"TAPPS_MCP_MEMORY_BRAIN_HTTP_URL": "http://brain:8080"}),
            patch("tapps_mcp.distribution.doctor.httpx", httpx_mod),
        ):
            result = check_brain_probe_latency(tmp_path)
        assert result.ok is True
        assert "unavailable" in result.message


class TestCheckBrainProfileGateVsDeferral:
    """ADR-0012: a profile gap is a real gate under narrow profiles, but benign
    deferred-loading under ``full``/``operator``."""

    def _run(self, tmp_path, headers, exposed):  # type: ignore[no-untyped-def]
        from tapps_mcp.distribution.doctor import check_brain_profile

        with (
            patch.dict(
                "os.environ", {"TAPPS_MCP_MEMORY_BRAIN_HTTP_URL": "http://brain:8080"}
            ),
            patch("tapps_core.config.settings.load_settings", return_value=MagicMock()),
            patch("tapps_core.brain_auth.build_brain_headers", return_value=dict(headers)),
            patch(
                "tapps_mcp.distribution.doctor._probe_warm_cache_status",
                return_value="n/a",
            ),
            patch(
                "tapps_mcp.distribution.doctor._fetch_exposed_tools",
                return_value=(frozenset(exposed), "rest"),
            ),
        ):
            return check_brain_profile(tmp_path)

    def test_narrow_profile_gap_is_a_real_gate(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        result = self._run(tmp_path, {"X-Brain-Profile": "coder"}, {"brain_recall"})
        assert result.ok is False
        assert "GATES" in result.message
        assert "ToolNotInProfileError" in result.message
        assert "full" in (result.detail or "")

    def test_full_profile_gap_is_benign_deferral(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        result = self._run(tmp_path, {"X-Brain-Profile": "full"}, {"brain_recall"})
        assert result.ok is True
        assert "deferred" in result.message

    def test_no_profile_uses_server_default_full(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        # No X-Brain-Profile header → doctor probes with the server default
        # (``full``), so the gap is classified as benign deferral, not a gate.
        result = self._run(tmp_path, {}, {"brain_recall"})
        assert result.ok is True
        assert "deferred" in result.message
        assert "server default" in result.message


# ---------------------------------------------------------------------------
# Epic 114: call graph doctor checks
# ---------------------------------------------------------------------------


class TestCheckCallGraph:
    """Call graph tools profile and index cache doctor rows."""

    def _nlt_mcp_json(self, tmp_path: Path) -> None:
        (tmp_path / ".mcp.json").write_text(
            json.dumps(
                {"mcpServers": {"nlt-build": {"command": "nlt-build-serve.sh", "args": []}}}
            )
        )

    def test_tools_skipped_without_nlt_build(self, tmp_path: Path) -> None:
        from tapps_mcp.distribution.doctor import check_call_graph_tools_profile

        result = check_call_graph_tools_profile(tmp_path)
        assert result.ok is True
        assert "skipped" in result.message.lower()

    def test_tools_pass_when_in_profile(self, tmp_path: Path) -> None:
        from tapps_mcp.distribution.doctor import check_call_graph_tools_profile

        self._nlt_mcp_json(tmp_path)
        result = check_call_graph_tools_profile(tmp_path)
        assert result.ok is True
        assert "nlt-build" in result.message

    def test_tools_pass_despite_yaml_developer_preset(self, tmp_path: Path) -> None:
        from tapps_mcp.distribution.doctor import check_call_graph_tools_profile

        self._nlt_mcp_json(tmp_path)
        (tmp_path / ".tapps-mcp.yaml").write_text("tool_preset: developer\n")
        result = check_call_graph_tools_profile(tmp_path)
        assert result.ok is True
        assert "nlt-build" in result.message

    def test_tools_fail_when_stripped(self, tmp_path: Path) -> None:
        from tapps_mcp.distribution.doctor import check_call_graph_tools_profile

        self._nlt_mcp_json(tmp_path)
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "disabled_tools:\n  - tapps_call_graph\n  - tapps_diff_impact\n"
        )
        result = check_call_graph_tools_profile(tmp_path)
        assert result.ok is False
        assert "tapps_call_graph" in result.message

    def test_tools_fail_on_old_package_version(self, tmp_path: Path) -> None:
        from tapps_mcp.distribution.doctor import check_call_graph_tools_profile

        self._nlt_mcp_json(tmp_path)
        with patch("tapps_mcp.__version__", "3.12.29"):
            result = check_call_graph_tools_profile(tmp_path)
        assert result.ok is False
        assert "3.12.30" in result.message

    def test_index_missing_is_ok(self, tmp_path: Path) -> None:
        from tapps_mcp.distribution.doctor import check_call_graph_index_cache

        result = check_call_graph_index_cache(tmp_path)
        assert result.ok is True
        assert "No cache yet" in result.message

    def test_index_present_quick_mode(self, tmp_path: Path) -> None:
        from tapps_mcp.distribution.doctor import check_call_graph_index_cache
        from tapps_mcp.project.call_graph import build_call_graph_index

        (tmp_path / "mod.py").write_text("def f():\n    pass\n")
        build_call_graph_index(tmp_path, force_rebuild=True)
        result = check_call_graph_index_cache(tmp_path, quick=True)
        assert result.ok is True
        assert "Cache present" in result.message
        assert "fresh" in result.message


class TestMcpOperatorSecrets:
    """Doctor warns when GUI MCP cannot resolve operator secrets."""

    def _write_mcp_json(self, root: Path) -> None:
        (root / ".cursor").mkdir(parents=True, exist_ok=True)
        (root / ".cursor" / "mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "nlt-build": {
                            "env": {
                                "TAPPS_MCP_CONTEXT7_API_KEY": "${TAPPS_MCP_CONTEXT7_API_KEY}",
                                "TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN": "${TAPPS_BRAIN_AUTH_TOKEN}",
                                "TAPPS_MCP_MEMORY_BRAIN_HTTP_URL": "http://localhost:8080",
                            }
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

    def test_passes_when_operator_env_present(self, tmp_path, monkeypatch) -> None:
        from tapps_mcp.distribution.doctor import check_mcp_operator_secrets

        monkeypatch.delenv("TAPPS_MCP_CONTEXT7_API_KEY", raising=False)
        monkeypatch.delenv("TAPPS_BRAIN_AUTH_TOKEN", raising=False)
        self._write_mcp_json(tmp_path)
        operator_env = Path.home() / ".tapps-operator.env"
        backup = operator_env.read_text(encoding="utf-8") if operator_env.is_file() else None
        try:
            operator_env.write_text(
                "TAPPS_MCP_CONTEXT7_API_KEY=ctx7-test\nTAPPS_BRAIN_AUTH_TOKEN=tb-test\n",
                encoding="utf-8",
            )
            result = check_mcp_operator_secrets(tmp_path)
        finally:
            if backup is None:
                operator_env.unlink(missing_ok=True)
            else:
                operator_env.write_text(backup, encoding="utf-8")
        assert result.ok is True
        assert "operator" in result.message.lower()

    def test_fails_when_secrets_missing(self, tmp_path, monkeypatch) -> None:
        from tapps_mcp.distribution.doctor import check_mcp_operator_secrets

        monkeypatch.delenv("TAPPS_MCP_CONTEXT7_API_KEY", raising=False)
        monkeypatch.delenv("CONTEXT7_API_KEY", raising=False)
        monkeypatch.delenv("TAPPS_BRAIN_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN", raising=False)
        self._write_mcp_json(tmp_path)
        operator_env = Path.home() / ".tapps-operator.env"
        backup = operator_env.read_text(encoding="utf-8") if operator_env.is_file() else None
        try:
            operator_env.unlink(missing_ok=True)
            result = check_mcp_operator_secrets(tmp_path)
        finally:
            if backup is not None:
                operator_env.write_text(backup, encoding="utf-8")
        assert result.ok is False
        assert "TAPPS_MCP_CONTEXT7_API_KEY" in result.message
        assert "OPERATOR-SECRETS" in (result.detail or "")
