"""Tests for atomic handoff write (TAP-3792)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from tapps_mcp.cli import main
from tapps_mcp.tools.handoff_schema import (
    handoff_memory_key,
    handoff_path,
    parse_handoff_markdown,
)
from tapps_mcp.tools.handoff_write import (
    HandoffWriteError,
    build_handoff_metadata,
    write_handoff,
)

pytestmark = pytest.mark.usefixtures("envelope_guard")

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
            return_value={"success": True, "key": handoff_memory_key()},
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
        data = json.loads(result.stdout)
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
        assert result["data"]["handoff_sections"]["next_p0"] == ["Implement handoff write CLI"]

    @pytest.mark.asyncio
    async def test_mcp_handoff_save_lint_failure_returns_structured_error(
        self, tmp_path: Path
    ) -> None:
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
            mock_write.side_effect = HandoffWriteError(
                ["Next (P0) is missing or empty when Open has items"],
                [],
            )
            result = await spt.tapps_handoff_save(_INVALID_HANDOFF)

        assert result["success"] is False
        assert result["elapsed_ms"] >= 0
        assert result["error"]["code"] == "handoff_lint_failed"
        assert "Next (P0)" in result["error"]["message"]
        assert result["error"]["errors"] == ["Next (P0) is missing or empty when Open has items"]


class TestSessionSearchQuery:
    def test_prefers_linear_p0_over_next_p0_and_iso(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.session_end_helpers import build_session_search_query

        handoff_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        handoff_path(tmp_path).write_text(_VALID_HANDOFF, encoding="utf-8")
        query, source = build_session_search_query(
            "2026-06-12T10:00:00+00:00",
            tmp_path,
        )
        assert query == "TAP-3790"
        assert source == "handoff_linear_p0"

    def test_prefers_next_p0_when_linear_absent(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.session_end_helpers import build_session_search_query

        body = _VALID_HANDOFF.replace("**Linear P0:** TAP-3790\n", "**Linear P0:** none\n")
        handoff_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        handoff_path(tmp_path).write_text(body, encoding="utf-8")
        query, source = build_session_search_query("", tmp_path)
        assert query == "Implement handoff write CLI"
        assert source == "handoff_next_p0"

    def test_falls_back_to_recent_without_handoff(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.session_end_helpers import build_session_search_query

        query, source = build_session_search_query("", tmp_path)
        assert query == "recent"
        assert source == "fallback_recent"


class TestResolveSessionStartIso:
    def test_uses_in_process_iso_first(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.session_end_helpers import (
            persist_session_start_iso,
            resolve_session_start_iso,
        )

        persist_session_start_iso(tmp_path, "2026-06-12T08:00:00+00:00")
        iso, source = resolve_session_start_iso(
            "2026-06-12T10:00:00+00:00",
            tmp_path,
        )
        assert iso == "2026-06-12T10:00:00+00:00"
        assert source == "session_state"

    def test_falls_back_to_persisted_file(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.session_end_helpers import (
            persist_session_start_iso,
            resolve_session_start_iso,
        )

        persist_session_start_iso(tmp_path, "2026-06-12T08:00:00+00:00")
        iso, source = resolve_session_start_iso("", tmp_path)
        assert iso == "2026-06-12T08:00:00+00:00"
        assert source == "persisted_file"


class TestBrainMirrorStatusSurfacing:
    """A failed brain mirror must not read as a completed handoff.

    The tool returned top-level ``success: true`` with a clean lint while
    ``brain_mirror`` carried ``{"error": "bad_request", "detail": "Value
    exceeds max length (4829 > 4096)"}``. A caller that did not inspect the
    nested key believed the handoff was retrievable next session when the
    cross-session copy had never persisted.
    """

    @staticmethod
    def _mock_result(tmp_path: Path, brain_mirror: dict[str, object] | None) -> MagicMock:
        return MagicMock(
            file_path=str(handoff_path(tmp_path)),
            doc=parse_handoff_markdown(_VALID_HANDOFF),
            metadata={"linear_p0": "TAP-3790"},
            lint=MagicMock(ok=True, errors=[], warnings=[]),
            brain_mirror=brain_mirror,
            session_end=None,
        )

    async def _save(self, tmp_path: Path, brain_mirror: dict[str, object] | None) -> dict:
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
            mock_write.return_value = self._mock_result(tmp_path, brain_mirror)
            return await spt.tapps_handoff_save(_VALID_HANDOFF)

    @pytest.mark.asyncio
    async def test_failed_mirror_marks_response_degraded(self, tmp_path: Path) -> None:
        result = await self._save(
            tmp_path,
            {
                "error": "bad_request",
                "detail": "Value error, Value exceeds max length (4829 > 4096)",
                "value_length": 4829,
                "max_value_length": 4096,
            },
        )

        assert result["degraded"] is True
        assert result["data"]["brain_mirror_status"] == "failed"
        assert any("Brain mirror failed" in w for w in result["data"]["warnings"])
        # The size mismatch is named so the caller knows how to fix it.
        assert any("4829" in step and "4096" in step for step in result["data"]["next_steps"])

    @pytest.mark.asyncio
    async def test_successful_mirror_is_not_degraded(self, tmp_path: Path) -> None:
        result = await self._save(tmp_path, {"key": handoff_memory_key(), "success": True})

        assert result["data"]["brain_mirror_status"] == "ok"
        assert result.get("degraded") is not True
        assert "warnings" not in result["data"]

    @pytest.mark.asyncio
    async def test_skipped_mirror_is_not_a_failure(self, tmp_path: Path) -> None:
        """No configured bridge is an expected offline state, not a defect."""
        result = await self._save(
            tmp_path,
            {"success": False, "skipped": True, "reason": "bridge_unavailable"},
        )

        assert result["data"]["brain_mirror_status"] == "skipped"
        assert result.get("degraded") is not True

    @pytest.mark.asyncio
    async def test_failed_mirror_still_reports_the_intact_file(self, tmp_path: Path) -> None:
        result = await self._save(tmp_path, {"error": "bad_request", "detail": "nope"})

        assert result["data"]["file_path"] == str(handoff_path(tmp_path))
        assert any("intact" in step for step in result["data"]["next_steps"])

    @pytest.mark.asyncio
    async def test_failed_session_end_also_degrades(self, tmp_path: Path) -> None:
        """session_end is best-effort too and was equally invisible.

        check-response-envelope.py flagged it as the second instance of the
        same shape in this very response (TAP-5656/TAP-5660).
        """
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
            result_stub = self._mock_result(
                tmp_path, {"key": handoff_memory_key(), "success": True}
            )
            result_stub.session_end = {"success": False, "error": "flywheel_process timed out"}
            mock_write.return_value = result_stub
            result = await spt.tapps_handoff_save(_VALID_HANDOFF)

        assert result["degraded"] is True
        assert result["data"]["brain_mirror_status"] == "ok"
        assert result["data"]["session_end_status"] == "failed"
        assert any("Session end failed" in w for w in result["data"]["warnings"])

    @pytest.mark.asyncio
    async def test_absent_session_end_is_skipped_not_failed(self, tmp_path: Path) -> None:
        result = await self._save(tmp_path, {"key": handoff_memory_key(), "success": True})

        assert result["data"]["session_end_status"] == "skipped"
        assert result.get("degraded") is not True


_UNPARSEABLE_HANDOFF = """\
# Session handoff
**Updated:** 2026-06-12T12:00:00Z

## Completed
- shipped the mirror fix

## Todo
- finish the linter
"""


def _over_cap_handoff() -> str:
    """A lint-clean handoff whose body exceeds the brain's per-value cap."""
    from tapps_mcp.tools.handoff_schema import _brain_max_value_length

    padding = "\n".join(f"- filler line {i}" for i in range(_brain_max_value_length() // 8))
    return _VALID_HANDOFF.replace("- Shipped memory search HTTP bridge", padding)


class TestEmptyParseWritesNothing:
    """TAP-6493: an unparseable handoff must not reach disk or the brain.

    ``## Completed`` / ``## Todo`` map to no section key, so the parser
    dropped every bullet, lint passed vacuously, and the tool wrote and
    mirrored a document that continue-session reads back as empty — while
    silently replacing the previous, real handoff.
    """

    @pytest.mark.asyncio
    async def test_write_refuses_and_leaves_no_file(self, tmp_path: Path) -> None:
        mock_mirror = AsyncMock(return_value={"success": True})
        with (
            patch("tapps_mcp.tools.handoff_write.mirror_handoff_to_brain", mock_mirror),
            pytest.raises(HandoffWriteError) as exc_info,
        ):
            await write_handoff(tmp_path, _UNPARSEABLE_HANDOFF)

        assert not handoff_path(tmp_path).exists()
        mock_mirror.assert_not_awaited()
        assert "zero populated sections" in exc_info.value.errors[0]
        assert "'Completed'" in exc_info.value.errors[0]

    @pytest.mark.asyncio
    async def test_refusal_survives_fail_on_lint_errors_false(self, tmp_path: Path) -> None:
        """The advisory-lint escape hatch does not cover a document with no content."""
        with pytest.raises(HandoffWriteError):
            await write_handoff(tmp_path, _UNPARSEABLE_HANDOFF, fail_on_lint_errors=False)

        assert not handoff_path(tmp_path).exists()

    @pytest.mark.asyncio
    async def test_existing_handoff_is_not_clobbered(self, tmp_path: Path) -> None:
        handoff_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        handoff_path(tmp_path).write_text(_VALID_HANDOFF, encoding="utf-8")

        with pytest.raises(HandoffWriteError):
            await write_handoff(tmp_path, _UNPARSEABLE_HANDOFF)

        assert handoff_path(tmp_path).read_text(encoding="utf-8") == _VALID_HANDOFF

    @pytest.mark.asyncio
    async def test_mcp_save_returns_structured_empty_parse_error(self, tmp_path: Path) -> None:
        from tapps_mcp import server_pipeline_tools as spt

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
        ):
            mock_settings.return_value.project_root = tmp_path
            result = await spt.tapps_handoff_save(_UNPARSEABLE_HANDOFF)

        assert result["success"] is False
        assert result["error"]["code"] == "handoff_lint_failed"
        assert result["error"]["retryable"] is False
        message = result["error"]["message"]
        assert "'Completed'" in message and "'Todo'" in message
        assert "Next (P0)" in message and "Success criterion" in message
        assert not handoff_path(tmp_path).exists()


class TestOverCapMirrorIsRefusedUpFront:
    """TAP-6444: the cap is a constant, so the rejection is decidable locally.

    Attempting the round-trip meant the caller learned about it from a
    ``bad_request`` — or not at all when the bridge queued the doomed value
    offline and reported success.
    """

    @pytest.mark.asyncio
    async def test_bridge_is_never_called_for_an_over_cap_body(self) -> None:
        from tapps_mcp.tools.handoff_write import mirror_handoff_to_brain

        bridge = MagicMock()
        bridge.save = AsyncMock(return_value={"success": True})
        payload = await mirror_handoff_to_brain(_over_cap_handoff(), {}, bridge=bridge)

        bridge.save.assert_not_awaited()
        assert payload["success"] is False
        assert payload["error"] == "value_over_cap"

    @pytest.mark.asyncio
    async def test_refusal_names_size_cap_and_section(self) -> None:
        from tapps_mcp.tools.handoff_write import mirror_handoff_to_brain

        bridge = MagicMock()
        bridge.save = AsyncMock()
        payload = await mirror_handoff_to_brain(_over_cap_handoff(), {}, bridge=bridge)

        detail = payload["detail"]
        assert str(payload["value_length"]) in detail
        assert str(payload["max_value_length"]) in detail
        assert "## Done" in detail
        assert payload["largest_section"][0] == "Done"

    @pytest.mark.asyncio
    async def test_within_cap_body_still_reaches_the_bridge(self) -> None:
        from tapps_mcp.tools.handoff_write import mirror_handoff_to_brain

        bridge = MagicMock()
        bridge.save = AsyncMock(return_value={"success": True, "key": handoff_memory_key()})
        payload = await mirror_handoff_to_brain(_VALID_HANDOFF, {}, bridge=bridge)

        bridge.save.assert_awaited_once()
        assert payload["success"] is True


class TestOverCapSaveEnvelopeIsNotPlainSuccess:
    """The whole point of TAP-6444: the envelope must not claim the mirror landed."""

    @staticmethod
    async def _save(tmp_path: Path, **kwargs: object) -> dict:
        from tapps_mcp import server_pipeline_tools as spt

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
        ):
            mock_settings.return_value.project_root = tmp_path
            return await spt.tapps_handoff_save(_over_cap_handoff(), **kwargs)

    @pytest.mark.asyncio
    async def test_default_call_refuses_and_names_the_overage(self, tmp_path: Path) -> None:
        result = await self._save(tmp_path)

        assert result["success"] is False
        assert result["error"]["code"] == "handoff_lint_warnings"
        # Decided from the submitted body alone: telling the caller to retry
        # would be telling them to re-submit the same over-cap document.
        assert result["error"]["retryable"] is False
        assert result["error"]["category"] == "user_input"
        warning = "; ".join(result["error"]["warnings"])
        assert "value cap" in warning and "## Done" in warning
        # The file did land, so the refusal says where it is rather than
        # leaving the caller to assume nothing happened.
        assert result["error"]["file_path"] == str(handoff_path(tmp_path))

    @pytest.mark.asyncio
    async def test_allow_warnings_path_is_degraded_not_success(self, tmp_path: Path) -> None:
        """The escape hatch the skill tells agents to use for stale timestamps.

        Passing it must not convert a rejected mirror into a clean success --
        that was the exact route from "lint warned" to "tool said done".
        """
        result = await self._save(tmp_path, allow_lint_warnings=True)

        assert result["degraded"] is True
        assert result["data"]["brain_mirror_status"] == "failed"
        assert result["data"]["brain_mirror"]["error"] == "value_over_cap"
        steps = " ".join(result["data"]["next_steps"])
        assert "## Done" in steps
        assert str(result["data"]["brain_mirror"]["value_length"]) in steps

    @pytest.mark.asyncio
    async def test_within_cap_handoff_still_returns_plain_success(self, tmp_path: Path) -> None:
        """The control: same escape hatch, a body that fits, no degradation.

        ``allow_lint_warnings`` here only covers the fixture's fixed (and by
        now stale) Updated timestamp — it is the flag the previous test uses,
        so holding it constant isolates the overage as the cause.
        """
        from tapps_mcp import server_pipeline_tools as spt

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch(
                "tapps_mcp.tools.handoff_write.mirror_handoff_to_brain",
                new_callable=AsyncMock,
                return_value={"success": True, "key": handoff_memory_key()},
            ),
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
        ):
            mock_settings.return_value.project_root = tmp_path
            result = await spt.tapps_handoff_save(_VALID_HANDOFF, allow_lint_warnings=True)

        assert result["success"] is True
        assert result.get("degraded") is not True
        assert result["data"]["brain_mirror_status"] == "ok"
