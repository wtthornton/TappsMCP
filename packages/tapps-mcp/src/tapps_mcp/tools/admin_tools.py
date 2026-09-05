"""Admin-facing MCP tools: ``tapps_init``, ``tapps_upgrade``,
``tapps_set_engagement_level``, ``tapps_doctor``.

Extracted from ``server_pipeline_tools.py`` (TAP-6881) to shrink that
module toward the maintainability gate. ``load_settings``, response
builders, and session-start module state (``_SESSION_START_CACHE``,
``_prepend_next_step``) are looked up through
``tapps_mcp.server_pipeline_tools`` at call time (not imported directly
here) so that ``patch("tapps_mcp.server_pipeline_tools.load_settings")``
in the existing test suite keeps intercepting these calls regardless of
which module physically defines the tool body -- the same late-binding
pattern already used by ``tools/pipeline_init_helpers.py``.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Literal

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
    from tapps_mcp.server_helpers import success_response
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
    resp = success_response("tapps_init", elapsed_ms, result)
    resp["success"] = not result["errors"]
    return _with_nudges("tapps_init", resp)


async def tapps_upgrade(
    platform: str = "",
    force: bool = False,
    dry_run: bool = False,
    output_mode: str = "auto",
    mcp_only: bool = False,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Refreshes TappsMCP-managed scaffolding (agents, skills, hooks,
    ``AGENTS.md``, platform rules, ``.mcp.json``) after a tapps-mcp
    version bump, preserving consumer customizations.

    Call this after upgrading the tapps-mcp package (``uv tool install
    --reinstall``) — the new package may ship updated templates that
    existing scaffolding does not pick up automatically. For a brand-new
    install use ``tapps_init`` instead; this tool assumes the project
    was already initialized. Always preview with ``dry_run=True`` first
    when the project has heavy customizations; the response's
    ``dry_run_summary.verdict`` flags whether any user-editable files
    (``CLAUDE.md``, hook merges) would be touched.

    Writes are scoped to tapps-managed names (the four ``tapps-*``
    subagents, the ``tapps-*`` + ``linear-issue`` skills, ``tapps-*``
    hook scripts). Consumer-authored agents/skills/hooks with other
    names are preserved. ``AGENTS.md`` uses section-aware merge;
    ``.claude/settings.json`` hooks are merged by matcher (no entries
    removed). A timestamped backup is created at
    ``.tapps-mcp/backups/`` before any write.

    Args:
        platform: Restrict the upgrade to one platform bundle:
            ``"claude-code"``, ``"cursor"``, or ``"vscode"``. Empty
            (default) upgrades all detected platforms.
        force: Overwrite consumer files even when the section-aware
            merge would normally preserve them. Default ``False``;
            enable only after reviewing the ``dry_run`` diff.
        dry_run: Return the upgrade plan with a per-component breakdown
            and a top-level ``dry_run_summary`` (``verdict``,
            ``managed_file_count``, ``preserved_files``,
            ``review_recommended_for``, ``skipped_components``) without
            writing anything. Use this before any real upgrade on a
            customized project.
        output_mode: ``"auto"`` (default), ``"writes"``, or
            ``"content"`` — controls whether the response embeds file
            contents (for sandboxed servers that cannot write directly)
            or just file-system writes (the default for local servers).
        mcp_only: When ``True``, refresh only ``.mcp.json`` (and the
            sibling Cursor/VS Code mirrors); skip agents, skills, hooks,
            and prompt templates. Use after an ``.mcp.json``-only change
            like the Context7 default-env wiring.
    """
    from tapps_mcp import server_pipeline_tools as _host
    from tapps_mcp.pipeline.upgrade import upgrade_pipeline
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges
    from tapps_mcp.server_helpers import emit_ctx_info, success_response
    from tapps_mcp.tools import pipeline_init_helpers as _pih

    start = time.perf_counter_ns()
    _record_call("tapps_upgrade")

    settings = _host.load_settings()

    if not dry_run:
        await emit_ctx_info(ctx, "Creating backup...")

    prev_write_mode = _pih.resolve_write_mode_env(output_mode)
    try:
        result = upgrade_pipeline(
            settings.project_root,
            platform=platform,
            force=force,
            dry_run=dry_run,
            mcp_only=mcp_only,
        )
    finally:
        _pih.restore_write_mode_env(prev_write_mode)

    if not dry_run:
        await _pih.emit_upgrade_progress(ctx, result)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution(
        "tapps_upgrade",
        start,
        status="success" if result.get("success") else "failed",
    )

    resp = success_response("tapps_upgrade", elapsed_ms, result)
    return _with_nudges("tapps_upgrade", resp)


