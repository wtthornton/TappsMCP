"""Output-shaping helpers for validate_changed.

Extracted from ``validate_changed.py`` to keep that module under the
800-line budget. TAP-2468 added the response-data assembly, judge
invocation, and timeout-hint helpers that were previously in
``validate_changed.py``.
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
    except Exception:
        _logger.debug("impact_analysis_failed", exc_info=True)
        return {"error": "impact analysis failed"}
    return {
        "max_severity": max_severity,
        "total_affected_files": total_affected,
        "per_file": impact_results,
    }


def _compute_affected_tests(
    paths: list[Path],
    project_root: Path,
    *,
    limit: int = 20,
) -> dict[str, Any] | None:
    """Rank tests affected by changed Python source files (Epic 114 / TAP-4054)."""
    from tapps_mcp.project.diff_impact import DEFAULT_AFFECTED_TESTS_LIMIT, analyze_diff_impact
    from tapps_mcp.project.impact_analyzer import _is_test_file

    py_sources = [
        p for p in paths if p.suffix in {".py", ".pyi"} and p.exists() and not _is_test_file(p)
    ]
    if not py_sources:
        return None
    cap = max(1, limit if limit > 0 else DEFAULT_AFFECTED_TESTS_LIMIT)
    try:
        data = analyze_diff_impact(py_sources, project_root, max_tests=cap)
        return {
            "total_affected_tests": data.get("total_affected_tests", 0),
            "affected_tests": list(data.get("affected_tests", [])),
            "max_tests": data.get("max_tests", cap),
            "degraded": bool(data.get("degraded")),
        }
    except Exception:
        _logger.debug("affected_tests_analysis_failed", exc_info=True)
        return {"error": "affected tests analysis failed"}


def _compute_diff_impact(
    paths: list[Path],
    project_root: Path,
) -> dict[str, Any] | None:
    """Per-changed-symbol callers + ranked affected tests (TAP-4526).

    Deterministic reuse of the cached call graph. Degrades gracefully (a
    ``degraded`` block with a ``note``) when the cache is missing or stale —
    never raises. Only source (non-test) Python files are enriched.
    """
    from tapps_mcp.project.diff_impact import build_diff_impact_enrichment
    from tapps_mcp.project.impact_analyzer import _is_test_file

    py_sources = [
        p for p in paths if p.suffix in {".py", ".pyi"} and p.exists() and not _is_test_file(p)
    ]
    if not py_sources:
        return None
    try:
        return build_diff_impact_enrichment(py_sources, project_root)
    except Exception:
        _logger.debug("diff_impact_enrichment_failed", exc_info=True)
        return {
            "degraded": True,
            "note": "diff-impact enrichment failed",
            "symbols": {},
        }


def _compute_blast_radius_caveat(
    paths: list[Path],
    project_root: Path,
) -> dict[str, Any] | None:
    """Derive an incomplete-blast-radius caveat from call-graph health (TAP-4528).

    Deterministic reuse of ``summarize_call_graph_cache`` — no new analysis pass,
    no network / LLM (ADR-0004). Returns ``None`` for a healthy / low-gap region
    (no false alarms) and a machine-readable caveat dict (with a human-readable
    ``note``) when the call graph is materially incomplete. Only relevant when
    source (non-test) Python files are in the change set.
    """
    from tapps_mcp.project.diff_impact import build_blast_radius_caveat
    from tapps_mcp.project.impact_analyzer import _is_test_file

    py_sources = [
        p for p in paths if p.suffix in {".py", ".pyi"} and p.exists() and not _is_test_file(p)
    ]
    if not py_sources:
        return None
    try:
        return build_blast_radius_caveat(project_root)
    except Exception:
        _logger.debug("blast_radius_caveat_failed", exc_info=True)
        return None


def attach_blast_radius_caveat(
    resp_data: dict[str, Any],
    caveat: dict[str, Any] | None,
) -> None:
    """Attach a top-level ``blast_radius_caveat`` when the call graph is degraded.

    Absent when healthy (``caveat is None``) so low-gap reviews stay clean
    (TAP-4528). Sits beside ``diff_impact`` on the review verdict.
    """
    if caveat is not None:
        resp_data["blast_radius_caveat"] = caveat


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
                security_passed=r.get("security_passed", False),
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


def _build_file_entry(
    r: dict[str, Any],
    *,
    near_miss_slots_remaining: int,
) -> tuple[dict[str, Any], str, int]:
    """Build a single per-file entry and grep-friendly row."""
    file_path = r.get("file_path", r.get("file", "unknown"))
    file_name = Path(file_path).name if file_path != "unknown" else "unknown"
    gate_passed = r.get("gate_passed", False)
    score = r.get("score", r.get("overall_score", 0.0))
    security_issues = r.get("security_issues", 0)
    errors = r.get("errors", [])
    lint_issues = r.get("lint_issues") or []

    status = "PASS" if gate_passed and not errors else "FAIL"
    security_status = "fail" if security_issues > 0 else "pass"
    issue_count = len(errors) + security_issues + len(lint_issues)

    entry: dict[str, Any] = {
        "file": file_name,
        "file_path": str(file_path),
        "status": status,
        "score": round(float(score if score is not None else 0.0), 1),
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

    from tapps_mcp.tools.validate_changed_diagnostics import enrich_file_entry

    remaining = enrich_file_entry(
        entry,
        row_parts,
        r,
        near_miss_slots_remaining=near_miss_slots_remaining,
    )
    return entry, "  ".join(row_parts), remaining


def _build_per_file_results(
    results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build machine-readable per-file results and grep-friendly summary rows."""
    from tapps_mcp.tools.validate_changed_diagnostics import _MAX_NEAR_MISS_FILES

    per_file: list[dict[str, Any]] = []
    rows: list[str] = []
    near_miss_slots = _MAX_NEAR_MISS_FILES
    for r in results:
        entry, row, near_miss_slots = _build_file_entry(
            r,
            near_miss_slots_remaining=near_miss_slots,
        )
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
            "Auto-detect already checks unstaged, staged (--cached), and "
            "untracked scorable files. Pass explicit file_paths=... or a "
            "different base_ref (e.g. base_ref='main') if you expected "
            "committed-on-branch changes."
        )
    return warnings


