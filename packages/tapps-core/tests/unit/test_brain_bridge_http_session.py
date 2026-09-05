"""Tests for tapps_core.brain_bridge_http_session — session handshake,
capability negotiation, and raw POST layer for HttpBrainBridge.

Split out of test_brain_bridge_http.py alongside the TAP-6736 megafile split
(and its own further split into session/health/memory/kg_hive mixins).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tapps_core.brain_bridge import HttpBrainBridge
from tapps_core.brain_bridge_errors import BadJsonError, BrainMcpError, ToolNotInProfileError


def _make_bridge() -> HttpBrainBridge:
    return HttpBrainBridge("http://brain:8080", {"Authorization": "Bearer t"})


def _mock_response(payload: dict[str, Any], *, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    resp.headers = {}
    resp.raise_for_status = MagicMock()
    return resp


class TestCheckToolsWarmCache:
    def test_no_cache_dir_returns_none(self) -> None:
        bridge = _make_bridge()
        assert bridge._tools_cache_dir is None
        assert bridge._check_tools_warm_cache() is None


class TestRaiseForRpcError:
    def test_bad_json_raises_bad_json_error(self) -> None:
        bridge = _make_bridge()
        rpc_error = {
            "code": -32602,
            "data": {"error": "bad_json", "field": "payload_json", "detail": "boom"},
        }
        with pytest.raises(BadJsonError) as exc_info:
            bridge._raise_for_rpc_error(rpc_error, "memory_save")
        assert exc_info.value.field == "payload_json"

    def test_out_of_profile_raises_tool_not_in_profile(self) -> None:
        bridge = _make_bridge()
        rpc_error = {
            "code": -32602,
            "data": {"reason": "out_of_profile", "tool": "memory_save", "profile": "reviewer"},
        }
        with pytest.raises(ToolNotInProfileError) as exc_info:
            bridge._raise_for_rpc_error(rpc_error, "memory_save")
        assert exc_info.value.tool == "memory_save"

    def test_other_error_raises_brain_mcp_error(self) -> None:
        bridge = _make_bridge()
        with pytest.raises(BrainMcpError):
            bridge._raise_for_rpc_error({"code": -32601, "message": "gone"}, "removed_tool")


class TestRaiseForErrorResult:
    def test_parses_out_of_profile_text_message(self) -> None:
        bridge = _make_bridge()
        result = {
            "content": [
                {"type": "text", "text": "Tool 'memory_save' is not available in profile 'reviewer'."}
            ]
        }
        with pytest.raises(ToolNotInProfileError):
            bridge._raise_for_error_result(result, "memory_save")

    def test_generic_message_raises_runtime_error(self) -> None:
        bridge = _make_bridge()
        result = {"content": [{"type": "text", "text": "something broke"}]}
        with pytest.raises(RuntimeError):
            bridge._raise_for_error_result(result, "memory_save")


class TestDoMcpPost:
    @pytest.mark.asyncio
    async def test_happy_path_returns_decoded_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        bridge = _make_bridge()
        bridge._http_client = MagicMock()
        bridge._session_id = "sess-1"
        bridge._negotiated = True
        payload = {"key": "k", "value": "v"}
        response = _mock_response(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"content": [{"type": "text", "text": json.dumps(payload)}]},
            }
        )
        bridge._http_client.post = AsyncMock(return_value=response)
        result = await bridge._do_mcp_post("memory_get", {"key": "k"})
        assert result == payload

    @pytest.mark.asyncio
    async def test_retries_once_on_session_rejection(self) -> None:
        bridge = _make_bridge()
        bridge._http_client = MagicMock()
        bridge._session_id = "stale-session"
        bridge._negotiated = True

        rejected = _mock_response({}, status_code=404)
        ok = _mock_response(
            {"jsonrpc": "2.0", "id": 1, "result": {"content": [], "isError": False}}
        )

        async def _post(*args: Any, **kwargs: Any) -> MagicMock:
            if bridge._session_id == "stale-session":
                return rejected
            return ok

        bridge._http_client.post = AsyncMock(side_effect=_post)

        async def _ensure_session() -> str:
            bridge._session_id = "fresh-session"
            return "fresh-session"

        monkeypatch_target = bridge._ensure_session
        bridge._ensure_session = AsyncMock(side_effect=_ensure_session)
        try:
            result = await bridge._do_mcp_post("memory_get", {"key": "k"})
        finally:
            bridge._ensure_session = monkeypatch_target
        assert result == {"content": [], "isError": False}
        assert bridge._session_id == "fresh-session"


class TestVersionCheckDefaults:
    def test_new_bridge_has_skipped_version_check(self) -> None:
        bridge = _make_bridge()
        assert bridge.version_check["skipped"] is True
        assert bridge.version_check["ok"] is True
