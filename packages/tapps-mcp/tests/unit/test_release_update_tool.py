"""Tests for tapps_mcp.server_release_tools and tools.release_update."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tapps_mcp.tools.release_update import (
    _parse_changelog_bullets,
    source_changelog_section,
    source_git_log,
)

# ---------------------------------------------------------------------------
# _parse_changelog_bullets
# ---------------------------------------------------------------------------


class TestParseChangelogBullets:
    """Unit tests for the multi-line bullet parser (TAP-2056)."""

    def test_single_line_bullet(self) -> None:
        text = "- Fixed a bug\n"
        assert _parse_changelog_bullets(text) == ["Fixed a bug"]

    def test_multiple_single_line_bullets(self) -> None:
        text = "- First fix\n- Second fix\n- Third fix\n"
        result = _parse_changelog_bullets(text)
        assert result == ["First fix", "Second fix", "Third fix"]

    def test_multiline_bullet_joins_continuation(self) -> None:
        """Continuation lines (indented 2+ spaces) are joined to the parent bullet."""
        text = "- **MatchType.CLOSE confirmations now**: First sentence\n  continued text that wraps\n"
        result = _parse_changelog_bullets(text)
        assert len(result) == 1
        assert "First sentence" in result[0]
        # Content from the 2nd physical line must appear
        assert "continued text that wraps" in result[0]

    def test_multiline_and_singleline_mixed(self) -> None:
        text = (
            "- **Feature A**: Bold header\n"
            "  second line of A\n"
            "- Simple bullet B\n"
            "- **Feature C**: Another header\n"
            "  second line of C\n"
            "  third line of C\n"
        )
        result = _parse_changelog_bullets(text)
        assert len(result) == 3
        assert "second line of A" in result[0]
        assert result[1] == "Simple bullet B"
        assert "second line of C" in result[2]
        assert "third line of C" in result[2]

    def test_empty_line_terminates_bullet(self) -> None:
        text = "- First\n\n- Second\n"
        result = _parse_changelog_bullets(text)
        assert result == ["First", "Second"]

    def test_section_header_terminates_bullet(self) -> None:
        text = "- Bullet text\n## Next Section\n- New bullet\n"
        result = _parse_changelog_bullets(text)
        assert "Bullet text" in result[0]
        assert "New bullet" in result[1]

    def test_nine_bullets_agentforge_shape(self) -> None:
        """Simulates the AgentForge v4.9.0 reproducer from TAP-2056."""
        section = "\n".join([
            "## [4.9.0] - 2026-05-17",
            "",
            *[
                line
                for i in range(1, 10)
                for line in (
                    f"- **Feature {i}**: First sentence of bullet {i}",
                    f"  continuation of bullet {i}",
                )
            ],
        ])
        result = _parse_changelog_bullets(section)
        assert len(result) == 9
        for i, bullet in enumerate(result, 1):
            assert f"continuation of bullet {i}" in bullet, (
                f"Bullet {i} missing its continuation line: {bullet!r}"
            )

    def test_no_false_regression_on_lone_dash(self) -> None:
        """Lone dashes (section separators) are skipped without error."""
        text = "- Real bullet\n-\n- Another bullet\n"
        result = _parse_changelog_bullets(text)
        assert "Real bullet" in result
        assert "Another bullet" in result
        assert "" not in result  # no empty strings from lone dash


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
        from tapps_mcp.tools.subprocess_utils import CommandResult

        with patch("tapps_mcp.tools.release_update.run_command") as mock_run:
            mock_run.return_value = CommandResult(
                returncode=1,
                stdout="",
                stderr="fatal: not a git repo",
                command=["git"],
            )
            highlights, issues = source_git_log(tmp_path, "1.4.2")
        assert highlights == []
        assert issues == []

    def test_parses_feat_commits(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.subprocess_utils import CommandResult

        git_output = "abc1234 feat(tools): add tapps_release_update (TAP-1112)\ndef5678 fix: edge case in scorer\n"
        with patch("tapps_mcp.tools.release_update.run_command") as mock_run:
            mock_run.return_value = CommandResult(
                returncode=0,
                stdout=git_output,
                stderr="",
                command=["git"],
            )
            highlights, _ = source_git_log(tmp_path, "1.4.2")
        assert any("add tapps_release_update" in h for h in highlights)

    def test_scrapes_tap_refs(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.subprocess_utils import CommandResult

        git_output = "abc1234 feat: something (TAP-1112)\ndef5678 fix: other thing (TAP-999)\n"
        with patch("tapps_mcp.tools.release_update.run_command") as mock_run:
            mock_run.return_value = CommandResult(
                returncode=0,
                stdout=git_output,
                stderr="",
                command=["git"],
            )
            _, issues = source_git_log(tmp_path, "1.4.2")
        tap_ids = [i.split(":")[0] for i in issues]
        assert "TAP-1112" in tap_ids
        assert "TAP-999" in tap_ids

    def test_deduplicates_tap_refs(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.subprocess_utils import CommandResult

        git_output = "abc1234 feat: thing TAP-1112\ndef5678 fix: same TAP-1112\n"
        with patch("tapps_mcp.tools.release_update.run_command") as mock_run:
            mock_run.return_value = CommandResult(
                returncode=0,
                stdout=git_output,
                stderr="",
                command=["git"],
            )
            _, issues = source_git_log(tmp_path, "1.4.2")
        tap_ids = [i.split(":")[0] for i in issues]
        assert tap_ids.count("TAP-1112") == 1

    def test_timeout_returns_empty(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.subprocess_utils import CommandResult

        with patch("tapps_mcp.tools.release_update.run_command") as mock_run:
            mock_run.return_value = CommandResult(
                returncode=-1,
                stdout="",
                stderr="Timed out after 10s",
                command=["git"],
                timed_out=True,
            )
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
            patch("tapps_mcp.tools.release_update.run_command") as mock_run,
        ):
            from tapps_mcp.tools.subprocess_utils import CommandResult

            mock_settings.return_value = MagicMock(project_root=str(tmp_path))
            mock_run.return_value = CommandResult(
                returncode=0,
                stdout="",
                stderr="",
                command=["git"],
            )
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

    async def test_multiline_changelog_bullets_preserved(self, tmp_path: Path) -> None:
        """Regression test for TAP-2056: multi-line CHANGELOG bullets must not be truncated."""
        from tapps_mcp.server_release_tools import tapps_release_update

        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(
            "## [1.5.0] - 2026-04-29\n\n"
            "- **Feature A**: First line of bullet A\n"
            "  second line of bullet A completing the sentence\n"
            "- **Feature B**: Single-line bullet B\n"
            "- **Feature C**: First line of bullet C\n"
            "  second line of bullet C with more detail\n\n"
            "## [1.4.2] - 2026-04-01\n\n"
            "- Old stuff\n",
            encoding="utf-8",
        )

        with (
            patch("tapps_core.config.settings.load_settings") as mock_settings,
            patch("tapps_mcp.server_release_tools._record_call"),
        ):
            mock_settings.return_value = MagicMock(project_root=str(tmp_path))
            result = await tapps_release_update(version="1.5.0", prev_version="1.4.2", dry_run=True)

        assert result["success"] is True
        body = result["data"]["body"]

        # Content from the 2nd physical line of each multi-line bullet must appear in the body
        assert "second line of bullet A completing the sentence" in body, (
            f"Continuation of bullet A missing from body:\n{body}"
        )
        assert "second line of bullet C with more detail" in body, (
            f"Continuation of bullet C missing from body:\n{body}"
        )
        # Single-line bullet must also appear
        assert "Feature B" in body, f"Feature B missing from body:\n{body}"
