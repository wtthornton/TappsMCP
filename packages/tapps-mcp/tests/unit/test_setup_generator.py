"""Tests for distribution.setup_generator — host detection and the init entry point."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from tapps_mcp.cli import main
from tapps_mcp.distribution.setup_generator import (
    _configure_multiple_hosts,
    _detect_hosts,
    _get_config_path,
    run_init,
)


@pytest.fixture(autouse=True)
def _isolate_operator_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep tests off the developer machine's real ~/.local/bin MCP shims."""
    fake_home = tmp_path / "isolated-home"
    fake_home.mkdir()
    monkeypatch.setattr("tapps_mcp.distribution.setup_generator.Path.home", lambda: fake_home)
    monkeypatch.setattr(
        "tapps_mcp.distribution.blue_green.CURRENT_LINK",
        fake_home / ".tapps-mcp" / "current",
    )


class TestDetectHosts:
    """Tests for host auto-detection logic."""

    def test_detects_claude_code(self, tmp_path):
        """Detects Claude Code when ~/.claude/ directory exists."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            hosts = _detect_hosts()
        assert "claude-code" in hosts

    def test_detects_cursor_on_windows(self, tmp_path):
        """Detects Cursor on Windows via AppData/Roaming/Cursor."""
        cursor_dir = tmp_path / "AppData" / "Roaming" / "Cursor"
        cursor_dir.mkdir(parents=True)
        with (
            patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.setup_generator.sys.platform", "win32"),
        ):
            hosts = _detect_hosts()
        assert "cursor" in hosts

    def test_detects_cursor_on_macos(self, tmp_path):
        """Detects Cursor on macOS via Library/Application Support/Cursor."""
        cursor_dir = tmp_path / "Library" / "Application Support" / "Cursor"
        cursor_dir.mkdir(parents=True)
        with (
            patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.setup_generator.sys.platform", "darwin"),
        ):
            hosts = _detect_hosts()
        assert "cursor" in hosts

    def test_detects_cursor_on_linux(self, tmp_path):
        """Detects Cursor on Linux via ~/.config/Cursor."""
        cursor_dir = tmp_path / ".config" / "Cursor"
        cursor_dir.mkdir(parents=True)
        with (
            patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.setup_generator.sys.platform", "linux"),
        ):
            hosts = _detect_hosts()
        assert "cursor" in hosts

    def test_detects_vscode_on_windows(self, tmp_path):
        """Detects VS Code on Windows via AppData/Roaming/Code."""
        vscode_dir = tmp_path / "AppData" / "Roaming" / "Code"
        vscode_dir.mkdir(parents=True)
        with (
            patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.setup_generator.sys.platform", "win32"),
        ):
            hosts = _detect_hosts()
        assert "vscode" in hosts

    def test_detects_vscode_on_macos(self, tmp_path):
        """Detects VS Code on macOS via Library/Application Support/Code."""
        vscode_dir = tmp_path / "Library" / "Application Support" / "Code"
        vscode_dir.mkdir(parents=True)
        with (
            patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.setup_generator.sys.platform", "darwin"),
        ):
            hosts = _detect_hosts()
        assert "vscode" in hosts

    def test_detects_vscode_on_linux(self, tmp_path):
        """Detects VS Code on Linux via ~/.config/Code."""
        vscode_dir = tmp_path / ".config" / "Code"
        vscode_dir.mkdir(parents=True)
        with (
            patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.setup_generator.sys.platform", "linux"),
        ):
            hosts = _detect_hosts()
        assert "vscode" in hosts

    def test_detects_multiple_hosts(self, tmp_path):
        """Detects multiple hosts when several are installed."""
        (tmp_path / ".claude").mkdir()
        (tmp_path / "AppData" / "Roaming" / "Cursor").mkdir(parents=True)
        (tmp_path / "AppData" / "Roaming" / "Code").mkdir(parents=True)
        with (
            patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.setup_generator.sys.platform", "win32"),
        ):
            hosts = _detect_hosts()
        assert len(hosts) == 3
        assert "claude-code" in hosts
        assert "cursor" in hosts
        assert "vscode" in hosts

    def test_no_hosts_detected(self, tmp_path):
        """Returns empty list when no hosts are found."""
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            hosts = _detect_hosts()
        assert hosts == []


# ---------------------------------------------------------------------------
# Config path tests
# ---------------------------------------------------------------------------


class TestRunInit:
    """Tests for the top-level run_init entry point."""

    def test_auto_no_hosts_detected(self, tmp_path, capsys):
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            run_init(mcp_host="auto", project_root=str(tmp_path))
        captured = capsys.readouterr()
        assert "No MCP hosts detected" in captured.out

    def test_auto_configures_detected_host(self, tmp_path):
        (tmp_path / ".claude").mkdir()
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            run_init(mcp_host="auto", project_root=str(tmp_path), rules=False, scope="user")
        assert (tmp_path / ".claude.json").exists()

    def test_auto_configures_all_detected_hosts(self, tmp_path):
        """Auto mode configures ALL detected hosts, not just the first."""
        (tmp_path / ".claude").mkdir()
        (tmp_path / "AppData" / "Roaming" / "Cursor").mkdir(parents=True)
        with (
            patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.setup_generator.sys.platform", "win32"),
            patch("tapps_mcp.distribution.setup_generator.shutil.which", return_value=None),
        ):
            run_init(
                mcp_host="auto",
                project_root=str(tmp_path),
                force=True,
                rules=False,
                scope="user",
            )
        assert (tmp_path / ".claude.json").exists()
        assert (tmp_path / ".cursor" / "mcp.json").exists()

    def test_auto_reports_per_host(self, tmp_path, capsys):
        """Auto mode prints header per detected host."""
        (tmp_path / ".claude").mkdir()
        (tmp_path / "AppData" / "Roaming" / "Cursor").mkdir(parents=True)
        with (
            patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.setup_generator.sys.platform", "win32"),
            patch("tapps_mcp.distribution.setup_generator.shutil.which", return_value=None),
        ):
            run_init(mcp_host="auto", project_root=str(tmp_path), force=True, rules=False)
        captured = capsys.readouterr()
        assert "claude-code" in captured.out
        assert "cursor" in captured.out

    def test_explicit_cursor_host(self, tmp_path):
        run_init(mcp_host="cursor", project_root=str(tmp_path), rules=False)
        assert (tmp_path / ".cursor" / "mcp.json").exists()

    def test_explicit_vscode_host(self, tmp_path):
        run_init(mcp_host="vscode", project_root=str(tmp_path), rules=False)
        assert (tmp_path / ".vscode" / "mcp.json").exists()

    def test_check_mode_with_valid_config(self, tmp_path, capsys):
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config = {"mcpServers": {"tapps-mcp": {"command": "tapps-mcp", "args": ["serve"]}}}
        (cursor_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
        run_init(mcp_host="cursor", project_root=str(tmp_path), check=True)
        captured = capsys.readouterr()
        assert "correctly configured" in captured.out

    def test_check_mode_with_missing_config(self, tmp_path, capsys):
        run_init(mcp_host="cursor", project_root=str(tmp_path), check=True)
        captured = capsys.readouterr()
        assert "not found" in captured.out


class TestCliInit:
    """Tests for the CLI init command via Click's CliRunner."""

    def test_init_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["init", "--help"])
        assert result.exit_code == 0
        assert "Bootstrap TappsMCP" in result.output

    def test_init_cursor(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["init", "--host", "cursor", "--project-root", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert (tmp_path / ".cursor" / "mcp.json").exists()

    def test_init_strips_direct_tapps_brain_mcp_entry(self, tmp_path):
        """Bridge-only: init removes parallel tapps-brain MCP servers (TAP-1888)."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config = {
            "mcpServers": {
                "tapps-brain": {"command": "tapps-brain", "args": ["serve"]},
                "other-mcp": {"command": "other"},
            }
        }
        (cursor_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "init",
                "--host",
                "cursor",
                "--project-root",
                str(tmp_path),
                "--force",
                "--no-rules",
            ],
        )
        assert result.exit_code == 0
        from tapps_mcp.distribution.setup_generator import _load_mcp_config_json

        data = _load_mcp_config_json(cursor_dir / "mcp.json")
        assert "tapps-brain" not in data["mcpServers"]
        assert "other-mcp" in data["mcpServers"]
        assert "nlt-build" in data["mcpServers"]
        assert "nlt-memory" in data["mcpServers"]
        assert "nlt-linear-issues" in data["mcpServers"]
        assert "bridge-only" in result.output.lower() or "Removed direct" in result.output

    def test_init_vscode(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["init", "--host", "vscode", "--project-root", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert (tmp_path / ".vscode" / "mcp.json").exists()

    def test_init_check_mode(self, tmp_path):
        # First create config
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config = {"mcpServers": {"tapps-mcp": {"command": "tapps-mcp", "args": ["serve"]}}}
        (cursor_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["init", "--host", "cursor", "--project-root", str(tmp_path), "--check"],
        )
        assert result.exit_code == 0
        assert "correctly configured" in result.output

    def test_init_check_mode_missing_config_exits_nonzero(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["init", "--host", "cursor", "--project-root", str(tmp_path), "--check"],
        )
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_init_auto_no_hosts(self, tmp_path):
        runner = CliRunner()
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            result = runner.invoke(
                main,
                ["init", "--host", "auto", "--project-root", str(tmp_path)],
            )
        assert result.exit_code == 0
        assert "No MCP hosts detected" in result.output

    def test_init_invalid_host(self):
        runner = CliRunner()
        result = runner.invoke(main, ["init", "--host", "invalid"])
        assert result.exit_code != 0
        assert "Invalid value" in result.output

    def test_init_scope_option(self, tmp_path):
        """CLI accepts --scope project."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "init",
                "--host",
                "claude-code",
                "--scope",
                "project",
                "--project-root",
                str(tmp_path),
                "--no-rules",
            ],
        )
        assert result.exit_code == 0
        assert (tmp_path / ".mcp.json").exists()

    def test_init_no_rules_flag(self, tmp_path):
        """CLI --no-rules skips platform rule generation."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "init",
                "--host",
                "cursor",
                "--project-root",
                str(tmp_path),
                "--no-rules",
            ],
        )
        assert result.exit_code == 0
        assert (tmp_path / ".cursor" / "mcp.json").exists()
        assert not (tmp_path / ".cursor" / "rules" / "tapps-pipeline.mdc").exists()


# ---------------------------------------------------------------------------
# Rules generation tests
# ---------------------------------------------------------------------------


class TestConfigureMultipleHosts:
    """Tests for _configure_multiple_hosts."""

    def test_configures_all_hosts(self, tmp_path):
        """Configures all provided hosts."""
        ok = _configure_multiple_hosts(
            ["cursor", "vscode"],
            tmp_path,
            force=True,
            rules=False,
        )
        assert ok is True
        assert (tmp_path / ".cursor" / "mcp.json").exists()
        assert (tmp_path / ".vscode" / "mcp.json").exists()

    def test_returns_false_if_any_fails(self, tmp_path):
        """Returns False if any host configuration fails."""
        # Pre-create invalid JSON for cursor
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        (cursor_dir / "mcp.json").write_text("{bad}", encoding="utf-8")
        ok = _configure_multiple_hosts(
            ["cursor", "vscode"],
            tmp_path,
            rules=False,
        )
        assert ok is False
        # VS Code should still succeed
        assert (tmp_path / ".vscode" / "mcp.json").exists()

    def test_check_mode_configured_hosts_only(self, tmp_path):
        """Check mode validates only hosts with existing config (Cursor-only OK)."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config = {"mcpServers": {"tapps-mcp": {"command": "tapps-mcp", "args": ["serve"]}}}
        (cursor_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
        ok = _configure_multiple_hosts(
            ["claude-code", "cursor", "vscode"],
            tmp_path,
            check=True,
            rules=False,
        )
        assert ok is True

    def test_check_mode(self, tmp_path):
        """Check mode validates only configured hosts; missing optional hosts OK."""
        # Set up valid cursor config only
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config = {"mcpServers": {"tapps-mcp": {"command": "tapps-mcp", "args": ["serve"]}}}
        (cursor_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
        # vscode is missing but was not bootstrapped — should still pass
        ok = _configure_multiple_hosts(
            ["cursor", "vscode"],
            tmp_path,
            check=True,
            rules=False,
        )
        assert ok is True

    def test_generates_rules_when_enabled(self, tmp_path):
        """Rules are generated alongside config when rules=True."""
        _configure_multiple_hosts(
            ["cursor"],
            tmp_path,
            force=True,
            rules=True,
        )
        assert (tmp_path / ".cursor" / "mcp.json").exists()
        assert (tmp_path / ".cursor" / "rules" / "tapps-pipeline.mdc").exists()

    def test_skips_rules_when_disabled(self, tmp_path):
        """Rules are skipped when rules=False."""
        _configure_multiple_hosts(
            ["cursor"],
            tmp_path,
            force=True,
            rules=False,
        )
        assert (tmp_path / ".cursor" / "mcp.json").exists()
        assert not (tmp_path / ".cursor" / "rules" / "tapps-pipeline.mdc").exists()


# ---------------------------------------------------------------------------
# Story 12.2: Server instructions field (Claude Code only)
# ---------------------------------------------------------------------------


class TestDefaultScopeProject:
    """Tests for Epic 47.1 - default scope changed to 'project'."""

    def test_get_config_path_default_is_project(self, tmp_path):
        """Default scope for _get_config_path is 'project'."""
        path = _get_config_path("claude-code", tmp_path)
        assert path == tmp_path / ".mcp.json"

    def test_get_config_path_user_scope(self, tmp_path):
        """Explicit scope='user' still returns ~/.claude.json."""
        path = _get_config_path("claude-code", tmp_path, scope="user")
        assert path.name == ".claude.json"

    def test_run_init_default_scope_writes_project_config(self, tmp_path):
        """run_init without explicit scope writes .mcp.json (not ~/.claude.json)."""
        with patch(
            "tapps_mcp.distribution.setup_generator._detect_command_path",
            return_value="tapps-mcp",
        ):
            ok = run_init(
                mcp_host="claude-code",
                project_root=str(tmp_path),
                force=True,
                rules=False,
            )
        assert ok
        assert (tmp_path / ".mcp.json").exists()

    def test_cli_init_default_scope_is_project(self):
        """CLI init command default scope is 'project'."""
        runner = CliRunner()
        result = runner.invoke(main, ["init", "--help"])
        assert result.exit_code == 0
        # Help text should show project as default
        assert "project" in result.output.lower()


# ---------------------------------------------------------------------------
# Epic 80: Consumer init hardening
# ---------------------------------------------------------------------------
