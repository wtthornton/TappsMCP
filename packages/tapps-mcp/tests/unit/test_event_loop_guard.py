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
