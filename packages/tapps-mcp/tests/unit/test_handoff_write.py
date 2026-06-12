"""Tests for atomic handoff write (TAP-3792)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from tapps_mcp.cli import main
from tapps_mcp.tools.handoff_schema import handoff_path, parse_handoff_markdown
from tapps_mcp.tools.handoff_write import (
    HandoffWriteError,
    build_handoff_metadata,
    write_handoff,
)

_VALID_HANDOFF = """\
# Session handoff
**Updated:** 2026-06-12T12:00:00Z
**Linear P0:** TAP-3790

## Done
- Shipped memory search HTTP bridge

## Open
- none

## Next (P0)
- Implement handoff write CLI

## Blockers
- none

## Verify
- uv run pytest packages/tapps-mcp/tests/unit/test_handoff_write.py

## Success criterion
- handoff write passes lint and mirrors full body
"""

_INVALID_HANDOFF = """\
# Session handoff
**Updated:** 2026-06-12T12:00:00Z

## Done
- partial

## Open
- unfinished work

## Next (P0)
- none

## Success criterion
- MET
"""


class TestHandoffWriteCore:
    @pytest.mark.asyncio
    async def test_write_valid_handoff_creates_file(self, tmp_path: Path) -> None:
        with patch(
            "tapps_mcp.tools.handoff_write.mirror_handoff_to_brain",
            new_callable=AsyncMock,
            return_value={"success": True, "key": "session-handoff"},
        ):
            result = await write_handoff(
                tmp_path,
                _VALID_HANDOFF,
                mirror_brain=True,
                run_session_end=False,
            )

        assert handoff_path(tmp_path).is_file()
        assert result.file_path == str(handoff_path(tmp_path))
        assert result.lint.ok
        assert result.doc.linear_p0 == "TAP-3790"
        assert handoff_path(tmp_path).read_text(encoding="utf-8") == _VALID_HANDOFF

    @pytest.mark.asyncio
    async def test_write_fails_on_open_without_p0(self, tmp_path: Path) -> None:
        with pytest.raises(HandoffWriteError) as exc_info:
            await write_handoff(tmp_path, _INVALID_HANDOFF)
        assert "Next (P0) is missing" in exc_info.value.errors[0]
        assert not handoff_path(tmp_path).exists()

    @pytest.mark.asyncio
    async def test_mirror_uses_full_markdown(self, tmp_path: Path) -> None:
        mock_mirror = AsyncMock(return_value={"success": True})
        with patch("tapps_mcp.tools.handoff_write.mirror_handoff_to_brain", mock_mirror):
            await write_handoff(tmp_path, _VALID_HANDOFF, mirror_brain=True)

        mock_mirror.assert_awaited_once()
        assert mock_mirror.await_args.args[0] == _VALID_HANDOFF
        metadata = mock_mirror.await_args.args[1]
        assert metadata["linear_p0"] == "TAP-3790"
        assert "updated_at" in metadata

    def test_build_handoff_metadata_includes_git(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.handoff_schema import parse_handoff_markdown

        doc = parse_handoff_markdown(_VALID_HANDOFF)
        with patch(
            "tapps_mcp.tools.handoff_write._git_context_sync",
            return_value={"git_sha": "abc1234", "git_branch": "main"},
        ):
            meta = build_handoff_metadata(doc, {"git_sha": "abc1234", "git_branch": "main"})
        assert meta["git_sha"] == "abc1234"
        assert meta["git_branch"] == "main"
        assert meta["linear_p0"] == "TAP-3790"


class TestHandoffWriteCli:
    def test_cli_write_from_stdin(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with (
            patch(
                "tapps_mcp.tools.handoff_write.write_handoff_sync",
                return_value=MagicMock(
                    file_path=str(handoff_path(tmp_path)),
                    doc=MagicMock(linear_p0="TAP-3790"),
                    metadata={"linear_p0": "TAP-3790"},
                    lint=MagicMock(ok=True, errors=[], warnings=[]),
                    brain_mirror={"success": True},
                    session_end=None,
                ),
            ),
            patch("tapps_mcp.cli._get_project_root", return_value=tmp_path),
        ):
            result = runner.invoke(
                main,
                ["handoff", "write"],
                input=_VALID_HANDOFF,
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["linear_p0"] == "TAP-3790"
        assert data["brain_mirror"]["success"] is True

    def test_cli_write_lint_failure_exits_1(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.md"
        bad.write_text(_INVALID_HANDOFF, encoding="utf-8")
        runner = CliRunner()
        with patch("tapps_mcp.cli._get_project_root", return_value=tmp_path):
            result = runner.invoke(main, ["handoff", "write", "--file", str(bad)])
        assert result.exit_code == 1
        assert "lint failed" in result.output.lower()

    def test_cli_requires_file_or_stdin(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with patch("tapps_mcp.cli._get_project_root", return_value=tmp_path):
            result = runner.invoke(main, ["handoff", "write"])
        assert result.exit_code == 2


class TestTappsHandoffSaveMcp:
    @pytest.mark.asyncio
    async def test_mcp_handoff_save_success(self, tmp_path: Path) -> None:
        from tapps_mcp import server_pipeline_tools as spt

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch(
                "tapps_mcp.tools.handoff_write.write_handoff",
                new_callable=AsyncMock,
            ) as mock_write,
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_write.return_value = MagicMock(
                file_path=str(handoff_path(tmp_path)),
                doc=parse_handoff_markdown(_VALID_HANDOFF),
                metadata={"linear_p0": "TAP-3790"},
                lint=MagicMock(ok=True, errors=[], warnings=[]),
                brain_mirror={"success": True},
                session_end=None,
            )
            result = await spt.tapps_handoff_save(_VALID_HANDOFF)

        assert result["success"] is True
        assert result["data"]["handoff_sections"]["next_p0"] == [
            "Implement handoff write CLI"
        ]


class TestSessionSearchQuery:
    def test_prefers_handoff_p0_over_iso(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.session_end_helpers import build_session_search_query

        handoff_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        handoff_path(tmp_path).write_text(_VALID_HANDOFF, encoding="utf-8")
        query, source = build_session_search_query(
            "2026-06-12T10:00:00+00:00",
            tmp_path,
        )
        assert query == "Implement handoff write CLI"
        assert source == "handoff_next_p0"

    def test_falls_back_to_recent_without_handoff(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.session_end_helpers import build_session_search_query

        query, source = build_session_search_query("", tmp_path)
        assert query == "recent"
        assert source == "fallback_recent"
