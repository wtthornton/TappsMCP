"""Bootstrap TAPPS pipeline files in a consuming project.

This module is the ``tapps_init`` / ``tapps_upgrade`` entry point and the
stable import surface for the bootstrap subsystem.  The implementation lives
in focused siblings (TAP-5733), re-exported here so existing
``from tapps_mcp.pipeline.init import X`` call sites keep working:

- :mod:`~tapps_mcp.pipeline.init_state` — ``BootstrapConfig``, ``_BootstrapState``
- :mod:`~tapps_mcp.pipeline.init_permissions` — Claude permission entries and settings
- :mod:`~tapps_mcp.pipeline.init_claude_md` — CLAUDE.md / Cursor rule bootstrap
- :mod:`~tapps_mcp.pipeline.init_verification` — server verification, cache warming
- :mod:`~tapps_mcp.pipeline.init_tech_stack` — TECH_STACK.md rendering
- :mod:`~tapps_mcp.pipeline.init_github` — GitHub templates, CI, Copilot, governance
- :mod:`~tapps_mcp.pipeline.init_config_yaml` — comment-preserving .tapps-mcp.yaml writers
- :mod:`~tapps_mcp.pipeline.init_platform` — platform rules, hooks, agents, skills
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tapps_core.common.file_operations import (
    WriteMode,
    detect_write_mode,
)
from tapps_core.prompts.prompt_loader import (
    load_handoff_template,
    load_runlog_template,
)
from tapps_mcp import __version__
from tapps_mcp.pipeline.init_claude_md import (
    _bootstrap_claude,
    _bootstrap_cursor,
    _replace_tapps_section,
    _split_by_h1_headings,
)
from tapps_mcp.pipeline.init_config_yaml import (
    _ensure_cursor_stop_completion_gate_config,
    _ensure_memory_hooks_config,
    _memory_hooks_defaults_for_engagement,
)
from tapps_mcp.pipeline.init_permissions import (
    _CLAUDE_DENY_RULES,
    _CLAUDE_HIGH_ENGAGEMENT_PERMISSIONS,
    _CLAUDE_PERMISSION_ENTRIES,
    _CLAUDE_SETTINGS_SCHEMA,
    _NLT_PERMISSION_ENTRIES,
    _bootstrap_claude_settings,
    generate_permission_settings,
)
from tapps_mcp.pipeline.init_platform import (
    _generate_platform_file_ops,
    _install_karpathy_blocks,
    _karpathy_primary_home,
    _setup_platform,
)
from tapps_mcp.pipeline.init_state import BootstrapConfig, _BootstrapState
from tapps_mcp.pipeline.init_tech_stack import _render_tech_stack_md
from tapps_mcp.pipeline.init_verification import _run_server_verification, _warm_caches
from tapps_mcp.prompts.prompt_loader import (
    load_agents_template,
)

if TYPE_CHECKING:
    from pathlib import Path

# Backward-compatible import surface: these names moved to init_* siblings in
# TAP-5733 but are still imported from this module by tests and call sites.
__all__ = [
    "_CLAUDE_DENY_RULES",
    "_CLAUDE_HIGH_ENGAGEMENT_PERMISSIONS",
    "_CLAUDE_PERMISSION_ENTRIES",
    "_CLAUDE_SETTINGS_SCHEMA",
    "_NLT_PERMISSION_ENTRIES",
    "BootstrapConfig",
    "_BootstrapState",
    "_bootstrap_claude",
    "_bootstrap_claude_settings",
    "_bootstrap_cursor",
    "_ensure_cursor_stop_completion_gate_config",
    "_ensure_memory_hooks_config",
    "_karpathy_primary_home",
    "_memory_hooks_defaults_for_engagement",
    "_replace_tapps_section",
    "_split_by_h1_headings",
    "bootstrap_pipeline",
    "generate_permission_settings",
]


def bootstrap_pipeline(
    project_root: Path,
    config: BootstrapConfig | None = None,
    *,
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
    destructive_guard: bool = False,
    linear_enforce_gate: bool = False,
    linear_enforce_cache_gate: str = "off",
    session_start_gate: str = "off",
    install_git_hooks: bool = False,
    linear_sdlc: bool = False,
    linear_issue_prefix: str = "TAP",
    linear_team_id: str = "",
    linear_project_id: str = "",
    minimal: bool = False,
    dry_run: bool = False,
    verify_only: bool = False,
    llm_engagement_level: str | None = None,
    skill_tier: str | None = None,
    scaffold_experts: bool = False,
    include_karpathy: bool = True,
) -> dict[str, Any]:
    """Create pipeline template files in the project.

    Pass *config* to use a pre-built :class:`BootstrapConfig`, or use keyword
    arguments. Keyword args are ignored when *config* is provided.

    When ``dry_run=True``, computes and returns the same result structure
    without writing files or warming caches. Skips server verification in
    dry_run to keep it lightweight.

    When ``verify_only=True``, runs only server verification and returns
    immediately (fast, ~1-3s). Use for quick connectivity/checker checks.

    Returns a summary dict with ``created``, ``skipped``, ``errors``, and
    subsystem result dicts.
    """
    if config is not None:
        cfg = config
    else:
        cfg = BootstrapConfig.from_params(
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
            memory_auto_recall=memory_auto_recall,
            memory_auto_capture=memory_auto_capture,
            destructive_guard=destructive_guard,
            linear_enforce_gate=linear_enforce_gate,
            linear_enforce_cache_gate=linear_enforce_cache_gate,
            session_start_gate=session_start_gate,
            install_git_hooks=install_git_hooks,
            linear_sdlc=linear_sdlc,
            linear_issue_prefix=linear_issue_prefix,
            linear_team_id=linear_team_id,
            linear_project_id=linear_project_id,
            minimal=minimal,
            dry_run=dry_run,
            verify_only=verify_only,
            llm_engagement_level=llm_engagement_level,
            skill_tier=skill_tier,
            scaffold_experts=scaffold_experts,
            include_karpathy=include_karpathy,
        )
    # Determine write mode: direct (local) or content-return (Docker/read-only)
    resolved_root = project_root.resolve()
    write_mode = detect_write_mode(resolved_root) if not cfg.dry_run else WriteMode.DIRECT_WRITE

    state = _BootstrapState(
        project_root=resolved_root,
        dry_run=cfg.dry_run,
        write_mode=write_mode,
    )

    # Content-return mode: generate files without writing (Epic 87)
    if state.content_return and not cfg.verify_only:
        import structlog

        structlog.get_logger(__name__).info(
            "content_return_mode",
            project_root=str(project_root),
            reason="read-only filesystem or TAPPS_WRITE_MODE=content",
        )

    _verify_server(cfg, state)
    if cfg.verify_only:
        return state.finalize()

    if not cfg.dry_run:
        from tapps_mcp.distribution.doctor import strip_brain_mcp_entries

        state.result["brain_mcp_strip"] = strip_brain_mcp_entries(
            state.project_root,
            dry_run=False,
        )

    _detect_profile(cfg, state)
    _detect_docsmcp(state)
    _create_templates(cfg, state)
    if state.content_return:
        # Content-return mode (Epic 87): generate platform files as
        # FileOperations instead of writing them directly.  Platform
        # generators write to disk, so we generate the key files from
        # template loaders and skip side-effects (cache warming, etc.).
        _generate_platform_file_ops(cfg, state)
        state.result["cache_warming"] = {
            "warmed": 0,
            "attempted": 0,
            "skipped": "content_return",
            "libraries": [],
        }
        state.result["expert_rag_warming"] = {
            "warmed": 0,
            "attempted": 0,
            "skipped": "content_return",
            "domains": [],
        }
    elif not cfg.dry_run:
        _setup_platform(cfg, state)
        _install_karpathy_blocks(cfg, state)
        # Ensure Claude Code permissions even when platform != "claude",
        # if the .claude/ directory already exists (user is in Claude Code).
        if cfg.platform != "claude" and (state.project_root / ".claude").is_dir():
            settings_action = _bootstrap_claude_settings(
                state.project_root,
                engagement_level=cfg.llm_engagement_level,
                docsmcp_detected=state.result.get("docsmcp_detected", False),
            )
            state.result["claude_settings"] = {"action": settings_action}
            if settings_action == "created":
                state.created.append(".claude/settings.json")
        if cfg.minimal:
            state.result["cache_warming"] = {
                "warmed": 0,
                "attempted": 0,
                "skipped": "minimal",
                "libraries": [],
            }
            state.result["expert_rag_warming"] = {
                "warmed": 0,
                "attempted": 0,
                "skipped": "minimal",
                "domains": [],
            }
        else:
            _warm_caches(cfg, state)
    else:
        state.result["platform_rules"] = {
            "platform": cfg.platform or "(none)",
            "action": "skipped",
            "reason": "dry_run",
        }
        state.result["cache_warming"] = {
            "warmed": 0,
            "attempted": 0,
            "skipped": "dry_run",
            "libraries": [],
        }
        state.result["expert_rag_warming"] = {
            "warmed": 0,
            "attempted": 0,
            "skipped": "dry_run",
            "domains": [],
        }

    if state.content_return:
        manifest = state.build_manifest()
        result = state.finalize()
        result["file_manifest"] = manifest.to_full_response_data()
        result["content_return"] = True
        return result

    if not cfg.dry_run:
        from tapps_mcp.distribution.setup_generator import ensure_tapps_runtime_gitignore

        added = ensure_tapps_runtime_gitignore(project_root)
        state.result["runtime_gitignore"] = {
            "action": "updated" if added else "unchanged",
            "added": added,
        }

    return state.finalize()


def _detect_docsmcp(state: _BootstrapState) -> bool:
    """Detect whether DocsMCP is available (importable or in project deps).

    Checks:
    1. Whether ``docs_mcp`` is importable in the current environment.
    2. Whether ``docs-mcp`` appears in any ``pyproject.toml`` or
       ``requirements*.txt`` in the project root.

    Stores the result in ``state.result["docsmcp_detected"]``.
    """
    # Check importability
    try:
        import importlib

        importlib.import_module("docs_mcp")
    except ImportError:
        pass
    else:
        state.result["docsmcp_detected"] = True
        return True

    # Check project dependencies
    from pathlib import Path as _Path

    root = _Path(state.project_root)

    # Check pyproject.toml
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text(encoding="utf-8")
            if "docs-mcp" in content or "docs_mcp" in content:
                state.result["docsmcp_detected"] = True
                return True
        except OSError:
            pass

    # Check requirements files
    for req_file in root.glob("requirements*.txt"):
        try:
            content = req_file.read_text(encoding="utf-8")
            if "docs-mcp" in content or "docs_mcp" in content:
                state.result["docsmcp_detected"] = True
                return True
        except OSError:
            pass

    state.result["docsmcp_detected"] = False
    return False


def _verify_server(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Run server verification and optional checker install.

    When dry_run=True, skips actual subprocess calls (checker detection) to keep
    dry_run lightweight; returns a placeholder instead.

    Stays in this module rather than ``init_verification``: tests patch
    ``tapps_mcp.pipeline.init._run_server_verification``, which only binds if
    the caller resolves that name from this module's globals.
    """
    if cfg.dry_run and (cfg.verify_server or cfg.install_missing_checkers):
        state.result["server_verification"] = {
            "ok": True,
            "skipped": "dry_run",
            "message": "Server verification skipped in dry_run"
            " (use verify_only for actual verification)",
        }
    elif cfg.verify_server or cfg.install_missing_checkers:
        state.result["server_verification"] = _run_server_verification(
            state.project_root,
            install_missing=cfg.install_missing_checkers,
        )
    else:
        state.result["server_verification"] = {"ok": True, "skipped": True}


