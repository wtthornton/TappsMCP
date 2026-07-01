"""Pluggable cache staleness strategies (TAP-4556, ADR-0029).

The staleness models tapps caches use are irreconcilable by nature — a wall
clock (TTL) vs a content fingerprint vs a schema version. ADR-0029 keeps them
*pluggable* behind a common protocol rather than collapsing them into one
(collapsing is exactly the "code-as-KBCache-provider" anti-pattern the ADR
rejects). Each strategy is constructed with the *current* expectation and, given
a cached marker, answers one question: is the cached entry stale?
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar

# Contravariant: the marker type appears only in an input position (``is_stale``
# consumes a cached marker), so a strategy over a wider marker type substitutes
# for one over a narrower type.
T_contra = TypeVar("T_contra", contravariant=True)


class StalenessStrategy(Protocol[T_contra]):
    """Answers whether a cached marker of type ``T_contra`` is stale.

    The marker is what a cache persists alongside each entry: a timestamp (TTL),
    a content fingerprint (str), or a schema version (int). The strategy holds
    the current expectation; ``is_stale`` compares the cached marker to it.
    """

    def is_stale(self, cached: T_contra, /) -> bool: ...


@dataclass(frozen=True)
class TTLStaleness:
    """Clock-based: stale once ``ttl_seconds`` have elapsed since ``cached``.

    The model for network/agent-fetched values that simply age out — docs
    (KBCache), dependency-scan, and Linear snapshots. ``now_fn`` is injectable so
    tests can advance the clock deterministically.
    """

    ttl_seconds: float
    now_fn: Callable[[], float] = time.time

    def is_stale(self, cached: float, /) -> bool:
        return (self.now_fn() - cached) >= self.ttl_seconds


@dataclass(frozen=True)
class FingerprintStaleness:
    """Content-fingerprint: stale when the cached hash differs from current.

    The model for locally-derived artifacts that are fresh exactly while their
    inputs are unchanged — the code graph (per-file sha) and content-hash cache.
    This is the tree-sitter file-incremental model 2026 research favors over full
    re-index; ADR-0029 keeps it rather than forcing a clock onto it.
    """

    current: str

    def is_stale(self, cached: str, /) -> bool:
        return cached != self.current


@dataclass(frozen=True)
class VersionStaleness:
    """Schema-version: stale when the cached version differs from current.

    Rejects an on-disk artifact whose *schema* predates the running code (e.g.
    the call-graph ``INDEX_VERSION``), independent of content freshness.
    """

    current: int

    def is_stale(self, cached: int, /) -> bool:
        return cached != self.current