async def _handle_no_changed_files(
    start: int,
    settings: TappsMCPSettings,
    record_execution: Callable[..., object],
    with_nudges: Callable[..., dict[str, object]],
    *,
    explicit_paths: bool = False,
    base_ref: str = "HEAD",
    correlation_id: str = "",
    judges: list[dict[str, Any]] | None = None,
    project_root_override: bool = False,
) -> dict[str, Any]:
    """Return early response when no changed scorable files are found."""
    from tapps_mcp import server_pipeline_tools as _host

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    def _deferred_record() -> None:
        record_execution("tapps_validate_changed", start)

    task = asyncio.create_task(asyncio.to_thread(_deferred_record))
    _host._background_tasks.add(task)
    task.add_done_callback(_host._background_tasks.discard)

    resp_data: dict[str, Any] = {
        "files_validated": 0,
        "all_gates_passed": False,
        "total_security_issues": 0,
        "results": [],
        "summary": "No changed scorable files found — inconclusive, nothing was gated.",
    }

    summary = resp_data["summary"]
    if judges:
        judge_payload = await _run_judges(
            judges,
            settings.project_root,
            changed_paths=None,
            base_ref=base_ref,
        )
        summary = apply_judge_payload(resp_data, judge_payload, summary=summary)

    warnings = _no_changed_warnings(explicit_paths, base_ref)
    if explicit_paths:
        if project_root_override:
            resp_data["path_hint"] = (
                "Explicit paths provided but none validated under the "
                "project_root override. Paths must be repo-relative to "
                "project_root, not the MCP host workspace. When the MCP host "
                "maps consumer repo paths, set TAPPS_MCP_HOST_PROJECT_ROOT on "
                "the server."
            )
            resp_data["next_steps"] = [
                "FALLBACK: Use tapps_quick_check on individual files with the same project_root.",
                f'Example: tapps_validate_changed(file_paths="packages/foo/src/bar.py", '
                f'project_root="{settings.project_root}")',
            ]
        else:
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


