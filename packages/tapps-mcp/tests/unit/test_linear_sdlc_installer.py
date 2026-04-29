"""Tests for the Linear SDLC installer (TAP-411)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_mcp.pipeline.linear_sdlc import LinearSDLCConfig
from tapps_mcp.pipeline.linear_sdlc.installer import (
    SKILL_INSTALL_PATH,
    UPSTREAM_SKILL_REPO,
    _detect_prefix_from_installed,
    install_linear_sdlc,
    refresh_linear_sdlc,
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


class TestPrefixDetection:
    """Verify _detect_prefix_from_installed."""

    def test_detects_prefix_from_workflow(
        self,
        tmp_path: Path,
        config: LinearSDLCConfig,
    ) -> None:
        with patch(
            "tapps_mcp.pipeline.linear_sdlc.installer.shutil.which",
            return_value=None,
        ):
            install_linear_sdlc(tmp_path, config)
        assert _detect_prefix_from_installed(tmp_path) == "TAP"

    def test_returns_tap_when_file_absent(self, tmp_path: Path) -> None:
        assert _detect_prefix_from_installed(tmp_path) == "TAP"


class TestRefreshLinearSDLC:
    """Verify refresh_linear_sdlc round-trip behaviour (TAP-417)."""

    def _install(self, tmp_path: Path, config: LinearSDLCConfig) -> None:
        with patch(
            "tapps_mcp.pipeline.linear_sdlc.installer.shutil.which",
            return_value=None,
        ):
            install_linear_sdlc(tmp_path, config)

    def test_unchanged_when_content_matches(
        self,
        tmp_path: Path,
        config: LinearSDLCConfig,
    ) -> None:
        self._install(tmp_path, config)
        result = refresh_linear_sdlc(tmp_path, config)
        assert result["refreshed"] == []
        assert sorted(result["unchanged"]) == sorted(TEMPLATE_PATHS)
        assert result["errors"] == []
        assert result["backup_dir"] == ""

    def test_refreshed_when_file_is_stale(
        self,
        tmp_path: Path,
        config: LinearSDLCConfig,
    ) -> None:
        self._install(tmp_path, config)
        stale_path = tmp_path / TEMPLATE_PATHS[0]
        stale_path.write_text("# old content\n", encoding="utf-8")
        result = refresh_linear_sdlc(tmp_path, config)
        assert TEMPLATE_PATHS[0] in result["refreshed"]
        assert TEMPLATE_PATHS[0] not in result["unchanged"]
        assert result["errors"] == []

    def test_backup_written_before_overwrite(
        self,
        tmp_path: Path,
        config: LinearSDLCConfig,
    ) -> None:
        self._install(tmp_path, config)
        stale_path = tmp_path / TEMPLATE_PATHS[0]
        old_body = "# backup me\n"
        stale_path.write_text(old_body, encoding="utf-8")
        result = refresh_linear_sdlc(tmp_path, config)
        backup_dir = tmp_path / result["backup_dir"]
        assert backup_dir.is_dir()
        backed_up = list(backup_dir.iterdir())
        assert len(backed_up) == 1
        assert backed_up[0].read_text(encoding="utf-8") == old_body

    def test_dry_run_reports_stale_without_writing(
        self,
        tmp_path: Path,
        config: LinearSDLCConfig,
    ) -> None:
        self._install(tmp_path, config)
        stale_path = tmp_path / TEMPLATE_PATHS[0]
        stale_path.write_text("# old\n", encoding="utf-8")
        result = refresh_linear_sdlc(tmp_path, config, dry_run=True)
        assert TEMPLATE_PATHS[0] in result["refreshed"]
        assert result["backup_dir"] == ""
        assert stale_path.read_text(encoding="utf-8") == "# old\n"

    def test_refresh_missing_file_creates_it(
        self,
        tmp_path: Path,
        config: LinearSDLCConfig,
    ) -> None:
        self._install(tmp_path, config)
        missing = tmp_path / TEMPLATE_PATHS[-1]
        missing.unlink()
        result = refresh_linear_sdlc(tmp_path, config)
        assert TEMPLATE_PATHS[-1] in result["refreshed"]
        assert missing.exists()

    def test_config_none_uses_detected_prefix(
        self,
        tmp_path: Path,
        config: LinearSDLCConfig,
    ) -> None:
        self._install(tmp_path, config)
        result = refresh_linear_sdlc(tmp_path, config=None)
        assert result["refreshed"] == []
