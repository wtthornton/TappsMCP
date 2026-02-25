"""Next-step nudge engine - computes actionable suggestions based on session state.

Every tool response includes ``next_steps`` telling the LLM exactly what
to call next.  The nudge engine reads ``CallTracker`` to know which tools
have already been called and produces a short, imperative list.

When ``tapps_mcp.tools.checklist`` is unavailable (e.g. incomplete binary),
CallTracker is not loaded and nudges/pipeline progress are omitted.
"""

from __future__ import annotations

from typing import Any

from tapps_mcp.experts.models import LOW_CONFIDENCE_THRESHOLD
from tapps_mcp.pipeline.models import STAGE_ORDER, STAGE_TOOLS, PipelineStage

# Lazy: avoid breaking when checklist module is missing (e.g. standalone binary).
# Use a list to avoid global statement (PLW0603); index 0 holds type or False.
_call_tracker_cache: list[type[Any] | bool] = []


def _get_call_tracker() -> type[Any] | None:
    """Return CallTracker class if available, else None."""
    if _call_tracker_cache:
        val = _call_tracker_cache[0]
        return val if isinstance(val, type) else None
    try:
        from tapps_mcp.tools.checklist import CallTracker

        _call_tracker_cache.append(CallTracker)
        return CallTracker
    except ImportError:
        _call_tracker_cache.append(False)
        return None


# Max nudges per response to avoid noise
_MAX_NUDGES = 3

# Discover-stage tools that should NOT trigger "you haven't called lookup_docs"
_DISCOVER_TOOLS = frozenset(STAGE_TOOLS[PipelineStage.DISCOVER])

# Tools that satisfy the "session initialized" requirement
_SESSION_INIT_TOOLS = frozenset({"tapps_server_info", "tapps_session_start"})


# ---------------------------------------------------------------------------
# Per-tool nudge rules
# ---------------------------------------------------------------------------
# Each entry: (condition(called, ctx) -> bool, nudge_text)
NudgeRule = tuple[Any, str]  # (callable, str) - use Any to avoid verbose typing

_TOOL_NUDGES: dict[str, list[NudgeRule]] = {
    "tapps_server_info": [
        (
            lambda called, _ctx: (
                "tapps_project_profile" not in called and "tapps_session_start" not in called
            ),
            "NEXT: Call tapps_project_profile() to detect the project tech stack.",
        ),
    ],
    "tapps_session_start": [
        (
            lambda called, _ctx: "tapps_lookup_docs" not in called,
            "NEXT: Call tapps_lookup_docs() for any external libraries you will use.",
        ),
    ],
    "tapps_score_file": [
        (
            lambda called, _ctx: "tapps_quality_gate" not in called,
            "NEXT: Call tapps_quality_gate() to verify this file passes the quality bar.",
        ),
        (
            lambda _called, ctx: (ctx or {}).get("security_issue_count", 0) > 0,
            "WARNING: Security issues detected. Call tapps_security_scan() for full analysis.",
        ),
    ],
    "tapps_quick_check": [
        (
            lambda called, _ctx: "tapps_checklist" not in called,
            "NEXT: Call tapps_checklist() as the final step before declaring done.",
        ),
    ],
    "tapps_quality_gate": [
        (
            lambda _called, ctx: (ctx or {}).get("gate_passed") is False,
            "Gate FAILED. Fix the issues, then re-run tapps_score_file() and tapps_quality_gate().",
        ),
        (
            lambda called, ctx: (
                (ctx or {}).get("gate_passed") is True and "tapps_checklist" not in called
            ),
            "NEXT: Call tapps_checklist() to verify no required steps were skipped.",
        ),
    ],
    "tapps_security_scan": [
        (
            lambda called, _ctx: "tapps_quality_gate" not in called,
            "NEXT: Call tapps_quality_gate() to verify the file passes the quality bar.",
        ),
    ],
    "tapps_project_profile": [
        (
            lambda called, _ctx: "tapps_lookup_docs" not in called,
            "NEXT: Call tapps_lookup_docs() for any external libraries you will use.",
        ),
    ],
    "tapps_consult_expert": [
        (
            lambda _called, ctx: (
                (ctx or {}).get("confidence", 1.0) < LOW_CONFIDENCE_THRESHOLD
            ),
            "Low confidence. Call tapps_research() for combined expert + docs lookup.",
        ),
    ],
    "tapps_research": [
        (
            lambda called, _ctx: (
                "tapps_score_file" not in called and "tapps_quick_check" not in called
            ),
            "NEXT: Write your code, then call tapps_score_file() or tapps_quick_check().",
        ),
    ],
    "tapps_lookup_docs": [
        (
            lambda called, _ctx: (
                "tapps_score_file" not in called and "tapps_quick_check" not in called
            ),
            "NEXT: Write your code, then call tapps_score_file() or tapps_quick_check().",
        ),
    ],
    "tapps_validate_changed": [
        (
            lambda called, _ctx: "tapps_checklist" not in called,
            "NEXT: Call tapps_checklist() as the final verification step.",
        ),
    ],
    "tapps_checklist": [
        (
            lambda _called, ctx: (ctx or {}).get("complete") is False,
            "Checklist incomplete. Address the missing required tools listed above.",
        ),
    ],
}


# Global nudge: remind about lookup_docs if never called
_GLOBAL_LOOKUP_NUDGE = "REMINDER: Call tapps_lookup_docs() before using any external library API."

