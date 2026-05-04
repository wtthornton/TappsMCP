"""Tests for distribution.setup_generator (Story 6.2 - One-Command Setup)."""

import json
import os
import sys
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from tapps_mcp.cli import main
from tapps_mcp.distribution.setup_generator import (
    _build_uv_run_tapps_launch,
    _check_config,
    _collect_plaintext_secrets,
    _configure_multiple_hosts,
    _detect_hosts,
    _detect_uv_context,
    _ensure_gitignore_entry,
    _generate_config,
    _generate_rules,
    _get_config_path,
    _get_servers_key,
    _load_existing_env_from_other_scope,
    _looks_like_secret_key,
    _merge_config,
    _should_use_uv_launch,
    _value_is_plaintext_secret,
    is_tapps_mcp_package_layout,
    run_init,
    run_upgrade,
)

# ---------------------------------------------------------------------------
# Auto-detection tests
# ---------------------------------------------------------------------------


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


class TestGetConfigPath:
    """Tests for config path resolution."""

    def test_claude_code_path(self, tmp_path):
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            path = _get_config_path("claude-code", tmp_path / "project", scope="user")
        assert path == tmp_path / ".claude.json"

    def test_cursor_path(self, tmp_path):
        project = tmp_path / "project"
        path = _get_config_path("cursor", project)
        assert path == project / ".cursor" / "mcp.json"

    def test_vscode_path(self, tmp_path):
        project = tmp_path / "project"
        path = _get_config_path("vscode", project)
        assert path == project / ".vscode" / "mcp.json"

    def test_claude_code_project_scope(self, tmp_path):
        """Project scope returns .mcp.json in project root."""
        project = tmp_path / "project"
        path = _get_config_path("claude-code", project, scope="project")
        assert path == project / ".mcp.json"

    def test_claude_code_project_scope_is_default(self, tmp_path):
        """Default scope is project, returning .mcp.json in project root."""
        project = tmp_path / "project"
        path = _get_config_path("claude-code", project)
        assert path == project / ".mcp.json"

    def test_cursor_scope_ignored(self, tmp_path):
        """Cursor always uses project-local path regardless of scope."""
        project = tmp_path / "project"
        path_user = _get_config_path("cursor", project, scope="user")
        path_project = _get_config_path("cursor", project, scope="project")
        assert path_user == path_project == project / ".cursor" / "mcp.json"

    def test_unknown_host_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Unknown host"):
            _get_config_path("unknown", tmp_path)


# ---------------------------------------------------------------------------
# Servers key tests
# ---------------------------------------------------------------------------


class TestGetServersKey:
    """Tests for server key mapping."""

    def test_claude_code_uses_mcp_servers(self):
        assert _get_servers_key("claude-code") == "mcpServers"

    def test_cursor_uses_mcp_servers(self):
        assert _get_servers_key("cursor") == "mcpServers"

    def test_vscode_uses_servers(self):
        assert _get_servers_key("vscode") == "servers"


# ---------------------------------------------------------------------------
# Config merging tests
# ---------------------------------------------------------------------------


class TestMergeConfig:
    """Tests for merging tapps-mcp into existing configs."""

    def test_merge_into_empty(self):
        result = _merge_config({}, "cursor")
        assert "mcpServers" in result
        assert "tapps-mcp" in result["mcpServers"]
        assert result["mcpServers"]["tapps-mcp"]["command"] == "tapps-mcp"

    def test_merge_preserves_existing_servers(self):
        existing = {
            "mcpServers": {
                "other-server": {"command": "other", "args": []},
            },
        }
        result = _merge_config(existing, "cursor")
        assert "other-server" in result["mcpServers"]
        assert "tapps-mcp" in result["mcpServers"]

    def test_merge_preserves_other_top_level_keys(self):
        existing = {
            "mcpServers": {},
            "someOtherKey": "value",
        }
        result = _merge_config(existing, "cursor")
        assert result["someOtherKey"] == "value"

    def test_merge_overwrites_existing_tapps_entry(self):
        existing = {
            "mcpServers": {
                "tapps-mcp": {"command": "old-command", "args": ["old"]},
            },
        }
        result = _merge_config(existing, "cursor")
        assert result["mcpServers"]["tapps-mcp"]["command"] == "tapps-mcp"
        assert result["mcpServers"]["tapps-mcp"]["args"] == ["serve"]

    def test_merge_vscode_uses_servers_key(self):
        existing = {"servers": {"other": {"command": "x"}}}
        result = _merge_config(existing, "vscode")
        assert "servers" in result
        assert "tapps-mcp" in result["servers"]
        assert "other" in result["servers"]


# ---------------------------------------------------------------------------
# Config generation tests
# ---------------------------------------------------------------------------


