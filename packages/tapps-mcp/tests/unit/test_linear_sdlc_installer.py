"""Tests for the Linear SDLC installer (TAP-411)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_mcp.pipeline.linear_sdlc import LinearSDLCConfig
from tapps_mcp.pipeline.linear_sdlc.installer import (
    SKILL_INSTALL_PATH,
    UPSTREAM_SKILL_REPO,
    install_linear_sdlc,
)
from tapps_mcp.pipeline.linear_sdlc.renderer import TEMPLATE_PATHS


@pytest.fixture
def config() -> LinearSDLCConfig:
    return LinearSDLCConfig(issue_prefix="TAP", team_id="team-uuid", project_id="proj-slug")


class TestRendersAllTemplates:
    def test_writes_every_path_in_template_paths(
        self,
        tmp_path: Path,
        config: LinearSDLCConfig,
    ) -> None:
        with patch(
            "tapps_mcp.pipeline.linear_sdlc.installer.shutil.which",
            return_value=None,
        ):
            result = install_linear_sdlc(tmp_path, config)
        for relative in TEMPLATE_PATHS:
            assert (tmp_path / relative).exists(), f"missing {relative}"
        assert sorted(result["files_written"]) == sorted(TEMPLATE_PATHS)

    def test_hook_scripts_marked_executable(
        self,
        tmp_path: Path,
        config: LinearSDLCConfig,
    ) -> None:
        with patch(
            "tapps_mcp.pipeline.linear_sdlc.installer.shutil.which",
            return_value=None,
        ):
            install_linear_sdlc(tmp_path, config)
        for relative in TEMPLATE_PATHS:
            if relative.endswith(".sh"):
                mode = (tmp_path / relative).stat().st_mode
                assert mode & 0o111, f"{relative} not executable"

    def test_template_substitutions_applied(
        self,
        tmp_path: Path,
        config: LinearSDLCConfig,
    ) -> None:
        with patch(
            "tapps_mcp.pipeline.linear_sdlc.installer.shutil.which",
            return_value=None,
        ):
            install_linear_sdlc(tmp_path, config)
        workflow = (tmp_path / "docs/linear-sdlc/guides/WORKFLOW.md").read_text(encoding="utf-8")
        assert "TAP" in workflow
        assert "{{PREFIX}}" not in workflow


class TestSkillCloneBehavior:
    def test_invokes_git_clone_when_skill_absent(
        self,
        tmp_path: Path,
        config: LinearSDLCConfig,
    ) -> None:
        captured: dict[str, list[str]] = {}

        def fake_run(cmd: list[str], **_: object) -> object:
            captured["cmd"] = cmd
            (tmp_path / SKILL_INSTALL_PATH / ".git").mkdir(parents=True, exist_ok=True)

            class _Result:
                returncode = 0
                stdout = b""
                stderr = b""

            return _Result()

        with (
            patch(
                "tapps_mcp.pipeline.linear_sdlc.installer.shutil.which",
                return_value="/usr/bin/git",
            ),
            patch(
                "tapps_mcp.pipeline.linear_sdlc.installer.subprocess.run",
                side_effect=fake_run,
            ),
        ):
            result = install_linear_sdlc(tmp_path, config)

        assert result["skill_cloned"] is True
        assert "clone" in captured["cmd"]
        assert UPSTREAM_SKILL_REPO in captured["cmd"]

    def test_idempotent_when_skill_already_present(
        self,
        tmp_path: Path,
        config: LinearSDLCConfig,
    ) -> None:
        (tmp_path / SKILL_INSTALL_PATH / ".git").mkdir(parents=True)
        with patch(
            "tapps_mcp.pipeline.linear_sdlc.installer.subprocess.run"
        ) as mock_run:
            result = install_linear_sdlc(tmp_path, config)
        assert result["skill_cloned"] is False
        assert "already cloned" in result["skipped_reason"]
        mock_run.assert_not_called()

    def test_skips_clone_when_git_missing(
        self,
        tmp_path: Path,
        config: LinearSDLCConfig,
    ) -> None:
        with patch(
            "tapps_mcp.pipeline.linear_sdlc.installer.shutil.which",
            return_value=None,
        ):
            result = install_linear_sdlc(tmp_path, config)
        assert result["skill_cloned"] is False
        assert "git not on PATH" in result["skipped_reason"]


class TestDryRunAndContentReturn:
    def test_dry_run_writes_nothing(
        self,
        tmp_path: Path,
        config: LinearSDLCConfig,
    ) -> None:
        result = install_linear_sdlc(tmp_path, config, dry_run=True)
        assert result["files_written"] == list(TEMPLATE_PATHS)
        assert result["skipped_reason"] == "dry_run"
        for relative in TEMPLATE_PATHS:
            assert not (tmp_path / relative).exists()

    def test_content_return_emits_dict_without_writing(
        self,
        tmp_path: Path,
        config: LinearSDLCConfig,
    ) -> None:
        result = install_linear_sdlc(tmp_path, config, content_return=True)
        assert "content" in result
        assert sorted(result["content"].keys()) == sorted(TEMPLATE_PATHS)
        assert result["skill_cloned"] is False
        for relative in TEMPLATE_PATHS:
            assert not (tmp_path / relative).exists()
