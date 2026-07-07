"""Unified cache-stats registry (TAP-4561, ADR-0029).

Every cache registers a zero-arg provider returning its counters
(hits / misses / whatever it tracks); ``collect_cache_stats`` reports them all
into one surface (``tapps_stats``). The registry holds no opinion about what a
cache counts — it only unifies *where* the numbers show up.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

_providers: dict[str, Callable[[], dict[str, Any]]] = {}
_lock = threading.Lock()


def register_cache_stats(name: str, provider: Callable[[], dict[str, Any]]) -> None:
    """Register (or replace) the stats provider for cache *name*.

    Idempotent by design — module-import registration may run more than once.
    """
    with _lock:
        _providers[name] = provider


def unregister_cache_stats(name: str) -> None:
    """Remove a provider (tests)."""
    with _lock:
        _providers.pop(name, None)


def collect_cache_stats() -> dict[str, dict[str, Any]]:
    """Snapshot every registered cache's stats.

    A failing provider reports ``{"error": ...}`` instead of breaking the
    collection — one broken cache must not take down ``tapps_stats``.
    """
    with _lock:
        providers = dict(_providers)
    out: dict[str, dict[str, Any]] = {}
    for name, provider in providers.items():
        try:
            out[name] = dict(provider())
        except Exception as exc:
            out[name] = {"error": str(exc)}
    return out
