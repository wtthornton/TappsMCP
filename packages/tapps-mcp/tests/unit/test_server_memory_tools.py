"""TAP-1993/TAP-1994: tapps_memory internal-function tests.

TAP-1993 (Phase 2): non-lifecycle actions return a refused-redirect envelope.
TAP-1994 (Phase 3): tapps_memory is no longer registered as an MCP tool.
The function continues to exist as an internal helper for lifecycle calls;
all non-lifecycle behaviour remains as before (refused envelope redirects).
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp import server_memory_tools
from tapps_mcp.server_memory_tools import (
    _LIFECYCLE_ACTIONS,
    _REFUSED_BRAIN_TOOL,
    _VALID_ACTIONS,
    tapps_memory,
)

pytestmark = pytest.mark.usefixtures("envelope_guard")


async def _noop_init() -> None:
    """Async no-op for ensure_session_initialized."""


@pytest.mark.asyncio()
class TestRefusedEnvelope:
    """TAP-1993: non-lifecycle actions return a refused-redirect envelope."""

    @pytest.fixture(autouse=True)
    def _mock_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Skip session initialization in tests."""
        monkeypatch.setattr(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            _noop_init,
        )

    def _make_mock_bridge(self) -> MagicMock:
        bridge = MagicMock()
        bridge.record_event = AsyncMock(return_value={"recorded": True})
        return bridge

    @pytest.mark.parametrize("action", sorted(_VALID_ACTIONS - _LIFECYCLE_ACTIONS))
    async def test_non_lifecycle_action_returns_refused(self, action: str) -> None:
        """Every non-lifecycle action must return a refused envelope, not execute."""
        bridge = self._make_mock_bridge()

        with patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge):
            result = await tapps_memory(action=action)
            await asyncio.sleep(0)  # let any background tasks complete

        assert result["success"] is True, (
            f"action={action!r}: expected success=True for refused envelope, got {result}"
        )
        data = result["data"]
        assert data.get("refused") is True, (
            f"action={action!r}: expected 'refused': True in data, got {data}"
        )
        assert data.get("action") == action, (
            f"action={action!r}: 'action' field in envelope must echo the original action"
        )
        use = data.get("use", "")
        assert use.startswith("mcp__tapps-brain__"), (
            f"action={action!r}: 'use' field must reference a mcp__tapps-brain__ tool, got {use!r}"
        )
        assert "hint" in data, (
            f"action={action!r}: refused envelope must include a 'hint' field"
        )

    async def test_refused_envelope_use_field_matches_mapping(self) -> None:
        """The 'use' field in the refused envelope must match _REFUSED_BRAIN_TOOL."""
        bridge = self._make_mock_bridge()

        for action, expected_tool in _REFUSED_BRAIN_TOOL.items():
            with patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge):
                result = await tapps_memory(action=action)

            data = result["data"]
            assert data.get("refused") is True
            assert data.get("use") == expected_tool, (
                f"action={action!r}: expected use={expected_tool!r}, got {data.get('use')!r}"
            )

    async def test_refused_actions_do_not_touch_store(self) -> None:
        """Non-lifecycle actions must return before initializing the memory store."""
        bridge = self._make_mock_bridge()

        with (
            patch(
                "tapps_mcp.server_memory_tools._get_memory_store",
                side_effect=AssertionError("store must not be initialized for refused actions"),
            ),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
        ):
            # 'save' is a non-lifecycle action that must never hit _get_memory_store
            result = await tapps_memory(action="save", key="k", value="v")

        data = result["data"]
        assert data.get("refused") is True

    async def test_refused_envelope_is_parseable_for_self_correction(self) -> None:
        """Integration test: an agent receiving a refused envelope can self-correct.

        The envelope must contain enough machine-readable info for the agent to:
        1. Detect refusal (refused=True).
        2. Identify the correct brain tool (use='mcp__tapps-brain__...').
        3. Echo the original action for logging (action='...').
        """
        bridge = self._make_mock_bridge()

        with patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge):
            result = await tapps_memory(action="search", query="session patterns")

        data = result["data"]
        # Step 1: detect refusal.
        assert data["refused"] is True
        # Step 2: self-correct — the use field names a callable brain tool.
        brain_tool = data["use"]
        assert brain_tool.startswith("mcp__tapps-brain__"), (
            f"use={brain_tool!r} is not a tapps-brain tool — agent cannot self-correct"
        )
        # Step 3: original action is preserved for diagnostics.
        assert data["action"] == "search"

    async def test_refused_telemetry_still_fires(self) -> None:
        """TAP-1992 telemetry fires even when the action is refused (Phase 1 data preserved)."""
        bridge = self._make_mock_bridge()

        with patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge):
            await tapps_memory(action="save", key="k", value="v")
            await asyncio.sleep(0)

        bridge.record_event.assert_called_once_with(
            "deprecated_tool_call", "tapps_memory:save"
        )


