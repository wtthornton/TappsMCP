"""Task decomposition helpers for ``tapps_decompose`` (TAP-479).

Extracted from ``server_pipeline_tools.py`` for maintainability.
Re-exported from ``server_pipeline_tools`` for backward compatibility.
"""

from __future__ import annotations

import re as _re
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel as _BaseModel

from tapps_mcp.server_helpers import error_response, success_response

# Model tier keyword sets (order matters — checked from highest to lowest tier)
_OPUS_KEYWORDS = frozenset(
    {"design", "architect", "architecture", "audit", "review", "security", "threat", "model"}
)
_SONNET_KEYWORDS = frozenset(
    {"implement", "refactor", "test", "fix", "write", "build", "create", "migrate", "integrate"}
)
_HAIKU_KEYWORDS = frozenset(
    {"search", "list", "read", "grep", "find", "format", "parse", "display", "show", "check"}
)

# Risk classification keywords
_HIGH_RISK_KEYWORDS = frozenset(
    {
        "security",
        "auth",
        "payment",
        "database",
        "migration",
        "deploy",
        "delete",
        "remove",
        "architect",
        "design",
        "threat",
    }
)
_LOW_RISK_KEYWORDS = frozenset(
    {"read", "search", "list", "format", "display", "show", "grep", "find"}
)


class TaskUnit(_BaseModel):
    """A single 15-minute decomposed work unit."""

    id: str
    title: str
    description: str
    estimated_minutes: int = 15
    model_tier: str  # haiku | sonnet | opus
    model_tier_reason: str
    dominant_risk: str  # high | medium | low
    done_condition: str
    depends_on: list[str] = []


def _summarize_quick_check(qc_data: dict[str, Any]) -> str:
    """Compact one-line summary of a quick_check response."""
    if "batch" in qc_data:
        batch = qc_data["batch"]
        return f"{batch.get('passed_count', 0)} passed / {batch.get('failed_count', 0)} failed"
    score = qc_data.get("score") or qc_data.get("overall_score")
    return f"score={score}" if score is not None else "ok"


def _classify_model_tier(text: str) -> tuple[str, str]:
    """Return (tier, reason) for a task text using keyword matching."""
    words = set(text.lower().split())
    if words & _OPUS_KEYWORDS:
        matched = sorted(words & _OPUS_KEYWORDS)
        return "opus", f"Keywords suggest architectural/security work: {matched}"
    if words & _SONNET_KEYWORDS:
        matched = sorted(words & _SONNET_KEYWORDS)
        return "sonnet", f"Keywords suggest implementation/refactor work: {matched}"
    if words & _HAIKU_KEYWORDS:
        matched = sorted(words & _HAIKU_KEYWORDS)
        return "haiku", f"Keywords suggest read/search/format work: {matched}"
    return "sonnet", "No strong signal — defaulting to sonnet"


def _classify_risk(text: str) -> str:
    """Return 'high' | 'medium' | 'low' based on keyword presence."""
    words = set(text.lower().split())
    if words & _HIGH_RISK_KEYWORDS:
        return "high"
    if words & _LOW_RISK_KEYWORDS:
        return "low"
    return "medium"


def _split_task_into_phrases(task: str) -> list[str]:
    """Split a free-text task into candidate sub-task phrases."""
    # Split on common sentence/clause separators.
    # Comma-space splits when followed by a known verb/keyword to avoid splitting
    # within a noun phrase.  Plain semicolons and newlines always split.
    parts = _re.split(
        r"(?:\.\s+|\band\s+also\b|\bthen\s+|\bthen,\s+|;\s*|\n|,\s+(?=[a-z]+\s))",
        task,
        flags=_re.IGNORECASE,
    )
    phrases = [p.strip().rstrip(",") for p in parts if p.strip() and len(p.strip()) > 5]
    return phrases or [task.strip()]


def _build_unit(idx: int, phrase: str, context_files: list[str]) -> TaskUnit:
    """Construct a single TaskUnit for one phrase."""
    tier, reason = _classify_model_tier(phrase)
    risk = _classify_risk(phrase)
    unit_id = f"u{idx}"

    desc = phrase
    if idx == 1 and context_files:
        file_names = ", ".join(context_files[:5])
        desc = f"{phrase} [context: {file_names}]"

    verb = phrase.lower().split()[0] if phrase.split() else "complete"
    done = f"{verb.capitalize()} done and verified independently"

    return TaskUnit(
        id=unit_id,
        title=phrase[:80],
        description=desc,
        estimated_minutes=15,
        model_tier=tier,
        model_tier_reason=reason,
        dominant_risk=risk,
        done_condition=done,
        depends_on=[f"u{idx - 1}"] if idx > 1 else [],
    )


def _decompose_task(
    task: str,
    context_files: list[str],
) -> list[TaskUnit]:
    """Break *task* into independently-verifiable ~15-minute units.

    Uses keyword matching only — no LLM calls.  Units are ordered risk-first
    (highest risk first) so failures surface early.
    """
    phrases = _split_task_into_phrases(task)
    units: list[TaskUnit] = [
        _build_unit(idx, phrase, context_files) for idx, phrase in enumerate(phrases, start=1)
    ]

    # Risk-first ordering: high → medium → low
    risk_order = {"high": 0, "medium": 1, "low": 2}
    units.sort(key=lambda u: risk_order.get(u.dominant_risk, 1))

    # Re-assign IDs after sort, reset depends_on to sequential
    for pos, unit in enumerate(units, start=1):
        unit.id = f"u{pos}"
        unit.depends_on = [f"u{pos - 1}"] if pos > 1 else []

    return units


def _collect_file_summaries(files: list[str]) -> list[dict[str, Any]]:
    """Collect best-effort file size summaries for context files."""
    summaries: list[dict[str, Any]] = []
    for fp in files[:10]:
        try:
            p = Path(fp)
            size = p.stat().st_size if p.exists() else None
            summaries.append({"path": fp, "size_bytes": size, "exists": p.exists()})
        except Exception:
            summaries.append({"path": fp, "size_bytes": None, "exists": False})
    return summaries


async def tapps_decompose(
    task: str,
    context_files: list[str] | None = None,
) -> dict[str, Any]:
    """Break a task into independently-verifiable ~15-minute work units with
    model tier recommendations.

    Decomposition is deterministic (keyword-based, no LLM calls).  Units are
    ordered risk-first (highest-risk first) so failures surface early.

    Args:
        task: Free-text description of the work to decompose.
        context_files: Optional list of file paths that provide context.
            File names and sizes are used to inform decomposition (no content read).
    """
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_decompose")

    if not task.strip():
        return error_response("tapps_decompose", "empty_task", "task must not be empty")

    files = context_files or []
    file_summaries = _collect_file_summaries(files)

    units = _decompose_task(task, [p["path"] for p in file_summaries])

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_decompose", start)

    data: dict[str, Any] = {
        "task": task,
        "unit_count": len(units),
        "units": [u.model_dump() for u in units],
        "context_files": file_summaries,
        "ordering": "risk-first (highest-risk units first)",
        "note": "Decomposition is advisory — units are suggestions, not requirements.",
    }

    resp = success_response("tapps_decompose", elapsed_ms, data)
    return _with_nudges("tapps_decompose", resp, {})
