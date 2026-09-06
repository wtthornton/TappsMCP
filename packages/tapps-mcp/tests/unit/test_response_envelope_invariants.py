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

    def test_allow_covers_a_marker_at_the_root_of_data(self, envelope_consistent) -> None:
        """No parent key names it, so ``allow`` must reach the signal itself.

        ``tapps_dependency_scan`` puts ``error`` directly on ``data`` — a suite
        deferring that known inconsistency has nothing else to name (TAP-5659).
        """
        response = {"tool": "demo", "success": True, "data": {"error": "pip-audit missing"}}
        with pytest.raises(AssertionError):
            envelope_consistent(response)
        envelope_consistent(response, allow=("error",))

    def test_allow_covers_a_named_key_holding_success_false(self, envelope_consistent) -> None:
        """Naming the subtree key silences its own success:false marker too."""
        response = {"tool": "demo", "success": True, "data": {"sub": {"success": False}}}
        envelope_consistent(response, allow=("sub",))

    def test_allow_does_not_globally_cover_success_false(self, envelope_consistent) -> None:
        """A field name in ``allow`` is not a global mask (TAP-6618): naming
        "success" must not silence a success:false on an unrelated nested node."""
        response = {"tool": "demo", "success": True, "data": {"other": {"success": False}}}
        with pytest.raises(AssertionError):
            envelope_consistent(response, allow=("success",))


@pytest.mark.usefixtures("envelope_guard")
class TestEnvelopeGuardFixture:
    """The sweep's chokepoint: every envelope a test builds gets checked.

    Without these, ``envelope_guard`` could silently degrade to a no-op — it
    discovers its patch targets from ``sys.modules`` at runtime, so a refactor
    that moves ``success_response`` would leave the whole sweep green and blind.
    """

    def test_guard_patches_the_modules_that_bind_the_helper(self) -> None:
        """Most tool modules ``from ... import success_response`` at import time."""
        from tapps_mcp import server_analysis_tools, server_helpers, server_scoring_tools

        original = getattr(server_helpers.success_response, "__wrapped_original__", None)
        assert original is None  # the spy is a plain closure, not a functools wrapper
        assert server_helpers.success_response is server_scoring_tools.success_response
        assert server_helpers.success_response is server_analysis_tools.success_response
        assert server_helpers.success_response.__name__ == "_spy"

    def test_guard_records_envelopes_built_during_the_test(self) -> None:
        from tapps_mcp import server_helpers

        response = server_helpers.success_response("demo", 1, {"count": 1})
        assert response["success"] is True


class TestEnvelopeGuardTeardown:
    """The guard must fail the test when a real envelope lies, and clean up after."""

    def test_guard_raises_at_teardown_on_a_lying_envelope(self) -> None:
        """Driven through the fixture generator directly — the failure is a
        teardown error, which a test cannot observe from inside its own body."""
        import sys

        # ``pythonpath = packages/docs-mcp`` owns the top-level ``tests`` package,
        # so ``from tests.conftest import ...`` resolves to the wrong conftest.
        # Importlib import mode registers this package's under its own key.
        conftest = next(
            module
            for name, module in sys.modules.items()
            if name.endswith("conftest") and hasattr(module, "envelope_guard")
        )
        envelope_guard = conftest.envelope_guard

        request = MagicMock()
        request.node.iter_markers.return_value = []
        guard = envelope_guard.__wrapped__(request)
        next(guard)
        try:
            from tapps_mcp import server_helpers

            server_helpers.success_response("demo", 1, {"sub": {"error": "boom"}})
        finally:
            with pytest.raises(AssertionError, match="plain success while nested"):
                next(guard, None)

    def test_bindings_are_restored_after_the_guard_exits(self) -> None:
        """A leaked spy would keep appending to a dead fixture's list all session."""
        from tapps_mcp import server_helpers, server_scoring_tools

        assert server_helpers.success_response.__name__ == "success_response"
        assert server_scoring_tools.success_response is server_helpers.success_response


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
