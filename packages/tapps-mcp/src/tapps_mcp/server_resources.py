"""MCP resources and prompts for TappsMCP.

Extracted from ``server.py`` to reduce file size. Resources and prompts
are registered on the shared ``mcp`` instance via :func:`register`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP



def _get_quality_presets() -> str:
    """Get available quality gate presets and their thresholds."""
    from tapps_core.config.settings import PRESETS

    lines = ["# Quality Gate Presets\n"]
    for name, thresholds in PRESETS.items():
        lines.append(f"## {name}")
        for key, value in thresholds.items():
            lines.append(f"  {key}: {value}")
        lines.append("")
    return "\n".join(lines)


def _get_scoring_weights() -> str:
    """Get current scoring category weights."""
    from tapps_core.config.settings import ScoringWeights, load_settings

    settings = load_settings()
    w = settings.scoring_weights

    lines = ["# Scoring Weights\n"]
    for field_name in ScoringWeights.model_fields:
        lines.append(f"  {field_name}: {getattr(w, field_name)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_WORKFLOWS: dict[str, str] = {
    "general": (
        "TappsMCP Workflow - General\n\n"
        "1. tapps_session_start\n"
        "2. tapps_score_file(quick=True)\n3. tapps_score_file\n"
        "4. tapps_quality_gate\n5. tapps_checklist(task_type='review')"
    ),
    "feature": (
        "TappsMCP Workflow - New Feature\n\n"
        "1. tapps_session_start\n2. tapps_lookup_docs\n"
        "4. tapps_score_file(quick=True)\n5. tapps_score_file\n"
        "6. tapps_security_scan\n7. tapps_quality_gate\n"
        "8. tapps_checklist(task_type='feature')"
    ),
    "bugfix": (
        "TappsMCP Workflow - Bug Fix\n\n"
        "1. tapps_session_start\n2. tapps_impact_analysis\n"
        "3. tapps_score_file(quick=True)\n4. tapps_score_file\n"
        "5. tapps_quality_gate\n6. tapps_checklist(task_type='bugfix')"
    ),
    "refactor": (
        "TappsMCP Workflow - Refactoring\n\n"
        "1. tapps_session_start\n2. tapps_impact_analysis\n"
        "3. tapps_score_file(quick=True)\n4. tapps_score_file\n"
        "5. tapps_quality_gate\n6. tapps_checklist(task_type='refactor')"
    ),
    "security": (
        "TappsMCP Workflow - Security Review\n\n"
        "1. tapps_session_start\n2. tapps_security_scan\n"
        "3. tapps_score_file\n4. tapps_quality_gate(preset='strict')\n"
        "5. tapps_checklist(task_type='security')"
    ),
    "review": (
        "TappsMCP Workflow - Code Review\n\n"
        "1. tapps_session_start\n2. tapps_score_file\n"
        "3. tapps_security_scan\n4. tapps_quality_gate\n"
        "5. tapps_checklist(task_type='review')"
    ),
}


def _tapps_pipeline(stage: str = "discover") -> str:
    """TAPPS quality pipeline - structured 5-stage workflow."""
    from tapps_core.prompts.prompt_loader import load_stage_prompt

    return load_stage_prompt(stage)


def _tapps_pipeline_overview() -> str:
    """Get a summary of the full TAPPS 5-stage quality pipeline."""
    from tapps_core.prompts.prompt_loader import load_overview

    return load_overview()


def _tapps_workflow(
    task_type: str = "general",
    engagement_level: str | None = None,
) -> str:
    """Generate the TappsMCP workflow prompt for a specific task type."""
    from tapps_core.config.settings import load_settings

    level = engagement_level or load_settings().llm_engagement_level
    if level not in ("high", "medium", "low"):
        level = "medium"

    body = _WORKFLOWS.get(task_type, _WORKFLOWS["general"])
    if level == "high":
        return "You MUST call these tools in order.\n\n" + body
    if level == "low":
        return "Optional workflow - consider these tools when useful.\n\n" + body
    return "Recommended tool call order:\n\n" + body


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(mcp_instance: FastMCP) -> None:
    """Register MCP resources and prompts on the shared *mcp_instance*."""
    # Resources
    mcp_instance.resource("tapps://config/quality-presets")(_get_quality_presets)
    mcp_instance.resource("tapps://config/scoring-weights")(_get_scoring_weights)

    # Prompts
    mcp_instance.prompt()(_tapps_pipeline)
    mcp_instance.prompt()(_tapps_pipeline_overview)
    mcp_instance.prompt()(_tapps_workflow)
