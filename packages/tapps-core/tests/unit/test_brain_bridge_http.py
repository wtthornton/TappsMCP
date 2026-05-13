"""Unit tests for HttpBrainBridge — the tapps-brain HTTP MCP transport.

Coverage:
- Factory: create_brain_bridge returns HttpBrainBridge when brain_http_url is set
- Factory: in-process path still selected when brain_http_url is empty (DSN present)
- Factory: returns None when neither transport is configured
- HttpBrainBridge._do_mcp_post: happy path, RPC error, tool error, JSON decode
- search, get, list_memories, recall_for_prompt, save, delete, reinforce, supersede
- hive_search, hive_status, hive_propagate, agent_register
- gc, consolidate
- Circuit breaker: opens after failures, blocks calls while open
- Retry: retries on transient error, exhausts and raises BrainBridgeUnavailable
- Offline write queue: save enqueues when circuit open; drain_blocking sends HTTP
- health_check: ok when /health returns 200; error when request fails
- close: drains queue and releases client
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mcp_response(payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    """Build a fake MCP tools/call JSON-RPC response."""
    text = json.dumps(payload)
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "content": [{"type": "text", "text": text}],
            "isError": is_error,
        },
    }


def _make_async_post(response_data: dict[str, Any], *, status_code: int = 200) -> AsyncMock:
    """Return an AsyncMock for httpx.AsyncClient.post that yields *response_data*."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = response_data
    mock_response.raise_for_status = MagicMock()
    if status_code >= 400:
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=mock_response
        )
    post_mock = AsyncMock(return_value=mock_response)
    return post_mock


def _make_http_bridge(url: str = "http://brain:8080", headers: dict[str, str] | None = None) -> Any:
    from tapps_core.brain_bridge import HttpBrainBridge

    return HttpBrainBridge(url, headers or {"Authorization": "Bearer test-token"})


# ---------------------------------------------------------------------------
# TAP-1616: X-Brain-Profile header resolution
# ---------------------------------------------------------------------------


