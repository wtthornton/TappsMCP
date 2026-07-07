"""Fingerprint-keyed disk cache for test edges (TAP-4080, ADR-0029).

TESTS edges are a deterministic derivative of the call-graph index, so this
cache follows the same content-fingerprint model as the call-graph cache
(``call_graph_cache.py``): the cached payload embeds the call-graph fingerprint
it was built from, and :class:`FingerprintStaleness` rejects it the moment the
current fingerprint differs. No TTL, no clock — fresh exactly while the call
graph is unchanged.

Built on the ADR-0029 substrate (``AtomicJsonCache`` + ``FingerprintStaleness``);
no hand-rolled atomic-write or staleness code.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import structlog

from tapps_core.cache import AtomicJsonCache, FingerprintStaleness, register_cache_stats
from tapps_mcp.project.test_linker import TestEdge

logger = structlog.get_logger(__name__)

# Fingerprint-keyed cache path (TAP-4080). Distinct from the pre-TAP-4080
# fixed-path file — this one is validated against the call-graph fingerprint.
TEST_EDGES_CACHE_REL = ".tapps-mcp/test-edges-index.json"

# ADR-0029 / TAP-4561: unified cache-stats counters (test edge load hits/misses).
_stats: dict[str, int] = {"hits": 0, "misses": 0}
register_cache_stats("test_edges", lambda: dict(_stats))


def _reset_test_edges_stats() -> None:
    """Reset hit/miss counters (test isolation — conftest ``_reset_caches``)."""
    _stats["hits"] = 0
    _stats["misses"] = 0


def load_test_edges_cache(project_root: Path, fingerprint: str) -> list[TestEdge] | None:
    """Load cached test edges when fresh for *fingerprint*, else ``None``.

    Returns ``None`` on a missing file, an unreadable/malformed payload, or a
    fingerprint mismatch (the cache was built from a stale call graph). The
    caller treats every ``None`` as a miss and rebuilds — a stale cache is never
    served.
    """
    path = project_root / TEST_EDGES_CACHE_REL
    if not path.is_file():
        _stats["misses"] += 1
        return None
    raw = AtomicJsonCache.read_json(path)
    if not isinstance(raw, dict):
        if raw is not None:
            logger.warning("test_edges_cache_read_failed", path=str(path))
        _stats["misses"] += 1
        return None

    cached_fp = raw.get("fingerprint")
    if not isinstance(cached_fp, str) or FingerprintStaleness(fingerprint).is_stale(cached_fp):
        # Stale: cached edges came from a different call-graph fingerprint.
        _stats["misses"] += 1
        return None

    raw_edges = raw.get("edges")
    if not isinstance(raw_edges, list):
        _stats["misses"] += 1
        return None
    edges = _test_edges_from_list(raw_edges)
    if edges is None:
        _stats["misses"] += 1
        return None
    _stats["hits"] += 1
    return edges


def save_test_edges_cache(
    project_root: Path, fingerprint: str, edges: list[TestEdge]
) -> None:
    """Persist *edges* keyed by *fingerprint*, atomically.

    On write failure, logs a warning and leaves the cache untouched.
    """
    path = project_root / TEST_EDGES_CACHE_REL
    payload = {"fingerprint": fingerprint, "edges": _test_edges_to_list(edges)}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        AtomicJsonCache.write_json(path, payload, indent=2, sort_keys=True)
    except OSError as exc:
        logger.warning("test_edges_cache_write_failed", path=str(path), error=str(exc))


def _test_edges_to_list(edges: list[TestEdge]) -> list[dict[str, object]]:
    """Serialize TestEdge list to JSON-compatible list of dicts."""
    return [asdict(e) for e in edges]


def _test_edges_from_list(raw: list[object]) -> list[TestEdge] | None:
    """Deserialize JSON list of dicts back to TestEdge list.

    Returns None if deserialization fails (malformed or wrong structure).
    """
    try:
        edges: list[TestEdge] = []
        for item in raw:
            if not isinstance(item, dict):
                return None
            edge = TestEdge(
                test_symbol=str(item.get("test_symbol", "")),
                test_file=str(item.get("test_file", "")),
                code_symbol=str(item.get("code_symbol", "")),
                code_file=str(item.get("code_file", "")),
                line=int(item.get("line", 0)),
            )
            edges.append(edge)
        return edges
    except (TypeError, ValueError, KeyError):
        return None