@pytest.mark.asyncio()
class TestLifecycleActions:
    """TAP-1993: lifecycle actions (session_start_capture, session_end_consolidate) execute."""

    @pytest.fixture(autouse=True)
    def _mock_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            _noop_init,
        )

    def _make_mock_bridge(self) -> MagicMock:
        bridge = MagicMock()
        bridge.record_event = AsyncMock(return_value={"recorded": True})
        return bridge

    async def test_session_start_capture_does_not_return_refused(self) -> None:
        """session_start_capture must NOT return the refused envelope."""
        bridge = self._make_mock_bridge()
        bridge.index_session = AsyncMock(return_value={"indexed": True, "session_id": "s1"})

        with (
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
            patch(
                "tapps_mcp.server_memory_tools._get_memory_store", side_effect=Exception("no store")
            ),
        ):
            result = await tapps_memory(
                action="session_start_capture",
                value="testing session capture",
            )

        data = result.get("data", result)
        assert data.get("refused") is not True, (
            f"session_start_capture must not return refused envelope; got {data}"
        )

    async def test_session_end_consolidate_does_not_return_refused(self) -> None:
        """session_end_consolidate must NOT return the refused envelope."""
        bridge = self._make_mock_bridge()
        bridge.session_end = AsyncMock(return_value={"finalized": True})

        with (
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
            patch(
                "tapps_mcp.server_memory_tools._get_memory_store", side_effect=Exception("no store")
            ),
        ):
            result = await tapps_memory(
                action="session_end_consolidate",
                value="Session complete — fixed TAP-1993",
            )

        data = result.get("data", result)
        assert data.get("refused") is not True, (
            f"session_end_consolidate must not return refused envelope; got {data}"
        )

    def test_lifecycle_actions_are_in_valid_actions(self) -> None:
        """Both lifecycle actions must be registered in _VALID_ACTIONS."""
        assert "session_start_capture" in _VALID_ACTIONS
        assert "session_end_consolidate" in _VALID_ACTIONS

    def test_lifecycle_actions_not_in_refused_mapping(self) -> None:
        """Lifecycle actions must not appear in _REFUSED_BRAIN_TOOL (they are not redirected)."""
        assert "session_start_capture" not in _REFUSED_BRAIN_TOOL
        assert "session_end_consolidate" not in _REFUSED_BRAIN_TOOL

    def test_refused_mapping_covers_all_non_lifecycle_valid_actions(self) -> None:
        """Every non-lifecycle valid action must have an entry in _REFUSED_BRAIN_TOOL."""
        non_lifecycle = _VALID_ACTIONS - _LIFECYCLE_ACTIONS
        missing = non_lifecycle - set(_REFUSED_BRAIN_TOOL.keys())
        assert not missing, (
            f"These non-lifecycle actions are missing from _REFUSED_BRAIN_TOOL: {sorted(missing)}"
        )


