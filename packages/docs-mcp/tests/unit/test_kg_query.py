"""Tests for docs_kg_query (TAP-1950).

The bridge is mocked for both modes plus the invalid/degraded paths.
asyncio auto-mode → tests need no marker.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from docs_mcp.server_kg_tools import docs_kg_query


class FakeBridge:
    def __init__(self) -> None:
        self.neighbors_calls: list[dict[str, Any]] = []
        self.explain_calls: list[dict[str, Any]] = []

    async def get_neighbors(
        self, entity_ids: list[str], *, hops: int = 1, limit: int = 20, predicate_filter: str = ""
    ) -> dict[str, Any]:
        self.neighbors_calls.append(
            {"entity_ids": entity_ids, "hops": hops, "limit": limit, "pf": predicate_filter}
        )
        return {"neighbors": [{"id": entity_ids[0]}]}

    async def explain_connection(
        self, subject_id: str, object_id: str, *, max_hops: int = 3
    ) -> dict[str, Any]:
        self.explain_calls.append(
            {"subject_id": subject_id, "object_id": object_id, "max_hops": max_hops}
        )
        return {"explanation": f"{subject_id}->{object_id}"}


def _patch(bridge: Any) -> Any:
    return patch("docs_mcp.server_kg_tools._get_brain_bridge", return_value=bridge)


async def test_neighbors_mode_delegates() -> None:
    bridge = FakeBridge()
    with _patch(bridge):
        resp = await docs_kg_query(mode="neighbors", entity_ids=["docs:a.py"], hops=2)
    assert resp["success"] is True
    assert resp["data"]["mode"] == "neighbors"
    assert resp["data"]["result"]["neighbors"][0]["id"] == "docs:a.py"
    assert bridge.neighbors_calls[0]["hops"] == 2


async def test_neighbors_hops_clamped_to_2() -> None:
    bridge = FakeBridge()
    with _patch(bridge):
        await docs_kg_query(mode="neighbors", entity_ids=["x"], hops=9)
    assert bridge.neighbors_calls[0]["hops"] == 2


async def test_explain_mode_delegates() -> None:
    bridge = FakeBridge()
    with _patch(bridge):
        resp = await docs_kg_query(mode="explain", subject_id="a", object_id="b", max_hops=3)
    assert resp["data"]["result"]["explanation"] == "a->b"
    assert bridge.explain_calls[0]["max_hops"] == 3


async def test_explain_max_hops_clamped_to_3() -> None:
    bridge = FakeBridge()
    with _patch(bridge):
        await docs_kg_query(mode="explain", subject_id="a", object_id="b", max_hops=9)
    assert bridge.explain_calls[0]["max_hops"] == 3


async def test_invalid_mode_returns_structured_error() -> None:
    with _patch(FakeBridge()):
        resp = await docs_kg_query(mode="bogus")
    assert resp["success"] is False
    assert resp["error"]["code"] == "INVALID_MODE"


async def test_neighbors_requires_entity_ids() -> None:
    with _patch(FakeBridge()):
        resp = await docs_kg_query(mode="neighbors", entity_ids=[])
    assert resp["success"] is False
    assert resp["error"]["code"] == "INVALID_ARGS"


async def test_explain_requires_both_ids() -> None:
    with _patch(FakeBridge()):
        resp = await docs_kg_query(mode="explain", subject_id="a")
    assert resp["success"] is False
    assert resp["error"]["code"] == "INVALID_ARGS"


async def test_bridge_unavailable_is_degraded_not_crash() -> None:
    with patch("docs_mcp.server_kg_tools._get_brain_bridge", return_value=None):
        resp = await docs_kg_query(mode="neighbors", entity_ids=["x"])
    assert resp["success"] is True
    assert resp["data"]["available"] is False
    assert resp["data"]["degraded"] is True


async def test_bridge_read_failure_is_degraded() -> None:
    class Boom:
        async def get_neighbors(self, *a: Any, **k: Any) -> dict[str, Any]:
            raise RuntimeError("circuit open")

    with patch("docs_mcp.server_kg_tools._get_brain_bridge", return_value=Boom()):
        resp = await docs_kg_query(mode="neighbors", entity_ids=["x"])
    assert resp["data"]["available"] is False
    assert resp["data"]["degraded"] is True


def test_description_within_lean_budget() -> None:
    assert docs_kg_query.__doc__ is not None
    assert len(docs_kg_query.__doc__) <= 200
