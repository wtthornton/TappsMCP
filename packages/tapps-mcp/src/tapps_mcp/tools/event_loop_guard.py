"""Limit concurrent CPU-bound tool work on the shared HTTP fleet event loop.

``asyncio.to_thread`` keeps sync bodies off the loop thread, but pure-Python
work still contends for the GIL. Unbounded parallel ``validate_changed`` /
impact / radon from multiple Cursor windows can starve ``initialize`` /
``tools/list`` (Cursor "Loading tools") even after offload.

One process-wide semaphore caps how many heavy bodies run at once so the
loop can still service MCP handshakes (ADR-0024).

Acquisition is re-entrant *per asyncio task* (TAP-5965). Heavy call paths
nest: ``validate_changed`` holds a slot across ``CodeScorer.score_file``,
which takes one for its own category build. A plain semaphore deadlocks
there — every slot ends up held by an outer waiter that can only finish by
acquiring an inner slot. Re-entry reuses the slot the task already owns, so
the budget still bounds *distinct* heavy bodies. Ownership is keyed on the
running task, so a task spawned while its parent holds a slot still queues
for one of its own.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar

# Keep this small: each slot may hold the GIL for hundreds of ms (radon/AST).
_DEFAULT_LIMIT = 2
_LIMIT = max(1, int(os.environ.get("TAPPS_MCP_HEAVY_CPU_LIMIT", str(_DEFAULT_LIMIT))))

_sem: asyncio.Semaphore | None = None

# The task that owns the slot bound to the current context, if any.
_slot_owner: ContextVar[asyncio.Task[object] | None] = ContextVar(
    "tapps_heavy_cpu_slot_owner",
    default=None,
)


def heavy_cpu_limit() -> int:
    """Return the configured concurrent heavy-CPU slot count."""
    return _LIMIT


def _get_sem() -> asyncio.Semaphore:
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(_LIMIT)
    return _sem


@asynccontextmanager
async def heavy_cpu() -> AsyncIterator[None]:
    """Acquire a process-wide slot before running GIL-heavy ``to_thread`` work.

    Re-entrant within a single task: a nested acquire reuses the slot the
    task already holds instead of waiting for a second one.
    """
    task = asyncio.current_task()
    if task is not None and _slot_owner.get() is task:
        yield
        return

    async with _get_sem():
        token = _slot_owner.set(task)
        try:
            yield
        finally:
            _slot_owner.reset(token)


def reset_heavy_cpu_semaphore_for_tests() -> None:
    """Drop the cached semaphore (unit tests only)."""
    global _sem
    _sem = None
