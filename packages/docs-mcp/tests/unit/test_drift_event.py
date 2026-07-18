"""Tests for docs_check_drift brain-event emission (TAP-1951).

``_emit_drift_events`` is exercised directly with a FakeBridge so no live
tapps-brain is needed. asyncio auto-mode means tests need no marker.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from docs_mcp.server_val_tools import _emit_drift_events
from docs_mcp.validators.drift import DriftItem, DriftReport


class FakeBridge:
    """Records record_kg_event calls; serves them back via get_neighbors."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def record_kg_event(
        self,
        event_type: str,
        entities: list[dict[str, str]],
        edges: list[dict[str, str]] | None = None,
        payload_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.events.append(
            {"event_type": event_type, "entities": entities, "payload_data": payload_data}
        )
        return {"recorded": True}

    async def get_neighbors(
        self, entity_ids: list[str], *, hops: int = 1, limit: int = 20, predicate_filter: str = ""
    ) -> dict[str, Any]:
        hits = [e for e in self.events if any(en["id"] in entity_ids for en in e["entities"])]
        return {"neighbors": hits}


def _report(score: float, paths: list[str]) -> DriftReport:
    items = [
        DriftItem(file_path=p, drift_type="added_undocumented", symbols=["foo"]) for p in paths
    ]
    return DriftReport(
        items=items, drift_score=score, total_items=len(items), checked_files=len(items)
    )


def _patch_bridge(bridge: Any) -> Any:
    return patch("docs_mcp.server_val_tools._get_brain_bridge", return_value=bridge)


async def test_emits_one_event_per_drifted_path() -> None:
    bridge = FakeBridge()
    with _patch_bridge(bridge):
        await _emit_drift_events(_report(42.0, ["a.py", "b.py"]))
    assert len(bridge.events) == 2
    assert all(e["event_type"] == "drift_detected" for e in bridge.events)
    ids = {e["entities"][0]["id"] for e in bridge.events}
    assert ids == {"docs:a.py", "docs:b.py"}


async def test_payload_carries_drift_score_and_doc_entity_type() -> None:
    bridge = FakeBridge()
    with _patch_bridge(bridge):
        await _emit_drift_events(_report(73.0, ["a.py"]))
    event = bridge.events[0]
    assert event["payload_data"]["drift_score"] == 73.0
    assert event["payload_data"]["path"] == "a.py"
    assert event["entities"][0]["type"] == "doc"


async def test_dedupes_repeated_paths() -> None:
    bridge = FakeBridge()
    with _patch_bridge(bridge):
        await _emit_drift_events(_report(10.0, ["a.py", "a.py"]))
    assert len(bridge.events) == 1


async def test_no_emit_when_no_drift() -> None:
    bridge = FakeBridge()
    with _patch_bridge(bridge):
        await _emit_drift_events(_report(0.0, ["a.py"]))
    assert bridge.events == []


async def test_no_emit_when_bridge_unavailable() -> None:
    with patch("docs_mcp.server_val_tools._get_brain_bridge", return_value=None):
        await _emit_drift_events(_report(50.0, ["a.py"]))  # must not raise


async def test_emit_failure_is_swallowed() -> None:
    class BoomBridge:
        async def record_kg_event(self, *a: Any, **k: Any) -> dict[str, Any]:
            raise RuntimeError("circuit open")

    with patch("docs_mcp.server_val_tools._get_brain_bridge", return_value=BoomBridge()):
        await _emit_drift_events(_report(50.0, ["a.py"]))  # must not raise


async def test_events_read_back_via_get_neighbors() -> None:
    """Integration: emitted events are queryable through the KG neighbor path."""
    bridge = FakeBridge()
    with _patch_bridge(bridge):
        await _emit_drift_events(_report(20.0, ["pkg/x.py"]))
    result = await bridge.get_neighbors(entity_ids=["docs:pkg/x.py"], hops=1)
    assert len(result["neighbors"]) == 1
    assert result["neighbors"][0]["event_type"] == "drift_detected"
