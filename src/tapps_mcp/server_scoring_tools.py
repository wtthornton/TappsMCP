"""Scoring and quality-gate tool handlers for TappsMCP.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:`register`.
"""

from __future__ import annotations

import ast
import logging
import time
from typing import TYPE_CHECKING, Any

from tapps_mcp.config.settings import load_settings
from tapps_mcp.server_helpers import error_response, serialize_issues, success_response

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

_logger = logging.getLogger(__name__)

# Complexity thresholds for AST heuristic
_CC_MODERATE_THRESHOLD = 10
_CC_HIGH_THRESHOLD = 15


async def tapps_score_file(
    file_path: str,
    quick: bool = False,
    fix: bool = False,
    mode: str = "auto",
) -> dict[str, Any]:
    """REQUIRED after editing any Python file. Scores quality across 7
    categories (complexity, security, maintainability, test coverage,
    performance, structure, devex). Skipping means quality issues go
    undetected and the quality gate will likely fail.

    Use quick=True during edit-lint-fix loops; use full (quick=False) before
    declaring work complete.

    Args:
        file_path: Path to the Python file to score.
        quick: If True, run ruff-only scoring (< 500 ms).
        fix: If True (requires quick=True), apply ruff auto-fixes first.
        mode: Execution mode - "subprocess", "direct", or "auto" (default).
            "direct" uses radon as a library and sync subprocess in thread
            pool, avoiding async subprocess reliability issues.
    """
    from tapps_mcp.server import _record_call, _record_execution, _validate_file_path, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_score_file")

    try:
        resolved = _validate_file_path(file_path)
    except (ValueError, FileNotFoundError) as exc:
        return error_response("tapps_score_file", "path_denied", str(exc))

    from tapps_mcp.scoring.scorer import CodeScorer

    scorer = CodeScorer()
    fixes_applied = 0

    if quick:
        if fix:
            from tapps_mcp.tools.ruff import run_ruff_fix

            fixes_applied = run_ruff_fix(str(resolved), cwd=str(resolved.parent))

        result = scorer.score_file_quick(resolved)
    else:
        result = await scorer.score_file(resolved, mode=mode)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

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

    try:
        from tapps_mcp.knowledge.cache import KBCache
        from tapps_mcp.knowledge.import_analyzer import (
            extract_external_imports,
            find_uncached_libraries,
        )

        settings_cache = load_settings()
        cache = KBCache(settings_cache.project_root / ".tapps-mcp-cache")
        external = extract_external_imports(resolved, settings_cache.project_root)
        uncached = find_uncached_libraries(external, cache)
        if uncached:
            data["uncached_libraries"] = uncached[:10]
            data["docs_hint"] = (
                f"Call tapps_lookup_docs for {', '.join(uncached[:5])} "
                "to avoid hallucinated APIs"
            )
    except Exception:
        _logger.debug("uncached_libraries detection failed", exc_info=True)

    _record_execution(
        "tapps_score_file",
        start,
        file_path=str(resolved),
        score=round(result.overall_score, 2),
        degraded=result.degraded,
    )

    resp = success_response("tapps_score_file", elapsed_ms, data, degraded=result.degraded)
    return _with_nudges("tapps_score_file", resp, {
        "security_issue_count": len(result.security_issues),
    })


async def tapps_quality_gate(
    file_path: str,
    preset: str = "standard",
) -> dict[str, Any]:
    """BLOCKING REQUIREMENT before declaring work complete. Runs full scoring
    then evaluates pass/fail against the quality preset. Work is NOT done
    until this passes (or the user explicitly accepts the risk).

    Args:
        file_path: Path to the Python file to evaluate.
        preset: Quality preset — "standard" (70+), "strict" (80+), or "framework" (75+).
    """
    from tapps_mcp.server import _record_call, _record_execution, _validate_file_path, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_quality_gate")

    try:
        resolved = _validate_file_path(file_path)
    except (ValueError, FileNotFoundError) as exc:
        return error_response("tapps_quality_gate", "path_denied", str(exc))

    from tapps_mcp.gates.evaluator import evaluate_gate
    from tapps_mcp.scoring.scorer import CodeScorer

    scorer = CodeScorer()
    score_result = await scorer.score_file(resolved)
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

    resp = success_response(
        "tapps_quality_gate",
        elapsed_ms,
        gate_data,
        degraded=score_result.degraded,
    )
    return _with_nudges("tapps_quality_gate", resp, {
        "gate_passed": gate_result.passed,
    })


