"""Helper functions for ``tapps_init`` and ``tapps_upgrade``.

Extracted from ``server_pipeline_tools.py`` to keep that module a thin
orchestrator.  Functions here are private helpers and are not exposed
as MCP tools.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from mcp.server.fastmcp import Context

from tapps_mcp.server_helpers import emit_ctx_info, success_response


async def maybe_elicit_init_confirmation(
    ctx: Context[Any, Any, Any] | None,
    start: int,
    verify_only: bool,
    dry_run: bool,
) -> dict[str, Any] | None:
    """Optionally ask the host to confirm tapps_init via elicitation.

    Returns the cancelled response dict if user declined, else ``None``.
    """
    from tapps_mcp import server_pipeline_tools as _host
    from tapps_mcp.server import _record_execution

    if ctx is None or verify_only or dry_run:
        return None

    from tapps_mcp.common.elicitation import elicit_init_confirmation

    settings_peek = _host.load_settings()
    confirmed = await elicit_init_confirmation(ctx, str(settings_peek.project_root))
    if confirmed is False:
        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        _record_execution("tapps_init", start, status="cancelled")
        return success_response(
            "tapps_init",
            elapsed_ms,
            {"cancelled": True, "message": "tapps_init cancelled - no files were written."},
        )
    return None


def resolve_write_mode_env(output_mode: str) -> str:
    """Set TAPPS_WRITE_MODE per output_mode and return the previous value."""
    import os as _os

    prev = _os.environ.get("TAPPS_WRITE_MODE", "")
    if output_mode == "content_return":
        _os.environ["TAPPS_WRITE_MODE"] = "content"
    elif output_mode == "direct_write":
        _os.environ["TAPPS_WRITE_MODE"] = "direct"
    return prev


def restore_write_mode_env(prev: str) -> None:
    """Restore TAPPS_WRITE_MODE to its previous value."""
    import os as _os

    if prev:
        _os.environ["TAPPS_WRITE_MODE"] = prev
    else:
        _os.environ.pop("TAPPS_WRITE_MODE", None)


async def run_init_wizard_if_needed(
    ctx: Context[Any, Any, Any] | None,
    *,
    verify_only: bool,
    dry_run: bool,
    llm_engagement_level: str | None,
    platform: str,
    agent_teams: bool,
) -> tuple[Any, str | None, str, bool, bool]:
    """Optionally run the first-run wizard. Returns updated args + hint flag."""
    from tapps_mcp import server_pipeline_tools as _host

    wizard_answers = None
    add_other_mcps_hint = False
    if ctx is not None and not verify_only and not dry_run:
        wizard_answers = await _host._maybe_run_wizard(
            ctx,
            llm_engagement_level=llm_engagement_level,
            platform=platform,
            agent_teams=agent_teams,
        )
        if wizard_answers is not None:
            llm_engagement_level = wizard_answers.engagement_level
            agent_teams = wizard_answers.agent_teams
            if not platform:
                platform = "claude"
    if wizard_answers is not None and wizard_answers.add_other_mcps:
        add_other_mcps_hint = True
    return wizard_answers, llm_engagement_level, platform, agent_teams, add_other_mcps_hint


def skill_tier_from_wizard(wizard_answers: Any, settings: Any) -> str:
    """Resolve skill_tier from wizard answers or settings (default full)."""
    if wizard_answers is not None:
        tier = getattr(wizard_answers, "skill_tier", None)
        if tier in {"core", "full"}:
            return str(tier)
    tier = getattr(settings, "skill_tier", "full")
    return tier if tier in {"core", "full"} else "full"


def resolve_init_mcp_bundle(mcp_bundle: str | None, settings: Any) -> tuple[str, str]:
    """Resolve the ``mcp_bundle`` ``tapps_init`` actually deploys with (TAP-7020).

    Precedence: an explicit caller argument wins; else an existing
    ``.tapps-mcp.yaml`` value (so a re-run never silently re-expands a
    project someone already narrowed); else
    :data:`tapps_mcp.distribution.nlt_mcp_config.DEFAULT_NLT_BUNDLE`
    (ADR-0018's greenfield default), sourced from the constant rather than
    restated as a second literal. Returns ``(bundle, reason)``.
    """
    from tapps_mcp.distribution.nlt_mcp_config import DEFAULT_NLT_BUNDLE

    settings_bundle = getattr(settings, "mcp_bundle", None)
    if mcp_bundle is not None:
        return mcp_bundle, "explicit caller argument"
    if isinstance(settings_bundle, str):
        return settings_bundle, "from .tapps-mcp.yaml"
    return DEFAULT_NLT_BUNDLE, "greenfield default (ADR-0018)"


def maybe_write_mcp_config(
    result: dict[str, Any],
    settings: Any,
    platform: str,
    mcp_config: bool,
    dry_run: bool,
    *,
    mcp_bundle: str = "full",
) -> None:
    """Write project-scoped MCP config (Epic 47.2; default on for ``tapps_init``).

    Strips direct ``tapps-brain`` MCP entries before generation (TAP-1888)
    and includes docs-mcp when bootstrap detected it in the project.
    """
    if not mcp_config or dry_run:
        return

    from tapps_mcp.distribution.doctor import strip_brain_mcp_entries
    from tapps_mcp.distribution.setup_generator import _generate_config

    mcp_host = "claude-code"
    if platform == "cursor":
        mcp_host = "cursor"
    elif platform == "vscode":
        mcp_host = "vscode"

    with_docs_mcp = bool(result.get("docsmcp_detected"))
    strip_brain_mcp_entries(settings.project_root)
    config_ok = _generate_config(
        mcp_host,
        settings.project_root,
        force=True,
        scope="project",
        with_docs_mcp=with_docs_mcp,
        mcp_bundle=mcp_bundle,
        use_nlt_plugin=True,
    )
    if config_ok:
        result["mcp_config_written"] = True
        result["mcp_config_scope"] = "project"
        result["mcp_config_with_docs_mcp"] = with_docs_mcp
        result["mcp_config_bundle"] = mcp_bundle
        result["brain_mcp_stripped"] = True


async def emit_init_progress(ctx: Context[Any, Any, Any] | None, result: dict[str, Any]) -> None:
    """Emit ctx.info() for each created file and warning."""
    for filename in result.get("created", []):
        await emit_ctx_info(ctx, f"Created {filename}")
    for warning in result.get("warnings", []):
        await emit_ctx_info(ctx, f"Warning: {warning}")


def build_init_bootstrap_config(
    *,
    create_handoff: bool,
    create_runlog: bool,
    create_agents_md: bool,
    create_tech_stack_md: bool,
    platform: str,
    verify_server: bool,
    install_missing_checkers: bool,
    warm_cache_from_tech_stack: bool,
    warm_expert_rag_from_tech_stack: bool,
    overwrite_platform_rules: bool,
    overwrite_agents_md: bool,
    overwrite_tech_stack_md: bool,
    agent_teams: bool,
    memory_auto_capture: bool,
    memory_auto_recall: bool,
    destructive_guard: bool,
    linear_enforce_gate: bool,
    linear_enforce_cache_gate: str,
    session_start_gate: str,
    install_git_hooks: bool,
    linear_sdlc: bool,
    with_report_studio: bool,
    report_studio_tag: str,
    report_studio_scaffold: str,
    report_studio_template: str,
    linear_issue_prefix: str,
    linear_team_id: str,
    linear_project_id: str,
    minimal: bool,
    dry_run: bool,
    verify_only: bool,
    llm_engagement_level: str | None,
    scaffold_experts: bool,
    include_karpathy: bool,
    mcp_bundle: str,
    settings: Any,
    skill_tier: str | None = None,
    wizard_answers: Any = None,
) -> Any:
    """Assemble the :class:`BootstrapConfig` used by :func:`bootstrap_pipeline`."""
    from tapps_mcp.pipeline.init import BootstrapConfig

    resolved_tier = skill_tier or skill_tier_from_wizard(wizard_answers, settings)
    return BootstrapConfig(
        create_handoff=create_handoff,
        create_runlog=create_runlog,
        create_agents_md=create_agents_md,
        create_tech_stack_md=create_tech_stack_md,
        platform=platform,
        verify_server=verify_server,
        install_missing_checkers=install_missing_checkers,
        warm_cache_from_tech_stack=warm_cache_from_tech_stack,
        warm_expert_rag_from_tech_stack=warm_expert_rag_from_tech_stack,
        overwrite_platform_rules=overwrite_platform_rules,
        overwrite_agents_md=overwrite_agents_md,
        overwrite_tech_stack_md=overwrite_tech_stack_md,
        agent_teams=agent_teams,
        memory_auto_capture=memory_auto_capture,
        memory_auto_recall=memory_auto_recall,
        destructive_guard=destructive_guard,
        linear_enforce_gate=linear_enforce_gate,
        linear_enforce_cache_gate=linear_enforce_cache_gate,
        session_start_gate=session_start_gate,
        install_git_hooks=install_git_hooks,
        linear_sdlc=linear_sdlc,
        with_report_studio=with_report_studio,
        report_studio_tag=report_studio_tag,
        report_studio_scaffold=report_studio_scaffold,
        report_studio_template=report_studio_template,
        linear_issue_prefix=linear_issue_prefix,
        linear_team_id=linear_team_id,
        linear_project_id=linear_project_id,
        minimal=minimal,
        dry_run=dry_run,
        verify_only=verify_only,
        llm_engagement_level=llm_engagement_level or settings.llm_engagement_level,
        skill_tier=resolved_tier,
        scaffold_experts=scaffold_experts,
        include_karpathy=include_karpathy,
        mcp_bundle=mcp_bundle,
    )


def _update_action_dict(comp_val: Any) -> bool:
    """Check whether a platform component dict indicates an update."""
    if isinstance(comp_val, str) and comp_val in ("created", "updated", "regenerated"):
        return True
    return bool(
        isinstance(comp_val, dict)
        and comp_val.get("action") in ("created", "updated", "regenerated")
    )


async def emit_upgrade_progress(
    ctx: Context[Any, Any, Any] | None,
    result: dict[str, Any],
) -> None:
    """Emit ctx.info() for upgraded components."""
    components = result.get("components", {})
    agents_md = components.get("agents_md", {})
    if isinstance(agents_md, dict):
        action = agents_md.get("action", "")
        if action in ("created", "merged", "updated"):
            await emit_ctx_info(ctx, f"Updated AGENTS.md ({action})")
    for plat_result in components.get("platforms", []):
        host = plat_result.get("host", "unknown")
        for comp_name, comp_val in plat_result.get("components", {}).items():
            if _update_action_dict(comp_val):
                await emit_ctx_info(ctx, f"Updated {host}/{comp_name}")


def enrich_init_result_hints(
    result: dict[str, Any],
    *,
    add_other_mcps_hint: bool,
) -> None:
    """Populate the final hint/workflow fields on a ``tapps_init`` result dict."""
    from tapps_mcp.common.developer_workflow import get_developer_workflow_dict

    if add_other_mcps_hint:
        result["add_other_mcps_hint"] = (
            "See docs/MCP_COMPOSITION.md for guidance on adding GitHub, "
            "YouTube, Sentry, and other MCPs alongside TappsMCP."
        )
    result["agency_agents_hint"] = (
        "Optional: For persona voice (e.g. Frontend Developer), install "
        "https://github.com/msitarzewski/agency-agents and pair with TappsMCP "
        "domain skills (`/tapps-domain-frontend`, `/tapps-flow-frontend`). "
        "TappsMCP owns quality gates; agency-agents owns tone only."
    )
    result["consumer_requirements"] = (
        "For a full checklist of what you need to use most tools "
        "(server visibility, permissions, CLI fallback), "
        "see docs/TAPPS_MCP_REQUIREMENTS.md"
    )
    result["developer_workflow"] = get_developer_workflow_dict(
        setup_done=not result["errors"],
    )


#: TAP-6442: bootstrap_pipeline's error producers (pipeline/init*.py,
#: skills_validator.py) write free-form strings with no structured code, and
#: each embeds a variable substring (an exception message, a relative path)
#: that makes the raw string unstable to aggregate over. This maps the fixed
#: portion of each known message to a stable code; ordered by first match,
#: most specific first. Extend this list -- do not derive a code by slugging
#: the raw message -- when a new producer's error needs to be told apart.
_INIT_ERROR_CODE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("Karpathy guidelines install failed for", "karpathy_guidelines_failed"),
    ("Karpathy Cursor rule install failed", "karpathy_cursor_rule_failed"),
    ("GitHub templates:", "github_templates_failed"),
    ("CI workflows:", "ci_workflows_failed"),
    ("Copilot config:", "copilot_config_failed"),
    ("Governance:", "governance_failed"),
    ("start-program.sh:", "start_program_sh_failed"),
    ("Unknown platform:", "unknown_platform"),
    ("path escapes project root", "path_escapes_project_root"),
    ("Project profile detection failed", "project_profile_detection_failed"),
    ("Could not create TECH_STACK.md", "tech_stack_md_creation_failed"),
    ("AGENTS.md update failed", "agents_md_update_failed"),
    ("Cache warming failed", "cache_warming_failed"),
    ("Expert RAG failed for domains", "expert_rag_failed"),
    ("frontmatter missing", "skill_frontmatter_missing_field"),
    ("must be a string", "skill_frontmatter_wrong_type"),
    ("must be lowercase alphanumeric", "skill_name_invalid_format"),
    ("exceeds", "skill_frontmatter_field_too_long"),
)

INIT_ERROR_CODE_FALLBACK = "other_init_error"


def classify_init_error_code(message: str) -> str:
    """Derive a stable, aggregable error_code from the first tapps_init error.

    See :data:`_INIT_ERROR_CODE_PATTERNS`. Falls back to
    :data:`INIT_ERROR_CODE_FALLBACK` for a message this table does not
    recognise, rather than slugging the raw text -- a slug of free text
    carries no aggregation value once the variable part (an exception
    message, a path) dominates the string.
    """
    for needle, code in _INIT_ERROR_CODE_PATTERNS:
        if needle in message:
            return code
    return INIT_ERROR_CODE_FALLBACK


__all__ = [
    "INIT_ERROR_CODE_FALLBACK",
    "build_init_bootstrap_config",
    "classify_init_error_code",
    "emit_init_progress",
    "emit_upgrade_progress",
    "enrich_init_result_hints",
    "maybe_elicit_init_confirmation",
    "maybe_write_mcp_config",
    "resolve_write_mode_env",
    "restore_write_mode_env",
    "run_init_wizard_if_needed",
]


# Suppress "imported but unused" (asyncio may be used in future helpers)
_ = asyncio
