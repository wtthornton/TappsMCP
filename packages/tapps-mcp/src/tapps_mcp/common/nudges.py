"""Next-step nudge engine - computes actionable suggestions based on session state.

Every tool response includes ``next_steps`` telling the LLM exactly what
to call next.  The nudge engine reads ``CallTracker`` to know which tools
have already been called and produces a short, imperative list.

When ``tapps_mcp.tools.checklist`` is unavailable (e.g. incomplete binary),
CallTracker is not loaded and nudges/pipeline progress are omitted.
"""

from __future__ import annotations

from typing import Any

from tapps_core.common.pipeline_models import STAGE_ORDER, STAGE_TOOLS, PipelineStage

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


# STORY-101.5: Return only the single highest-impact nudge per response.
# Impact constants control priority when multiple rules fire simultaneously.
_MAX_NUDGES = 1

_IMPACT_CRITICAL = 90   # missing session/config — results may be wrong
_IMPACT_BLOCKING = 80   # failure or incomplete — must fix before proceeding
_IMPACT_HIGH = 70       # important next action (quality gate, etc.)
_IMPACT_MEDIUM = 60     # recommended follow-up
_IMPACT_LOW = 50        # suggested next step
_IMPACT_INFO = 40       # informational (e.g. skipped-step telemetry)
_IMPACT_REMINDER = 30   # low-priority global reminders

# Discover-stage tools that should NOT trigger "you haven't called lookup_docs"
_DISCOVER_TOOLS = frozenset(STAGE_TOOLS[PipelineStage.DISCOVER])

# Tools that satisfy the "session initialized" requirement
_SESSION_INIT_TOOLS = frozenset({"tapps_server_info", "tapps_session_start"})


# ---------------------------------------------------------------------------
# Per-tool nudge rules
# ---------------------------------------------------------------------------
# Each entry: (condition(called, ctx) -> bool, nudge_text, impact_score)
NudgeRule = tuple[Any, str, int]  # (callable, str, int) - use Any to avoid verbose typing

_TOOL_NUDGES: dict[str, list[NudgeRule]] = {
    "tapps_server_info": [
        (
            lambda called, _ctx: "tapps_session_start" not in called,
            "NEXT: Call tapps_session_start() to initialize project context.",
            _IMPACT_HIGH,
        ),
    ],
    "tapps_session_start": [
        (
            lambda called, _ctx: "tapps_lookup_docs" not in called,
            "NEXT: Call tapps_lookup_docs() for any external libraries you will use.",
            _IMPACT_LOW,
        ),
    ],
    "tapps_score_file": [
        (
            lambda _called, ctx: (ctx or {}).get("security_issue_count", 0) > 0,
            "WARNING: Security issues detected. Call tapps_security_scan() for full analysis.",
            _IMPACT_BLOCKING,
        ),
        (
            lambda called, _ctx: "tapps_quality_gate" not in called,
            "NEXT: Call tapps_quality_gate() to verify this file passes the quality bar.",
            _IMPACT_HIGH,
        ),
    ],
    "tapps_quick_check": [
        (
            lambda _called, ctx: (ctx or {}).get("gate_passed") is False,
            "Gate FAILED. Fix the issues, then re-run tapps_quick_check().",
            _IMPACT_BLOCKING,
        ),
        (
            lambda _called, ctx: (ctx or {}).get("security_passed") is False,
            "Security issues detected. Call tapps_security_scan() for full analysis.",
            _IMPACT_BLOCKING,
        ),
        (
            lambda called, _ctx: "tapps_checklist" not in called,
            "NEXT: Call tapps_checklist() as the final step before declaring done.",
            _IMPACT_MEDIUM,
        ),
    ],
    "tapps_quality_gate": [
        (
            lambda _called, ctx: (ctx or {}).get("gate_passed") is False,
            "Gate FAILED. Fix the issues, then re-run tapps_score_file() and tapps_quality_gate().",
            _IMPACT_BLOCKING,
        ),
        (
            lambda called, ctx: (
                (ctx or {}).get("gate_passed") is True and "tapps_checklist" not in called
            ),
            "NEXT: Call tapps_checklist() to verify no required steps were skipped.",
            _IMPACT_MEDIUM,
        ),
    ],
    "tapps_security_scan": [
        (
            lambda called, _ctx: "tapps_quality_gate" not in called,
            "NEXT: Call tapps_quality_gate() to verify the file passes the quality bar.",
            _IMPACT_HIGH,
        ),
    ],
    "tapps_lookup_docs": [
        (
            lambda called, _ctx: (
                "tapps_score_file" not in called and "tapps_quick_check" not in called
            ),
            "NEXT: Write your code, then call tapps_score_file() or tapps_quick_check().",
            _IMPACT_LOW,
        ),
    ],
    "tapps_validate_changed": [
        (
            lambda called, _ctx: "tapps_checklist" not in called,
            "NEXT: Call tapps_checklist() as the final verification step.",
            _IMPACT_MEDIUM,
        ),
    ],
    "tapps_checklist": [
        (
            lambda _called, ctx: (ctx or {}).get("complete") is False,
            "Checklist incomplete. Address the missing required tools listed above.",
            _IMPACT_BLOCKING,
        ),
        # STORY-101.7: Detect when validate_changed was skipped entirely.
        (
            lambda called, ctx: (
                (ctx or {}).get("complete") is True
                and "tapps_validate_changed" not in called
                and "tapps_pipeline" not in called
                and any(t in called for t in ("tapps_score_file", "tapps_quick_check"))
            ),
            "WARNING: tapps_validate_changed was never called. "
            "Run tapps_validate_changed(file_paths=...) to batch-confirm all changes pass the quality gate.",
            _IMPACT_INFO,
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
    """Return the single highest-impact next-step string for the given tool.

    STORY-101.5: Collects all matching nudges, ranks by impact score, and
    returns only the top-1 so agents always get one clear action — not a
    noisy list to triage.

    Args:
        tool_name: The tool that was just called.
        context: Optional dict with tool-specific state (e.g.
            ``{"security_issue_count": 2, "gate_passed": False}``).

    Returns:
        List with at most 1 short imperative string.
    """
    tracker = _get_call_tracker()
    if tracker is None:
        return []
    called = tracker.get_called_tools()

    # Collect all matching nudges as (impact, text) pairs.
    candidates: list[tuple[int, str]] = []

    for condition, text, impact in _TOOL_NUDGES.get(tool_name, []):
        if condition(called, context):
            candidates.append((impact, text))

    # Global nudge: session-init guard for scoring/validation tools.
    if (
        tool_name in _SESSION_DEPENDENT_TOOLS
        and not _SESSION_INIT_TOOLS.intersection(called)
    ):
        candidates.append((_IMPACT_CRITICAL, _SESSION_INIT_NUDGE))

    # Global nudge: lookup_docs reminder (only for non-discover tools).
    if (
        tool_name not in _DISCOVER_TOOLS
        and tool_name != "tapps_lookup_docs"
        and "tapps_lookup_docs" not in called
    ):
        candidates.append((_IMPACT_REMINDER, _GLOBAL_LOOKUP_NUDGE))

    # Return top-1 by impact descending.
    candidates.sort(key=lambda x: x[0], reverse=True)
    return [text for _, text in candidates[:_MAX_NUDGES]]


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
