"""cursor artifact upgrades under one shared plan (TAP-6913).

``hooks``, ``agents``, and ``skills`` mirror the Cursor directory tokens added
in TAP-7054 (``cursor_hooks``, ``cursor_agents``, ``cursor_skills``). The
remaining components (``cursor_rules``, ``docs_automation``,
``cursor_rule_types``) have no covering token, so they keep ``skip_key=None``.
Otherwise the shape is the same as the claude-code host: one plan, one write
step selected by ``dry_run``.
"""

from __future__ import annotations

from typing import Any

from tapps_core.common.logging import get_logger
from tapps_mcp.pipeline.upgrade_host_context import (
    HostContext,
    apply_docs_automation,
    apply_skills,
    docsmcp_gate,
    plan_skills,
    record_hooks_parse_error,
    resolve_component,
)
from tapps_mcp.pipeline.upgrade_report import enumerate_preserved

log = get_logger(__name__)


def _plan_cursor_hooks(ctx: HostContext) -> dict[str, Any]:
    """Preview the ``.cursor/hooks.json`` merge and the scripts it would write."""
    from tapps_mcp.pipeline.platform_hooks import preview_cursor_hooks_merge

    hooks_dir = ctx.project_root / ".cursor" / "hooks"
    managed_hooks = (
        frozenset(p.name for p in hooks_dir.glob("tapps-*")) if hooks_dir.is_dir() else frozenset()
    )
    preview = preview_cursor_hooks_merge(ctx.project_root)
    would_remove = preview.get("would_remove_keys") or []
    return {
        "action": "would-write-managed-scripts",
        "note": (
            f"hooks.json would-remove-keys: {', '.join(would_remove)}"
            if would_remove
            else "hooks.json entries merged — third-party keys preserved"
        ),
        "preserved_hook_keys": preview.get("preserved_hook_keys", []),
        "third_party_hook_keys": preview.get("third_party_hook_keys", []),
        "would_remove_keys": would_remove,
        "preserved_files": enumerate_preserved(hooks_dir, managed_hooks),
    }


def _remove_retired_pipeline_rule(ctx: HostContext) -> str:
    """Delete the retired ``.cursor/rules/tapps-pipeline.md`` (TAP-6440).

    ``tapps-pipeline.mdc`` (written by ``_bootstrap_cursor``) is now the sole
    Cursor pipeline rule; the plain-``.md`` copy a prior release also wrote is
    dead weight left on disk that a doctor presence check would otherwise
    still accept, masking the duplicate.
    """
    retired = ctx.project_root / ".cursor" / "rules" / "tapps-pipeline.md"
    if not retired.is_file():
        return "absent"
    retired.unlink()
    return "removed"


def _apply_cursor_hooks(ctx: HostContext) -> dict[str, Any]:
    from tapps_mcp.pipeline.platform_generators import generate_cursor_hooks
    from tapps_mcp.pipeline.platform_hooks import wire_memory_hooks

    hooks_result = generate_cursor_hooks(ctx.project_root)
    component = {
        "scripts_created": hooks_result.get("scripts_created", []),
        "hooks_added": hooks_result.get("hooks_added", 0),
        "third_party_hook_keys": hooks_result.get("third_party_hook_keys", []),
        "preserved_hook_keys": hooks_result.get("preserved_hook_keys", []),
    }
    ctx.result["components"]["memory_hooks"] = wire_memory_hooks(
        ctx.project_root, platform="cursor"
    )
    return component


def upgrade_cursor(ctx: HostContext) -> None:
    """Upgrade every cursor artifact under one shared plan.

    ``hooks``, ``agents``, and ``skills`` are covered by the ``cursor_hooks``,
    ``cursor_agents``, and ``cursor_skills`` tokens (TAP-7054); the rest of the
    components have no covering token and pass ``skip_key=None``.
    """
    from tapps_mcp.pipeline.init import _bootstrap_cursor
    from tapps_mcp.pipeline.platform_docs_automation import CURSOR_DOCS_SKILLS
    from tapps_mcp.pipeline.platform_generators import (
        generate_cursor_rules,
        generate_skills,
        generate_subagent_definitions,
    )
    from tapps_mcp.pipeline.platform_hooks import ManagedJsonError
    from tapps_mcp.pipeline.platform_skills import CURSOR_SKILLS
    from tapps_mcp.pipeline.platform_subagents import CURSOR_AGENTS

    retired_pipeline_rule = ctx.project_root / ".cursor" / "rules" / "tapps-pipeline.md"
    resolve_component(
        ctx,
        "cursor_rules",
        skip_key=None,
        plan=lambda: {
            "action": "would-refresh" if ctx.force else "check-needed",
            "retired_tapps-pipeline.md": (
                "would-remove" if retired_pipeline_rule.is_file() else "absent"
            ),
        },
        apply=lambda: {
            "action": _bootstrap_cursor(ctx.project_root, overwrite=ctx.force),
            "retired_tapps-pipeline.md": _remove_retired_pipeline_rule(ctx),
        },
    )

    try:
        resolve_component(
            ctx,
            "hooks",
            skip_key="cursor_hooks",
            plan=lambda: _plan_cursor_hooks(ctx),
            apply=lambda: _apply_cursor_hooks(ctx),
        )
    except ManagedJsonError as exc:
        record_hooks_parse_error(ctx, exc)

    managed_agents = frozenset(CURSOR_AGENTS.keys())
    resolve_component(
        ctx,
        "agents",
        skip_key="cursor_agents",
        plan=lambda: {
            "action": "would-write-managed-files",
            "managed_files": sorted(managed_agents),
            "preserved_files": enumerate_preserved(
                ctx.project_root / ".cursor" / "agents", managed_agents
            ),
        },
        apply=lambda: generate_subagent_definitions(ctx.project_root, "cursor", overwrite=True),
    )

    resolve_component(
        ctx,
        "skills",
        skip_key="cursor_skills",
        plan=lambda: plan_skills(ctx, "cursor", CURSOR_SKILLS),
        apply=lambda: apply_skills(
            ctx,
            "cursor",
            lambda: generate_skills(
                ctx.project_root, "cursor", overwrite=True, skill_tier=ctx.skill_tier
            ),
        ),
    )

    resolve_component(
        ctx,
        "docs_automation",
        skip_key=None,
        gate=docsmcp_gate(ctx.project_root),
        plan=lambda: {
            "action": "would-write-managed-skills",
            "managed_skills": sorted(CURSOR_DOCS_SKILLS.keys()),
        },
        apply=lambda: apply_docs_automation(ctx, "cursor"),
    )

    resolve_component(
        ctx,
        "cursor_rule_types",
        skip_key=None,
        plan=lambda: "would-regenerate",
        apply=lambda: generate_cursor_rules(ctx.project_root, overwrite=ctx.force),
    )
