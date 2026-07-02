"""Disk cache for test edges (TAP-4080)."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import structlog

from tapps_core.cache import AtomicJsonCache, register_cache_stats
from tapps_mcp.project.test_linker import TestEdge

logger = structlog.get_logger(__name__)

TEST_EDGES_CACHE_REL = ".tapps-mcp/test-edges.json"

# ADR-0029 / TAP-4561: unified cache-stats counters (test edge load hits/misses).
_stats: dict[str, int] = {"hits": 0, "misses": 0}
register_cache_stats("test_edges", lambda: dict(_stats))


def load_test_edges_cache(project_root: Path) -> list[TestEdge] | None:
    """Load cached test edges from disk, or None if cache is missing/unreadable.

    Returns None on cache miss or read failure; a derived cache treats this
    as a cache miss and rebuilds.
    """
    path = project_root / TEST_EDGES_CACHE_REL
    if not path.is_file():
        _stats["misses"] += 1
        return None
    raw = AtomicJsonCache.read_json(path)
    if raw is None:
        logger.warning("test_edges_cache_read_failed", path=str(path))
        _stats["misses"] += 1
        return None
    if not isinstance(raw, list):
        _stats["misses"] += 1
        return None
    edges = _test_edges_from_list(raw)
    if edges is None:
        _stats["misses"] += 1
        return None
    _stats["hits"] += 1
    return edges


def save_test_edges_cache(project_root: Path, edges: list[TestEdge]) -> None:
    """Save test edges to disk atomically.

    On write failure, logs a warning and leaves the cache untouched.
    """
    path = project_root / TEST_EDGES_CACHE_REL
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # sort_keys/indent preserve the exact prior byte layout (ADR-0029 pilot).
        AtomicJsonCache.write_json(path, _test_edges_to_list(edges), indent=2, sort_keys=True)
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
