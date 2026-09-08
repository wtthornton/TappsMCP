"""TAP-1993/TAP-1994/TAP-3895: tapps_memory internal-function tests.

ADR-0016: tapps_memory is the slim ``nlt-memory`` facade over BrainBridge —
search/save/get/health/related plus the two session lifecycle actions dispatch;
every other action is refused with an honest ``error_response`` (not a
success-shaped redirect) pointing the caller at the CLI.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp import server_memory_tools
from tapps_mcp.server_memory_tools import (
    _LIFECYCLE_ACTIONS,
    _VALID_ACTIONS,
    NLT_MEMORY_SLIM_ACTIONS,
    tapps_memory,
)

pytestmark = pytest.mark.usefixtures("envelope_guard")


async def _noop_init() -> None:
    """Async no-op for ensure_session_initialized."""


@pytest.mark.asyncio()
class TestSlimGateRefusal:
    """ADR-0016: actions outside the nlt-memory slim allow-list are refused."""

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

    @pytest.mark.parametrize(
        "action",
        sorted(_VALID_ACTIONS - _LIFECYCLE_ACTIONS - NLT_MEMORY_SLIM_ACTIONS),
    )
    async def test_non_slim_action_returns_error_response(self, action: str) -> None:
        """Every non-slim, non-lifecycle action must return a real error, not execute."""
        bridge = self._make_mock_bridge()

        with (
            patch("tapps_mcp.server_memory_tools._MCP_MEMORY_MODE", "slim"),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
        ):
            result = await tapps_memory(action=action)
            await asyncio.sleep(0)  # let any background tasks complete

        assert result["success"] is False, (
            f"action={action!r}: expected success=False for a refused action, got {result}"
        )
        error = result["error"]
        assert error["code"] == "action_not_on_nlt_memory"
        assert error["category"] == "user_input"
        assert error["retryable"] is False
        assert "mcp__tapps-brain__" not in error["message"]
        assert "mcp__tapps-brain__" not in error["remediation"]

    async def test_refused_actions_do_not_touch_store(self) -> None:
        """Non-slim actions must return before initializing the memory store."""
        bridge = self._make_mock_bridge()

        with (
            patch("tapps_mcp.server_memory_tools._MCP_MEMORY_MODE", "slim"),
            patch(
                "tapps_mcp.server_memory_tools._get_memory_store",
                side_effect=AssertionError("store must not be initialized for refused actions"),
            ),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
        ):
            # 'delete' is not on the nlt-memory slim allow-list.
            result = await tapps_memory(action="delete", key="k")

        assert result["success"] is False
        assert result["error"]["code"] == "action_not_on_nlt_memory"

    async def test_off_mode_refuses_even_slim_eligible_actions(self) -> None:
        """When the tool isn't registered on nlt-memory, every action is refused.

        Unreachable over MCP by construction (register() only sets "slim" when
        the tool is registered), but a direct function call must still refuse
        honestly rather than silently dispatch.
        """
        bridge = self._make_mock_bridge()

        with (
            patch("tapps_mcp.server_memory_tools._MCP_MEMORY_MODE", "off"),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
        ):
            result = await tapps_memory(action="search", query="q")

        assert result["success"] is False
        assert result["error"]["code"] == "action_not_on_nlt_memory"

    async def test_refused_telemetry_fires_as_refused_not_deprecated(self) -> None:
        """A refused action records a 'tapps_memory_refused' event, not 'deprecated_tool_call'."""
        bridge = self._make_mock_bridge()

        with (
            patch("tapps_mcp.server_memory_tools._MCP_MEMORY_MODE", "slim"),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
        ):
            await tapps_memory(action="save_bulk", entries="[]")
            await asyncio.sleep(0)

        bridge.record_event.assert_called_once_with(
            "tapps_memory_refused", "tapps_memory:save_bulk"
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

    async def test_lifecycle_actions_dispatch_even_in_off_mode(self) -> None:
        """Lifecycle actions dispatch on every profile, unlike the slim allow-list."""
        bridge = self._make_mock_bridge()
        bridge.index_session = AsyncMock(return_value={"indexed": True, "session_id": "s1"})

        with (
            patch("tapps_mcp.server_memory_tools._MCP_MEMORY_MODE", "off"),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
            patch(
                "tapps_mcp.server_memory_tools._get_memory_store", side_effect=Exception("no store")
            ),
        ):
            result = await tapps_memory(action="session_start_capture", value="hello")

        error_code = (result.get("error") or {}).get("code")
        assert error_code != "action_not_on_nlt_memory", (
            f"lifecycle action must not hit the slim gate; got {result}"
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
