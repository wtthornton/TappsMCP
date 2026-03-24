"""Scoring and quality-gate tool handlers for TappsMCP.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:`register`.
"""

from __future__ import annotations

import ast
import asyncio
import structlog
import time
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import (
    Context,
)
from mcp.types import ToolAnnotations

from tapps_core.config.settings import load_settings
from tapps_mcp.quick_check_recurring import record_quick_check_recurring
from tapps_mcp.server_helpers import (
    _get_scorer,
    _get_scorer_for_file,
    _is_scorable_file,
    ensure_session_initialized,
    error_response,
    serialize_issues,
    success_response,
)

if TYPE_CHECKING:
    from pathlib import Path

    from mcp.server.fastmcp import FastMCP

    from tapps_mcp.gates.models import GateResult
    from tapps_mcp.scoring.models import ScoreResult
    from tapps_mcp.security.security_scanner import SecurityScanResult

_ANNOTATIONS_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

logger = structlog.get_logger(__name__)

# Complexity thresholds for AST heuristic
_CC_MODERATE_THRESHOLD = 10
_CC_HIGH_THRESHOLD = 15


def _build_score_file_data(
    result: ScoreResult,
    quick: bool,
    fix: bool,
    fixes_applied: int,
) -> tuple[dict[str, Any], list[str]]:
    """Build the response data dict and suggestions list for score_file."""
    all_suggestions: list[str] = []
    for cat in result.categories.values():
        all_suggestions.extend(cat.suggestions)

    data: dict[str, Any] = {
        "file_path": result.file_path,
        "overall_score": round(result.overall_score, 2),
        "categories": {
            name: {
                "score": round(cat.score, 2),
                "weight": cat.weight,
                "details": cat.details,
                "suggestions": cat.suggestions,
            }
            for name, cat in result.categories.items()
        },
        "suggestions": all_suggestions,
        "lint_issue_count": len(result.lint_issues),
        "type_issue_count": len(result.type_issues),
        "security_issue_count": len(result.security_issues),
    }

    if quick and fix:
        data["fixes_applied"] = fixes_applied
    if result.lint_issues:
        data["lint_issues"] = serialize_issues(result.lint_issues)
    if result.type_issues:
        data["type_issues"] = serialize_issues(result.type_issues)
    if result.security_issues:
        data["security_issues"] = serialize_issues(result.security_issues)
    if result.tool_errors:
        data["tool_errors"] = result.tool_errors

    return data, all_suggestions


