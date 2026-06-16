"""Disk cache for call graph indexes (TAP-4053)."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

import structlog

from tapps_mcp.project.call_graph_types import (
    CALL_GRAPH_CACHE_REL,
    INDEX_VERSION,
    CallEdge,
    CallGraphIndex,
    ResolutionGap,
    SymbolRecord,
)
from tapps_mcp.project.import_graph import _DEFAULT_EXCLUDES, _should_skip

logger = structlog.get_logger(__name__)


def _write_atomic(target: Path, content: str) -> None:
    """Write *content* to *target* atomically via tempfile + replace (TAP-4075)."""
    fd, tmp_path = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=".tmp_",
        suffix=target.suffix,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        Path(tmp_path).replace(target)
    except BaseException:
        with contextlib.suppress(OSError):
            Path(tmp_path).unlink()
        raise


def index_fingerprint(
    project_root: Path,
    exclude_patterns: list[str] | None,
    top_level_package: str,
) -> str:
    excludes = set(_DEFAULT_EXCLUDES)
    if exclude_patterns:
        excludes.update(exclude_patterns)
    parts = [f"v{INDEX_VERSION}", top_level_package]
    for py_file in sorted(project_root.rglob("*.py")):
        if _should_skip(py_file, excludes) or py_file.name.endswith("_pb2.py"):
            continue
        try:
            stat = py_file.stat()
        except OSError:
            continue
        parts.append(f"{py_file.relative_to(project_root)}:{stat.st_mtime_ns}:{stat.st_size}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def load_call_graph_index(project_root: Path) -> CallGraphIndex | None:
    path = project_root / CALL_GRAPH_CACHE_REL
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("call_graph_cache_read_failed", path=str(path), error=str(exc))
        return None
    if not isinstance(raw, dict):
        return None
    return index_from_dict(raw)


def save_call_graph_index(project_root: Path, index: CallGraphIndex) -> None:
    path = project_root / CALL_GRAPH_CACHE_REL
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(index_to_dict(index), indent=2, sort_keys=True)
        _write_atomic(path, payload)
    except OSError as exc:
        logger.warning("call_graph_cache_write_failed", path=str(path), error=str(exc))


def index_to_dict(index: CallGraphIndex) -> dict[str, object]:
    return {
        "version": index.version,
        "fingerprint": index.fingerprint,
        "project_root": index.project_root,
        "symbols": [asdict(s) for s in index.symbols],
        "edges": [asdict(e) for e in index.edges],
        "resolution_gaps": [asdict(g) for g in index.resolution_gaps],
    }


def index_from_dict(raw: dict[str, object]) -> CallGraphIndex:
    symbols = [SymbolRecord(**s) for s in raw.get("symbols", []) if isinstance(s, dict)]  # type: ignore[arg-type]
    edges = [CallEdge(**e) for e in raw.get("edges", []) if isinstance(e, dict)]  # type: ignore[arg-type]
    gaps = [ResolutionGap(**g) for g in raw.get("resolution_gaps", []) if isinstance(g, dict)]  # type: ignore[arg-type]
    return CallGraphIndex(
        symbols=symbols,
        edges=edges,
        resolution_gaps=gaps,
        project_root=str(raw.get("project_root", "")),
        fingerprint=str(raw.get("fingerprint", "")),
        version=int(raw.get("version", INDEX_VERSION)),
    )


def summarize_call_graph_cache(project_root: Path) -> dict[str, object]:
    """Lightweight call-graph cache status for session_start and doctor (TAP-4074)."""
    cache_path = project_root / CALL_GRAPH_CACHE_REL
    if not cache_path.is_file():
        return {
            "status": "missing",
            "ready": False,
            "stale": False,
            "hint": "Call tapps_call_graph(symbol='...', query='callers') to build the index.",
        }

    cached = load_call_graph_index(project_root)
    if cached is None:
        return {
            "status": "unreadable",
            "ready": False,
            "stale": True,
            "hint": "Cache unreadable — rebuild via tapps_call_graph(force_rebuild=true).",
        }

    if cached.version != INDEX_VERSION:
        return {
            "status": "stale",
            "ready": False,
            "stale": True,
            "reason": "index_version_mismatch",
            "cached_version": cached.version,
            "current_version": INDEX_VERSION,
            "symbols": len(cached.symbols),
            "edges": len(cached.edges),
            "hint": "Index schema changed — rebuild via tapps_call_graph(force_rebuild=true).",
        }

    current_fp = index_fingerprint(project_root, None, "")
    stale = cached.fingerprint != current_fp
    edge_count = len(cached.edges)
    gap_count = len(cached.resolution_gaps)

    age_hours: float | None = None
    try:
        import time

        age_hours = round((time.time() - cache_path.stat().st_mtime) / 3600, 1)
    except OSError:
        pass

    status = "stale" if stale else "ready"
    result: dict[str, object] = {
        "status": status,
        "ready": not stale,
        "stale": stale,
        "symbols": len(cached.symbols),
        "edges": edge_count,
        "resolution_gaps": gap_count,
        "gap_rate": round(gap_count / max(edge_count, 1), 3),
        "age_hours": age_hours,
    }
    if stale:
        result["hint"] = "Call graph index is stale — tapps_call_graph(force_rebuild=true)."
    return result