class TestProfileHeader:
    def test_caller_supplied_profile_is_preserved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``build_brain_headers`` is the canonical resolution site —
        whatever it returns must flow to the wire untouched.
        """
        monkeypatch.delenv("TAPPS_BRAIN_PROFILE", raising=False)
        bridge = _make_http_bridge(
            headers={
                "Authorization": "Bearer t",
                "X-Brain-Profile": "coder",
            }
        )
        assert bridge._http_headers["X-Brain-Profile"] == "coder"

    def test_env_fallback_when_header_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Direct construction without settings (``settings=None`` factory
        path) must still honour the canonical ``TAPPS_BRAIN_PROFILE`` env.
        """
        monkeypatch.setenv("TAPPS_BRAIN_PROFILE", "agent_brain")
        bridge = _make_http_bridge(headers={"Authorization": "Bearer t"})
        assert bridge._http_headers.get("X-Brain-Profile") == "agent_brain"

    def test_no_header_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AC: when no profile is configured the bridge sends NO header so
        the server-side default profile applies — zero behavior change.
        """
        monkeypatch.delenv("TAPPS_BRAIN_PROFILE", raising=False)
        bridge = _make_http_bridge(headers={"Authorization": "Bearer t"})
        assert "X-Brain-Profile" not in bridge._http_headers


# ---------------------------------------------------------------------------
# TAP-1616: error classifier covers the new wire shape
# ---------------------------------------------------------------------------


class TestClassifyMcpError:
    def test_out_of_profile_data_reason_is_gated(self) -> None:
        from tapps_core.brain_bridge import (
            BrainMcpError,
            ToolNotInProfileError,
            _classify_mcp_error,
        )

        # Plain ToolNotInProfileError
        exc = ToolNotInProfileError(
            "gated",
            tool="memory_save",
            profile="agent_brain",
            data={"reason": "out_of_profile", "tool": "memory_save", "profile": "agent_brain"},
        )
        assert _classify_mcp_error(exc) == "gated"

        # Same shape carried on a generic BrainMcpError instance
        plain = BrainMcpError("generic", code=-32602, data={"reason": "out_of_profile"})
        assert _classify_mcp_error(plain) == "gated"

    def test_legacy_tool_not_in_profile_still_gated(self) -> None:
        """Back-compat for brains <3.17 that emitted the old shape."""
        from tapps_core.brain_bridge import BrainMcpError, _classify_mcp_error

        legacy = BrainMcpError("legacy", code=-32601, data={"error": "tool_not_in_profile"})
        assert _classify_mcp_error(legacy) == "gated"

    def test_unknown_tool_message_is_removed(self) -> None:
        from tapps_core.brain_bridge import _classify_mcp_error

        assert _classify_mcp_error(RuntimeError("Unknown tool: foo")) == "removed"

    def test_other_failures_are_other(self) -> None:
        from tapps_core.brain_bridge import _classify_mcp_error

        assert _classify_mcp_error(RuntimeError("timeout")) == "other"


# ---------------------------------------------------------------------------
# Factory dispatch
# ---------------------------------------------------------------------------


class TestCreateBrainBridgeDispatch:
    def test_returns_http_bridge_when_url_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", "http://brain:8080")
        monkeypatch.delenv("TAPPS_BRAIN_DATABASE_URL", raising=False)
        from tapps_core.brain_bridge import HttpBrainBridge, create_brain_bridge

        settings = MagicMock()
        settings.memory.brain_http_url = "http://brain:8080"
        settings.memory.brain_auth_token = None
        settings.memory.brain_project_id = ""
        settings.project_root = "."

        with patch(
            "tapps_core.brain_bridge.check_brain_version",
            return_value={
                "ok": True,
                "skipped": True,
                "degraded": False,
                "url": "",
                "floor": "3.7.2",
                "ceiling": "4.0.0",
                "version": None,
                "errors": [],
                "warnings": [],
            },
        ):
            result = create_brain_bridge(settings)

        assert isinstance(result, HttpBrainBridge)

    def test_http_url_from_env_when_settings_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", "http://brain:9000")
        monkeypatch.delenv("TAPPS_BRAIN_DATABASE_URL", raising=False)
        from tapps_core.brain_bridge import HttpBrainBridge, create_brain_bridge

        with patch(
            "tapps_core.brain_bridge.check_brain_version",
            return_value={
                "ok": True,
                "skipped": True,
                "degraded": False,
                "url": "",
                "floor": "3.7.2",
                "ceiling": "4.0.0",
                "version": None,
                "errors": [],
                "warnings": [],
            },
        ):
            result = create_brain_bridge(settings=None)

        assert isinstance(result, HttpBrainBridge)

    def test_falls_back_to_inprocess_when_no_http_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", raising=False)
        monkeypatch.setenv("TAPPS_BRAIN_DATABASE_URL", "postgresql://x/db")
        from tapps_core.brain_bridge import BrainBridge, HttpBrainBridge, create_brain_bridge

        mock_brain = MagicMock()
        mock_brain.store.count.return_value = 0
        mock_brain.store.project_root = "."
        mock_brain.hive = None
        with patch("tapps_brain.AgentBrain", return_value=mock_brain):
            result = create_brain_bridge(settings=None)

        assert isinstance(result, BrainBridge)
        assert not isinstance(result, HttpBrainBridge)

    def test_returns_none_when_nothing_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", raising=False)
        monkeypatch.delenv("TAPPS_BRAIN_DATABASE_URL", raising=False)
        from tapps_core.brain_bridge import create_brain_bridge

        assert create_brain_bridge(settings=None) is None

    def test_http_url_takes_precedence_over_dsn(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", "http://brain:8080")
        monkeypatch.setenv("TAPPS_BRAIN_DATABASE_URL", "postgresql://x/db")
        from tapps_core.brain_bridge import HttpBrainBridge, create_brain_bridge

        with patch(
            "tapps_core.brain_bridge.check_brain_version",
            return_value={
                "ok": True,
                "skipped": True,
                "degraded": False,
                "url": "",
                "floor": "3.7.2",
                "ceiling": "4.0.0",
                "version": None,
                "errors": [],
                "warnings": [],
            },
        ):
            result = create_brain_bridge(settings=None)

        assert isinstance(result, HttpBrainBridge)


# ---------------------------------------------------------------------------
# HttpBrainBridge._do_mcp_post
# ---------------------------------------------------------------------------


class TestDoMcpPost:
    @pytest.mark.asyncio
    async def test_happy_path_returns_parsed_json(self) -> None:
        bridge = _make_http_bridge()
        response_data = _mcp_response({"results": [{"key": "k1", "value": "v1"}]})
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post(response_data)

        result = await bridge._do_mcp_post("memory_search", {"query": "test"})

        assert result == {"results": [{"key": "k1", "value": "v1"}]}

    @pytest.mark.asyncio
    async def test_rpc_error_raises(self) -> None:
        bridge = _make_http_bridge()
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post(
            {"jsonrpc": "2.0", "id": 1, "error": {"code": -32600, "message": "bad request"}}
        )

        with pytest.raises(RuntimeError, match="tapps-brain MCP RPC error"):
            await bridge._do_mcp_post("memory_search", {})

    @pytest.mark.asyncio
    async def test_out_of_profile_raises_tool_not_in_profile_error(self) -> None:
        """TAP-1616: ``-32602 INVALID_PARAMS`` with ``data.reason ==
        "out_of_profile"`` surfaces as :class:`ToolNotInProfileError` so
        callers can dispatch separately from a generic JSON-RPC error.
        """
        from tapps_core.brain_bridge import BrainMcpError, ToolNotInProfileError

        bridge = _make_http_bridge()
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "code": -32602,
                    "message": "tool is not in active profile",
                    "data": {
                        "reason": "out_of_profile",
                        "tool": "memory_save",
                        "profile": "agent_brain",
                    },
                },
            }
        )

        with pytest.raises(ToolNotInProfileError) as excinfo:
            await bridge._do_mcp_post("memory_save", {"key": "k", "value": "v"})

        exc = excinfo.value
        assert isinstance(exc, BrainMcpError)
        assert exc.code == -32602
        assert exc.tool == "memory_save"
        assert exc.profile == "agent_brain"
        assert isinstance(exc.data, dict)
        assert exc.data["reason"] == "out_of_profile"

    @pytest.mark.asyncio
    async def test_method_not_found_does_not_raise_profile_error(self) -> None:
        """TAP-1616: ``-32601 METHOD_NOT_FOUND`` means tool removed, NOT
        profile-gated. Must surface as plain ``BrainMcpError``.
        """
        from tapps_core.brain_bridge import BrainMcpError, ToolNotInProfileError

        bridge = _make_http_bridge()
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32601, "message": "Unknown tool: bogus_tool"},
            }
        )

        with pytest.raises(BrainMcpError) as excinfo:
            await bridge._do_mcp_post("bogus_tool", {})

        assert not isinstance(excinfo.value, ToolNotInProfileError)
        assert excinfo.value.code == -32601

    @pytest.mark.asyncio
    async def test_invalid_params_without_out_of_profile_reason(self) -> None:
        """TAP-1616: ``-32602`` without ``data.reason == "out_of_profile"``
        is a generic schema rejection, NOT a profile gate.
        """
        from tapps_core.brain_bridge import BrainMcpError, ToolNotInProfileError

        bridge = _make_http_bridge()
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "code": -32602,
                    "message": "validation",
                    "data": {"reason": "schema_mismatch"},
                },
            }
        )

        with pytest.raises(BrainMcpError) as excinfo:
            await bridge._do_mcp_post("memory_save", {})

        assert not isinstance(excinfo.value, ToolNotInProfileError)

    @pytest.mark.asyncio
    async def test_tool_error_raises(self) -> None:
        bridge = _make_http_bridge()
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "content": [{"type": "text", "text": "not found"}],
                    "isError": True,
                },
            }
        )

        with pytest.raises(RuntimeError, match="tapps-brain tool error"):
            await bridge._do_mcp_post("memory_get", {"key": "missing"})

    @pytest.mark.asyncio
    async def test_non_json_text_returned_as_value_dict(self) -> None:
        bridge = _make_http_bridge()
        bridge._session_id = "__test__"
        bridge._negotiated = True  # TAP-1629: skip capability handshake in this unit test
        bridge._http_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": "plain-text-not-json"}],
                "isError": False,
            },
        }
        bridge._http_client.post = AsyncMock(return_value=mock_resp)

        result = await bridge._do_mcp_post("memory_save", {})

        assert result == {"value": "plain-text-not-json"}

    @pytest.mark.asyncio
    async def test_http_4xx_raises(self) -> None:
        bridge = _make_http_bridge()
        bridge._session_id = "__test__"
        bridge._negotiated = True  # TAP-1629: skip capability handshake in this unit test
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post({}, status_code=401)

        with pytest.raises(RuntimeError, match="tapps-brain HTTP 401"):
            await bridge._do_mcp_post("memory_search", {})

    @pytest.mark.asyncio
    async def test_lazy_client_created_on_first_call(self) -> None:
        bridge = _make_http_bridge()
        assert bridge._http_client is None

        response_data = _mcp_response({"results": []})
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = _make_async_post(response_data)
            mock_cls.return_value = mock_client
            await bridge._do_mcp_post("memory_search", {"query": "q"})

        mock_cls.assert_called_once()
        assert bridge._http_client is not None


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


class TestHttpReadOps:
    @pytest.mark.asyncio
    async def test_search_returns_list(self) -> None:
        bridge = _make_http_bridge()
        entries = [{"key": "k1", "value": "v1"}, {"key": "k2", "value": "v2"}]
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post(_mcp_response(entries))

        result = await bridge.search("query", limit=5)

        assert result == entries

    @pytest.mark.asyncio
    async def test_search_unwraps_results_dict(self) -> None:
        bridge = _make_http_bridge()
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post(
            _mcp_response({"results": [{"key": "k1", "value": "v1"}]})
        )

        result = await bridge.search("query")

        assert result == [{"key": "k1", "value": "v1"}]

    @pytest.mark.asyncio
    async def test_get_returns_entry(self) -> None:
        bridge = _make_http_bridge()
        entry = {"key": "k1", "value": "v1", "tier": "pattern"}
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post(_mcp_response(entry))

        result = await bridge.get("k1")

        assert result == entry

    @pytest.mark.asyncio
    async def test_get_returns_none_when_no_key(self) -> None:
        bridge = _make_http_bridge()
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post(_mcp_response({}))

        result = await bridge.get("missing")

        assert result is None

    @pytest.mark.asyncio
    async def test_list_memories_returns_entries(self) -> None:
        bridge = _make_http_bridge()
        entries = [{"key": "k1", "value": "v1"}]
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post(_mcp_response({"entries": entries}))

        result = await bridge.list_memories(limit=10)

        assert result == entries

    @pytest.mark.asyncio
    async def test_recall_for_prompt_returns_string(self) -> None:
        bridge = _make_http_bridge()
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post(_mcp_response("- [k1] remembered value"))

        result = await bridge.recall_for_prompt("query")

        assert result == "- [k1] remembered value"

    @pytest.mark.asyncio
    async def test_recall_for_prompt_returns_none_on_empty(self) -> None:
        bridge = _make_http_bridge()
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post(_mcp_response(""))

        result = await bridge.recall_for_prompt("query")

        assert result is None

    @pytest.mark.asyncio
    async def test_hive_search_returns_list(self) -> None:
        bridge = _make_http_bridge()
        hits = [{"key": "h1", "value": "hive-value"}]
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post(_mcp_response(hits))

        result = await bridge.hive_search("query", limit=5)

        assert result == hits

    @pytest.mark.asyncio
    async def test_hive_status_returns_dict(self) -> None:
        bridge = _make_http_bridge()
        status_payload = {"enabled": True, "degraded": False, "namespace_count": 3}
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post(_mcp_response(status_payload))

        result = await bridge.hive_status(agent_id="test-agent")

        assert result == status_payload


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------


class TestHttpWriteOps:
    @pytest.mark.asyncio
    async def test_save_calls_memory_save_tool(self) -> None:
        bridge = _make_http_bridge()
        saved = {"key": "k1", "value": "v1", "tier": "pattern"}
        bridge._http_client = AsyncMock()
        post_mock = _make_async_post(_mcp_response(saved))
        bridge._http_client.post = post_mock

        result = await bridge.save("k1", "v1", tier="pattern")

        assert result == saved
        call_payload = post_mock.call_args[1]["json"]
        assert call_payload["params"]["name"] == "memory_save"
        assert call_payload["params"]["arguments"]["key"] == "k1"

    @pytest.mark.asyncio
    async def test_save_enqueues_when_circuit_open(self) -> None:
        bridge = _make_http_bridge()
        bridge._failures = 10
        bridge._open_at = asyncio.get_event_loop().time()

        result = await bridge.save("k1", "v1")

        assert result["degraded"] is True
        assert result["reason"] == "circuit open"
        assert bridge.queue_depth == 1

    @pytest.mark.asyncio
    async def test_delete_returns_true_on_success(self) -> None:
        bridge = _make_http_bridge()
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post(_mcp_response({"deleted": True}))

        result = await bridge.delete("k1")

        assert result is True

    @pytest.mark.asyncio
    async def test_reinforce_returns_dict(self) -> None:
        bridge = _make_http_bridge()
        entry = {"key": "k1", "confidence": 0.9}
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post(_mcp_response(entry))

        result = await bridge.reinforce("k1", boost=0.1)

        assert result == entry

    @pytest.mark.asyncio
    async def test_supersede_returns_dict(self) -> None:
        bridge = _make_http_bridge()
        entry = {"key": "k1", "value": "new-value"}
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post(_mcp_response(entry))

        result = await bridge.supersede("k1", "new-value")

        assert result == entry


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------


class TestHttpMaintenanceOps:
    @pytest.mark.asyncio
    async def test_gc_returns_dict(self) -> None:
        bridge = _make_http_bridge()
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post(_mcp_response({"archived_count": 3}))

        result = await bridge.gc()

        assert result["archived_count"] == 3

    @pytest.mark.asyncio
    async def test_consolidate_returns_dict(self) -> None:
        bridge = _make_http_bridge()
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post(_mcp_response({"groups_found": 2}))

        result = await bridge.consolidate()

        assert result["groups_found"] == 2


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class TestHttpCircuitBreaker:
    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold_failures(self) -> None:
        bridge = _make_http_bridge()
        bridge._http_client = AsyncMock()
        bridge._http_client.post = AsyncMock(
            side_effect=httpx.ConnectError("refused", request=MagicMock())
        )

        for _ in range(3):
            with pytest.raises((Exception,)):
                await bridge._http_mcp_call("memory_search", {"query": "q"})

        assert bridge.circuit_open

    @pytest.mark.asyncio
    async def test_open_circuit_raises_immediately(self) -> None:
        import time

        bridge = _make_http_bridge()
        bridge._failures = 10
        bridge._open_at = time.monotonic()

        with pytest.raises(Exception, match="circuit open"):
            await bridge._http_mcp_call("memory_search", {"query": "q"})


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------


class TestHttpRetry:
    @pytest.mark.asyncio
    async def test_retries_on_transient_error_then_succeeds(self) -> None:
        bridge = _make_http_bridge()
        # Pre-populate the session so _ensure_session() short-circuits
        # and the retry test only counts tools/call POSTs (TAP-836). TAP-1629
        # extended _ensure_session to also run capability negotiation on the
        # first call — flag it as done so this retry test isolates the
        # tools/call retry loop.
        bridge._session_id = "__test__"
        bridge._negotiated = True
        response_data = _mcp_response({"results": []})
        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.raise_for_status = MagicMock()
        ok_response.json.return_value = response_data

        call_count = 0

        async def _flaky_post(*_args: Any, **_kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.ConnectError("transient", request=MagicMock())
            return ok_response

        bridge._http_client = AsyncMock()
        bridge._http_client.post = _flaky_post

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await bridge._http_mcp_call("memory_search", {"query": "q"})

        assert result == {"results": []}
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_exhausted_retries_raise_unavailable(self) -> None:
        bridge = _make_http_bridge()
        bridge._http_client = AsyncMock()
        bridge._http_client.post = AsyncMock(
            side_effect=httpx.ConnectError("refused", request=MagicMock())
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            from tapps_core.brain_bridge import BrainBridgeUnavailable

            with pytest.raises(BrainBridgeUnavailable, match="all retries exhausted"):
                await bridge._http_mcp_call("memory_search", {"query": "q"})

    @pytest.mark.asyncio
    async def test_tool_not_in_profile_skips_retry(self) -> None:
        """TAP-1616: a profile gate is a permanent server decision —
        ``_http_mcp_call`` must propagate :class:`ToolNotInProfileError`
        on the first attempt without exhausting the retry budget.
        """
        from tapps_core.brain_bridge import ToolNotInProfileError

        bridge = _make_http_bridge()
        bridge._session_id = "__test__"
        bridge._negotiated = True  # TAP-1629: skip capability handshake
        # Pretend the wire knows about memory_save so the client-side
        # short-circuit does not fire — this test is about the wire-level
        # error path, not the preflight ProfileMismatchError path.
        bridge._exposed_tools = frozenset({"memory_save"})

        gated_response = MagicMock()
        gated_response.status_code = 200
        gated_response.raise_for_status = MagicMock()
        gated_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {
                "code": -32602,
                "message": "tool is not in active profile",
                "data": {
                    "reason": "out_of_profile",
                    "tool": "memory_save",
                    "profile": "agent_brain",
                },
            },
        }
        call_count = 0

        async def _gated_post(*_args: Any, **_kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            return gated_response

        bridge._http_client = AsyncMock()
        bridge._http_client.post = _gated_post

        with pytest.raises(ToolNotInProfileError):
            await bridge._http_mcp_call("memory_save", {"key": "k", "value": "v"})

        # No retries: one and only one tools/call POST and the circuit
        # breaker is undisturbed.
        assert call_count == 1
        assert bridge._failures == 0
        assert not bridge.circuit_open


# ---------------------------------------------------------------------------
# Offline write queue / drain_blocking
# ---------------------------------------------------------------------------


class TestHttpWriteQueue:
    def test_drain_blocking_posts_queued_entries(self) -> None:
        bridge = _make_http_bridge()
        bridge._failures = 10
        bridge._open_at = __import__("time").monotonic()

        # Enqueue by calling save while circuit is open
        loop = asyncio.new_event_loop()
        loop.run_until_complete(bridge.save("k1", "v1"))
        loop.run_until_complete(bridge.save("k2", "v2"))
        loop.close()

        assert bridge.queue_depth == 2

        with patch("httpx.post") as mock_post:
            mock_post.return_value = MagicMock()
            result = bridge.drain_blocking(timeout=5.0)

        assert result["drained"] == 2
        assert result["dropped"] == 0
        assert bridge.queue_depth == 0

    def test_drain_blocking_counts_dropped_on_http_error(self) -> None:
        bridge = _make_http_bridge()
        loop = asyncio.new_event_loop()
        bridge._failures = 10
        bridge._open_at = __import__("time").monotonic()
        loop.run_until_complete(bridge.save("k1", "v1"))
        loop.close()

        with patch("httpx.post", side_effect=httpx.ConnectError("refused", request=MagicMock())):
            result = bridge.drain_blocking(timeout=5.0)

        assert result["dropped"] == 1
        assert result["drained"] == 0


# ---------------------------------------------------------------------------
# MCP session lifecycle (TAP-836)
# ---------------------------------------------------------------------------


class TestHttpSessionLifecycle:
    """Brain 3.10.3+ requires initialize → Mcp-Session-Id → tools/call."""

    @pytest.mark.asyncio
    async def test_initialize_called_on_first_tool_invocation(self) -> None:
        """TAP-836 initialize handshake + TAP-1629 capability negotiation.

        First tool invocation now triggers four POSTs in order:
          1. ``initialize`` (returns Mcp-Session-Id)
          2. ``tools/list`` (capability negotiation — fills ``_exposed_tools``)
          3. ``tools/call profile_info`` (negotiation — fills ``_memory_profile``)
          4. ``tools/call memory_list`` (the actual user call)
        """
        bridge = _make_http_bridge()
        init_response = MagicMock()
        init_response.status_code = 200
        init_response.headers = {"mcp-session-id": "sess-abc"}
        init_response.raise_for_status = MagicMock()
        init_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": {}}

        tools_list_response = MagicMock()
        tools_list_response.status_code = 200
        tools_list_response.raise_for_status = MagicMock()
        tools_list_response.json.return_value = _tools_list_response(_FULL_PROFILE_TOOLS)

        profile_info_response = MagicMock()
        profile_info_response.status_code = 200
        profile_info_response.raise_for_status = MagicMock()
        profile_info_response.json.return_value = _profile_info_response()

        tool_response = MagicMock()
        tool_response.status_code = 200
        tool_response.raise_for_status = MagicMock()
        tool_response.json.return_value = _mcp_response({"ok": True})

        post_mock = AsyncMock(
            side_effect=[
                init_response,
                tools_list_response,
                profile_info_response,
                tool_response,
            ]
        )
        bridge._http_client = AsyncMock()
        bridge._http_client.post = post_mock

        await bridge._http_mcp_call("memory_list", {"limit": 1})

        assert bridge._session_id == "sess-abc"
        assert post_mock.await_count == 4
        init_call = post_mock.await_args_list[0]
        tools_list_call = post_mock.await_args_list[1]
        profile_info_call = post_mock.await_args_list[2]
        tool_call = post_mock.await_args_list[3]
        assert init_call.kwargs["json"]["method"] == "initialize"
        assert tools_list_call.kwargs["json"]["method"] == "tools/list"
        assert profile_info_call.kwargs["json"]["params"]["name"] == "profile_info"
        # Session id threaded into the subsequent tools/call.
        assert tool_call.kwargs["headers"]["Mcp-Session-Id"] == "sess-abc"
        # Negotiation cache is populated.
        assert "memory_list" in (bridge._exposed_tools or set())

    @pytest.mark.asyncio
    async def test_second_tool_call_reuses_cached_session(self) -> None:
        bridge = _make_http_bridge()
        bridge._session_id = "cached-sess"
        bridge._negotiated = True  # TAP-1629: pretend negotiation already ran

        tool_response = MagicMock()
        tool_response.status_code = 200
        tool_response.raise_for_status = MagicMock()
        tool_response.json.return_value = _mcp_response({"ok": True})
        post_mock = AsyncMock(return_value=tool_response)
        bridge._http_client = AsyncMock()
        bridge._http_client.post = post_mock

        await bridge._http_mcp_call("memory_list", {"limit": 1})

        # No initialize call; session was already cached.
        assert post_mock.await_count == 1
        assert post_mock.await_args.kwargs["headers"]["Mcp-Session-Id"] == "cached-sess"

    @pytest.mark.asyncio
    async def test_400_triggers_session_refresh(self) -> None:
        bridge = _make_http_bridge()
        bridge._session_id = "stale-sess"
        bridge._negotiated = True  # TAP-1629: skip negotiation; isolate refresh path

        stale_response = MagicMock()
        stale_response.status_code = 400
        init_response = MagicMock()
        init_response.status_code = 200
        init_response.headers = {"mcp-session-id": "fresh-sess"}
        init_response.raise_for_status = MagicMock()
        init_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": {}}
        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.raise_for_status = MagicMock()
        ok_response.json.return_value = _mcp_response({"ok": True})

        bridge._http_client = AsyncMock()
        bridge._http_client.post = AsyncMock(
            side_effect=[stale_response, init_response, ok_response]
        )

        await bridge._http_mcp_call("memory_list", {"limit": 1})

        assert bridge._session_id == "fresh-sess"

    @pytest.mark.asyncio
    async def test_close_clears_session_id(self) -> None:
        bridge = _make_http_bridge()
        bridge._session_id = "to-clear"
        bridge._http_client = AsyncMock()
        # Simulate closed loop so close() doesn't try to aclose the client.
        bridge._http_client.aclose = AsyncMock()

        bridge.close(drain_timeout=0.1)

        assert bridge._session_id is None

    @pytest.mark.asyncio
    async def test_no_session_header_becomes_sentinel(self) -> None:
        """Older brains don't return Mcp-Session-Id. Sentinel avoids re-handshake.

        Negotiation (TAP-1629) still runs after init even on no-session brains;
        the side_effect therefore covers init → tools/list → profile_info →
        tools/call.
        """
        bridge = _make_http_bridge()
        init_response = MagicMock()
        init_response.status_code = 200
        init_response.headers = {}
        init_response.raise_for_status = MagicMock()
        init_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": {}}

        tools_list_response = MagicMock()
        tools_list_response.status_code = 200
        tools_list_response.raise_for_status = MagicMock()
        tools_list_response.json.return_value = _tools_list_response(_FULL_PROFILE_TOOLS)

        profile_info_response = MagicMock()
        profile_info_response.status_code = 200
        profile_info_response.raise_for_status = MagicMock()
        profile_info_response.json.return_value = _profile_info_response()

        tool_response = MagicMock()
        tool_response.status_code = 200
        tool_response.raise_for_status = MagicMock()
        tool_response.json.return_value = _mcp_response({"ok": True})

        bridge._http_client = AsyncMock()
        bridge._http_client.post = AsyncMock(
            side_effect=[
                init_response,
                tools_list_response,
                profile_info_response,
                tool_response,
            ]
        )

        await bridge._http_mcp_call("memory_list", {"limit": 1})

        assert bridge._session_id == "__no_session__"


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


class TestHttpHealthCheck:
    def test_ok_when_health_returns_200(self) -> None:
        bridge = _make_http_bridge("http://brain:8080")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"status": "ok", "version": "3.8.0"}

        with patch("httpx.get", return_value=mock_response):
            result = bridge.health_check()

        assert result["ok"] is True
        assert result["details"]["mode"] == "http"
        assert result["details"]["brain_version"] == "3.8.0"

    def test_error_when_health_request_fails(self) -> None:
        bridge = _make_http_bridge("http://brain:8080")

        with patch("httpx.get", side_effect=httpx.ConnectError("refused", request=MagicMock())):
            result = bridge.health_check()

        assert result["ok"] is False
        assert result["errors"]

    def test_strip_trailing_slash_from_url(self) -> None:
        bridge = _make_http_bridge("http://brain:8080/")
        assert bridge._http_url == "http://brain:8080"


# ---------------------------------------------------------------------------
# store property
# ---------------------------------------------------------------------------


class TestHttpStoreProperty:
    def test_store_returns_none(self) -> None:
        bridge = _make_http_bridge()
        assert bridge.store is None


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


class TestHttpClose:
    def test_close_releases_client(self) -> None:
        bridge = _make_http_bridge()
        mock_client = AsyncMock()
        bridge._http_client = mock_client

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.is_closed.return_value = False
            mock_loop.return_value.run_until_complete = MagicMock()
            bridge.close()

        assert bridge._http_client is None

    def test_close_handles_missing_event_loop(self) -> None:
        bridge = _make_http_bridge()
        bridge._http_client = AsyncMock()

        with patch("asyncio.get_event_loop", side_effect=RuntimeError("no loop")):
            bridge.close()  # should not raise

        assert bridge._http_client is None


# ---------------------------------------------------------------------------
# is_http_mode flag
# ---------------------------------------------------------------------------


class TestHttpModeFlag:
    def test_is_http_mode_true(self) -> None:
        bridge = _make_http_bridge()
        assert bridge.is_http_mode is True

    def test_inprocess_bridge_has_no_is_http_mode(self) -> None:
        from tapps_core.brain_bridge import BrainBridge

        brain = MagicMock()
        brain.store.count.return_value = 0
        bridge = BrainBridge(brain)
        assert not getattr(bridge, "is_http_mode", False)


# ---------------------------------------------------------------------------
# TAP-1629: profile negotiation + ProfileMismatchError short-circuit
# ---------------------------------------------------------------------------


_FULL_PROFILE_TOOLS = [
    "memory_save",
    "memory_get",
    "memory_delete",
    "memory_search",
    "memory_list",
    "memory_recall",
    "memory_reinforce",
    "memory_supersede",
    "memory_save_many",
    "memory_recall_many",
    "memory_reinforce_many",
    "memory_index_session",
    "memory_search_sessions",
    "memory_capture",
    "feedback_rate",
    "feedback_gap",
    "profile_info",
    "profile_switch",
    "hive_status",
    "hive_search",
    "hive_propagate",
    "agent_register",
    "memory_find_related",
    "memory_relations",
    "brain_get_neighbors",
    "brain_explain_connection",
]

_CODER_PROFILE_TOOLS = [
    "brain_remember",
    "brain_recall",
    "brain_forget",
    "brain_status",
    "memory_reinforce",
    "memory_index_session",
    "memory_search_sessions",
    "memory_capture",
    "feedback_rate",
    "feedback_gap",
    "hive_search",
    "memory_find_related",
    "brain_get_neighbors",
    "brain_explain_connection",
]


def _tools_list_response(names: list[str]) -> dict[str, Any]:
    """Build a fake JSON-RPC ``tools/list`` response."""
    return {
        "jsonrpc": "2.0",
        "id": "negotiate_tools",
        "result": {"tools": [{"name": n} for n in names]},
    }


def _profile_info_response(profile_name: str = "repo-brain") -> dict[str, Any]:
    payload = {"name": profile_name, "version": "1.1", "layers": []}
    return {
        "jsonrpc": "2.0",
        "id": "negotiate_profile",
        "result": {
            "content": [{"type": "text", "text": json.dumps(payload)}],
            "isError": False,
        },
    }


def _negotiation_post(tools: list[str], profile_name: str = "repo-brain") -> AsyncMock:
    """AsyncMock that dispatches tools/list vs tools/call responses by method.

    Returns the right canned response based on the ``method`` field of the
    JSON-RPC request body so the same mock can serve multiple distinct
    requests in one negotiation pass.
    """

    async def _post(url: str, **kwargs: Any) -> MagicMock:
        body = kwargs.get("json", {})
        method = body.get("method")
        params = body.get("params") or {}
        name = params.get("name") if isinstance(params, dict) else None
        response = MagicMock()
        response.status_code = 200
        response.raise_for_status = MagicMock()
        if method == "tools/list":
            response.json.return_value = _tools_list_response(tools)
        elif method == "tools/call" and name == "profile_info":
            response.json.return_value = _profile_info_response(profile_name)
        else:
            response.json.return_value = _mcp_response({"ok": True})
        return response

    return AsyncMock(side_effect=_post)


class TestProfileMismatchError:
    """ProfileMismatchError is the typed exception agents catch (TAP-1629)."""

    def test_is_subclass_of_tool_not_in_profile(self) -> None:
        from tapps_core.brain_bridge import ProfileMismatchError, ToolNotInProfileError

        assert issubclass(ProfileMismatchError, ToolNotInProfileError)

    def test_carries_out_of_profile_reason_with_preflight_transport(self) -> None:
        from tapps_core.brain_bridge import ProfileMismatchError

        exc = ProfileMismatchError(
            "denied",
            tool="memory_save",
            profile="coder",
            exposed_tools=frozenset({"brain_remember"}),
        )
        assert exc.tool == "memory_save"
        assert exc.profile == "coder"
        assert exc.code == -32602
        assert isinstance(exc.data, dict)
        assert exc.data["reason"] == "out_of_profile"
        assert exc.data["transport"] == "client_preflight"
        assert exc.exposed_tools == frozenset({"brain_remember"})

    def test_classify_mcp_error_treats_profile_mismatch_as_gated(self) -> None:
        """ProfileMismatchError must classify as ``gated`` so existing degraded
        paths (gc, consolidate) keep working with the preflight error.
        """
        from tapps_core.brain_bridge import ProfileMismatchError, _classify_mcp_error

        exc = ProfileMismatchError("denied", tool="memory_save", profile="coder")
        assert _classify_mcp_error(exc) == "gated"


class TestNegotiateProfile:
    """Capability negotiation populates exposed_tools + memory_profile."""

    @pytest.mark.asyncio
    async def test_full_profile_populates_exposed_tools(self) -> None:
        bridge = _make_http_bridge()
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _negotiation_post(_FULL_PROFILE_TOOLS)
        bridge._session_id = "test-session"

        await bridge._negotiate_profile_locked()

        assert bridge._negotiated is True
        assert bridge._exposed_tools is not None
        assert "memory_save" in bridge._exposed_tools
        assert "agent_register" in bridge._exposed_tools
        assert bridge._memory_profile == {
            "name": "repo-brain",
            "version": "1.1",
            "layers": [],
        }
        assert bridge._negotiation_error is None

    @pytest.mark.asyncio
    async def test_coder_profile_marks_bridge_tools_as_gated(self) -> None:
        from tapps_core.brain_bridge import _BRIDGE_USED_TOOLS

        bridge = _make_http_bridge(
            headers={"Authorization": "Bearer t", "X-Brain-Profile": "coder"}
        )
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _negotiation_post(_CODER_PROFILE_TOOLS)
        bridge._session_id = "test-session"

        await bridge._negotiate_profile_locked()

        status = bridge.profile_status()
        assert status["negotiated"] is True
        assert status["declared_profile"] == "coder"
        assert status["memory_profile_name"] == "repo-brain"
        # The seven gated-write tools called out in TAP-1629 must surface.
        for required_gated in (
            "memory_save",
            "memory_get",
            "memory_delete",
            "memory_search",
            "memory_list",
            "memory_supersede",
            "agent_register",
        ):
            assert required_gated in status["gated_used_tools"], required_gated
            assert required_gated in _BRIDGE_USED_TOOLS, required_gated
        assert status["profile_mismatch"] is True

    @pytest.mark.asyncio
    async def test_tools_list_failure_leaves_short_circuit_disabled(self) -> None:
        """A flaky brain must not block legitimate calls — when tools/list
        fails the bridge falls back to the wire as authoritative.
        """
        bridge = _make_http_bridge()
        bridge._http_client = AsyncMock()

        async def _post(url: str, **kwargs: Any) -> MagicMock:
            raise httpx.ConnectError("brain unreachable")

        bridge._http_client.post = AsyncMock(side_effect=_post)
        bridge._session_id = "test-session"

        await bridge._negotiate_profile_locked()

        assert bridge._negotiated is True
        assert bridge._exposed_tools is None
        assert bridge._negotiation_error is not None
        assert "tools_list_failed" in bridge._negotiation_error
        status = bridge.profile_status()
        assert status["profile_mismatch"] is False  # no data, no mismatch claim
        assert status["gated_used_tools"] == []

    @pytest.mark.asyncio
    async def test_empty_tools_list_is_treated_as_anomaly(self) -> None:
        """A response with zero tools is structurally impossible on a healthy
        brain (even coder exposes brain_*). Treat it as a negotiation failure
        instead of caching an empty allow-list that would short-circuit
        everything.
        """
        bridge = _make_http_bridge()
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _negotiation_post([])
        bridge._session_id = "test-session"

        await bridge._negotiate_profile_locked()

        assert bridge._negotiated is True
        assert bridge._exposed_tools is None
        assert bridge._negotiation_error == "tools_list_empty"


class TestProfileMismatchShortCircuit:
    """``_do_mcp_post`` short-circuits gated bridge tools with the typed error."""

    @pytest.mark.asyncio
    async def test_gated_bridge_tool_raises_profile_mismatch_before_wire(self) -> None:
        from tapps_core.brain_bridge import ProfileMismatchError

        bridge = _make_http_bridge(
            headers={"Authorization": "Bearer t", "X-Brain-Profile": "coder"}
        )
        bridge._http_client = AsyncMock()
        # No further post() will be made — the short-circuit fires before any
        # tools/call goes over the wire.
        bridge._http_client.post = AsyncMock(
            side_effect=AssertionError("post must not be called for gated tools")
        )
        bridge._session_id = "test-session"
        bridge._exposed_tools = frozenset(_CODER_PROFILE_TOOLS)
        bridge._negotiated = True

        with pytest.raises(ProfileMismatchError) as excinfo:
            await bridge._do_mcp_post("memory_save", {"key": "k", "value": "v"})

        assert excinfo.value.tool == "memory_save"
        assert excinfo.value.profile == "coder"
        # Bridge already knew the tool would be denied — the short-circuit
        # MUST not call out to the wire.
        bridge._http_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_exposed_bridge_tool_passes_through(self) -> None:
        bridge = _make_http_bridge()
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post(_mcp_response({"key": "k1", "value": "v1"}))
        bridge._session_id = "test-session"
        bridge._exposed_tools = frozenset(_FULL_PROFILE_TOOLS)
        bridge._negotiated = True

        result = await bridge._do_mcp_post("memory_save", {"key": "k1", "value": "v1"})

        assert result == {"key": "k1", "value": "v1"}

    @pytest.mark.asyncio
    async def test_unknown_tool_is_not_short_circuited(self) -> None:
        """Tools outside ``_BRIDGE_USED_TOOLS`` are not gated client-side —
        the wire stays authoritative for anything we have not enumerated.
        """
        bridge = _make_http_bridge()
        bridge._http_client = AsyncMock()
        bridge._http_client.post = _make_async_post(_mcp_response({"ok": True}))
        bridge._session_id = "test-session"
        bridge._exposed_tools = frozenset({"only_other_tool"})
        bridge._negotiated = True

        # ``maintenance_gc`` is invoked by HttpBrainBridge.gc() but is NOT in
        # _BRIDGE_USED_TOOLS — it has a degraded fallback. The short-circuit
        # must not fire for it.
        result = await bridge._do_mcp_post("maintenance_gc", {})

        assert result == {"ok": True}


class TestProfileStatusShape:
    """``profile_status`` returns a stable shape before and after negotiation."""

    def test_before_negotiation_returns_empty_shape(self) -> None:
        from tapps_core.brain_bridge import _BRIDGE_USED_TOOLS

        bridge = _make_http_bridge()
        status = bridge.profile_status()
        assert status["negotiated"] is False
        assert status["exposed_tools"] == []
        assert status["gated_used_tools"] == []
        assert status["profile_mismatch"] is False
        assert status["memory_profile_name"] is None
        assert status["bridge_used_tools"] == sorted(_BRIDGE_USED_TOOLS)

    def test_after_negotiation_lists_gated_subset(self) -> None:
        bridge = _make_http_bridge(
            headers={"Authorization": "Bearer t", "X-Brain-Profile": "coder"}
        )
        bridge._exposed_tools = frozenset(_CODER_PROFILE_TOOLS)
        bridge._memory_profile = {"name": "repo-brain"}
        bridge._negotiated = True
        status = bridge.profile_status()
        assert status["negotiated"] is True
        assert status["declared_profile"] == "coder"
        assert status["memory_profile_name"] == "repo-brain"
        assert "memory_save" in status["gated_used_tools"]
        assert status["profile_mismatch"] is True
