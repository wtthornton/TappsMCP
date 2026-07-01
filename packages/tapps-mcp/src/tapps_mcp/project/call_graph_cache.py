"""Disk cache for call graph indexes (TAP-4053)."""

from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path

import structlog

from tapps_core.cache import (
    AtomicJsonCache,
    FingerprintStaleness,
    VersionStaleness,
    register_cache_stats,
)
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
    DeferredCall,
    ModuleExports,
    ParseFailure,
    PerFileRaw,
    ResolutionGap,
    RouteEdge,
    SymbolRecord,
)

logger = structlog.get_logger(__name__)

# ADR-0029 / TAP-4561: unified cache-stats counters (index load hits/misses).
_stats: dict[str, int] = {"hits": 0, "misses": 0}
register_cache_stats("call_graph", lambda: dict(_stats))


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
        _stats["misses"] += 1
        return None
    raw = AtomicJsonCache.read_json(path)
    if raw is None:
        logger.warning("call_graph_cache_read_failed", path=str(path))
        _stats["misses"] += 1
        return None
    if not isinstance(raw, dict):
        _stats["misses"] += 1
        return None
    _stats["hits"] += 1
    return index_from_dict(raw)


def save_call_graph_index(project_root: Path, index: CallGraphIndex) -> None:
    path = project_root / CALL_GRAPH_CACHE_REL
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # sort_keys/indent preserve the exact prior byte layout (ADR-0029 pilot).
        AtomicJsonCache.write_json(path, index_to_dict(index), indent=2, sort_keys=True)
    except OSError as exc:
        logger.warning("call_graph_cache_write_failed", path=str(path), error=str(exc))


def _module_exports_to_dict(exports: ModuleExports) -> dict[str, object]:
    return {
        "module": exports.module,
        "default_symbol": exports.default_symbol,
        # tuple values (specifier, origin_name) serialize as JSON lists.
        "reexports": {k: list(v) for k, v in exports.reexports.items()},
        "star_reexports": list(exports.star_reexports),
    }


def _deferred_call_to_dict(deferred: DeferredCall) -> dict[str, object]:
    return {
        "gap": asdict(deferred.gap),
        "kind": deferred.kind,
        "imported_name": deferred.imported_name,
        "target_module": deferred.target_module,
        "specifier": deferred.specifier,
        "caller": deferred.caller,
    }


def _per_file_raw_to_dict(raw: PerFileRaw) -> dict[str, object]:
    return {
        "symbols": [asdict(s) for s in raw.symbols],
        "edges": [asdict(e) for e in raw.edges],
        "gaps": [asdict(g) for g in raw.gaps],
        "parse_failures": [asdict(p) for p in raw.parse_failures],
        "routes": [asdict(r) for r in raw.routes],
        "ts_module": raw.ts_module,
        "ts_exports": (
            _module_exports_to_dict(raw.ts_exports) if raw.ts_exports is not None else None
        ),
        "ts_deferred": [_deferred_call_to_dict(d) for d in raw.ts_deferred],
    }


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
        # Incremental-reindex material (TAP-4533).
        "per_file_fingerprints": dict(index.per_file_fingerprints),
        "raw_by_file": {rel: _per_file_raw_to_dict(raw) for rel, raw in index.raw_by_file.items()},
    }


def _module_exports_from_dict(raw: dict[str, object]) -> ModuleExports:
    reexports_raw = raw.get("reexports", {})
    reexports: dict[str, tuple[str, str]] = {}
    if isinstance(reexports_raw, dict):
        for key, value in reexports_raw.items():
            if isinstance(value, (list, tuple)) and len(value) == 2:
                reexports[str(key)] = (str(value[0]), str(value[1]))
    star_raw = raw.get("star_reexports", [])
    star = [str(s) for s in star_raw] if isinstance(star_raw, list) else []
    default_symbol = raw.get("default_symbol")
    return ModuleExports(
        module=str(raw.get("module", "")),
        default_symbol=str(default_symbol) if default_symbol is not None else None,
        reexports=reexports,
        star_reexports=star,
    )


