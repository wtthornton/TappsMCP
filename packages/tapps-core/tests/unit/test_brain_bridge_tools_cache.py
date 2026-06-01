"""Unit tests for TAP-1927 — tools-list warm-cache in HttpBrainBridge.

Coverage:
- ``_read_tools_warm_cache``: returns frozenset on valid/fresh file
- ``_read_tools_warm_cache``: returns None on missing file
- ``_read_tools_warm_cache``: returns None when TTL is exceeded
- ``_read_tools_warm_cache``: returns None on malformed JSON
- ``_write_tools_warm_cache``: writes the expected JSON payload
- ``_write_tools_warm_cache``: silently swallows write errors
- ``_negotiate_profile_locked`` warm-cache hit: skips live MCP tools/list POST
- ``_negotiate_profile_locked`` warm-cache miss: falls through to live POST,
  writes cache on success
- ``_negotiate_profile_locked`` stale cache: falls through to live POST
- ``HttpBrainBridge`` constructor: ``cache_dir`` attribute set correctly
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bridge(cache_dir: Path | None = None) -> Any:
    from tapps_core.brain_bridge import HttpBrainBridge

    return HttpBrainBridge(
        "http://brain:8080",
        {"Authorization": "Bearer test-token"},
        cache_dir=cache_dir,
    )


def _make_tools_post_mock(tool_names: list[str], *, status_code: int = 200) -> AsyncMock:
    """Return an AsyncMock for httpx.AsyncClient.post that returns a tools/list payload."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = {
        "jsonrpc": "2.0",
        "id": "negotiate_tools",
        "result": {
            "tools": [{"name": n} for n in tool_names],
        },
    }
    mock_response.raise_for_status = MagicMock()
    return AsyncMock(return_value=mock_response)


