"""Tests for tapps_core.brain_bridge_inprocess_ops — AgentBrain-delegating
read/write/maintenance methods for the in-process BrainBridge.

Split out of test_brain_bridge.py alongside the TAP-6736 megafile split.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from tapps_core.brain_bridge_inprocess import BrainBridge


def _make_entry(**kwargs: Any) -> MagicMock:
    entry = MagicMock()
    entry.model_dump.return_value = {"key": "k", "value": "v", "tier": "pattern", **kwargs}
    return entry


@pytest.fixture()
def bridge() -> BrainBridge:
    brain = MagicMock()
    brain.store.save.return_value = _make_entry()
    brain.store.get.return_value = _make_entry()
    brain.store.delete.return_value = True
    brain.hive = None
    return BrainBridge(brain)


class TestToDict:
    def test_model_dump_object(self, bridge: BrainBridge) -> None:
        obj = MagicMock()
        obj.model_dump.return_value = {"a": 1}
        assert bridge._to_dict(obj) == {"a": 1}

    def test_plain_object_falls_back_to_vars(self, bridge: BrainBridge) -> None:
        class Plain:
            def __init__(self) -> None:
                self.x = 1

        assert bridge._to_dict(Plain()) == {"x": 1}

    def test_scalar_falls_back_to_str(self, bridge: BrainBridge) -> None:
        assert bridge._to_dict(42) == {"value": "42"}


class TestSave:
    @pytest.mark.asyncio
    async def test_save_delegates_to_store(self, bridge: BrainBridge) -> None:
        result = await bridge.save("k", "v", tier="pattern")
        assert result["key"] == "k"
        bridge._brain.store.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_queues_when_circuit_open(self, bridge: BrainBridge) -> None:
        bridge._record_failure()
        bridge._record_failure()
        bridge._record_failure()
        assert bridge.circuit_open is True
        result = await bridge.save("k", "v")
        assert result["degraded"] is True
        assert result["queued"] is True


class TestHiveDisabled:
    @pytest.mark.asyncio
    async def test_hive_search_returns_empty_without_hive(self, bridge: BrainBridge) -> None:
        assert await bridge.hive_search("q") == []

    @pytest.mark.asyncio
    async def test_hive_status_reports_degraded_without_hive(self, bridge: BrainBridge) -> None:
        result = await bridge.hive_status(agent_id="a1")
        assert result["degraded"] is True


class TestHttpOnlyMethodsRaise:
    @pytest.mark.asyncio
    async def test_docs_lookup_raises_bridge_unavailable(self, bridge: BrainBridge) -> None:
        from tapps_core.brain_bridge_errors import BrainBridgeUnavailable

        with pytest.raises(BrainBridgeUnavailable):
            await bridge.docs_lookup("some-lib")
