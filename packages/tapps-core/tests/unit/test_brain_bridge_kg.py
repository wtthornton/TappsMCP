"""Tests for BrainBridge KG semantic-upsert shims (TAP-1947).

Covers: deterministic entity-id derivation + idempotency, delegation to
``record_kg_event`` (no second write path), ADR-012 evidence-required edges,
``add_evidence`` XOR enforcement, and circuit-open queueing + drain replay.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest

from tapps_core.brain_bridge import HttpBrainBridge
from tapps_core.knowledge.kg_keys import entity_uuid


def _bridge(project: str = "tapps-mcp") -> HttpBrainBridge:
    return HttpBrainBridge("http://brain:8080", {"X-Project-Id": project})


def _open_circuit(bridge: HttpBrainBridge) -> None:
    bridge._open_at = time.monotonic()
    bridge._failures = 99


# ---------------------------------------------------------------------------
# upsert_entity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_entity_returns_deterministic_id() -> None:
    bridge = _bridge()
    bridge._http_mcp_call = AsyncMock(return_value={"recorded": True})  # type: ignore[method-assign]

    result = await bridge.upsert_entity("tapps_core.brain_bridge", "module")

    expected = str(entity_uuid("tapps-mcp", "module", "tapps_core.brain_bridge"))
    assert result["entity_id"] == expected
    bridge._http_mcp_call.assert_awaited_once()
    tool_name, args = bridge._http_mcp_call.await_args.args
    assert tool_name == "brain_record_event"  # delegated; no new write path


@pytest.mark.asyncio
async def test_upsert_entity_idempotent() -> None:
    bridge = _bridge()
    bridge._http_mcp_call = AsyncMock(return_value={"recorded": True})  # type: ignore[method-assign]

    a = await bridge.upsert_entity("pkg.mod", "module")
    b = await bridge.upsert_entity("pkg.mod", "module")
    assert a["entity_id"] == b["entity_id"]


@pytest.mark.asyncio
async def test_upsert_entity_carries_aliases_and_metadata() -> None:
    bridge = _bridge()
    bridge._http_mcp_call = AsyncMock(return_value={"recorded": True})  # type: ignore[method-assign]

    import json

    await bridge.upsert_entity(
        "pkg", "package", aliases=["pkg-alias"], metadata={"loc": 42}
    )
    _tool, args = bridge._http_mcp_call.await_args.args
    payload = json.loads(args["payload_json"])
    assert payload["event_type"] == "entity_upsert"
    assert payload["payload"]["aliases"] == ["pkg-alias"]
    assert payload["payload"]["metadata"] == {"loc": 42}


@pytest.mark.asyncio
async def test_upsert_entity_explicit_project_overrides_header() -> None:
    bridge = _bridge(project="header-proj")
    bridge._http_mcp_call = AsyncMock(return_value={"recorded": True})  # type: ignore[method-assign]

    result = await bridge.upsert_entity("pkg.mod", "module", project_id="other-proj")
    assert result["entity_id"] == str(entity_uuid("other-proj", "module", "pkg.mod"))


# ---------------------------------------------------------------------------
# upsert_edge — ADR-012 evidence-required
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_edge_success_with_evidence() -> None:
    bridge = _bridge()
    bridge._http_mcp_call = AsyncMock(return_value={"recorded": True})  # type: ignore[method-assign]

    import json

    await bridge.upsert_edge(
        "a",
        "depends_on",
        "b",
        evidence={"file_path": "pkg/a.py", "line_range": "1-10", "commit_sha": "abc"},
        confidence=0.9,
    )
    _tool, args = bridge._http_mcp_call.await_args.args
    payload = json.loads(args["payload_json"])
    assert payload["event_type"] == "edge_upsert"
    assert payload["edges"] == [{"src": "a", "predicate": "depends_on", "dst": "b"}]
    assert payload["payload"]["confidence"] == 0.9
    assert payload["payload"]["evidence"]["file_path"] == "pkg/a.py"


@pytest.mark.asyncio
async def test_upsert_edge_refuses_without_evidence() -> None:
    bridge = _bridge()
    bridge._http_mcp_call = AsyncMock(return_value={"recorded": True})  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="ADR-012"):
        await bridge.upsert_edge("a", "depends_on", "b", evidence={})
    bridge._http_mcp_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_edge_refuses_evidence_without_file_path() -> None:
    bridge = _bridge()
    bridge._http_mcp_call = AsyncMock(return_value={"recorded": True})  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="ADR-012"):
        await bridge.upsert_edge("a", "rel", "b", evidence={"commit_sha": "abc"})


# ---------------------------------------------------------------------------
# add_evidence — XOR
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_evidence_for_entity() -> None:
    bridge = _bridge()
    bridge._http_mcp_call = AsyncMock(return_value={"recorded": True})  # type: ignore[method-assign]

    import json

    await bridge.add_evidence(
        file_path="pkg/a.py", line_range="1-5", commit_sha="abc", entity_id="e1"
    )
    _tool, args = bridge._http_mcp_call.await_args.args
    payload = json.loads(args["payload_json"])
    assert payload["event_type"] == "evidence_add"
    assert payload["payload"]["target_kind"] == "entity"
    assert payload["entities"] == [{"type": "entity_ref", "id": "e1"}]


@pytest.mark.asyncio
async def test_add_evidence_requires_exactly_one_target() -> None:
    bridge = _bridge()
    bridge._http_mcp_call = AsyncMock(return_value={"recorded": True})  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="exactly one"):
        await bridge.add_evidence(file_path="a", line_range="1", commit_sha="x")
    with pytest.raises(ValueError, match="exactly one"):
        await bridge.add_evidence(
            file_path="a", line_range="1", commit_sha="x", entity_id="e1", edge_id="g1"
        )
    bridge._http_mcp_call.assert_not_awaited()


# ---------------------------------------------------------------------------
# Circuit-open queueing + drain replay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_entity_queues_when_circuit_open() -> None:
    bridge = _bridge()
    bridge._http_mcp_call = AsyncMock(return_value={"recorded": True})  # type: ignore[method-assign]
    _open_circuit(bridge)

    result = await bridge.upsert_entity("pkg.mod", "module")

    # id is still returned (deterministic), the write is queued, the wire is untouched
    assert result["entity_id"] == str(entity_uuid("tapps-mcp", "module", "pkg.mod"))
    assert result["queued"] is True
    assert result["degraded"] is True
    assert bridge.queue_depth == 1
    bridge._http_mcp_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_drain_replays_queued_kg_event() -> None:
    bridge = _bridge()
    bridge._http_mcp_call = AsyncMock(return_value={"recorded": True})  # type: ignore[method-assign]
    _open_circuit(bridge)
    await bridge.upsert_entity("pkg.mod", "module")
    assert bridge.queue_depth == 1

    # close the circuit and drain
    bridge._open_at = None
    bridge._failures = 0
    await bridge._drain_write_queue()

    assert bridge.queue_depth == 0
    bridge._http_mcp_call.assert_awaited()
    tool_name, args = bridge._http_mcp_call.await_args.args
    assert tool_name == "brain_record_event"


@pytest.mark.asyncio
async def test_drain_still_replays_save_entries() -> None:
    """Save-shaped queue entries must still route through save() after the
    KG-aware override (regression guard for the _replay_queued_write seam)."""
    bridge = _bridge()
    bridge.save = AsyncMock(return_value={"key": "k", "success": True})  # type: ignore[method-assign]
    bridge._write_queue.put_nowait({"key": "k", "value": "v", "tier": "pattern"})

    await bridge._drain_write_queue()

    bridge.save.assert_awaited_once_with(key="k", value="v", tier="pattern")
    assert bridge.queue_depth == 0
