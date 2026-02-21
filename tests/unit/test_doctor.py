"""Tests for the tapps-mcp doctor command."""

import json
from unittest.mock import patch

from click.testing import CliRunner

from tapps_mcp.cli import main
from tapps_mcp.distribution.doctor import (
    CheckResult,
    check_binary_on_path,
    check_claude_code_project,
    check_claude_code_user,
    check_claude_md,
    check_cursor_config,
    check_cursor_rules,
    check_json_config,
    check_vscode_config,
    run_doctor,
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
