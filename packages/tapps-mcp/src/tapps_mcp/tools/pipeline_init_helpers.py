"""Helper functions for ``tapps_init`` and ``tapps_upgrade``.

Extracted from ``server_pipeline_tools.py`` to keep that module a thin
orchestrator.  Functions here are private helpers and are not exposed
as MCP tools.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context

from tapps_mcp.server_helpers import emit_ctx_info, success_response

if TYPE_CHECKING:
    pass


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


def maybe_write_mcp_config(
    result: dict[str, Any],
    settings: Any,
    platform: str,
    mcp_config: bool,
    dry_run: bool,
) -> None:
    """Write project-scoped MCP config when opt-in (Epic 47.2)."""
    if not mcp_config or dry_run:
        return

    from tapps_mcp.distribution.setup_generator import _generate_config

    mcp_host = "claude-code"
    if platform == "cursor":
        mcp_host = "cursor"
    elif platform == "vscode":
        mcp_host = "vscode"

    config_ok = _generate_config(
        mcp_host,
        settings.project_root,
        force=True,
        scope="project",
    )
    if config_ok:
        result["mcp_config_written"] = True
        result["mcp_config_scope"] = "project"


async def emit_init_progress(
    ctx: Context[Any, Any, Any] | None, result: dict[str, Any]
) -> None:
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
    memory_capture: bool,
    memory_auto_capture: bool,
    memory_auto_recall: bool,
    destructive_guard: bool,
    linear_enforce_gate: bool,
    minimal: bool,
    dry_run: bool,
    verify_only: bool,
    llm_engagement_level: str | None,
    scaffold_experts: bool,
    include_karpathy: bool,
    settings: Any,
) -> Any:
    """Assemble the :class:`BootstrapConfig` used by :func:`bootstrap_pipeline`."""
    from tapps_mcp.pipeline.init import BootstrapConfig

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
        memory_capture=memory_capture,
        memory_auto_capture=memory_auto_capture,
        memory_auto_recall=memory_auto_recall,
        destructive_guard=destructive_guard,
        linear_enforce_gate=linear_enforce_gate,
        minimal=minimal,
        dry_run=dry_run,
        verify_only=verify_only,
        llm_engagement_level=llm_engagement_level or settings.llm_engagement_level,
        scaffold_experts=scaffold_experts,
        include_karpathy=include_karpathy,
    )


def _update_action_dict(comp_val: Any) -> bool:
    """Check whether a platform component dict indicates an update."""
    if isinstance(comp_val, str) and comp_val in ("created", "updated", "regenerated"):
        return True
    if isinstance(comp_val, dict) and comp_val.get("action") in (
        "created",
        "updated",
        "regenerated",
    ):
        return True
    return False


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
        "Optional: For more specialized agents (e.g. Frontend Developer, Reality Checker), "
        "see https://github.com/msitarzewski/agency-agents and run their install script for your platform."
    )
    result["consumer_requirements"] = (
        "For a full checklist of what you need to use most tools "
        "(server visibility, permissions, CLI fallback), "
        "see docs/TAPPS_MCP_REQUIREMENTS.md"
    )
    result["developer_workflow"] = get_developer_workflow_dict(
        setup_done=not result["errors"],
    )


__all__ = [
    "build_init_bootstrap_config",
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
