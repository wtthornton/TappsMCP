"""TAP-1421: tapps_memory CRUD works in HTTP-bridge mode.

Before TAP-1421, ``tapps_memory(action="save", ...)`` returned
``http_mode_not_supported`` whenever the BrainBridge was running in HTTP mode
(``store`` is None). That silently disabled every write-side workflow —
auto-capture, federation hand-off, cross-session handoff — for HTTP-bridge
deployments.

The fix routes save/get/delete/search/list/reinforce through ``BrainBridge``
async methods when the in-process store is unavailable. Actions that genuinely
need raw ``MemoryStore`` access (history, supersede, federation primitives,
maintenance) keep the gate, now renamed ``requires_in_process_store``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from tapps_mcp.server_memory_tools import tapps_memory


async def _noop_init() -> None:
    """Async no-op replacement for ensure_session_initialized."""


@pytest.fixture(autouse=True)
def _mock_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "tapps_mcp.server_memory_tools.ensure_session_initialized",
        _noop_init,
    )


class _FakeBridge:
    """Minimal in-memory stand-in for ``BrainBridge`` async methods."""

    def __init__(self) -> None:
        self.store_data: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def save(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("save", kwargs))
        entry = {
            "key": kwargs["key"],
            "value": kwargs["value"],
            "tier": kwargs.get("tier", "pattern"),
            "scope": kwargs.get("scope", "project"),
            "tags": kwargs.get("tags") or [],
        }
        self.store_data[kwargs["key"]] = entry
        return entry

    async def get(self, key: str) -> dict[str, Any] | None:
        self.calls.append(("get", {"key": key}))
        return self.store_data.get(key)

    async def delete(self, key: str) -> bool:
        self.calls.append(("delete", {"key": key}))
        return self.store_data.pop(key, None) is not None

    async def search(
        self, query: str, limit: int = 10, tier: str | None = None
    ) -> list[dict[str, Any]]:
        self.calls.append(("search", {"query": query, "limit": limit, "tier": tier}))
        return [e for e in self.store_data.values() if query in e["value"]][:limit]

    async def list_memories(
        self, limit: int = 20, tier: str | None = None
    ) -> list[dict[str, Any]]:
        self.calls.append(("list", {"limit": limit, "tier": tier}))
        return list(self.store_data.values())[:limit]

    async def reinforce(self, key: str) -> dict[str, Any]:
        self.calls.append(("reinforce", {"key": key}))
        entry = self.store_data.get(key, {"key": key})
        return {**entry, "confidence_boost": 0.1}


@pytest.mark.asyncio()
class TestSaveInHttpBridgeMode:
    """Save must succeed end-to-end when the BrainBridge is in HTTP mode."""

    async def test_save_does_not_return_requires_in_process_store(self) -> None:
        bridge = _FakeBridge()
        with (
            patch(
                "tapps_mcp.server_memory_tools._get_memory_store",
                return_value=None,
            ),
            patch(
                "tapps_mcp.server_memory_tools._get_brain_bridge",
                return_value=bridge,
            ),
        ):
            result = await tapps_memory(
                action="save",
                key="tap1421/test",
                value="hello from http mode",
                tier="pattern",
            )

        assert result["success"] is True, result
        assert result["data"]["entry"]["key"] == "tap1421/test"
        assert ("save", {"key": "tap1421/test", "value": "hello from http mode",
                         "tier": "pattern", "scope": "project", "tags": None,
                         "source": "agent", "source_agent": "",
                         "branch": None, "confidence": 0.7}) in bridge.calls or any(
            c[0] == "save" and c[1]["key"] == "tap1421/test" for c in bridge.calls
        )

    async def test_save_then_get_round_trip(self) -> None:
        bridge = _FakeBridge()
        with (
            patch(
                "tapps_mcp.server_memory_tools._get_memory_store",
                return_value=None,
            ),
            patch(
                "tapps_mcp.server_memory_tools._get_brain_bridge",
                return_value=bridge,
            ),
        ):
            save_result = await tapps_memory(
                action="save",
                key="tap1421/round-trip",
                value="payload",
            )
            get_result = await tapps_memory(
                action="get",
                key="tap1421/round-trip",
            )

        assert save_result["success"] is True
        assert get_result["success"] is True
        assert get_result["data"]["found"] is True
        assert get_result["data"]["entry"]["value"] == "payload"

    async def test_search_in_http_mode(self) -> None:
        bridge = _FakeBridge()
        bridge.store_data["k1"] = {"key": "k1", "value": "needle in haystack",
                                   "tier": "pattern", "scope": "project", "tags": []}
        with (
            patch(
                "tapps_mcp.server_memory_tools._get_memory_store",
                return_value=None,
            ),
            patch(
                "tapps_mcp.server_memory_tools._get_brain_bridge",
                return_value=bridge,
            ),
        ):
            result = await tapps_memory(action="search", query="needle")

        assert result["success"] is True
        assert result["data"]["result_count"] == 1

    async def test_delete_in_http_mode(self) -> None:
        bridge = _FakeBridge()
        bridge.store_data["doomed"] = {"key": "doomed", "value": "x",
                                       "tier": "pattern", "scope": "project", "tags": []}
        with (
            patch(
                "tapps_mcp.server_memory_tools._get_memory_store",
                return_value=None,
            ),
            patch(
                "tapps_mcp.server_memory_tools._get_brain_bridge",
                return_value=bridge,
            ),
        ):
            result = await tapps_memory(action="delete", key="doomed")

        assert result["success"] is True
        assert result["data"]["deleted"] is True
        assert "doomed" not in bridge.store_data

    async def test_list_in_http_mode(self) -> None:
        bridge = _FakeBridge()
        for i in range(3):
            k = f"k{i}"
            bridge.store_data[k] = {"key": k, "value": f"v{i}",
                                    "tier": "pattern", "scope": "project", "tags": []}
        with (
            patch(
                "tapps_mcp.server_memory_tools._get_memory_store",
                return_value=None,
            ),
            patch(
                "tapps_mcp.server_memory_tools._get_brain_bridge",
                return_value=bridge,
            ),
        ):
            result = await tapps_memory(action="list")

        assert result["success"] is True
        assert result["data"]["total_count"] == 3


@pytest.mark.asyncio()
class TestGateRetainedForInProcessOnlyActions:
    """Federation + maintenance still need a raw store; they get the renamed code."""

    async def test_federate_publish_returns_requires_in_process_store(self) -> None:
        with patch(
            "tapps_mcp.server_memory_tools._get_memory_store",
            return_value=None,
        ):
            result = await tapps_memory(action="federate_publish")

        assert result["success"] is False
        assert result["error"]["code"] == "requires_in_process_store"
        # Old code is gone.
        assert result["error"]["code"] != "http_mode_not_supported"

    async def test_consolidate_returns_requires_in_process_store(self) -> None:
        with patch(
            "tapps_mcp.server_memory_tools._get_memory_store",
            return_value=None,
        ):
            result = await tapps_memory(action="consolidate")

        assert result["success"] is False
        assert result["error"]["code"] == "requires_in_process_store"


@pytest.mark.asyncio()
class TestSaveStillWorksInProcessMode:
    """Don't break the in-process path — when store is non-None, save MUST
    route through the sync ``_DISPATCH`` table, not the HTTP fallback.
    """

    async def test_save_in_process_does_not_call_brain_bridge(self) -> None:
        """If store is present, the HTTP-bridge fallback must NOT be invoked.

        Regression guard: a too-eager rewrite of the dispatch could route
        every save through the bridge. We assert the bridge async ``save`` is
        never awaited when the in-process store is available.
        """
        bridge = _FakeBridge()
        sentinel_store = object()  # truthy, non-None — triggers sync path
        with (
            patch(
                "tapps_mcp.server_memory_tools._get_memory_store",
                return_value=sentinel_store,
            ),
            patch(
                "tapps_mcp.server_memory_tools._get_brain_bridge",
                return_value=bridge,
            ),
        ):
            # The sync handler will fail (sentinel_store has no .save), but
            # crucially via the SYNC path — not the bridge.
            await tapps_memory(action="save", key="x", value="y")

        assert all(c[0] != "save" for c in bridge.calls), (
            "Bridge.save was called even though an in-process store was "
            "available — HTTP fallback fired incorrectly."
        )


@pytest.mark.asyncio()
class TestErrorCodeRename:
    """The legacy ``http_mode_not_supported`` code is gone everywhere."""

    async def test_no_http_mode_not_supported_for_save(self) -> None:
        # Even with a misconfigured bridge (None bridge), the response
        # must not carry the old code.
        with (
            patch(
                "tapps_mcp.server_memory_tools._get_memory_store",
                return_value=None,
            ),
            patch(
                "tapps_mcp.server_memory_tools._get_brain_bridge",
                return_value=None,
            ),
        ):
            result = await tapps_memory(
                action="save", key="x", value="y"
            )

        # Either succeeds or fails with action_failed (bridge missing) but
        # never the legacy code.
        assert result.get("error", {}).get("code") != "http_mode_not_supported"
