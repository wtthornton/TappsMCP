"""Tests for distribution.setup_wrappers — generated stdio wrapper scripts."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_mcp.distribution.setup_generator import (
    _generate_config,
    _nlt_profile_from_serve_args,
    _parse_cursor_wrapper_launch,
    _render_cursor_mcp_wrapper_script,
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


class TestCursorMcpWrapper:
    """TAP-3255: Cursor wrapper script sources .env before spawning tapps-mcp."""

    def test_wrapper_maps_brain_token_and_is_executable(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        (project / ".env").write_text("TAPPS_BRAIN_AUTH_TOKEN=from-env\n", encoding="utf-8")
        with patch(
            "tapps_mcp.distribution.setup_generator.shutil.which", return_value="/bin/tapps-mcp"
        ):
            _generate_config("cursor", project, force=True)
        wrapper = project / ".cursor" / "bin" / "tapps-mcp-serve.sh"
        assert wrapper.exists()
        assert os.access(wrapper, os.X_OK)
        text = wrapper.read_text(encoding="utf-8")
        assert "source .env" in text
        assert ".tapps-operator.env" in text
        assert "TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN" in text
        assert "TAPPS_BRAIN_AUTH_TOKEN" in text
        assert "${TAPPS_BRAIN_AUTH_TOKEN}" in text  # placeholder treated as unset
        assert "set +u" in text  # .env may reference unset vars
        assert ".local/bin" in text  # PATH export for GUI-launched Cursor

    def test_nlt_profile_from_serve_args(self) -> None:
        assert _nlt_profile_from_serve_args(["serve", "--profile", "nlt-build"]) == "nlt-build"
        assert _nlt_profile_from_serve_args(["serve"]) is None

    def test_cursor_wrapper_reaps_stale_profile_before_exec(self) -> None:
        """Wrappers do not profile-global reap (unsafe with multiple Cursor windows)."""
        script = _render_cursor_mcp_wrapper_script(
            "/home/user/.local/bin/tapps-mcp",
            ["serve", "--profile", "nlt-build"],
        )
        assert "serve --profile nlt-build" in script
        assert "Reaping stale serve PIDs" not in script
        assert "_blue_green=" in script
        assert 'exec "$_blue_green"' in script

    def test_cursor_wrapper_without_nlt_profile_skips_reap(self) -> None:
        script = _render_cursor_mcp_wrapper_script(
            "uv",
            ["run", "--extra", "mcp", "--no-sync", "tapps-mcp", "serve"],
        )
        assert "Reaping stale serve PIDs" not in script

    def test_nlt_wrapper_regenerates_global_launch_not_stale_venv(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Re-init must not recycle a stale .venv path embedded in an old NLT wrapper."""
        from tapps_mcp.distribution.setup_generator import (
            _apply_cursor_launch_wrapper,
            _parse_cursor_wrapper_launch,
        )

        project = tmp_path / "proj"
        (project / ".cursor" / "bin").mkdir(parents=True)
        stale = project / ".cursor" / "bin" / "nlt-build-serve.sh"
        stale.write_text(
            _render_cursor_mcp_wrapper_script(
                str(project / ".venv" / "bin" / "tapps-mcp"),
                ["serve", "--profile", "nlt-build"],
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "tapps_mcp.distribution.setup_generator.shutil.which",
            lambda name: "/home/user/.local/bin/tapps-mcp" if name == "tapps-mcp" else None,
        )
        entry: dict[str, object] = {"command": str(stale), "args": []}
        _apply_cursor_launch_wrapper(entry, project, server_id="nlt-build")
        parsed = _parse_cursor_wrapper_launch(stale)
        assert parsed is not None
        assert parsed[0] == "/home/user/.local/bin/tapps-mcp"
        assert ".venv" not in parsed[0]

    def test_parse_cursor_wrapper_launch_extracts_exec_line(self, tmp_path: Path) -> None:
        wrapper = tmp_path / "tapps-mcp-serve.sh"
        wrapper.write_text(
            _render_cursor_mcp_wrapper_script(
                "uv",
                ["run", "--extra", "mcp", "--no-sync", "tapps-mcp", "serve"],
            ),
            encoding="utf-8",
        )
        assert _parse_cursor_wrapper_launch(wrapper) == (
            "uv",
            ["run", "--extra", "mcp", "--no-sync", "tapps-mcp", "serve"],
        )

    def test_parse_cursor_wrapper_launch_missing_file(self, tmp_path: Path) -> None:
        assert _parse_cursor_wrapper_launch(tmp_path / "missing.sh") is None

    def test_upgrade_preserves_uv_launch_in_existing_wrapper(self, tmp_path):
        """Re-upgrade must not replace uv run embedded in an existing wrapper script."""
        project = tmp_path / "project"
        project.mkdir()
        uv_launch = ("uv", ["run", "--extra", "mcp", "--no-sync", "tapps-mcp", "serve"])
        _generate_config("cursor", project, uv_launch=uv_launch, force=True)
        wrapper = project / ".cursor" / "bin" / "tapps-mcp-serve.sh"
        assert "uv" in wrapper.read_text(encoding="utf-8")
        assert "--extra" in wrapper.read_text(encoding="utf-8")

        def _which(cmd: str) -> str | None:
            return None  # no global tapps-mcp — preserve wrapper launch on upgrade

        with patch("tapps_mcp.distribution.setup_generator.shutil.which", side_effect=_which):
            _generate_config("cursor", project, force=True, upgrade_mode=True)

        script = wrapper.read_text(encoding="utf-8")
        assert "uv" in script
        assert "--extra" in script
        assert "mcp" in script


# ---------------------------------------------------------------------------
# Config merging tests
# ---------------------------------------------------------------------------
