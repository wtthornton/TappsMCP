"""SHA-256 content-hash cache for per-file tool results (STORY-101.1).

Motivation: scoring, quality-gate evaluation, and security scanning are all
deterministic functions of file content. If the same file is queried
repeatedly without editing (a common pattern when agents loop through
quick_check → validate_changed → checklist), we can return the previous
result directly.

Design:
- Keys are ``(kind, sha256(file_bytes))`` tuples. The file path is *not*
  part of the key: renaming or copying a file should still hit the cache.
- Values are opaque ``dict[str, Any]`` (the tool's response or a sub-slice
  of it — the caller decides what to store).
- Bounded by ``_MAX_ENTRIES`` to prevent unbounded memory growth in
  long-lived servers; eviction is simple FIFO.
- Optional TTL so stale entries from a previous day's session can be
  purged. TTL is checked lazily on ``get``.

The cache intentionally has no cross-process persistence. It is a
per-server-process accelerator, not a durable store.
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

# Supported kinds — advisory, not enforced. Keeps callers honest.
KIND_SCORE = "score"
KIND_GATE = "gate"
KIND_SECURITY = "security"
KIND_QUICK_CHECK = "quick_check"

# Cache ceiling. At 4KB/entry average (rough), 2000 entries ≈ 8 MB.
_MAX_ENTRIES: int = 2000

# Default TTL (1 hour). Caller can override per-get.
_DEFAULT_TTL: float = 3600.0

# (kind, sha256) -> (value, stored_at_monotonic)
_cache: OrderedDict[tuple[str, str], tuple[dict[str, Any], float]] = OrderedDict()

# Telemetry counters (observed by tapps_doctor / tapps_stats in future slices).
_stats: dict[str, int] = {"hits": 0, "misses": 0, "sets": 0, "evictions": 0}


def content_hash(path: Path) -> str:
    """SHA-256 hex of a file's bytes. Raises FileNotFoundError if absent."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def get(kind: str, sha: str, *, ttl: float = _DEFAULT_TTL) -> dict[str, Any] | None:
    """Return a cached value if present and not expired; else ``None``."""
    entry = _cache.get((kind, sha))
    if entry is None:
        _stats["misses"] += 1
        return None
    value, stored_at = entry
    if ttl > 0 and (time.monotonic() - stored_at) > ttl:
        _cache.pop((kind, sha), None)
        _stats["misses"] += 1
        return None
    _stats["hits"] += 1
    # Move to end (LRU-ish behavior for eviction).
    _cache.move_to_end((kind, sha))
    return value


def set(kind: str, sha: str, value: dict[str, Any]) -> None:  # noqa: A001
    """Store ``value`` under ``(kind, sha)``. Evicts FIFO when over cap."""
    _cache[(kind, sha)] = (value, time.monotonic())
    _cache.move_to_end((kind, sha))
    _stats["sets"] += 1
    while len(_cache) > _MAX_ENTRIES:
        _cache.popitem(last=False)
        _stats["evictions"] += 1


def clear() -> None:
    """Empty the cache and reset stats (for tests and tapps_doctor reset)."""
    _cache.clear()
    for k in _stats:
        _stats[k] = 0


def stats() -> dict[str, int]:
    """Return a copy of hit/miss/set/eviction counters."""
    return dict(_stats)


def size() -> int:
    """Current number of entries in the cache."""
    return len(_cache)