def _detect_profile(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Detect project profile if needed for tech stack or cache warming."""
    if cfg.create_tech_stack_md or cfg.warm_cache_from_tech_stack:
        try:
            from tapps_mcp.project.profiler import detect_project_profile

            state.profile = detect_project_profile(state.project_root)
        except Exception as exc:
            state.errors.append(f"Project profile detection failed: {exc}")


def _create_templates(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Create handoff, runlog, agents, and tech stack templates."""
    if not cfg.minimal:
        if cfg.create_handoff:
            state.safe_write("docs/TAPPS_HANDOFF.md", load_handoff_template())
        if cfg.create_runlog:
            state.safe_write("docs/TAPPS_RUNLOG.md", load_runlog_template())

    # AGENTS.md
    if cfg.create_agents_md:
        _create_agents_md(cfg, state)
    else:
        state.result["agents_md"] = {"action": "skipped", "reason": "disabled"}

    # TECH_STACK.md
    if cfg.create_tech_stack_md and state.profile is not None:
        tech_stack_path = state.project_root / "TECH_STACK.md"
        if tech_stack_path.exists() and not cfg.overwrite_tech_stack_md:
            state.result["tech_stack_md"] = {"action": "preserved"}
        else:
            content = _render_tech_stack_md(state.profile)
            action = state.safe_write_or_overwrite("TECH_STACK.md", content)
            state.result["tech_stack_md"] = {"action": action}
    elif cfg.create_tech_stack_md:
        state.result["tech_stack_md"] = {"action": "skipped", "reason": "profile_failed"}
        state.errors.append("Could not create TECH_STACK.md: project profile detection failed")
    else:
        state.result["tech_stack_md"] = {"action": "skipped", "reason": "disabled"}

    # docs/TAPPS_WORKFLOW.md (Setup / Update / Daily reference)
    if not state.dry_run:
        from tapps_mcp.common.developer_workflow import render_workflow_md

        action = state.safe_write_or_overwrite("docs/TAPPS_WORKFLOW.md", render_workflow_md())
        state.result["workflow_doc"] = {"action": action}


def _create_agents_md(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Create or update AGENTS.md."""
    agents_path = state.project_root / "AGENTS.md"
    template_content = load_agents_template(cfg.llm_engagement_level)
    if agents_path.exists():
        from tapps_mcp.pipeline.agents_md import update_agents_md

        try:
            action, detail = update_agents_md(
                agents_path,
                template_content,
                overwrite=cfg.overwrite_agents_md,
            )
            state.result["agents_md"] = {"action": action, **detail}
            if action == "validated":
                state.skipped.append("AGENTS.md")
        except Exception as exc:
            state.errors.append(f"AGENTS.md update failed: {exc}")
            state.result["agents_md"] = {"action": "error", "reason": str(exc)}
    else:
        state.safe_write("AGENTS.md", template_content)
        state.result["agents_md"] = {"action": "created", "version": __version__}
