"""Tests for distribution.setup_generator (Story 6.2 - One-Command Setup)."""

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from tapps_mcp.cli import main
from tapps_mcp.distribution.setup_generator import (
    _check_config,
    _detect_hosts,
    _generate_config,
    _get_config_path,
    _get_servers_key,
    _merge_config,
    run_init,
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
            path = _get_config_path("claude-code", tmp_path / "project")
        assert path == tmp_path / ".claude.json"

    def test_cursor_path(self, tmp_path):
        project = tmp_path / "project"
        path = _get_config_path("cursor", project)
        assert path == project / ".cursor" / "mcp.json"

    def test_vscode_path(self, tmp_path):
        project = tmp_path / "project"
        path = _get_config_path("vscode", project)
        assert path == project / ".vscode" / "mcp.json"

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
            _generate_config("claude-code", tmp_path / "project")
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
        with patch("tapps_mcp.distribution.setup_generator.click.confirm", return_value=False):
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

        with patch("tapps_mcp.distribution.setup_generator.click.confirm", return_value=True):
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
            assert _check_config("claude-code", tmp_path / "project") is True


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

    def test_auto_uses_first_detected_host(self, tmp_path):
        (tmp_path / ".claude").mkdir()
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            run_init(mcp_host="auto", project_root=str(tmp_path))
        # Should have written claude-code config
        assert (tmp_path / ".claude.json").exists()

    def test_auto_multiple_hosts_uses_first(self, tmp_path):
        (tmp_path / ".claude").mkdir()
        (tmp_path / "AppData" / "Roaming" / "Cursor").mkdir(parents=True)
        with (
            patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.setup_generator.sys.platform", "win32"),
        ):
            run_init(mcp_host="auto", project_root=str(tmp_path), check=False)
        # Claude Code should be first detected, so its config is written
        assert (tmp_path / ".claude.json").exists()

    def test_explicit_cursor_host(self, tmp_path):
        run_init(mcp_host="cursor", project_root=str(tmp_path))
        assert (tmp_path / ".cursor" / "mcp.json").exists()

    def test_explicit_vscode_host(self, tmp_path):
        run_init(mcp_host="vscode", project_root=str(tmp_path))
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
        assert "Generate MCP configuration" in result.output

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