def _write_cache_file(path: Path, tool_names: list[str]) -> None:
    """Write a well-formed tools cache file to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"tools": [{"name": n} for n in tool_names]}),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# _read_tools_warm_cache — pure function unit tests
# ---------------------------------------------------------------------------


class TestReadToolsWarmCache:
    def test_returns_frozenset_on_fresh_valid_file(self, tmp_path: Path) -> None:
        from tapps_core.brain_bridge import _read_tools_warm_cache

        cache_file = tmp_path / ".brain-tools-list..json"
        _write_cache_file(cache_file, ["brain_status", "memory_save"])

        result = _read_tools_warm_cache(cache_file)

        assert result == frozenset({"brain_status", "memory_save"})

    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        from tapps_core.brain_bridge import _read_tools_warm_cache

        result = _read_tools_warm_cache(tmp_path / "no-such-file.json")

        assert result is None

    def test_returns_none_when_ttl_expired(self, tmp_path: Path) -> None:
        from tapps_core.brain_bridge import _TOOLS_CACHE_TTL_SECONDS, _read_tools_warm_cache

        cache_file = tmp_path / ".brain-tools-list..json"
        _write_cache_file(cache_file, ["brain_status"])

        # Back-date the file's mtime to simulate an expired cache.
        expired_mtime = time.time() - _TOOLS_CACHE_TTL_SECONDS - 1
        import os

        os.utime(cache_file, (expired_mtime, expired_mtime))

        result = _read_tools_warm_cache(cache_file)

        assert result is None

    def test_returns_none_on_malformed_json(self, tmp_path: Path) -> None:
        from tapps_core.brain_bridge import _read_tools_warm_cache

        cache_file = tmp_path / ".brain-tools-list..json"
        cache_file.write_text("not-json", encoding="utf-8")

        result = _read_tools_warm_cache(cache_file)

        assert result is None

    def test_returns_none_when_tools_list_empty(self, tmp_path: Path) -> None:
        from tapps_core.brain_bridge import _read_tools_warm_cache

        cache_file = tmp_path / ".brain-tools-list..json"
        cache_file.write_text(json.dumps({"tools": []}), encoding="utf-8")

        result = _read_tools_warm_cache(cache_file)

        assert result is None

    def test_returns_none_when_payload_is_not_dict(self, tmp_path: Path) -> None:
        from tapps_core.brain_bridge import _read_tools_warm_cache

        cache_file = tmp_path / ".brain-tools-list..json"
        cache_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

        result = _read_tools_warm_cache(cache_file)

        assert result is None

    def test_filters_out_entries_missing_name(self, tmp_path: Path) -> None:
        from tapps_core.brain_bridge import _read_tools_warm_cache

        cache_file = tmp_path / ".brain-tools-list..json"
        cache_file.write_text(
            json.dumps({"tools": [{"name": "brain_status"}, {"no_name": True}, {"name": ""}]}),
            encoding="utf-8",
        )

        result = _read_tools_warm_cache(cache_file)

        assert result == frozenset({"brain_status"})


# ---------------------------------------------------------------------------
# _write_tools_warm_cache — pure function unit tests
# ---------------------------------------------------------------------------


class TestWriteToolsWarmCache:
    def test_writes_expected_json(self, tmp_path: Path) -> None:
        from tapps_core.brain_bridge import _write_tools_warm_cache

        cache_file = tmp_path / "sub" / ".brain-tools-list..json"
        tool_names: frozenset[str] = frozenset({"memory_save", "brain_status"})

        _write_tools_warm_cache(cache_file, tool_names)

        assert cache_file.exists()
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        written_names = {t["name"] for t in payload["tools"]}
        assert written_names == tool_names

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        from tapps_core.brain_bridge import _write_tools_warm_cache

        nested = tmp_path / "a" / "b" / "c" / "cache.json"
        _write_tools_warm_cache(nested, frozenset({"tool_x"}))

        assert nested.exists()

    def test_silent_on_write_error(self, tmp_path: Path) -> None:
        """Writing to an unwritable path must not raise."""
        from tapps_core.brain_bridge import _write_tools_warm_cache

        _write_tools_warm_cache(Path("/no/such/path/cache.json"), frozenset({"tool_x"}))
        # No exception → test passes


# ---------------------------------------------------------------------------
# HttpBrainBridge constructor
# ---------------------------------------------------------------------------


class TestHttpBrainBridgeCacheDir:
    def test_cache_dir_stored_on_bridge(self, tmp_path: Path) -> None:
        bridge = _make_bridge(cache_dir=tmp_path)
        assert bridge._tools_cache_dir == tmp_path

    def test_cache_dir_none_when_not_supplied(self) -> None:
        bridge = _make_bridge()
        assert bridge._tools_cache_dir is None


# ---------------------------------------------------------------------------
# _negotiate_profile_locked — integration tests (async)
# ---------------------------------------------------------------------------


class TestNegotiateProfileLockedCache:
    """Drive ``_negotiate_profile_locked`` directly to verify cache behaviour."""

    def _bridge_with_mock_client(
        self,
        cache_dir: Path | None,
        post_mock: AsyncMock,
        profile: str = "",
    ) -> Any:
        """Return a bridge whose httpx client is replaced by *post_mock*.

        Sets ``_session_id`` so the method can proceed past the early-return guard.
        """
        headers: dict[str, str] = {"Authorization": "Bearer test"}
        if profile:
            headers["X-Brain-Profile"] = profile

        bridge = _make_bridge(cache_dir=cache_dir)
        bridge._http_headers = headers
        bridge._session_id = "test-session-id"

        mock_client = MagicMock()
        mock_client.post = post_mock
        bridge._http_client = mock_client
        return bridge

    @pytest.mark.asyncio
    async def test_warm_hit_skips_live_post(self, tmp_path: Path) -> None:
        """When a fresh cache file is present, ``tools/list`` POST is not called."""
        cache_file = tmp_path / ".brain-tools-list..json"
        _write_cache_file(cache_file, ["brain_status", "memory_save"])

        post_mock = _make_tools_post_mock(["brain_status"])
        bridge = self._bridge_with_mock_client(cache_dir=tmp_path, post_mock=post_mock)

        # Also need to mock the profile_info call or it will try to post
        # We need to patch the second post call (profile_info) as well.
        # Since warm hit skips the tools/list POST, the post_mock should
        # only be called for profile_info (if at all).
        profile_mock_response = MagicMock()
        profile_mock_response.raise_for_status = MagicMock()
        profile_mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "negotiate_profile",
            "result": {"isError": True, "content": []},
        }
        post_mock.side_effect = None
        # First call = tools/list (should be skipped on warm hit),
        # but to be safe we allow the mock to return profile_info response.
        post_mock.return_value = profile_mock_response

        await bridge._negotiate_profile_locked()

        assert bridge._negotiated is True
        assert bridge._exposed_tools == frozenset({"brain_status", "memory_save"})
        # The POST should have been called at most once — for profile_info — NOT for tools/list.
        # We check this by verifying the first arg of any call was NOT "tools/list".
        for call in post_mock.call_args_list:
            call_json = call.kwargs.get("json") or (call.args[1] if len(call.args) > 1 else {})
            assert call_json.get("method") != "tools/list", (
                "tools/list POST should be skipped on warm-cache hit"
            )

    @pytest.mark.asyncio
    async def test_cache_miss_calls_live_post_and_writes_cache(self, tmp_path: Path) -> None:
        """When no cache file exists, live POST is called and the result is cached."""
        tool_names = ["brain_status", "memory_save", "memory_search"]
        profile_mock_response = MagicMock()
        profile_mock_response.raise_for_status = MagicMock()
        profile_mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "negotiate_profile",
            "result": {"isError": True, "content": []},
        }

        tools_list_mock = MagicMock()
        tools_list_mock.raise_for_status = MagicMock()
        tools_list_mock.json.return_value = {
            "jsonrpc": "2.0",
            "id": "negotiate_tools",
            "result": {"tools": [{"name": n} for n in tool_names]},
        }

        call_count = 0

        async def side_effect(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            json_body = kwargs.get("json", {})
            if json_body.get("method") == "tools/list":
                return tools_list_mock
            return profile_mock_response

        post_mock = AsyncMock(side_effect=side_effect)
        bridge = self._bridge_with_mock_client(cache_dir=tmp_path, post_mock=post_mock)

        await bridge._negotiate_profile_locked()

        assert bridge._negotiated is True
        assert bridge._exposed_tools == frozenset(tool_names)

        # Cache file must be written.
        cache_file = tmp_path / ".brain-tools-list..json"
        assert cache_file.exists()
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        written_names = {t["name"] for t in payload["tools"]}
        assert written_names == frozenset(tool_names)

    @pytest.mark.asyncio
    async def test_stale_cache_falls_through_to_live_post(self, tmp_path: Path) -> None:
        """A stale cache (age >= TTL) should be ignored and the live POST called."""
        from tapps_core.brain_bridge import _TOOLS_CACHE_TTL_SECONDS

        cache_file = tmp_path / ".brain-tools-list..json"
        _write_cache_file(cache_file, ["old_tool"])

        import os

        expired_mtime = time.time() - _TOOLS_CACHE_TTL_SECONDS - 1
        os.utime(cache_file, (expired_mtime, expired_mtime))

        fresh_tools = ["brain_status", "memory_save"]
        profile_mock_response = MagicMock()
        profile_mock_response.raise_for_status = MagicMock()
        profile_mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "negotiate_profile",
            "result": {"isError": True, "content": []},
        }

        tools_list_mock = MagicMock()
        tools_list_mock.raise_for_status = MagicMock()
        tools_list_mock.json.return_value = {
            "jsonrpc": "2.0",
            "id": "negotiate_tools",
            "result": {"tools": [{"name": n} for n in fresh_tools]},
        }

        async def side_effect(*args: Any, **kwargs: Any) -> Any:
            json_body = kwargs.get("json", {})
            if json_body.get("method") == "tools/list":
                return tools_list_mock
            return profile_mock_response

        post_mock = AsyncMock(side_effect=side_effect)
        bridge = self._bridge_with_mock_client(cache_dir=tmp_path, post_mock=post_mock)

        await bridge._negotiate_profile_locked()

        assert bridge._exposed_tools == frozenset(fresh_tools)

        # Verify tools/list was called (stale cache was bypassed).
        tools_list_calls = [
            c
            for c in post_mock.call_args_list
            if (c.kwargs.get("json") or {}).get("method") == "tools/list"
        ]
        assert len(tools_list_calls) == 1

    @pytest.mark.asyncio
    async def test_no_cache_dir_does_not_create_file(self, tmp_path: Path) -> None:
        """When ``cache_dir`` is None, no cache file should be written."""
        tool_names = ["brain_status"]
        tools_list_mock = MagicMock()
        tools_list_mock.raise_for_status = MagicMock()
        tools_list_mock.json.return_value = {
            "jsonrpc": "2.0",
            "id": "negotiate_tools",
            "result": {"tools": [{"name": n} for n in tool_names]},
        }
        profile_mock_response = MagicMock()
        profile_mock_response.raise_for_status = MagicMock()
        profile_mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "negotiate_profile",
            "result": {"isError": True, "content": []},
        }

        async def side_effect(*args: Any, **kwargs: Any) -> Any:
            json_body = kwargs.get("json", {})
            if json_body.get("method") == "tools/list":
                return tools_list_mock
            return profile_mock_response

        post_mock = AsyncMock(side_effect=side_effect)
        bridge = self._bridge_with_mock_client(cache_dir=None, post_mock=post_mock)

        await bridge._negotiate_profile_locked()

        assert bridge._exposed_tools == frozenset(tool_names)
        # No cache files should have been written to tmp_path (just a sanity check).
        assert list(tmp_path.rglob("*.json")) == []

    @pytest.mark.asyncio
    async def test_profile_used_in_cache_filename(self, tmp_path: Path) -> None:
        """Profile name is used to build the cache filename."""
        profile = "coder"
        tool_names = ["brain_status"]

        cache_file = tmp_path / f".brain-tools-list.{profile}.json"
        _write_cache_file(cache_file, tool_names)

        profile_mock_response = MagicMock()
        profile_mock_response.raise_for_status = MagicMock()
        profile_mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "negotiate_profile",
            "result": {"isError": True, "content": []},
        }
        post_mock = AsyncMock(return_value=profile_mock_response)
        bridge = self._bridge_with_mock_client(
            cache_dir=tmp_path, post_mock=post_mock, profile=profile
        )

        await bridge._negotiate_profile_locked()

        assert bridge._exposed_tools == frozenset(tool_names)
        # tools/list POST was NOT called since warm cache was found.
        for call in post_mock.call_args_list:
            call_json = call.kwargs.get("json") or {}
            assert call_json.get("method") != "tools/list"
