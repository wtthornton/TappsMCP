"""MCP resources and prompts for TappsMCP.

Extracted from ``server.py`` to reduce file size. Resources and prompts
are registered on the shared ``mcp`` instance via :func:`register`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def _get_knowledge_resource(domain: str, topic: str) -> str:
    """Retrieve expert knowledge for a domain and topic."""
    import re

    from tapps_core.experts.registry import ExpertRegistry

    if domain not in ExpertRegistry.TECHNICAL_DOMAINS:
        valid = ", ".join(sorted(ExpertRegistry.TECHNICAL_DOMAINS))
        return f"Unknown domain: {domain}. Valid domains: {valid}"

    if not re.match(r"^[a-zA-Z0-9_-]+$", topic):
        return f"Invalid topic name: '{topic}'. Use only alphanumeric, hyphens, underscores."

    knowledge_dir = ExpertRegistry.get_knowledge_base_path() / domain
    topic_file = knowledge_dir / f"{topic}.md"

    try:
        topic_file.resolve().relative_to(knowledge_dir.resolve())
    except ValueError:
        return f"Invalid topic path: '{topic}'."

    if not topic_file.exists():
        if knowledge_dir.exists():
            available = [f.stem for f in knowledge_dir.glob("*.md")]
            avail = ", ".join(sorted(available))
            return f"Topic '{topic}' not found in domain '{domain}'. Available: {avail}"
        return f"No knowledge directory for domain '{domain}'."

    return topic_file.read_text(encoding="utf-8")


def _list_knowledge_domains() -> str:
    """List all available expert knowledge domains and their topics."""
    from tapps_core.experts.registry import ExpertRegistry

    knowledge_base = ExpertRegistry.get_knowledge_base_path()
    lines = ["# TappsMCP Knowledge Domains\n"]
    for domain_dir in sorted(knowledge_base.iterdir()):
        if not domain_dir.is_dir():
            continue
        topics = sorted(f.stem for f in domain_dir.glob("*.md") if f.stem != "README")
        lines.append(f"\n## {domain_dir.name}")
        lines.append(f"Topics ({len(topics)}):")
        for t in topics:
            lines.append(f"  - {t}")
    return "\n".join(lines)


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
        "1. tapps_session_start\n2. tapps_project_profile (when project context needed)\n"
        "3. tapps_score_file(quick=True)\n4. tapps_score_file\n"
        "5. tapps_quality_gate\n6. tapps_checklist(task_type='review')"
    ),
    "feature": (
        "TappsMCP Workflow - New Feature\n\n"
        "1. tapps_session_start\n2. tapps_project_profile (when project context needed)\n"
        "3. tapps_lookup_docs\n4. tapps_consult_expert\n"
        "5. tapps_score_file(quick=True)\n6. tapps_score_file\n"
        "7. tapps_security_scan\n8. tapps_quality_gate\n"
        "9. tapps_checklist(task_type='feature')"
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
        "3. tapps_consult_expert(domain='software-architecture')\n"
        "4. tapps_score_file(quick=True)\n5. tapps_score_file\n"
        "6. tapps_quality_gate\n7. tapps_checklist(task_type='refactor')"
    ),
    "security": (
        "TappsMCP Workflow - Security Review\n\n"
        "1. tapps_session_start\n2. tapps_security_scan\n"
        "3. tapps_consult_expert(domain='security')\n"
        "4. tapps_score_file\n5. tapps_quality_gate(preset='strict')\n"
        "6. tapps_checklist(task_type='security')"
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
    mcp_instance.resource("tapps://knowledge/{domain}/{topic}")(_get_knowledge_resource)
    mcp_instance.resource("tapps://knowledge/domains")(_list_knowledge_domains)
    mcp_instance.resource("tapps://config/quality-presets")(_get_quality_presets)
    mcp_instance.resource("tapps://config/scoring-weights")(_get_scoring_weights)

    # Prompts
    mcp_instance.prompt()(_tapps_pipeline)
    mcp_instance.prompt()(_tapps_pipeline_overview)
    mcp_instance.prompt()(_tapps_workflow)
