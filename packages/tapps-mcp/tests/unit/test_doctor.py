"""Tests for the tapps-mcp doctor command."""

import json
import sys
from unittest.mock import patch

from click.testing import CliRunner

from tapps_mcp.cli import main
from tapps_mcp.distribution.doctor import (
    CheckResult,
    _collect_checks,
    _read_engagement_level,
    check_agents_md,
    check_binary_on_path,
    check_claude_code_project,
    check_claude_code_user,
    check_claude_md,
    check_claude_settings,
    check_cursor_config,
    check_cursor_rules,
    check_hooks,
    check_json_config,
    check_mcp_client_config,
    check_scope_recommendation,
    check_stale_exe_backups,
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

    def test_valid_level_high(self, tmp_path):
        (tmp_path / ".tapps-mcp.yaml").write_text("llm_engagement_level: high\n")
        assert _read_engagement_level(tmp_path) == "high"

    def test_valid_level_medium(self, tmp_path):
        (tmp_path / ".tapps-mcp.yaml").write_text("llm_engagement_level: medium\n")
        assert _read_engagement_level(tmp_path) == "medium"

    def test_valid_level_low(self, tmp_path):
        (tmp_path / ".tapps-mcp.yaml").write_text("llm_engagement_level: low\n")
        assert _read_engagement_level(tmp_path) == "low"

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
        assert "tapps-mcp not in" in result.message

    def test_wrong_command(self, tmp_path):
        config = {"mcpServers": {"tapps-mcp": {"command": "wrong"}}}
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        result = check_json_config(path, "mcpServers", "Test")
        assert result.ok is False
        assert "Unexpected command" in result.message

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
        (settings_dir / "settings.json").write_text(
            json.dumps(config, indent=2), encoding="utf-8"
        )
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
        (settings_dir / "settings.json").write_text(
            json.dumps(config, indent=2), encoding="utf-8"
        )
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
        (settings_dir / "settings.json").write_text(
            json.dumps(config, indent=2), encoding="utf-8"
        )
        result = check_claude_settings(tmp_path)
        assert result.ok is True

    def test_settings_missing_bare_entry(self, tmp_path):
        """Settings with only wildcard (no bare entry) fails."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        config = {"permissions": {"allow": ["mcp__tapps-mcp__*"]}}
        (settings_dir / "settings.json").write_text(
            json.dumps(config, indent=2), encoding="utf-8"
        )
        result = check_claude_settings(tmp_path)
        assert result.ok is False
        assert "mcp__tapps-mcp" in result.message

    def test_settings_with_unsupported_hook_key_fails(self, tmp_path):
        """Unsupported hook keys (e.g. PostCompact) cause check to fail."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        config = {
            "permissions": {"allow": ["mcp__tapps-mcp", "mcp__tapps-mcp__*"]},
            "hooks": {"PostCompact": [{"matcher": "*", "hooks": [{"type": "command", "command": "true"}]}]},
        }
        (settings_dir / "settings.json").write_text(
            json.dumps(config, indent=2), encoding="utf-8"
        )
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
        """Cursor hooks directory with before-mcp hook and valid hooks.json passes."""
        hooks_dir = tmp_path / ".cursor" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "tapps-before-mcp.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        (hooks_dir / "tapps-after-edit.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        (tmp_path / ".cursor" / "hooks.json").write_text(
            json.dumps({
                "version": 1,
                "hooks": {
                    "beforeMCPExecution": [{"command": ".cursor/hooks/tapps-before-mcp.sh"}],
                    "afterFileEdit": [{"command": ".cursor/hooks/tapps-after-edit.sh"}],
                },
            }, indent=2),
            encoding="utf-8",
        )
        result = check_hooks(tmp_path)
        assert result.ok is True
        assert "Cursor" in result.message

    def test_both_hooks_present(self, tmp_path):
        """Both Claude and Cursor hooks with session-start hooks and valid config passes."""
        claude_hooks = tmp_path / ".claude" / "hooks"
        claude_hooks.mkdir(parents=True)
        (claude_hooks / "tapps-session-start.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        cursor_hooks = tmp_path / ".cursor" / "hooks"
        cursor_hooks.mkdir(parents=True)
        (cursor_hooks / "tapps-before-mcp.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        (tmp_path / ".cursor" / "hooks.json").write_text(
            json.dumps({
                "version": 1,
                "hooks": {
                    "beforeMCPExecution": [{"command": ".cursor/hooks/tapps-before-mcp.sh"}],
                    "afterFileEdit": [{"command": ".cursor/hooks/tapps-after-edit.sh"}],
                },
            }, indent=2),
            encoding="utf-8",
        )
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

    def test_cursor_hooks_json_unsupported_key_fails(self, tmp_path):
        """Cursor hooks.json with unsupported hook key fails check."""
        hooks_dir = tmp_path / ".cursor" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "tapps-before-mcp.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        (hooks_dir / "tapps-after-edit.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        (tmp_path / ".cursor" / "hooks.json").write_text(
            json.dumps({
                "version": 1,
                "hooks": {
                    "beforeMCPExecution": [{"command": ".cursor/hooks/tapps-before-mcp.sh"}],
                    "postCompact": [{"command": "echo x"}],
                },
            }, indent=2),
            encoding="utf-8",
        )
        result = check_hooks(tmp_path)
        assert result.ok is False
        assert "postCompact" in result.message or "unsupported" in result.message.lower()


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
        skip_check = [c for c in checks if c.name == "Quality tools"][0]
        assert skip_check.ok is True
        assert "quick mode" in skip_check.message.lower()

    def test_collect_checks_full_includes_quality_tools(self, tmp_path):
        """Full mode (default) includes quality tool checks."""
        with patch(
            "tapps_mcp.tools.tool_detection.detect_installed_tools", return_value=[]
        ):
            checks = _collect_checks(tmp_path, quick=False)
        names = [c.name for c in checks]
        # Should NOT contain the skip placeholder
        assert "Quality tools" not in names

    def test_run_doctor_structured_quick(self, tmp_path):
        """run_doctor_structured with quick=True includes quick_mode flag."""
        with patch(
            "tapps_mcp.distribution.doctor._collect_checks"
        ) as mock_collect, patch(
            "tapps_mcp.distribution.doctor._collect_docker_checks_sync",
            return_value=[],
        ):
            mock_collect.return_value = [CheckResult("test", True, "ok")]
            result = run_doctor_structured(
                project_root=str(tmp_path), quick=True
            )
        assert result["quick_mode"] is True
        mock_collect.assert_called_once_with(tmp_path.resolve(), quick=True)

    def test_run_doctor_structured_default_not_quick(self, tmp_path):
        """run_doctor_structured defaults to quick_mode=False."""
        with patch(
            "tapps_mcp.distribution.doctor._collect_checks"
        ) as mock_collect, patch(
            "tapps_mcp.distribution.doctor._collect_docker_checks_sync",
            return_value=[],
        ):
            mock_collect.return_value = [CheckResult("test", True, "ok")]
            result = run_doctor_structured(project_root=str(tmp_path))
        assert result["quick_mode"] is False

    def test_cli_doctor_quick_flag(self):
        """CLI doctor --quick flag works."""
        runner = CliRunner()
        with patch(
            "tapps_mcp.distribution.doctor.run_doctor", return_value=True
        ) as mock_run:
            result = runner.invoke(main, ["doctor", "--quick"])
        assert result.exit_code == 0
        mock_run.assert_called_once_with(project_root=".", quick=True)

    def test_cli_doctor_without_quick(self):
        """CLI doctor without --quick defaults to quick=False."""
        runner = CliRunner()
        with patch(
            "tapps_mcp.distribution.doctor.run_doctor", return_value=True
        ) as mock_run:
            result = runner.invoke(main, ["doctor"])
        assert result.exit_code == 0
        mock_run.assert_called_once_with(project_root=".", quick=False)
