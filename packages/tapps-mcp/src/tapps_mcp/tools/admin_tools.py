"""Admin-facing MCP tools: ``tapps_init`` (project bootstrap).

Extracted from ``server_pipeline_tools.py`` (TAP-6881) to shrink that
module toward the maintainability gate. ``load_settings`` and
``success_response`` are looked up through ``tapps_mcp.server_pipeline_tools``
at call time (not imported directly here) so that
``patch("tapps_mcp.server_pipeline_tools.load_settings")`` in the existing
test suite keeps intercepting these calls regardless of which module
physically defines the tool body -- the same late-binding pattern already
used by ``tools/pipeline_init_helpers.py``.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from mcp.server.fastmcp import Context


async def tapps_init(
    create_handoff: bool = True,
    create_runlog: bool = True,
    create_agents_md: bool = True,
    create_tech_stack_md: bool = True,
    platform: str = "",
    verify_server: bool = True,
    install_missing_checkers: bool = False,
    warm_cache_from_tech_stack: bool = False,
    warm_expert_rag_from_tech_stack: bool = False,
    overwrite_platform_rules: bool = False,
    overwrite_agents_md: bool = False,
    overwrite_tech_stack_md: bool = False,
    agent_teams: bool = False,
    memory_auto_capture: bool = False,
    memory_auto_recall: bool = False,
    destructive_guard: bool | None = None,
    linear_enforce_gate: bool | None = None,
    linear_enforce_cache_gate: str | None = None,
    session_start_gate: str | None = None,
    install_git_hooks: bool | None = None,
    linear_sdlc: bool = False,
    with_report_studio: bool = False,
    report_studio_tag: str = "v0.1.3",
    report_studio_scaffold: str = "",
    report_studio_template: str = "architecture_theory",
    linear_issue_prefix: str = "TAP",
    linear_team_id: str = "",
    linear_project_id: str = "",
    minimal: bool = False,
    dry_run: bool = False,
    verify_only: bool = False,
    llm_engagement_level: str | None = None,
    scaffold_experts: bool = False,
    include_karpathy: bool = True,
    mcp_config: bool = True,
    mcp_bundle: str | None = None,
    output_mode: str = "auto",
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Bootstraps the TAPPS pipeline into a fresh project: writes
    ``AGENTS.md``, ``TECH_STACK.md``, ``.tapps-mcp.yaml``, platform rules
    (``.claude/`` or ``.cursor/``), git hooks, agents, and skills.

    By default also writes project-scoped MCP config (``mcp_config=True``):
    merges a ``tapps-mcp`` server entry, strips direct ``tapps-brain`` MCP
    keys (bridge-only, TAP-1888), and includes docs-mcp when bootstrap
    detects it. Pass ``mcp_config=False`` to scaffold pipeline files only.

    Call this when adding tapps-mcp to a new repo, or to add a previously
    disabled component (e.g., switching ``agent_teams`` on). For an
    existing install upgrading to a new tapps-mcp version use
    ``tapps_upgrade`` instead — it preserves user customizations that
    ``tapps_init`` may overwrite. Side effects: writes many files;
    creates or merges ``.tapps-mcp.yaml`` on first run.

    Set ``dry_run=True`` to preview the file set without writing, or
    ``verify_only=True`` to check whether the install is already
    complete without modifying anything. See package docs for the full
    flag matrix (``linear_sdlc``, ``scaffold_experts``,
    ``include_karpathy``, profile-specific bundles, etc.).
    """
    from tapps_mcp import server_pipeline_tools as _host
    from tapps_mcp.pipeline.init import bootstrap_pipeline
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges
    from tapps_mcp.tools import pipeline_init_helpers as _pih

    start = time.perf_counter_ns()
    _record_call("tapps_init")

    cancelled = await _pih.maybe_elicit_init_confirmation(ctx, start, verify_only, dry_run)
    if cancelled is not None:
        return cancelled

    (
        _wizard,
        llm_engagement_level,
        platform,
        agent_teams,
        add_other_mcps_hint,
    ) = await _pih.run_init_wizard_if_needed(
        ctx,
        verify_only=verify_only,
        dry_run=dry_run,
        llm_engagement_level=llm_engagement_level,
        platform=platform,
        agent_teams=agent_teams,
    )

    settings = _host.load_settings()
    mcp_bundle, mcp_bundle_reason = _pih.resolve_init_mcp_bundle(mcp_bundle, settings)
    dg = destructive_guard
    if dg is None:
        dg = getattr(settings, "destructive_guard", True)
    leg = linear_enforce_gate
    if leg is None:
        # TAP-981: engagement-aware default — true at high/medium, false at low.
        # Honors explicit overrides from .tapps-mcp.yaml or env.
        leg = settings.linear_enforce_gate_resolved()
    lcg = linear_enforce_cache_gate
    if lcg is None:
        # TAP-1224: engagement-aware default — "warn" at high/medium, "off" at low.
        lcg = settings.linear_enforce_cache_gate_resolved()
    ssg = session_start_gate
    if ssg is None:
        # Engagement-aware default — "warn" at high/medium, "off" at low.
        ssg = settings.session_start_gate_resolved()
    igh = install_git_hooks
    if igh is None:
        # TAP-979: opt-in git pre-commit hook.
        igh = getattr(settings, "install_git_hooks", False)

    cfg = _pih.build_init_bootstrap_config(
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
        destructive_guard=dg,
        linear_enforce_gate=leg,
        linear_enforce_cache_gate=lcg,
        session_start_gate=ssg,
        install_git_hooks=igh,
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
        llm_engagement_level=llm_engagement_level,
        scaffold_experts=scaffold_experts,
        include_karpathy=include_karpathy,
        mcp_bundle=mcp_bundle,
        settings=settings,
        wizard_answers=_wizard,
    )

    prev_write_mode = _pih.resolve_write_mode_env(output_mode)
    try:
        result = await asyncio.to_thread(
            bootstrap_pipeline,
            settings.project_root,
            config=cfg,
        )
    finally:
        _pih.restore_write_mode_env(prev_write_mode)

    result.update(mcp_bundle_chosen=mcp_bundle, mcp_bundle_reason=mcp_bundle_reason)
    _pih.maybe_write_mcp_config(
        result, settings, platform, mcp_config, dry_run, mcp_bundle=mcp_bundle
    )
    await _pih.emit_init_progress(ctx, result)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    init_errors = result["errors"]
    # TAP-6442: error_code aggregates the metrics row over a stable code
    # instead of the raw first-error string, which embeds an exception
    # message or path and would otherwise never repeat across calls.
    #
    # Only the first error is classified -- one code per failed call,
    # matching the one status per call the row already records. The
    # classification table itself lives in pipeline_init_helpers.py,
    # next to the other tapps_init-only helpers, not here.
    _record_execution(
        "tapps_init",
        start,
        status="success" if not init_errors else "failed",
        error_code=_pih.classify_init_error_code(init_errors[0]) if init_errors else None,
    )

    _pih.enrich_init_result_hints(result, add_other_mcps_hint=add_other_mcps_hint)
    resp = _host.success_response("tapps_init", elapsed_ms, result)
    resp["success"] = not result["errors"]
    return _with_nudges("tapps_init", resp)


__all__ = ["tapps_init"]
