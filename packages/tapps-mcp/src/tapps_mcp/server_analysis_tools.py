"""Analysis and inspection tool handlers for TappsMCP.

Contains: tapps_report, tapps_dead_code, tapps_dependency_scan,
tapps_dependency_graph, tapps_session_notes, tapps_impact_analysis.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:`register`.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json as _json
import time
from datetime import datetime, timezone
from pathlib import Path as _Path
from typing import TYPE_CHECKING, Any

import structlog
from mcp.server.fastmcp import Context  # noqa: TC002 - MCP SDK needs runtime access
from mcp.types import ToolAnnotations

from tapps_core.config.settings import load_settings
from tapps_mcp.server_helpers import (
    emit_ctx_info,
    ensure_session_initialized,
    error_response,
    success_response,
)

if TYPE_CHECKING:
    from pathlib import Path

    from mcp.server.fastmcp import FastMCP

    from tapps_mcp.project.models import SessionNote
    from tapps_mcp.project.session_notes import SessionNoteStore

logger = structlog.get_logger(__name__)

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


def _promote_note_to_memory(note: SessionNote, tier: str = "context") -> dict[str, Any]:
    """Promote a session note to the memory store."""
    try:
        from tapps_mcp.server_helpers import _get_memory_store

        mem_store = _get_memory_store()
        entry = mem_store.save(
            key=note.key,
            value=note.value,
            tier=tier,
            source="agent",
            source_agent="session-promote",
            scope="session",
            tags=["promoted-from-session-notes"],
        )
        return {
            "action": "promote",
            "promoted": True,
            "memory_entry": entry.model_dump(),
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
    """Persist notes across the session to avoid losing context.

    Args:
        action: "save" | "get" | "list" | "clear" | "promote".
        key: Note key (required for save/get/promote).
        value: Note value (required for save). For promote, optional tier name.
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
            return error_response(
                "tapps_session_notes", "missing_params", "promote requires key"
            )
        found = store.get(key)
        if found is None:
            return error_response(
                "tapps_session_notes", "not_found", f"Note '{key}' not found"
            )
        data = _promote_note_to_memory(found, value or "context")
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
    file_path: str, change_type: str = "modified"
) -> dict[str, Any]:
    """REQUIRED before refactoring or deleting files. Maps the blast radius.

    Args:
        file_path: Path to the file being changed.
        change_type: "added" | "modified" | "removed".
    """
    start = time.perf_counter_ns()
    _record_call("tapps_impact_analysis")

    try:
        resolved = _validate_file_path_lazy(file_path)
    except (ValueError, FileNotFoundError) as exc:
        return error_response("tapps_impact_analysis", "path_denied", str(exc))

    from tapps_mcp.project.impact_analyzer import analyze_impact

    settings = load_settings()
    report = analyze_impact(resolved, settings.project_root, change_type)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_impact_analysis", start, file_path=str(resolved))

    resp = success_response(
        "tapps_impact_analysis",
        elapsed_ms,
        {
            "changed_file": report.changed_file,
            "change_type": report.change_type,
            "severity": report.severity,
            "total_affected": report.total_affected,
            "direct_dependents": [d.model_dump() for d in report.direct_dependents],
            "transitive_dependents": [d.model_dump() for d in report.transitive_dependents],
            "test_files": [t.model_dump() for t in report.test_files],
            "recommendations": report.recommendations,
        },
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
            recommendations=report.recommendations,
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        logger.debug("structured_output_failed: tapps_impact_analysis", exc_info=True)

    return _with_nudges("tapps_impact_analysis", resp)


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
            self._started_at = datetime.now(tz=timezone.utc).isoformat()
            self._write_sidecar({})
        except Exception:
            self._sidecar_path = None

    def record_file_result(self, file_path: str, result: dict[str, Any]) -> None:
        self._results.append({
            "file": file_path,
            "score": result.get("overall_score", 0),
        })
        self._write_sidecar({})

    def finalize(self, summary: str, elapsed_ms: int) -> None:
        self._write_sidecar({
            "status": "completed",
            "summary": summary,
            "elapsed_ms": elapsed_ms,
        })

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
            self._sidecar_path.write_text(
                _json.dumps(data, indent=2), encoding="utf-8"
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# tapps_report
# ---------------------------------------------------------------------------


async def tapps_report(
    file_path: str = "",
    report_format: str = "json",
    max_files: int = 20,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Generate a quality report combining scoring and gate results.

    Args:
        file_path: Path to a Python file (optional - project-wide if omitted).
        report_format: "json" | "markdown" | "html".
        max_files: Maximum files to score for project-wide report (default 20).
    """
    start = time.perf_counter_ns()
    _record_call("tapps_report")

    from tapps_mcp.gates.evaluator import evaluate_gate
    from tapps_mcp.project.report import generate_report
    from tapps_mcp.server_helpers import _get_scorer

    settings = load_settings()
    scorer = _get_scorer()
    score_results: list[Any] = []
    gate_results: list[Any] = []

    if file_path:
        try:
            resolved = _validate_file_path_lazy(file_path)
        except (ValueError, FileNotFoundError) as exc:
            return error_response("tapps_report", "path_denied", str(exc))
        result = await scorer.score_file(resolved)
        score_results.append(result)
        gate_results.append(evaluate_gate(result, preset=settings.quality_preset))
    else:
        from tapps_core.common.utils import should_skip_path

        # should_skip_path excludes .venv*, node_modules, dist,
        # build, __pycache__, and other generated directories.
        py_files = sorted(_Path(settings.project_root).rglob("*.py"))
        py_files = [f for f in py_files if not should_skip_path(f)][: max(1, max_files)]

        tracker = _ReportProgressTracker(total=len(py_files))
        tracker.init_sidecar(settings.project_root)

        async def _score_one(pf: _Path) -> tuple[Any, Any] | None:
            try:
                res = await scorer.score_file(pf)
                gate = evaluate_gate(res, preset=settings.quality_preset)
                tracker.completed += 1
                tracker.last_file = pf.name
                score_val = getattr(res, "overall_score", 0)
                tracker.record_file_result(str(pf), {"overall_score": score_val})
                await emit_ctx_info(ctx, f"Scored {pf.name}: {score_val}/100")
                return res, gate
            except (ValueError, OSError, RuntimeError) as e:
                logger.warning("report_file_skip", file=str(pf), error=str(e))
                return None

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
                    with contextlib.suppress(asyncio.CancelledError):
                        await asyncio.wait_for(_stop_event.wait(), timeout=5.0)

            _heartbeat_task = asyncio.create_task(_report_heartbeat())

        try:
            tasks = [_score_one(pf) for pf in py_files]
            outcomes = await asyncio.gather(*tasks, return_exceptions=False)
            for out in outcomes:
                if out is not None:
                    score_results.append(out[0])
                    gate_results.append(out[1])

            elapsed_ms_inner = (time.perf_counter_ns() - start) // 1_000_000
            tracker.finalize(
                f"{len(score_results)} files scored", elapsed_ms_inner
            )
        except Exception as exc:
            tracker.finalize_error(str(exc))
            raise
        finally:
            _stop_event.set()
            if _heartbeat_task is not None:
                _heartbeat_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await _heartbeat_task

    report_data = generate_report(score_results, gate_results, report_format=report_format)
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
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Scan a Python file for dead code (unused functions, classes, imports, variables).

    Args:
        file_path: Path to the Python file to scan (required when scope="file").
        min_confidence: Minimum confidence threshold (0-100, default 80).
        scope: Scan scope - "file" (single file), "project" (all .py files),
            or "changed" (git-changed .py files only).
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

    if scope == "file":
        if not file_path:
            return error_response(
                "tapps_dead_code", "missing_file_path",
                "file_path is required when scope='file'",
            )
        try:
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
        files_scanned = 1
        display_path = str(resolved)
    else:
        project_root = settings.project_root
        if scope == "project":
            file_list = collect_python_files(project_root)
        else:
            file_list = collect_changed_python_files(project_root)

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
            cwd=str(project_root),
            timeout=120,
        )
        findings = result.findings
        files_scanned = result.files_scanned
        degraded = result.degraded
        display_path = str(project_root)

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
        await emit_ctx_info(ctx, f"Dead code scan complete: {len(findings)} items in {files_scanned} file(s)")

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
    """Scan project dependencies for known vulnerabilities using pip-audit.

    Args:
        project_root: Project root path (default: server's configured root).
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
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.wait_for(_stop_event.wait(), timeout=5.0)

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
            with contextlib.suppress(asyncio.CancelledError):
                await _heartbeat_task

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
    summary = (
        f"Scanned {result.scanned_packages} packages: "
        f"{len(result.findings)} vulnerabilities"
    )
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
    """Analyze import dependencies: detect circular imports and measure coupling.

    Args:
        project_root: Project root path (default: server's configured root).
        detect_cycles: Whether to detect circular dependency cycles.
        include_coupling: Whether to calculate coupling metrics.
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
# Registration
# ---------------------------------------------------------------------------


def register(mcp_instance: FastMCP) -> None:
    """Register analysis tools on the shared *mcp_instance*."""
    mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_session_notes)
    mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_impact_analysis)
    mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_report)
    mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_dead_code)
    mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY_OPEN)(tapps_dependency_scan)
    mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_dependency_graph)
