"""Analysis and inspection tool handlers for TappsMCP.

Contains: tapps_report, tapps_dead_code, tapps_dependency_scan,
tapps_dependency_graph, tapps_session_notes, tapps_impact_analysis,
tapps_call_graph, tapps_diff_impact.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:`register`.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json as _json
import os
import time
from datetime import UTC, datetime
from pathlib import Path as _Path
from typing import TYPE_CHECKING, Any

import structlog
from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

from tapps_core.config.settings import load_settings
from tapps_mcp.mcp_register import register_tool
from tapps_mcp.server_helpers import (
    _get_brain_bridge,
    build_impact_memory_context,
    emit_ctx_info,
    ensure_session_initialized,
    error_response,
    success_response,
)
from tapps_mcp.tools.project_paths import (
    resolve_effective_project_root,
    resolve_path_under_root,
    validate_read_path_under_root,
)

if TYPE_CHECKING:
    from pathlib import Path

    from mcp.server.fastmcp import FastMCP

    from tapps_mcp.project.models import SessionNote
    from tapps_mcp.project.session_notes import SessionNoteStore

logger = structlog.get_logger(__name__)

# Cap simultaneous file scorers in project-wide reports. Each scorer forks
# ruff + mypy + bandit + radon + vulture subprocesses, so an unbounded
# asyncio.gather over max_files (up to 100) spawns hundreds of processes at
# once and blows past the request deadline / file-descriptor limits.
_REPORT_MAX_CONCURRENCY = min(8, (os.cpu_count() or 4))

# Interval between project-wide progress heartbeats. Module-level so tests can
# shrink it to exercise the heartbeat wake-up path quickly.
_REPORT_HEARTBEAT_INTERVAL_S = 5.0

# ---------------------------------------------------------------------------
# Tool annotation presets
# ---------------------------------------------------------------------------

_ANNOTATIONS_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

_ANNOTATIONS_READ_ONLY_OPEN = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)

# TAP-2798: tapps_audit_close_coverage writes a brain coverage record (a
# side effect) but is idempotent — re-closing the same file at the same SHA
# yields the same final state (sha set, tickets deduped).
_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

# TAP-961: large-output tools advertise a per-tool result-size ceiling via
# the MCP `_meta` tool field. Claude Code reads `anthropic/maxResultSizeChars`
# from `tools/list` and keeps the result in-context instead of persisting it
# to disk as a file reference. Ceiling chosen conservatively under the 500K
# spec maximum — dependency_graph can be large on big repos (see TAP-613),
# so it gets a higher cap than the other three.
_META_LARGE_OUTPUT_200K: dict[str, Any] = {"anthropic/maxResultSizeChars": 200_000}
_META_LARGE_OUTPUT_100K: dict[str, Any] = {"anthropic/maxResultSizeChars": 100_000}

# TAP-1986: tapps_impact_analysis is the only daily-driver analysis tool (eager).
# All other analysis tools are deferred — combined dicts for large-output+deferred.
_META_DEFERRED: dict[str, Any] = {"defer_loading": True}
_META_LARGE_OUTPUT_100K_D: dict[str, Any] = {**_META_LARGE_OUTPUT_100K, "defer_loading": True}
_META_LARGE_OUTPUT_200K_D: dict[str, Any] = {**_META_LARGE_OUTPUT_200K, "defer_loading": True}


# ---------------------------------------------------------------------------
# Shared helpers (imported lazily from server.py to avoid circular imports)
# ---------------------------------------------------------------------------


def _validate_file_path_lazy(file_path: str) -> Path:
    """Delegate to server._validate_file_path to avoid duplicating logic."""
    from tapps_mcp.server import _validate_file_path

    return _validate_file_path(file_path)


def _record_call(tool_name: str) -> None:
    """Delegate to server._record_call."""
    from tapps_mcp.server import _record_call as _rc

    _rc(tool_name)


def _record_execution(
    tool_name: str,
    start_ns: int,
    *,
    status: str = "success",
    file_path: str | None = None,
    gate_passed: bool | None = None,
    score: float | None = None,
    error_code: str | None = None,
    degraded: bool = False,
) -> None:
    """Delegate to server._record_execution."""
    from tapps_mcp.server import _record_execution as _re

    _re(
        tool_name,
        start_ns,
        status=status,
        file_path=file_path,
        gate_passed=gate_passed,
        score=score,
        error_code=error_code,
        degraded=degraded,
    )


def _with_nudges(
    tool_name: str,
    response: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Delegate to server._with_nudges."""
    from tapps_mcp.server import _with_nudges as _wn

    return _wn(tool_name, response, context)


# ---------------------------------------------------------------------------
# Session note store singleton
# ---------------------------------------------------------------------------

_session_store: SessionNoteStore | None = None


def _get_session_store() -> SessionNoteStore:
    """Lazily create or return the session note store."""
    global _session_store
    if _session_store is None:
        from tapps_mcp.project.session_notes import SessionNoteStore

        settings = load_settings()
        _session_store = SessionNoteStore(settings.project_root)
    return _session_store


def _reset_session_store() -> None:
    """Reset the session store singleton (for testing)."""
    global _session_store
    _session_store = None


