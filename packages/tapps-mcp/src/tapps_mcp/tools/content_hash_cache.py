"""SHA-256 content-hash cache for per-file tool results (STORY-101.1).

Motivation: scoring, quality-gate evaluation, and security scanning are all
deterministic functions of file content. If the same file is queried
repeatedly without editing (a common pattern when agents loop through
quick_check → validate_changed → checklist), we can return the previous
result directly.

Design:
- Keys are ``(kind, entry_key)`` tuples, where ``entry_key`` is built by
  :func:`result_key` from the file bytes **plus every other input the cached
  result depends on** — the resolved path and the gate preset.
- Values are opaque ``dict[str, Any]`` (the tool's response or a sub-slice
  of it — the caller decides what to store).

The path is part of the key (TAP-5401). An earlier revision keyed on content
alone, on the theory that "renaming or copying a file should still hit the
cache". That is wrong for the scoring pipeline: three of the seven score
categories — ``devex``, ``structure``, and ``test_coverage`` — are pure
functions of *directory context* (proximity to ``AGENTS.md``, the nearest
project root, sibling test files) and do not read the file's bytes at all.
Byte-identical files at different depths legitimately score differently, so a
content-only key served the first location's ``overall_score``,
``gate_passed``, and ``file_path`` to the second — silently corrupting the
"score a pristine copy and compare against the working copy" workflow. The
preset is in the key for the same reason: a ``standard`` verdict is not a
``strict`` verdict.
- Bounded by ``_MAX_ENTRIES`` to prevent unbounded memory growth in
  long-lived servers; eviction is LRU (least-recently-used).
- Optional TTL so stale entries from a previous day's session can be
  purged. TTL is checked lazily on ``get``.

The cache intentionally has no cross-process persistence. It is a
per-server-process accelerator, not a durable store.
"""

from __future__ import annotations

import copy
import hashlib
import threading
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

# TAP-1797: serialise all OrderedDict mutations + stats updates. Async tool
# handlers offload hash+lookup work onto threads (`asyncio.to_thread`); without
# this lock, concurrent `move_to_end` / `popitem` / `__setitem__` calls hit
# `RuntimeError: OrderedDict mutated during iteration` and lose entries.
_lock = threading.Lock()


def content_hash(path: Path) -> str:
    """SHA-256 hex of a file's bytes. Raises FileNotFoundError if absent."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sibling_test_signature(path: Path) -> str:
    """TAP-6608: exact/fuzzy test-sibling match counts for *path*'s stem.

    The ``test_coverage`` category is a pure function of this state (see
    ``scoring.coverage_heuristic``), and content + path alone cannot see it:
    adding or removing a name-matched test file (``test_auth.py`` for
    ``auth.py``) changes nothing about ``auth.py``'s own bytes or location.
    Folded into the cache key so that add/remove forces a rescore immediately
    instead of waiting out the TTL.
    """
    from tapps_mcp.scoring.coverage_heuristic import _count_test_files, _find_project_root

    root = _find_project_root(path)
    if root is None:
        return "0:0"
    exact, fuzzy = _count_test_files(root, path.stem)
    return f"{exact}:{fuzzy}"


def result_key(path: Path, *, preset: str) -> str:
    """Cache key for a per-file tool result.

    Combines the file's content hash with the inputs the result also depends
    on but that the bytes do not capture: the resolved path (directory context
    drives the ``devex`` / ``structure`` / ``test_coverage`` categories), the
    gate ``preset`` (drives ``gate_passed``), and the sibling-test signature
    (TAP-6608, see :func:`_sibling_test_signature`). See the module docstring.
    """
    return f"{content_hash(path)}|{path.resolve()}|{preset}|{_sibling_test_signature(path)}"


def get(kind: str, sha: str, *, ttl: float = _DEFAULT_TTL) -> dict[str, Any] | None:
    """Return a cached value if present and not expired; else ``None``."""
    with _lock:
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
        return copy.deepcopy(value)


def set(kind: str, sha: str, value: dict[str, Any]) -> None:  # noqa: A001
    """Store ``value`` under ``(kind, sha)``. Evicts LRU when over cap."""
    with _lock:
        # Copy so callers cannot mutate the live cache entry after set.
        _cache[(kind, sha)] = (copy.deepcopy(value), time.monotonic())
        _cache.move_to_end((kind, sha))
        _stats["sets"] += 1
        while len(_cache) > _MAX_ENTRIES:
            _cache.popitem(last=False)
            _stats["evictions"] += 1


def clear() -> None:
    """Empty the cache and reset stats (for tests and tapps_doctor reset)."""
    with _lock:
        _cache.clear()
        for k in _stats:
            _stats[k] = 0


def stats() -> dict[str, int]:
    """Return a copy of hit/miss/set/eviction counters."""
    with _lock:
        return dict(_stats)


def size() -> int:
    """Current number of entries in the cache."""
    with _lock:
        return len(_cache)


# ADR-0029 / TAP-4561: report into the unified cache-stats surface.
from tapps_core.cache import register_cache_stats as _register_cache_stats

_register_cache_stats("content_hash", lambda: {**stats(), "size": size()})
