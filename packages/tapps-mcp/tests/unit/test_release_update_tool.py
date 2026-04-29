"""Tests for tapps_mcp.server_release_tools and tools.release_update."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tapps_mcp.tools.release_update import (
    build_release_content,
    source_changelog_section,
    source_git_log,
)


# ---------------------------------------------------------------------------
# source_changelog_section
# ---------------------------------------------------------------------------


class TestSourceChangelogSection:
    def test_returns_none_when_no_file(self, tmp_path: Path) -> None:
        assert source_changelog_section(tmp_path, "1.5.0") is None

    def test_extracts_version_section(self, tmp_path: Path) -> None:
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n## [1.5.0] - 2026-04-29\n\n- Added feature\n\n## [1.4.2] - 2026-04-01\n\n- Old stuff\n",
            encoding="utf-8",
        )
        result = source_changelog_section(tmp_path, "1.5.0")
        assert result is not None
        assert "Added feature" in result
        assert "Old stuff" not in result

    def test_returns_none_when_version_not_found(self, tmp_path: Path) -> None:
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text("## [1.4.2] - 2026-04-01\n\n- Old stuff\n", encoding="utf-8")
        assert source_changelog_section(tmp_path, "9.9.9") is None

    def test_v_prefix_stripped(self, tmp_path: Path) -> None:
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text("## [1.5.0] - 2026-04-29\n\n- Fixed thing\n", encoding="utf-8")
        result = source_changelog_section(tmp_path, "v1.5.0")
        assert result is not None
        assert "Fixed thing" in result


# ---------------------------------------------------------------------------
# source_git_log
# ---------------------------------------------------------------------------


class TestSourceGitLog:
    def test_returns_empty_on_git_failure(self, tmp_path: Path) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="fatal: not a git repo")
            highlights, issues = source_git_log(tmp_path, "1.4.2")
        assert highlights == []
        assert issues == []

    def test_parses_feat_commits(self, tmp_path: Path) -> None:
        git_output = "abc1234 feat(tools): add tapps_release_update (TAP-1112)\ndef5678 fix: edge case in scorer\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=git_output, stderr="")
            highlights, _ = source_git_log(tmp_path, "1.4.2")
        assert any("add tapps_release_update" in h for h in highlights)

    def test_scrapes_tap_refs(self, tmp_path: Path) -> None:
        git_output = "abc1234 feat: something (TAP-1112)\ndef5678 fix: other thing (TAP-999)\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=git_output, stderr="")
            _, issues = source_git_log(tmp_path, "1.4.2")
        tap_ids = [i.split(":")[0] for i in issues]
        assert "TAP-1112" in tap_ids
        assert "TAP-999" in tap_ids

    def test_deduplicates_tap_refs(self, tmp_path: Path) -> None:
        git_output = "abc1234 feat: thing TAP-1112\ndef5678 fix: same TAP-1112\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=git_output, stderr="")
            _, issues = source_git_log(tmp_path, "1.4.2")
        tap_ids = [i.split(":")[0] for i in issues]
        assert tap_ids.count("TAP-1112") == 1

    def test_timeout_returns_empty(self, tmp_path: Path) -> None:
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10)):
            highlights, issues = source_git_log(tmp_path, "1.4.2")
        assert highlights == []
        assert issues == []


# ---------------------------------------------------------------------------
# tapps_release_update handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTappsReleaseUpdateHandler:
    async def test_missing_version_returns_error(self) -> None:
        from tapps_mcp.server_release_tools import tapps_release_update

        result = await tapps_release_update(version="", prev_version="1.4.2")
        assert result["success"] is False
        assert "version" in result["error"]["message"].lower()

    async def test_missing_prev_version_returns_error(self) -> None:
        from tapps_mcp.server_release_tools import tapps_release_update

        result = await tapps_release_update(version="1.5.0", prev_version="")
        assert result["success"] is False
        assert "prev_version" in result["error"]["message"].lower()

    async def test_dry_run_returns_body(self, tmp_path: Path) -> None:
        from tapps_mcp.server_release_tools import tapps_release_update

        with (
            patch("tapps_core.config.settings.load_settings") as mock_settings,
            patch("tapps_mcp.server_release_tools._record_call"),
        ):
            mock_settings.return_value = MagicMock(project_root=str(tmp_path))
            result = await tapps_release_update(
                version="1.5.0",
                prev_version="1.4.2",
                dry_run=True,
            )

        assert result["success"] is True
        data = result["data"]
        assert "body" in data
        assert "## Release v1.5.0" in data["body"]
        assert data["dry_run"] is True

    async def test_includes_team_and_project_in_response(self, tmp_path: Path) -> None:
        from tapps_mcp.server_release_tools import tapps_release_update

        with (
            patch("tapps_core.config.settings.load_settings") as mock_settings,
            patch("tapps_mcp.server_release_tools._record_call"),
        ):
            mock_settings.return_value = MagicMock(project_root=str(tmp_path))
            result = await tapps_release_update(
                version="1.5.0",
                prev_version="1.4.2",
                team="TappsCodingAgents",
                project="TappsMCP Platform",
                dry_run=True,
            )

        assert result["success"] is True
        assert result["data"]["team"] == "TappsCodingAgents"
        assert result["data"]["project"] == "TappsMCP Platform"

    async def test_document_title_format(self, tmp_path: Path) -> None:
        import re

        from tapps_mcp.server_release_tools import tapps_release_update

        with (
            patch("tapps_core.config.settings.load_settings") as mock_settings,
            patch("tapps_mcp.server_release_tools._record_call"),
        ):
            mock_settings.return_value = MagicMock(project_root=str(tmp_path))
            result = await tapps_release_update(version="1.5.0", prev_version="1.4.2", dry_run=True)

        title = result["data"]["document_title"]
        assert re.match(r"Release v1\.5\.0 — \d{4}-\d{2}-\d{2}", title)

    async def test_source_field_git_log_when_no_changelog(self, tmp_path: Path) -> None:
        from tapps_mcp.server_release_tools import tapps_release_update

        with (
            patch("tapps_core.config.settings.load_settings") as mock_settings,
            patch("tapps_mcp.server_release_tools._record_call"),
            patch("subprocess.run") as mock_run,
        ):
            mock_settings.return_value = MagicMock(project_root=str(tmp_path))
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = await tapps_release_update(version="1.5.0", prev_version="1.4.2", dry_run=True)

        assert result["data"]["source"] == "git_log"

    async def test_source_field_changelog_when_present(self, tmp_path: Path) -> None:
        from tapps_mcp.server_release_tools import tapps_release_update

        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(
            "## [1.5.0] - 2026-04-29\n\n- Added feature\n\n## [1.4.2] - 2026-04-01\n\n- Old\n",
            encoding="utf-8",
        )

        with (
            patch("tapps_core.config.settings.load_settings") as mock_settings,
            patch("tapps_mcp.server_release_tools._record_call"),
        ):
            mock_settings.return_value = MagicMock(project_root=str(tmp_path))
            result = await tapps_release_update(version="1.5.0", prev_version="1.4.2", dry_run=True)

        assert result["data"]["source"] == "changelog"
