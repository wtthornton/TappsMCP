"""Tests for tapps_core.brain_bridge.BrainBridge.

Coverage targets:
- create_brain_bridge returns None when TAPPS_BRAIN_DATABASE_URL is unset
- Circuit breaker opens after 3 failures
- Circuit breaker auto-resets after the timeout
- Write queue: saves are enqueued when circuit is open
- Write queue: queued writes drain after circuit resets
- All async methods delegate to the underlying store
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_mock_entry(**kwargs: Any) -> MagicMock:
    """Return a mock MemoryEntry with model_dump."""
    entry = MagicMock()
    data: dict[str, Any] = {"key": "k", "value": "v", "tier": "pattern", **kwargs}
    entry.model_dump.return_value = data
    return entry


def _make_brain(*, store_overrides: dict[str, Any] | None = None) -> MagicMock:
    """Return a mock AgentBrain with a realistic store."""
    brain = MagicMock()
    store = MagicMock()
    store.count.return_value = 0
    store.save.return_value = _make_mock_entry()
    store.get.return_value = _make_mock_entry()
    store.search.return_value = [_make_mock_entry()]
    store.list_all.return_value = [_make_mock_entry()]
    store.delete.return_value = True
    store.reinforce.return_value = _make_mock_entry()
    store.supersede.return_value = _make_mock_entry()
    store.gc.return_value = MagicMock(model_dump=lambda: {"purged": 0})
    store.health.return_value = MagicMock(
        model_dump=lambda: {"store_available": True, "postgres_available": True, "current_count": 5}
    )
    store.project_root = "."
    if store_overrides:
        for k, v in store_overrides.items():
            setattr(store, k, v)
    brain.store = store
    brain.recall.return_value = [{"key": "k1", "value": "recalled", "score": 0.8}]
    brain.hive = None
    return brain


@pytest.fixture()
def bridge() -> Any:
    from tapps_core.brain_bridge import BrainBridge

    brain = _make_brain()
    return BrainBridge(brain)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestCreateBrainBridge:
    def test_returns_none_when_no_dsn(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TAPPS_BRAIN_DATABASE_URL", raising=False)
        from tapps_core.brain_bridge import create_brain_bridge

        assert create_brain_bridge(settings=None) is None

    def test_returns_none_when_dsn_empty_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAPPS_BRAIN_DATABASE_URL", "")
        from tapps_core.brain_bridge import create_brain_bridge

        assert create_brain_bridge(settings=None) is None

    def test_returns_bridge_when_dsn_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAPPS_BRAIN_DATABASE_URL", "postgresql://user:pass@localhost/db")
        from tapps_core.brain_bridge import BrainBridge, create_brain_bridge

        mock_brain = _make_brain()
        # Patch at the source module: create_brain_bridge does `from tapps_brain import AgentBrain`
        # at call time, so AgentBrain is not a module-level name in brain_bridge.
        with patch("tapps_brain.AgentBrain", return_value=mock_brain):
            result = create_brain_bridge(settings=None)

        assert isinstance(result, BrainBridge)

    def test_returns_none_when_agent_brain_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAPPS_BRAIN_DATABASE_URL", "postgresql://bad/dsn")
        from tapps_core.brain_bridge import create_brain_bridge

        with patch("tapps_brain.AgentBrain", side_effect=RuntimeError("bad DSN")):
            result = create_brain_bridge(settings=None)

        assert result is None

    def test_reads_dsn_from_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TAPPS_BRAIN_DATABASE_URL", raising=False)
        from tapps_core.brain_bridge import BrainBridge, create_brain_bridge

        settings = MagicMock()
        settings.memory.database_url = "postgresql://settings/db"
        settings.memory.profile = "repo-brain"
        settings.memory.hive_dsn = ""

        mock_brain = _make_brain()
        with patch("tapps_brain.AgentBrain", return_value=mock_brain):
            result = create_brain_bridge(settings=settings)

        assert isinstance(result, BrainBridge)


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    def test_circuit_closed_initially(self, bridge: Any) -> None:
        assert bridge.circuit_open is False

    def test_opens_after_threshold_failures(self, bridge: Any) -> None:
        for _ in range(3):
            bridge._record_failure()
        assert bridge.circuit_open is True

    def test_stays_closed_below_threshold(self, bridge: Any) -> None:
        bridge._record_failure()
        bridge._record_failure()
        assert bridge.circuit_open is False

    def test_resets_after_timeout(self, bridge: Any) -> None:
        for _ in range(3):
            bridge._record_failure()
        assert bridge.circuit_open is True

        # Simulate elapsed time past reset window
        bridge._open_at = time.monotonic() - 31.0
        assert bridge.circuit_open is False
        assert bridge._failures == 0

    def test_success_clears_failure_count(self, bridge: Any) -> None:
        bridge._record_failure()
        bridge._record_failure()
        bridge._record_success()
        assert bridge._failures == 0
        assert bridge.circuit_open is False

    @pytest.mark.asyncio()
    async def test_call_raises_when_circuit_open(self, bridge: Any) -> None:
        from tapps_core.brain_bridge import BrainBridgeUnavailable

        for _ in range(3):
            bridge._record_failure()

        with pytest.raises(BrainBridgeUnavailable, match="circuit open"):
            await bridge._call(lambda: None)

    @pytest.mark.asyncio()
    async def test_call_retries_on_transient_failure(self, bridge: Any) -> None:
        call_count = 0

        def flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("transient")
            return "ok"

        result = await bridge._call(flaky)
        assert result == "ok"
        assert call_count == 2

    @pytest.mark.asyncio()
    async def test_call_opens_circuit_after_repeated_failures(self, bridge: Any) -> None:
        from tapps_core.brain_bridge import BrainBridgeUnavailable

        def always_fail() -> None:
            raise RuntimeError("always fails")

        with pytest.raises(BrainBridgeUnavailable):
            await bridge._call(always_fail)

        assert bridge.circuit_open is True


# ---------------------------------------------------------------------------
# Write queue
# ---------------------------------------------------------------------------


class TestWriteQueue:
    def test_queue_depth_zero_initially(self, bridge: Any) -> None:
        assert bridge.queue_depth == 0

    def test_enqueue_write_when_circuit_open(self, bridge: Any) -> None:
        for _ in range(3):
            bridge._record_failure()

        assert bridge.circuit_open is True
        queued = bridge._enqueue_write({"key": "k", "value": "v"})
        assert queued is True
        assert bridge.queue_depth == 1

    def test_enqueue_returns_false_when_full(self, bridge: Any) -> None:
        # Fill the queue
        for i in range(100):
            bridge._write_queue.put_nowait({"key": f"k{i}", "value": "v"})

        result = bridge._enqueue_write({"key": "overflow", "value": "v"})
        assert result is False

    @pytest.mark.asyncio()
    async def test_save_queues_when_circuit_open(self, bridge: Any) -> None:
        for _ in range(3):
            bridge._record_failure()

        result = await bridge.save("my-key", "my-value")
        assert result["degraded"] is True
        assert result["queued"] is True
        assert bridge.queue_depth == 1

    @pytest.mark.asyncio()
    async def test_drain_empties_queue_after_reset(self, bridge: Any) -> None:
        # Open circuit and queue a write
        for _ in range(3):
            bridge._record_failure()
        bridge._enqueue_write({"key": "k", "value": "v"})
        assert bridge.queue_depth == 1

        # Reset circuit manually (simulate timeout)
        bridge._open_at = time.monotonic() - 31.0
        assert bridge.circuit_open is False

        # Drain
        await bridge._drain_write_queue()
        assert bridge.queue_depth == 0
        bridge._brain.store.save.assert_called_once()


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


class TestReadOperations:
    @pytest.mark.asyncio()
    async def test_search_delegates_to_store(self, bridge: Any) -> None:
        results = await bridge.search("test query", limit=5)
        assert isinstance(results, list)
        bridge._brain.store.search.assert_called_once_with("test query", tier=None)

    @pytest.mark.asyncio()
    async def test_get_returns_dict(self, bridge: Any) -> None:
        result = await bridge.get("my-key")
        assert isinstance(result, dict)
        bridge._brain.store.get.assert_called_once_with("my-key")

    @pytest.mark.asyncio()
    async def test_get_returns_none_when_missing(self, bridge: Any) -> None:
        bridge._brain.store.get.return_value = None
        result = await bridge.get("missing")
        assert result is None

    @pytest.mark.asyncio()
    async def test_list_memories(self, bridge: Any) -> None:
        results = await bridge.list_memories(limit=10, tier="pattern")
        assert isinstance(results, list)
        bridge._brain.store.list_all.assert_called_once_with(tier="pattern")

    @pytest.mark.asyncio()
    async def test_recall_for_prompt_formats_hits(self, bridge: Any) -> None:
        result = await bridge.recall_for_prompt("query", threshold=0.5)
        assert result is not None
        assert "recalled" in result

    @pytest.mark.asyncio()
    async def test_recall_for_prompt_returns_none_below_threshold(self, bridge: Any) -> None:
        bridge._brain.recall.return_value = [{"key": "k", "value": "v", "score": 0.1}]
        result = await bridge.recall_for_prompt("query", threshold=0.9)
        assert result is None

    @pytest.mark.asyncio()
    async def test_hive_search_returns_empty_when_no_hive(self, bridge: Any) -> None:
        bridge._brain.hive = None
        results = await bridge.hive_search("query")
        assert results == []


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------


class TestWriteOperations:
    @pytest.mark.asyncio()
    async def test_save_delegates_to_store(self, bridge: Any) -> None:
        result = await bridge.save("key", "value", tier="pattern")
        assert isinstance(result, dict)
        bridge._brain.store.save.assert_called_once()

    @pytest.mark.asyncio()
    async def test_save_many_counts(self, bridge: Any) -> None:
        entries = [{"key": f"k{i}", "value": "v"} for i in range(3)]
        result = await bridge.save_many(entries)
        assert result["saved"] == 3
        assert result["failed"] == 0

    @pytest.mark.asyncio()
    async def test_delete_returns_bool(self, bridge: Any) -> None:
        result = await bridge.delete("key")
        assert result is True
        bridge._brain.store.delete.assert_called_once_with("key")

    @pytest.mark.asyncio()
    async def test_reinforce_passes_boost(self, bridge: Any) -> None:
        await bridge.reinforce("key", boost=0.2)
        bridge._brain.store.reinforce.assert_called_once_with("key", confidence_boost=0.2)

    @pytest.mark.asyncio()
    async def test_supersede_delegates(self, bridge: Any) -> None:
        await bridge.supersede("key", "new-value")
        bridge._brain.store.supersede.assert_called_once_with("key", "new-value")


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------


class TestMaintenance:
    @pytest.mark.asyncio()
    async def test_gc_delegates_to_store(self, bridge: Any) -> None:
        result = await bridge.gc(dry_run=True)
        assert isinstance(result, dict)
        bridge._brain.store.gc.assert_called_once_with(dry_run=True)

    @pytest.mark.asyncio()
    async def test_health_includes_status(self, bridge: Any) -> None:
        result = await bridge.health()
        assert "status" in result
        assert result["status"] == "ok"
        assert "postgres" in result
        assert result["entry_count"] == 5

    # TAP-412 / EPIC-95.3: extended maintenance API.

    @pytest.mark.asyncio()
    async def test_verify_integrity_delegates_to_store(self, bridge: Any) -> None:
        bridge._brain.store.verify_integrity = MagicMock(
            return_value={
                "total": 3,
                "verified": 3,
                "tampered": 0,
                "no_hash": 0,
                "tampered_keys": [],
            }
        )
        result = await bridge.verify_integrity()
        assert result["total"] == 3
        assert result["verified"] == 3
        bridge._brain.store.verify_integrity.assert_called_once()

    @pytest.mark.asyncio()
    async def test_undo_consolidation_delegates_to_store(self, bridge: Any) -> None:
        bridge._brain.store.undo_consolidation_merge = MagicMock(
            return_value=MagicMock(
                model_dump=lambda: {
                    "ok": True,
                    "reason": "ok",
                    "consolidated_key": "k",
                    "source_keys": ["a", "b"],
                }
            )
        )
        result = await bridge.undo_consolidation("k")
        assert result["ok"] is True
        assert result["source_keys"] == ["a", "b"]
        bridge._brain.store.undo_consolidation_merge.assert_called_once_with("k")

    @pytest.mark.asyncio()
    async def test_detect_conflicts_runs_detector(self, bridge: Any) -> None:
        from pathlib import Path

        from unittest.mock import patch as _patch

        fake_contradictions = [
            MagicMock(memory_key="k1", model_dump=lambda: {"memory_key": "k1"}),
        ]
        fake_detector = MagicMock()
        fake_detector.detect_contradictions.return_value = fake_contradictions
        bridge._brain.store.list_all = MagicMock(return_value=[MagicMock(key="k1")])
        bridge._brain.store.update_fields = MagicMock()

        with _patch(
            "tapps_brain.contradictions.ContradictionDetector",
            return_value=fake_detector,
        ):
            result = await bridge.detect_conflicts(profile=MagicMock(), project_root=Path("."))

        assert result["count"] == 1
        assert result["checked_count"] == 1
        bridge._brain.store.update_fields.assert_called_once_with("k1", contradicted=True)

    # TAP-413 / EPIC-95.4: hive operations.

    @pytest.mark.asyncio()
    async def test_hive_status_degraded_when_no_hive(self, bridge: Any) -> None:
        bridge._brain.hive = None
        result = await bridge.hive_status(agent_id="a1")
        assert result["enabled"] is True
        assert result["degraded"] is True

    @pytest.mark.asyncio()
    async def test_hive_status_returns_namespaces(self, bridge: Any) -> None:
        hive = MagicMock()
        hive.list_namespaces.return_value = ["universal", "domain-foo"]
        bridge._brain.hive = hive

        with patch("tapps_brain.backends.AgentRegistry") as reg_cls:
            reg = MagicMock()
            reg.list_agents.return_value = []
            reg_cls.return_value = reg
            result = await bridge.hive_status(
                agent_id="a1", agent_name="x", agent_profile="repo-brain"
            )

        assert result["degraded"] is False
        assert result["namespace_count"] == 2
        assert "universal" in result["namespaces"]

    @pytest.mark.asyncio()
    async def test_hive_propagate_skips_private(self, bridge: Any) -> None:
        bridge._brain.hive = MagicMock()
        entry = MagicMock(
            key="k1",
            value="v1",
            agent_scope="private",
            tier="pattern",
            confidence=0.7,
            source=MagicMock(value="agent"),
            tags=[],
        )
        with patch(
            "tapps_brain.backends.PropagationEngine.propagate", return_value=None
        ):
            result = await bridge.hive_propagate(
                [entry], agent_id="a1", agent_profile="repo-brain"
            )
        assert result["propagated"] == 0
        assert result["skipped_private"] == 1

    @pytest.mark.asyncio()
    async def test_hive_propagate_degraded_when_no_hive(self, bridge: Any) -> None:
        bridge._brain.hive = None
        result = await bridge.hive_propagate(
            [], agent_id="a1", agent_profile="repo-brain"
        )
        assert result["degraded"] is True
        assert result["propagated"] == 0

    @pytest.mark.asyncio()
    async def test_agent_register_calls_registry(self, bridge: Any) -> None:
        with patch("tapps_brain.backends.AgentRegistry") as reg_cls:
            reg = MagicMock()
            reg_cls.return_value = reg
            result = await bridge.agent_register(
                agent_id="a1",
                name="display",
                profile="repo-brain",
                skills=["python"],
            )
        reg.register.assert_called_once()
        assert result["agent_id"] == "a1"
        assert result["skills"] == ["python"]

    @pytest.mark.asyncio()
    async def test_maintain_chains_phases(self, bridge: Any) -> None:
        bridge._brain.store.gc = MagicMock(
            return_value=MagicMock(model_dump=lambda: {"archived_count": 2})
        )
        # consolidate path uses run_periodic_consolidation_scan via patched import
        bridge._brain.store.snapshot = MagicMock(
            return_value=MagicMock(entries=[])
        )

        with patch(
            "tapps_brain.auto_consolidation.run_periodic_consolidation_scan",
            return_value=MagicMock(model_dump=lambda: {"groups_found": 1}),
        ):
            result = await bridge.maintain()

        assert "gc_archived" in result
        assert "consolidated" in result
        assert "deduplicated" in result


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    def test_circuit_open_property(self, bridge: Any) -> None:
        assert bridge.circuit_open is False

    def test_queue_depth_property(self, bridge: Any) -> None:
        assert bridge.queue_depth == 0


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_close_calls_brain_close(self, bridge: Any) -> None:
        bridge.close()
        bridge._brain.close.assert_called_once()

    def test_close_tolerates_exception(self, bridge: Any) -> None:
        bridge._brain.close.side_effect = RuntimeError("already closed")
        bridge.close()  # should not raise
