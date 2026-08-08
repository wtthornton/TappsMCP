"""Tests for distribution.setup_launch — uv detection and launch-command resolution."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from tapps_mcp.cli import main
from tapps_mcp.distribution.setup_generator import (
    _build_nlt_launch,
    _build_uv_run_tapps_launch,
    _detect_uv_context,
    _generate_config,
    _should_include_docs_mcp,
    _should_use_uv_launch,
    is_tapps_mcp_dev_monorepo,
    is_tapps_mcp_package_layout,
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


def _cursor_wrapper_path(project: Path) -> str:
    return str((project / ".cursor" / "bin" / "tapps-mcp-serve.sh").resolve())


class TestEpic80ConsumerInit:
    """Regression tests for Epic 80 (hooks, MCP merge, package-root guard)."""

    def test_is_tapps_mcp_package_layout(self, tmp_path):
        root = tmp_path / "r" / "packages" / "tapps-mcp"
        root.mkdir(parents=True)
        assert is_tapps_mcp_package_layout(root) is True
        assert is_tapps_mcp_package_layout(tmp_path / "other") is False

    def test_is_tapps_mcp_dev_monorepo(self, tmp_path):
        root = tmp_path / "tapps-mcp"
        (root / "packages" / "tapps-mcp" / "src" / "tapps_mcp").mkdir(parents=True)
        (root / "packages" / "docs-mcp").mkdir(parents=True)
        (root / "pyproject.toml").write_text("[project]\nname='tapps-mcp'\n", encoding="utf-8")
        assert is_tapps_mcp_dev_monorepo(root) is True
        assert is_tapps_mcp_dev_monorepo(tmp_path / "consumer-app") is False

    def test_resolve_global_cli_prefers_shim_over_uv_tool_venv(self, tmp_path, monkeypatch) -> None:
        shim = tmp_path / ".local" / "bin" / "tapps-mcp"
        shim.parent.mkdir(parents=True)
        shim.write_text("#!/bin/sh\n", encoding="utf-8")
        monkeypatch.setattr(
            "tapps_mcp.distribution.setup_generator.Path.home",
            lambda: tmp_path,
        )
        monkeypatch.setattr(
            "tapps_mcp.distribution.setup_generator.shutil.which",
            lambda name: str(tmp_path / ".local/share/uv/tools/tapps-mcp/bin" / name),
        )
        from tapps_mcp.distribution.setup_generator import _resolve_global_cli

        assert _resolve_global_cli("tapps-mcp") == str(shim)

    def test_resolve_global_cli_rejects_uv_tool_venv_without_shim(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "tapps_mcp.distribution.setup_generator.Path.home",
            lambda: tmp_path,
        )
        monkeypatch.setattr(
            "tapps_mcp.distribution.setup_generator.shutil.which",
            lambda name: str(tmp_path / ".local/share/uv/tools/tapps-mcp/bin" / name),
        )
        from tapps_mcp.distribution.setup_generator import _resolve_global_cli

        assert _resolve_global_cli("tapps-mcp") is None

    def test_dev_monorepo_nlt_launch_prefers_blue_green_binary(self, tmp_path, monkeypatch) -> None:
        """When blue/green current exists, dev wrappers exec that release binary."""
        root = tmp_path / "tapps-mcp"
        (root / "packages" / "tapps-mcp" / "src" / "tapps_mcp").mkdir(parents=True)
        (root / "packages" / "docs-mcp").mkdir(parents=True)
        (root / "pyproject.toml").write_text("[project]\nname='tapps-mcp'\n", encoding="utf-8")
        bg_home = tmp_path / "bg-home"
        release = bg_home / "releases" / "3.12.35-deadbeef" / "bin"
        release.mkdir(parents=True)
        (release / "tapps-mcp").write_text("#!/bin/sh\n", encoding="utf-8")
        current = bg_home / "current"
        current.symlink_to(release.parent, target_is_directory=True)
        monkeypatch.setattr("tapps_mcp.distribution.blue_green.CURRENT_LINK", current)
        command, args = _build_nlt_launch("nlt-build", None, project_root=root)
        assert command == str(current / "bin" / "tapps-mcp")
        assert args[:2] == ["serve", "--profile"]
        assert "nlt-build" in args

    def test_dev_monorepo_nlt_launch_prefers_global_binary(self, tmp_path, monkeypatch) -> None:
        """Without blue/green current, the dev wrapper execs the deployed global binary."""
        root = tmp_path / "tapps-mcp"
        (root / "packages" / "tapps-mcp" / "src" / "tapps_mcp").mkdir(parents=True)
        (root / "packages" / "docs-mcp").mkdir(parents=True)
        (root / "pyproject.toml").write_text("[project]\nname='tapps-mcp'\n", encoding="utf-8")
        shim = Path.home() / ".local" / "bin" / "tapps-mcp"
        shim.parent.mkdir(parents=True, exist_ok=True)
        shim.write_text("#!/bin/sh\n", encoding="utf-8")
        monkeypatch.setattr(
            "tapps_mcp.distribution.blue_green.CURRENT_LINK",
            tmp_path / "missing-current",
        )
        command, args = _build_nlt_launch("nlt-build", None, project_root=root)
        assert command == str(shim)
        assert args[:2] == ["serve", "--profile"]
        assert "nlt-build" in args
        assert "uv" not in command

    def test_dev_monorepo_nlt_launch_falls_back_to_uv_run(self, tmp_path, monkeypatch) -> None:
        """Without a global CLI (fresh checkout pre-deploy), fall back to ``uv run``."""
        root = tmp_path / "tapps-mcp"
        (root / "packages" / "tapps-mcp" / "src" / "tapps_mcp").mkdir(parents=True)
        (root / "packages" / "docs-mcp").mkdir(parents=True)
        (root / "pyproject.toml").write_text("[project]\nname='tapps-mcp'\n", encoding="utf-8")
        monkeypatch.setattr(
            "tapps_mcp.distribution.blue_green.CURRENT_LINK",
            tmp_path / "missing-current",
        )
        monkeypatch.setattr(
            "tapps_mcp.distribution.setup_generator.shutil.which",
            lambda name: None,
        )
        command, args = _build_nlt_launch("nlt-build", None, project_root=root)
        assert command == "uv"
        assert args[:3] == ["run", "--directory", str(root.resolve())]
        assert "tapps-mcp" in args
        assert "serve" in args
        assert "--profile" in args

    def test_merge_preserves_extra_env_keys(self, tmp_path):
        """User-managed env keys (not in the default set) survive merge.

        Note: keys that ARE in the default set (e.g. TAPPS_MCP_CONTEXT7_API_KEY)
        get normalized to ${VAR} interpolation on upgrade for commit safety —
        see ``test_upgrade_normalizes_literal_context7_key_to_substitution`` below.
        """
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
                        "OPENAI_API_KEY": "user-managed-secret",
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
        assert env.get("OPENAI_API_KEY") == "user-managed-secret"

    def test_upgrade_normalizes_literal_context7_key_to_substitution(self, tmp_path):
        """A pre-existing plaintext TAPPS_MCP_CONTEXT7_API_KEY gets replaced
        with ${TAPPS_MCP_CONTEXT7_API_KEY} on upgrade — commit safety.

        Consumers who had hardcoded their key in .mcp.json (a security smell)
        get auto-migrated to env-var interpolation. The actual key value must
        come from the shell env going forward.
        """
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
                        "TAPPS_MCP_CONTEXT7_API_KEY": "ctx7sk-literal-secret-leaked",
                    },
                },
            },
        }
        (cursor_dir / "mcp.json").write_text(json.dumps(existing), encoding="utf-8")
        with patch(
            "tapps_mcp.distribution.setup_generator.shutil.which", return_value="/bin/tapps-mcp"
        ):
            _generate_config("cursor", project, force=True, upgrade_mode=True)
        data = json.loads((cursor_dir / "mcp.json").read_text(encoding="utf-8"))
        ctx7 = data["mcpServers"]["tapps-mcp"]["env"]["TAPPS_MCP_CONTEXT7_API_KEY"]
        assert ctx7 == "${TAPPS_MCP_CONTEXT7_API_KEY}"

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
        assert data["mcpServers"]["tapps-mcp"]["command"] == _cursor_wrapper_path(project)

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

    def test_global_clis_emit_direct_commands(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        (project / "pyproject.toml").write_text(
            '[project]\nname = "demo"\n[project.optional-dependencies]\nmcp = ["tapps-mcp"]\n',
            encoding="utf-8",
        )
        (project / "uv.lock").write_text("", encoding="utf-8")

        def _which(cmd: str) -> str | None:
            if cmd in ("tapps-mcp", "docsmcp"):
                return f"/bin/{cmd}"
            return None

        with patch("tapps_mcp.distribution.setup_generator.shutil.which", side_effect=_which):
            _generate_config("cursor", project, force=True)
        data = json.loads((project / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        assert data["mcpServers"]["tapps-mcp"]["command"] == _cursor_wrapper_path(project)
        assert data["mcpServers"]["tapps-mcp"]["args"] == []
        assert data["mcpServers"]["docs-mcp"]["command"] == "/bin/docsmcp"
        assert data["mcpServers"]["docs-mcp"]["args"] == ["serve"]

    def test_should_include_docs_mcp_when_binary_on_path(self) -> None:
        with patch(
            "tapps_mcp.distribution.setup_generator.shutil.which",
            return_value="/bin/docsmcp",
        ):
            assert _should_include_docs_mcp(False) is True

    def test_upgrade_replaces_uv_launch_with_global_binary(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        config = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "uv",
                    "args": ["run", "--no-sync", "tapps-mcp", "serve"],
                    "env": {"TAPPS_MCP_PROJECT_ROOT": str(project)},
                },
                "docs-mcp": {
                    "command": "uv",
                    "args": ["run", "--no-sync", "docsmcp", "serve"],
                    "env": {"DOCS_MCP_PROJECT_ROOT": str(project)},
                },
            }
        }
        (project / ".cursor").mkdir()
        (project / ".cursor" / "mcp.json").write_text(
            json.dumps(config, indent=2),
            encoding="utf-8",
        )

        def _which(cmd: str) -> str | None:
            if cmd in ("tapps-mcp", "docsmcp"):
                return f"/bin/{cmd}"
            return None

        with patch("tapps_mcp.distribution.setup_generator.shutil.which", side_effect=_which):
            _generate_config("cursor", project, force=True, upgrade_mode=True)
        data = json.loads((project / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        assert data["mcpServers"]["tapps-mcp"]["command"] == _cursor_wrapper_path(project)
        assert data["mcpServers"]["docs-mcp"]["command"] == "/bin/docsmcp"


# ---------------------------------------------------------------------------
# Story 47.5: Upgrade command has --scope flag
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

    def test_should_use_uv_launch_prefers_global_binary(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\n[project.optional-dependencies]\nmcp = ["tapps-mcp"]\n',
            encoding="utf-8",
        )
        (tmp_path / "uv.lock").write_text("", encoding="utf-8")
        with patch(
            "tapps_mcp.distribution.setup_generator.shutil.which",
            return_value="/bin/tapps-mcp",
        ):
            use_uv, _, _ = _should_use_uv_launch(tmp_path, uv_mode=None)
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
        assert entry["command"] == _cursor_wrapper_path(project)
        assert entry["args"] == []
        script = (project / ".cursor" / "bin" / "tapps-mcp-serve.sh").read_text(encoding="utf-8")
        assert "uv" in script
        assert "--extra" in script

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


# ---------------------------------------------------------------------------
# TAP-2199: never emit literal ${workspaceFolder} into .mcp.json
# ---------------------------------------------------------------------------
