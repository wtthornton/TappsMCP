"""Tests for tapps_core.brain_bridge_inprocess_core — circuit breaker, write
queue, and lifecycle mixin for the in-process BrainBridge.

Split out of test_brain_bridge_circuit_breaker.py / test_brain_bridge_shutdown.py
alongside the TAP-6736 megafile split.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tapps_core.brain_bridge_inprocess import BrainBridge


@pytest.fixture()
def bridge() -> BrainBridge:
    brain = MagicMock()
    brain.store.count.return_value = 0
    return BrainBridge(brain)


class TestCircuitBreaker:
    def test_starts_closed(self, bridge: BrainBridge) -> None:
        assert bridge.circuit_open is False
        assert bridge.circuit_state == "closed"

    def test_opens_after_threshold_failures(self, bridge: BrainBridge) -> None:
        for _ in range(3):
            bridge._record_failure()
        assert bridge.circuit_open is True
        assert bridge.circuit_state == "open"

    def test_success_resets_failure_count(self, bridge: BrainBridge) -> None:
        bridge._record_failure()
        bridge._record_failure()
        bridge._record_success()
        assert bridge.status()["failures"] == 0


class TestWriteQueue:
    @pytest.mark.asyncio
    async def test_enqueue_write_reports_full_queue(self, bridge: BrainBridge) -> None:
        # Fill the queue past capacity to force the overflow (logged) path.
        from tapps_core.brain_bridge_errors import _WRITE_QUEUE_CAP

        for i in range(_WRITE_QUEUE_CAP):
            assert bridge._enqueue_write({"key": f"k{i}", "value": "v"}) is True
        assert bridge._enqueue_write({"key": "overflow", "value": "v"}) is False

    def test_queue_depth_reflects_pending_writes(self, bridge: BrainBridge) -> None:
        assert bridge.queue_depth == 0
        bridge._enqueue_write({"key": "k", "value": "v"})
        assert bridge.queue_depth == 1


class TestLifecycle:
    def test_drain_blocking_reports_empty_queue(self, bridge: BrainBridge) -> None:
        result = bridge.drain_blocking(timeout=0.1)
        assert result == {"drained": 0, "dropped": 0, "remaining": 0}

    def test_close_calls_drain_and_brain_close(self, bridge: BrainBridge) -> None:
        bridge.close()
        bridge._brain.close.assert_called_once()
