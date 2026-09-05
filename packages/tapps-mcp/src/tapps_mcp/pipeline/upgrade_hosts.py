"""Per-host upgrade entry point.

Extracted from :mod:`tapps_mcp.pipeline.upgrade` (TAP-6913). Owns the MCP-config
step every host shares, the narrow ``mcp_only`` install, and dispatch to the
per-host modules.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from tapps_core.common.logging import get_logger
from tapps_mcp.distribution.nlt_mcp_config import DEFAULT_NLT_BUNDLE
from tapps_mcp.pipeline.upgrade_host_claude import upgrade_claude_code
from tapps_mcp.pipeline.upgrade_host_context import HookFlags, HostContext
from tapps_mcp.pipeline.upgrade_host_cursor import upgrade_cursor
from tapps_mcp.pipeline.upgrade_mcp_config import upgrade_mcp_config
from tapps_mcp.pipeline.upgrade_report import skipped
from tapps_mcp.pipeline.upgrade_signals import has_infra_signals, has_python_signals

log = get_logger(__name__)

_MCP_ONLY_SKIPPED = [
    "claude_md",
    "hooks",
    "agents",
    "skills",
    "python_quality_rule",
    "agent_scope_rule",
    "autonomy_rule",
    "linear_standards_rule",
    "pipeline_rule",
    "security_rule",
    "test_quality_rule",
    "config_files_rule",
    "cursor_rules",
]


_HOST_UPGRADERS: dict[str, Callable[[HostContext], None]] = {
    "claude-code": upgrade_claude_code,
    "cursor": upgrade_cursor,
}


def _record_mcp_only(ctx: HostContext, host: str) -> None:
    """Narrow install: settings merge only, then report what was left alone."""
    from tapps_mcp.pipeline.init import _bootstrap_claude_settings

    # Still run settings merge — it's the other half of "just wire the MCP server in".
    if host == "claude-code" and not ctx.dry_run and not skipped("claude_settings", ctx.skip):
        ctx.result["components"]["settings"] = _bootstrap_claude_settings(
            ctx.project_root, engagement_level=ctx.engagement_level
        )
    ctx.result["components"]["mcp_only_skipped"] = {
        "reason": "mcp_only=True",
        "skipped": list(_MCP_ONLY_SKIPPED),
    }


def upgrade_platform(
    host: str,
    project_root: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    engagement_level: str = "medium",
    skill_tier: str = "full",
    skip_files: set[str] | None = None,
    mcp_only: bool = False,
    force_python_rule: bool = False,
    destructive_guard: bool = True,
    linear_enforce_gate: bool = False,
    linear_enforce_cache_gate: str = "off",
    session_start_gate: str = "off",
    mcp_bundle: str | None = DEFAULT_NLT_BUNDLE,
) -> dict[str, Any]:
    """Upgrade platform-specific files for a single host.

    Parameters
    ----------
    mcp_only:
        When True, only the ``.mcp.json`` (when already opted in) and
        ``.claude/settings.json`` permissions merge run.
    force_python_rule:
        When True, skip the Python-language gate and always generate
        ``python-quality.md`` / ``tapps-pipeline.md``.
    destructive_guard:
        Forwarded to ``generate_claude_hooks`` so the destructive-command
        PreToolUse hook is regenerated on upgrade (TAP-987).
    linear_enforce_gate:
        Forwarded to ``generate_claude_hooks`` so the Linear routing gate
        scripts land (or get removed) based on the current flag value
        (TAP-987).

    Per-artifact skip tokens (via ``skip_files``) are honored independently —
    skipping ``CLAUDE.md`` no longer gates hooks/agents/skills/rules — and are
    honored identically in dry-run and live mode (TAP-6913).
    """
    result: dict[str, Any] = {"host": host, "components": {}}
    skip = skip_files or set()
    ctx = HostContext(
        project_root=project_root,
        result=result,
        dry_run=dry_run,
        force=force,
        engagement_level=engagement_level,
        skill_tier=skill_tier,
        skip=skip,
        python_ok=force_python_rule or has_python_signals(project_root),
        infra_ok=has_infra_signals(project_root),
        hook_flags=HookFlags(
            destructive_guard=destructive_guard,
            linear_enforce_gate=linear_enforce_gate,
            linear_enforce_cache_gate=linear_enforce_cache_gate,
            session_start_gate=session_start_gate,
        ),
    )

    if skipped("mcp_config", skip):
        result["components"]["mcp_config"] = "skipped (upgrade_skip_files)"
    else:
        upgrade_mcp_config(
            host,
            project_root,
            result,
            force=force,
            dry_run=dry_run,
            mcp_bundle=mcp_bundle,
        )

    if mcp_only:
        _record_mcp_only(ctx, host)
        return result

    upgrader = _HOST_UPGRADERS.get(host)
    if upgrader is not None:
        upgrader(ctx)
    elif host == "vscode":
        result["components"]["note"] = "no platform rules to upgrade"

    if not dry_run and host in _HOST_UPGRADERS:
        from tapps_mcp.distribution.doctor import check_session_handoff_skills

        handoff_check = check_session_handoff_skills(project_root)
        result["session_handoff_skills"] = {
            "ok": handoff_check.ok,
            "message": handoff_check.message,
            "detail": handoff_check.detail,
        }

    return result