def _build_response_data(
    results: list[dict[str, Any]],
    all_passed: bool,
    total_sec: int,
    per_file_results: list[dict[str, Any]],
    summary_rows: list[str],
    summary: str,
    impact_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """Assemble the base response data dict for tapps_validate_changed."""
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
    return resp_data


def attach_affected_tests(
    resp_data: dict[str, Any],
    affected_tests_data: dict[str, Any] | None,
) -> None:
    """Add optional affected_tests block when diff-impact ranking is available."""
    if affected_tests_data is not None:
        resp_data["affected_tests"] = affected_tests_data


def attach_diff_impact(
    resp_data: dict[str, Any],
    diff_impact_data: dict[str, Any] | None,
) -> None:
    """Add optional per-symbol diff_impact block (callers + affected tests, TAP-4526)."""
    if diff_impact_data is not None:
        resp_data["diff_impact"] = diff_impact_data


def _build_judge_summary_rows(judge_results: list[dict[str, Any]]) -> list[str]:
    """Build grep-friendly PASS/FAIL rows for post-gate judges."""
    rows: list[str] = []
    for item in judge_results:
        outcome = str(item.get("result", "error"))
        status = "PASS" if outcome == "pass" else "SKIP" if outcome == "skipped" else "FAIL"
        label = str(item.get("judge", item.get("type", "judge")))
        short = label if len(label) <= 40 else f"{label[:37]}..."
        message = str(item.get("message", ""))
        row = f"{status:<5}  judge:{short:<40}  {outcome}"
        if message and status == "FAIL":
            row = f"{row}  {message[:80]}"
        rows.append(row)
    return rows


def _append_judge_summary(summary: str, judge_results: list[dict[str, Any]]) -> str:
    """Append judge pass/fail counts to the human-readable summary."""
    if not judge_results:
        return summary
    passed = sum(1 for r in judge_results if r.get("result") == "pass")
    failed = sum(
        1 for r in judge_results if r.get("result") in {"fail", "error"} and r.get("blocking")
    )
    skipped = sum(1 for r in judge_results if r.get("result") == "skipped")
    suffix = f" | judges: {passed} passed"
    if failed:
        suffix += f", {failed} blocking failed"
    if skipped:
        suffix += f", {skipped} skipped"
    return f"{summary}{suffix}"


def apply_judge_payload(
    resp_data: dict[str, Any],
    judge_payload: dict[str, Any],
    *,
    summary: str,
) -> str:
    """Fold judge results into response data and return updated summary."""
    resp_data.update(judge_payload)
    judge_results = list(judge_payload.get("judge_results") or [])
    if judge_results:
        resp_data["summary_rows"] = [
            *list(resp_data.get("summary_rows") or []),
            *_build_judge_summary_rows(judge_results),
        ]
        summary = _append_judge_summary(summary, judge_results)
        resp_data["summary"] = summary
    if not judge_payload.get("judges_passed", True):
        resp_data["all_gates_passed"] = False
    return summary


async def _run_judges(
    judges: list[dict[str, Any]],
    project_root: Path,
    *,
    changed_paths: list[str] | None = None,
    base_ref: str = "HEAD",
) -> dict[str, Any]:
    """Invoke judges and return the judge-result payload."""
    try:
        from tapps_core.metrics.judge import run_judges

        return await run_judges(
            judges,
            cwd=project_root,
            changed_paths=changed_paths,
            base_ref=base_ref,
        )
    except Exception as exc:
        _logger.debug("judge_run_failed", exc_info=True)
        return {
            "judge_results": [
                {
                    "judge": "judge runner",
                    "type": "shell",
                    "result": "error",
                    "message": str(exc),
                    "blocking": True,
                }
            ],
            "judges_passed": False,
        }


def _append_timeout_hint(
    resp: dict[str, Any],
    files_remaining: list[Path],
) -> None:
    """Inject an auto-detect-budget hint into the response's next_steps."""
    from tapps_mcp import server_pipeline_tools as _host

    data = resp.get("data", {})
    sample = ",".join(str(p) for p in files_remaining[:10])
    hint = (
        f"Auto-detect exceeded {_host._AUTO_DETECT_BUDGET_S:.0f}s budget with "
        f"{len(files_remaining)} files unvalidated. Finish with explicit "
        f'paths: tapps_validate_changed(file_paths="{sample}")'
    )
    existing = list(data.get("next_steps") or [])
    data["next_steps"] = [hint, *existing][:5]


__all__ = [
    "_SEVERITY_RANK",
    "_append_judge_summary",
    "_append_timeout_hint",
    "_build_file_entry",
    "_build_judge_summary_rows",
    "_build_per_file_results",
    "_build_response_data",
    "_build_structured_validation_output",
    "_build_validation_summary",
    "_compute_affected_tests",
    "_compute_blast_radius_caveat",
    "_compute_impact_analysis",
    "_handle_no_changed_files",
    "_resolve_security_depth",
    "_run_judges",
    "apply_judge_payload",
    "attach_affected_tests",
    "attach_blast_radius_caveat",
]
