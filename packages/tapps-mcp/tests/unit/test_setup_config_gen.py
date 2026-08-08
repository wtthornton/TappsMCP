"""Tests for distribution.setup_config_gen — writing/merging one host config."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_mcp.distribution.setup_generator import (
    _generate_config,
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


def _cursor_wrapper_path(project: Path) -> str:
    return str((project / ".cursor" / "bin" / "tapps-mcp-serve.sh").resolve())


class TestGenerateConfig:
    """Tests for config file generation."""

    def test_generates_cursor_config(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        _generate_config("cursor", project)
        config_path = project / ".cursor" / "mcp.json"
        assert config_path.exists()
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["mcpServers"]["tapps-mcp"]["command"] == _cursor_wrapper_path(project)
        assert data["mcpServers"]["tapps-mcp"]["args"] == []
        wrapper = project / ".cursor" / "bin" / "tapps-mcp-serve.sh"
        assert wrapper.exists()
        assert "source .env" in wrapper.read_text(encoding="utf-8")

    def test_generates_vscode_config(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        with patch(
            "tapps_mcp.distribution.setup_generator.shutil.which",
            return_value="/bin/tapps-mcp",
        ):
            _generate_config("vscode", project)
        config_path = project / ".vscode" / "mcp.json"
        assert config_path.exists()
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["servers"]["tapps-mcp"]["command"] == "/bin/tapps-mcp"

    def test_generates_claude_code_config(self, tmp_path):
        with (
            patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path),
            patch(
                "tapps_mcp.distribution.setup_generator.shutil.which",
                return_value="/bin/tapps-mcp",
            ),
        ):
            _generate_config("claude-code", tmp_path / "project", scope="user")
        config_path = tmp_path / ".claude.json"
        assert config_path.exists()
        data = json.loads(config_path.read_text(encoding="utf-8"))
        # Claude Code uses stdio wrapper scripts (TAP-5155) to probe ~/.tapps-mcp/current
        expected_command = str(tmp_path / "project" / ".claude/bin/tapps-mcp-serve.sh")
        assert data["mcpServers"]["tapps-mcp"]["command"] == expected_command

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
        assert data["mcpServers"]["tapps-mcp"]["command"] == _cursor_wrapper_path(project)

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
        """Project scope writes .mcp.json in project root with current-probe wrapper."""
        project = tmp_path / "project"
        project.mkdir()
        with patch(
            "tapps_mcp.distribution.setup_generator.shutil.which",
            return_value="/bin/tapps-mcp",
        ):
            _generate_config("claude-code", project, scope="project")
        config_path = project / ".mcp.json"
        assert config_path.exists()
        data = json.loads(config_path.read_text(encoding="utf-8"))
        command = data["mcpServers"]["tapps-mcp"]["command"]
        assert command.endswith(".claude/bin/tapps-mcp-serve.sh")
        wrapper = Path(command)
        assert wrapper.is_file()
        text = wrapper.read_text(encoding="utf-8")
        assert "_blue_green=" in text
        assert "${HOME}/.tapps-mcp/current/bin/tapps-mcp" in text

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

    def test_claude_nlt_stdio_writes_current_probe_wrappers(self, tmp_path: Path) -> None:
        """TAP-5155: Claude NLT stdio configs use .claude/bin wrappers with current probe."""
        from tapps_mcp.distribution.setup_generator import (
            _stdio_wrapper_rel,
            regenerate_nlt_stdio_wrappers,
        )

        project = tmp_path / "proj"
        project.mkdir()
        with patch(
            "tapps_mcp.distribution.setup_generator.shutil.which",
            side_effect=lambda name: f"/home/user/.local/bin/{name}",
        ):
            _generate_config(
                "claude-code",
                project,
                scope="project",
                force=True,
                use_nlt_plugin=True,
                mcp_bundle="minimal",
            )
        data = json.loads((project / ".mcp.json").read_text(encoding="utf-8"))
        entry = data["mcpServers"]["nlt-build"]
        assert "url" not in entry
        command = entry["command"]
        assert command.endswith(str(_stdio_wrapper_rel("claude-code", "nlt-build")))
        script = Path(command).read_text(encoding="utf-8")
        assert "_blue_green=" in script
        assert 'exec "$_blue_green"' in script

        # HTTP Claude configs must not grow wrappers on regenerate.
        http_proj = tmp_path / "http-proj"
        http_proj.mkdir()
        (http_proj / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "nlt-build": {
                            "type": "http",
                            "url": "http://127.0.0.1:8760/mcp",
                            "headers": {"X-Tapps-Project-Root": str(http_proj)},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        assert regenerate_nlt_stdio_wrappers(http_proj) == []
        assert not (http_proj / ".claude" / "bin").exists()


# ---------------------------------------------------------------------------
# Check mode tests
# ---------------------------------------------------------------------------


class TestDeveloperBundleMcpConfig:
    """TAP-3925: developer bundle writes three active NLT MCP servers."""

    def test_generate_mcp_json_developer_three_active(self, tmp_path: Path) -> None:
        with patch(
            "tapps_mcp.distribution.setup_generator.shutil.which",
            return_value="/bin/tapps-mcp",
        ):
            ok = _generate_config(
                "cursor",
                tmp_path,
                force=True,
                mcp_bundle="developer",
                use_nlt_plugin=True,
            )
        assert ok is True
        from tapps_mcp.distribution.setup_generator import _load_mcp_config_json

        data = _load_mcp_config_json(tmp_path / ".cursor" / "mcp.json")
        servers = data["mcpServers"]
        assert set(servers.keys()) == {
            "nlt-build",
            "nlt-memory",
            "nlt-linear-issues",
        }

    def test_generate_mcp_json_minimal_build_only(self, tmp_path: Path) -> None:
        with patch(
            "tapps_mcp.distribution.setup_generator.shutil.which",
            return_value="/bin/tapps-mcp",
        ):
            ok = _generate_config(
                "cursor",
                tmp_path,
                force=True,
                mcp_bundle="minimal",
                use_nlt_plugin=True,
            )
        assert ok is True
        from tapps_mcp.distribution.setup_generator import _load_mcp_config_json

        data = _load_mcp_config_json(tmp_path / ".cursor" / "mcp.json")
        servers = data["mcpServers"]
        assert set(servers.keys()) == {"nlt-build"}


# ---------------------------------------------------------------------------
# CLI integration tests (Click CliRunner)
# ---------------------------------------------------------------------------
