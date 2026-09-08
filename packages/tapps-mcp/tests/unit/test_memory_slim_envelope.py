"""TAP-3895 / ADR-0016: `tapps_memory` envelope-honesty tests.

Three envelopes measured as dishonest on the base tree, each with its own
test group:

1. A refused (non-slim) action returned `success=True` with a `refused`
   flag pointing at a forbidden `mcp__tapps-brain__*` tool, category
   `"internal"`. It must instead be a real `error_response`, category
   `"user_input"`, with no `mcp__tapps-brain__` string anywhere (VAL-02).
2. `deprecated_tool_call` telemetry fired for *every* action, including
   allowed slim actions like `search` — mislabeling sanctioned calls as
   deprecated. Allowed actions must fire `tapps_memory_call`; only refused
   actions fire `tapps_memory_refused` (VAL-03).
3. `health` in HTTP-bridge mode (`store is None`) coerced a missing brain
   `entry_count` to a literal `0` — a false zero. It must be `None` with
   `entry_count_source: "unavailable"` (VAL-04).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.server_memory_tools import tapps_memory

pytestmark = pytest.mark.usefixtures("envelope_guard")


async def _noop_init() -> None:
    """Async no-op for ensure_session_initialized."""


def _make_mock_bridge() -> MagicMock:
    bridge = MagicMock()
    bridge.record_event = AsyncMock(return_value={"recorded": True})
    return bridge


@pytest.fixture(autouse=True)
def _mock_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "tapps_mcp.server_memory_tools.ensure_session_initialized",
        _noop_init,
    )


@pytest.mark.asyncio()
class TestRefusedEnvelopeIsHonest:
    """VAL-02: a refused action returns error_response, not a redirect."""

    async def test_refused_action_is_error_not_success(self) -> None:
        bridge = _make_mock_bridge()
        with (
            patch("tapps_mcp.server_memory_tools._MCP_MEMORY_MODE", "slim"),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
        ):
            result = await tapps_memory(action="reinforce", key="k")
            await asyncio.sleep(0)

        assert result["success"] is False, f"refused action must be success=False, got {result}"

    async def test_refused_envelope_category_is_user_input_not_internal(self) -> None:
        bridge = _make_mock_bridge()
        with (
            patch("tapps_mcp.server_memory_tools._MCP_MEMORY_MODE", "slim"),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
        ):
            result = await tapps_memory(action="gc")
            await asyncio.sleep(0)

        error = result["error"]
        assert error["category"] == "user_input", (
            f"a client-side misuse (asking for a non-slim action) must not be "
            f"category='internal'; got {error['category']!r}"
        )
        assert error["retryable"] is False

    async def test_refused_envelope_never_names_a_forbidden_brain_tool(self) -> None:
        bridge = _make_mock_bridge()
        with (
            patch("tapps_mcp.server_memory_tools._MCP_MEMORY_MODE", "slim"),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
        ):
            result = await tapps_memory(action="hive_status")
            await asyncio.sleep(0)

        as_text = str(result)
        assert "mcp__tapps-brain__" not in as_text, (
            f"refused envelope must never cite a forbidden mcp__tapps-brain__ tool: {result}"
        )
        assert result["error"]["remediation"].startswith("Use one of:")


@pytest.mark.asyncio()
class TestTelemetryReflectsOutcome:
    """VAL-03: only refused actions are labelled 'deprecated'; allowed ones are not."""

    async def test_allowed_action_fires_tapps_memory_call_not_deprecated(self) -> None:
        bridge = _make_mock_bridge()
        with (
            patch("tapps_mcp.server_memory_tools._MCP_MEMORY_MODE", "slim"),
            patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=None),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
        ):
            await tapps_memory(action="search", query="q")
            await asyncio.sleep(0)

        bridge.record_event.assert_called_once_with("tapps_memory_call", "tapps_memory:search")

    async def test_refused_action_fires_tapps_memory_refused_not_deprecated(self) -> None:
        bridge = _make_mock_bridge()
        with (
            patch("tapps_mcp.server_memory_tools._MCP_MEMORY_MODE", "slim"),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
        ):
            await tapps_memory(action="search_sessions", query="q")
            await asyncio.sleep(0)

        bridge.record_event.assert_called_once_with(
            "tapps_memory_refused", "tapps_memory:search_sessions"
        )
        fired_types = {c.args[0] for c in bridge.record_event.call_args_list}
        assert "deprecated_tool_call" not in fired_types


@pytest.mark.asyncio()
class TestHealthEntryCountIsHonest:
    """VAL-04: HTTP-bridge health never coerces a missing count to 0."""

    async def test_health_entry_count_null_when_store_none_and_brain_omits_count(self) -> None:
        bridge = _make_mock_bridge()
        bridge.health = AsyncMock(
            return_value={"status": "ok", "postgres": "connected", "store_path": None}
        )
        with (
            patch("tapps_mcp.server_memory_tools._MCP_MEMORY_MODE", "slim"),
            patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=None),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
        ):
            result = await tapps_memory(action="health")
            await asyncio.sleep(0)

        data = result["data"]
        assert data["entry_count"] is None, (
            f"a store=None health with no brain-reported count must be None, "
            f"not a coerced 0; got {data['entry_count']!r}"
        )
        assert data["entry_count_source"] == "unavailable"

    async def test_health_entry_count_from_brain_when_http_reports_it(self) -> None:
        bridge = _make_mock_bridge()
        bridge.health = AsyncMock(return_value={"status": "ok", "entry_count": 387})
        with (
            patch("tapps_mcp.server_memory_tools._MCP_MEMORY_MODE", "slim"),
            patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=None),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
        ):
            result = await tapps_memory(action="health")
            await asyncio.sleep(0)

        data = result["data"]
        assert data["entry_count"] == 387
        assert data["entry_count_source"] == "brain"

    async def test_health_entry_count_source_in_process_when_store_present(self) -> None:
        bridge = _make_mock_bridge()
        bridge.health = AsyncMock(return_value={"status": "ok", "entry_count": 5})
        with (
            patch("tapps_mcp.server_memory_tools._MCP_MEMORY_MODE", "slim"),
            patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=MagicMock()),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
        ):
            result = await tapps_memory(action="health")
            await asyncio.sleep(0)

        data = result["data"]
        assert data["entry_count"] == 5
        assert data["entry_count_source"] == "in_process"