async def _promote_note_to_memory(note: SessionNote, tier: str = "context") -> dict[str, Any]:
    """Promote a session note to memory via BrainBridge (TAP-414).

    Always writes with ``scope="session"`` and the requested tier (default
    ``context``) so promoted notes match the EPIC-95.5 contract for
    session-scoped tapps-brain entries.
    """
    try:
        from tapps_mcp.server_helpers import _get_brain_bridge

        bridge = _get_brain_bridge()
        if bridge is None:
            return {
                "action": "promote",
                "promoted": False,
                "degraded": True,
                "reason": "TAPPS_BRAIN_DATABASE_URL not configured",
            }
        entry = await bridge.save(
            key=note.key,
            value=note.value,
            tier=tier,
            scope="session",
            source="agent",
            source_agent="session-promote",
            tags=["promoted-from-session-notes"],
        )
        return {
            "action": "promote",
            "promoted": True,
            "memory_entry": entry,
        }
    except Exception as exc:
        logger.debug("promote_to_memory_failed", key=note.key, error=str(exc))
        return {
            "action": "promote",
            "promoted": False,
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# tapps_session_notes
# ---------------------------------------------------------------------------


async def tapps_session_notes(action: str, key: str = "", value: str = "") -> dict[str, Any]:
    """Stores short-lived per-session notes in a local KV store, with the
    option to promote a note into cross-session brain memory.

    Call this when you want to remember intermediate findings during a
    task ("library X has bug Y", "the failing test is in Z") without
    polluting brain memory — notes are session-scoped and discarded when
    the MCP server restarts. Promote (``action="promote"``) only when
    the note is durable architectural knowledge worth carrying forward;
    for direct durable storage use ``tapps_memory(action="save")``.

    Args:
        action: ``"save"`` (store key→value), ``"get"`` (read by key),
            ``"list"`` (enumerate all keys), ``"clear"`` (wipe the
            session store), or ``"promote"`` (move a saved note into
            brain memory at the named tier).
        key: Note key. Required for ``save``, ``get``, and ``promote``.
            Use short slugs (``"failing-test"``, ``"lib-issue"``).
        value: Note value (required for ``save``). For ``promote``,
            optional brain tier override: ``"architectural"``,
            ``"pattern"``, ``"procedural"``, or ``"context"`` (default).
    """
    start = time.perf_counter_ns()
    _record_call("tapps_session_notes")

    store = _get_session_store()
    data: dict[str, Any] = {}

    if action == "save":
        if not key or not value:
            return error_response(
                "tapps_session_notes",
                "missing_params",
                "save requires key and value",
            )
        note = store.save(key, value)
        data = {"action": "save", "note": note.model_dump()}
    elif action == "get":
        if not key:
            return error_response("tapps_session_notes", "missing_params", "get requires key")
        found = store.get(key)
        data = {
            "action": "get",
            "note": found.model_dump() if found else None,
            "found": found is not None,
        }
    elif action == "list":
        data = {"action": "list", "notes": [n.model_dump() for n in store.list_all()]}
    elif action == "clear":
        data = {"action": "clear", "cleared_count": store.clear(key or None)}
    elif action == "promote":
        if not key:
            return error_response("tapps_session_notes", "missing_params", "promote requires key")
        found = store.get(key)
        if found is None:
            return error_response("tapps_session_notes", "not_found", f"Note '{key}' not found")
        data = await _promote_note_to_memory(found, value or "context")
    else:
        return error_response(
            "tapps_session_notes",
            "invalid_action",
            f"Unknown action: {action}. Use save/get/list/clear/promote.",
        )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_session_notes", start)
    data.update(store.metadata())
    data["migration_hint"] = "Use tapps_memory for persistent cross-session storage."
    resp = success_response("tapps_session_notes", elapsed_ms, data)
    return _with_nudges("tapps_session_notes", resp)


# ---------------------------------------------------------------------------
# tapps_impact_analysis
# ---------------------------------------------------------------------------


async def tapps_impact_analysis(
    file_path: str,
    change_type: str = "modified",
    project_root: str = "",
    symbol: str = "",
    granularity: str = "module",
) -> dict[str, Any]:
    """Maps the blast radius of a file change: direct importers, transitive
    dependents, and overlapping test coverage, with a severity verdict
    (low/medium/high) based on fan-in.

    Call this before refactoring or deleting any file — especially
    public modules, framework adapters, and anything in ``__init__.py``.
    The verdict drives whether a quick check is enough or whether the
    full suite must run. Skip for new files (``change_type="added"``
    returns trivial), pure test files, and one-off scripts.

    Pass ``symbol`` with ``granularity="symbol"`` or ``"both"`` for
    function-level caller/callee blast radius (Epic 114 / ADR-0017).

    Args:
        file_path: Path to the file being changed. Must be inside the
            project root. Returns ``error.code=path_denied`` for
            traversal segments.
        change_type: ``"added"`` (new file — trivial blast radius),
            ``"modified"`` (default — analyzes current importers), or
            ``"removed"`` (analyzes who breaks when the file is gone).
        project_root: Override the project root. Default is empty (use
            server-configured root). Set this when analyzing a sibling
            repo from a long-lived server.
        symbol: Optional qualified or short function/method name for
            symbol-level analysis via the call graph.
        granularity: ``"module"`` (default), ``"symbol"``, or ``"both"``.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_impact_analysis")

    settings = load_settings()
    root_result = resolve_effective_project_root(settings.project_root, project_root)
    if root_result.error_code:
        return error_response(
            "tapps_impact_analysis",
            root_result.error_code,
            root_result.error_message or "",
        )
    root = root_result.root

    if project_root:
        try:
            resolved = validate_read_path_under_root(file_path, root)
        except (ValueError, FileNotFoundError) as exc:
            return error_response("tapps_impact_analysis", "path_denied", str(exc))
    else:
        try:
            resolved = _validate_file_path_lazy(file_path)
        except (ValueError, FileNotFoundError) as exc:
            return error_response("tapps_impact_analysis", "path_denied", str(exc))

    from tapps_mcp.project.impact_analyzer import analyze_impact, analyze_symbol_impact

    report = analyze_impact(resolved, root, change_type)
    mem_ctx = build_impact_memory_context(resolved, root, settings)

    symbol_granularity = granularity.strip().lower() or "module"
    symbol_block: dict[str, object] | None = None
    if symbol.strip() and symbol_granularity in {"symbol", "both"}:
        symbol_block = analyze_symbol_impact(symbol.strip(), root)

    # TAP-2007: write procedural refactor-sequence memory on completion.
    from tapps_mcp.tools.procedural_patterns import fire_refactor_sequence

    fire_refactor_sequence(
        str(resolved),
        report.severity,
        len(report.direct_dependents),
        report.recommendations,
    )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_impact_analysis", start, file_path=str(resolved))

    recommendations = list(report.recommendations)
    from tapps_mcp.pipeline.document_judges import is_document_layout_path

    if is_document_layout_path(resolved, root):
        recommendations.append(
            "Document layout/template changed — rebuild shipped PDFs/HTML and run "
            "validate_changed shell judge (e.g. consumer audit CLI) before declaring done."
        )

    data: dict[str, Any] = {
        "changed_file": report.changed_file,
        "change_type": report.change_type,
        "severity": report.severity,
        "total_affected": report.total_affected,
        "direct_dependents": [d.model_dump() for d in report.direct_dependents],
        "transitive_dependents": [d.model_dump() for d in report.transitive_dependents],
        "test_files": [t.model_dump() for t in report.test_files],
        "recommendations": recommendations,
    }
    if symbol_block is not None:
        data["symbol"] = symbol.strip()
        data["granularity"] = symbol_granularity
        data["symbol_impact"] = symbol_block
        if symbol_block.get("recommendations"):
            for rec in symbol_block["recommendations"]:
                if isinstance(rec, str) and rec not in recommendations:
                    recommendations.append(rec)
        data["recommendations"] = recommendations
    data.update(mem_ctx)

    resp = success_response(
        "tapps_impact_analysis",
        elapsed_ms,
        data,
    )

    # Attach structured output
    try:
        from tapps_mcp.common.output_schemas import ImpactOutput

        structured = ImpactOutput(
            changed_file=report.changed_file,
            change_type=report.change_type,
            severity=report.severity,
            total_affected=report.total_affected,
            direct_dependents=[d.file_path for d in report.direct_dependents],
            test_files=[t.file_path for t in report.test_files],
            recommendations=recommendations,
            memory_context=mem_ctx.get("memory_context", []),
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        logger.debug("structured_output_failed: tapps_impact_analysis", exc_info=True)

    return _with_nudges(
        "tapps_impact_analysis",
        resp,
        {
            "granularity": symbol_granularity,
            "has_symbol": bool(symbol.strip()),
            "file_path": str(resolved),
        },
    )


# ---------------------------------------------------------------------------
# tapps_call_graph (Epic 114 Tier B)
# ---------------------------------------------------------------------------


async def tapps_call_graph(
    symbol: str,
    query: str = "all",
    project_root: str = "",
    max_depth: int = 5,
    token_budget: int = 4000,
    force_rebuild: bool = False,
) -> dict[str, Any]:
    """Query function-level callers, callees, call chains, or HTTP routes.

    Deterministic Python/TypeScript call graph (ADR-0017). Use before refactoring
    a function to replace grep-based caller discovery.

    Route queries (TAP-4532) resolve HTTP route <-> handler edges (FastAPI
    decorators, React Router JSX):
      * ``query="route_handler"`` — pass ``symbol`` as a route path (e.g.
        ``/users/{id}``); returns the handler(s) serving it.
      * ``query="handler_routes"`` — pass ``symbol`` as a handler function /
        component name; returns the routes that break if it changes (blast radius).

    Args:
        symbol: Qualified or short function/method name; a route path for
            ``route_handler``; a handler symbol for ``handler_routes``.
        query: ``callers``, ``callees``, ``chain``, ``all`` (default),
            ``route_handler``, or ``handler_routes``.
        project_root: Optional project root override.
        max_depth: Max expansion depth for graph traversal.
        token_budget: Approximate token cap for serialized graph payload.
        force_rebuild: Rebuild ``.tapps-mcp/call-graph-index.json`` cache.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_call_graph")

    settings = load_settings()
    root_result = resolve_effective_project_root(settings.project_root, project_root)
    if root_result.error_code:
        return error_response(
            "tapps_call_graph",
            root_result.error_code,
            root_result.error_message or "",
        )
    root = root_result.root

    mode = query.strip().lower() or "all"
    if mode not in {"callers", "callees", "chain", "all", "route_handler", "handler_routes"}:
        return error_response(
            "tapps_call_graph",
            "invalid_query",
            "query must be callers, callees, chain, all, route_handler, or handler_routes",
        )

    from tapps_mcp.project.call_graph import build_call_graph_index
    from tapps_mcp.project.call_graph_queries import (
        query_call_graph,
        query_route_handler,
        query_routes_for_handler,
    )

    index = build_call_graph_index(root, force_rebuild=force_rebuild)
    if mode == "route_handler":
        result = query_route_handler(index, symbol)
    elif mode == "handler_routes":
        result = query_routes_for_handler(index, symbol)
    else:
        result = query_call_graph(
            index,
            symbol,
            mode=mode,  # type: ignore[arg-type]
            max_depth=max(1, max_depth),
            token_budget=max(256, token_budget),
        )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution(
        "tapps_call_graph",
        start,
        degraded=bool(result.get("degraded")),
    )
    resp = success_response("tapps_call_graph", elapsed_ms, result)
    return _with_nudges("tapps_call_graph", resp)


# ---------------------------------------------------------------------------
# tapps_diff_impact (Epic 114 Tier C)
# ---------------------------------------------------------------------------


async def tapps_diff_impact(
    file_paths: str,
    project_root: str = "",
    force_rebuild: bool = False,
) -> dict[str, Any]:
    """Rank affected tests for changed Python files using TESTS edges.

    Combines TDAD-style test linkage, call-graph callers in tests, and
    module-level import impact heuristics.

    Args:
        file_paths: Comma-separated paths to changed Python files.
        project_root: Optional project root override.
        force_rebuild: Rebuild call graph index before analysis.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_diff_impact")

    settings = load_settings()
    root_result = resolve_effective_project_root(settings.project_root, project_root)
    if root_result.error_code:
        return error_response(
            "tapps_diff_impact",
            root_result.error_code,
            root_result.error_message or "",
        )
    root = root_result.root

    raw_paths = [p.strip() for p in file_paths.split(",") if p.strip()]
    if not raw_paths:
        return error_response(
            "tapps_diff_impact",
            "missing_file_paths",
            "file_paths is required (comma-separated)",
        )

    resolved: list[_Path] = []
    for fp in raw_paths:
        try:
            if project_root:
                resolved.append(validate_read_path_under_root(fp, root))
            else:
                resolved.append(_validate_file_path_lazy(fp))
        except (ValueError, FileNotFoundError) as exc:
            return error_response("tapps_diff_impact", "path_denied", str(exc))

    if force_rebuild:
        from tapps_mcp.project.call_graph import build_call_graph_index

        build_call_graph_index(root, force_rebuild=True)

    from tapps_mcp.project.diff_impact import analyze_diff_impact

    data = analyze_diff_impact(resolved, root)
    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution(
        "tapps_diff_impact",
        start,
        file_path=",".join(str(p) for p in resolved),
        degraded=bool(data.get("degraded")),
    )
    resp = success_response("tapps_diff_impact", elapsed_ms, data)
    return _with_nudges("tapps_diff_impact", resp)


# ---------------------------------------------------------------------------
# Report progress sidecar (Story 40.1)
# ---------------------------------------------------------------------------

_REPORT_PROGRESS_FILE = ".tapps-mcp/.report-progress.json"


@dataclasses.dataclass
class _ReportProgressTracker:
    """Shared progress state for tapps_report sidecar file."""

    total: int = 0
    completed: int = 0
    last_file: str = ""
    _sidecar_path: _Path | None = dataclasses.field(default=None, repr=False)
    _results: list[dict[str, Any]] = dataclasses.field(default_factory=list, repr=False)
    _started_at: str = dataclasses.field(default="", repr=False)

    def init_sidecar(self, project_root: _Path) -> None:
        sidecar_dir = project_root / ".tapps-mcp"
        try:
            sidecar_dir.mkdir(parents=True, exist_ok=True)
            self._sidecar_path = sidecar_dir / ".report-progress.json"
            self._started_at = datetime.now(tz=UTC).isoformat()
            self._write_sidecar({})
        except Exception:
            self._sidecar_path = None

    def record_file_result(self, file_path: str, result: dict[str, Any]) -> None:
        self._results.append(
            {
                "file": file_path,
                "score": result.get("overall_score", 0),
            }
        )
        self._write_sidecar({})

    def finalize(self, summary: str, elapsed_ms: int) -> None:
        self._write_sidecar(
            {
                "status": "completed",
                "summary": summary,
                "elapsed_ms": elapsed_ms,
            }
        )

    def finalize_error(self, error: str) -> None:
        self._write_sidecar({"status": "error", "error": error})

    def _write_sidecar(self, extra: dict[str, Any]) -> None:
        if self._sidecar_path is None:
            return
        data: dict[str, Any] = {
            "status": extra.get("status", "running"),
            "total": self.total,
            "completed": self.completed,
            "last_file": self.last_file,
            "started_at": self._started_at,
            "results": list(self._results),
        }
        data.update(extra)
        try:
            self._sidecar_path.write_text(_json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# tapps_report
# ---------------------------------------------------------------------------


async def tapps_report(
    file_path: str = "",
    report_format: str = "json",
    max_files: int = 20,
    project_root: str = "",
    scope: str = "",
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Generates a quality report (single-file or project-wide), combining
    scoring + gate verdict + per-category breakdown into JSON, Markdown,
    or HTML output.

    Call this when you need a portable artifact — to attach to a PR,
    paste into a Linear comment, or render for a non-LLM reader. For
    in-flight per-edit checks use ``tapps_quick_check`` instead; for the
    batch validation use ``tapps_validate_changed``. Project-wide
    reports score up to ``max_files`` files; raise the cap only when
    you actually need exhaustive coverage.

    Args:
        file_path: Single source-file path. Empty (default) generates a
            project-wide report ranking the top ``max_files`` files by
            score.
        report_format: ``"json"`` (default, machine-readable),
            ``"markdown"`` (PR-comment friendly), or ``"html"``
            (standalone web view with charts).
        max_files: Maximum files to include in a project-wide report
            (default ``20``). Capped at 100 to prevent runaway scans
            on monorepos.
        project_root: Override the project root. Empty (default) uses
            the server-configured root. Set when reporting on a sibling
            repo from a long-lived MCP host.
        scope: Subdirectory under ``project_root`` for project-wide
            reports. Empty (default) scans the whole root.
        ctx: MCP context handle for progress notifications during
            long project-wide scans. Injected by the host.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_report")

    from tapps_mcp.gates.evaluator import evaluate_gate
    from tapps_mcp.project.report import generate_report
    from tapps_mcp.server_helpers import _get_scorer

    settings = load_settings()
    root_result = resolve_effective_project_root(settings.project_root, project_root)
    if root_result.error_code:
        return error_response(
            "tapps_report",
            root_result.error_code,
            root_result.error_message or "",
        )
    root = root_result.root
    cross_repo = bool(project_root.strip())

    scorer = _get_scorer()
    score_results: list[Any] = []
    gate_results: list[Any] = []
    skipped_files: list[dict[str, str]] = []

    if file_path:
        try:
            if cross_repo:
                resolved = validate_read_path_under_root(file_path, root)
            else:
                resolved = _validate_file_path_lazy(file_path)
        except (ValueError, FileNotFoundError) as exc:
            return error_response("tapps_report", "path_denied", str(exc))
        try:
            result = await scorer.score_file(resolved)
        except Exception as exc:  # surface cause, never an empty message
            return error_response(
                "tapps_report",
                "scan_failed",
                f"Failed to score {resolved.name}: {type(exc).__name__}: {exc}",
            )
        score_results.append(result)
        gate_results.append(evaluate_gate(result, preset=settings.quality_preset))
    else:
        from tapps_core.common.utils import should_skip_path

        try:
            scan_root = resolve_path_under_root(scope, root) if scope.strip() else root
        except ValueError as exc:
            return error_response("tapps_report", "path_denied", str(exc))

        # should_skip_path excludes .venv*, node_modules, dist,
        # build, __pycache__, and other generated directories.
        py_files = sorted(scan_root.rglob("*.py"))
        py_files = [f for f in py_files if not should_skip_path(f)][: max(1, max_files)]

        tracker = _ReportProgressTracker(total=len(py_files))
        tracker.init_sidecar(root)

        # Bound concurrent scorers (see _REPORT_MAX_CONCURRENCY) so a project-wide
        # scan does not fork hundreds of subprocesses at once.
        sem = asyncio.Semaphore(_REPORT_MAX_CONCURRENCY)

        async def _score_one(pf: _Path) -> tuple[Any, Any] | None:
            async with sem:
                try:
                    res = await scorer.score_file(pf)
                except Exception as e:  # one bad file must not abort the report
                    logger.warning("report_file_skip", file=str(pf), error=str(e))
                    skipped_files.append({"file": str(pf), "error": f"{type(e).__name__}: {e}"})
                    return None
                gate = evaluate_gate(res, preset=settings.quality_preset)
                tracker.completed += 1
                tracker.last_file = pf.name
                score_val = getattr(res, "overall_score", 0)
                tracker.record_file_result(str(pf), {"overall_score": score_val})
                await emit_ctx_info(ctx, f"Scored {pf.name}: {score_val}/100")
                return res, gate

        # Heartbeat task for project-wide progress reporting
        _stop_event = asyncio.Event()
        _heartbeat_task: asyncio.Task[None] | None = None
        report_fn = getattr(ctx, "report_progress", None) if ctx else None
        if callable(report_fn):

            async def _report_heartbeat() -> None:
                while not _stop_event.is_set():
                    with contextlib.suppress(Exception):
                        await report_fn(
                            progress=tracker.completed,
                            total=tracker.total,
                            message=f"Scored {tracker.completed}/{tracker.total} files ({tracker.last_file or 'starting...'})",
                        )
                    # wait_for raises TimeoutError every 5s while the scan is
                    # still running — that is the expected wake-up, not a failure.
                    # Suppress it (and CancelledError) so the heartbeat task never
                    # dies with an exception that the finally below would re-raise
                    # as an empty-message error.
                    with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                        await asyncio.wait_for(
                            _stop_event.wait(), timeout=_REPORT_HEARTBEAT_INTERVAL_S
                        )

            _heartbeat_task = asyncio.create_task(_report_heartbeat())

        try:
            tasks = [_score_one(pf) for pf in py_files]
            # return_exceptions=True: a stray BaseException from one file (e.g.
            # a per-file cancellation) is recorded, not allowed to abort the run.
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)
            for pf, out in zip(py_files, outcomes, strict=True):
                if isinstance(out, BaseException):
                    logger.warning("report_file_skip", file=str(pf), error=str(out))
                    skipped_files.append({"file": str(pf), "error": f"{type(out).__name__}: {out}"})
                    continue
                if out is not None:
                    score_results.append(out[0])
                    gate_results.append(out[1])

            elapsed_ms_inner = (time.perf_counter_ns() - start) // 1_000_000
            tracker.finalize(f"{len(score_results)} files scored", elapsed_ms_inner)
        except Exception as exc:  # return the real cause, never an empty message
            tracker.finalize_error(f"{type(exc).__name__}: {exc}")
            return error_response(
                "tapps_report",
                "scan_failed",
                f"{type(exc).__name__}: {exc} (last file: {tracker.last_file or 'n/a'})",
                extra={"skipped_files": skipped_files},
            )
        finally:
            _stop_event.set()
            if _heartbeat_task is not None:
                _heartbeat_task.cancel()
                # gather(return_exceptions=True) drains the task without
                # re-raising whatever it stored (CancelledError or otherwise).
                await asyncio.gather(_heartbeat_task, return_exceptions=True)

    try:
        report_data = generate_report(score_results, gate_results, report_format=report_format)
    except Exception as exc:  # return the real cause, never an empty message
        return error_response(
            "tapps_report",
            "scan_failed",
            f"Report rendering failed: {type(exc).__name__}: {exc}",
            extra={"skipped_files": skipped_files},
        )
    if skipped_files:
        report_data["skipped_files"] = skipped_files
    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_report", start, file_path=file_path or None)
    resp = success_response("tapps_report", elapsed_ms, report_data)
    return _with_nudges("tapps_report", resp)


# ---------------------------------------------------------------------------
# tapps_dead_code
# ---------------------------------------------------------------------------


async def tapps_dead_code(
    file_path: str = "",
    min_confidence: int = 80,
    scope: str = "file",
    project_root: str = "",
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Reports unused Python code (functions, classes, imports, variables)
    via vulture, with per-finding confidence and line numbers.

    GA tool (TAP-4527). Accuracy caveat: vulture works from static
    references only, so in repos with heavy dynamic dispatch (``getattr``,
    plugin entry points, CLI registries, reflective calls) a symbol whose
    only callers are dynamic can be reported as unused when it is not — a
    false "unused" positive. Cross-check high ``in_repo_gap_rate`` repos
    (where the call graph cannot resolve many in-repo callers) and treat
    those dead-code results as advisory. Call this during cleanup passes
    (after a refactor, before a release) or as part of an audit campaign.
    Skip for routine per-edit checks (use ``tapps_quick_check``) — vulture
    is slower. Use the ``min_confidence`` knob to filter the noise floor.

    Args:
        file_path: Path to a single Python file. Required when
            ``scope="file"``; ignored otherwise.
        min_confidence: Vulture confidence threshold (0-100). Default
            ``80`` filters most false positives; drop to ``60`` for
            deeper sweeps, raise to ``95`` for high-precision results.
        scope: ``"file"`` (single file specified by ``file_path``),
            ``"project"`` (all ``.py`` files under the project root),
            or ``"changed"`` (git-changed ``.py`` files only — fastest
            way to spot dead code introduced by the current task).
        project_root: Override the project root. Empty (default) uses
            the server-configured root.
        ctx: MCP context handle for progress notifications during
            project-wide scans. Injected by the host.
    """
    from tapps_mcp.tools.vulture import (
        clamp_confidence,
        collect_changed_python_files,
        collect_python_files,
        is_vulture_available,
        run_vulture_async,
        run_vulture_multi_async,
    )

    start = time.perf_counter_ns()
    _record_call("tapps_dead_code")
    # TAP-2022: fire-and-forget call-count event via brain so usage is measurable.
    try:
        _dc_bridge = _get_brain_bridge()
        if _dc_bridge is not None and hasattr(_dc_bridge, "record_event"):

            async def _fire_dead_code_event() -> None:
                try:
                    await _dc_bridge.record_event("tool_call", "tapps_dead_code")  # type: ignore[union-attr]
                except Exception:
                    pass

            asyncio.create_task(_fire_dead_code_event())  # noqa: RUF006
    except Exception:
        pass  # never block tapps_dead_code for telemetry
    await ensure_session_initialized()

    min_confidence = clamp_confidence(min_confidence)

    valid_scopes = {"file", "project", "changed"}
    if scope not in valid_scopes:
        return error_response(
            "tapps_dead_code",
            "invalid_scope",
            f"Invalid scope '{scope}'. Must be one of: {', '.join(sorted(valid_scopes))}",
        )

    settings = load_settings()
    root_result = resolve_effective_project_root(settings.project_root, project_root)
    if root_result.error_code:
        return error_response(
            "tapps_dead_code",
            root_result.error_code,
            root_result.error_message or "",
        )
    root = root_result.root
    cross_repo = bool(project_root.strip())

    if scope == "file":
        if not file_path:
            return error_response(
                "tapps_dead_code",
                "missing_file_path",
                "file_path is required when scope='file'",
            )
        try:
            if cross_repo:
                resolved = validate_read_path_under_root(file_path, root)
            else:
                resolved = _validate_file_path_lazy(file_path)
        except (ValueError, FileNotFoundError) as exc:
            return error_response("tapps_dead_code", "path_denied", str(exc))

        degraded = not is_vulture_available()
        findings = await run_vulture_async(
            str(resolved),
            min_confidence=min_confidence,
            whitelist_patterns=settings.dead_code_whitelist_patterns,
            cwd=str(resolved.parent),
        )
        if findings is None:
            degraded = True
            findings = []
        files_scanned = 1
        display_path = str(resolved)
    else:
        scan_root = root
        if scope == "project":
            file_list = collect_python_files(scan_root)
        else:
            file_list = collect_changed_python_files(scan_root)

        await emit_ctx_info(ctx, f"Scanning {len(file_list)} files for dead code...")

        if not file_list:
            elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
            _record_execution("tapps_dead_code", start)
            resp = success_response(
                "tapps_dead_code",
                elapsed_ms,
                {
                    "file_path": "",
                    "scope": scope,
                    "total_findings": 0,
                    "files_scanned": 0,
                    "degraded": not is_vulture_available(),
                    "min_confidence": min_confidence,
                    "by_type": {},
                    "type_counts": {},
                    "summary": f"No Python files found for scope '{scope}'",
                },
            )
            return _with_nudges("tapps_dead_code", resp)

        result = await run_vulture_multi_async(
            file_list,
            min_confidence=min_confidence,
            whitelist_patterns=settings.dead_code_whitelist_patterns,
            cwd=str(scan_root),
            timeout=120,
        )
        findings = result.findings
        files_scanned = result.files_scanned
        degraded = result.degraded
        display_path = str(scan_root)

    # Group by type
    by_type: dict[str, list[dict[str, Any]]] = {}
    for f in findings:
        entry: dict[str, Any] = {
            "name": f.name,
            "line": f.line,
            "confidence": f.confidence,
            "message": f.message,
        }
        if scope != "file":
            entry["file_path"] = f.file_path
        by_type.setdefault(f.finding_type, []).append(entry)

    if scope != "file":
        await emit_ctx_info(
            ctx, f"Dead code scan complete: {len(findings)} items in {files_scanned} file(s)"
        )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_dead_code", start, file_path=display_path)

    type_counts = {k: len(v) for k, v in by_type.items()}
    summary = f"Found {len(findings)} dead code items in {files_scanned} file(s)"
    if type_counts:
        parts = [f"{count} {typ}" for typ, count in sorted(type_counts.items())]
        summary += f" ({', '.join(parts)})"

    resp = success_response(
        "tapps_dead_code",
        elapsed_ms,
        {
            "file_path": display_path,
            "scope": scope,
            "total_findings": len(findings),
            "files_scanned": files_scanned,
            "degraded": degraded,
            "min_confidence": min_confidence,
            "by_type": by_type,
            "type_counts": type_counts,
            "summary": summary,
        },
    )
    return _with_nudges("tapps_dead_code", resp)


# ---------------------------------------------------------------------------
# tapps_dependency_scan
# ---------------------------------------------------------------------------


async def tapps_dependency_scan(
    project_root: str = "",
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Scans project dependencies for known CVEs via pip-audit and returns
    findings sorted by severity (critical/high/medium/low) with fixed-in
    versions where available.

    Call this before any release, after upgrading any dependency, and
    on a routine cadence during long-running maintenance windows.
    pip-audit hits the PyPI advisory database, so this needs network
    access. For dependency *structure* (circular imports, coupling) use
    ``tapps_dependency_graph`` instead — different concern.

    Args:
        project_root: Override the project root. Default empty (use
            server-configured root). Set when scanning a sibling repo.
        ctx: MCP context handle for progress notifications during long
            scans (large dep trees can take 30+ seconds). Injected by
            the host.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_dependency_scan")
    await ensure_session_initialized()

    settings = load_settings()

    if not settings.dependency_scan_enabled:
        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        _record_execution("tapps_dependency_scan", start)
        resp = success_response(
            "tapps_dependency_scan",
            elapsed_ms,
            {
                "scanned_packages": 0,
                "vulnerable_packages": 0,
                "total_findings": 0,
                "scan_source": "disabled",
                "by_severity": {},
                "severity_counts": {},
                "summary": "Dependency scanning is disabled (dependency_scan_enabled=False).",
            },
        )
        return _with_nudges("tapps_dependency_scan", resp)

    from tapps_mcp.tools.pip_audit import run_pip_audit_async

    root = project_root if project_root else str(settings.project_root)

    # Heartbeat task for dependency scan progress
    _stop_event = asyncio.Event()
    _heartbeat_task: asyncio.Task[None] | None = None
    report_fn = getattr(ctx, "report_progress", None) if ctx else None
    if callable(report_fn):
        _scan_start = time.monotonic()

        async def _scan_heartbeat() -> None:
            while not _stop_event.is_set():
                elapsed = int(time.monotonic() - _scan_start)
                with contextlib.suppress(Exception):
                    await report_fn(
                        progress=elapsed,
                        total=0,
                        message=f"Scanning dependencies... ({elapsed}s elapsed)",
                    )
                # TimeoutError is the expected per-interval wake-up; suppress it
                # (and CancelledError) so the heartbeat task never dies with an
                # exception the finally below would re-raise as an empty error.
                with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                    await asyncio.wait_for(_stop_event.wait(), timeout=_REPORT_HEARTBEAT_INTERVAL_S)

        _heartbeat_task = asyncio.create_task(_scan_heartbeat())

    try:
        result = await run_pip_audit_async(
            project_root=root,
            source=settings.dependency_scan_source,
            severity_threshold=settings.dependency_scan_severity_threshold,
            ignore_ids=settings.dependency_scan_ignore_ids or None,
        )
    finally:
        _stop_event.set()
        if _heartbeat_task is not None:
            _heartbeat_task.cancel()
            await asyncio.gather(_heartbeat_task, return_exceptions=True)

    # Populate session cache so scorer.py applies dependency penalties
    if not result.error:
        from tapps_mcp.tools.dependency_scan_cache import set_dependency_findings

        set_dependency_findings(root, result.findings)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_dependency_scan", start)

    # Group by severity
    by_severity: dict[str, list[dict[str, str]]] = {}
    for f in result.findings:
        by_severity.setdefault(f.severity, []).append(
            {
                "package": f.package,
                "installed_version": f.installed_version,
                "fixed_version": f.fixed_version,
                "vulnerability_id": f.vulnerability_id,
                "description": f.description[:200] if f.description else "",
            }
        )

    sev_counts = {k: len(v) for k, v in by_severity.items()}
    summary = f"Scanned {result.scanned_packages} packages: {len(result.findings)} vulnerabilities"
    if sev_counts:
        parts = [f"{count} {sev}" for sev, count in sorted(sev_counts.items())]
        summary += f" ({', '.join(parts)})"

    await emit_ctx_info(
        ctx,
        f"Scan complete: {len(result.findings)} vulnerabilities in {result.scanned_packages} packages",
    )

    data: dict[str, Any] = {
        "scanned_packages": result.scanned_packages,
        "vulnerable_packages": result.vulnerable_packages,
        "total_findings": len(result.findings),
        "scan_source": result.scan_source,
        "by_severity": by_severity,
        "severity_counts": sev_counts,
        "summary": summary,
    }
    if result.error:
        data["error"] = result.error

    resp = success_response("tapps_dependency_scan", elapsed_ms, data)
    return _with_nudges("tapps_dependency_scan", resp)


# ---------------------------------------------------------------------------
# tapps_dependency_graph
# ---------------------------------------------------------------------------


async def tapps_dependency_graph(
    project_root: str = "",
    detect_cycles: bool = True,
    include_coupling: bool = True,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Builds an import graph for the project and reports circular
    imports plus per-module coupling metrics (afferent / efferent /
    instability per Martin's metrics).

    Call this when triaging an ``ImportError`` at startup, when planning
    a large refactor that splits a package, or when adding a new layer
    to verify the dependency direction is one-way. Skip for routine
    per-edit checks. For CVE scanning use ``tapps_dependency_scan``
    instead — that's about package vulnerabilities, this is about
    internal import structure.

    Args:
        project_root: Override the project root. Default empty (use
            server-configured root).
        detect_cycles: Run circular-import detection. Default ``True``.
            Disable for pure coupling-metric reports on known-acyclic
            codebases.
        include_coupling: Calculate per-module fan-in / fan-out and
            instability. Default ``True``. Disable for the fast
            cycle-only check.
        ctx: MCP context handle for progress notifications. Injected
            by the host.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_dependency_graph")
    await ensure_session_initialized()

    settings = load_settings()
    root = settings.project_root
    if project_root:
        from pathlib import Path

        root = Path(project_root).resolve()

    def _build_graph_sync() -> dict[str, Any]:
        """Run graph building, cycle detection, and coupling analysis synchronously."""
        from tapps_mcp.project.import_graph import build_import_graph

        graph = build_import_graph(root)
        result: dict[str, Any] = {
            "project_root": str(root),
            "total_modules": len(graph.modules),
            "total_edges": len(graph.edges),
        }

        if detect_cycles:
            from tapps_mcp.project.cycle_detector import (
                detect_cycles as _detect,
            )
            from tapps_mcp.project.cycle_detector import (
                suggest_cycle_fixes,
            )

            analysis = _detect(graph)
            result["cycles"] = {
                "total": len(analysis.cycles),
                "runtime_cycles": analysis.runtime_cycles,
                "type_checking_cycles": analysis.type_checking_cycles,
                "details": [
                    {
                        "modules": c.modules,
                        "length": c.length,
                        "severity": c.severity,
                        "description": c.description,
                    }
                    for c in analysis.cycles[:10]
                ],
            }
            result["cycle_suggestions"] = suggest_cycle_fixes(analysis.cycles[:5])

        if include_coupling:
            from tapps_mcp.project.coupling_metrics import (
                calculate_coupling,
                suggest_coupling_fixes,
            )

            couplings = calculate_coupling(graph)
            hubs = [c for c in couplings if c.is_hub]
            result["coupling"] = {
                "total_modules_analysed": len(couplings),
                "hub_count": len(hubs),
                "top_coupled": [
                    {
                        "module": c.module,
                        "afferent": c.afferent,
                        "efferent": c.efferent,
                        "instability": round(c.instability, 3),
                        "is_hub": c.is_hub,
                    }
                    for c in couplings[:10]
                ],
            }
            result["coupling_suggestions"] = suggest_coupling_fixes(couplings[:5])

        # Attach external imports for cross-tool integration
        result["_external_imports"] = {
            pkg: list(mods) for pkg, mods in graph.external_imports.items()
        }
        return result

    await emit_ctx_info(ctx, "Building import graph...")
    data = await asyncio.to_thread(_build_graph_sync)

    if detect_cycles:
        await emit_ctx_info(
            ctx,
            f"Cycle detection complete: {data.get('cycles', {}).get('total', 0)} cycles found",
        )
    if include_coupling:
        await emit_ctx_info(
            ctx,
            f"Coupling analysis complete: {data.get('coupling', {}).get('hub_count', 0)} hubs found",
        )
    total_modules = data.get("total_modules", 0)
    await emit_ctx_info(ctx, f"Analysis complete: {total_modules} modules analyzed")

    # Cross-reference with cached vulnerability findings when available
    external_imports = data.pop("_external_imports", {})
    if external_imports:
        from tapps_mcp.tools.dependency_scan_cache import get_dependency_findings

        dep_findings = get_dependency_findings(str(root))
        if dep_findings:
            from tapps_mcp.project.vulnerability_impact import analyze_vulnerability_impact

            impact = analyze_vulnerability_impact(dep_findings, external_imports)
            if impact.impacts:
                data["vulnerability_impact"] = {
                    "total_vulnerable_imports": impact.total_vulnerable_imports,
                    "most_exposed_modules": impact.most_exposed_modules[:10],
                    "impacts": [
                        {
                            "package": vi.package,
                            "vulnerability_id": vi.vulnerability_id,
                            "severity": vi.severity,
                            "importing_modules": vi.importing_modules[:10],
                            "import_count": vi.import_count,
                        }
                        for vi in impact.impacts[:10]
                    ],
                }

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_dependency_graph", start)

    resp = success_response("tapps_dependency_graph", elapsed_ms, data)
    return _with_nudges("tapps_dependency_graph", resp)


# ---------------------------------------------------------------------------
# tapps_audit_campaign (mode=plan)
# ---------------------------------------------------------------------------


async def tapps_audit_campaign(
    scope: str = "",
    categories: str = "quality,security,dead_code",
    chunk_size: int = 6,
    graph_root: str = "",
    project_root: str = "",
    campaign_id: str = "",
    mode: str = "plan",
    epic_ref: str = "",
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Plans, finalizes, or converts an audit campaign to a fix plan.

    Call ``mode="plan"`` when scoping a "review every file in directory
    X" effort — the response is a campaign spec ready for the
    ``linear-issue`` skill to file as an epic + N session stories. Call
    ``mode="dispatch"`` after the epic is filed to substitute the real
    Linear epic id into every session body before filing the children.
    Call ``mode="fix_plan"`` after a campaign has been planned to generate
    a companion fix epic + child fix stories (one per audit session cluster)
    that autonomous agents can implement. Fix stories carry ``agent_ready=True`` by
    construction and are tracked under ``fix.campaign.<id>`` in brain,
    distinct from the audit spec at ``audit.campaign.<id>``.

    Use ``categories`` to focus the audit; ``"quality,security,
    dead_code"`` is the default well-balanced bundle.

    Args:
        scope: Directory to audit. Plan-mode default is the project
            root. Use ``packages/tapps-mcp/src`` to scope to one
            package in a monorepo.
        categories: Comma-separated audit categories. Subset of
            ``{"quality", "security", "dead_code", "docs"}``.
            Default ``"quality,security,dead_code"``.
        chunk_size: Soft target for files per session story. Default
            ``6``. Raise to ``10-12`` for shallow audits, drop to
            ``3-4`` for deep ones.
        graph_root: Source root used to build the import graph for
            cohesive chunking. Empty (default) = ``project_root``.
            **Set this for monorepos** (e.g.
            ``"packages/tapps-mcp/src"``) so module names resolve and
            inter-file edges land in chunks — workaround for TAP-2035.
        project_root: Override the project root. Empty (default) uses
            the server-configured root.
        campaign_id: Explicit campaign id. **Required for**
            ``mode="dispatch"`` and ``mode="fix_plan"``. Empty in plan
            mode auto-generates an id from scope + date + SHA.
        mode: ``"plan"`` (default), ``"dispatch"``, or ``"fix_plan"``.
        epic_ref: Linear identifier of the filed campaign epic (e.g.
            ``"TAP-2050"``). **Required for** ``mode="dispatch"``;
            ignored in other modes.
        ctx: MCP context handle for progress notifications. Injected
            by the host.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_audit_campaign")
    await ensure_session_initialized()

    if mode not in {"plan", "dispatch", "fix_plan"}:
        return error_response(
            "tapps_audit_campaign",
            "invalid_mode",
            f"mode must be 'plan', 'dispatch', or 'fix_plan', got: {mode!r}",
        )

    if mode == "dispatch":
        return await _handle_dispatch_mode(
            start=start,
            campaign_id=campaign_id,
            epic_ref=epic_ref,
            ctx=ctx,
        )

    if mode == "fix_plan":
        return await _handle_fix_plan_mode(
            start=start,
            campaign_id=campaign_id,
            ctx=ctx,
        )

    from tapps_mcp.tools.audit_campaign import build_campaign_spec

    settings = load_settings()
    root_result = resolve_effective_project_root(settings.project_root, project_root)
    if root_result.error_code:
        return error_response(
            "tapps_audit_campaign",
            root_result.error_code,
            root_result.error_message or "",
        )
    root = root_result.root

    try:
        scope_path = resolve_path_under_root(scope, root) if scope else root
    except ValueError as exc:
        return error_response("tapps_audit_campaign", "path_denied", str(exc))

    if not scope_path.is_dir():
        return error_response(
            "tapps_audit_campaign",
            "invalid_scope",
            f"scope is not an existing directory: {scope_path}",
        )

    graph_root_path: _Path | None = None
    if graph_root:
        try:
            graph_root_path = resolve_path_under_root(graph_root, root)
        except ValueError as exc:
            return error_response("tapps_audit_campaign", "path_denied", str(exc))
        if not graph_root_path.is_dir():
            return error_response(
                "tapps_audit_campaign",
                "invalid_graph_root",
                f"graph_root is not an existing directory: {graph_root_path}",
            )

    cats = [c.strip() for c in categories.split(",") if c.strip()]
    commit_sha = await _resolve_git_short_sha(root)

    try:
        spec = build_campaign_spec(
            root,
            scope_path,
            graph_root=graph_root_path,
            commit_sha=commit_sha,
            categories=cats,
            chunk_size=chunk_size,
            campaign_id=campaign_id,
        )
    except ValueError as exc:
        return error_response("tapps_audit_campaign", "invalid_categories", str(exc))

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_audit_campaign", start)

    data: dict[str, Any] = {
        "campaign_id": spec.campaign_id,
        "project_root": spec.project_root,
        "scope": spec.scope,
        "graph_root": spec.graph_root,
        "commit_sha": spec.commit_sha,
        "categories": spec.categories,
        "total_files": spec.total_files,
        "total_chunks": spec.total_chunks,
        "skipped_trivial": spec.skipped_trivial,
        "epic": {"title": spec.epic.title, "body": spec.epic.body},
        "sessions": [
            {
                "session_index": s.session_index,
                "title": s.title,
                "body": s.body,
                "files": s.files,
                "modules": s.modules,
                "intra_edges": s.intra_edges,
                "boundary_edges": s.boundary_edges,
                "rationale": s.rationale,
                "labels": list(s.labels),
            }
            for s in spec.sessions
        ],
    }
    persisted = await _persist_campaign_spec(spec.campaign_id, data)
    data["persisted_to_brain"] = persisted
    await emit_ctx_info(
        ctx,
        f"Planned campaign {spec.campaign_id}: "
        f"{spec.total_chunks} sessions across {spec.total_files} files "
        f"(persisted={persisted})",
    )

    resp = success_response("tapps_audit_campaign", elapsed_ms, data)
    return _with_nudges("tapps_audit_campaign", resp)


async def _persist_campaign_spec(campaign_id: str, spec_dict: dict[str, Any]) -> bool:
    """Save the rendered spec to brain so dispatch can pick it up."""
    from tapps_mcp.tools.audit_manifest import save_campaign_spec

    try:
        return await save_campaign_spec(campaign_id, spec_dict)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.debug("audit_campaign_persist_failed", error=str(exc))
        return False


async def _handle_dispatch_mode(
    *,
    start: int,
    campaign_id: str,
    epic_ref: str,
    ctx: Context[Any, Any, Any] | None,
) -> dict[str, Any]:
    """Load a planned campaign, substitute epic_ref, return the finalized spec."""
    from tapps_mcp.tools.audit_campaign import finalize_session_bodies
    from tapps_mcp.tools.audit_manifest import (
        load_campaign_spec,
        save_campaign_spec,
    )

    if not campaign_id:
        return error_response(
            "tapps_audit_campaign",
            "missing_campaign_id",
            "mode='dispatch' requires campaign_id from a prior plan run",
        )
    if not epic_ref:
        return error_response(
            "tapps_audit_campaign",
            "missing_epic_ref",
            "mode='dispatch' requires epic_ref (e.g. 'TAP-2050')",
        )

    spec = await load_campaign_spec(campaign_id)
    if spec is None:
        return error_response(
            "tapps_audit_campaign",
            "campaign_not_found",
            f"no campaign spec found in brain for campaign_id={campaign_id!r}. "
            "Run mode='plan' first.",
        )

    try:
        finalized = finalize_session_bodies(spec, epic_ref)
    except ValueError as exc:
        return error_response("tapps_audit_campaign", "invalid_epic_ref", str(exc))

    re_persisted = await save_campaign_spec(campaign_id, finalized)
    finalized["persisted_to_brain"] = re_persisted

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_audit_campaign", start)
    await emit_ctx_info(
        ctx,
        f"Dispatched campaign {campaign_id} with epic_ref={epic_ref} "
        f"({len(finalized.get('sessions') or [])} sessions ready to file)",
    )
    resp = success_response("tapps_audit_campaign", elapsed_ms, finalized)
    return _with_nudges("tapps_audit_campaign", resp)


async def _handle_fix_plan_mode(
    *,
    start: int,
    campaign_id: str,
    ctx: Context[Any, Any, Any] | None,
) -> dict[str, Any]:
    """Load a planned campaign spec and emit an implementable fix epic + stories.

    Each session cluster in the persisted spec becomes one fix story via
    :func:`~tapps_mcp.tools.audit_campaign.build_fix_plan_spec`. Stories
    are guaranteed ``agent_ready=True`` by construction (no iterative
    validator loop required). The fix plan is persisted under the distinct
    brain key ``fix.campaign.<campaign_id>`` so audit and fix coverage
    remain independently trackable (TAP-2718).
    """
    from tapps_mcp.tools.audit_campaign import build_fix_plan_spec
    from tapps_mcp.tools.audit_manifest import load_campaign_spec

    if not campaign_id:
        return error_response(
            "tapps_audit_campaign",
            "missing_campaign_id",
            "mode='fix_plan' requires campaign_id from a prior plan run",
        )

    spec = await load_campaign_spec(campaign_id)
    if spec is None:
        return error_response(
            "tapps_audit_campaign",
            "campaign_not_found",
            f"no campaign spec found in brain for campaign_id={campaign_id!r}. "
            "Run mode='plan' first.",
        )

    try:
        fix_plan = build_fix_plan_spec(spec)
    except ValueError as exc:
        return error_response("tapps_audit_campaign", "invalid_campaign_spec", str(exc))

    data: dict[str, Any] = {
        "campaign_id": fix_plan.campaign_id,
        "total_fix_stories": fix_plan.total_stories,
        "fix_epic": {
            "title": fix_plan.fix_epic_title,
            "body": fix_plan.fix_epic_body,
        },
        "fix_stories": [
            {
                "session_index": s.session_index,
                "title": s.title,
                "body": s.body,
                "files": s.files,
                "labels": list(s.labels),
                "agent_ready": s.agent_ready,
                "estimate": s.estimate,
                "priority": s.priority,
            }
            for s in fix_plan.fix_stories
        ],
    }
    persisted = await _persist_fix_plan_spec(fix_plan.campaign_id, data)
    data["persisted_to_brain"] = persisted

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_audit_campaign", start)
    await emit_ctx_info(
        ctx,
        f"Fix plan for campaign {campaign_id}: "
        f"{fix_plan.total_stories} fix stories generated "
        f"(persisted={persisted})",
    )
    resp = success_response(
        "tapps_audit_campaign",
        elapsed_ms,
        data,
        next_steps=[
            "Use the linear-issue skill to file fix_epic as a new epic "
            "(title=data['fix_epic']['title'], description=data['fix_epic']['body']).",
            "File each entry in data['fix_stories'] as a child story under the fix epic "
            "(labels=['audit-fix'], parent_id=<fix epic id>).",
            "Mark this campaign's audit epic as Done once all fix stories are filed.",
        ],
    )
    return _with_nudges("tapps_audit_campaign", resp)


async def _persist_fix_plan_spec(campaign_id: str, spec_dict: dict[str, Any]) -> bool:
    """Save the rendered fix-plan spec to brain under ``fix.campaign.<id>``."""
    from tapps_mcp.tools.audit_manifest import save_fix_plan_spec

    try:
        return await save_fix_plan_spec(campaign_id, spec_dict)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.debug("audit_campaign_persist_fix_plan_failed", error=str(exc))
        return False


async def _resolve_git_short_sha(root: Path) -> str:
    """Return ``git rev-parse --short HEAD`` from ``root``, or empty."""
    from tapps_mcp.tools.subprocess_runner import run_command_async

    try:
        result = await run_command_async(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root),
            timeout=5,
        )
    except (OSError, RuntimeError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# tapps_finding_to_story (TAP-2717)
# ---------------------------------------------------------------------------


async def tapps_finding_to_story(
    severity: str,
    category: str,
    files: list[str],
    evidence: str,
    recommendation: str,
    parent_id: str = "",
    avg_complexity: float = 0.0,
    snapshot_issues_json: str = "",
) -> dict[str, Any]:
    """Convert an audit finding into a Linear fix-story ready for ``save_issue``.

    Produces a 5-section story body that is guaranteed to pass
    ``docs_validate_linear_issue`` with ``agent_ready=true`` by
    construction — no iterative validation loop required.

    Section mapping:

    - ``## What``       ← ``recommendation``
    - ``## Where``      ← ``files`` (numbered list; bare paths get ``:1`` appended)
    - ``## Why``        ← ``evidence``
    - ``## Acceptance`` ← severity-derived checkboxes (always ≥1 ``- [ ]``)
    - ``## Refs``       ← ``severity`` + ``category`` + optional ``parent_id``

    Args:
        severity: ``"P0"`` | ``"P1"`` | ``"P2"`` | ``"P3"``.
        category: ``"security"`` | ``"correctness"`` | ``"performance"``
            | ``"style"`` | ``"docs"`` | ``"deadcode"``.
        files: File paths with optional line ranges, e.g.
            ``["src/module.py:10-25"]``.  Bare paths (no line ref) get
            ``:1`` appended automatically.
        evidence: One-line symptom description (usually a tool-output snippet).
        recommendation: One-line fix direction (informational, from the finding).
        parent_id: Optional Linear parent ticket id (e.g. ``"TAP-2040"``).
            Included in ``## Refs`` for traceability.
        avg_complexity: Average radon cyclomatic complexity of affected files
            (TAP-2720). Increases the story-point estimate when above 10 (+1)
            or 20 (+2). Default ``0.0`` (no bonus).
        snapshot_issues_json: JSON-encoded list of existing Linear issue dicts
            (TAP-2721 dedup). Each dict must carry at least ``"id"`` and
            ``"title"`` keys.  Pass the ``data.issues`` list from a prior
            ``tapps_linear_snapshot_get`` call (compact projection is fine).
            When non-empty, the generated title is compared against existing
            titles; if a match is found, ``data.should_file`` is ``false``
            and ``data.duplicate_of`` holds the existing issue id.  Default
            ``""`` (skip dedup — always file).

    Returns:
        Response envelope with ``data.title``, ``data.body``,
        ``data.severity``, ``data.category``, ``data.parent_id``,
        ``data.estimate``, ``data.priority``, ``data.section_count``,
        ``data.should_file``, ``data.duplicate_found``, and
        ``data.duplicate_of``.  The title is ≤80 chars; the body passes
        the docs-mcp agent-issue lint rules.
    """
    _record_call("tapps_finding_to_story")
    start_ns = time.perf_counter_ns()

    from tapps_mcp.tools.finding_to_story import (
        VALID_CATEGORIES,
        VALID_SEVERITIES,
        finding_to_story,
    )

    # --- Input validation ---
    severity_uc = severity.upper().strip()
    category_lc = category.lower().strip()

    if severity_uc not in VALID_SEVERITIES:
        return error_response(
            "tapps_finding_to_story",
            "invalid_severity",
            f"severity={severity!r} is not valid. Use one of: {sorted(VALID_SEVERITIES)}",
        )
    if category_lc not in VALID_CATEGORIES:
        return error_response(
            "tapps_finding_to_story",
            "invalid_category",
            f"category={category!r} is not valid. Use one of: {sorted(VALID_CATEGORIES)}",
        )
    if not files:
        return error_response(
            "tapps_finding_to_story",
            "missing_files",
            "`files` must contain at least one file path",
        )
    if not evidence.strip():
        return error_response(
            "tapps_finding_to_story",
            "missing_evidence",
            "`evidence` must be non-empty",
        )
    if not recommendation.strip():
        return error_response(
            "tapps_finding_to_story",
            "missing_recommendation",
            "`recommendation` must be non-empty",
        )

    story = finding_to_story(
        severity=severity_uc,
        category=category_lc,
        files=files,
        evidence=evidence,
        recommendation=recommendation,
        parent_id=parent_id,
        avg_complexity=avg_complexity,
    )

    # --- TAP-2721: Dedup against cached Linear snapshot ---
    import json as _json

    from tapps_mcp.tools.finding_to_story import find_duplicate_in_snapshot

    duplicate: dict[str, Any] | None = None
    if snapshot_issues_json.strip():
        try:
            snapshot_issues = _json.loads(snapshot_issues_json)
            if isinstance(snapshot_issues, list):
                duplicate = find_duplicate_in_snapshot(story.title, snapshot_issues)
        except (ValueError, TypeError):
            pass  # malformed JSON — skip dedup, proceed to file

    elapsed_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
    _record_execution("tapps_finding_to_story", start_ns)

    should_file = duplicate is None
    data: dict[str, Any] = {
        "title": story.title,
        "body": story.body,
        "severity": severity_uc,
        "category": category_lc,
        "parent_id": parent_id,
        "labels": list(story.labels),
        "estimate": story.estimate,
        "priority": story.priority,
        "section_count": story.body.count("\n## ") + 1,
        "should_file": should_file,
        "duplicate_found": not should_file,
        "duplicate_of": (
            (duplicate.get("identifier") or duplicate.get("id")) if duplicate else None
        ),
    }
    if should_file:
        next_steps = [
            "Call docs_validate_linear_issue(title, body) to confirm agent_ready=true.",
            "Then call save_issue(title, description=body, parent_id=parent_id, "
            "labels=data['labels']) — pass labels so the audit-fix tag lands on "
            "the Linear issue and agents can select it.",
        ]
    else:
        dup_id = (duplicate or {}).get("identifier") or (duplicate or {}).get("id")
        next_steps = [
            f"Issue {dup_id!r} already covers this finding — "
            "skip filing or link to it instead of creating a duplicate.",
            "Set data['should_file']=false in your filing logic to suppress the write.",
        ]
    return success_response(
        "tapps_finding_to_story",
        elapsed_ms,
        data,
        next_steps=next_steps,
    )


# ---------------------------------------------------------------------------
# tapps_audit_close_coverage (TAP-2798)
# ---------------------------------------------------------------------------


async def tapps_audit_close_coverage(
    rel_path: str,
    new_sha: str,
    fix_ticket: str = "",
    finding_ticket: str = "",
) -> dict[str, Any]:
    """Close an audit finding by updating its brain coverage record (TAP-2722).

    Wraps the internal ``close_coverage`` helper so the audit-fix loop can
    record a landed fix without importing tapps-mcp internals. Records *new_sha*
    as the entry's ``fix_sha`` and links the fix/finding tickets into the
    coverage → finding → fix chain. It deliberately leaves ``audited_sha``
    untouched: a fix is not an audit, so the post-fix file reads as *changed*
    and a subsequent ``tapps_audit_campaign`` re-audits it (re-audit-as-changed,
    per the audit-fix-loop handoff — see TAP-2799).

    Call this after committing a fix that resolves an audit finding, passing the
    new short SHA of the fixed file. The finding's coverage entry must already
    exist (created by a prior ``tapps_audit_campaign`` audit session).

    Args:
        rel_path: Repo-relative path of the fixed file (e.g.
            ``"packages/tapps-mcp/src/tapps_mcp/server.py"``).
        new_sha: The git SHA the fix landed at (recorded as ``fix_sha``).
        fix_ticket: Optional Linear id of the fix story (e.g. ``"TAP-2799"``).
            Appended to the entry's ``fix_tickets`` (deduped).
        finding_ticket: Optional Linear id of the original finding. Ensured
            present in the entry's ``finding_tickets``.

    Returns:
        Response envelope. ``data.ok`` is ``True`` when the coverage entry was
        updated. When the brain bridge is unavailable the envelope is
        ``degraded=True`` with ``data.ok=False`` and
        ``data.reason="bridge_unavailable"``; when no coverage entry exists for
        *rel_path* (or the write failed) ``data.ok=False`` and
        ``data.reason="coverage_entry_missing_or_write_failed"``.
    """
    _record_call("tapps_audit_close_coverage")
    start_ns = time.perf_counter_ns()

    from tapps_mcp.tools.audit_manifest import _get_bridge_or_none, close_coverage

    if not rel_path.strip():
        return error_response(
            "tapps_audit_close_coverage",
            "missing_rel_path",
            "`rel_path` must be a non-empty repo-relative file path",
        )
    if not new_sha.strip():
        return error_response(
            "tapps_audit_close_coverage",
            "missing_new_sha",
            "`new_sha` must be a non-empty git SHA",
        )

    # Detect the degraded-bridge path explicitly so we can return a structured
    # {ok:false, reason} envelope instead of an ambiguous bare False (TAP-2798).
    if _get_bridge_or_none() is None:
        elapsed_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
        _record_execution("tapps_audit_close_coverage", start_ns, degraded=True)
        return success_response(
            "tapps_audit_close_coverage",
            elapsed_ms,
            {
                "ok": False,
                "reason": "bridge_unavailable",
                "rel_path": rel_path,
                "new_sha": new_sha,
            },
            degraded=True,
            next_steps=[
                "Brain bridge unavailable — coverage was NOT updated. Re-run after "
                "tapps_session_start succeeds, or fix brain auth (TAPPS_BRAIN_AUTH_TOKEN).",
            ],
        )

    ok = await close_coverage(
        rel_path,
        new_sha,
        fix_ticket=fix_ticket,
        finding_ticket=finding_ticket,
    )
    elapsed_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
    _record_execution("tapps_audit_close_coverage", start_ns)

    data: dict[str, Any] = {
        "ok": ok,
        "reason": "" if ok else "coverage_entry_missing_or_write_failed",
        "rel_path": rel_path,
        "new_sha": new_sha,
        "fix_ticket": fix_ticket,
        "finding_ticket": finding_ticket,
    }
    if ok:
        next_steps = [
            "Coverage closed — fix recorded and tickets linked. The file now reads "
            "as changed, so re-run tapps_audit_campaign to re-audit it and confirm "
            "the finding no longer surfaces.",
        ]
    else:
        next_steps = [
            f"No coverage entry exists for {rel_path!r} (or the write failed). Audit "
            "the file via tapps_audit_campaign before closing its coverage.",
        ]
    return success_response(
        "tapps_audit_close_coverage",
        elapsed_ms,
        data,
        next_steps=next_steps,
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register analysis tools on the shared *mcp_instance* (Epic 79.1: conditional).

    TAP-1986: tapps_impact_analysis is the only eager daily-driver here.
    All other analysis tools carry defer_loading=True (combined with size hints where needed).
    """
    if "tapps_session_notes" in allowed_tools:
        register_tool(
            mcp_instance, tapps_session_notes, annotations=_ANNOTATIONS_READ_ONLY, meta=_META_DEFERRED
        )
    if "tapps_impact_analysis" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_impact_analysis,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta=_META_LARGE_OUTPUT_100K,
        )
    if "tapps_call_graph" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_call_graph,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta=_META_LARGE_OUTPUT_100K_D,
        )
    if "tapps_diff_impact" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_diff_impact,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta=_META_DEFERRED,
        )
    if "tapps_report" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_report,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta=_META_LARGE_OUTPUT_100K_D,
        )
    if "tapps_dead_code" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_dead_code,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta=_META_LARGE_OUTPUT_100K_D,
        )
    if "tapps_dependency_scan" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_dependency_scan,
            annotations=_ANNOTATIONS_READ_ONLY_OPEN,
            meta=_META_DEFERRED,
        )
    if "tapps_dependency_graph" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_dependency_graph,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta=_META_LARGE_OUTPUT_200K_D,
        )
    if "tapps_audit_campaign" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_audit_campaign,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta=_META_LARGE_OUTPUT_200K_D,
        )
    if "tapps_finding_to_story" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_finding_to_story,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta=_META_DEFERRED,
        )
    if "tapps_audit_close_coverage" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_audit_close_coverage,
            annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
            meta=_META_DEFERRED,
        )