def _attach_score_file_structured_output(
    resp: dict[str, Any],
    result: ScoreResult,
    all_suggestions: list[str],
) -> None:
    """Attach structured output to the score_file response in-place."""
    try:
        from tapps_mcp.common.output_schemas import CategoryScoreOutput, ScoreFileOutput

        structured = ScoreFileOutput(
            file_path=result.file_path,
            overall_score=round(result.overall_score, 2),
            categories={
                name: CategoryScoreOutput(
                    name=name,
                    score=round(cat.score, 2),
                    weight=cat.weight,
                    suggestions=cat.suggestions,
                )
                for name, cat in result.categories.items()
            },
            lint_issue_count=len(result.lint_issues),
            type_issue_count=len(result.type_issues),
            security_issue_count=len(result.security_issues),
            degraded=result.degraded,
            tool_errors=result.tool_errors,
            suggestions=all_suggestions,
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        logger.debug("structured_output_failed: tapps_score_file", exc_info=True)


async def tapps_score_file(
    file_path: str,
    quick: bool = False,
    fix: bool = False,
    mode: str = "auto",
) -> dict[str, Any]:
    """REQUIRED after editing any source file. Scores quality across 7
    categories (complexity, security, maintainability, test coverage,
    performance, structure, devex). Skipping means quality issues go
    undetected and the quality gate will likely fail.

    Supports Python (.py), TypeScript/JavaScript (.ts, .tsx, .js, .jsx),
    Go (.go), and Rust (.rs) files.

    Use quick=True during edit-lint-fix loops; use full (quick=False) before
    declaring work complete.

    Args:
        file_path: Path to the source file to score.
        quick: If True, run quick-mode scoring (< 500 ms).
        fix: If True (requires quick=True, Python only), apply ruff auto-fixes first.
        mode: Execution mode - "subprocess", "direct", or "auto" (default).
            "direct" uses radon as a library and sync subprocess in thread
            pool, avoiding async subprocess reliability issues.
    """
    from tapps_mcp.server import _record_call, _record_execution, _validate_file_path, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_score_file")
    await ensure_session_initialized()

    try:
        resolved = _validate_file_path(file_path)
    except (ValueError, FileNotFoundError) as exc:
        return error_response("tapps_score_file", "path_denied", str(exc))

    # Get language-appropriate scorer
    scorer = _get_scorer_for_file(resolved)
    if scorer is None:
        return error_response(
            "tapps_score_file",
            "unsupported_language",
            f"File extension not supported for scoring: {resolved.suffix}. "
            "Supported: .py, .pyi, .ts, .tsx, .js, .jsx, .mjs, .cjs, .go, .rs",
        )

    fixes_applied = 0

    try:
        if quick:
            # Auto-fix only supported for Python files
            if fix and scorer.language == "python":
                from tapps_mcp.tools.ruff import run_ruff_fix

                fixes_applied = await asyncio.to_thread(
                    run_ruff_fix, str(resolved), cwd=str(resolved.parent)
                )
            result = await asyncio.to_thread(scorer.score_file_quick, resolved)
        else:
            result = await scorer.score_file(resolved, mode=mode)
    except Exception as exc:
        logger.error("scoring_failed", file_path=str(resolved), error=str(exc))
        return error_response("tapps_score_file", "scoring_failed", str(exc))

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    data, all_suggestions = _build_score_file_data(result, quick, fix, fixes_applied)

    settings_cache = load_settings()
    _attach_uncached_libraries_hint(data, resolved, settings_cache.project_root)

    _record_execution(
        "tapps_score_file",
        start,
        file_path=str(resolved),
        score=round(result.overall_score, 2),
        degraded=result.degraded,
    )

    resp = success_response("tapps_score_file", elapsed_ms, data, degraded=result.degraded)
    _attach_score_file_structured_output(resp, result, all_suggestions)

    return _with_nudges(
        "tapps_score_file",
        resp,
        {
            "security_issue_count": len(result.security_issues),
            "overall_score": round(result.overall_score, 2),
        },
    )


def _attach_quality_gate_structured_output(
    resp: dict[str, Any],
    resolved: Path,
    score_result: ScoreResult,
    gate_result: GateResult,
    gate_suggestions: list[str],
) -> None:
    """Attach structured output to the quality_gate response in-place."""
    try:
        from tapps_mcp.common.output_schemas import GateFailure, QualityGateOutput

        structured = QualityGateOutput(
            file_path=str(resolved),
            passed=gate_result.passed,
            preset=gate_result.preset,
            overall_score=round(score_result.overall_score, 2),
            threshold=gate_result.thresholds.overall_min,
            scores={k: round(v, 2) for k, v in gate_result.scores.items()},
            failures=[
                GateFailure(
                    category=f.category,
                    actual=f.actual,
                    threshold=f.threshold,
                    message=f.message,
                )
                for f in gate_result.failures
            ],
            warnings=gate_result.warnings,
            suggestions=gate_suggestions,
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        logger.debug("structured_output_failed: tapps_quality_gate", exc_info=True)


async def _resolve_preset(
    preset: str,
    ctx: Context[Any, Any, Any] | None,
) -> str:
    """Resolve the quality gate preset, using elicitation if available."""
    if not preset and ctx is not None:
        from tapps_mcp.common.elicitation import elicit_preset

        selected = await elicit_preset(ctx)
        if selected is not None:
            return selected
    return preset or "standard"


def _build_quality_gate_data(
    resolved: Path,
    score_result: ScoreResult,
    gate_result: GateResult,
) -> tuple[dict[str, Any], list[str]]:
    """Build the response data dict and suggestions for quality_gate."""
    failing_cats = {f.category for f in gate_result.failures}
    gate_suggestions: list[str] = []
    for name, cat in score_result.categories.items():
        if name in failing_cats and cat.suggestions:
            gate_suggestions.extend(cat.suggestions)

    gate_data: dict[str, Any] = {
        "file_path": str(resolved),
        "passed": gate_result.passed,
        "preset": gate_result.preset,
        "overall_score": round(score_result.overall_score, 2),
        "scores": {k: round(v, 2) for k, v in gate_result.scores.items()},
        "thresholds": gate_result.thresholds.model_dump(),
        "failures": [f.model_dump() for f in gate_result.failures],
        "warnings": gate_result.warnings,
        "suggestions": gate_suggestions,
    }
    if score_result.tool_errors:
        gate_data["tool_errors"] = score_result.tool_errors

    return gate_data, gate_suggestions


async def tapps_quality_gate(
    file_path: str,
    preset: str = "",
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """BLOCKING REQUIREMENT before declaring work complete. Runs full scoring
    then evaluates pass/fail against the quality preset. Work is NOT done
    until this passes (or the user explicitly accepts the risk).

    Supports Python (.py), TypeScript/JavaScript (.ts, .tsx, .js, .jsx),
    Go (.go), and Rust (.rs) files.

    If this tool is unavailable or rejected, use tapps_quick_check as a
    lighter alternative that includes a basic quality gate.

    Args:
        file_path: Path to the source file to evaluate.
        preset: Quality preset - "standard" (70+), "strict" (80+), or "framework" (75+).
            When empty, prompts the user to select via elicitation (if supported).
    """
    from tapps_mcp.server import _record_call, _record_execution, _validate_file_path, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_quality_gate")
    await ensure_session_initialized()

    preset = await _resolve_preset(preset, ctx)

    try:
        resolved = _validate_file_path(file_path)
    except (ValueError, FileNotFoundError) as exc:
        return error_response("tapps_quality_gate", "path_denied", str(exc))

    from tapps_mcp.gates.evaluator import evaluate_gate

    # Get language-appropriate scorer
    scorer = _get_scorer_for_file(resolved)
    if scorer is None:
        return error_response(
            "tapps_quality_gate",
            "unsupported_language",
            f"File extension not supported for scoring: {resolved.suffix}. "
            "Supported: .py, .pyi, .ts, .tsx, .js, .jsx, .mjs, .cjs, .go, .rs",
        )

    try:
        score_result = await scorer.score_file(resolved)
    except Exception as exc:
        logger.error("scoring_failed", file_path=str(resolved), error=str(exc))
        return error_response("tapps_quality_gate", "scoring_failed", str(exc))
    gate_result = evaluate_gate(score_result, preset=preset)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution(
        "tapps_quality_gate",
        start,
        file_path=str(resolved),
        gate_passed=gate_result.passed,
        score=round(score_result.overall_score, 2),
        degraded=score_result.degraded,
    )

    gate_data, gate_suggestions = _build_quality_gate_data(
        resolved, score_result, gate_result,
    )

    resp = success_response(
        "tapps_quality_gate",
        elapsed_ms,
        gate_data,
        degraded=score_result.degraded,
    )
    _attach_quality_gate_structured_output(
        resp, resolved, score_result, gate_result, gate_suggestions,
    )

    return _with_nudges(
        "tapps_quality_gate",
        resp,
        {
            "gate_passed": gate_result.passed,
        },
    )


def _compute_complexity_hint(resolved: Path) -> dict[str, Any] | None:
    """Compute AST-based complexity hint for a file.

    Returns a dict with max_cc_estimate and level, or None if not applicable.
    """
    try:
        code = resolved.read_text(encoding="utf-8", errors="replace")
        max_cc = ast_quick_complexity(code)
    except OSError:
        return None
    if max_cc is None or max_cc <= _CC_MODERATE_THRESHOLD:
        return None
    level = "high" if max_cc > _CC_HIGH_THRESHOLD else "moderate"
    return {"max_cc_estimate": max_cc, "level": level}


def _build_quick_check_data(
    resolved: Path,
    score_result: ScoreResult,
    sec_result: SecurityScanResult,
    gate_result: GateResult,
    preset: str,
    complexity_hint: dict[str, Any] | None,
    fixes_applied: int,
    fix: bool,
) -> tuple[dict[str, Any], list[str]]:
    """Build the response data dict and suggestions list for quick_check."""
    quick_categories: dict[str, float] = {
        name: round(cat.score, 2)
        for name, cat in score_result.categories.items()
        if cat.weight > 0
    }

    data: dict[str, Any] = {
        "file_path": str(resolved),
        "overall_score": round(score_result.overall_score, 2),
        "gate_passed": gate_result.passed,
        "gate_preset": preset,
        "security_passed": sec_result.passed,
        "lint_issue_count": len(score_result.lint_issues),
        "security_issue_count": sec_result.total_issues,
        "quick_categories": quick_categories,
    }

    _add_optional_quick_check_fields(
        data, score_result, sec_result, gate_result,
        complexity_hint, fixes_applied, fix,
    )
    suggestions = _build_quick_check_suggestions(score_result, complexity_hint)
    if suggestions:
        data["suggestions"] = suggestions

    return data, suggestions


def _add_optional_quick_check_fields(
    data: dict[str, Any],
    score_result: ScoreResult,
    sec_result: SecurityScanResult,
    gate_result: GateResult,
    complexity_hint: dict[str, Any] | None,
    fixes_applied: int,
    fix: bool,
) -> None:
    """Add conditional fields to quick_check data dict in-place."""
    if fix:
        data["fixes_applied"] = fixes_applied
    if complexity_hint:
        data["complexity_hint"] = complexity_hint
    if gate_result.failures:
        data["gate_failures"] = [f.model_dump() for f in gate_result.failures]
    if score_result.lint_issues:
        data["lint_issues"] = serialize_issues(score_result.lint_issues)
    if sec_result.total_issues > 0:
        data["security_issues"] = serialize_issues(
            sec_result.bandit_issues + sec_result.secret_findings,
            limit=10,
        )


def _build_quick_check_suggestions(
    score_result: ScoreResult,
    complexity_hint: dict[str, Any] | None,
) -> list[str]:
    """Collect suggestions from score categories and complexity hint."""
    suggestions: list[str] = []
    for cat in score_result.categories.values():
        suggestions.extend(cat.suggestions)
    if complexity_hint:
        cc = complexity_hint["max_cc_estimate"]
        suggestions.append(f"Max function CC~{cc}. Consider splitting complex functions.")
    return suggestions


def _attach_cross_file_analysis(
    data: dict[str, Any],
    resolved: Path,
    project_root: Path,
) -> None:
    """Run cross-file kwarg mismatch detection and attach results in-place.

    Story 75.2: Adds ``cross_file_analysis`` status and optional
    ``cross_file_findings`` list to the data dict.
    """
    try:
        from tapps_mcp.scoring.cross_ref import analyze_cross_references

        cross_ref = analyze_cross_references(resolved, project_root)
        data["cross_file_analysis"] = cross_ref.status
        if cross_ref.findings:
            data["cross_file_findings"] = [f.to_dict() for f in cross_ref.findings]
    except Exception:
        data["cross_file_analysis"] = "degraded"


def _attach_uncached_libraries_hint(
    data: dict[str, Any],
    resolved: Path,
    project_root: Path,
) -> None:
    """Detect uncached libraries and add hints to data dict in-place."""
    try:
        from tapps_mcp.knowledge.cache import KBCache
        from tapps_mcp.knowledge.import_analyzer import (
            extract_external_imports,
            find_uncached_libraries,
        )

        cache = KBCache(project_root / ".tapps-mcp-cache")
        external = extract_external_imports(resolved, project_root)
        uncached = find_uncached_libraries(external, cache)
        if uncached:
            data["uncached_libraries"] = uncached[:10]
            data["docs_hint"] = (
                f"Call tapps_lookup_docs for {', '.join(uncached[:5])} "
                "to avoid hallucinated APIs"
            )
    except Exception:
        logger.debug("uncached_libraries detection failed", exc_info=True)


def _attach_quick_check_structured_output(
    resp: dict[str, Any],
    resolved: Path,
    score_result: ScoreResult,
    sec_result: SecurityScanResult,
    gate_result: GateResult,
    preset: str,
    suggestions: list[str],
    complexity_hint: dict[str, Any] | None,
    quick_categories: dict[str, float],
    fixes_applied: int | None,
    recurring_events: list[dict[str, str]] | None = None,
) -> None:
    """Attach structured output to the response dict in-place."""
    try:
        from tapps_mcp.common.output_schemas import QuickCheckOutput

        structured = QuickCheckOutput(
            file_path=str(resolved),
            overall_score=round(score_result.overall_score, 2),
            gate_passed=gate_result.passed,
            gate_preset=preset,
            security_passed=sec_result.passed,
            lint_issue_count=len(score_result.lint_issues),
            security_issue_count=sec_result.total_issues,
            suggestions=suggestions,
            complexity_hint=complexity_hint,
            gate_failures=[f.model_dump() for f in gate_result.failures],
            quick_categories=quick_categories,
            fixes_applied=fixes_applied,
            recurring_quality_memory_events=list(recurring_events or []),
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        logger.debug("structured_output_failed: tapps_quick_check", exc_info=True)


_BATCH_CONCURRENCY = 10


async def _quick_check_single(
    resolved: Path,
    preset: str,
    fix: bool,
    settings: Any,
) -> dict[str, Any]:
    """Run quick_check logic on a single validated file and return the result dict."""
    from tapps_mcp.gates.evaluator import evaluate_gate
    from tapps_mcp.security.security_scanner import run_security_scan

    scorer = _get_scorer_for_file(resolved)
    if scorer is None:
        return {
            "file_path": str(resolved),
            "success": False,
            "error": (
                f"File extension not supported for scoring: {resolved.suffix}. "
                "Supported: .py, .pyi, .ts, .tsx, .js, .jsx, .mjs, .cjs, .go, .rs"
            ),
        }

    is_python = scorer.language == "python"

    fixes_applied = 0
    if fix and is_python:
        from tapps_mcp.tools.ruff import run_ruff_fix

        fixes_applied = await asyncio.to_thread(
            run_ruff_fix, str(resolved), cwd=str(resolved.parent)
        )

    if is_python:
        score_coro = asyncio.to_thread(scorer.score_file_quick_enriched, resolved)
    else:
        score_coro = asyncio.to_thread(scorer.score_file_quick, resolved)

    if is_python:
        sec_coro = asyncio.to_thread(
            run_security_scan,
            str(resolved),
            scan_secrets=True,
            cwd=str(settings.project_root),
            timeout=settings.tool_timeout,
        )
        score_result, sec_result = await asyncio.gather(score_coro, sec_coro)
    else:
        score_result = await score_coro
        from tapps_mcp.security.security_scanner import SecurityScanResult

        sec_result = SecurityScanResult(
            passed=True,
            bandit_issues=[],
            secret_findings=[],
            bandit_available=False,
            total_issues=0,
        )

    complexity_hint = _compute_complexity_hint(resolved) if is_python else None
    gate_result = evaluate_gate(score_result, preset=preset)

    data, _suggestions = _build_quick_check_data(
        resolved, score_result, sec_result, gate_result,
        preset, complexity_hint, fixes_applied, fix,
    )
    data.update(
        record_quick_check_recurring(settings, resolved, gate_result.passed, gate_result.failures)
    )

    _attach_uncached_libraries_hint(data, resolved, settings.project_root)

    # Story 75.2: Cross-file kwarg mismatch detection (Python only)
    if is_python:
        _attach_cross_file_analysis(data, resolved, settings.project_root)

    data["success"] = True
    data["gate_passed"] = gate_result.passed
    data["security_passed"] = sec_result.passed
    return data


async def tapps_quick_check(
    file_path: str,
    preset: str = "standard",
    fix: bool = False,
    file_paths: str = "",
) -> dict[str, Any]:
    """REQUIRED at minimum after editing any source file. Runs quick
    score + quality gate + basic security check in one fast call.
    For Python files, supplements with an AST complexity heuristic.
    For thorough validation, use tapps_validate_changed or individual tools.
    Skipping means quality regressions go unnoticed.

    Supports Python (.py), TypeScript/JavaScript (.ts, .tsx, .js, .jsx),
    Go (.go), and Rust (.rs) files.

    Supports batch mode: pass multiple comma-separated paths via ``file_paths``
    to check many files in one call with bounded concurrency.

    Args:
        file_path: Path to the source file to check (single-file mode).
        preset: Quality gate preset - "standard", "strict", or "framework".
        fix: If True (Python only), apply ruff auto-fixes before scoring.
        file_paths: Comma-separated file paths for batch mode. When non-empty,
            takes precedence over ``file_path``.
    """
    from tapps_mcp.server import _record_call, _record_execution, _validate_file_path, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_quick_check")
    await ensure_session_initialized()

    # --- Batch mode ---
    if file_paths.strip():
        raw_paths = [p.strip() for p in file_paths.split(",") if p.strip()]
        if not raw_paths:
            return error_response(
                "tapps_quick_check", "invalid_input", "file_paths is empty after parsing"
            )

        settings = load_settings()
        sem = asyncio.Semaphore(_BATCH_CONCURRENCY)

        async def _run_one(fp: str) -> dict[str, Any]:
            async with sem:
                try:
                    resolved = _validate_file_path(fp)
                except (ValueError, FileNotFoundError) as exc:
                    return {
                        "file_path": fp,
                        "success": False,
                        "error": str(exc),
                    }
                try:
                    return await _quick_check_single(resolved, preset, fix, settings)
                except Exception as exc:
                    logger.error(
                        "quick_check_batch_file_failed", file_path=fp, error=str(exc),
                    )
                    return {
                        "file_path": fp,
                        "success": False,
                        "error": str(exc),
                    }

        results = await asyncio.gather(*[_run_one(fp) for fp in raw_paths])
        result_list: list[dict[str, Any]] = list(results)

        passed_count = sum(
            1 for r in result_list if r.get("success") and r.get("gate_passed", False)
        )
        failure_count = len(result_list) - passed_count

        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        _record_execution("tapps_quick_check", start)

        return success_response(
            "tapps_quick_check",
            elapsed_ms,
            {
                "files_checked": len(result_list),
                "all_passed": failure_count == 0,
                "failure_count": failure_count,
                "results": result_list,
            },
        )

    # --- Single-file mode (original behavior) ---
    try:
        resolved = _validate_file_path(file_path)
    except (ValueError, FileNotFoundError) as exc:
        return error_response("tapps_quick_check", "path_denied", str(exc))

    from tapps_mcp.gates.evaluator import evaluate_gate
    from tapps_mcp.security.security_scanner import run_security_scan

    settings = load_settings()

    scorer = _get_scorer_for_file(resolved)
    if scorer is None:
        return error_response(
            "tapps_quick_check",
            "unsupported_language",
            f"File extension not supported for scoring: {resolved.suffix}. "
            "Supported: .py, .pyi, .ts, .tsx, .js, .jsx, .mjs, .cjs, .go, .rs",
        )

    is_python = scorer.language == "python"

    fixes_applied = 0
    if fix and is_python:
        from tapps_mcp.tools.ruff import run_ruff_fix

        fixes_applied = await asyncio.to_thread(
            run_ruff_fix, str(resolved), cwd=str(resolved.parent)
        )

    if is_python:
        score_coro = asyncio.to_thread(scorer.score_file_quick_enriched, resolved)
    else:
        score_coro = asyncio.to_thread(scorer.score_file_quick, resolved)

    if is_python:
        sec_coro = asyncio.to_thread(
            run_security_scan,
            str(resolved),
            scan_secrets=True,
            cwd=str(settings.project_root),
            timeout=settings.tool_timeout,
        )
        try:
            score_result, sec_result = await asyncio.gather(score_coro, sec_coro)
        except Exception as exc:
            logger.error("quick_check_failed", file_path=str(resolved), error=str(exc))
            return error_response("tapps_quick_check", "scoring_failed", str(exc))
    else:
        try:
            score_result = await score_coro
        except Exception as exc:
            logger.error("quick_check_failed", file_path=str(resolved), error=str(exc))
            return error_response("tapps_quick_check", "scoring_failed", str(exc))

        from tapps_mcp.security.security_scanner import SecurityScanResult

        sec_result = SecurityScanResult(
            passed=True,
            bandit_issues=[],
            secret_findings=[],
            bandit_available=False,
            total_issues=0,
        )

    complexity_hint = _compute_complexity_hint(resolved) if is_python else None
    gate_result = evaluate_gate(score_result, preset=preset)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution(
        "tapps_quick_check",
        start,
        file_path=str(resolved),
        gate_passed=gate_result.passed,
        score=round(score_result.overall_score, 2),
    )

    data, suggestions = _build_quick_check_data(
        resolved, score_result, sec_result, gate_result,
        preset, complexity_hint, fixes_applied, fix,
    )
    data.update(
        record_quick_check_recurring(settings, resolved, gate_result.passed, gate_result.failures)
    )

    _attach_uncached_libraries_hint(data, resolved, settings.project_root)

    # Story 75.2: Cross-file kwarg mismatch detection (Python only)
    if is_python:
        _attach_cross_file_analysis(data, resolved, settings.project_root)

    resp = success_response(
        "tapps_quick_check",
        elapsed_ms,
        data,
        degraded=not sec_result.bandit_available,
    )

    quick_categories = data.get("quick_categories", {})
    _attach_quick_check_structured_output(
        resp, resolved, score_result, sec_result, gate_result,
        preset, suggestions, complexity_hint, quick_categories,
        fixes_applied if fix else None,
        recurring_events=data.get("recurring_quality_memory_events", []),
    )

    return _with_nudges(
        "tapps_quick_check",
        resp,
        {
            "gate_passed": gate_result.passed,
            "security_passed": sec_result.passed,
            "overall_score": round(score_result.overall_score, 2),
            "security_issue_count": sec_result.total_issues,
        },
    )


_CC_BRANCH_NODES = (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With, ast.Assert)


def _cc_for_node(child: ast.AST) -> int:
    """Return the cyclomatic complexity contribution of a single AST node."""
    if isinstance(child, _CC_BRANCH_NODES):
        return 1
    if isinstance(child, ast.BoolOp):
        return len(child.values) - 1
    if isinstance(child, (ast.Match, ast.match_case)):
        return 1
    return 0


def _function_cc(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Compute cyclomatic complexity for a single function node."""
    cc = 1
    for child in ast.walk(node):
        cc += _cc_for_node(child)
    return cc


def ast_quick_complexity(code: str) -> int | None:
    """Compute a lightweight AST-based max function cyclomatic complexity.

    Returns the max CC or ``None`` on parse failure.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    max_cc = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            max_cc = max(max_cc, _function_cc(node))
    return max_cc


def register(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register scoring/gate tools on the shared *mcp_instance* (Epic 79.1: conditional)."""
    if "tapps_score_file" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_score_file)
    if "tapps_quality_gate" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_quality_gate)
    if "tapps_quick_check" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_quick_check)
