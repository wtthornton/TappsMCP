"""Pipeline orchestration and validation tool handlers for TappsMCP.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:`register`.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json as _json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

from tapps_core.config.settings import load_settings
from tapps_mcp.common.developer_workflow import get_developer_workflow_dict
from tapps_mcp.server_helpers import (
    collect_session_hive_status,
    emit_ctx_info,
    error_response,
    initial_session_hive_status,
    success_response,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from mcp.server.fastmcp import FastMCP

    from tapps_core.config.settings import TappsMCPSettings
    from tapps_core.memory.models import MemorySnapshot
    from tapps_core.memory.store import MemoryStore
    from tapps_mcp.common.elicitation import WizardResult

_logger = structlog.get_logger(__name__)


def _current_docs_provider() -> dict[str, Any]:
    """Return a summary of the active docs-lookup provider (Issue #79).

    Gives agents a way to see at a glance whether ``tapps_lookup_docs``
    will use Context7 (full coverage) or the LlmsTxt fallback (reduced).
    """
    import os as _os

    has_key = bool(
        _os.environ.get("TAPPS_MCP_CONTEXT7_API_KEY")
        or _os.environ.get("CONTEXT7_API_KEY")
    )
    info: dict[str, Any] = {
        "primary": "context7" if has_key else "llmstxt",
        "context7_configured": has_key,
    }
    if not has_key:
        info["hint"] = (
            "Set TAPPS_MCP_CONTEXT7_API_KEY for richer docs via Context7. "
            "https://context7.com"
        )
    return info

# Maximum files to validate concurrently (balances speed vs subprocess pressure).
_VALIDATE_CONCURRENCY = 10

# STORY-101.3 — wall-clock cap on auto-detect tapps_validate_changed runs.
# Large repos can yield hundreds of changed files; without a cap, agents
# can block for minutes. Explicit file_paths mode ignores this budget.
# Kept module-level so STORY-101.6 (perf budget regression test) can tune it.
_AUTO_DETECT_BUDGET_S: float = 30.0

# Track whether auto-GC and consolidation have already run this session.
# Uses a mutable container to avoid PLW0603 ``global`` statements.
_session_state: dict[str, bool] = {
    "gc_done": False,
    "consolidation_done": False,
    "doc_validation_done": False,
}


def _reset_session_gc_flag() -> None:
    """Reset the auto-GC flag (for testing)."""
    _session_state["gc_done"] = False


def _reset_session_consolidation_flag() -> None:
    """Reset the consolidation scan flag (for testing)."""
    _session_state["consolidation_done"] = False


def _reset_session_doc_validation_flag() -> None:
    """Reset the doc validation flag (for testing)."""
    _session_state["doc_validation_done"] = False


def _reset_session_state() -> None:
    """Reset all session state flags (for testing)."""
    _session_state["gc_done"] = False
    _session_state["consolidation_done"] = False


# Prevent garbage collection of fire-and-forget background tasks.
# Without strong references, asyncio tasks may be collected before completion.
_background_tasks: set[asyncio.Task[Any]] = set()

_ANNOTATIONS_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


_PROGRESS_HEARTBEAT_INTERVAL = 5  # seconds between progress notifications


_VALIDATION_PROGRESS_FILE = ".tapps-mcp/.validation-progress.json"


@dataclasses.dataclass
class _ProgressTracker:
    """Shared progress state for validate_changed heartbeat and sidecar file."""

    total: int = 0
    completed: int = 0
    last_file: str = ""
    _sidecar_path: Path | None = dataclasses.field(default=None, repr=False)
    _results: list[dict[str, Any]] = dataclasses.field(
        default_factory=list, repr=False
    )
    _started_at: str = dataclasses.field(default="", repr=False)

    def init_sidecar(self, project_root: Path) -> None:
        """Create sidecar progress file with initial 'running' status."""
        self._sidecar_path = project_root / _VALIDATION_PROGRESS_FILE
        self._started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._write_sidecar({"status": "running"})

    def record_file_result(self, file_path: str, result: dict[str, Any]) -> None:
        """Record a completed file result and update the sidecar."""
        self._results.append({
            "file": file_path,
            "score": result.get("overall_score", 0.0),
            "gate_passed": result.get("gate_passed", False),
        })
        self._write_sidecar({"status": "running"})

    def finalize(
        self,
        all_passed: bool,
        summary: str,
        elapsed_ms: int,
    ) -> None:
        """Write final sidecar state with completed status."""
        self._write_sidecar({
            "status": "completed",
            "all_gates_passed": all_passed,
            "summary": summary,
            "elapsed_ms": elapsed_ms,
        })

    def finalize_error(self, error: str) -> None:
        """Write error status to sidecar."""
        self._write_sidecar({"status": "error", "error": error})

    def _write_sidecar(self, extra: dict[str, Any]) -> None:
        """Write the sidecar progress file (best-effort, never raises)."""
        if self._sidecar_path is None:
            return
        try:
            data = {
                "started_at": self._started_at,
                "total": self.total,
                "completed": self.completed,
                "last_file": self.last_file,
                "results": self._results,
                **extra,
            }
            self._sidecar_path.parent.mkdir(parents=True, exist_ok=True)
            self._sidecar_path.write_text(
                _json.dumps(data, indent=2), encoding="utf-8"
            )
        except Exception:
            _logger.debug("sidecar_write_failed", exc_info=True)


# Marker file for stop hook: if present and recent, hook skips "run validate" reminder.
_VALIDATE_OK_MARKER = ".tapps-mcp/sessions/last_validate_ok"

# Severity ranking for impact analysis aggregation.
_SEVERITY_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}


def _write_validate_ok_marker(project_root: Path) -> None:
    """Write markers so hooks can detect that validation was run.

    Writes two markers:
    - ``_VALIDATE_OK_MARKER`` (legacy, for Cursor stop hook)
    - ``.tapps-mcp/.validation-marker`` (for Claude Code blocking hooks)
    """
    ts = str(time.time())
    with contextlib.suppress(OSError):
        marker = project_root / _VALIDATE_OK_MARKER
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(ts, encoding="utf-8")
    with contextlib.suppress(OSError):
        validation_marker = project_root / ".tapps-mcp" / ".validation-marker"
        validation_marker.parent.mkdir(parents=True, exist_ok=True)
        validation_marker.write_text(ts, encoding="utf-8")


async def _maybe_run_wizard(
    ctx: Context[Any, Any, Any],
    *,
    llm_engagement_level: str | None,
    platform: str,
    agent_teams: bool,
) -> WizardResult | None:
    """Run the interactive wizard if this is a true first-run.

    Returns a :class:`WizardResult` when the wizard ran and completed,
    or ``None`` when skipped.
    """
    # Skip if explicit params were provided (not all defaults)
    if llm_engagement_level is not None or platform or agent_teams:
        return None

    # Skip if existing config already present
    settings = load_settings()
    proj = settings.project_root
    has_settings = (proj / ".claude" / "settings.json").exists()
    has_yaml = (proj / ".tapps-mcp.yaml").exists()
    if has_settings or has_yaml:
        return None

    from tapps_mcp.common.elicitation import run_init_wizard

    wizard = await run_init_wizard(ctx)
    if not wizard.completed:
        return None

    # Persist wizard answers in .tapps-mcp.yaml
    yaml_content = (
        f"llm_engagement_level: {wizard.engagement_level}\n"
        f"quality_preset: {wizard.quality_preset}\n"
    )
    yaml_path = proj / ".tapps-mcp.yaml"
    with contextlib.suppress(OSError):
        await asyncio.to_thread(yaml_path.write_text, yaml_content, encoding="utf-8")

    return wizard


async def _validate_progress_heartbeat(
    ctx: object,
    total_files: int,
    start_ns: int,
    stop_event: asyncio.Event,
    tracker: _ProgressTracker | None = None,
) -> None:
    """Send progress notifications every _PROGRESS_HEARTBEAT_INTERVAL seconds.
    Stops when stop_event is set. No-op if ctx has no report_progress.
    """
    report = getattr(ctx, "report_progress", None)
    if not callable(report):
        return
    while True:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=_PROGRESS_HEARTBEAT_INTERVAL)
        if stop_event.is_set():
            return
        with contextlib.suppress(Exception):
            if tracker is not None:
                done = tracker.completed
                last = tracker.last_file
                msg = f"Validated {done}/{tracker.total} files"
                if last:
                    msg += f" ({last})"
                await report(progress=done, total=tracker.total, message=msg)
            else:
                elapsed_sec = (time.perf_counter_ns() - start_ns) / 1_000_000_000.0
                await report(
                    progress=elapsed_sec,
                    total=None,
                    message=f"Validating {total_files} files... (in progress)",
                )


def _discover_changed_files(
    file_paths: str,
    base_ref: str,
    project_root: Path,
) -> list[Path]:
    """Resolve the list of scorable files to validate.

    When *file_paths* is non-empty, parse the comma-separated list and
    validate each path. Otherwise, auto-detect changed scorable files
    via ``git diff``.

    Supports: Python (.py, .pyi), TypeScript/JavaScript (.ts, .tsx, .js, .jsx, .mjs, .cjs),
    Go (.go), and Rust (.rs) files.
    """
    from tapps_mcp.server import _validate_file_path
    from tapps_mcp.server_helpers import _is_scorable_file
    from tapps_mcp.tools.batch_validator import detect_changed_scorable_files

    paths: list[Path] = []
    if file_paths.strip():
        for raw_fp in file_paths.split(","):
            cleaned_fp = raw_fp.strip()
            if not cleaned_fp:
                continue
            # Check if the file has a scorable extension
            if not _is_scorable_file(cleaned_fp):
                continue
            with contextlib.suppress(ValueError, FileNotFoundError):
                paths.append(_validate_file_path(cleaned_fp))
    else:
        paths = detect_changed_scorable_files(project_root, base_ref)
    return paths


async def _validate_single_file(
    path: Path,
    preset: str,
    quick: bool,
    do_security_full: bool,
    sem: asyncio.Semaphore,
    tracker: _ProgressTracker | None = None,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Score and optionally security-scan a single file under concurrency limit.

    Supports multi-language files by using the appropriate scorer based on file extension:
    - Python (.py, .pyi) -> CodeScorer
    - TypeScript/JavaScript (.ts, .tsx, .js, .jsx, .mjs, .cjs) -> TypeScriptScorer
    - Go (.go) -> GoScorer
    - Rust (.rs) -> RustScorer
    """
    from tapps_mcp.gates.evaluator import evaluate_gate
    from tapps_mcp.server_helpers import _get_scorer_for_file

    async with sem:
        file_result: dict[str, Any] = {"file_path": str(path)}
        try:
            # Get the appropriate scorer for this file's language
            scorer = _get_scorer_for_file(path)
            if scorer is None:
                file_result["errors"] = [f"Unsupported file type: {path.suffix}"]
                return file_result

            file_result["language"] = scorer.language

            if quick:
                score = await asyncio.to_thread(scorer.score_file_quick, path)
            else:
                score = await scorer.score_file(path)
            file_result["overall_score"] = round(score.overall_score, 2)

            gate = evaluate_gate(score, preset=preset)
            file_result["gate_passed"] = gate.passed
            if gate.failures:
                file_result["gate_failures"] = [f.model_dump() for f in gate.failures]

            # Security scanning - currently Python-only (bandit-based)
            is_python = scorer.language == "python"
            if do_security_full and is_python:
                from tapps_mcp.security.secret_scanner import SecretScanner

                secret_result = SecretScanner().scan_file(str(path))
                bandit_count = len(score.security_issues)
                secret_count = secret_result.total_findings
                bandit_crit_high = sum(
                    1 for i in score.security_issues if i.severity in ("critical", "high")
                )
                file_result["security_passed"] = (
                    bandit_crit_high + secret_result.high_severity
                ) == 0
                file_result["security_issues"] = bandit_count + secret_count
            elif is_python and quick:
                file_result["security_passed"] = True
                file_result["security_issues"] = 0
            else:
                # Non-Python files: no security scanning yet (future: eslint-plugin-security, gosec, etc.)
                file_result["security_passed"] = True
                file_result["security_issues"] = 0
        except Exception as exc:
            file_result["errors"] = [str(exc)]
        if tracker is not None:
            tracker.completed += 1
            tracker.last_file = path.name
            tracker.record_file_result(str(path), file_result)
        await _emit_file_info(ctx, path, file_result)
        return file_result


async def _emit_file_info(
    ctx: Context[Any, Any, Any] | None,
    path: Path,
    result: dict[str, Any],
) -> None:
    """Send a ctx.info() log notification for the completed file (best-effort)."""
    score = result.get("overall_score", "?")
    passed = result.get("gate_passed", False)
    status = "PASSED" if passed else "FAILED"
    await emit_ctx_info(ctx, f"Validated {path.name}: {score}/100, gate {status}")


def _compute_impact_analysis(
    paths: list[Path],
    project_root: Path,
) -> dict[str, Any] | None:
    """Build impact analysis data for the given file paths.

    Returns a summary dict or ``None`` if impact analysis is not requested.
    On failure, returns ``{"error": "impact analysis failed"}``.
    """
    try:
        from tapps_mcp.project.impact_analyzer import analyze_impact, build_import_graph

        import_graph = build_import_graph(project_root)

        impact_results: list[dict[str, Any]] = []
        for p in paths:
            try:
                impact_report = analyze_impact(p, project_root, graph=import_graph)
                impact_results.append(
                    {
                        "file": str(p),
                        "severity": impact_report.severity,
                        "direct_dependents": len(impact_report.direct_dependents),
                        "transitive_dependents": len(impact_report.transitive_dependents),
                        "test_files": len(impact_report.test_files),
                    }
                )
            except Exception:
                _logger.debug("impact_analysis_file_failed", file=str(p), exc_info=True)
                impact_results.append({"file": str(p), "severity": "unknown", "error": True})

        max_severity = "low"
        for ir in impact_results:
            s = ir.get("severity", "low")
            if _SEVERITY_RANK.get(s, 0) > _SEVERITY_RANK.get(max_severity, 0):
                max_severity = s

        total_affected = sum(
            ir.get("direct_dependents", 0) + ir.get("transitive_dependents", 0)
            for ir in impact_results
        )
        return {
            "max_severity": max_severity,
            "total_affected_files": total_affected,
            "per_file": impact_results,
        }
    except Exception:
        _logger.debug("impact_analysis_failed", exc_info=True)
        return {"error": "impact analysis failed"}


def _build_structured_validation_output(
    results: list[dict[str, Any]],
    all_passed: bool,
    security_depth: str,
    impact_data: dict[str, Any] | None,
    resp: dict[str, Any],
) -> None:
    """Attach structured content to the response dict (best-effort)."""
    try:
        from tapps_mcp.common.output_schemas import (
            FileValidationResult,
            ValidateChangedOutput,
        )

        file_results = [
            FileValidationResult(
                file_path=r.get("file_path", ""),
                score=r.get("overall_score", 0.0),
                gate_passed=r.get("gate_passed", False),
                security_passed=r.get("security_passed", True),
            )
            for r in results
        ]
        failed_count = sum(1 for r in results if not r.get("gate_passed", False))
        structured = ValidateChangedOutput(
            files=file_results,
            overall_passed=all_passed,
            total_files=len(results),
            passed_count=len(results) - failed_count,
            failed_count=failed_count,
            security_depth=security_depth,
            impact_summary=impact_data,
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        _logger.debug("structured_output_failed: tapps_validate_changed", exc_info=True)


def _resolve_security_depth(
    security_depth: str, include_security: bool, quick: bool
) -> bool:
    """Determine whether to run full security scanning."""
    return (security_depth == "full") or (include_security and not quick)


def _build_per_file_results(
    results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build machine-readable per-file results and grep-friendly summary rows.

    Returns:
        Tuple of (per_file_results list, summary_rows text lines).
    """
    per_file: list[dict[str, Any]] = []
    rows: list[str] = []

    for r in results:
        file_path = r.get("file_path", r.get("file", "unknown"))
        file_name = Path(file_path).name if file_path != "unknown" else "unknown"
        gate_passed = r.get("gate_passed", False)
        score = r.get("score", r.get("overall_score", 0.0))
        security_issues = r.get("security_issues", 0)
        errors = r.get("errors", [])

        status = "PASS" if gate_passed and not errors else "FAIL"
        security_status = "fail" if security_issues > 0 else "pass"
        issue_count = len(errors) + security_issues

        entry: dict[str, Any] = {
            "file": file_name,
            "file_path": str(file_path),
            "status": status,
            "score": round(float(score), 1) if score else 0.0,
            "gate_passed": gate_passed,
            "security_passed": security_issues == 0,
            "issue_count": issue_count,
        }
        per_file.append(entry)

        # Build grep-friendly row
        row_parts = [
            f"{status:<5}",
            f"{file_name:<30}",
            f"score={entry['score']:.1f}",
            f"gate={'pass' if gate_passed else 'fail'}",
            f"security={security_status}",
        ]
        if issue_count > 0:
            row_parts.append(f"issues={issue_count}")
        rows.append("  ".join(row_parts))

    return per_file, rows


def _build_validation_summary(
    results: list[dict[str, Any]],
    quick: bool,
    capped: bool,
    extra_count: int,
) -> str:
    """Build the human-readable validation summary string."""
    from tapps_mcp.tools.batch_validator import MAX_BATCH_FILES, format_batch_summary

    summary = format_batch_summary(results)
    if quick:
        summary = f"[Quick mode] {summary}"
    if capped:
        summary += f" ({extra_count} additional files not validated - cap {MAX_BATCH_FILES})"
    return summary


async def tapps_validate_changed(
    file_paths: str = "",
    base_ref: str = "HEAD",
    preset: str = "standard",
    include_security: bool = True,
    quick: bool = True,
    security_depth: str = "basic",
    include_impact: bool = True,
    correlation_id: str = "",
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """REQUIRED before declaring multi-file work complete.
    Detects changed scorable files (via git diff) or accepts an explicit
    comma-separated list. Runs score + quality gate on each file; security
    scan only for Python files when quick=False or security_depth='full'
    (default quick=True does not run security). Skipping means quality
    issues in changed files go undetected.

    Supports multi-language scoring:
    - Python (.py, .pyi)
    - TypeScript/JavaScript (.ts, .tsx, .js, .jsx, .mjs, .cjs)
    - Go (.go)
    - Rust (.rs)

    If this tool is unavailable or rejected, use tapps_quick_check on
    individual changed files as a fallback.

    Default is quick=True (ruff-only, typically under 10s). Pass quick=False
    for full validation (ruff, mypy, bandit, radon, vulture per file, 1-5+ min).
    To include security scan in default quick mode, pass security_depth='full'.

    Args:
        file_paths: Comma-separated file paths (empty = auto-detect via git diff).
        base_ref: Git ref to diff against (default: HEAD for unstaged changes).
        preset: Quality gate preset - "standard", "strict", or "framework".
        include_security: Whether to run security scan on each file (ignored if quick=True).
        quick: If True (default), ruff-only scoring for speed. If False, full validation.
        security_depth: Security scan depth - "basic" (default) or "full". When "full",
            security scan runs even in quick mode.
        include_impact: Whether to run impact analysis on changed files (default: True).
        correlation_id: Optional caller-provided ID echoed in the response for traceability.
            Empty string (default) means no correlation ID is included in the response.
        ctx: Optional MCP context (injected by host); used for progress notifications.
    """
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges
    from tapps_mcp.server_helpers import ensure_session_initialized
    from tapps_mcp.tools.batch_validator import MAX_BATCH_FILES

    start = time.perf_counter_ns()
    _record_call("tapps_validate_changed")

    settings = load_settings()
    paths = _discover_changed_files(file_paths, base_ref, settings.project_root)

    if not paths:
        return _handle_no_changed_files(
            start, settings, _record_execution, _with_nudges,
            explicit_paths=bool(file_paths.strip()),
            base_ref=base_ref,
            correlation_id=correlation_id,
        )

    capped = len(paths) > MAX_BATCH_FILES
    extra_count = len(paths) - MAX_BATCH_FILES if capped else 0
    paths = paths[:MAX_BATCH_FILES]
    total_files = len(paths)

    tracker = _ProgressTracker(total=total_files)
    tracker.init_sidecar(settings.project_root)
    stop_progress = asyncio.Event()
    progress_task = _start_progress_reporting(
        ctx, total_files, start, stop_progress, tracker
    )

    auto_detect = not file_paths.strip()
    cached_results, uncached_paths = _partition_by_cache(paths)

    timed_out = False
    files_remaining: list[Path] = []

    try:
        await ensure_session_initialized()
        _maybe_warm_dependency_cache(settings, quick)

        sem = asyncio.Semaphore(_VALIDATE_CONCURRENCY)
        do_security_full = _resolve_security_depth(security_depth, include_security, quick)

        tasks = [
            asyncio.create_task(
                _validate_single_file(
                    p, preset, quick, do_security_full, sem, tracker, ctx
                )
            )
            for p in uncached_paths
        ]

        if auto_detect and tasks:
            elapsed_s = (time.perf_counter_ns() - start) / 1e9
            remaining_budget = max(0.0, _AUTO_DETECT_BUDGET_S - elapsed_s)
            done, pending = await asyncio.wait(tasks, timeout=remaining_budget)
            raw_results: list[dict[str, Any] | BaseException] = []
            completed_paths: list[Path] = []
            for p, t in zip(uncached_paths, tasks, strict=True):
                if t in done:
                    try:
                        raw_results.append(t.result())
                    except Exception as exc:
                        raw_results.append(exc)
                    completed_paths.append(p)
                else:
                    files_remaining.append(p)
                    t.cancel()
            if pending:
                timed_out = True
                with contextlib.suppress(Exception):
                    await asyncio.gather(*pending, return_exceptions=True)
            task_results = _collect_results(raw_results, completed_paths)
        elif tasks:
            raw_results = list(
                await asyncio.gather(*tasks, return_exceptions=True)
            )
            task_results = _collect_results(raw_results, uncached_paths)
        else:
            task_results = []
    except Exception as exc:
        _record_call("tapps_validate_changed", success=False)
        tracker.finalize_error(str(exc))
        raise
    finally:
        if progress_task is not None:
            stop_progress.set()
            progress_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await progress_task

    results = [*task_results, *cached_results]
    all_passed = all(r.get("gate_passed", False) for r in results)
    total_sec = sum(r.get("security_issues", 0) for r in results)

    impact_data = (
        _compute_impact_analysis(paths, settings.project_root) if include_impact and paths else None
    )

    summary = _build_validation_summary(results, quick, capped, extra_count)
    per_file_results, summary_rows = _build_per_file_results(results)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    if not all_passed:
        _record_call("tapps_validate_changed", success=False)
    _record_execution("tapps_validate_changed", start, gate_passed=all_passed)
    tracker.finalize(all_passed, summary, elapsed_ms)
    if all_passed:
        _write_validate_ok_marker(settings.project_root)

    resp_data: dict[str, Any] = {
        "files_validated": len(results),
        "all_gates_passed": all_passed,
        "total_security_issues": total_sec,
        "per_file_results": per_file_results,
        "summary_rows": summary_rows,
        "results": results,
        "summary": summary,
    }
    if impact_data is not None:
        resp_data["impact_summary"] = impact_data

    # EPIC-102: auto-recall of relevant insights (opt-in)
    if settings.memory.recall_on_validate:
        from tapps_mcp.tools.insight_recall import recall_insights_for_validate

        recall_data = recall_insights_for_validate(paths, settings.project_root)
        resp_data.update(recall_data)
    if correlation_id.strip():
        resp_data["correlation_id"] = correlation_id.strip()
    if timed_out:
        resp_data["timed_out"] = True
        resp_data["files_remaining"] = len(files_remaining)
        resp_data["files_remaining_paths"] = [str(p) for p in files_remaining]
        resp_data["auto_detect_budget_s"] = _AUTO_DETECT_BUDGET_S

    resp = success_response("tapps_validate_changed", elapsed_ms, resp_data)
    _build_structured_validation_output(results, all_passed, security_depth, impact_data, resp)
    resp = _with_nudges("tapps_validate_changed", resp)
    if timed_out:
        data = resp.get("data", {})
        sample = ",".join(str(p) for p in files_remaining[:10])
        hint = (
            f"Auto-detect exceeded {_AUTO_DETECT_BUDGET_S:.0f}s budget with "
            f"{len(files_remaining)} files unvalidated. Finish with explicit "
            f'paths: tapps_validate_changed(file_paths="{sample}")'
        )
        existing = list(data.get("next_steps") or [])
        data["next_steps"] = [hint, *existing][:5]
    return resp


def _handle_no_changed_files(
    start: int,
    settings: TappsMCPSettings,
    record_execution: Callable[..., object],
    with_nudges: Callable[..., dict[str, object]],
    *,
    explicit_paths: bool = False,
    base_ref: str = "HEAD",
    correlation_id: str = "",
) -> dict[str, Any]:
    """Return early response when no changed Python files are found."""
    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    def _deferred_record() -> None:
        record_execution("tapps_validate_changed", start)

    task = asyncio.create_task(asyncio.to_thread(_deferred_record))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    _write_validate_ok_marker(settings.project_root)

    resp_data: dict[str, Any] = {
        "files_validated": 0,
        "all_gates_passed": True,
        "total_security_issues": 0,
        "results": [],
        "summary": "No changed scorable files found.",
    }

    warnings: list[str] = []

    # Warn when auto-detecting with base_ref=HEAD and zero files found
    if not explicit_paths and base_ref.strip().upper() == "HEAD":
        warnings.append(
            "Zero changed files detected with base_ref=HEAD. "
            "If you have staged-but-uncommitted changes, diff against HEAD "
            "will not include them. Consider committing first or using a "
            "different base_ref (e.g. base_ref='HEAD~1')."
        )

    if explicit_paths:
        resp_data["path_hint"] = (
            "Explicit paths provided but none validated. "
            "If using Docker, check TAPPS_MCP_PROJECT_ROOT / "
            "TAPPS_MCP_HOST_PROJECT_ROOT for path mapping."
        )
        resp_data["next_steps"] = [
            "FALLBACK: Use tapps_quick_check on individual files when paths don't map.",
            "Check that file paths are relative to server's project_root"
            " or use TAPPS_MCP_HOST_PROJECT_ROOT.",
        ]

    if warnings:
        resp_data["warnings"] = warnings
    if correlation_id.strip():
        resp_data["correlation_id"] = correlation_id.strip()

    resp = success_response(
        "tapps_validate_changed",
        elapsed_ms,
        resp_data,
    )
    return with_nudges("tapps_validate_changed", resp)


def _start_progress_reporting(
    ctx: Context[Any, Any, Any] | None,
    total_files: int,
    start: int,
    stop_event: asyncio.Event,
    tracker: _ProgressTracker | None = None,
) -> asyncio.Task[None] | None:
    """Start the progress heartbeat task if context supports it."""
    if ctx is None or total_files <= 0:
        return None
    report = getattr(ctx, "report_progress", None)
    if callable(report):
        with contextlib.suppress(Exception):
            # Fire initial progress via background task (store ref to prevent GC)
            init_task = asyncio.create_task(
                _report_initial_progress(report, total_files)
            )
            _background_tasks.add(init_task)
            init_task.add_done_callback(_background_tasks.discard)
    return asyncio.create_task(
        _validate_progress_heartbeat(ctx, total_files, start, stop_event, tracker),
    )


async def _report_initial_progress(
    report: Callable[..., Awaitable[Any]],
    total_files: int,
) -> None:
    """Send the initial progress=0 notification."""
    with contextlib.suppress(Exception):
        await report(
            progress=0,
            total=total_files,
            message=f"Validating {total_files} files...",
        )


def _maybe_warm_dependency_cache(
    settings: TappsMCPSettings,
    quick: bool,
) -> None:
    """Warm dependency cache in background when empty (does not block)."""
    if not settings.dependency_scan_enabled or quick:
        return
    from tapps_mcp.tools.dependency_scan_cache import get_dependency_findings

    if not get_dependency_findings(str(settings.project_root)):
        task = asyncio.create_task(_warm_dependency_cache(settings))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)


def _cache_hit_as_file_result(path: Path) -> dict[str, Any] | None:
    """Return a validate_changed-shaped file_result from content-hash cache.

    STORY-101.3 — reuses the ``KIND_QUICK_CHECK`` entry populated by
    :func:`tapps_quick_check` so identical-content re-validations don't
    consume the auto-detect wall-clock budget.
    """
    from tapps_mcp.tools import content_hash_cache as _chc

    try:
        sha = _chc.content_hash(path)
    except (OSError, FileNotFoundError):
        return None
    cached = _chc.get(_chc.KIND_QUICK_CHECK, sha)
    if cached is None:
        return None
    return {
        "file_path": str(path),
        "overall_score": cached.get("overall_score", 0.0),
        "gate_passed": cached.get("gate_passed", False),
        "security_passed": cached.get("security_passed", True),
        "security_issues": cached.get("security_issue_count", 0),
        "cache_hit": True,
    }


def _partition_by_cache(
    paths: list[Path],
) -> tuple[list[dict[str, Any]], list[Path]]:
    """Split ``paths`` into (cached_results, uncached_paths)."""
    cached_results: list[dict[str, Any]] = []
    uncached_paths: list[Path] = []
    for p in paths:
        hit = _cache_hit_as_file_result(p)
        if hit is not None:
            cached_results.append(hit)
        else:
            uncached_paths.append(p)
    return cached_results, uncached_paths


def _collect_results(
    raw_results: list[dict[str, Any] | BaseException],
    paths: list[Path],
) -> list[dict[str, Any]]:
    """Normalize gather results, converting exceptions to error dicts."""
    results: list[dict[str, Any]] = []
    for i, raw in enumerate(raw_results):
        if isinstance(raw, BaseException):
            results.append({"file_path": str(paths[i]), "errors": [str(raw)]})
        else:
            results.append(raw)
    return results


async def _warm_dependency_cache(
    settings: TappsMCPSettings,
) -> None:
    """Best-effort background task to warm the dependency scan cache.

    Available for use by :func:`tapps_validate_changed` or on first
    :func:`tapps_score_file` so subsequent scoring can apply vulnerability
    penalties. Not called from :func:`tapps_session_start` (session start
    is kept lightweight). Failures are silently ignored.
    """
    try:
        from tapps_mcp.tools.dependency_scan_cache import set_dependency_findings
        from tapps_mcp.tools.pip_audit import run_pip_audit_async

        result = await run_pip_audit_async(
            project_root=str(settings.project_root),
            source=settings.dependency_scan_source,
            severity_threshold=settings.dependency_scan_severity_threshold,
            ignore_ids=settings.dependency_scan_ignore_ids or None,
            timeout=30,
        )
        if not result.error:
            set_dependency_findings(str(settings.project_root), result.findings)
            _logger.debug(
                "dependency_cache_warmed",
                findings=len(result.findings),
            )
    except Exception:
        _logger.debug("dependency_cache_warming_failed", exc_info=True)


def _maybe_auto_gc(
    store: MemoryStore,
    current_count: int,
    settings: object,
) -> dict[str, Any] | None:
    """Run garbage collection if memory usage exceeds the configured threshold.

    Returns a summary dict when GC ran, or ``None`` if skipped.
    Only runs once per session (guarded by ``_session_state["gc_done"]``).
    """
    if _session_state["gc_done"]:
        return None

    mem_settings = getattr(settings, "memory", None)
    if mem_settings is None:
        return None

    gc_enabled = getattr(mem_settings, "gc_enabled", True)
    if not gc_enabled:
        return None

    max_memories = getattr(mem_settings, "max_memories", 1500)
    threshold = getattr(mem_settings, "gc_auto_threshold", 0.8)
    trigger_count = int(max_memories * threshold)

    if current_count <= trigger_count:
        return None

    _session_state["gc_done"] = True

    try:
        from tapps_core.memory.decay import DecayConfig
        from tapps_core.memory.gc import MemoryGarbageCollector

        config = DecayConfig()
        gc = MemoryGarbageCollector(config)

        snapshot = store.snapshot()
        candidates = gc.identify_candidates(snapshot.entries)

        archived_keys: list[str] = []
        for candidate in candidates:
            deleted = store.delete(candidate.key)
            if deleted:
                archived_keys.append(candidate.key)

        remaining = store.count()

        _logger.info(
            "session_auto_gc_completed",
            evicted=len(archived_keys),
            remaining=remaining,
            threshold=threshold,
        )

        return {
            "ran": True,
            "evicted": len(archived_keys),
            "remaining": remaining,
        }
    except Exception:
        _logger.debug("session_auto_gc_failed", exc_info=True)
        return {"ran": False, "error": "auto-gc failed"}


def _enrich_memory_status_hints(
    memory_status: dict[str, Any],
    entries: list[Any],
    settings: TappsMCPSettings,
) -> None:
    """Add consolidation and federation hints to memory_status when applicable (Epic 65.1)."""
    try:
        from tapps_core.metrics.dashboard import DashboardGenerator

        consolidation = DashboardGenerator._compute_consolidation_stats(entries)
        if consolidation.get("consolidation_groups", 0) > 0:
            memory_status["consolidation_hint"] = (
                f"{consolidation['consolidated_count']} groups, "
                f"{consolidation['source_entries_count']} source entries"
            )

        from tapps_core.memory.federation import load_federation_config

        config = load_federation_config()
        project_root_str = str(settings.project_root)
        if any(p.project_root == project_root_str for p in config.projects):
            synced = sum(1 for e in entries if "federated" in (e.tags or []))
            memory_status["federation_hint"] = (
                f"hub_registered, {synced} synced entries"
            )
    except Exception:
        _logger.debug("memory_status_hints_failed", exc_info=True)


def _enrich_memory_profile_status(
    memory_status: dict[str, Any],
    store: Any,
    settings: TappsMCPSettings,
) -> None:
    """Add active profile name and source to memory_status (Epic M2.4)."""
    try:
        profile = store.profile
        if profile is not None:
            profile_name = profile.name
        else:
            profile_name = "repo-brain"

        # Detect source
        project_yaml = settings.project_root / ".tapps-brain" / "profile.yaml"
        if settings.memory.profile:
            source = "settings"
        elif project_yaml.exists():
            source = "project_override"
        else:
            source = "default"

        memory_status["profile"] = profile_name
        memory_status["profile_source"] = source
    except Exception:
        _logger.debug("memory_profile_status_failed", exc_info=True)


def _maybe_consolidation_scan(
    store: MemoryStore,
    settings: TappsMCPSettings,
) -> dict[str, Any] | None:
    """Run periodic memory consolidation scan if enabled and due.

    Returns a summary dict when scan ran, or ``None`` if skipped.
    Only runs once per session (guarded by ``_session_state["consolidation_done"]``).

    Epic 58, Story 58.3: Periodic consolidation scan at session start.
    """
    # Early exit: already ran this session or settings not configured
    if _session_state.get("consolidation_done", False):
        return None

    mem_settings = getattr(settings, "memory", None)
    consolidation_settings = (
        getattr(mem_settings, "consolidation", None) if mem_settings else None
    )
    scan_enabled = getattr(consolidation_settings, "scan_on_session_start", True)
    if not consolidation_settings or not scan_enabled:
        return None

    _session_state["consolidation_done"] = True

    try:
        from tapps_core.memory.auto_consolidation import run_periodic_consolidation_scan

        result = run_periodic_consolidation_scan(
            store,
            settings.project_root,
            threshold=consolidation_settings.threshold,
            min_group_size=consolidation_settings.min_entries,
            scan_interval_days=consolidation_settings.scan_interval_days,
        )

        if result.scanned:
            _logger.info(
                "session_consolidation_scan_completed",
                groups_found=result.groups_found,
                entries_consolidated=result.entries_consolidated,
            )
            return result.to_dict()

        if result.skipped_reason:
            _logger.debug(
                "session_consolidation_scan_skipped",
                reason=result.skipped_reason,
            )
            return {"skipped": True, "reason": result.skipped_reason}

        return None
    except Exception:
        _logger.debug("session_consolidation_scan_failed", exc_info=True)
        return {"ran": False, "error": "consolidation scan failed"}


def _process_session_capture(
    project_root: Path,
    store: MemoryStore,
) -> dict[str, Any] | None:
    """Check for and process a session-capture.json left by the Stop hook.

    If the file exists, reads it, persists the data to memory, deletes
    the capture file, and returns a summary dict.  Returns ``None`` if
    no capture file exists.  Failures are logged and silently ignored.
    """
    import json as _json

    capture_path = project_root / ".tapps-mcp" / "session-capture.json"
    if not capture_path.exists():
        return None

    try:
        raw = capture_path.read_text(encoding="utf-8")
        data = _json.loads(raw)
        date_str = data.get("date", "unknown")
        validated = data.get("validated", False)
        files_edited = data.get("files_edited", 0)

        value = (
            f"Session on {date_str}: "
            f"{'validated' if validated else 'not validated'}, "
            f"{files_edited} Python file(s) edited."
        )
        store.save(
            key=f"session-capture.{date_str}",
            value=value,
            tier="context",
            source="system",
            source_agent="tapps-memory-capture-hook",
            scope="project",
            tags=["session-capture", "auto"],
        )

        capture_path.unlink(missing_ok=True)

        _logger.info(
            "session_capture_processed",
            date=date_str,
            validated=validated,
            files_edited=files_edited,
        )
        return {
            "date": date_str,
            "validated": validated,
            "files_edited": files_edited,
        }
    except Exception:
        _logger.debug("session_capture_processing_failed", exc_info=True)
        # Clean up even on failure to avoid re-processing bad data
        with contextlib.suppress(OSError):
            capture_path.unlink(missing_ok=True)
        return None


async def _maybe_validate_memories(
    store: MemoryStore,
    settings: TappsMCPSettings,
) -> dict[str, Any] | None:
    """Validate stale memories against authoritative docs at session start.

    Returns a summary dict when validation ran, or ``None`` if skipped.
    Only runs once per session (guarded by ``_session_state["doc_validation_done"]``).

    Epic 62, Story 62.6: Session-start validation pass.
    """
    if _session_state.get("doc_validation_done", False):
        return None

    mem_settings = getattr(settings, "memory", None)
    doc_val = getattr(mem_settings, "doc_validation", None) if mem_settings else None
    if (
        doc_val is None
        or not getattr(doc_val, "enabled", False)
        or not getattr(doc_val, "validate_on_session_start", True)
    ):
        return None

    _session_state["doc_validation_done"] = True

    try:
        from tapps_core.knowledge.cache import KBCache
        from tapps_core.knowledge.lookup import LookupEngine
        from tapps_core.memory.doc_validation import MemoryDocValidator

        _cache = KBCache(settings.project_root / ".tapps-mcp-cache")
        lookup = LookupEngine(_cache, settings=settings)
        validator = MemoryDocValidator(lookup)  # type: ignore[arg-type]  # LookupEngine has extra kwargs vs LookupEngineLike Protocol

        all_entries = store.list_all()
        max_entries = getattr(doc_val, "max_entries_per_session", 5)
        threshold = getattr(doc_val, "confidence_threshold", 0.5)
        dry_run = getattr(doc_val, "dry_run", False)

        report = await validator.validate_stale(
            all_entries,
            confidence_threshold=threshold,
            max_entries=max_entries,
        )

        if not report.entries:
            return {"ran": True, "validated": 0, "skipped": "no stale entries"}

        apply_result = await validator.apply_results(
            report, store, dry_run=dry_run,
        )

        _logger.info(
            "session_doc_validation_completed",
            validated=report.validated,
            flagged=report.flagged,
            no_docs=report.no_docs,
            dry_run=dry_run,
        )

        return {
            "ran": True,
            "validated": report.validated,
            "flagged": report.flagged,
            "no_docs": report.no_docs,
            "adjustments": apply_result.boosted + apply_result.penalised,
            "dry_run": dry_run,
        }
    except Exception:
        _logger.debug("session_doc_validation_failed", exc_info=True)
        return {"ran": False, "error": "doc validation failed"}


def _schedule_background_maintenance(
    mem_store: MemoryStore,
    snapshot: MemorySnapshot,
    settings: TappsMCPSettings,
) -> None:
    """Schedule heavy memory maintenance ops as fire-and-forget background tasks.

    Moves GC, consolidation scan, doc validation, and session capture
    processing off the critical path so ``tapps_session_start`` returns faster.

    Epic 68.2: Session start performance optimization.
    """

    async def _run_maintenance() -> None:
        """Execute all maintenance ops sequentially in the background."""
        total_count: int = snapshot.total_count
        try:
            _maybe_auto_gc(mem_store, total_count, settings)
        except Exception:
            _logger.debug("background_auto_gc_failed", exc_info=True)

        try:
            _maybe_consolidation_scan(mem_store, settings)
        except Exception:
            _logger.debug("background_consolidation_scan_failed", exc_info=True)

        try:
            await _maybe_validate_memories(mem_store, settings)
        except Exception:
            _logger.debug("background_doc_validation_failed", exc_info=True)

        try:
            _process_session_capture(settings.project_root, mem_store)
        except Exception:
            _logger.debug("background_session_capture_failed", exc_info=True)

    task = asyncio.create_task(_run_maintenance())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _collect_memory_status(settings: Any) -> dict[str, Any]:
    """Collect memory subsystem status for session start."""
    status: dict[str, Any] = {"enabled": False}
    try:
        if not settings.memory.enabled:
            return status
        from tapps_mcp.server_helpers import _get_memory_store

        mem_store = _get_memory_store()
        if mem_store is None:
            return status

        snapshot = mem_store.snapshot()
        contradicted_count = sum(1 for entry in snapshot.entries if entry.contradicted)

        by_tier: dict[str, int] = {
            "architectural": 0, "pattern": 0, "procedural": 0, "context": 0,
        }
        confidences: list[float] = []
        for entry in snapshot.entries:
            tier_val = entry.tier if isinstance(entry.tier, str) else entry.tier.value
            by_tier[tier_val] = by_tier.get(tier_val, 0) + 1
            confidences.append(entry.confidence)

        avg_conf = round(sum(confidences) / len(confidences), 4) if confidences else 0.0
        max_mem = settings.memory.max_memories
        cap_pct = round((snapshot.total_count / max_mem) * 100, 1) if max_mem > 0 else 0.0

        status = {
            "enabled": True,
            "total": snapshot.total_count,
            "stale": 0,
            "contradicted": contradicted_count,
            "by_tier": by_tier,
            "avg_confidence": avg_conf,
            "capacity_pct": cap_pct,
        }

        _enrich_memory_profile_status(status, mem_store, settings)
        _enrich_memory_status_hints(status, snapshot.entries, settings)
        _schedule_background_maintenance(mem_store, snapshot, settings)
    except Exception:
        _logger.debug("memory_status_check_failed", exc_info=True)
    return status


async def tapps_session_start(
    project_root: str = "",
    quick: bool = False,
) -> dict[str, Any]:
    """REQUIRED as the FIRST call in every session. Returns server info
    (version, checkers, configuration, and project context).

    Args:
        project_root: Unused; reserved for future use. Server uses configured root.
        quick: When True, return minimal response using cached tool versions
            (no subprocess calls, no diagnostics, no memory GC). Target: < 1s.
    """
    from tapps_mcp.server import (
        _record_call,
        _record_execution,
        _with_nudges,
    )

    start = time.perf_counter_ns()
    try:
        from tapps_mcp.tools.checklist import CallTracker

        CallTracker.begin_session()
    except ImportError:
        pass
    _record_call("tapps_session_start")

    if quick:
        return await _session_start_quick(start, _record_execution, _with_nudges)

    from tapps_mcp.server import _server_info_async

    timings: dict[str, int] = {}
    settings = load_settings()

    phase_start = time.perf_counter_ns()
    info = await _server_info_async()
    timings["server_info_ms"] = (time.perf_counter_ns() - phase_start) // 1_000_000

    # Memory status (lazy, non-blocking)
    phase_start = time.perf_counter_ns()
    memory_status = _collect_memory_status(settings)
    timings["memory_status_ms"] = (time.perf_counter_ns() - phase_start) // 1_000_000

    # Hive / Agent Teams (Epic M3)
    phase_start = time.perf_counter_ns()
    hive_status: dict[str, Any] = initial_session_hive_status()
    try:
        hive_status = collect_session_hive_status(settings)
    except Exception:
        _logger.debug("hive_status_check_failed", exc_info=True)
    timings["hive_status_ms"] = (time.perf_counter_ns() - phase_start) // 1_000_000

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_session_start", start)
    timings["total_ms"] = elapsed_ms

    # Docker path mapping (Story 75.1)
    path_mapping = None
    container_warning = None
    try:
        from tapps_core.common.utils import get_path_mapping, is_running_in_container

        if is_running_in_container():
            path_mapping = get_path_mapping()
            if path_mapping and not path_mapping.get("mapping_available"):
                container_warning = (
                    "Running in container but TAPPS_HOST_ROOT not set. "
                    "File paths will use container paths (e.g. /workspace/...). "
                    "Set TAPPS_HOST_ROOT to enable host path mapping."
                )
    except Exception:
        _logger.debug("path_mapping_detection_failed", exc_info=True)

    checklist_sid: str | None = None
    try:
        from tapps_mcp.tools.checklist import CallTracker

        checklist_sid = CallTracker.get_active_checklist_session_id()
    except ImportError:
        pass

    # Include binary path for version-mismatch diagnosis (#89)
    import shutil
    import sys

    server_info = dict(info["data"]["server"])
    server_info["executable"] = sys.executable
    server_info["binary_path"] = shutil.which("tapps-mcp") or ""

    data: dict[str, Any] = {
        "project_root": str(settings.project_root),
        "server": server_info,
        "configuration": info["data"]["configuration"],
        "installed_checkers": info["data"]["installed_checkers"],
        "checker_environment": info["data"].get("checker_environment", "mcp_server"),
        "checker_environment_note": info["data"].get(
            "checker_environment_note",
            "Checker availability reflects the MCP server process environment. "
            "Target project may have different tools installed.",
        ),
        "docs_provider": info["data"].get("docs_provider", _current_docs_provider()),
        "diagnostics": info["data"]["diagnostics"],
        "quick_start": info["data"].get("quick_start", []),
        "critical_rules": info["data"].get("critical_rules", []),
        "pipeline": info["data"]["pipeline"],
        "checklist_session_id": checklist_sid,
        "memory_status": memory_status,
        "hive_status": hive_status,
        "memory_gc": "background",
        "memory_consolidation": "background",
        "memory_doc_validation": "background",
        "session_capture": "background",
        "timings": timings,
        "path_mapping": path_mapping,
        "cache": info["data"].get("cache"),
    }

    if container_warning:
        data["warnings"] = [container_warning]

    resp = success_response("tapps_session_start", elapsed_ms, data)

    # Attach structured output
    try:
        from tapps_mcp.common.output_schemas import SessionStartOutput

        checker_names = [
            c.get("name", "") if isinstance(c, dict) else getattr(c, "name", "")
            for c in info["data"].get("installed_checkers", [])
        ]
        structured = SessionStartOutput(
            server_version=info["data"]["server"].get("version", ""),
            project_root=info["data"]["configuration"].get("project_root", ""),
            project_type=None,
            quality_preset=info["data"]["configuration"].get("quality_preset", "standard"),
            installed_checkers=[n for n in checker_names if n],
            has_ci=False,
            has_docker=False,
            has_tests=False,
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        _logger.debug("structured_output_failed: tapps_session_start", exc_info=True)

    from tapps_mcp.server_helpers import mark_session_initialized

    mark_session_initialized(
        {
            "project_root": info["data"]["configuration"].get("project_root", ""),
            "quality_preset": info["data"]["configuration"].get("quality_preset", "standard"),
            "auto_initialized": False,
        }
    )

    return _with_nudges("tapps_session_start", resp, {})


async def _session_start_quick(
    start_ns: int,
    record_execution: Callable[..., None],
    with_nudges: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Quick session start: cached tool versions, no diagnostics or memory GC.

    Loads tool versions from disk cache (no subprocess calls). Skips
    diagnostics, memory GC, and contradiction checks.
    """
    from tapps_mcp import __version__
    from tapps_mcp.server import _bootstrap_cache_dir, _cache_info_dict
    from tapps_mcp.tools.tool_detection import detect_installed_tools

    settings = load_settings()

    # Story 75.3: Auto-create cache directory for faster subsequent starts
    cache_dir, cache_fallback = _bootstrap_cache_dir(settings.project_root)

    # Load tools from cache only (disk cache -> memory cache, no subprocesses if cached)
    installed = detect_installed_tools()

    elapsed_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
    record_execution("tapps_session_start", start_ns)

    hive_status: dict[str, Any] = initial_session_hive_status()
    try:
        hive_status = collect_session_hive_status(settings)
    except Exception:
        _logger.debug("hive_status_check_failed_quick", exc_info=True)

    checklist_sid_q: str | None = None
    try:
        from tapps_mcp.tools.checklist import CallTracker

        checklist_sid_q = CallTracker.get_active_checklist_session_id()
    except ImportError:
        pass

    data: dict[str, Any] = {
        "project_root": str(settings.project_root),
        "server": {
            "name": "TappsMCP",
            "version": __version__,
            "protocol_version": "2025-11-25",
        },
        "configuration": {
            "project_root": str(settings.project_root),
            "quality_preset": settings.quality_preset,
            "log_level": settings.log_level,
        },
        "installed_checkers": [t.model_dump() for t in installed],
        "checker_environment": "mcp_server",
        "checker_environment_note": (
            "Checker availability reflects the MCP server process environment. "
            "Target project may have different tools installed."
        ),
        "docs_provider": _current_docs_provider(),
        "cache": _cache_info_dict(cache_dir, cache_fallback),
        "quick": True,
        "checklist_session_id": checklist_sid_q,
        "hive_status": hive_status,
        "recommended_next": (
            "Quick session started (diagnostics skipped). "
            "Call tapps_session_start() without quick=True for full diagnostics."
        ),
    }

    resp = success_response("tapps_session_start", elapsed_ms, data)

    # Attach structured output
    try:
        from tapps_mcp.common.output_schemas import SessionStartOutput

        checker_names = [t.name for t in installed if t.available]
        structured = SessionStartOutput(
            server_version=__version__,
            project_root=str(settings.project_root),
            project_type=None,
            quality_preset=settings.quality_preset,
            installed_checkers=checker_names,
            has_ci=False,
            has_docker=False,
            has_tests=False,
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        _logger.debug("structured_output_failed: tapps_session_start_quick", exc_info=True)

    from tapps_mcp.server_helpers import mark_session_initialized

    mark_session_initialized(
        {
            "project_root": str(settings.project_root),
            "quality_preset": settings.quality_preset,
            "auto_initialized": False,
            "project_profile": None,
        }
    )

    return with_nudges("tapps_session_start", resp, {})


async def tapps_init(
    create_handoff: bool = True,
    create_runlog: bool = True,
    create_agents_md: bool = True,
    create_tech_stack_md: bool = True,
    platform: str = "",
    verify_server: bool = True,
    install_missing_checkers: bool = False,
    warm_cache_from_tech_stack: bool = False,
    warm_expert_rag_from_tech_stack: bool = False,
    overwrite_platform_rules: bool = False,
    overwrite_agents_md: bool = False,
    overwrite_tech_stack_md: bool = False,
    agent_teams: bool = False,
    memory_capture: bool = False,
    memory_auto_capture: bool = False,
    memory_auto_recall: bool = False,
    destructive_guard: bool | None = None,
    minimal: bool = False,
    dry_run: bool = False,
    verify_only: bool = False,
    llm_engagement_level: str | None = None,
    scaffold_experts: bool = False,
    mcp_config: bool = False,
    output_mode: str = "auto",
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Bootstrap TAPPS pipeline in the current project.

    Side effects: Writes files (AGENTS.md, TECH_STACK.md, platform rules, hooks,
    agents, skills). May create or merge ``.tapps-mcp.yaml`` on first run (memory
    pipeline + ``memory_hooks`` defaults follow shipped ``default.yaml`` unless
    overridden). Optionally warms caches. Call once per project.

    Verifies server info and optionally installs missing checkers (ruff, mypy,
    bandit, radon). Creates handoff, runlog, AGENTS.md, and TECH_STACK.md.
    Optionally warms the Context7 cache from the detected tech stack.
    Optionally generates platform-specific rule files for Claude Code or Cursor.

    On first run (no existing ``.claude/settings.json`` or ``.tapps-mcp.yaml``),
    an interactive 5-question wizard is presented via MCP elicitation (quality
    preset, engagement level, agent teams, skill tier, prompt hooks). Answers
    are persisted in ``.tapps-mcp.yaml``. The wizard is skipped when explicit
    parameters are provided or when the client does not support elicitation.

    Call once per project to set up the pipeline workflow.

    Duration: Full init can take 10-35+ seconds (profile, templates, cache/RAG
    warming). For timeout-prone MCP clients, use dry_run or verify_only first,
    or set warm_cache_from_tech_stack=False and warm_expert_rag_from_tech_stack=False
    for a faster init (~5-15s). See docs/MCP_CLIENT_TIMEOUTS.md for timeout guidance.

    Args:
        create_handoff: Create docs/TAPPS_HANDOFF.md template.
        create_runlog: Create docs/TAPPS_RUNLOG.md template.
        create_agents_md: Create AGENTS.md with AI assistant workflow (if missing).
        create_tech_stack_md: Create or update TECH_STACK.md from project profile.
        platform: Generate platform rules. One of: "claude", "cursor", "".
        verify_server: Verify server info and installed checkers.
        install_missing_checkers: Attempt to pip-install missing checkers (opt-in).
        warm_cache_from_tech_stack: Pre-fetch docs for tech stack libraries into cache.
        warm_expert_rag_from_tech_stack: Pre-build expert RAG indices for relevant domains.
        overwrite_platform_rules: When ``True``, refresh platform rule files even if
            they already exist (useful when templates are upgraded).
        overwrite_agents_md: When ``True``, replace AGENTS.md entirely with the latest
            template. When ``False`` (default), validate and smart-merge missing
            sections/tools.
        overwrite_tech_stack_md: When ``True``, overwrite an existing TECH_STACK.md
            with auto-detected content. When ``False`` (default), preserve any
            existing TECH_STACK.md (user-curated content is never lost).
        agent_teams: When ``True`` and platform is ``"claude"``, generate Agent Teams
            hooks (TeammateIdle, TaskCompleted) for quality watchdog teammate.
        memory_capture: When ``True`` and platform is ``"claude"``, generate a Stop
            hook that captures session quality data for memory persistence.
        memory_auto_recall: When ``True`` and platform is ``"claude"``, generate
            SessionStart/PreCompact hooks that inject relevant memories before
            agent prompt (Epic 65.4). Use ``memory_hooks.auto_recall.enabled`` in
            ``.tapps-mcp.yaml`` to enable.
        memory_auto_capture: When ``True`` and platform is ``"claude"``, generate a
            Stop hook that extracts durable facts from context and saves via
            MemoryStore (Epic 65.5).
        destructive_guard: When ``True``, add a PreToolUse hook that blocks Bash
            commands containing destructive patterns (rm -rf, format c:, etc.).
            When ``None``, uses value from settings. Default ``False``.
        minimal: When ``True``, create only AGENTS.md, TECH_STACK.md, platform rules,
            and MCP config. Skip hooks, skills, sub-agents, CI, governance, GitHub
            templates, handoff/runlog, and cache warming.
        dry_run: When ``True``, compute and return what would be created without
            writing files or warming caches. Keeps dry_run lightweight (~2-5s).
        verify_only: When ``True``, run only server verification and return (~1-3s).
            Use for quick connectivity/checker checks without creating files.
        llm_engagement_level: When set, use this level (high/medium/low) for
            AGENTS.md and platform rules. When ``None``, use config/settings.
        scaffold_experts: When ``True`` and ``.tapps-mcp/experts.yaml`` exists,
            scaffold missing knowledge directories for business experts
            (creates README.md and overview.md starter files).
        mcp_config: When ``True``, write project-scoped MCP server config after
            bootstrap completes. Always uses ``scope="project"`` (never user).
        output_mode: Controls file writing behavior (Epic 87).
            ``"auto"`` (default): detect automatically — writes files directly
            when the filesystem is writable, returns file contents as structured
            output when read-only (e.g. Docker container).
            ``"content_return"``: always return file contents without writing.
            ``"direct_write"``: always write files directly (error if read-only).
    """
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_init")

    # If context available, try elicitation confirmation (skip for verify_only/dry_run)
    if ctx is not None and not verify_only and not dry_run:
        from tapps_mcp.common.elicitation import elicit_init_confirmation

        settings_peek = load_settings()
        confirmed = await elicit_init_confirmation(ctx, str(settings_peek.project_root))
        if confirmed is False:
            elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
            _record_execution("tapps_init", start, status="cancelled")
            return success_response(
                "tapps_init",
                elapsed_ms,
                {"cancelled": True, "message": "tapps_init cancelled - no files were written."},
            )
        # confirmed is True or None (unsupported) - proceed normally

    # Interactive wizard (Epic 37.1): triggers on true first-run with no
    # explicit config and no explicit params, when elicitation is available.
    wizard_answers = None
    add_other_mcps_hint = False
    if ctx is not None and not verify_only and not dry_run:
        wizard_answers = await _maybe_run_wizard(
            ctx,
            llm_engagement_level=llm_engagement_level,
            platform=platform,
            agent_teams=agent_teams,
        )
        if wizard_answers is not None:
            llm_engagement_level = wizard_answers.engagement_level
            agent_teams = wizard_answers.agent_teams
            if not platform:
                platform = "claude"

    if wizard_answers is not None and wizard_answers.add_other_mcps:
        add_other_mcps_hint = True

    from tapps_mcp.pipeline.init import BootstrapConfig, bootstrap_pipeline

    settings = load_settings()
    dg = destructive_guard
    if dg is None:
        dg = getattr(settings, "destructive_guard", False)

    # Construct BootstrapConfig at the call site instead of forwarding
    # 18 kwargs individually (Story 67.4).
    cfg = BootstrapConfig(
        create_handoff=create_handoff,
        create_runlog=create_runlog,
        create_agents_md=create_agents_md,
        create_tech_stack_md=create_tech_stack_md,
        platform=platform,
        verify_server=verify_server,
        install_missing_checkers=install_missing_checkers,
        warm_cache_from_tech_stack=warm_cache_from_tech_stack,
        warm_expert_rag_from_tech_stack=warm_expert_rag_from_tech_stack,
        overwrite_platform_rules=overwrite_platform_rules,
        overwrite_agents_md=overwrite_agents_md,
        overwrite_tech_stack_md=overwrite_tech_stack_md,
        agent_teams=agent_teams,
        memory_capture=memory_capture,
        memory_auto_capture=memory_auto_capture,
        memory_auto_recall=memory_auto_recall,
        destructive_guard=dg,
        minimal=minimal,
        dry_run=dry_run,
        verify_only=verify_only,
        llm_engagement_level=llm_engagement_level or settings.llm_engagement_level,
        scaffold_experts=scaffold_experts,
    )

    # Epic 87: Set TAPPS_WRITE_MODE for content-return override
    import os as _os

    _prev_write_mode = _os.environ.get("TAPPS_WRITE_MODE", "")
    if output_mode == "content_return":
        _os.environ["TAPPS_WRITE_MODE"] = "content"
    elif output_mode == "direct_write":
        _os.environ["TAPPS_WRITE_MODE"] = "direct"
    # "auto" leaves the env var unchanged — detect_write_mode() probes the fs

    # Run in thread to avoid blocking the event loop - bootstrap_pipeline
    # is sync and may run subprocesses, file I/O, and cache warming.
    try:
        result = await asyncio.to_thread(
            bootstrap_pipeline,
            settings.project_root,
            config=cfg,
        )
    finally:
        # Restore env var
        if _prev_write_mode:
            _os.environ["TAPPS_WRITE_MODE"] = _prev_write_mode
        else:
            _os.environ.pop("TAPPS_WRITE_MODE", None)

    # Optional: write project-scoped MCP config (Epic 47.2)
    if mcp_config and not dry_run:
        from tapps_mcp.distribution.setup_generator import _generate_config

        mcp_host = "claude-code"
        if platform == "cursor":
            mcp_host = "cursor"
        elif platform == "vscode":
            mcp_host = "vscode"

        config_ok = _generate_config(
            mcp_host,
            settings.project_root,
            force=True,
            scope="project",
        )
        if config_ok:
            result["mcp_config_written"] = True
            result["mcp_config_scope"] = "project"

    # Emit ctx.info for each created file (Pattern 1: progress notifications)
    for filename in result.get("created", []):
        await emit_ctx_info(ctx, f"Created {filename}")

    # Emit ctx.info for warnings (Story 51.3)
    for warning in result.get("warnings", []):
        await emit_ctx_info(ctx, f"Warning: {warning}")

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution(
        "tapps_init",
        start,
        status="success" if not result["errors"] else "failed",
    )

    if add_other_mcps_hint:
        result["add_other_mcps_hint"] = (
            "See docs/MCP_COMPOSITION.md for guidance on adding GitHub, "
            "YouTube, Sentry, and other MCPs alongside TappsMCP."
        )
    result["agency_agents_hint"] = (
        "Optional: For more specialized agents (e.g. Frontend Developer, Reality Checker), "
        "see https://github.com/msitarzewski/agency-agents and run their install script for your platform."
    )
    result["consumer_requirements"] = (
        "For a full checklist of what you need to use most tools "
        "(server visibility, permissions, CLI fallback), "
        "see docs/TAPPS_MCP_REQUIREMENTS.md"
    )
    result["developer_workflow"] = get_developer_workflow_dict(
        setup_done=not result["errors"],
    )
    resp = success_response("tapps_init", elapsed_ms, result)
    resp["success"] = not result["errors"]
    return _with_nudges("tapps_init", resp)


async def tapps_upgrade(
    platform: str = "",
    force: bool = False,
    dry_run: bool = False,
    output_mode: str = "auto",
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Upgrade all TappsMCP-generated files after a version update.

    Side effects: Overwrites AGENTS.md, platform rules, hooks, agents, skills.
    Creates a timestamped backup first (.tapps-mcp/backups/). Use dry_run=True
    to preview without writing.

    Validates and refreshes AGENTS.md, platform rules, hooks, agents,
    skills, and settings. Preserves custom command paths in MCP configs
    (e.g. PyInstaller exe paths are never overwritten).

    Creates a timestamped backup of all files that will be overwritten
    before making changes. Backups are stored in ``.tapps-mcp/backups/``
    and can be restored with ``tapps-mcp rollback`` (CLI) or
    ``tapps-mcp rollback --list`` to view available backups.

    Use ``dry_run=True`` to preview what would change. After upgrading TappsMCP, compare
    your ``.tapps-mcp.yaml`` to ``packages/tapps-mcp/src/tapps_mcp/config/default.yaml``
    if you depend on explicit opt-out flags for memory or hooks.

    Args:
        platform: Target platform - "claude", "cursor", "both", or "" for auto-detection.
        force: If True, overwrite all generated files without prompting.
        dry_run: If True, show what would be updated without making changes.
        output_mode: Controls file writing behavior (Epic 87).
            ``"auto"`` (default): detect automatically — writes files directly
            when the filesystem is writable, returns file contents as structured
            output when read-only (e.g. Docker container).
            ``"content_return"``: always return file contents without writing.
            ``"direct_write"``: always write files directly (error if read-only).
    """
    from tapps_mcp.pipeline.upgrade import upgrade_pipeline
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_upgrade")

    settings = load_settings()

    if not dry_run:
        await emit_ctx_info(ctx, "Creating backup...")

    # Epic 87: Set TAPPS_WRITE_MODE for content-return override
    import os as _os

    _prev_write_mode = _os.environ.get("TAPPS_WRITE_MODE", "")
    if output_mode == "content_return":
        _os.environ["TAPPS_WRITE_MODE"] = "content"
    elif output_mode == "direct_write":
        _os.environ["TAPPS_WRITE_MODE"] = "direct"
    # "auto" leaves the env var unchanged — detect_write_mode() probes the fs

    try:
        result = upgrade_pipeline(
            settings.project_root,
            platform=platform,
            force=force,
            dry_run=dry_run,
        )
    finally:
        # Restore env var
        if _prev_write_mode:
            _os.environ["TAPPS_WRITE_MODE"] = _prev_write_mode
        else:
            _os.environ.pop("TAPPS_WRITE_MODE", None)

    # Emit ctx.info for upgraded components (skip in dry_run mode)
    if not dry_run:
        components = result.get("components", {})
        agents_md = components.get("agents_md", {})
        if isinstance(agents_md, dict):
            action = agents_md.get("action", "")
            if action in ("created", "merged", "updated"):
                await emit_ctx_info(ctx, f"Updated AGENTS.md ({action})")
        for plat_result in components.get("platforms", []):
            host = plat_result.get("host", "unknown")
            for comp_name, comp_val in plat_result.get("components", {}).items():
                if (isinstance(comp_val, str) and comp_val in ("created", "updated", "regenerated")) or (isinstance(comp_val, dict) and comp_val.get("action") in (
                    "created",
                    "updated",
                    "regenerated",
                )):
                    await emit_ctx_info(ctx, f"Updated {host}/{comp_name}")

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution(
        "tapps_upgrade",
        start,
        status="success" if result.get("success") else "failed",
    )

    resp = success_response("tapps_upgrade", elapsed_ms, result)
    return _with_nudges("tapps_upgrade", resp)


def tapps_set_engagement_level(level: str) -> dict[str, Any]:
    """Set the LLM engagement level (high / medium / low) for the project.

    Side effects: Writes ``llm_engagement_level`` to ``.tapps-mcp.yaml``. Run
    tapps_init(overwrite_agents_md=True) afterward to regenerate AGENTS.md.

    Writes or updates ``llm_engagement_level`` in the project's ``.tapps-mcp.yaml``.
    Use when the user asks to change enforcement intensity (e.g. \"set tappsmcp to high\"
    or \"make quality checks optional\").

    Args:
        level: One of ``\"high\"`` (mandatory), ``\"medium\"`` (balanced),
            ``\"low\"`` (optional guidance).
    """
    import yaml

    from tapps_core.security.path_validator import PathValidator
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_set_engagement_level")

    valid = ("high", "medium", "low")
    if level not in valid:
        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        _record_execution("tapps_set_engagement_level", start, status="failed")
        return error_response(
            "tapps_set_engagement_level",
            "invalid_level",
            f"Invalid level {level!r}. Use one of: {', '.join(valid)}",
        )

    settings = load_settings()
    root = Path(settings.project_root)
    validator = PathValidator(root)
    config_path = validator.validate_write_path(".tapps-mcp.yaml")

    data: dict[str, Any] = {}
    if config_path.exists():
        try:
            with config_path.open(encoding="utf-8-sig") as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
            _record_execution("tapps_set_engagement_level", start, status="failed")
            return error_response(
                "tapps_set_engagement_level",
                "config_read_error",
                f"Could not read existing .tapps-mcp.yaml: {e}",
            )
    if not isinstance(data, dict):
        data = {}

    data["llm_engagement_level"] = level

    # Epic 87: content-return mode for Docker/read-only
    from tapps_core.common.file_operations import WriteMode, detect_write_mode

    write_mode = detect_write_mode(root)
    yaml_content = yaml.dump(data, default_flow_style=False, sort_keys=False)

    if write_mode == WriteMode.DIRECT_WRITE:
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with config_path.open("w", encoding="utf-8") as f:
                f.write(yaml_content)
        except OSError as e:
            elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
            _record_execution("tapps_set_engagement_level", start, status="failed")
            return error_response(
                "tapps_set_engagement_level",
                "config_write_error",
                f"Could not write .tapps-mcp.yaml: {e}",
            )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_set_engagement_level", start)

    next_step = (
        "Run tapps_init with overwrite_agents_md=True (and platform if needed) "
        "to regenerate AGENTS.md and platform rules with the new level."
    )
    msg = f"Engagement level set to {level!r}. {next_step}"
    result_data: dict[str, Any] = {"level": level, "message": msg}

    if write_mode == WriteMode.CONTENT_RETURN:
        from tapps_core.common.file_operations import (
            AgentInstructions,
            FileManifest,
            FileOperation,
        )

        manifest = FileManifest(
            summary=f"Set engagement level to {level}",
            source_version=settings.version if hasattr(settings, "version") else "",
            files=[
                FileOperation(
                    path=".tapps-mcp.yaml",
                    content=yaml_content,
                    mode="overwrite",
                    description="TappsMCP config with updated engagement level.",
                    priority=1,
                ),
            ],
            agent_instructions=AgentInstructions(
                persona=(
                    "You are a configuration assistant. Write the config "
                    "file exactly as provided."
                ),
                tool_preference="Use the Write tool to overwrite .tapps-mcp.yaml.",
                verification_steps=[
                    "Verify .tapps-mcp.yaml contains the expected engagement level.",
                ],
                warnings=[
                    "Config changes affect all subsequent tool behavior.",
                ],
            ),
        )
        result_data["content_return"] = True
        result_data["file_manifest"] = manifest.to_full_response_data()

    resp = success_response(
        "tapps_set_engagement_level",
        elapsed_ms,
        result_data,
    )
    return _with_nudges("tapps_set_engagement_level", resp)


def tapps_doctor(
    project_root: str = "",
    quick: bool = False,
) -> dict[str, Any]:
    """Diagnose TappsMCP configuration and connectivity.

    Checks binary availability, MCP configs, platform rules, generated
    files (AGENTS.md, settings), hooks, installed quality tools, tapps-brain,
    and an informational **Memory pipeline (effective config)** row (resolved
    ``memory.*`` and ``memory_hooks.*`` flags).

    Returns structured results with per-check pass/fail status and
    remediation hints for any failures.

    Args:
        project_root: Project root path (default: server's configured root).
        quick: When True, skip tool version checks for faster results.
    """
    from tapps_mcp.distribution.doctor import run_doctor_structured
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_doctor")

    settings = load_settings()
    root = project_root or str(settings.project_root)

    result = run_doctor_structured(project_root=root, quick=quick)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_doctor", start)

    resp = success_response("tapps_doctor", elapsed_ms, result)
    return _with_nudges("tapps_doctor", resp)


async def tapps_pipeline(
    file_paths: str = "",
    task_type: str = "feature",
    preset: str = "standard",
    skip_session_start: bool = False,
) -> dict[str, Any]:
    """One-call orchestrator for the full TappsMCP quality pipeline (STORY-101.2).

    Collapses the recommended edit → check → validate → done loop into a
    single tool call. Executes, in order:

    1. ``tapps_session_start`` (skipped if already initialized in-session
       or ``skip_session_start=True``)
    2. ``tapps_quick_check`` (batch mode) on ``file_paths``
    3. ``tapps_validate_changed`` on the same paths
    4. ``tapps_checklist`` for ``task_type``

    Short-circuits on a security floor failure from quick_check — no point
    running validate_changed if security is already failing below 50.

    Args:
        file_paths: Comma-separated file paths to check. Required.
        task_type: feature | bugfix | refactor | security | review | epic.
        preset: Quality gate preset — "standard", "strict", or "framework".
        skip_session_start: Skip session_start even if not initialized
            (for scripted CI callers that already ran it).

    Returns:
        Unified envelope with a ``stages`` array, each entry carrying
        ``name``, ``success``, ``elapsed_ms``, and a compact ``summary``.
        ``pipeline_passed`` is True only when every stage succeeded and no
        short-circuit fired.
    """
    from tapps_mcp.server import _record_call
    from tapps_mcp.server_helpers import ensure_session_initialized
    from tapps_mcp.server_scoring_tools import tapps_quick_check

    start = time.perf_counter_ns()
    _record_call("tapps_pipeline")

    if not file_paths.strip():
        return error_response(
            "tapps_pipeline",
            "NO_FILE_PATHS",
            "tapps_pipeline requires file_paths — pass comma-separated paths.",
        )

    stages: list[dict[str, Any]] = []
    pipeline_passed = True
    short_circuit: str | None = None

    # Stage 1 — session_start (cheap if already initialized).
    if not skip_session_start:
        stage_start = time.perf_counter_ns()
        try:
            await ensure_session_initialized()
            stages.append({
                "name": "session_start",
                "success": True,
                "elapsed_ms": (time.perf_counter_ns() - stage_start) // 1_000_000,
                "summary": "session initialized",
            })
        except Exception as exc:
            pipeline_passed = False
            stages.append({
                "name": "session_start",
                "success": False,
                "elapsed_ms": (time.perf_counter_ns() - stage_start) // 1_000_000,
                "summary": f"session_start failed: {exc}",
            })

    # Stage 2 — quick_check (batch).
    stage_start = time.perf_counter_ns()
    qc_resp = await tapps_quick_check(
        file_path="", preset=preset, fix=False, file_paths=file_paths,
    )
    qc_data = qc_resp.get("data", {}) if isinstance(qc_resp, dict) else {}
    qc_passed = bool(qc_resp.get("success")) and not qc_data.get("security_floor_failed")
    stages.append({
        "name": "quick_check",
        "success": qc_passed,
        "elapsed_ms": (time.perf_counter_ns() - stage_start) // 1_000_000,
        "summary": _summarize_quick_check(qc_data),
    })
    if not qc_passed:
        pipeline_passed = False
    if qc_data.get("security_floor_failed"):
        short_circuit = "security_floor_failed"

    # Stage 3 — validate_changed (skipped on security short-circuit).
    if short_circuit is None:
        stage_start = time.perf_counter_ns()
        vc_resp = await tapps_validate_changed(file_paths=file_paths, preset=preset)
        vc_data = vc_resp.get("data", {}) if isinstance(vc_resp, dict) else {}
        vc_passed = bool(vc_resp.get("success")) and bool(vc_data.get("all_passed", False))
        stages.append({
            "name": "validate_changed",
            "success": vc_passed,
            "elapsed_ms": (time.perf_counter_ns() - stage_start) // 1_000_000,
            "summary": (
                f"{vc_data.get('passed_count', 0)} passed / "
                f"{vc_data.get('failed_count', 0)} failed"
            ),
        })
        if not vc_passed:
            pipeline_passed = False
    else:
        stages.append({
            "name": "validate_changed",
            "success": False,
            "elapsed_ms": 0,
            "summary": f"skipped ({short_circuit})",
        })
        pipeline_passed = False

    # Stage 4 — checklist (always runs, even on failure, for the report).
    stage_start = time.perf_counter_ns()
    try:
        from tapps_mcp.server import tapps_checklist

        cl_resp = await tapps_checklist(task_type=task_type, output_format="compact")
        cl_data = cl_resp.get("data", {}) if isinstance(cl_resp, dict) else {}
        cl_passed = bool(cl_resp.get("success")) and not cl_data.get("missing")
        stages.append({
            "name": "checklist",
            "success": cl_passed,
            "elapsed_ms": (time.perf_counter_ns() - stage_start) // 1_000_000,
            "summary": cl_data.get("compact_summary") or str(cl_data.get("status", "")),
        })
        if not cl_passed:
            pipeline_passed = False
    except Exception as exc:
        pipeline_passed = False
        stages.append({
            "name": "checklist",
            "success": False,
            "elapsed_ms": (time.perf_counter_ns() - stage_start) // 1_000_000,
            "summary": f"checklist failed: {exc}",
        })

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    data: dict[str, Any] = {
        "pipeline_passed": pipeline_passed,
        "short_circuit": short_circuit,
        "stages": stages,
        "task_type": task_type,
        "file_paths": file_paths,
    }
    return success_response("tapps_pipeline", elapsed_ms, data)


def _summarize_quick_check(qc_data: dict[str, Any]) -> str:
    """Compact one-line summary of a quick_check response."""
    if "batch" in qc_data:
        batch = qc_data["batch"]
        return (
            f"{batch.get('passed_count', 0)} passed / "
            f"{batch.get('failed_count', 0)} failed"
        )
    score = qc_data.get("score") or qc_data.get("overall_score")
    return f"score={score}" if score is not None else "ok"


def register(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register pipeline/validation tools on *mcp_instance* (Epic 79.1: conditional)."""
    if "tapps_validate_changed" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_validate_changed)
    if "tapps_session_start" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(tapps_session_start)
    if "tapps_init" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(tapps_init)
    if "tapps_set_engagement_level" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(tapps_set_engagement_level)
    if "tapps_upgrade" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(tapps_upgrade)
    if "tapps_doctor" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_doctor)
    if "tapps_pipeline" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_pipeline)
