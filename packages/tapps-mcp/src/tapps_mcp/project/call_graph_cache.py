"""Disk cache for call graph indexes (TAP-4053)."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

import structlog

from tapps_mcp.pipeline.agent_contract import (
    CALL_GRAPH_DEGRADED_HINT,
    CALL_GRAPH_STALE_HINT,
)
from tapps_mcp.project.call_graph_fingerprint import (
    CallGraphFingerprintSettings,
    compute_index_fingerprint,
    fingerprint_settings,
)
from tapps_mcp.project.call_graph_gap_classify import split_gap_counts
from tapps_mcp.project.call_graph_types import (
    CALL_GRAPH_CACHE_REL,
    INDEX_VERSION,
    CallEdge,
    CallGraphIndex,
    ParseFailure,
    ResolutionGap,
    RouteEdge,
    SymbolRecord,
)

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
    """Backward-compatible fingerprint wrapper (TAP-4077)."""
    settings = fingerprint_settings(
        project_root,
        exclude_patterns=exclude_patterns,
        top_level_package=top_level_package,
    )
    return compute_index_fingerprint(settings, index_version=INDEX_VERSION)


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
        "parse_failures": [asdict(p) for p in index.parse_failures],
        "routes": [asdict(r) for r in index.routes],
    }


def index_from_dict(raw: dict[str, object]) -> CallGraphIndex:
    symbols = [SymbolRecord(**s) for s in raw.get("symbols", []) if isinstance(s, dict)]  # type: ignore[arg-type]
    edges = [CallEdge(**e) for e in raw.get("edges", []) if isinstance(e, dict)]  # type: ignore[arg-type]
    gaps = [ResolutionGap(**g) for g in raw.get("resolution_gaps", []) if isinstance(g, dict)]  # type: ignore[arg-type]
    failures = [
        ParseFailure(**p) for p in raw.get("parse_failures", []) if isinstance(p, dict)
    ]  # type: ignore[arg-type]
    routes = [RouteEdge(**r) for r in raw.get("routes", []) if isinstance(r, dict)]  # type: ignore[arg-type]
    return CallGraphIndex(
        symbols=symbols,
        edges=edges,
        resolution_gaps=gaps,
        parse_failures=failures,
        routes=routes,
        project_root=str(raw.get("project_root", "")),
        fingerprint=str(raw.get("fingerprint", "")),
        version=int(raw.get("version", INDEX_VERSION)),
    )


def _gap_reason_counts(gaps: list[ResolutionGap]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for gap in gaps:
        counts[gap.reason] = counts.get(gap.reason, 0) + 1
    return dict(sorted(counts.items()))


def summarize_call_graph_cache(
    project_root: Path,
    *,
    fp_settings: CallGraphFingerprintSettings | None = None,
) -> dict[str, object]:
    """Lightweight call-graph cache status for session_start and doctor (TAP-4074)."""
    settings = fp_settings or fingerprint_settings(project_root)
    cache_path = settings.project_root / CALL_GRAPH_CACHE_REL
    if not cache_path.is_file():
        return {
            "status": "missing",
            "ready": False,
            "stale": False,
            "hint": "Call tapps_call_graph(symbol='...', query='callers') to build the index.",
        }

    cached = load_call_graph_index(settings.project_root)
    if cached is None:
        return {
            "status": "unreadable",
            "ready": False,
            "stale": True,
            "hint": CALL_GRAPH_STALE_HINT,
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
            "hint": CALL_GRAPH_STALE_HINT,
        }

    current_fp = compute_index_fingerprint(settings, index_version=INDEX_VERSION)
    stale = cached.fingerprint != current_fp
    edge_count = len(cached.edges)
    gap_count = len(cached.resolution_gaps)
    parse_fail_count = len(cached.parse_failures)

    age_hours: float | None = None
    try:
        age_hours = round((time.time() - cache_path.stat().st_mtime) / 3600, 1)
    except OSError:
        pass

    external_gaps, in_repo_gaps, in_repo_gap_reasons = split_gap_counts(cached.resolution_gaps)
    in_repo_gap_rate = round(in_repo_gaps / max(edge_count, 1), 3)

    status = "stale" if stale else "ready"
    degraded = parse_fail_count > 0 or in_repo_gaps > 0
    result: dict[str, object] = {
        "status": status,
        "ready": not stale,
        "stale": stale,
        "degraded": degraded,
        "symbols": len(cached.symbols),
        "edges": edge_count,
        "resolution_gaps": gap_count,
        "external_gaps": external_gaps,
        "in_repo_gaps": in_repo_gaps,
        "gap_rate": round(gap_count / max(edge_count, 1), 3),
        "in_repo_gap_rate": in_repo_gap_rate,
        "gap_reasons": _gap_reason_counts(cached.resolution_gaps),
        "in_repo_gap_reasons": in_repo_gap_reasons,
        "parse_failures": parse_fail_count,
        "age_hours": age_hours,
    }
    if stale:
        result["hint"] = CALL_GRAPH_STALE_HINT
    elif parse_fail_count:
        result["hint"] = (
            f"{parse_fail_count} file(s) failed to parse — graph is incomplete for those modules."
        )
    elif degraded and in_repo_gaps:
        result["hint"] = CALL_GRAPH_DEGRADED_HINT
    return result


def invalidate_call_graph_cache_if_schema_stale(
    project_root: Path,
    *,
    dry_run: bool = False,
) -> dict[str, object]:
    """Remove call-graph cache when index schema version lags ``INDEX_VERSION`` (Epic 114).

    Called from ``upgrade_pipeline`` so consumers do not keep v1 indexes after upgrading.
    """
    path = project_root / CALL_GRAPH_CACHE_REL
    if not path.is_file():
        return {"action": "skipped", "reason": "no_cache"}

    cached = load_call_graph_index(project_root)
    if cached is None:
        if dry_run:
            return {"action": "would_remove", "reason": "unreadable"}
        path.unlink(missing_ok=True)
        return {"action": "removed", "reason": "unreadable"}

    if cached.version == INDEX_VERSION:
        return {
            "action": "skipped",
            "reason": "current_schema",
            "version": INDEX_VERSION,
        }

    payload: dict[str, object] = {
        "action": "would_remove" if dry_run else "removed",
        "reason": "index_version_mismatch",
        "cached_version": cached.version,
        "current_version": INDEX_VERSION,
    }
    if not dry_run:
        path.unlink(missing_ok=True)
    return payload