def tapps_set_engagement_level(level: Literal["high", "medium", "low"]) -> dict[str, Any]:
    """Persists the project's LLM engagement level to ``.tapps-mcp.yaml``,
    which controls how aggressively tapps-mcp enforces the quality pipeline.

    Call this once when adopting tapps-mcp, or to dial the friction up or
    down: ``high`` (full RFC-2119 obligations in AGENTS.md, blocking
    gates), ``medium`` (default; recommended trigger phrasing), ``low``
    (advisory hints only). After setting, re-run
    ``tapps_init(overwrite_agents_md=True)`` to regenerate ``AGENTS.md``
    and platform rules with the new level — the YAML alone does not
    propagate into the agent-visible prompts.

    Args:
        level: One of ``"high"``, ``"medium"`` (recommended default),
            or ``"low"``. Any other value returns
            ``error.code=invalid_level``.
    """
    import yaml

    from tapps_core.common.file_operations import WriteMode, detect_write_mode
    from tapps_core.security.path_validator import PathValidator
    from tapps_mcp import server_pipeline_tools as _host
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges
    from tapps_mcp.server_helpers import error_response, success_response
    from tapps_mcp.tools import engagement_level as _el

    start = time.perf_counter_ns()
    _record_call("tapps_set_engagement_level")

    valid = ("high", "medium", "low")
    if level not in valid:
        # Runtime guard kept as defence in depth: a non-MCP caller (CLI,
        # direct import) bypasses the schema-level enum entirely.
        _record_execution(
            "tapps_set_engagement_level",
            start,
            status="failed",
            error_code="invalid_level",
        )
        return error_response(
            "tapps_set_engagement_level",
            "invalid_level",
            f"Invalid level {level!r}. Use one of: {', '.join(valid)}",
        )

    settings = _host.load_settings()
    root = Path(settings.project_root)
    validator = PathValidator(root)
    try:
        config_path = validator.validate_write_path(".tapps-mcp.yaml")
    except Exception as exc:
        _record_execution(
            "tapps_set_engagement_level",
            start,
            status="failed",
            error_code="path_denied",
        )
        return error_response(
            "tapps_set_engagement_level",
            "path_denied",
            str(exc),
        )

    loaded = _el.read_engagement_yaml(config_path)
    if isinstance(loaded, str):
        _record_execution(
            "tapps_set_engagement_level",
            start,
            status="failed",
            error_code="config_read_error",
        )
        return error_response("tapps_set_engagement_level", "config_read_error", loaded)

    data = loaded
    data["llm_engagement_level"] = level

    write_mode = detect_write_mode(root)
    yaml_content = yaml.dump(data, default_flow_style=False, sort_keys=False)

    if write_mode == WriteMode.DIRECT_WRITE:
        err = _el.write_engagement_yaml(config_path, yaml_content)
        if err is not None:
            _record_execution(
                "tapps_set_engagement_level",
                start,
                status="failed",
                error_code="config_write_error",
            )
            return error_response("tapps_set_engagement_level", "config_write_error", err)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_set_engagement_level", start)

    next_step = (
        "Run tapps_init with overwrite_agents_md=True (and platform if needed) "
        "to regenerate AGENTS.md and platform rules with the new level."
    )
    msg = f"Engagement level set to {level!r}. {next_step}"
    result_data: dict[str, Any] = {"level": level, "message": msg}

    if write_mode == WriteMode.CONTENT_RETURN:
        result_data["content_return"] = True
        result_data["file_manifest"] = _el.engagement_manifest(yaml_content, level, settings)

    resp = success_response(
        "tapps_set_engagement_level",
        elapsed_ms,
        result_data,
    )
    return _with_nudges("tapps_set_engagement_level", resp)


