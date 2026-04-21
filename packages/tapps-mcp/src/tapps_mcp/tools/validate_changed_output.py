"""Output-shaping helpers for validate_changed.

Extracted from ``validate_changed.py`` to keep that module under the
800-line budget.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from tapps_mcp.server_helpers import success_response

if TYPE_CHECKING:
    from collections.abc import Callable

    from tapps_core.config.settings import TappsMCPSettings

_logger = structlog.get_logger(__name__)

# Severity ranking for impact analysis aggregation.
_SEVERITY_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}


def _impact_entry_for_path(p: Path, project_root: Path, import_graph: Any) -> dict[str, Any]:
    """Compute the per-file impact entry for one path."""
    from tapps_mcp.project.impact_analyzer import analyze_impact

    try:
        impact_report = analyze_impact(p, project_root, graph=import_graph)
        return {
            "file": str(p),
            "severity": impact_report.severity,
            "direct_dependents": len(impact_report.direct_dependents),
            "transitive_dependents": len(impact_report.transitive_dependents),
            "test_files": len(impact_report.test_files),
        }
    except Exception:
        _logger.debug("impact_analysis_file_failed", file=str(p), exc_info=True)
        return {"file": str(p), "severity": "unknown", "error": True}


def _compute_impact_analysis(
    paths: list[Path],
    project_root: Path,
) -> dict[str, Any] | None:
    """Build impact analysis data for the given file paths.

    Returns a summary dict or ``None`` if impact analysis is not requested.
    On failure, returns ``{"error": "impact analysis failed"}``.
    """
    try:
        from tapps_mcp.project.impact_analyzer import build_import_graph

        import_graph = build_import_graph(project_root)
        impact_results = [_impact_entry_for_path(p, project_root, import_graph) for p in paths]

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


def _resolve_security_depth(security_depth: str, include_security: bool, quick: bool) -> bool:
    """Determine whether to run full security scanning."""
    return (security_depth == "full") or (include_security and not quick)


def _build_file_entry(r: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Build a single per-file entry and grep-friendly row."""
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

    row_parts = [
        f"{status:<5}",
        f"{file_name:<30}",
        f"score={entry['score']:.1f}",
        f"gate={'pass' if gate_passed else 'fail'}",
        f"security={security_status}",
    ]
    if issue_count > 0:
        row_parts.append(f"issues={issue_count}")
    return entry, "  ".join(row_parts)


def _build_per_file_results(
    results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build machine-readable per-file results and grep-friendly summary rows."""
    per_file: list[dict[str, Any]] = []
    rows: list[str] = []
    for r in results:
        entry, row = _build_file_entry(r)
        per_file.append(entry)
        rows.append(row)
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


def _no_changed_warnings(
    explicit_paths: bool,
    base_ref: str,
) -> list[str]:
    """Return warnings for the no-changed-files response."""
    warnings: list[str] = []
    if not explicit_paths and base_ref.strip().upper() == "HEAD":
        warnings.append(
            "Zero changed files detected with base_ref=HEAD. "
            "If you have staged-but-uncommitted changes, diff against HEAD "
            "will not include them. Consider committing first or using a "
            "different base_ref (e.g. base_ref='HEAD~1')."
        )
    return warnings


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
    from tapps_mcp import server_pipeline_tools as _host

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    def _deferred_record() -> None:
        record_execution("tapps_validate_changed", start)

    task = asyncio.create_task(asyncio.to_thread(_deferred_record))
    _host._background_tasks.add(task)
    task.add_done_callback(_host._background_tasks.discard)

    _host._write_validate_ok_marker(settings.project_root)

    resp_data: dict[str, Any] = {
        "files_validated": 0,
        "all_gates_passed": True,
        "total_security_issues": 0,
        "results": [],
        "summary": "No changed scorable files found.",
    }

    warnings = _no_changed_warnings(explicit_paths, base_ref)
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


__all__ = [
    "_SEVERITY_RANK",
    "_build_file_entry",
    "_build_per_file_results",
    "_build_structured_validation_output",
    "_build_validation_summary",
    "_compute_impact_analysis",
    "_handle_no_changed_files",
    "_resolve_security_depth",
]