class TestMcpCatalogRemoval:
    """TAP-1994 / ADR-0016: tapps_memory only on nlt-memory profile."""

    def test_tapps_memory_not_on_default_server(self) -> None:
        from tapps_mcp.server import _resolve_allowed_tools

        settings = MagicMock()
        settings.enabled_tools = None
        settings.disabled_tools = []
        settings.tool_preset = "nlt-build"
        allowed = _resolve_allowed_tools(settings)
        assert "tapps_memory" not in allowed

    def test_tapps_memory_on_nlt_memory_profile(self) -> None:
        from tapps_mcp.server import _resolve_allowed_tools

        settings = MagicMock()
        settings.enabled_tools = None
        settings.disabled_tools = []
        settings.tool_preset = "nlt-memory"
        allowed = _resolve_allowed_tools(settings)
        assert "tapps_memory" in allowed

    def test_tapps_memory_in_all_tool_names(self) -> None:
        from tapps_mcp.server import ALL_TOOL_NAMES

        assert "tapps_memory" in ALL_TOOL_NAMES


def _big_entry(key: str = "k1") -> dict[str, object]:
    return {
        "key": key,
        "value": "x" * 2000,
        "tier": "pattern",
        "confidence": 0.9,
        "tags": ["a", "b"],
    }


_ENTRY_SHELL: dict[str, object] = {
    "key": "k1",
    "value": "",
    "tier": "pattern",
    "confidence": 0.9,
    "tags": ["a", "b"],
}
_ENTRY_SHELL_OVERHEAD_BYTES = len(json.dumps(_ENTRY_SHELL).encode("utf-8"))


def _entry_of_full_json_size(target_bytes: int, key: str = "k1") -> dict[str, object]:
    """Build an entry whose ``json.dumps`` (full, unprojected form) is
    exactly ``target_bytes`` long — the plain "x" filler has no chars that
    need escaping, so padding length is `target - <fixed-field overhead>`.
    """
    entry = dict(_ENTRY_SHELL)
    entry["key"] = key
    entry["value"] = "x" * (target_bytes - _ENTRY_SHELL_OVERHEAD_BYTES)
    assert len(json.dumps(entry).encode("utf-8")) == target_bytes
    return entry