async def tapps_quick_check(
    file_path: str,
    preset: str = "standard",
) -> dict[str, Any]:
    """REQUIRED at minimum after editing any Python file. Runs quick
    score + quality gate + basic security check in one fast call,
    supplemented with an AST complexity heuristic for better accuracy.
    For thorough validation, use tapps_validate_changed or individual tools.
    Skipping means quality regressions go unnoticed.

    Args:
        file_path: Path to the Python file to check.
        preset: Quality gate preset - "standard", "strict", or "framework".
    """
    from tapps_mcp.server import _record_call, _record_execution, _validate_file_path, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_quick_check")

    try:
        resolved = _validate_file_path(file_path)
    except (ValueError, FileNotFoundError) as exc:
        return error_response("tapps_quick_check", "path_denied", str(exc))

    from tapps_mcp.gates.evaluator import evaluate_gate
    from tapps_mcp.scoring.scorer import CodeScorer
    from tapps_mcp.security.security_scanner import run_security_scan

    settings = load_settings()
    scorer = CodeScorer()

    score_result = scorer.score_file_quick(resolved)

    # Supplement with AST complexity heuristic (Finding #9)
    complexity_hint: dict[str, Any] | None = None
    try:
        code = resolved.read_text(encoding="utf-8", errors="replace")
        max_cc = ast_quick_complexity(code)
        if max_cc is not None and max_cc > _CC_MODERATE_THRESHOLD:
            level = "high" if max_cc > _CC_HIGH_THRESHOLD else "moderate"
            complexity_hint = {"max_cc_estimate": max_cc, "level": level}
    except OSError:
        pass

    gate_result = evaluate_gate(score_result, preset=preset)

    sec_result = run_security_scan(
        str(resolved),
        scan_secrets=True,
        cwd=str(settings.project_root),
        timeout=settings.tool_timeout,
    )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution(
        "tapps_quick_check",
        start,
        file_path=str(resolved),
        gate_passed=gate_result.passed,
        score=round(score_result.overall_score, 2),
    )

    data: dict[str, Any] = {
        "file_path": str(resolved),
        "overall_score": round(score_result.overall_score, 2),
        "gate_passed": gate_result.passed,
        "gate_preset": preset,
        "security_passed": sec_result.passed,
        "lint_issue_count": len(score_result.lint_issues),
        "security_issue_count": sec_result.total_issues,
    }

    if complexity_hint:
        data["complexity_hint"] = complexity_hint

    if gate_result.failures:
        data["gate_failures"] = [f.model_dump() for f in gate_result.failures]
    if score_result.lint_issues:
        data["lint_issues"] = serialize_issues(score_result.lint_issues)
    if sec_result.total_issues > 0:
        data["security_issues"] = serialize_issues(
            sec_result.bandit_issues + sec_result.secret_findings, limit=10,
        )

    suggestions: list[str] = []
    for cat in score_result.categories.values():
        suggestions.extend(cat.suggestions)
    if complexity_hint:
        cc = complexity_hint["max_cc_estimate"]
        suggestions.append(f"Max function CC~{cc}. Consider splitting complex functions.")
    if suggestions:
        data["suggestions"] = suggestions

    resp = success_response(
        "tapps_quick_check", elapsed_ms, data,
        degraded=not sec_result.bandit_available,
    )
    return _with_nudges("tapps_quick_check", resp)


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
            cc = 1
            for child in ast.walk(node):
                if isinstance(child, (ast.If, ast.For, ast.While, ast.ExceptHandler,
                                      ast.With, ast.Assert, ast.BoolOp)):
                    cc += 1
            max_cc = max(max_cc, cc)
    return max_cc


def register(mcp_instance: FastMCP) -> None:
    """Register scoring/gate tools on the shared *mcp_instance*."""
    mcp_instance.tool()(tapps_score_file)
    mcp_instance.tool()(tapps_quality_gate)
    mcp_instance.tool()(tapps_quick_check)
