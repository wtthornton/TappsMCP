"""Failure-path coverage for memory handlers when BrainBridge raises.

TAP-515: every ``await bridge.X()`` inside a memory handler must catch
``BrainBridgeUnavailable`` and return a structured ``degraded=true``
payload instead of propagating the raw exception to the MCP client.

TAP-522: this file is also the unified failure-path sweep — one test per
handler that hits a ``BrainBridge`` method.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_core.brain_bridge import BrainBridgeUnavailable
from tapps_mcp.server_memory_tools import (
    _handle_agent_register,
    _handle_consolidate,
    _handle_contradictions,
    _handle_explain_connection,
    _handle_gc,
    _handle_health,
    _handle_hive_propagate,
    _handle_hive_search,
    _handle_hive_status,
    _handle_maintain,
    _handle_neighbors,
    _handle_related,
    _handle_relations,
    _handle_verify_integrity,
    _Params,
)


def _params(**kwargs: Any) -> _Params:
    """Build _Params with zero-value defaults."""
    base: dict[str, Any] = {
        "key": "",
        "value": "",
        "tier": "pattern",
        "source": "agent",
        "source_agent": "unknown",
        "scope": "project",
        "tag_list": [],
        "branch": "",
        "query": "",
        "confidence": -1.0,
        "ranked": True,
        "limit": 0,
        "include_summary": True,
        "file_path": "",
        "overwrite": False,
        "entries": "",
        "entry_ids": [],
        "dry_run": False,
        "include_sources": False,
        "project_id": "",
        "sources": [],
        "min_confidence": 0.5,
        "include_hub": True,
        "stale_only": False,
        "max_entries": 10,
        "export_format": "json",
        "include_frontmatter": True,
        "export_group_by": "tier",
        "include_session_index": False,
        "session_id": "",
        "chunks": "",
        "safety_bypass": False,
        "subject": "",
        "predicate": "",
        "object_entity": "",
        "max_hops": 0,
    }
    base.update(kwargs)
    return _Params(**base)


@pytest.fixture
def store() -> MagicMock:
    """Minimal MemoryStore double that satisfies _store_metadata()."""
    mock_store = MagicMock()
    snap = MagicMock()
    snap.total_count = 0
    snap.tier_counts = {}
    snap.entries = []
    mock_store.snapshot.return_value = snap
    mock_store.count.return_value = 0
    return mock_store


def _unavailable_bridge(method: str) -> MagicMock:
    """Bridge double whose *method* raises BrainBridgeUnavailable."""
    bridge = MagicMock()
    setattr(
        bridge,
        method,
        AsyncMock(side_effect=BrainBridgeUnavailable("circuit open")),
    )
    return bridge


def _assert_degraded(out: dict[str, Any], action: str) -> None:
    """Shared assertion: structured TAP-515 error shape."""
    assert out["action"] == action
    assert out["success"] is False
    assert out["ok"] is False
    assert out["degraded"] is True
    assert out["retryable"] is True
    assert out["reason"] == "brain_bridge_call_failed"
    assert "circuit open" in out["error"]
    assert "remediation" in out
    assert out["next_steps"]


# ---------------------------------------------------------------------------
# Non-hive handlers (no AGENT_TEAMS gate)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gc_returns_degraded_when_bridge_unavailable(store: MagicMock) -> None:
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=_unavailable_bridge("gc"),
    ):
        out = await _handle_gc(store, _params(dry_run=True))
    _assert_degraded(out, "gc")
    assert "store_metadata" in out


@pytest.mark.asyncio
async def test_contradictions_returns_degraded_when_bridge_unavailable(
    store: MagicMock,
) -> None:
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=_unavailable_bridge("detect_conflicts"),
    ):
        out = await _handle_contradictions(store, _params())
    _assert_degraded(out, "contradictions")
    assert "store_metadata" in out


@pytest.mark.asyncio
async def test_consolidate_auto_returns_degraded_when_bridge_unavailable(
    store: MagicMock,
) -> None:
    store.list_all.return_value = [MagicMock(contradicted=False) for _ in range(3)]
    for entry in store.list_all.return_value:
        entry.is_consolidated = False
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=_unavailable_bridge("consolidate"),
    ):
        out = await _handle_consolidate(store, _params(dry_run=False))
    _assert_degraded(out, "consolidate")
    assert "store_metadata" in out


@pytest.mark.asyncio
async def test_maintain_returns_degraded_when_bridge_unavailable(
    store: MagicMock,
) -> None:
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=_unavailable_bridge("maintain"),
    ):
        out = await _handle_maintain(store, _params())
    _assert_degraded(out, "maintain")
    assert "store_metadata" in out


@pytest.mark.asyncio
async def test_health_returns_degraded_when_bridge_unavailable(
    store: MagicMock,
) -> None:
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=_unavailable_bridge("health"),
    ):
        out = await _handle_health(store, _params())
    _assert_degraded(out, "health")
    assert out["status"] == "degraded"
    assert out["configured"] is True


@pytest.mark.asyncio
async def test_health_surfaces_brain_profile_block_when_available(
    store: MagicMock,
) -> None:
    """TAP-1629: ``_handle_health`` exposes ``profile_status()`` under the
    ``brain_profile`` key so agents can read the active capability profile
    and any gated bridge tools without a second tool call.
    """
    bridge = MagicMock()
    bridge.health = AsyncMock(
        return_value={"status": "ok", "entry_count": 0, "tier_distribution": {}}
    )
    bridge.profile_status = MagicMock(
        return_value={
            "negotiated": True,
            "declared_profile": "coder",
            "memory_profile_name": "repo-brain",
            "memory_profile": {"name": "repo-brain"},
            "exposed_tools": ["brain_remember", "memory_reinforce"],
            "bridge_used_tools": ["memory_save", "memory_get"],
            "gated_used_tools": ["memory_save", "memory_get"],
            "profile_mismatch": True,
            "negotiation_error": None,
        }
    )
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=bridge,
    ):
        out = await _handle_health(store, _params())

    assert out["success"] is True
    assert out["brain_profile"]["declared_profile"] == "coder"
    assert out["brain_profile"]["profile_mismatch"] is True
    assert "memory_save" in out["brain_profile"]["gated_used_tools"]


@pytest.mark.asyncio
async def test_health_omits_brain_profile_for_in_process_bridge(
    store: MagicMock,
) -> None:
    """In-process :class:`BrainBridge` (no HTTP) has no ``profile_status``;
    the key must simply be omitted rather than crash.
    """
    bridge = MagicMock(spec=["health"])
    bridge.health = AsyncMock(
        return_value={"status": "ok", "entry_count": 0, "tier_distribution": {}}
    )
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=bridge,
    ):
        out = await _handle_health(store, _params())

    assert out["success"] is True
    assert "brain_profile" not in out


@pytest.mark.asyncio
async def test_verify_integrity_returns_degraded_when_bridge_unavailable(
    store: MagicMock,
) -> None:
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=_unavailable_bridge("verify_integrity"),
    ):
        out = await _handle_verify_integrity(store, _params())
    _assert_degraded(out, "verify_integrity")
    assert "store_metadata" in out


# ---------------------------------------------------------------------------
# Hive handlers (require AGENT_TEAMS env)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hive_status_returns_degraded_when_bridge_unavailable(
    store: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=_unavailable_bridge("hive_status"),
    ):
        out = await _handle_hive_status(store, _params())
    _assert_degraded(out, "hive_status")
    assert out["enabled"] is True


@pytest.mark.asyncio
async def test_hive_search_returns_degraded_when_bridge_unavailable(
    store: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=_unavailable_bridge("hive_search"),
    ):
        out = await _handle_hive_search(store, _params(query="jwt"))
    _assert_degraded(out, "hive_search")
    assert out["enabled"] is True
    assert out["results"] == []
    assert out["result_count"] == 0


@pytest.mark.asyncio
async def test_hive_propagate_returns_degraded_when_bridge_unavailable(
    store: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=_unavailable_bridge("hive_propagate"),
    ):
        out = await _handle_hive_propagate(store, _params())
    _assert_degraded(out, "hive_propagate")
    assert out["enabled"] is True
    assert out["propagated"] == 0
    assert out["skipped_private"] == 0


@pytest.mark.asyncio
async def test_agent_register_returns_degraded_when_bridge_unavailable(
    store: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=_unavailable_bridge("agent_register"),
    ):
        out = await _handle_agent_register(store, _params(key="agent-42"))
    _assert_degraded(out, "agent_register")
    assert out["enabled"] is True


# ---------------------------------------------------------------------------
# TAP-1630: knowledge graph handlers
# ---------------------------------------------------------------------------


def _http_bridge_with_method(method: str, return_value: Any) -> MagicMock:
    """Build a bridge double that exposes the named async graph method.

    Mirrors :func:`_unavailable_bridge` but returns a successful payload, so
    happy-path coverage on the new ``related`` / ``relations`` / ``neighbors``
    / ``explain_connection`` actions doesn't need a live brain.
    """
    bridge = MagicMock()
    setattr(bridge, method, AsyncMock(return_value=return_value))
    return bridge


@pytest.mark.asyncio
async def test_related_happy_path(store: MagicMock) -> None:
    bridge = _http_bridge_with_method(
        "find_related", [{"key": "k-near", "score": 0.9}]
    )
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=bridge,
    ):
        out = await _handle_related(store, _params(key="k1", max_hops=4))

    assert out["success"] is True
    assert out["action"] == "related"
    assert out["key"] == "k1"
    assert out["max_hops"] == 4
    assert out["entries"] == [{"key": "k-near", "score": 0.9}]
    assert out["count"] == 1
    bridge.find_related.assert_awaited_once_with("k1", max_hops=4)


@pytest.mark.asyncio
async def test_related_rejects_missing_key(store: MagicMock) -> None:
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=MagicMock(),
    ):
        out = await _handle_related(store, _params())
    assert out["success"] is False
    assert out["error"] == "missing_key"


@pytest.mark.asyncio
async def test_related_returns_degraded_when_bridge_unavailable(
    store: MagicMock,
) -> None:
    """The bridge raises BrainBridgeUnavailable (circuit open / retries
    exhausted); the handler must surface the structured TAP-515 envelope so
    agents see ``degraded=True`` rather than an opaque ``action_failed``.
    """
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=_unavailable_bridge("find_related"),
    ):
        out = await _handle_related(store, _params(key="k1"))
    _assert_degraded(out, "related")


@pytest.mark.asyncio
async def test_related_returns_graph_transport_unavailable_for_in_process(
    store: MagicMock,
) -> None:
    """In-process BrainBridge has no ``find_related`` — handler must degrade
    instead of AttributeError'ing.
    """
    bridge = MagicMock(spec=["health"])  # no find_related attribute
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=bridge,
    ):
        out = await _handle_related(store, _params(key="k1"))
    assert out["success"] is False
    assert out["degraded"] is True
    assert out["reason"] == "knowledge_graph_requires_http_bridge"


@pytest.mark.asyncio
async def test_relations_by_key_calls_entry_relations(store: MagicMock) -> None:
    bridge = MagicMock()
    bridge.entry_relations = AsyncMock(return_value=[{"subject": "k1", "predicate": "supersedes"}])
    bridge.query_relations = AsyncMock()  # not used in this path
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=bridge,
    ):
        out = await _handle_relations(store, _params(key="k1"))
    assert out["success"] is True
    assert out["mode"] == "by_key"
    assert out["key"] == "k1"
    assert out["count"] == 1
    bridge.entry_relations.assert_awaited_once_with("k1")
    bridge.query_relations.assert_not_awaited()


@pytest.mark.asyncio
async def test_relations_by_triple_calls_query_relations(store: MagicMock) -> None:
    bridge = MagicMock()
    bridge.entry_relations = AsyncMock()  # not used in this path
    bridge.query_relations = AsyncMock(
        return_value=[{"subject": "A", "predicate": "uses", "object": "B"}]
    )
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=bridge,
    ):
        out = await _handle_relations(
            store, _params(subject="A", predicate="uses")
        )
    assert out["success"] is True
    assert out["mode"] == "by_triple"
    bridge.query_relations.assert_awaited_once_with(
        subject="A", predicate="uses", object_entity=""
    )
    bridge.entry_relations.assert_not_awaited()


@pytest.mark.asyncio
async def test_relations_rejects_empty_query(store: MagicMock) -> None:
    bridge = MagicMock()
    bridge.entry_relations = AsyncMock()
    bridge.query_relations = AsyncMock()
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=bridge,
    ):
        out = await _handle_relations(store, _params())
    assert out["success"] is False
    assert out["error"] == "missing_filter"
    bridge.entry_relations.assert_not_awaited()
    bridge.query_relations.assert_not_awaited()


@pytest.mark.asyncio
async def test_neighbors_serializes_entry_ids_and_passes_filter(store: MagicMock) -> None:
    bridge = _http_bridge_with_method(
        "get_neighbors", {"neighbors": [{"id": "n1"}], "edges": []}
    )
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=bridge,
    ):
        out = await _handle_neighbors(
            store,
            _params(
                entry_ids=["e1", "e2"],
                max_hops=2,
                limit=7,
                predicate="supersedes",
            ),
        )
    assert out["success"] is True
    assert out["entity_ids"] == ["e1", "e2"]
    assert out["hops"] == 2
    assert out["limit"] == 7
    assert out["predicate_filter"] == "supersedes"
    bridge.get_neighbors.assert_awaited_once_with(
        ["e1", "e2"], hops=2, limit=7, predicate_filter="supersedes"
    )


@pytest.mark.asyncio
async def test_neighbors_rejects_missing_entity_ids(store: MagicMock) -> None:
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=MagicMock(),
    ):
        out = await _handle_neighbors(store, _params())
    assert out["success"] is False
    assert out["error"] == "missing_entity_ids"


@pytest.mark.asyncio
async def test_explain_connection_passes_endpoints_and_max_hops(
    store: MagicMock,
) -> None:
    bridge = _http_bridge_with_method(
        "explain_connection", {"path": ["A", "B"], "hops": 1}
    )
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=bridge,
    ):
        out = await _handle_explain_connection(
            store,
            _params(subject="A", object_entity="B", max_hops=5),
        )
    assert out["success"] is True
    assert out["subject_id"] == "A"
    assert out["object_id"] == "B"
    assert out["max_hops"] == 5
    bridge.explain_connection.assert_awaited_once_with("A", "B", max_hops=5)


@pytest.mark.asyncio
async def test_explain_connection_rejects_partial_endpoints(
    store: MagicMock,
) -> None:
    with patch(
        "tapps_mcp.server_memory_tools._get_brain_bridge",
        return_value=MagicMock(),
    ):
        out = await _handle_explain_connection(
            store, _params(subject="A")  # missing object_entity
        )
    assert out["success"] is False
    assert out["error"] == "missing_endpoints"
