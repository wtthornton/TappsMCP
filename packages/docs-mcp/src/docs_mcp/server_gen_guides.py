"""Guide-style DocsMCP generation tools.

Onboarding, contributing, runbook, postmortem, and PRD documents. Split
out of ``server_gen_tools.py`` under TAP-5608 — that module is now a
registration facade that re-exports these handlers.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import structlog

from docs_mcp.server_gen_helpers import (
    get_settings as _get_settings,
)
from docs_mcp.server_gen_helpers import (
    record_call as _record_call,
)
from docs_mcp.server_helpers import (
    error_response,
    finalize_output,
    safe_slug,
    success_response,
)

logger = structlog.get_logger(__name__)


async def docs_generate_onboarding(
    output_path: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Generate a getting-started / onboarding guide for the project.

    Creates a developer onboarding document with prerequisites, installation,
    project structure, and first steps based on project analysis.

    Args:
        output_path: Output file path (default: docs/ONBOARDING.md).
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_generate_onboarding")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_onboarding",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.generators.guides import OnboardingGuideGenerator

    try:
        generator = OnboardingGuideGenerator()
        content = generator.generate(root)
    except Exception as exc:
        return error_response(
            "docs_generate_onboarding",
            "GENERATION_ERROR",
            f"Failed to generate onboarding guide: {exc}",
        )

    if not content:
        return error_response(
            "docs_generate_onboarding",
            "NO_CONTENT",
            "Could not generate onboarding content for this project.",
        )

    # Auto-compute output_path when not provided
    target = output_path.strip() or "docs/ONBOARDING.md"

    # Three-tier output: write-first / inline / manifest
    out = await finalize_output(
        "docs_generate_onboarding",
        content,
        target,
        root,
        description="Getting-started / onboarding guide.",
    )
    if not out.get("success", True):
        return out

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {**out}

    return success_response("docs_generate_onboarding", elapsed_ms, data)


async def docs_generate_contributing(
    output_path: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Generate a CONTRIBUTING.md file for the project.

    Creates a contribution guide with development setup, coding standards,
    testing, and PR workflow based on project analysis.

    Args:
        output_path: Output file path (default: CONTRIBUTING.md in project root).
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_generate_contributing")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_contributing",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.generators.guides import ContributingGuideGenerator

    try:
        generator = ContributingGuideGenerator()
        content = generator.generate(root)
    except Exception as exc:
        return error_response(
            "docs_generate_contributing",
            "GENERATION_ERROR",
            f"Failed to generate contributing guide: {exc}",
        )

    if not content:
        return error_response(
            "docs_generate_contributing",
            "NO_CONTENT",
            "Could not generate contributing content for this project.",
        )

    # Auto-compute output_path when not provided
    target = output_path.strip() or "CONTRIBUTING.md"

    # Three-tier output: write-first / inline / manifest
    out = await finalize_output(
        "docs_generate_contributing",
        content,
        target,
        root,
        description="Contribution guide with development setup and PR workflow.",
    )
    if not out.get("success", True):
        return out

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {**out}

    return success_response("docs_generate_contributing", elapsed_ms, data)


async def docs_generate_runbook(
    title: str,
    service: str = "",
    when_to_use: str = "",
    prerequisites: str = "",
    procedure: str = "",
    rollback_steps: str = "",
    escalation: str = "",
    output_path: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Generate an operational runbook with procedure, rollback, and escalation sections.

    Args:
        title: Runbook title (required).
        service: Service or system name.
        when_to_use: Symptoms or triggers for using this runbook.
        prerequisites: Access, credentials, and tooling required.
        procedure: Step-by-step procedure (numbered lines or markdown list).
        rollback_steps: How to revert if the procedure fails.
        escalation: On-call paths and severity thresholds.
        output_path: Output file path (default: docs/operations/runbooks/<slug>.md).
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_generate_runbook")
    start = time.perf_counter_ns()

    if not title.strip():
        return error_response(
            "docs_generate_runbook",
            "INPUT_INVALID",
            "title is required.",
        )

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_runbook",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.generators.operations import RunbookGenerator

    try:
        generator = RunbookGenerator()
        content = generator.generate(
            root,
            title=title,
            service=service,
            when_to_use=when_to_use,
            prerequisites=prerequisites,
            procedure=procedure,
            rollback_steps=rollback_steps,
            escalation=escalation,
        )
    except Exception as exc:
        return error_response(
            "docs_generate_runbook",
            "GENERATION_ERROR",
            f"Failed to generate runbook: {exc}",
        )

    if not content:
        return error_response(
            "docs_generate_runbook",
            "NO_CONTENT",
            "Could not generate runbook content.",
        )

    slug = safe_slug(title)
    target = output_path.strip() or f"docs/operations/runbooks/{slug}.md"

    out = await finalize_output(
        "docs_generate_runbook",
        content,
        target,
        root,
        description=f"Operational runbook: {title.strip()}.",
    )
    if not out.get("success", True):
        return out

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    return success_response("docs_generate_runbook", elapsed_ms, {**out})


async def docs_generate_postmortem(
    title: str,
    incident_date: str = "",
    summary: str = "",
    timeline: str = "",
    impact: str = "",
    root_cause: str = "",
    action_items: str = "",
    output_path: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Generate an incident postmortem document (blameless, action-oriented).

    Args:
        title: Postmortem title (required).
        incident_date: Incident date (ISO-8601 or free text).
        summary: Brief summary of what happened.
        timeline: Detection → mitigation → recovery timeline.
        impact: User/business impact and duration.
        root_cause: Root cause analysis (technical and process).
        action_items: Follow-ups with owners (markdown list).
        output_path: Output path (default: docs/operations/postmortems/<slug>.md).
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_generate_postmortem")
    start = time.perf_counter_ns()

    if not title.strip():
        return error_response(
            "docs_generate_postmortem",
            "INPUT_INVALID",
            "title is required.",
        )

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_postmortem",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.generators.operations import PostmortemGenerator

    try:
        generator = PostmortemGenerator()
        content = generator.generate(
            root,
            title=title,
            incident_date=incident_date,
            summary=summary,
            timeline=timeline,
            impact=impact,
            root_cause=root_cause,
            action_items=action_items,
        )
    except Exception as exc:
        return error_response(
            "docs_generate_postmortem",
            "GENERATION_ERROR",
            f"Failed to generate postmortem: {exc}",
        )

    if not content:
        return error_response(
            "docs_generate_postmortem",
            "NO_CONTENT",
            "Could not generate postmortem content.",
        )

    slug = safe_slug(title)
    target = output_path.strip() or f"docs/operations/postmortems/{slug}.md"

    out = await finalize_output(
        "docs_generate_postmortem",
        content,
        target,
        root,
        description=f"Incident postmortem: {title.strip()}.",
    )
    if not out.get("success", True):
        return out

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    return success_response("docs_generate_postmortem", elapsed_ms, {**out})


async def docs_generate_prd(
    title: str,
    problem: str = "",
    personas: str = "",
    phases: str = "",
    constraints: str = "",
    non_goals: str = "",
    style: str = "standard",
    auto_populate: bool = False,
    existing_content: str = "",
    output_path: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Generate a Product Requirements Document (PRD) with phased requirements.

    Creates a structured PRD with Executive Summary, Problem Statement, User
    Personas, Solution Overview, Phased Requirements, Acceptance Criteria
    (Gherkin), Technical Constraints, and Non-Goals.

    The ``comprehensive`` style adds a Boundary System ("Always do" /
    "Ask first" / "Never do") and Architecture Overview section.

    When ``auto_populate=True``, enriches sections from project analyzers
    (module map, tech stack, quality scores, git history).

    When ``existing_content`` is provided, uses SmartMerger to preserve
    hand-edited sections (identified by ``<!-- docsmcp:start:section -->``
    markers).

    Args:
        title: Title for the PRD (e.g. "User Authentication System").
        problem: Problem statement text.
        personas: Comma-separated list of user personas.
        phases: JSON array of phase objects with keys: name, description,
            requirements. Example: [{"name": "MVP", "requirements": ["Login"]}]
        constraints: Comma-separated list of technical constraints.
        non_goals: Comma-separated list of non-goals / out-of-scope items.
        style: PRD style - "standard" or "comprehensive".
        auto_populate: Enrich from project analyzers (ModuleMap, Metadata, etc).
        existing_content: Existing PRD markdown to merge with (preserves edits).
        output_path: File path to write the PRD (relative to project root).
            When empty, returns the content without writing a file.
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_generate_prd")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_prd",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.generators.specs import PRDConfig, PRDGenerator, PRDPhase

    # Parse comma-separated lists
    persona_list = [p.strip() for p in personas.split(",") if p.strip()] if personas else []
    constraint_list = (
        [c.strip() for c in constraints.split(",") if c.strip()] if constraints else []
    )
    non_goal_list = [n.strip() for n in non_goals.split(",") if n.strip()] if non_goals else []

    # Parse phases JSON
    phase_list: list[PRDPhase] = []
    if phases:
        try:
            phase_list = PRDGenerator.parse_phases_json(phases)
        except ValueError as exc:
            return error_response(
                "docs_generate_prd",
                "INVALID_PHASES",
                str(exc),
            )

    config = PRDConfig(
        title=title,
        problem=problem,
        personas=persona_list,
        phases=phase_list,
        constraints=constraint_list,
        non_goals=non_goal_list,
        style=style,
        existing_content=existing_content,
    )

    generator = PRDGenerator()

    try:
        content = generator.generate(
            config,
            project_root=root if auto_populate else None,
            auto_populate=auto_populate,
        )
    except Exception as exc:
        return error_response(
            "docs_generate_prd",
            "GENERATION_ERROR",
            f"Failed to generate PRD: {exc}",
        )

    # SmartMerger integration when existing content is provided
    merge_stats: dict[str, Any] = {}
    if existing_content.strip():
        from docs_mcp.generators.smart_merge import SmartMerger

        try:
            merger = SmartMerger()
            result = merger.merge(existing_content, content)
            content = result.content
            merge_stats = {
                "merged": True,
                "sections_preserved": result.sections_preserved,
                "sections_updated": result.sections_updated,
                "sections_added": result.sections_added,
            }
        except Exception as exc:
            return error_response(
                "docs_generate_prd",
                "MERGE_ERROR",
                f"Failed to merge with existing content: {exc}",
            )
    else:
        merge_stats = {"merged": False}

    # Auto-compute output_path when not provided
    if output_path.strip():
        target = output_path.strip()
    else:
        slug = title.strip().replace(" ", "-").lower()[:60]
        target = f"docs/PRD-{slug}.md"

    # Three-tier output: write-first / inline / manifest
    out = await finalize_output(
        "docs_generate_prd",
        content,
        target,
        root,
        description=f"Product Requirements Document: {title}",
    )
    if not out.get("success", True):
        return out

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "title": title,
        "style": style,
        "auto_populated": auto_populate,
        **merge_stats,
        **out,
    }

    return success_response(
        "docs_generate_prd",
        elapsed_ms,
        data,
        next_steps=[
            "Review the generated PRD and fill in placeholder sections.",
            "Human-written sections (without docsmcp markers) will be preserved on re-generation.",
        ],
    )
