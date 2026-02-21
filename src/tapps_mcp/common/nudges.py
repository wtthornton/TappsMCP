"""Next-step nudge engine - computes actionable suggestions based on session state.

Every tool response includes ``next_steps`` telling the LLM exactly what
to call next.  The nudge engine reads ``CallTracker`` to know which tools
have already been called and produces a short, imperative list.

When ``tapps_mcp.tools.checklist`` is unavailable (e.g. incomplete binary),
CallTracker is not loaded and nudges/pipeline progress are omitted.
"""

from __future__ import annotations

from typing import Any

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

    # Global nudge: lookup_docs reminder (only for non-discover tools)
    if (
        len(steps) < _MAX_NUDGES
        and tool_name not in _DISCOVER_TOOLS
        and tool_name != "tapps_lookup_docs"
        and "tapps_lookup_docs" not in called
    ):
        steps.append(_GLOBAL_LOOKUP_NUDGE)

    return steps[:_MAX_NUDGES]


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
