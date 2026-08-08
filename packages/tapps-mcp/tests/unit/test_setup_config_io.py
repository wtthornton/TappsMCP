"""Tests for distribution.setup_config_io — config paths, servers key, and validation."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_mcp.distribution.setup_generator import (
    _check_config,
    _get_config_path,
    _get_servers_key,
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


class TestCheckConfig:
    """Tests for --check mode verification."""

    def test_check_valid_config(self, tmp_path):
        project = tmp_path / "project"
        cursor_dir = project / ".cursor"
        cursor_dir.mkdir(parents=True)
        wrapper = cursor_dir / "bin" / "tapps-mcp-serve.sh"
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text("#!/bin/bash\nexec tapps-mcp serve\n", encoding="utf-8")
        config = {
            "mcpServers": {
                "tapps-mcp": {"command": str(wrapper.resolve()), "args": []},
            },
        }
        (cursor_dir / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
        assert _check_config("cursor", project) is True

    def test_check_valid_config_legacy_direct_launch(self, tmp_path):
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
