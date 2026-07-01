"""Shared cache substrate (ADR-0029): one atomic primitive + pluggable staleness.

Consolidates the atomic-write and staleness machinery that tapps caches
re-implemented independently. Only the *mechanics* are shared; each cache keeps
its own staleness model, provider, and retrieval — see
``docs/adr/0029-unified-cache-substrate.md``.
"""

from __future__ import annotations

from tapps_core.cache.atomic import AtomicJsonCache
from tapps_core.cache.staleness import (
    FingerprintStaleness,
    StalenessStrategy,
    TTLStaleness,
    VersionStaleness,
)

__all__ = [
    "AtomicJsonCache",
    "FingerprintStaleness",
    "StalenessStrategy",
    "TTLStaleness",
    "VersionStaleness",
]