class TestGenerateConfig:
    """Tests for config file generation."""

    def test_generates_cursor_config(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        _generate_config("cursor", project)
        config_path = project / ".cursor" / "mcp.json"
        assert config_path.exists()
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["mcpServers"]["tapps-mcp"]["command"] == "tapps-mcp"
        assert data["mcpServers"]["tapps-mcp"]["args"] == ["serve"]

    def test_generates_vscode_config(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        _generate_config("vscode", project)
        config_path = project / ".vscode" / "mcp.json"
        assert config_path.exists()
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["servers"]["tapps-mcp"]["command"] == "tapps-mcp"

    def test_generates_claude_code_config(self, tmp_path):
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            _generate_config("claude-code", tmp_path / "project", scope="user")
        config_path = tmp_path / ".claude.json"
        assert config_path.exists()
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["mcpServers"]["tapps-mcp"]["command"] == "tapps-mcp"

    def test_creates_parent_directories(self, tmp_path):
        project = tmp_path / "deep" / "nested" / "project"
        # .cursor dir doesn't exist yet
        _generate_config("cursor", project)
        assert (project / ".cursor" / "mcp.json").exists()

    def test_merges_with_existing_file(self, tmp_path):
        project = tmp_path / "project"
        cursor_dir = project / ".cursor"
        cursor_dir.mkdir(parents=True)
        existing = {"mcpServers": {"other": {"command": "x"}}, "extra": True}
        (cursor_dir / "mcp.json").write_text(json.dumps(existing), encoding="utf-8")
        _generate_config("cursor", project)
        data = json.loads((cursor_dir / "mcp.json").read_text(encoding="utf-8"))
        # Should preserve existing entries
        assert "other" in data["mcpServers"]
        assert "tapps-mcp" in data["mcpServers"]
        assert data["extra"] is True

    def test_prompts_before_overwriting_existing_entry(self, tmp_path):
        """When tapps-mcp already exists, confirms before overwriting."""
        project = tmp_path / "project"
        cursor_dir = project / ".cursor"
        cursor_dir.mkdir(parents=True)
        existing = {"mcpServers": {"tapps-mcp": {"command": "old"}}}
        (cursor_dir / "mcp.json").write_text(json.dumps(existing), encoding="utf-8")

        # Simulate user saying "no"
        with (
            patch.object(sys.stdin, "isatty", return_value=True),
            patch("tapps_mcp.distribution.setup_generator.click.confirm", return_value=False),
        ):
            _generate_config("cursor", project)
        # Should NOT have overwritten
        data = json.loads((cursor_dir / "mcp.json").read_text(encoding="utf-8"))
        assert data["mcpServers"]["tapps-mcp"]["command"] == "old"

    def test_overwrites_existing_entry_when_confirmed(self, tmp_path):
        """When tapps-mcp already exists and user confirms, overwrites."""
        project = tmp_path / "project"
        cursor_dir = project / ".cursor"
        cursor_dir.mkdir(parents=True)
        existing = {"mcpServers": {"tapps-mcp": {"command": "old"}}}
        (cursor_dir / "mcp.json").write_text(json.dumps(existing), encoding="utf-8")

        with (
            patch.object(sys.stdin, "isatty", return_value=True),
            patch("tapps_mcp.distribution.setup_generator.click.confirm", return_value=True),
            patch(
                "tapps_mcp.distribution.setup_generator.shutil.which", return_value="/bin/tapps-mcp"
            ),
        ):
            _generate_config("cursor", project)
        data = json.loads((cursor_dir / "mcp.json").read_text(encoding="utf-8"))
        assert data["mcpServers"]["tapps-mcp"]["command"] == "tapps-mcp"

    def test_handles_invalid_json_in_existing_file(self, tmp_path):
        """Does not overwrite when existing file has invalid JSON."""
        project = tmp_path / "project"
        cursor_dir = project / ".cursor"
        cursor_dir.mkdir(parents=True)
        (cursor_dir / "mcp.json").write_text("not valid json {{{", encoding="utf-8")

        ok = _generate_config("cursor", project)
        # Should report failure and leave file untouched so the user can fix it
        assert ok is False
        assert (cursor_dir / "mcp.json.bak").exists() is False
        assert (cursor_dir / "mcp.json").read_text(encoding="utf-8") == "not valid json {{{"

    def test_handles_empty_existing_file(self, tmp_path):
        """Treats empty file as empty config."""
        project = tmp_path / "project"
        cursor_dir = project / ".cursor"
        cursor_dir.mkdir(parents=True)
        (cursor_dir / "mcp.json").write_text("", encoding="utf-8")

        _generate_config("cursor", project)

        data = json.loads((cursor_dir / "mcp.json").read_text(encoding="utf-8"))
        assert "tapps-mcp" in data["mcpServers"]

    def test_config_ends_with_newline(self, tmp_path):
        """Generated config file should end with a newline."""
        project = tmp_path / "project"
        project.mkdir()
        _generate_config("cursor", project)
        raw = (project / ".cursor" / "mcp.json").read_text(encoding="utf-8")
        assert raw.endswith("\n")

    def test_claude_code_project_scope_writes_mcp_json(self, tmp_path):
        """Project scope writes .mcp.json in project root."""
        project = tmp_path / "project"
        project.mkdir()
        _generate_config("claude-code", project, scope="project")
        config_path = project / ".mcp.json"
        assert config_path.exists()
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["mcpServers"]["tapps-mcp"]["command"] == "tapps-mcp"

    def test_claude_code_project_scope_merges_existing(self, tmp_path):
        """Project scope merges with existing .mcp.json."""
        project = tmp_path / "project"
        project.mkdir()
        existing = {"mcpServers": {"other": {"command": "other"}}}
        (project / ".mcp.json").write_text(json.dumps(existing), encoding="utf-8")
        _generate_config("claude-code", project, scope="project", force=True)
        data = json.loads((project / ".mcp.json").read_text(encoding="utf-8"))
        assert "other" in data["mcpServers"]
        assert "tapps-mcp" in data["mcpServers"]


# ---------------------------------------------------------------------------
# Check mode tests
# ---------------------------------------------------------------------------


class TestCheckConfig:
    """Tests for --check mode verification."""

    def test_check_valid_config(self, tmp_path):
        project = tmp_path / "project"
        cursor_dir = project / ".cursor"
        cursor_dir.mkdir(parents=True)
        config = {"mcpServers": {"tapps-mcp": {"command": "tapps-mcp", "args": ["serve"]}}}
        (cursor_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
        assert _check_config("cursor", project) is True

    def test_check_missing_file(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        assert _check_config("cursor", project) is False

    def test_check_invalid_json(self, tmp_path):
        project = tmp_path / "project"
        cursor_dir = project / ".cursor"
        cursor_dir.mkdir(parents=True)
        (cursor_dir / "mcp.json").write_text("{bad json}", encoding="utf-8")
        assert _check_config("cursor", project) is False

    def test_check_missing_tapps_entry(self, tmp_path):
        project = tmp_path / "project"
        cursor_dir = project / ".cursor"
        cursor_dir.mkdir(parents=True)
        config = {"mcpServers": {"other": {"command": "other"}}}
        (cursor_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
        assert _check_config("cursor", project) is False

    def test_check_wrong_command(self, tmp_path):
        project = tmp_path / "project"
        cursor_dir = project / ".cursor"
        cursor_dir.mkdir(parents=True)
        config = {"mcpServers": {"tapps-mcp": {"command": "wrong-command"}}}
        (cursor_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
        assert _check_config("cursor", project) is False

    def test_check_vscode_config(self, tmp_path):
        project = tmp_path / "project"
        vscode_dir = project / ".vscode"
        vscode_dir.mkdir(parents=True)
        config = {"servers": {"tapps-mcp": {"command": "tapps-mcp", "args": ["serve"]}}}
        (vscode_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
        assert _check_config("vscode", project) is True

    def test_check_missing_servers_key(self, tmp_path):
        """Config exists but has no mcpServers/servers key."""
        project = tmp_path / "project"
        cursor_dir = project / ".cursor"
        cursor_dir.mkdir(parents=True)
        config = {"someOtherKey": "value"}
        (cursor_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
        assert _check_config("cursor", project) is False

    def test_check_claude_code_config(self, tmp_path):
        config = {"mcpServers": {"tapps-mcp": {"command": "tapps-mcp", "args": ["serve"]}}}
        (tmp_path / ".claude.json").write_text(json.dumps(config), encoding="utf-8")
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            assert _check_config("claude-code", tmp_path / "project", scope="user") is True

    def test_check_claude_code_project_scope(self, tmp_path):
        """Project-scope check looks at .mcp.json."""
        project = tmp_path / "project"
        project.mkdir()
        config = {"mcpServers": {"tapps-mcp": {"command": "tapps-mcp", "args": ["serve"]}}}
        (project / ".mcp.json").write_text(json.dumps(config), encoding="utf-8")
        assert _check_config("claude-code", project, scope="project") is True

    def test_check_claude_code_project_scope_missing(self, tmp_path):
        """Project-scope check fails when .mcp.json is absent."""
        project = tmp_path / "project"
        project.mkdir()
        assert _check_config("claude-code", project, scope="project") is False


# ---------------------------------------------------------------------------
# run_init integration tests
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


# ---------------------------------------------------------------------------
# CLI integration tests (Click CliRunner)
# ---------------------------------------------------------------------------


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
        assert not (tmp_path / ".cursor" / "rules" / "tapps-pipeline.md").exists()


# ---------------------------------------------------------------------------
# Rules generation tests
# ---------------------------------------------------------------------------


class TestGenerateRules:
    """Tests for platform rule file generation via _generate_rules."""

    def test_generates_claude_md(self, tmp_path):
        """Generates CLAUDE.md for claude-code host."""
        _generate_rules("claude-code", tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        assert claude_md.exists()
        content = claude_md.read_text(encoding="utf-8")
        assert "TAPPS" in content

    def test_generates_cursor_rules(self, tmp_path):
        """Generates .cursor/rules/tapps-pipeline.md for cursor host."""
        _generate_rules("cursor", tmp_path)
        rules = tmp_path / ".cursor" / "rules" / "tapps-pipeline.md"
        assert rules.exists()
        content = rules.read_text(encoding="utf-8")
        assert "TAPPS" in content

    def test_vscode_is_noop(self, tmp_path):
        """VS Code has no platform rules; _generate_rules is a no-op."""
        _generate_rules("vscode", tmp_path)
        assert not (tmp_path / "CLAUDE.md").exists()

    def test_existing_claude_md_gets_obligations_block_appended(self, tmp_path):
        """An existing user-authored CLAUDE.md is preserved; the marker-wrapped
        TAPPS obligations block is appended (TAP-970). User content remains
        unchanged at the top; the block lives at the bottom and can be
        refreshed by tapps_upgrade without disturbing the user's prose.
        """
        original = "# Rules\nUse TAPPS pipeline.\n"
        (tmp_path / "CLAUDE.md").write_text(original)
        _generate_rules("claude-code", tmp_path)
        content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        # User-authored prose preserved verbatim at top.
        assert content.startswith(original)
        # Marker-wrapped obligations block appended (TAP-970).
        assert "<!-- BEGIN: tapps-obligations" in content
        assert "<!-- END: tapps-obligations -->" in content

    def test_skips_existing_cursor_rules(self, tmp_path):
        """Skips cursor rules if file already exists."""
        rules = tmp_path / ".cursor" / "rules" / "tapps-pipeline.md"
        rules.parent.mkdir(parents=True)
        rules.write_text("existing rules")
        _generate_rules("cursor", tmp_path)
        assert rules.read_text(encoding="utf-8") == "existing rules"


# ---------------------------------------------------------------------------
# Multi-host configuration tests
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

    def test_check_mode(self, tmp_path):
        """Check mode verifies all hosts."""
        # Set up valid cursor config only
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config = {"mcpServers": {"tapps-mcp": {"command": "tapps-mcp", "args": ["serve"]}}}
        (cursor_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
        # vscode is missing → should return False
        ok = _configure_multiple_hosts(
            ["cursor", "vscode"],
            tmp_path,
            check=True,
            rules=False,
        )
        assert ok is False

    def test_generates_rules_when_enabled(self, tmp_path):
        """Rules are generated alongside config when rules=True."""
        _configure_multiple_hosts(
            ["cursor"],
            tmp_path,
            force=True,
            rules=True,
        )
        assert (tmp_path / ".cursor" / "mcp.json").exists()
        assert (tmp_path / ".cursor" / "rules" / "tapps-pipeline.md").exists()

    def test_skips_rules_when_disabled(self, tmp_path):
        """Rules are skipped when rules=False."""
        _configure_multiple_hosts(
            ["cursor"],
            tmp_path,
            force=True,
            rules=False,
        )
        assert (tmp_path / ".cursor" / "mcp.json").exists()
        assert not (tmp_path / ".cursor" / "rules" / "tapps-pipeline.md").exists()


# ---------------------------------------------------------------------------
# Story 12.2: Server instructions field (Claude Code only)
# ---------------------------------------------------------------------------


class TestServerInstructions:
    """Tests for the instructions field in generated Claude Code config."""

    def test_claude_code_has_instructions(self, tmp_path):
        """Claude Code config includes instructions field."""
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            _generate_config("claude-code", tmp_path / "project", scope="user")
        data = json.loads((tmp_path / ".claude.json").read_text(encoding="utf-8"))
        entry = data["mcpServers"]["tapps-mcp"]
        assert "instructions" in entry
        assert isinstance(entry["instructions"], str)
        assert len(entry["instructions"]) > 0

    def test_instructions_mentions_quality(self, tmp_path):
        """Instructions string mentions key capabilities for Tool Search matching."""
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            _generate_config("claude-code", tmp_path / "project", scope="user")
        data = json.loads((tmp_path / ".claude.json").read_text(encoding="utf-8"))
        instructions = data["mcpServers"]["tapps-mcp"]["instructions"]
        assert "quality" in instructions.lower()
        assert "security" in instructions.lower()

    def test_cursor_has_no_instructions(self, tmp_path):
        """Cursor config does NOT include instructions field."""
        project = tmp_path / "project"
        project.mkdir()
        _generate_config("cursor", project)
        data = json.loads((project / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        assert "instructions" not in data["mcpServers"]["tapps-mcp"]

    def test_vscode_has_no_instructions(self, tmp_path):
        """VS Code config does NOT include instructions field."""
        project = tmp_path / "project"
        project.mkdir()
        _generate_config("vscode", project)
        data = json.loads((project / ".vscode" / "mcp.json").read_text(encoding="utf-8"))
        assert "instructions" not in data["servers"]["tapps-mcp"]

    def test_instructions_in_merged_config(self, tmp_path):
        """Instructions field is present even when merging into existing config."""
        config_path = tmp_path / ".claude.json"
        existing = {"mcpServers": {"other": {"command": "other"}}}
        config_path.write_text(json.dumps(existing), encoding="utf-8")
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            _generate_config("claude-code", tmp_path / "project", force=True, scope="user")
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert "instructions" in data["mcpServers"]["tapps-mcp"]
        assert "other" in data["mcpServers"]


# ---------------------------------------------------------------------------
# Story 12.4: Environment variables in MCP config (all platforms)
# ---------------------------------------------------------------------------


class TestEnvInConfig:
    """Tests for env block in generated MCP configs."""

    def test_claude_code_has_env(self, tmp_path):
        """Claude Code config uses '.' (CWD == project root)."""
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            _generate_config("claude-code", tmp_path / "project", scope="user")
        data = json.loads((tmp_path / ".claude.json").read_text(encoding="utf-8"))
        entry = data["mcpServers"]["tapps-mcp"]
        assert entry["env"]["TAPPS_MCP_PROJECT_ROOT"] == "."

    def test_cursor_has_env(self, tmp_path):
        """Cursor config includes env with TAPPS_MCP_PROJECT_ROOT."""
        project = tmp_path / "project"
        project.mkdir()
        _generate_config("cursor", project)
        data = json.loads((project / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        entry = data["mcpServers"]["tapps-mcp"]
        assert entry["env"]["TAPPS_MCP_PROJECT_ROOT"] == "${workspaceFolder}"

    def test_vscode_has_env(self, tmp_path):
        """VS Code config includes env with TAPPS_MCP_PROJECT_ROOT."""
        project = tmp_path / "project"
        project.mkdir()
        _generate_config("vscode", project)
        data = json.loads((project / ".vscode" / "mcp.json").read_text(encoding="utf-8"))
        entry = data["servers"]["tapps-mcp"]
        assert entry["env"]["TAPPS_MCP_PROJECT_ROOT"] == "${workspaceFolder}"

    def test_env_preserves_command_and_args(self, tmp_path):
        """env block does not interfere with command and args fields."""
        project = tmp_path / "project"
        project.mkdir()
        _generate_config("cursor", project)
        data = json.loads((project / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        entry = data["mcpServers"]["tapps-mcp"]
        assert entry["command"] == "tapps-mcp"
        assert entry["args"] == ["serve"]
        assert "env" in entry

    def test_claude_code_includes_brain_env_block(self, tmp_path):
        """TAP-1336: tapps_init/upgrade emits the brain memory env block by default.

        Without these keys a fresh consumer install hits brain with no auth /
        identity and tapps_session_start hard-fails on the first call.
        """
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            (tmp_path / "myproject").mkdir()
            _generate_config("claude-code", tmp_path / "myproject", scope="user")
        data = json.loads((tmp_path / ".claude.json").read_text(encoding="utf-8"))
        env = data["mcpServers"]["tapps-mcp"]["env"]
        assert env["TAPPS_MCP_MEMORY_BRAIN_HTTP_URL"] == "http://localhost:8080"
        # Token uses ${...} substitution so the file is safe to commit.
        assert env["TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN"] == "${TAPPS_BRAIN_AUTH_TOKEN}"
        assert env["TAPPS_MCP_MEMORY_BRAIN_PROJECT_ID"] == "myproject"

    def test_brain_env_token_is_substitution_not_literal(self, tmp_path):
        """The auth token must never be written as a literal value (commit safety)."""
        project = tmp_path / "demo"
        project.mkdir()
        _generate_config("cursor", project)
        data = json.loads((project / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        token = data["mcpServers"]["tapps-mcp"]["env"]["TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN"]
        assert token.startswith("${") and token.endswith("}")

    def test_merge_preserves_other_servers_with_env(self, tmp_path):
        """Merging preserves existing servers while adding env to tapps-mcp."""
        project = tmp_path / "project"
        cursor_dir = project / ".cursor"
        cursor_dir.mkdir(parents=True)
        existing = {"mcpServers": {"other": {"command": "x"}}}
        (cursor_dir / "mcp.json").write_text(json.dumps(existing), encoding="utf-8")
        _generate_config("cursor", project)
        data = json.loads((cursor_dir / "mcp.json").read_text(encoding="utf-8"))
        assert "other" in data["mcpServers"]
        assert data["mcpServers"]["tapps-mcp"]["env"]["TAPPS_MCP_PROJECT_ROOT"] == (
            "${workspaceFolder}"
        )


# ---------------------------------------------------------------------------
# run_upgrade tests
# ---------------------------------------------------------------------------


class TestRunUpgrade:
    """Tests for the run_upgrade entry point."""

    def test_dry_run_no_file_changes(self, tmp_path, capsys):
        """dry_run=True should not create or modify files."""
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            result = run_upgrade(
                mcp_host="auto",
                project_root=str(tmp_path),
                dry_run=True,
            )
        assert result is True
        captured = capsys.readouterr()
        assert "DRY-RUN" in captured.out
        # AGENTS.md should not have been created
        assert not (tmp_path / "AGENTS.md").exists()

    def test_updates_agents_md_when_outdated(self, tmp_path, capsys):
        """run_upgrade updates AGENTS.md when it has an outdated version."""
        content = "<!-- tapps-agents-version: 0.0.1 -->\n# Old AGENTS\n\nOld content.\n"
        (tmp_path / "AGENTS.md").write_text(content, encoding="utf-8")
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            run_upgrade(
                mcp_host="auto",
                project_root=str(tmp_path),
            )
        captured = capsys.readouterr()
        # The AGENTS.md section should report an update
        assert "AGENTS.md" in captured.out

    def test_agents_md_up_to_date(self, tmp_path, capsys):
        """run_upgrade reports up-to-date when AGENTS.md is current."""
        from tapps_mcp.prompts.prompt_loader import load_agents_template

        (tmp_path / "AGENTS.md").write_text(load_agents_template(), encoding="utf-8")
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            run_upgrade(
                mcp_host="auto",
                project_root=str(tmp_path),
            )
        captured = capsys.readouterr()
        assert "up-to-date" in captured.out

    def test_creates_agents_md_when_missing(self, tmp_path, capsys):
        """run_upgrade creates AGENTS.md when it does not exist."""
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            run_upgrade(
                mcp_host="auto",
                project_root=str(tmp_path),
            )
        assert (tmp_path / "AGENTS.md").exists()
        captured = capsys.readouterr()
        assert "AGENTS.md" in captured.out
        assert "created" in captured.out

    def test_emit_json_outputs_parseable_json_with_summary(self, tmp_path, capsys):
        """``emit_json=True`` writes valid JSON to stdout with the full dry-run dict.

        Verifies the 3.2.2 CLI addition: the precision work from 3.2.0/3.2.1
        is now accessible via ``tapps-mcp upgrade --json`` so CLI consumers
        get the same ``dry_run_summary`` + ``managed_files`` / ``preserved_files``
        lists that MCP tool callers already receive.
        """
        import json

        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            result = run_upgrade(
                mcp_host="claude-code",
                project_root=str(tmp_path),
                dry_run=True,
                emit_json=True,
            )
        assert result is True
        captured = capsys.readouterr()
        # stdout must be pure JSON — no text-summary artefacts like "DRY-RUN"
        assert "[DRY-RUN]" not in captured.out
        parsed = json.loads(captured.out)
        assert parsed["dry_run"] is True
        assert "dry_run_summary" in parsed
        assert parsed["dry_run_summary"]["verdict"] in {
            "safe-to-run",
            "review-recommended",
        }
        # AGENTS.md must not have been created under dry_run
        assert not (tmp_path / "AGENTS.md").exists()


class TestCliUpgrade:
    """Tests for the CLI upgrade command via Click's CliRunner."""

    def test_upgrade_help(self):
        """CLI upgrade --help works."""
        runner = CliRunner()
        result = runner.invoke(main, ["upgrade", "--help"])
        assert result.exit_code == 0
        assert "Refresh generated files" in result.output

    def test_upgrade_dry_run_via_cli(self, tmp_path):
        """CLI upgrade --dry-run does not create files."""
        runner = CliRunner()
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            result = runner.invoke(
                main,
                ["upgrade", "--project-root", str(tmp_path), "--dry-run"],
            )
        assert result.exit_code == 0
        assert "DRY-RUN" in result.output
        # AGENTS.md should not have been created
        assert not (tmp_path / "AGENTS.md").exists()

    def test_upgrade_runs_successfully(self, tmp_path):
        """CLI upgrade creates expected files."""
        runner = CliRunner()
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            result = runner.invoke(
                main,
                ["upgrade", "--project-root", str(tmp_path)],
            )
        assert result.exit_code == 0
        assert "AGENTS.md" in result.output


# ---------------------------------------------------------------------------
# Story 47.1: Default scope is "project"
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


class TestEpic80ConsumerInit:
    """Regression tests for Epic 80 (hooks, MCP merge, package-root guard)."""

    def test_is_tapps_mcp_package_layout(self, tmp_path):
        root = tmp_path / "r" / "packages" / "tapps-mcp"
        root.mkdir(parents=True)
        assert is_tapps_mcp_package_layout(root) is True
        assert is_tapps_mcp_package_layout(tmp_path / "other") is False

    def test_merge_preserves_extra_env_keys(self, tmp_path):
        project = tmp_path / "project"
        cursor_dir = project / ".cursor"
        cursor_dir.mkdir(parents=True)
        existing = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "tapps-mcp",
                    "args": ["serve"],
                    "env": {
                        "TAPPS_MCP_PROJECT_ROOT": ".",
                        "TAPPS_MCP_CONTEXT7_API_KEY": "secret",
                    },
                },
            },
        }
        (cursor_dir / "mcp.json").write_text(json.dumps(existing), encoding="utf-8")
        with patch(
            "tapps_mcp.distribution.setup_generator.shutil.which", return_value="/bin/tapps-mcp"
        ):
            _generate_config("cursor", project, force=True)
        data = json.loads((cursor_dir / "mcp.json").read_text(encoding="utf-8"))
        env = data["mcpServers"]["tapps-mcp"]["env"]
        assert env.get("TAPPS_MCP_CONTEXT7_API_KEY") == "secret"

    def test_noninteractive_skips_overwrite_without_hang(self, tmp_path):
        project = tmp_path / "project"
        cursor_dir = project / ".cursor"
        cursor_dir.mkdir(parents=True)
        existing = {"mcpServers": {"tapps-mcp": {"command": "old"}}}
        (cursor_dir / "mcp.json").write_text(json.dumps(existing), encoding="utf-8")
        with patch.object(sys.stdin, "isatty", return_value=False):
            ok = _generate_config("cursor", project, force=False)
        assert ok is True
        data = json.loads((cursor_dir / "mcp.json").read_text(encoding="utf-8"))
        assert data["mcpServers"]["tapps-mcp"]["command"] == "old"

    def test_noninteractive_assume_yes_overwrites(self, tmp_path):
        project = tmp_path / "project"
        cursor_dir = project / ".cursor"
        cursor_dir.mkdir(parents=True)
        existing = {"mcpServers": {"tapps-mcp": {"command": "old"}}}
        (cursor_dir / "mcp.json").write_text(json.dumps(existing), encoding="utf-8")
        with (
            patch.object(sys.stdin, "isatty", return_value=False),
            patch.dict(os.environ, {"TAPPS_MCP_INIT_ASSUME_YES": "1"}),
            patch(
                "tapps_mcp.distribution.setup_generator.shutil.which", return_value="/x/tapps-mcp"
            ),
        ):
            ok = _generate_config("cursor", project, force=False)
        assert ok is True
        data = json.loads((cursor_dir / "mcp.json").read_text(encoding="utf-8"))
        assert data["mcpServers"]["tapps-mcp"]["command"] == "tapps-mcp"

    def test_run_init_refuses_package_dir_without_flag(self, tmp_path):
        pkg = tmp_path / "packages" / "tapps-mcp"
        pkg.mkdir(parents=True)
        ok = run_init(mcp_host="cursor", project_root=str(pkg), rules=False)
        assert ok is False

    def test_run_init_package_dir_with_allow_flag(self, tmp_path):
        pkg = tmp_path / "packages" / "tapps-mcp"
        pkg.mkdir(parents=True)
        with patch(
            "tapps_mcp.distribution.setup_generator.shutil.which", return_value="/bin/tapps-mcp"
        ):
            ok = run_init(
                mcp_host="cursor",
                project_root=str(pkg),
                rules=False,
                allow_package_init=True,
            )
        assert ok is True

    def test_with_docs_mcp_adds_server_entry(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()

        def _which(cmd: str) -> str | None:
            if cmd == "tapps-mcp":
                return "/bin/tapps-mcp"
            return None

        with patch("tapps_mcp.distribution.setup_generator.shutil.which", side_effect=_which):
            _generate_config("cursor", project, force=True, with_docs_mcp=True)
        data = json.loads((project / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        assert "docs-mcp" in data["mcpServers"]
        assert data["mcpServers"]["docs-mcp"]["command"] == "uv"
        assert "docsmcp" in data["mcpServers"]["docs-mcp"]["args"]


# ---------------------------------------------------------------------------
# Story 47.5: Upgrade command has --scope flag
# ---------------------------------------------------------------------------


class TestUpgradeScope:
    """Tests for Epic 47.5 - upgrade command scope support."""

    def test_cli_upgrade_has_scope_option(self):
        """CLI upgrade command has --scope flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["upgrade", "--help"])
        assert result.exit_code == 0
        assert "--scope" in result.output

    def test_run_upgrade_accepts_scope(self, tmp_path):
        """run_upgrade accepts scope parameter without error."""
        with patch(
            "tapps_mcp.pipeline.upgrade.upgrade_pipeline",
            return_value={
                "success": True,
                "version": "0.8.0",
                "components": {},
                "errors": [],
            },
        ):
            ok = run_upgrade(
                mcp_host="claude-code",
                project_root=str(tmp_path),
                dry_run=True,
                scope="project",
            )
        assert ok


# ---------------------------------------------------------------------------
# Issue #80.2: env var migration across scopes
# ---------------------------------------------------------------------------


class TestEnvMigrationAcrossScopes:
    """Issue #80.2 — init --scope project preserves env from user-scope config."""

    def test_load_existing_env_from_other_scope_user_to_project(self, tmp_path):
        """Project-scope init picks up env vars from ~/.claude.json."""
        home = tmp_path / "home"
        home.mkdir()
        user_cfg = home / ".claude.json"
        user_cfg.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "tapps-mcp": {
                            "command": "tapps-mcp",
                            "args": ["serve"],
                            "env": {
                                "CONTEXT7_API_KEY": "ctx7sk-test",
                                "TAPPS_MCP_PROJECT_ROOT": "/old/path",
                            },
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        project = tmp_path / "proj"
        project.mkdir()
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=home):
            env = _load_existing_env_from_other_scope("claude-code", project, "project")
        assert env == {"CONTEXT7_API_KEY": "ctx7sk-test"}

    def test_load_existing_env_returns_empty_when_missing(self, tmp_path):
        """Missing other-scope file → empty dict."""
        home = tmp_path / "home"
        home.mkdir()
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=home):
            env = _load_existing_env_from_other_scope("claude-code", tmp_path / "proj", "project")
        assert env == {}

    def test_load_existing_env_skips_non_claude_hosts(self, tmp_path):
        """Non-claude hosts have no alternate scope."""
        assert _load_existing_env_from_other_scope("cursor", tmp_path, "project") == {}

    def test_generate_config_migrates_env_from_user_scope(self, tmp_path):
        """Creating new project .mcp.json merges env from ~/.claude.json."""
        home = tmp_path / "home"
        home.mkdir()
        (home / ".claude.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "tapps-mcp": {
                            "command": "tapps-mcp",
                            "args": ["serve"],
                            "env": {"CONTEXT7_API_KEY": "ctx7sk-migrated"},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        project = tmp_path / "proj"
        project.mkdir()
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=home):
            ok = _generate_config("claude-code", project, scope="project", force=True)
        assert ok
        data = json.loads((project / ".mcp.json").read_text(encoding="utf-8"))
        env = data["mcpServers"]["tapps-mcp"]["env"]
        assert env["CONTEXT7_API_KEY"] == "ctx7sk-migrated"
        # Scope-specific key still set
        assert env["TAPPS_MCP_PROJECT_ROOT"] == "."


# ---------------------------------------------------------------------------
# Issue #80.3: plaintext secret detection
# ---------------------------------------------------------------------------


class TestPlaintextSecretDetection:
    def test_looks_like_secret_key_matches_common_patterns(self):
        assert _looks_like_secret_key("CONTEXT7_API_KEY")
        assert _looks_like_secret_key("GITHUB_TOKEN")
        assert _looks_like_secret_key("my_secret")
        assert _looks_like_secret_key("db_password")

    def test_looks_like_secret_key_ignores_known_benign(self):
        assert not _looks_like_secret_key("TAPPS_MCP_PROJECT_ROOT")
        assert not _looks_like_secret_key("DOCS_MCP_PROJECT_ROOT")
        assert not _looks_like_secret_key("VIRTUAL_ENV")
        assert not _looks_like_secret_key("FOO")

    def test_value_is_plaintext_secret_excludes_interpolation(self):
        assert _value_is_plaintext_secret("ctx7sk-abc123")
        assert not _value_is_plaintext_secret("${CONTEXT7_API_KEY}")
        assert not _value_is_plaintext_secret("$CONTEXT7_API_KEY")
        assert not _value_is_plaintext_secret("")
        assert not _value_is_plaintext_secret(None)

    def test_collect_plaintext_secrets(self):
        entry = {
            "env": {
                "TAPPS_MCP_PROJECT_ROOT": ".",
                "CONTEXT7_API_KEY": "ctx7sk-xyz",
                "SAFE_TOKEN": "${SAFE_TOKEN}",
            }
        }
        secrets = _collect_plaintext_secrets(entry)
        assert secrets == ["CONTEXT7_API_KEY"]

    def test_generate_config_warns_on_plaintext_secret(self, tmp_path, capsys):
        """_generate_config prints a warning when env has plaintext secrets."""
        project = tmp_path / "proj"
        project.mkdir()
        existing = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "tapps-mcp",
                    "args": ["serve"],
                    "env": {
                        "TAPPS_MCP_PROJECT_ROOT": ".",
                        "CONTEXT7_API_KEY": "ctx7sk-plain",
                    },
                }
            }
        }
        (project / ".mcp.json").write_text(json.dumps(existing), encoding="utf-8")
        ok = _generate_config("claude-code", project, scope="project", force=True)
        assert ok
        out = capsys.readouterr().out
        assert "plaintext secret" in out.lower()
        assert "CONTEXT7_API_KEY" in out

    def test_ensure_gitignore_entry_appends(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text("node_modules\n", encoding="utf-8")
        result = _ensure_gitignore_entry(tmp_path, ".mcp.json")
        assert result is True
        assert ".mcp.json" in gi.read_text(encoding="utf-8")

    def test_ensure_gitignore_entry_detects_existing(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text(".mcp.json\n", encoding="utf-8")
        assert _ensure_gitignore_entry(tmp_path, ".mcp.json") is False

    def test_ensure_gitignore_entry_returns_none_when_missing(self, tmp_path):
        assert _ensure_gitignore_entry(tmp_path, ".mcp.json") is None


# ---------------------------------------------------------------------------
# Issue #77: uv context detection
# ---------------------------------------------------------------------------


class TestUvContextDetection:
    def test_returns_none_when_no_pyproject(self, tmp_path):
        assert _detect_uv_context(tmp_path) is None

    def test_detects_uv_lock_and_extra(self, tmp_path):
        (tmp_path / "uv.lock").write_text("", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\n'
            "[project.optional-dependencies]\n"
            'mcp = ["tapps-mcp @ git+https://github.com/wtthornton/tapps-mcp"]\n',
            encoding="utf-8",
        )
        info = _detect_uv_context(tmp_path)
        assert info is not None
        assert info["has_uv_lock"] is True
        assert info["tapps_mcp_extra"] == "mcp"

    def test_detects_dependency_groups(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\n[dependency-groups]\ntapps-mcp = ["tapps-mcp>=1.0"]\n',
            encoding="utf-8",
        )
        info = _detect_uv_context(tmp_path)
        assert info is not None
        assert info["tapps_mcp_extra"] == "tapps-mcp"

    def test_no_extra_when_tapps_mcp_absent(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\n[project.optional-dependencies]\ndev = ["pytest"]\n',
            encoding="utf-8",
        )
        info = _detect_uv_context(tmp_path)
        assert info is not None
        assert info["tapps_mcp_extra"] is None

    def test_should_use_uv_launch_off_disables(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\n[project.optional-dependencies]\nmcp = ["tapps-mcp"]\n',
            encoding="utf-8",
        )
        use_uv, _, _ = _should_use_uv_launch(tmp_path, uv_mode="off")
        assert use_uv is False

    def test_should_use_uv_launch_on_forces(self, tmp_path):
        use_uv, extra, _ = _should_use_uv_launch(tmp_path, uv_mode="on")
        assert use_uv is True
        assert extra is None

    def test_build_uv_run_tapps_launch_with_extra(self):
        cmd, args = _build_uv_run_tapps_launch("mcp")
        assert cmd == "uv"
        assert args == ["run", "--extra", "mcp", "--no-sync", "tapps-mcp", "serve"]

    def test_build_uv_run_tapps_launch_without_extra(self):
        cmd, args = _build_uv_run_tapps_launch(None)
        assert cmd == "uv"
        assert args == ["run", "--no-sync", "tapps-mcp", "serve"]

    def test_generate_config_uses_uv_launch(self, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        uv_launch = ("uv", ["run", "--extra", "mcp", "--no-sync", "tapps-mcp", "serve"])
        _generate_config("cursor", project, uv_launch=uv_launch, force=True)
        data = json.loads((project / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        entry = data["mcpServers"]["tapps-mcp"]
        assert entry["command"] == "uv"
        assert "--extra" in entry["args"]
        assert "mcp" in entry["args"]

    def test_cli_init_has_uv_flags(self):
        runner = CliRunner()
        result = runner.invoke(main, ["init", "--help"])
        assert result.exit_code == 0
        assert "--uv" in result.output
        assert "--no-uv" in result.output
        assert "--uv-extra" in result.output

    def test_docsmcp_entry_uses_uv_launch(self, tmp_path):
        """docs-mcp entry should use uv launch when provided (Issue #79 sub)."""
        from tapps_mcp.distribution.setup_generator import _build_docsmcp_server_entry

        uv_launch = ("uv", ["run", "--extra", "mcp", "--no-sync", "tapps-mcp", "serve"])
        entry = _build_docsmcp_server_entry("cursor", uv_launch=uv_launch)
        assert entry["command"] == "uv"
        # tapps-mcp should be replaced with docsmcp in args
        assert "docsmcp" in entry["args"]
        assert "tapps-mcp" not in entry["args"]
        assert "serve" in entry["args"]

    def test_generate_config_with_extra_env(self, tmp_path):
        """extra_env should inject env vars into the tapps-mcp entry (Issue #79)."""
        project = tmp_path / "proj"
        project.mkdir()
        _generate_config(
            "cursor",
            project,
            force=True,
            extra_env={"TAPPS_MCP_CONTEXT7_API_KEY": "${TAPPS_MCP_CONTEXT7_API_KEY}"},
        )
        data = json.loads((project / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        entry = data["mcpServers"]["tapps-mcp"]
        assert entry["env"]["TAPPS_MCP_CONTEXT7_API_KEY"] == "${TAPPS_MCP_CONTEXT7_API_KEY}"
        # TAPPS_MCP_PROJECT_ROOT should still be present
        assert "TAPPS_MCP_PROJECT_ROOT" in entry["env"]

    def test_cli_init_has_with_context7_flag(self):
        """CLI init should have --with-context7 flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["init", "--help"])
        assert result.exit_code == 0
        assert "--with-context7" in result.output
