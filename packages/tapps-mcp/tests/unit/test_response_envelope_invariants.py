"""The envelope invariant, and its application to real tool responses (TAP-5659).

``assert_envelope_consistent`` (packages/tapps-mcp/tests/conftest.py) fails when
a response reports plain success while a nested sub-result reports failure. That
shape shipped two defects to a consuming project: ``tapps_handoff_save`` returned
``success: true`` over a brain mirror that had been rejected, and the caller had
no way to know short of reading the nested key.

The static counterpart is ``scripts/check-response-envelope.py``. The lint catches
the shape when it is written; these tests catch the behaviour when it runs.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.tools.handoff_schema import handoff_path, parse_handoff_markdown

_HANDOFF = """\
# Session handoff
**Updated:** 2026-06-12T12:00:00Z
**Linear P0:** TAP-3790

## Done
- Shipped the thing

## Open
- Finish the other thing

## Next (P0)
- Finish the other thing
"""


class TestEnvelopeInvariantItself:
    """The helper must actually catch the shape it exists for."""

    def test_flags_plain_success_over_nested_failure(self, envelope_consistent) -> None:
        response = {
            "tool": "demo",
            "success": True,
            "data": {"brain_mirror": {"error": "bad_request", "detail": "too long"}},
        }
        with pytest.raises(AssertionError, match="plain success while nested"):
            envelope_consistent(response)

    def test_flags_nested_success_false(self, envelope_consistent) -> None:
        response = {"tool": "demo", "success": True, "data": {"sub": {"success": False}}}
        with pytest.raises(AssertionError):
            envelope_consistent(response)

    def test_finds_failures_nested_in_lists(self, envelope_consistent) -> None:
        response = {
            "tool": "demo",
            "success": True,
            "data": {"results": [{"ok": True}, {"error": "boom"}]},
        }
        with pytest.raises(AssertionError, match=r"data\.results\[1\]"):
            envelope_consistent(response)

    def test_accepts_degraded_response(self, envelope_consistent) -> None:
        envelope_consistent(
            {
                "tool": "demo",
                "success": True,
                "degraded": True,
                "data": {"sub": {"error": "boom"}},
            }
        )

    def test_accepts_explicit_failure_response(self, envelope_consistent) -> None:
        envelope_consistent({"tool": "demo", "success": False, "data": {"sub": {"error": "b"}}})

    def test_skipped_is_not_a_failure(self, envelope_consistent) -> None:
        """Never-attempted is an expected offline state, not a silent loss."""
        envelope_consistent(
            {
                "tool": "demo",
                "success": True,
                "data": {"sub": {"success": False, "skipped": True, "reason": "no bridge"}},
            }
        )

    def test_clean_response_passes(self, envelope_consistent) -> None:
        envelope_consistent({"tool": "demo", "success": True, "data": {"count": 3}})

    def test_allow_skips_named_keys(self, envelope_consistent) -> None:
        """A report *about* failures embeds failure-shaped records legitimately."""
        response = {
            "tool": "demo",
            "success": True,
            "data": {"violation_log": {"error": "recorded earlier"}},
        }
        with pytest.raises(AssertionError):
            envelope_consistent(response)
        envelope_consistent(response, allow=("violation_log",))


class TestHandoffSaveEnvelope:
    """The response the defect was reported against, both ways round."""

    @staticmethod
    async def _save(tmp_path: Path, *, brain_mirror: dict, session_end: dict | None = None) -> dict:
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
                doc=parse_handoff_markdown(_HANDOFF),
                metadata={},
                lint=MagicMock(ok=True, errors=[], warnings=[]),
                brain_mirror=brain_mirror,
                session_end=session_end,
            )
            return await spt.tapps_handoff_save(_HANDOFF)

    @pytest.mark.asyncio
    async def test_successful_handoff_envelope_is_consistent(
        self, tmp_path: Path, envelope_consistent
    ) -> None:
        result = await self._save(tmp_path, brain_mirror={"key": "session-handoff", "success": True})
        envelope_consistent(result)

    @pytest.mark.asyncio
    async def test_rejected_mirror_no_longer_claims_plain_success(
        self, tmp_path: Path, envelope_consistent
    ) -> None:
        """The exact payload from the AgentForge report."""
        result = await self._save(
            tmp_path,
            brain_mirror={
                "error": "bad_request",
                "detail": "Value error, Value exceeds max length (4829 > 4096)",
            },
        )
        envelope_consistent(result)
        assert result["degraded"] is True

    @pytest.mark.asyncio
    async def test_failed_session_end_no_longer_claims_plain_success(
        self, tmp_path: Path, envelope_consistent
    ) -> None:
        result = await self._save(
            tmp_path,
            brain_mirror={"key": "session-handoff", "success": True},
            session_end={"success": False, "error": "flywheel_process timed out"},
        )
        envelope_consistent(result)
        assert result["degraded"] is True
