"""Shutdown-drain, queue overflow, and status snapshot coverage (TAP-517).

These tests target the behaviours added for TAP-517:

* Enqueue overflow emits a structured warning.
* ``status()`` exposes ``queue_depth`` and ``circuit_state``.
* ``drain_blocking()`` drains the offline queue under a bounded deadline.
* ``close()`` runs the drain before closing the underlying brain.
* ``_register_shutdown_hooks`` wires atexit idempotently.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


def _make_brain() -> MagicMock:
    brain = MagicMock()
    store = MagicMock()
    store.count.return_value = 0
    save_entry = MagicMock()
    save_entry.model_dump.return_value = {"key": "k", "value": "v"}
    store.save.return_value = save_entry
    brain.store = store
    brain.hive = None
    return brain


@pytest.fixture
def bridge() -> Any:
    from tapps_core.brain_bridge import BrainBridge

    return BrainBridge(_make_brain())


# ---------------------------------------------------------------------------
# Enqueue overflow warning
# ---------------------------------------------------------------------------


class TestEnqueueOverflowWarning:
    def test_warning_logged_when_queue_full(self, bridge: Any) -> None:
        from tapps_core.brain_bridge import _WRITE_QUEUE_CAP

        for i in range(_WRITE_QUEUE_CAP):
            assert bridge._enqueue_write({"key": f"k{i}", "value": "v"}) is True

        with patch("tapps_core.brain_bridge.logger") as mock_logger:
            overflow = bridge._enqueue_write({"key": "overflow", "value": "v"})

        assert overflow is False
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert call_args.args[0] == "brain_write_queue_full"
        assert call_args.kwargs["queue_depth"] == _WRITE_QUEUE_CAP
        assert call_args.kwargs["queue_cap"] == _WRITE_QUEUE_CAP
        assert call_args.kwargs["dropped_key"] == "overflow"


# ---------------------------------------------------------------------------
# Status snapshot
# ---------------------------------------------------------------------------


class TestStatusSnapshot:
    def test_status_returns_expected_keys(self, bridge: Any) -> None:
        snapshot = bridge.status()
        assert snapshot == {
            "queue_depth": 0,
            "queue_cap": 100,
            "circuit_state": "closed",
            "failures": 0,
        }

    def test_circuit_state_closed_initially(self, bridge: Any) -> None:
        assert bridge.circuit_state == "closed"

    def test_circuit_state_open_after_threshold_failures(self, bridge: Any) -> None:
        from tapps_core.brain_bridge import _CB_FAILURE_THRESHOLD

        for _ in range(_CB_FAILURE_THRESHOLD):
            bridge._record_failure()
        assert bridge.circuit_state == "open"

    def test_status_reflects_queued_writes(self, bridge: Any) -> None:
        bridge._enqueue_write({"key": "k1", "value": "v"})
        bridge._enqueue_write({"key": "k2", "value": "v"})
        assert bridge.status()["queue_depth"] == 2


# ---------------------------------------------------------------------------
# drain_blocking
# ---------------------------------------------------------------------------


class TestDrainBlocking:
    def test_drain_empties_queue_and_persists_entries(self, bridge: Any) -> None:
        bridge._enqueue_write({"key": "k1", "value": "v1"})
        bridge._enqueue_write({"key": "k2", "value": "v2"})

        result = bridge.drain_blocking(timeout=1.0)

        assert result["drained"] == 2
        assert result["dropped"] == 0
        assert result["remaining"] == 0
        assert bridge.queue_depth == 0
        assert bridge._brain.store.save.call_count == 2

    def test_drain_counts_dropped_on_store_exception(self, bridge: Any) -> None:
        bridge._enqueue_write({"key": "k1", "value": "v1"})
        bridge._brain.store.save.side_effect = RuntimeError("postgres is down")

        result = bridge.drain_blocking(timeout=1.0)

        assert result["drained"] == 0
        assert result["dropped"] == 1
        assert result["remaining"] == 0

    def test_drain_respects_timeout_deadline(self, bridge: Any) -> None:
        """Timeout=0 means we should not drain anything — deadline check fires first."""
        for i in range(5):
            bridge._enqueue_write({"key": f"k{i}", "value": "v"})

        # Timeout=0: deadline is exceeded immediately, nothing drains.
        result = bridge.drain_blocking(timeout=0.0)

        assert result["drained"] == 0
        assert result["remaining"] == 5
        assert bridge._brain.store.save.call_count == 0

    def test_drain_on_empty_queue_is_noop(self, bridge: Any) -> None:
        result = bridge.drain_blocking(timeout=1.0)
        assert result == {"drained": 0, "dropped": 0, "remaining": 0}
        assert bridge._brain.store.save.call_count == 0


# ---------------------------------------------------------------------------
# close() drains before closing
# ---------------------------------------------------------------------------


class TestCloseDrains:
    def test_close_invokes_drain_blocking_before_brain_close(self, bridge: Any) -> None:
        bridge._enqueue_write({"key": "k1", "value": "v1"})

        call_order: list[str] = []

        original_save = bridge._brain.store.save
        original_brain_close = bridge._brain.close

        def _save(*a: Any, **kw: Any) -> Any:
            call_order.append("store.save")
            return original_save(*a, **kw)

        def _brain_close() -> None:
            call_order.append("brain.close")
            original_brain_close()

        bridge._brain.store.save = _save
        bridge._brain.close = _brain_close

        bridge.close()

        assert call_order == ["store.save", "brain.close"]
        assert bridge.queue_depth == 0


# ---------------------------------------------------------------------------
# Shutdown-hook registration
# ---------------------------------------------------------------------------


class TestRegisterShutdownHooks:
    def test_registers_atexit_handler(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import tapps_core.brain_bridge as bb

        monkeypatch.setattr(bb, "_shutdown_hooks_registered", False)

        registered: list[Any] = []
        monkeypatch.setattr(
            "tapps_core.brain_bridge.atexit.register",
            lambda fn: registered.append(fn),
        )
        monkeypatch.setattr(
            "tapps_core.brain_bridge.signal.signal",
            lambda *_a, **_kw: None,
        )

        b = bb.BrainBridge(_make_brain())
        bb._register_shutdown_hooks(b)

        assert b.close in registered

    def test_registration_is_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import tapps_core.brain_bridge as bb

        monkeypatch.setattr(bb, "_shutdown_hooks_registered", False)
        call_count = {"n": 0}

        def _count(_fn: Any) -> None:
            call_count["n"] += 1

        monkeypatch.setattr("tapps_core.brain_bridge.atexit.register", _count)
        monkeypatch.setattr(
            "tapps_core.brain_bridge.signal.signal",
            lambda *_a, **_kw: None,
        )

        b = bb.BrainBridge(_make_brain())
        bb._register_shutdown_hooks(b)
        bb._register_shutdown_hooks(b)  # second call should be a no-op

        assert call_count["n"] == 1

    def test_sigterm_register_failure_is_tolerated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Signal registration from non-main threads raises ValueError; must be swallowed."""
        import tapps_core.brain_bridge as bb

        monkeypatch.setattr(bb, "_shutdown_hooks_registered", False)
        monkeypatch.setattr("tapps_core.brain_bridge.atexit.register", lambda _fn: None)

        def _raise(*_a: Any, **_kw: Any) -> None:
            raise ValueError("signal only works in main thread")

        monkeypatch.setattr("tapps_core.brain_bridge.signal.signal", _raise)

        b = bb.BrainBridge(_make_brain())
        bb._register_shutdown_hooks(b)  # must not raise


