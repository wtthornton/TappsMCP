"""Tests for process-wide heavy-CPU concurrency guard."""

from __future__ import annotations

import asyncio

import pytest

from tapps_mcp.tools import event_loop_guard as guard


@pytest.fixture(autouse=True)
def _reset_sem() -> None:
    guard.reset_heavy_cpu_semaphore_for_tests()
    yield
    guard.reset_heavy_cpu_semaphore_for_tests()


@pytest.mark.asyncio()
async def test_heavy_cpu_limits_concurrent_slots(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAPPS_MCP_HEAVY_CPU_LIMIT", "1")
    guard.reset_heavy_cpu_semaphore_for_tests()
    # Re-read limit from env — module cached _LIMIT at import. Patch attribute.
    monkeypatch.setattr(guard, "_LIMIT", 1)
    guard.reset_heavy_cpu_semaphore_for_tests()

    active = 0
    max_active = 0

    async def _hold() -> None:
        nonlocal active, max_active
        async with guard.heavy_cpu():
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.05)
            active -= 1

    await asyncio.gather(_hold(), _hold(), _hold())
    assert max_active == 1


@pytest.mark.asyncio()
async def test_nested_acquire_in_same_task_does_not_deadlock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TAP-5965: a task that re-enters heavy_cpu keeps its existing slot.

    ``validate_changed`` holds a slot across ``CodeScorer.score_file``, which
    acquires one of its own. With a plain semaphore, every slot ends up held
    by an outer waiter blocked on an inner acquire — a permanent deadlock.
    """
    monkeypatch.setattr(guard, "_LIMIT", 2)
    guard.reset_heavy_cpu_semaphore_for_tests()

    async def _nested() -> None:
        async with guard.heavy_cpu():
            await asyncio.sleep(0)
            async with guard.heavy_cpu():
                await asyncio.sleep(0)

    await asyncio.wait_for(asyncio.gather(_nested(), _nested()), timeout=5)


@pytest.mark.asyncio()
async def test_nested_acquire_does_not_widen_the_slot_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-entry must not let a task consume a second concurrency slot."""
    monkeypatch.setattr(guard, "_LIMIT", 1)
    guard.reset_heavy_cpu_semaphore_for_tests()

    active = 0
    max_active = 0

    async def _nested() -> None:
        nonlocal active, max_active
        async with guard.heavy_cpu():
            active += 1
            max_active = max(max_active, active)
            async with guard.heavy_cpu():
                await asyncio.sleep(0.02)
            active -= 1

    await asyncio.wait_for(asyncio.gather(_nested(), _nested()), timeout=5)
    assert max_active == 1


@pytest.mark.asyncio()
async def test_child_task_does_not_inherit_the_parent_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A task spawned while holding a slot must still queue for its own."""
    monkeypatch.setattr(guard, "_LIMIT", 1)
    guard.reset_heavy_cpu_semaphore_for_tests()

    child_entered = asyncio.Event()

    async def _child() -> None:
        async with guard.heavy_cpu():
            child_entered.set()

    async with guard.heavy_cpu():
        child = asyncio.create_task(_child())
        await asyncio.sleep(0.05)
        assert not child_entered.is_set()
    await asyncio.wait_for(child, timeout=5)
    assert child_entered.is_set()
