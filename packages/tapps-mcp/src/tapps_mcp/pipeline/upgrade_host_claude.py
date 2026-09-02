"""claude-code artifact upgrades under one shared plan (TAP-6913).

Every component resolves through
:func:`~tapps_mcp.pipeline.upgrade_host_context.resolve_component`, so the
skip-token check, the language/infra gate, and the managed-file plan are
computed identically whether the caller asked for a dry-run preview or a live
write. ``dry_run`` selects the last step only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import Any

from tapps_core.common.logging import get_logger
from tapps_mcp.pipeline.upgrade_docs import dry_run_claude_md_status
from tapps_mcp.pipeline.upgrade_hooks_migration import migrate_retired_hooks, verify_hook_manifest
from tapps_mcp.pipeline.upgrade_host_context import (
    Gate,
    HookFlags,
    HostContext,
    apply_docs_automation,
    apply_skills,
    docsmcp_gate,
    plan_skills,
    record_hooks_parse_error,
    resolve_component,
)
from tapps_mcp.pipeline.upgrade_report import enumerate_preserved, skipped

log = get_logger(__name__)


def _promote_gate(
    ctx: HostContext,
    key: str,
    probe: Callable[[str], tuple[bool, dict[str, Any]]],
    current: str,
) -> str:
    """Run one warn→block auto-promotion probe and record its telemetry.

    Read-only: the probe only reads rolling loop metrics, so dry-run runs it
    too and previews the same gate value the live run would deploy (TAP-6913).
    """
    try:
        promote, telemetry = probe(current)
    except Exception:
        log.debug("auto_promote_probe_failed", gate=key, exc_info=True)
        return current
    ctx.result.setdefault("auto_promote", {})[key] = telemetry
    if not promote:
        return current
    telemetry.update({"promoted": True, "from": "warn", "to": "block"})
    return "block"


def resolve_hook_flags(ctx: HostContext) -> HookFlags:
    """Apply the TAP-1333 warn→block auto-promotions to the configured flags."""
    from tapps_core.config.settings import load_settings
    from tapps_mcp.tools.loop_metrics import (
        should_auto_promote_cache_gate,
        should_auto_promote_session_start_gate,
    )

    try:
        settings = load_settings()
    except Exception:
        log.debug("auto_promote_settings_load_failed", exc_info=True)
        return ctx.hook_flags

    flags = ctx.hook_flags
    cache_gate = _promote_gate(
        ctx,
        "cache_gate",
        lambda current: should_auto_promote_cache_gate(
            ctx.project_root,
            current_mode=current,
            auto_promote_enabled=getattr(settings, "linear_enforce_cache_gate_auto_promote", True),
        ),
        flags.linear_enforce_cache_gate,
    )
    session_gate = _promote_gate(
        ctx,
        "session_start_gate",
        lambda current: should_auto_promote_session_start_gate(
            ctx.project_root,
            current_mode=current,
            auto_promote_enabled=getattr(settings, "session_start_gate_auto_promote", True),
        ),
        flags.session_start_gate,
    )
    return replace(
        flags,
        linear_enforce_cache_gate=cache_gate,
        session_start_gate=session_gate,
    )


def _conditional_hook_scripts(flags: HookFlags) -> list[str]:
    """Opt-in gate scripts that ship only when their flag is enabled.

    Surfaced explicitly so consumers can see what the flags will write.
    Bash-only (no Windows variants).
    """
    scripts: list[str] = []
    if flags.destructive_guard:
        scripts.append("tapps-pre-bash.sh")
    if flags.linear_enforce_gate:
        scripts.extend(["tapps-pre-linear-write.sh", "tapps-post-docs-validate.sh"])
    if flags.linear_enforce_cache_gate in {"warn", "block"}:
        scripts.extend(
            [
                "tapps-pre-linear-list.sh",
                "tapps-post-linear-snapshot-get.sh",
                "tapps-post-linear-list.sh",
            ]
        )
    if flags.session_start_gate in {"warn", "block"}:
        scripts.extend(["tapps-pre-session-start-gate.sh", "tapps-post-session-start.sh"])
    return scripts


def _plan_claude_hooks(ctx: HostContext, flags: HookFlags) -> dict[str, Any]:
    """The set of hook scripts a run would write, plus the files it leaves alone."""
    hooks_dir = ctx.project_root / ".claude" / "hooks"
    managed_hooks = (
        frozenset(p.name for p in hooks_dir.glob("tapps-*")) if hooks_dir.is_dir() else frozenset()
    )
    component: dict[str, Any] = {
        "action": "would-write-managed-scripts",
        "note": "settings.json hooks merged by matcher — existing entries preserved",
        "preserved_files": enumerate_preserved(hooks_dir, managed_hooks),
    }
    conditional_managed = _conditional_hook_scripts(flags)
    if conditional_managed:
        component["managed_files"] = sorted(conditional_managed)
    component["destructive_guard"] = flags.destructive_guard
    component["linear_enforce_gate"] = flags.linear_enforce_gate
    component["linear_enforce_cache_gate"] = flags.linear_enforce_cache_gate
    component["session_start_gate"] = flags.session_start_gate
    return component


def _apply_claude_hooks(ctx: HostContext, flags: HookFlags) -> dict[str, Any]:
    """Generate the hook scripts, migrate retired wiring, and wire memory hooks."""
    from tapps_mcp.pipeline.platform_generators import generate_claude_hooks
    from tapps_mcp.pipeline.platform_hooks import wire_memory_hooks

    hooks_result = generate_claude_hooks(
        ctx.project_root,
        engagement_level=ctx.engagement_level,
        destructive_guard=flags.destructive_guard,
        linear_enforce_gate=flags.linear_enforce_gate,
        linear_enforce_cache_gate=flags.linear_enforce_cache_gate,
        session_start_gate=flags.session_start_gate,
    )
    component = {
        "scripts_created": hooks_result.get("scripts_created", []),
        "hooks_added": hooks_result.get("hooks_added", 0),
        "destructive_guard": hooks_result.get("destructive_guard", False),
        "linear_enforce_gate": hooks_result.get("linear_enforce_gate", False),
        "linear_enforce_cache_gate": hooks_result.get("linear_enforce_cache_gate", "off"),
        "session_start_gate": hooks_result.get("session_start_gate", "off"),
        "manifest_verification": verify_hook_manifest(ctx.project_root),
    }
    # Migrate retired hook wiring: rename the fail-open destructive guard to its
    # fail-closed replacement, unwire the no-op memory-capture hook, and delete
    # retired files. Runs after generation (which redeploys the canonical
    # replacement) so the rename target exists.
    ctx.result["components"]["retired_hooks"] = migrate_retired_hooks(ctx.project_root)
    ctx.result["components"]["memory_hooks"] = wire_memory_hooks(
        ctx.project_root, platform="claude"
    )
    return component


def _resolve_claude_hooks(ctx: HostContext) -> None:
    """Resolve ``settings`` then ``hooks`` — the latter is blocked by a bad former."""
    from tapps_mcp.pipeline.init import _bootstrap_claude_settings
    from tapps_mcp.pipeline.platform_hooks import ManagedJsonError, dry_run_managed_json_status

    settings_status = resolve_component(
        ctx,
        "settings",
        skip_key="claude_settings",
        plan=lambda: dry_run_managed_json_status(
            ctx.project_root / ".claude" / "settings.json",
            ok_message="would-merge (hooks merged by matcher; existing entries preserved)",
        ),
        apply=lambda: _bootstrap_claude_settings(
            ctx.project_root, engagement_level=ctx.engagement_level
        ),
    )

    if skipped("claude_hooks", ctx.skip):
        ctx.result["components"]["hooks"] = "skipped (upgrade_skip_files)"
        return
    if isinstance(settings_status, dict) and settings_status.get("action") == "error":
        ctx.result["components"]["hooks"] = {
            "action": "skipped",
            "note": "blocked by malformed .claude/settings.json (see settings component)",
        }
        return

    flags = resolve_hook_flags(ctx)
    try:
        ctx.result["components"]["hooks"] = (
            _plan_claude_hooks(ctx, flags) if ctx.dry_run else _apply_claude_hooks(ctx, flags)
        )
    except ManagedJsonError as exc:
        record_hooks_parse_error(ctx, exc)


def _resolve_claude_assets(ctx: HostContext) -> None:
    """Agents, skills, Workflow scripts, and docs-automation skills."""
    from tapps_mcp.pipeline.platform_docs_automation import CLAUDE_DOCS_SKILLS
    from tapps_mcp.pipeline.platform_generators import (
        generate_skills,
        generate_subagent_definitions,
    )
    from tapps_mcp.pipeline.platform_skills import CLAUDE_SKILLS
    from tapps_mcp.pipeline.platform_subagents import CLAUDE_AGENTS

    managed_agents = frozenset(CLAUDE_AGENTS.keys())
    resolve_component(
        ctx,
        "agents",
        skip_key="claude_agents",
        plan=lambda: {
            "action": "would-write-managed-files",
            "managed_files": sorted(managed_agents),
            "preserved_files": enumerate_preserved(
                ctx.project_root / ".claude" / "agents", managed_agents
            ),
        },
        apply=lambda: generate_subagent_definitions(ctx.project_root, "claude", overwrite=True),
    )

    resolve_component(
        ctx,
        "skills",
        skip_key="claude_skills",
        plan=lambda: plan_skills(ctx, "claude", CLAUDE_SKILLS),
        apply=lambda: apply_skills(
            ctx,
            "claude",
            lambda: generate_skills(
                ctx.project_root,
                "claude",
                overwrite=True,
                engagement_level=ctx.engagement_level,
                skill_tier=ctx.skill_tier,
            ),
        ),
    )

    resolve_component(
        ctx,
        "workflows",
        skip_key="claude_workflows",
        plan=lambda: _plan_workflow_scripts(),
        apply=lambda: _apply_workflow_scripts(ctx),
    )

    resolve_component(
        ctx,
        "docs_automation",
        skip_key="docs_automation",
        gate=docsmcp_gate(ctx.project_root),
        plan=lambda: {
            "action": "would-write-managed-skills",
            "managed_skills": sorted(CLAUDE_DOCS_SKILLS.keys()),
        },
        apply=lambda: apply_docs_automation(ctx, "claude"),
    )


def _plan_workflow_scripts() -> dict[str, Any]:
    from tapps_mcp.pipeline.platform_workflow_scripts import WORKFLOW_SCRIPTS

    return {
        "action": "would-write-managed-files",
        "managed_files": sorted(WORKFLOW_SCRIPTS.keys()),
    }


def _apply_workflow_scripts(ctx: HostContext) -> Any:
    from tapps_mcp.pipeline.platform_workflow_scripts import generate_workflow_scripts

    return generate_workflow_scripts(ctx.project_root, dry_run=False)


def _resolve_claude_rules(ctx: HostContext) -> None:
    """The ``.claude/rules/*.md`` set — some universal, some language-gated."""
    from tapps_mcp.pipeline.platform_bundles import generate_claude_pipeline_rule
    from tapps_mcp.pipeline.platform_generators import (
        generate_claude_agent_scope_rule,
        generate_claude_agent_to_agent_rule,
        generate_claude_autonomy_rule,
        generate_claude_config_files_rule,
        generate_claude_integration_hygiene_rule,
        generate_claude_linear_standards_rule,
        generate_claude_python_quality_rule,
        generate_claude_security_rule,
        generate_claude_test_quality_rule,
    )

    root = ctx.project_root
    resolve_component(
        ctx,
        "python_quality_rule",
        skip_key="python_quality_rule",
        gate=ctx.python_gate,
        plan=lambda: "would-regenerate",
        apply=lambda: generate_claude_python_quality_rule(
            root, engagement_level=ctx.engagement_level
        ),
    )
    # Universal rules — they apply to any deployed agent regardless of language.
    universal: tuple[tuple[str, Callable[[Path], Any]], ...] = (
        ("agent_scope_rule", generate_claude_agent_scope_rule),
        ("agent_to_agent_rule", generate_claude_agent_to_agent_rule),
        ("autonomy_rule", generate_claude_autonomy_rule),
        ("linear_standards_rule", generate_claude_linear_standards_rule),
        ("integration_hygiene_rule", generate_claude_integration_hygiene_rule),
    )
    for name, generator in universal:
        resolve_component(
            ctx,
            name,
            skip_key=name,
            plan=lambda: "would-regenerate",
            apply=partial(generator, root),
        )
    # TAP-978: scoped quality rules. security/test-quality are Python-gated;
    # config-files is python-or-infra gated, mirroring pipeline_rule.
    gated: tuple[tuple[str, Gate, Callable[[Path], Any]], ...] = (
        ("pipeline_rule", ctx.infra_gate, generate_claude_pipeline_rule),
        ("security_rule", ctx.python_gate, generate_claude_security_rule),
        ("test_quality_rule", ctx.python_gate, generate_claude_test_quality_rule),
        ("config_files_rule", ctx.infra_gate, generate_claude_config_files_rule),
    )
    for name, gate, generator in gated:
        resolve_component(
            ctx,
            name,
            skip_key=name,
            gate=gate,
            plan=lambda: "would-regenerate",
            apply=partial(generator, root),
        )


def _resolve_project_scripts(ctx: HostContext) -> None:
    """``scripts/measure.py`` + ``scripts/gitfacts.sh`` — project-root, host-agnostic."""
    from tapps_mcp.pipeline.platform_project_scripts import (
        generate_gitfacts_script,
        generate_measure_script,
    )

    scripts: tuple[tuple[str, Callable[[Path], Any]], ...] = (
        ("measure_script", generate_measure_script),
        ("gitfacts_script", generate_gitfacts_script),
    )
    for name, generator in scripts:
        resolve_component(
            ctx,
            name,
            skip_key=name,
            plan=lambda: "would-regenerate",
            apply=partial(generator, ctx.project_root),
        )


def upgrade_claude_code(ctx: HostContext) -> None:
    """Upgrade every claude-code artifact under one shared plan."""
    from tapps_mcp.pipeline.init import _bootstrap_claude

    resolve_component(
        ctx,
        "claude_md",
        skip_key="claude_md",
        plan=lambda: dry_run_claude_md_status(ctx.project_root, force=ctx.force),
        apply=lambda: _bootstrap_claude(ctx.project_root, overwrite=ctx.force),
    )
    _resolve_claude_hooks(ctx)
    _resolve_claude_assets(ctx)
    _resolve_claude_rules(ctx)
    _resolve_project_scripts(ctx)