def tapps_doctor(
    project_root: str = "",
    quick: bool = False,
    include_passing: bool = False,
) -> dict[str, Any]:
    """Diagnoses TappsMCP configuration, checker installation, brain
    connectivity, cache health, install-drift, and Linear-write
    sentinel state; returns pass/fail per check with remediation hints.

    Call this when something feels wrong (lookups returning ``degraded``,
    brain probes failing, ``ENOENT`` from a checker) — it's the
    structured equivalent of ``tapps-mcp doctor`` on the CLI. For
    routine session startup use ``tapps_session_start`` (which embeds a
    subset of these checks); use ``tapps_doctor`` only when triaging.

    Args:
        project_root: Override the project root (default: server-configured
            root). Useful when running the doctor against a sibling repo
            from a long-lived server process.
        quick: Skip the slow subprocess probes (``ruff --version``,
            ``pip-audit --version``, etc.) and return cached versions.
            Default ``False``; the full diagnostic is what you usually
            want for triage.
        include_passing: Include ``severity == "pass"`` rows in ``checks``.
            Default ``False`` (TAP-6433) — triage only needs the warn/fail
            rows; ``pass_count``/``all_passed`` still reflect every check
            regardless. Pass ``True`` to see the full row-by-row report.
    """
    from tapps_mcp import server_pipeline_tools as _host
    from tapps_mcp.distribution.doctor import run_doctor_structured
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges
    from tapps_mcp.server_helpers import success_response
    from tapps_mcp.tools import doctor_tool_helpers as _dth
    from tapps_mcp.tools import session_health as _sh

    start = time.perf_counter_ns()
    _record_call("tapps_doctor")

    settings = _host.load_settings()
    root = Path(project_root or str(settings.project_root))

    # TAP-6900 / TAP-6901: was this session bootstrapped for real, and is this
    # the build that is installed on disk? A memoized session_start answers
    # success without running, and __version__ is frozen at process import.
    # run_doctor_structured attaches both blocks, so `tapps-mcp doctor` reports
    # them from the same helper instead of the MCP path alone. This is the only
    # caller holding a session-start memo, and the only one entitled to call
    # itself the server process — every other caller under-claims by default.
    result = run_doctor_structured(
        project_root=str(root),
        quick=quick,
        include_passing=include_passing,
        memo_cache=_host._SESSION_START_CACHE,
        probe_role=_sh.PROBE_ROLE_SERVER,
    )

    # TAP-1333: surface 7-day MCP-call ratio + gate-skip rate.
    result["loop_metrics_7d"] = _dth.doctor_loop_metrics(root)

    # TAP-1414: surface ruff/mypy missing as a top-level field for parity with
    # tapps_session_start. The per-tool checks already include install hints,
    # but agents reading the doctor result programmatically need a single
    # field to react to.
    degraded = _dth.doctor_degraded_checkers(root)
    if degraded is not None:
        result["degraded_checkers"], result["degraded_checkers_warning"] = degraded

    # TAP-2453: surface last 5 background push-test results so failures are
    # visible without digging into .tapps-mcp/.push-test-log manually.
    push_test_log = _dth.doctor_push_test_log(root)
    if push_test_log is not None:
        result["push_test_log"] = push_test_log

    # Completion-gate Stop-hook presence (warn-mode telemetry path).
    # When missing, the agent gets no "edits without validation" warn at end-of-turn.
    completion_gate_hook = _dth.doctor_completion_gate_hook(root, _host.load_settings)
    if completion_gate_hook is not None:
        result["completion_gate_hook"] = completion_gate_hook

    # Usage gap summary (per-session). Surfaces edits-without-validation,
    # lookup-docs-underused, etc. from tapps_usage tool data sources.
    usage_gaps = _dth.doctor_usage_gaps(root)
    if usage_gaps is not None:
        result["usage_gaps"] = usage_gaps

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_doctor", start)

    resp = success_response("tapps_doctor", elapsed_ms, result)
    resp = _with_nudges("tapps_doctor", resp)
    if result.get("degraded_checkers_warning"):
        _host._prepend_next_step(resp, result["degraded_checkers_warning"])
    if result.get("completion_gate_hook", {}).get("warning"):
        _host._prepend_next_step(resp, result["completion_gate_hook"]["warning"])
    _sh.prepend_session_health_warnings(resp, result, _host._prepend_next_step)
    return resp


__all__ = ["tapps_doctor", "tapps_init", "tapps_set_engagement_level", "tapps_upgrade"]