# Global nudge: session not initialized
_SESSION_INIT_NUDGE = (
    "SETUP: tapps_session_start() was not called yet. "
    "Call it to ensure project context (root path, profile) is set correctly."
)

# Tools that benefit from session initialization (scoring, validation, security)
_SESSION_DEPENDENT_TOOLS = frozenset({
    "tapps_score_file",
    "tapps_quick_check",
    "tapps_quality_gate",
    "tapps_validate_changed",
    "tapps_security_scan",
    "tapps_dead_code",
    "tapps_dependency_scan",
    "tapps_dependency_graph",
})


def compute_next_steps(
    tool_name: str,
    context: dict[str, Any] | None = None,
) -> list[str]:
    """Return up to 3 imperative next-step strings for the given tool.

    Args:
        tool_name: The tool that was just called.
        context: Optional dict with tool-specific state (e.g.
            ``{"security_issue_count": 2, "gate_passed": False}``).

    Returns:
        List of 1-3 short imperative strings.
    """
    tracker = _get_call_tracker()
    if tracker is None:
        return []
    called = tracker.get_called_tools()
    steps: list[str] = []

    # Apply tool-specific rules
    rules = _TOOL_NUDGES.get(tool_name, [])
    for condition, text in rules:
        if len(steps) >= _MAX_NUDGES:
            break
        if condition(called, context):
            steps.append(text)

    # Global nudge: session-init guard for scoring/validation tools
    if (
        len(steps) < _MAX_NUDGES
        and tool_name in _SESSION_DEPENDENT_TOOLS
        and not _SESSION_INIT_TOOLS.intersection(called)
    ):
        steps.insert(0, _SESSION_INIT_NUDGE)

    # Global nudge: lookup_docs reminder (only for non-discover tools)
    if (
        len(steps) < _MAX_NUDGES
        and tool_name not in _DISCOVER_TOOLS
        and tool_name != "tapps_lookup_docs"
        and "tapps_lookup_docs" not in called
    ):
        steps.append(_GLOBAL_LOOKUP_NUDGE)

    return steps[:_MAX_NUDGES]


# ---------------------------------------------------------------------------
# Multi-step workflow suggestions
# ---------------------------------------------------------------------------
# Each rule: (condition(ctx) -> bool, ordered step list)
_WorkflowRule = tuple[Any, list[str]]  # (callable, list[str])

_WORKFLOW_MIN_CHANGED_FILES = 2  # trigger review pipeline when > 1 changed file
_WORKFLOW_LOW_SCORE_THRESHOLD = 70  # trigger fix-rescore loop below this score

_WORKFLOW_RULES: dict[str, list[_WorkflowRule]] = {
    "tapps_session_start": [
        (
            lambda ctx: (
                (ctx or {}).get("changed_python_file_count", 0) >= _WORKFLOW_MIN_CHANGED_FILES
            ),
            [
                "Multiple changed Python files detected.",
                "Run /tapps-review-pipeline to spawn parallel review-fixer agents.",
                "Or: call tapps_validate_changed() to batch-check all files.",
            ],
        ),
    ],
    "tapps_score_file": [
        (
            lambda ctx: (
                (ctx or {}).get("overall_score", 100) < _WORKFLOW_LOW_SCORE_THRESHOLD
            ),
            [
                "Score is below 70 - fix the issues flagged above.",
                "Re-run tapps_score_file() to verify improvements.",
                "Then call tapps_quality_gate() to confirm the file passes.",
            ],
        ),
    ],
    "tapps_quality_gate": [
        (
            lambda ctx: (ctx or {}).get("gate_passed") is False,
            [
                "Quality gate failed - address the failing categories.",
                "Fix the highest-impact issues first (see suggestions above).",
                "Re-run tapps_quality_gate() after fixes to verify.",
            ],
        ),
    ],
}


def compute_suggested_workflow(
    tool_name: str,
    context: dict[str, Any] | None = None,
) -> list[str] | None:
    """Return an ordered workflow suggestion for the given tool, or None.

    Unlike :func:`compute_next_steps` which returns single-step nudges,
    this returns a multi-step workflow when the tool output indicates a
    non-trivial follow-up sequence (e.g. review pipeline for many changed
    files, or fix-rescore-gate loop for low scores).

    Args:
        tool_name: The tool that was just called.
        context: Optional dict with tool-specific state.

    Returns:
        Ordered list of workflow step strings, or ``None`` if no workflow
        is triggered.
    """
    rules = _WORKFLOW_RULES.get(tool_name)
    if not rules:
        return None
    for condition, steps in rules:
        if condition(context):
            return list(steps)
    return None


def compute_pipeline_progress() -> dict[str, Any]:
    """Return pipeline stage completion status based on which tools have been called.

    Returns:
        Dict with ``completed_stages``, ``next_stage``, ``tools_called``,
        and ``total_calls``.
    """
    tracker = _get_call_tracker()
    if tracker is None:
        return {
            "completed_stages": [],
            "next_stage": "discover",
            "tools_called": [],
            "total_calls": 0,
        }
    called = tracker.get_called_tools()

    completed: list[str] = []
    for stage in STAGE_ORDER:
        stage_tools = STAGE_TOOLS[stage]
        if any(t in called for t in stage_tools):
            completed.append(stage.value)

    next_stage: str | None = None
    for stage in STAGE_ORDER:
        if stage.value not in completed:
            next_stage = stage.value
            break

    return {
        "completed_stages": completed,
        "next_stage": next_stage,
        "tools_called": sorted(called),
        "total_calls": tracker.total_calls(),
    }