# ---------------------------------------------------------------------------
# Integration: BrainBridge.status() is stable across circuit transitions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_updates_after_circuit_opens_and_writes_queue(bridge: Any) -> None:
    from tapps_core.brain_bridge import _CB_FAILURE_THRESHOLD

    for _ in range(_CB_FAILURE_THRESHOLD):
        bridge._record_failure()
    assert bridge.status()["circuit_state"] == "open"

    await bridge.save(key="k1", value="v1")

    snap = bridge.status()
    assert snap["circuit_state"] == "open"
    assert snap["queue_depth"] == 1


@pytest.mark.asyncio
async def test_drain_blocking_clears_entries_queued_via_save(bridge: Any) -> None:
    from tapps_core.brain_bridge import _CB_FAILURE_THRESHOLD

    for _ in range(_CB_FAILURE_THRESHOLD):
        bridge._record_failure()
    await bridge.save(key="k1", value="v1")
    await bridge.save(key="k2", value="v2")

    result = bridge.drain_blocking(timeout=1.0)
    assert result["drained"] == 2
    assert bridge.queue_depth == 0


def test_drain_blocking_finishes_well_within_timeout(bridge: Any) -> None:
    """Sanity check: drain_blocking returns quickly on a small queue."""
    for i in range(3):
        bridge._enqueue_write({"key": f"k{i}", "value": "v"})

    start = time.monotonic()
    bridge.drain_blocking(timeout=5.0)
    elapsed = time.monotonic() - start

    assert elapsed < 1.0
