"""Diagnostic enrichment for ``tapps_validate_changed`` per-file results.

TAP-3585 / TAP-3589: propagate lint excerpts and ``failure_reason`` so batch
validate output matches the diagnostic depth of ``tapps_quick_check``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from tapps_mcp.server_helpers import serialize_issues

if TYPE_CHECKING:
    from tapps_mcp.scoring.models import ScoreResult

FailureReason = Literal[
    "parse_error",
    "lint_blocker",
    "gate_threshold",
    "scoring_error",
    "unsupported_file",
]

_TOP_FINDINGS_LIMIT = 3
_NEAR_MISS_MIN_SCORE = 70.0
_NEAR_MISS_MAX_SCORE = 80.0
_MAX_NEAR_MISS_FILES = 3
_MAX_IMPROVEMENT_HINTS = 2
_MULTI_FILE_MEMORY_SRC_THRESHOLD = 5


def is_near_miss_score(score: float | None) -> bool:
    """True when the file passed the gate but sits in the advisory improvement band."""
    if score is None:
        return False
    return _NEAR_MISS_MIN_SCORE <= float(score) < _NEAR_MISS_MAX_SCORE


def collect_improvement_hints(score: ScoreResult, *, max_hints: int = _MAX_IMPROVEMENT_HINTS) -> list[str]:
    """Collect category suggestions (same source as tapps_quick_check)."""
    hints: list[str] = []
    for cat in score.categories.values():
        hints.extend(cat.suggestions)
        if len(hints) >= max_hints:
            break
    return hints[:max_hints]


def attach_score_diagnostics(file_result: dict[str, Any], score: ScoreResult) -> None:
    """Attach truncated lint and security excerpts from the score result."""
    if score.lint_issues:
        file_result["lint_issues"] = serialize_issues(score.lint_issues, limit=_TOP_FINDINGS_LIMIT)
    if score.security_issues:
        file_result["security_issue_details"] = serialize_issues(
            score.security_issues,
            limit=_TOP_FINDINGS_LIMIT,
        )


def derive_failure_reason(file_result: dict[str, Any]) -> FailureReason | None:
    """Classify why a file failed validation."""
    errors = file_result.get("errors") or []
    if errors:
        err_text = " ".join(str(e) for e in errors).lower()
        if "unsupported file type" in err_text:
            return "unsupported_file"
        if "syntax" in err_text or "parse" in err_text:
            return "parse_error"
        return "scoring_error"

    score_val = file_result.get("overall_score", file_result.get("score"))
    lint_issues = file_result.get("lint_issues") or []
    # Missing gate_passed means the file never completed a gate evaluation
    # (error / unsupported paths) — treat as failed, not passed.
    gate_passed = file_result.get("gate_passed", False)

    if score_val == 0.0:
        return "lint_blocker" if lint_issues else "scoring_error"

    if not gate_passed:
        if file_result.get("gate_failures"):
            return "gate_threshold"
        if lint_issues:
            return "lint_blocker"

    return None


def _append_issue_findings(
    findings: list[dict[str, Any]],
    issues: list[Any],
    *,
    kind: str,
) -> None:
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        entry: dict[str, Any] = {
            "kind": kind,
            "code": issue.get("code", ""),
            "message": issue.get("message", ""),
        }
        if issue.get("line") is not None:
            entry["line"] = issue["line"]
        if issue.get("severity"):
            entry["severity"] = issue["severity"]
        findings.append(entry)
        if len(findings) >= _TOP_FINDINGS_LIMIT:
            return


def build_top_findings(file_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Return up to three lint/security findings for summary display."""
    findings: list[dict[str, Any]] = []
    _append_issue_findings(findings, file_result.get("lint_issues") or [], kind="lint")
    if len(findings) < _TOP_FINDINGS_LIMIT:
        _append_issue_findings(
            findings,
            file_result.get("security_issue_details") or [],
            kind="security",
        )
    return findings


def attach_improvement_hints(file_result: dict[str, Any], score: ScoreResult) -> None:
    """Store near-miss improvement hints when the file passed in the 70–79 band."""
    if not file_result.get("gate_passed", False):
        return
    overall = file_result.get("overall_score", score.overall_score)
    if not is_near_miss_score(overall if isinstance(overall, (int, float)) else None):
        return
    hints = collect_improvement_hints(score)
    if hints:
        file_result["improvement_hints"] = hints


def finalize_file_diagnostics(file_result: dict[str, Any]) -> None:
    """Compute failure_reason on the raw per-file result dict."""
    reason = derive_failure_reason(file_result)
    if reason is not None:
        file_result["failure_reason"] = reason


def count_src_paths(paths: list[Any]) -> int:
    """Count validated paths whose path contains a ``src`` segment."""
    count = 0
    for path in paths:
        parts = path.parts if hasattr(path, "parts") else Path(str(path)).parts
        if "src" in parts:
            count += 1
    return count


def build_multi_file_memory_hint(src_file_count: int) -> str | None:
    """Return an advisory memory-save hint for large multi-file engine work."""
    if src_file_count < _MULTI_FILE_MEMORY_SRC_THRESHOLD:
        return None
    return (
        f"Multi-file engine work ({src_file_count} files under src/ validated): "
        "consider `uv run tapps-mcp memory save --key <slug> --tier pattern --value \"...\"` "
        "for conventions learned this session, or invoke /tapps-finish-task to bundle "
        "validation + optional memory save."
    )


def enrich_file_entry(
    entry: dict[str, Any],
    row_parts: list[str],
    raw: dict[str, Any],
    *,
    near_miss_slots_remaining: int,
) -> int:
    """Add diagnostic fields to a per-file summary entry and grep row.

    Returns updated ``near_miss_slots_remaining`` after optionally attaching hints.
    """
    gate_passed = raw.get("gate_passed", False)
    errors = raw.get("errors") or []
    failed = not gate_passed or bool(errors)

    reason = raw.get("failure_reason") or derive_failure_reason(raw)
    if reason is not None:
        entry["failure_reason"] = reason
        row_parts.append(f"reason={reason}")

    if failed:
        top = build_top_findings(raw)
        if top:
            entry["top_findings"] = top
            first_code = top[0].get("code") or ""
            if first_code:
                row_parts.append(f"top={first_code}")
    elif near_miss_slots_remaining > 0:
        hints = raw.get("improvement_hints") or []
        if hints and gate_passed and is_near_miss_score(entry.get("score")):
            entry["improvement_hints"] = hints[:_MAX_IMPROVEMENT_HINTS]
            row_parts.append("near_miss=yes")
            return near_miss_slots_remaining - 1

    return near_miss_slots_remaining


__all__ = [
    "FailureReason",
    "_MAX_NEAR_MISS_FILES",
    "_MULTI_FILE_MEMORY_SRC_THRESHOLD",
    "attach_improvement_hints",
    "attach_score_diagnostics",
    "build_multi_file_memory_hint",
    "build_top_findings",
    "collect_improvement_hints",
    "count_src_paths",
    "derive_failure_reason",
    "enrich_file_entry",
    "finalize_file_diagnostics",
    "is_near_miss_score",
]