@pytest.mark.asyncio()
class TestCompactProjection:
    """TAP-6616: get/search accept projection='compact'; default stays full."""

    @pytest.fixture(autouse=True)
    def _mock_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            _noop_init,
        )

    async def test_get_default_projection_is_unchanged_full(self) -> None:
        entry = _big_entry()
        with (
            patch("tapps_mcp.server_memory_tools._MCP_MEMORY_MODE", "slim"),
            patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=MagicMock()),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=None),
            patch.dict(
                server_memory_tools._DISPATCH,
                {
                    "get": lambda _store, _p: {
                        "action": "get",
                        "found": True,
                        "entry": dict(entry),
                        "store_metadata": {},
                    }
                },
                clear=False,
            ),
        ):
            result = await tapps_memory(action="get", key="k1")

        assert result["data"]["entry"]["value"] == entry["value"]
        assert "summary" not in result["data"]["entry"]

    async def test_get_compact_projection_reduces_payload_by_70_percent(self) -> None:
        entry = _big_entry()
        with (
            patch("tapps_mcp.server_memory_tools._MCP_MEMORY_MODE", "slim"),
            patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=MagicMock()),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=None),
            patch.dict(
                server_memory_tools._DISPATCH,
                {
                    "get": lambda _store, _p: {
                        "action": "get",
                        "found": True,
                        "entry": dict(entry),
                        "store_metadata": {},
                    }
                },
                clear=False,
            ),
        ):
            result = await tapps_memory(action="get", key="k1", projection="compact")

        compact_entry = result["data"]["entry"]
        assert set(compact_entry) == {"key", "tier", "confidence", "tags", "summary"}
        assert len(compact_entry["summary"]) <= 203  # 200 chars + "..."

        full_bytes = len(json.dumps(entry).encode("utf-8"))
        compact_bytes = len(json.dumps(compact_entry).encode("utf-8"))
        assert full_bytes > 1024
        assert compact_bytes <= full_bytes * 0.3

    @pytest.mark.parametrize("target_bytes", [1024, 1100, 1500, 10240])
    async def test_get_compact_projection_holds_70_percent_at_boundary_sizes(
        self, target_bytes: int
    ) -> None:
        """TAP-6616 refutation: the ">=70% reduction on entries over 1KB"
        guarantee must hold AT the 1KB boundary itself, not just on far
        larger entries. On pre-fix HEAD (280-char summary cap) this failed
        at 1024B: compact was 369/1024 = 36.0% of full (a 64.0% reduction,
        short of the promised 70%+)."""
        entry = _entry_of_full_json_size(target_bytes)
        with (
            patch("tapps_mcp.server_memory_tools._MCP_MEMORY_MODE", "slim"),
            patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=MagicMock()),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=None),
            patch.dict(
                server_memory_tools._DISPATCH,
                {
                    "get": lambda _store, _p: {
                        "action": "get",
                        "found": True,
                        "entry": dict(entry),
                        "store_metadata": {},
                    }
                },
                clear=False,
            ),
        ):
            result = await tapps_memory(action="get", key="k1", projection="compact")

        compact_entry = result["data"]["entry"]
        full_bytes = len(json.dumps(entry).encode("utf-8"))
        compact_bytes = len(json.dumps(compact_entry).encode("utf-8"))
        assert full_bytes == target_bytes
        assert compact_bytes <= full_bytes * 0.3, (
            f"{target_bytes}B: compact={compact_bytes} is "
            f"{compact_bytes / full_bytes:.1%} of full, want <=30%"
        )

    async def test_get_projection_case_insensitive_compact(self) -> None:
        entry = _big_entry()
        with (
            patch("tapps_mcp.server_memory_tools._MCP_MEMORY_MODE", "slim"),
            patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=MagicMock()),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=None),
            patch.dict(
                server_memory_tools._DISPATCH,
                {
                    "get": lambda _store, _p: {
                        "action": "get",
                        "found": True,
                        "entry": dict(entry),
                        "store_metadata": {},
                    }
                },
                clear=False,
            ),
        ):
            result = await tapps_memory(action="get", key="k1", projection="Compact")

        compact_entry = result["data"]["entry"]
        assert set(compact_entry) == {"key", "tier", "confidence", "tags", "summary"}
        assert result["data"]["projection"] == "compact"
        assert "projection_downgraded" not in result["data"]

    async def test_get_projection_unrecognized_value_downgrades_honestly(self) -> None:
        entry = _big_entry()
        with (
            patch("tapps_mcp.server_memory_tools._MCP_MEMORY_MODE", "slim"),
            patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=MagicMock()),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=None),
            patch.dict(
                server_memory_tools._DISPATCH,
                {
                    "get": lambda _store, _p: {
                        "action": "get",
                        "found": True,
                        "entry": dict(entry),
                        "store_metadata": {},
                    }
                },
                clear=False,
            ),
        ):
            result = await tapps_memory(action="get", key="k1", projection="brief")

        assert result["data"]["entry"]["value"] == entry["value"]
        assert result["data"]["projection"] == "full"
        assert result["data"]["requested_projection"] == "brief"
        assert result["data"]["projection_downgraded"] is True

    async def test_search_compact_projection_applies_to_every_result(self) -> None:
        entries = [_big_entry("k1"), _big_entry("k2")]
        with (
            patch("tapps_mcp.server_memory_tools._MCP_MEMORY_MODE", "slim"),
            patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=MagicMock()),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=None),
            patch.dict(
                server_memory_tools._DISPATCH,
                {
                    "search": lambda _store, _p: {
                        "action": "search",
                        "ranked": False,
                        "results": [dict(e) for e in entries],
                        "total_count": 2,
                        "returned_count": 2,
                        "query": "q",
                        "store_metadata": {},
                    }
                },
                clear=False,
            ),
        ):
            result = await tapps_memory(action="search", query="q", projection="compact")

        for item in result["data"]["results"]:
            assert set(item) == {"key", "tier", "confidence", "tags", "summary"}
