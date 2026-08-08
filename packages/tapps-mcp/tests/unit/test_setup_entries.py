"""Tests for distribution.setup_entries — server entry construction and merging."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_mcp.distribution.setup_generator import (
    _generate_config,
    _merge_config,
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


class TestMergeConfig:
    """Tests for merging tapps-mcp into existing configs."""

    def test_merge_into_empty(self):
        with patch(
            "tapps_mcp.distribution.setup_generator.shutil.which",
            return_value="/bin/tapps-mcp",
        ):
            result = _merge_config({}, "cursor")
        assert "mcpServers" in result
        assert "tapps-mcp" in result["mcpServers"]
        assert result["mcpServers"]["tapps-mcp"]["command"] == "/bin/tapps-mcp"

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
        with patch(
            "tapps_mcp.distribution.setup_generator.shutil.which",
            return_value="/bin/tapps-mcp",
        ):
            result = _merge_config(existing, "cursor")
        assert result["mcpServers"]["tapps-mcp"]["command"] == "/bin/tapps-mcp"
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
        """Cursor config gets the resolved absolute project root (TAP-2199)."""
        project = tmp_path / "project"
        project.mkdir()
        _generate_config("cursor", project)
        data = json.loads((project / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        entry = data["mcpServers"]["tapps-mcp"]
        assert entry["env"]["TAPPS_MCP_PROJECT_ROOT"] == str(project.resolve())
        # TAP-2199: never the literal ${workspaceFolder} — Claude Code CLI does
        # not expand it and the server then mkdirs a phantom directory.
        assert "${" not in entry["env"]["TAPPS_MCP_PROJECT_ROOT"]

    def test_vscode_has_env(self, tmp_path):
        """VS Code config gets the resolved absolute project root (TAP-2199)."""
        project = tmp_path / "project"
        project.mkdir()
        _generate_config("vscode", project)
        data = json.loads((project / ".vscode" / "mcp.json").read_text(encoding="utf-8"))
        entry = data["servers"]["tapps-mcp"]
        assert entry["env"]["TAPPS_MCP_PROJECT_ROOT"] == str(project.resolve())
        assert "${" not in entry["env"]["TAPPS_MCP_PROJECT_ROOT"]

    def test_env_preserves_command_and_args(self, tmp_path):
        """env block does not interfere with command and args fields."""
        project = tmp_path / "project"
        project.mkdir()
        _generate_config("cursor", project)
        data = json.loads((project / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        entry = data["mcpServers"]["tapps-mcp"]
        assert entry["command"] == _cursor_wrapper_path(project)
        assert entry["args"] == []
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

    def test_brain_project_id_slugifies_special_chars(self, tmp_path):
        """Init-time slug matches runtime _slugify_project_root (foo.bar → foo-bar)."""
        project = tmp_path / "foo.bar"
        project.mkdir()
        _generate_config("cursor", project)
        env = json.loads((project / ".cursor" / "mcp.json").read_text(encoding="utf-8"))[
            "mcpServers"
        ]["tapps-mcp"]["env"]
        assert env["TAPPS_MCP_MEMORY_BRAIN_PROJECT_ID"] == "foo-bar"

    def test_brain_project_id_omitted_for_generic_dir(self, tmp_path):
        """Generic dir names must not auto-emit a colliding tenant slug."""
        project = tmp_path / "tmp"
        project.mkdir()
        _generate_config("cursor", project)
        env = json.loads((project / ".cursor" / "mcp.json").read_text(encoding="utf-8"))[
            "mcpServers"
        ]["tapps-mcp"]["env"]
        assert "TAPPS_MCP_MEMORY_BRAIN_PROJECT_ID" not in env

    def test_tapps_mcp_entry_pins_full_brain_profile(self, tmp_path):
        """ADR-0012: the tapps-mcp entry pins TAPPS_BRAIN_PROFILE=full — the
        server backs the full tapps_memory facade, which ``coder`` would gate."""
        project = tmp_path / "demo"
        project.mkdir()
        _generate_config("cursor", project)
        data = json.loads((project / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        assert data["mcpServers"]["tapps-mcp"]["env"]["TAPPS_BRAIN_PROFILE"] == "full"

    def test_tapps_mcp_entry_pins_dual_metrics_storage(self, tmp_path):
        """TAP-3572: generated MCP config pins TAPPS_METRICS_STORAGE=dual."""
        project = tmp_path / "demo"
        project.mkdir()
        _generate_config("cursor", project)
        data = json.loads((project / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        assert data["mcpServers"]["tapps-mcp"]["env"]["TAPPS_METRICS_STORAGE"] == "dual"

    def test_docs_mcp_entry_pins_agent_brain_profile(self, tmp_path):
        """TAP-1935: the docs-mcp entry pins TAPPS_BRAIN_PROFILE=agent_brain."""
        project = tmp_path / "demo"
        project.mkdir()
        _generate_config("cursor", project, force=True, with_docs_mcp=True)
        data = json.loads((project / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        assert data["mcpServers"]["docs-mcp"]["env"]["TAPPS_BRAIN_PROFILE"] == "agent_brain"

    def test_upgrade_reemits_brain_profile(self, tmp_path):
        """TAP-1935: an existing config missing the profile gets it on upgrade,
        and the merge preserves a human-added sibling env key."""
        project = tmp_path / "demo"
        project.mkdir()
        cfg = project / ".cursor" / "mcp.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "tapps-mcp": {
                            "command": "tapps-mcp",
                            "args": ["serve"],
                            "env": {"MY_CUSTOM_KEY": "keep-me"},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        _generate_config("cursor", project, force=True, upgrade_mode=True)
        env = json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"]["tapps-mcp"]["env"]
        assert env["TAPPS_BRAIN_PROFILE"] == "full"
        assert env["TAPPS_METRICS_STORAGE"] == "dual"
        assert env["MY_CUSTOM_KEY"] == "keep-me"  # human-added key preserved

    def test_brain_env_token_is_substitution_not_literal(self, tmp_path):
        """The auth token must never be written as a literal value (commit safety)."""
        project = tmp_path / "demo"
        project.mkdir()
        _generate_config("cursor", project)
        data = json.loads((project / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        token = data["mcpServers"]["tapps-mcp"]["env"]["TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN"]
        assert token.startswith("${") and token.endswith("}")

    def test_default_env_includes_context7_substitution(self, tmp_path):
        """Default env block must include TAPPS_MCP_CONTEXT7_API_KEY via ${...}.

        Without this, consumers fall back to llms.txt for tapps_lookup_docs even
        when they have a Context7 key exported in their shell — the MCP server
        process never sees the env var because .mcp.json doesn't propagate it.
        """
        project = tmp_path / "project"
        project.mkdir()
        _generate_config("cursor", project)
        data = json.loads((project / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        env = data["mcpServers"]["tapps-mcp"]["env"]
        assert env["TAPPS_MCP_CONTEXT7_API_KEY"] == "${TAPPS_MCP_CONTEXT7_API_KEY}"

    def test_docs_via_brain_omits_context7_from_mcp_env(self, tmp_path, monkeypatch):
        """ADR-0014: consumer MCP env drops Context7 when docs_via_brain is enabled."""
        monkeypatch.setenv("TAPPS_MCP_DOCS_VIA_BRAIN", "1")
        project = tmp_path / "project"
        project.mkdir()
        _generate_config("cursor", project)
        data = json.loads((project / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        env = data["mcpServers"]["tapps-mcp"]["env"]
        assert "TAPPS_MCP_CONTEXT7_API_KEY" not in env
        assert env.get("TAPPS_MCP_DOCS_VIA_BRAIN") == "1"

    def test_context7_key_value_is_substitution_not_literal(self, tmp_path):
        """The Context7 API key must never be written as a literal value."""
        project = tmp_path / "demo"
        project.mkdir()
        _generate_config("vscode", project)
        data = json.loads((project / ".vscode" / "mcp.json").read_text(encoding="utf-8"))
        ctx7 = data["servers"]["tapps-mcp"]["env"]["TAPPS_MCP_CONTEXT7_API_KEY"]
        assert ctx7.startswith("${") and ctx7.endswith("}")

    def test_upgrade_adds_context7_key_to_existing_consumer_config(self, tmp_path):
        """tapps_upgrade must inject TAPPS_MCP_CONTEXT7_API_KEY into existing configs.

        Simulates a consumer who installed tapps-mcp before Context7 was wired
        into the default template. On upgrade, _merge_config merges old env
        (no Context7) with the new default env (has Context7), and the new
        key gets added without disturbing other custom env keys.
        """
        existing = {
            "mcpServers": {
                "tapps-mcp": {
                    "type": "stdio",
                    "command": "tapps-mcp",
                    "args": ["serve"],
                    "env": {
                        "TAPPS_MCP_PROJECT_ROOT": "${workspaceFolder}",
                        "TAPPS_MCP_MEMORY_BRAIN_HTTP_URL": "http://localhost:8080",
                        "TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN": "${TAPPS_BRAIN_AUTH_TOKEN}",
                        "CUSTOM_USER_KEY": "preserved-value",
                    },
                },
            },
        }
        merged = _merge_config(existing, "cursor", upgrade_mode=True)
        env = merged["mcpServers"]["tapps-mcp"]["env"]
        assert env["TAPPS_MCP_CONTEXT7_API_KEY"] == "${TAPPS_MCP_CONTEXT7_API_KEY}"
        # Custom user keys survive the upgrade-merge.
        assert env["CUSTOM_USER_KEY"] == "preserved-value"
        # Existing brain env is unchanged.
        assert env["TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN"] == "${TAPPS_BRAIN_AUTH_TOKEN}"

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
        assert data["mcpServers"]["tapps-mcp"]["env"]["TAPPS_MCP_PROJECT_ROOT"] == str(
            project.resolve()
        )


# ---------------------------------------------------------------------------
# run_upgrade tests
# ---------------------------------------------------------------------------


class TestNoWorkspaceFolderLiteral:
    """Regression — Claude Code CLI does not expand VS Code variables, so the
    server would treat ``${workspaceFolder}`` as a relative path and mkdir a
    phantom directory at the real project root."""

    @pytest.mark.parametrize(
        "host,config_rel,servers_key",
        [
            ("cursor", ".cursor/mcp.json", "mcpServers"),
            ("vscode", ".vscode/mcp.json", "servers"),
        ],
    )
    def test_emit_resolves_to_absolute_path(self, tmp_path, host, config_rel, servers_key):
        """Cursor and VS Code env blocks contain a resolved absolute path."""
        project = tmp_path / "myproject"
        project.mkdir()
        _generate_config(host, project)
        data = json.loads((project / config_rel).read_text(encoding="utf-8"))
        env = data[servers_key]["tapps-mcp"]["env"]
        assert env["TAPPS_MCP_PROJECT_ROOT"] == str(project.resolve())
        assert "${" not in env["TAPPS_MCP_PROJECT_ROOT"]

    def test_claude_code_keeps_dot(self, tmp_path):
        """Claude Code stays on "." — launch CWD == project root."""
        project = tmp_path / "myproject"
        project.mkdir()
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            _generate_config("claude-code", project, scope="user")
        data = json.loads((tmp_path / ".claude.json").read_text(encoding="utf-8"))
        env = data["mcpServers"]["tapps-mcp"]["env"]
        assert env["TAPPS_MCP_PROJECT_ROOT"] == "."
        assert "${" not in env["TAPPS_MCP_PROJECT_ROOT"]

    @pytest.mark.parametrize(
        "host,config_rel,servers_key",
        [
            ("cursor", ".cursor/mcp.json", "mcpServers"),
            ("vscode", ".vscode/mcp.json", "servers"),
        ],
    )
    def test_docs_mcp_env_also_absolute(self, tmp_path, host, config_rel, servers_key):
        """DOCS_MCP_PROJECT_ROOT gets the same treatment as TAPPS_MCP_PROJECT_ROOT."""
        project = tmp_path / "myproject"
        project.mkdir()
        _generate_config(host, project, with_docs_mcp=True)
        data = json.loads((project / config_rel).read_text(encoding="utf-8"))
        docs_env = data[servers_key]["docs-mcp"]["env"]
        assert docs_env["DOCS_MCP_PROJECT_ROOT"] == str(project.resolve())
        assert "${" not in docs_env["DOCS_MCP_PROJECT_ROOT"]

    def test_no_unresolved_variable_in_any_env_key(self, tmp_path):
        """No emitted env value contains an unresolved ``${...}`` other than the
        known env-var substitutions (``${TAPPS_BRAIN_AUTH_TOKEN}``,
        ``${TAPPS_MCP_CONTEXT7_API_KEY}``) which the host resolves at launch.
        """
        project = tmp_path / "myproject"
        project.mkdir()
        _generate_config("cursor", project)
        env = json.loads((project / ".cursor" / "mcp.json").read_text(encoding="utf-8"))[
            "mcpServers"
        ]["tapps-mcp"]["env"]
        for key, value in env.items():
            if key in {"TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN", "TAPPS_MCP_CONTEXT7_API_KEY"}:
                continue
            assert "${" not in str(value), f"Unresolved variable leaked in env[{key!r}]={value!r}"

    def test_upgrade_self_heals_broken_workspacefolder(self, tmp_path):
        """An existing .mcp.json with ``${workspaceFolder}`` gets rewritten on
        re-merge — the new entry overlays the old env so the broken value is
        replaced with the resolved absolute path.
        """
        project = tmp_path / "demo"
        cursor_dir = project / ".cursor"
        cursor_dir.mkdir(parents=True)
        broken = {
            "mcpServers": {
                "tapps-mcp": {
                    "type": "stdio",
                    "command": "tapps-mcp",
                    "args": ["serve"],
                    "env": {
                        "TAPPS_MCP_PROJECT_ROOT": "${workspaceFolder}",
                        "CUSTOM_KEY": "keep-me",
                    },
                },
            },
        }
        (cursor_dir / "mcp.json").write_text(json.dumps(broken), encoding="utf-8")
        _generate_config("cursor", project, force=True, upgrade_mode=True)
        env = json.loads((cursor_dir / "mcp.json").read_text(encoding="utf-8"))["mcpServers"][
            "tapps-mcp"
        ]["env"]
        assert env["TAPPS_MCP_PROJECT_ROOT"] == str(project.resolve())
        assert env["CUSTOM_KEY"] == "keep-me"
