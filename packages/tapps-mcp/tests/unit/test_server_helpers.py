"""Tests for tapps_mcp.server_helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from tapps_mcp.server_helpers import error_response, serialize_issues, success_response


class TestErrorResponse:
    def test_basic_error(self) -> None:
        result = error_response("tapps_score_file", "path_denied", "not found")
        assert result["tool"] == "tapps_score_file"
        assert result["success"] is False
        assert result["elapsed_ms"] == 0
        assert result["error"]["code"] == "path_denied"
        assert result["error"]["message"] == "not found"

    def test_no_degraded_key(self) -> None:
        result = error_response("tapps_test", "err", "msg")
        assert "degraded" not in result


class TestSuccessResponse:
    def test_basic_success(self) -> None:
        data = {"key": "value"}
        result = success_response("tapps_score_file", 42, data)
        assert result["tool"] == "tapps_score_file"
        assert result["success"] is True
        assert result["elapsed_ms"] == 42
        assert result["data"] == {"key": "value"}
        assert "degraded" not in result

    def test_degraded_flag(self) -> None:
        result = success_response("tapps_test", 10, {}, degraded=True)
        assert result["degraded"] is True

    def test_degraded_false_included_when_explicit(self) -> None:
        result = success_response("tapps_test", 10, {}, degraded=False)
        assert "degraded" in result
        assert result["degraded"] is False

    def test_degraded_omitted_when_not_passed(self) -> None:
        result = success_response("tapps_test", 10, {})
        assert "degraded" not in result


class TestSerializeIssues:
    def test_empty_list(self) -> None:
        assert serialize_issues([]) == []

    def test_with_models(self) -> None:
        m1 = MagicMock()
        m1.model_dump.return_value = {"code": "E001"}
        m2 = MagicMock()
        m2.model_dump.return_value = {"code": "E002"}
        result = serialize_issues([m1, m2])
        assert result == [{"code": "E001"}, {"code": "E002"}]

    def test_truncation(self) -> None:
        items = [MagicMock() for _ in range(30)]
        for i, item in enumerate(items):
            item.model_dump.return_value = {"i": i}
        result = serialize_issues(items, limit=5)
        assert len(result) == 5


class TestGetBrainBridgeProfile:
    """ADR-0012: the server bridge backs the full tapps_memory facade, so it
    must declare the ``full`` profile — ``coder`` gates ~18 of the bridge's
    tools (memory_save/get/search/list/supersede, hive_*, batch ops, …), which
    fail with ToolNotInProfileError on tapps-brain v3.20.0+.
    """

    def test_get_brain_bridge_uses_full_default_profile(self) -> None:
        """``_get_brain_bridge()`` must call ``create_brain_bridge`` with
        ``default_profile=BRAIN_PROFILE_SERVER`` (``full``)."""
        from tapps_core.brain_bridge import (
            BRAIN_PROFILE_SERVER,
            BRAIN_PROFILES_DEFERRED_OK,
            _BRIDGE_USED_TOOLS,
        )
        from tapps_mcp.server_helpers import _get_brain_bridge, _reset_brain_bridge_cache

        # Guard the invariant the choice rests on: the server profile must be a
        # broad-surface profile (one where a missing eager tool is benign
        # deferred-loading, not a real gate) — never a narrow facade profile.
        assert BRAIN_PROFILE_SERVER in BRAIN_PROFILES_DEFERRED_OK
        assert len(_BRIDGE_USED_TOOLS) > 18  # facade needs the wide surface

        mock_bridge = MagicMock()
        mock_settings = MagicMock()

        # load_settings is imported lazily inside _get_brain_bridge, so patch at
        # the source module, not at tapps_mcp.server_helpers.
        with (
            patch(
                "tapps_core.brain_bridge.create_brain_bridge", return_value=mock_bridge
            ) as mock_create,
            patch(
                "tapps_core.config.settings.load_settings", return_value=mock_settings
            ),
        ):
            _reset_brain_bridge_cache()
            bridge = _get_brain_bridge()

        assert bridge is mock_bridge
        mock_create.assert_called_once()
        _, call_kwargs = mock_create.call_args
        assert call_kwargs.get("default_profile") == BRAIN_PROFILE_SERVER == "full", (
            f"Expected default_profile='full', got {call_kwargs}"
        )
        # Cleanup singleton so other tests start clean.
        _reset_brain_bridge_cache()


class TestChecklistStateMarker:
    """TAP-2000: checklist outcomes emit brain events, not local JSON."""

    def test_emits_checklist_outcome_event(self, tmp_path: Path) -> None:
        from tapps_mcp.server_helpers import _reset_brain_bridge_cache, write_checklist_state_marker

        mock_bridge = MagicMock()
        mock_bridge.record_kg_event = AsyncMock(return_value={"recorded": True})
        captured: list[Any] = []

        with (
            patch("tapps_mcp.server_helpers._reset_brain_bridge_cache"),
            patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=mock_bridge),
            patch(
                "tapps_mcp.server_helpers.asyncio.create_task",
                side_effect=lambda coro: captured.append(coro),
            ),
        ):
            write_checklist_state_marker(
                tmp_path,
                complete=False,
                missing_required=["tapps_validate_changed"],
            )
            import asyncio

            asyncio.run(captured[0])

        kwargs = mock_bridge.record_kg_event.await_args.kwargs
        assert kwargs["event_type"] == "checklist_outcome"
        assert kwargs["payload_data"]["complete"] is False
        assert kwargs["payload_data"]["missing_required"] == ["tapps_validate_changed"]
        assert "ts" in kwargs["payload_data"]
        _reset_brain_bridge_cache()