def _deferred_call_from_dict(raw: dict[str, object]) -> DeferredCall | None:
    gap_raw = raw.get("gap")
    if not isinstance(gap_raw, dict):
        return None
    imported = raw.get("imported_name")
    target = raw.get("target_module")
    return DeferredCall(
        gap=ResolutionGap(**gap_raw),
        kind=str(raw.get("kind", "named")),  # type: ignore[arg-type]
        imported_name=str(imported) if imported is not None else None,
        target_module=str(target) if target is not None else None,
        specifier=str(raw.get("specifier", "")),
        caller=str(raw.get("caller", "")),
    )


def _as_int(value: object, default: int) -> int:
    """Coerce an untyped JSON value to ``int``, falling back to *default*."""
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, str)):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _dict_items(value: object) -> list[dict[str, object]]:
    """Return the ``dict`` elements of *value* if it is a list, else ``[]``.

    Narrows an untyped JSON value (``object``) to an iterable of dicts so the
    ``Cls(**d)`` reconstructors below are type-clean without per-line ignores.
    """
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _per_file_raw_from_dict(raw: dict[str, object]) -> PerFileRaw:
    symbols = [SymbolRecord(**s) for s in _dict_items(raw.get("symbols"))]  # type: ignore[arg-type]
    edges = [CallEdge(**e) for e in _dict_items(raw.get("edges"))]  # type: ignore[arg-type]
    gaps = [ResolutionGap(**g) for g in _dict_items(raw.get("gaps"))]  # type: ignore[arg-type]
    failures = [ParseFailure(**p) for p in _dict_items(raw.get("parse_failures"))]  # type: ignore[arg-type]
    routes = [RouteEdge(**r) for r in _dict_items(raw.get("routes"))]  # type: ignore[arg-type]
    ts_module_raw = raw.get("ts_module")
    ts_module = str(ts_module_raw) if ts_module_raw is not None else None
    ts_exports_raw = raw.get("ts_exports")
    ts_exports = (
        _module_exports_from_dict(ts_exports_raw) if isinstance(ts_exports_raw, dict) else None
    )
    ts_deferred = [
        d
        for d in (_deferred_call_from_dict(item) for item in _dict_items(raw.get("ts_deferred")))
        if d is not None
    ]
    return PerFileRaw(
        symbols=symbols,
        edges=edges,
        gaps=gaps,
        parse_failures=failures,
        routes=routes,
        ts_module=ts_module,
        ts_exports=ts_exports,
        ts_deferred=ts_deferred,
    )


def index_from_dict(raw: dict[str, object]) -> CallGraphIndex:
    symbols = [SymbolRecord(**s) for s in _dict_items(raw.get("symbols"))]  # type: ignore[arg-type]
    edges = [CallEdge(**e) for e in _dict_items(raw.get("edges"))]  # type: ignore[arg-type]
    gaps = [ResolutionGap(**g) for g in _dict_items(raw.get("resolution_gaps"))]  # type: ignore[arg-type]
    failures = [ParseFailure(**p) for p in _dict_items(raw.get("parse_failures"))]  # type: ignore[arg-type]
    routes = [RouteEdge(**r) for r in _dict_items(raw.get("routes"))]  # type: ignore[arg-type]
    per_file_raw = raw.get("per_file_fingerprints", {})
    per_file_fingerprints = (
        {str(k): str(v) for k, v in per_file_raw.items()} if isinstance(per_file_raw, dict) else {}
    )
    raw_by_file_raw = raw.get("raw_by_file", {})
    raw_by_file = (
        {
            str(rel): _per_file_raw_from_dict(entry)
            for rel, entry in raw_by_file_raw.items()
            if isinstance(entry, dict)
        }
        if isinstance(raw_by_file_raw, dict)
        else {}
    )
    return CallGraphIndex(
        symbols=symbols,
        edges=edges,
        resolution_gaps=gaps,
        parse_failures=failures,
        routes=routes,
        project_root=str(raw.get("project_root", "")),
        fingerprint=str(raw.get("fingerprint", "")),
        version=_as_int(raw.get("version"), INDEX_VERSION),
        per_file_fingerprints=per_file_fingerprints,
        raw_by_file=raw_by_file,
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

    if VersionStaleness(INDEX_VERSION).is_stale(cached.version):
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
    stale = FingerprintStaleness(current_fp).is_stale(cached.fingerprint)
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
