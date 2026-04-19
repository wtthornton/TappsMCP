"""TAP-520: dedicated CircuitBreaker + offline-queue-drain coverage for BrainBridge.

TAP-520 flagged the BrainBridge circuit breaker as untested. Some coverage
existed in ``test_brain_bridge.py`` (state transitions, threshold, reset
timeout); this file adds the canonical named tests the issue asked for
plus edge-case coverage: boundary conditions, partial drains, reopening
mid-drain, and recovery after sustained failures.

Separate from ``test_circuit_breaker.py``, which tests the knowledge-base
CircuitBreaker used for Context7 lookups — a different, unrelated class.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import MagicMock

import pytest


def _make_brain() -> MagicMock:
    brain = MagicMock()
    store = MagicMock()
    store.count.return_value = 0
    saved = MagicMock()
    saved.model_dump.return_value = {"key": "k", "value": "v"}
    store.save.return_value = saved
    brain.store = store
    brain.hive = None
    return brain


@pytest.fixture
def bridge() -> Any:
    from tapps_core.brain_bridge import BrainBridge

    return BrainBridge(_make_brain())


# ---------------------------------------------------------------------------
# Canonical tests requested in TAP-520
# ---------------------------------------------------------------------------


class TestTap520Canonical:
    def test_circuit_opens_after_3_failures(self, bridge: Any) -> None:
        from tapps_core.brain_bridge import _CB_FAILURE_THRESHOLD

        assert _CB_FAILURE_THRESHOLD == 3
        for _ in range(3):
            bridge._record_failure()
        assert bridge.circuit_open is True

    def test_circuit_resets_after_30s(self, bridge: Any) -> None:
        from tapps_core.brain_bridge import _CB_RESET_SECONDS

        assert _CB_RESET_SECONDS == 30.0
        for _ in range(3):
            bridge._record_failure()
        assert bridge.circuit_open is True

        # At 30s exactly, the reset clause (``>=``) fires and closes the circuit.
        bridge._open_at = time.monotonic() - 30.0
        assert bridge.circuit_open is False
        assert bridge._failures == 0
        assert bridge._open_at is None

    @pytest.mark.asyncio
    async def test_calls_rejected_while_open(self, bridge: Any) -> None:
        from tapps_core.brain_bridge import BrainBridgeUnavailable

        for _ in range(3):
            bridge._record_failure()

        with pytest.raises(BrainBridgeUnavailable, match="circuit open"):
            await bridge._call(lambda: "never runs")

    @pytest.mark.asyncio
    async def test_offline_queue_drains_on_recover(self, bridge: Any) -> None:
        # Open circuit
        for _ in range(3):
            bridge._record_failure()
        assert bridge.circuit_open is True

        # Queue three writes while offline
        await bridge.save(key="k1", value="v1")
        await bridge.save(key="k2", value="v2")
        await bridge.save(key="k3", value="v3")
        assert bridge.queue_depth == 3
        assert bridge._brain.store.save.call_count == 0  # nothing persisted yet

        # Simulate 30s elapsed — circuit closes on next probe
        bridge._open_at = time.monotonic() - 30.0
        assert bridge.circuit_open is False

        # Drain
        await bridge._drain_write_queue()

        assert bridge.queue_depth == 0
        # All three queued entries were persisted in FIFO order. BrainBridge.save
        # calls ``store.save(key, value, ...)`` with key/value positional.
        assert bridge._brain.store.save.call_count == 3
        persisted_keys = [call.args[0] for call in bridge._brain.store.save.call_args_list]
        assert persisted_keys == ["k1", "k2", "k3"]


# ---------------------------------------------------------------------------
# Boundary + edge cases
# ---------------------------------------------------------------------------


class TestBreakerBoundary:
    def test_just_below_reset_window_remains_open(self, bridge: Any) -> None:
        for _ in range(3):
            bridge._record_failure()
        bridge._open_at = time.monotonic() - 29.5
        assert bridge.circuit_open is True

    def test_failure_threshold_minus_one_keeps_circuit_closed(self, bridge: Any) -> None:
        bridge._record_failure()
        bridge._record_failure()
        assert bridge.circuit_open is False

    def test_success_after_two_failures_resets_counter(self, bridge: Any) -> None:
        bridge._record_failure()
        bridge._record_failure()
        bridge._record_success()
        # Next two failures alone should NOT open the circuit.
        bridge._record_failure()
        bridge._record_failure()
        assert bridge.circuit_open is False

    def test_reopens_after_recovery_if_failures_resume(self, bridge: Any) -> None:
        for _ in range(3):
            bridge._record_failure()
        bridge._open_at = time.monotonic() - 31.0
        assert bridge.circuit_open is False  # reset

        for _ in range(3):
            bridge._record_failure()
        assert bridge.circuit_open is True


# ---------------------------------------------------------------------------
# Retry + _call semantics
# ---------------------------------------------------------------------------


class TestCallSemantics:
    @pytest.mark.asyncio
    async def test_retries_up_to_three_attempts_on_transient_failures(self, bridge: Any) -> None:
        """Two transient failures then success should return normally."""
        call_count = {"n": 0}

        def flaky() -> str:
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise RuntimeError("transient")
            return "recovered"

        result = await bridge._call(flaky)
        assert result == "recovered"
        assert call_count["n"] == 3

    @pytest.mark.asyncio
    async def test_circuit_opens_when_all_retries_exhausted(self, bridge: Any) -> None:
        from tapps_core.brain_bridge import BrainBridgeUnavailable

        def always_fail() -> None:
            raise RuntimeError("boom")

        with pytest.raises(BrainBridgeUnavailable):
            await bridge._call(always_fail)
        assert bridge.circuit_open is True

    @pytest.mark.asyncio
    async def test_brain_bridge_unavailable_not_swallowed_by_retry(self, bridge: Any) -> None:
        from tapps_core.brain_bridge import BrainBridgeUnavailable

        def raise_unavailable() -> None:
            raise BrainBridgeUnavailable("already unreachable")

        with pytest.raises(BrainBridgeUnavailable, match="already unreachable"):
            await bridge._call(raise_unavailable)


# ---------------------------------------------------------------------------
# Drain robustness
# ---------------------------------------------------------------------------


class TestDrainRobustness:
    @pytest.mark.asyncio
    async def test_drain_stops_if_circuit_reopens_mid_drain(self, bridge: Any) -> None:
        """Store failures during drain should reopen the breaker and leave
        remaining entries on the queue."""
        bridge._enqueue_write({"key": "a", "value": "1"})
        bridge._enqueue_write({"key": "b", "value": "2"})
        bridge._enqueue_write({"key": "c", "value": "3"})
        bridge._brain.store.save.side_effect = RuntimeError("db down")

        await bridge._drain_write_queue()

        assert bridge.circuit_open is True
        assert bridge.queue_depth >= 1  # remaining entries not dropped

    @pytest.mark.asyncio
    async def test_drain_on_closed_circuit_is_noop(self, bridge: Any) -> None:
        assert bridge.circuit_open is False
        assert bridge.queue_depth == 0
        await bridge._drain_write_queue()
        assert bridge._brain.store.save.call_count == 0

    def test_maybe_start_drain_is_noop_when_queue_empty(self, bridge: Any) -> None:
        bridge._maybe_start_drain()
        assert bridge._drain_task is None

    def test_maybe_start_drain_is_noop_when_circuit_open(self, bridge: Any) -> None:
        bridge._enqueue_write({"key": "k", "value": "v"})
        for _ in range(3):
            bridge._record_failure()
        bridge._maybe_start_drain()
        assert bridge._drain_task is None

    @pytest.mark.asyncio
    async def test_maybe_start_drain_spawns_task_when_ready(self, bridge: Any) -> None:
        bridge._enqueue_write({"key": "k", "value": "v"})
        assert bridge.circuit_open is False

        bridge._maybe_start_drain()
        assert bridge._drain_task is not None

        await bridge._drain_task
        assert bridge.queue_depth == 0
        bridge._brain.store.save.assert_called_once()


# ---------------------------------------------------------------------------
# Concurrent enqueue safety
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_enqueue_preserves_all_entries(bridge: Any) -> None:
    """Concurrent save() calls while circuit is open must not lose entries below cap."""
    for _ in range(3):
        bridge._record_failure()  # force circuit open so saves queue

    async def enqueue_one(i: int) -> None:
        await bridge.save(key=f"k{i}", value=f"v{i}")

    await asyncio.gather(*(enqueue_one(i) for i in range(20)))
    assert bridge.queue_depth == 20
