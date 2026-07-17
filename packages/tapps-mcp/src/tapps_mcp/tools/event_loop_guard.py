"""Limit concurrent CPU-bound tool work on the shared HTTP fleet event loop.

``asyncio.to_thread`` keeps sync bodies off the loop thread, but pure-Python
work still contends for the GIL. Unbounded parallel ``validate_changed`` /
impact / radon from multiple Cursor windows can starve ``initialize`` /
``tools/list`` (Cursor "Loading tools") even after offload.

One process-wide semaphore caps how many heavy bodies run at once so the
loop can still service MCP handshakes (ADR-0024).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

# Keep this small: each slot may hold the GIL for hundreds of ms (radon/AST).
_DEFAULT_LIMIT = 2
_LIMIT = max(1, int(os.environ.get("TAPPS_MCP_HEAVY_CPU_LIMIT", str(_DEFAULT_LIMIT))))

_sem: asyncio.Semaphore | None = None


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
    """Acquire a process-wide slot before running GIL-heavy ``to_thread`` work."""
    async with _get_sem():
        yield


def reset_heavy_cpu_semaphore_for_tests() -> None:
    """Drop the cached semaphore (unit tests only)."""
    global _sem
    _sem = None
