"""Shared plumbing for per-host upgrades — one path for dry-run and live.

Extracted from :mod:`tapps_mcp.pipeline.upgrade` (TAP-6913).

Before that split, each host had a ``_dry_run`` twin of its ``_live`` function
and the two drifted: the claude-code preview ignored ``upgrade_skip_files`` for
four rules, omitted ``agent_to_agent_rule`` entirely, and never ran the gate
auto-promotion that decides which hook scripts a live run actually writes.

The rule is now structural — every component goes through
:func:`resolve_component`, which computes the skip decision, the language/infra
gate, and the managed-file plan *once*; ``dry_run`` selects only between
reporting that plan and executing the write.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tapps_core.common.logging import get_logger
from tapps_mcp.pipeline.upgrade_report import (
    enumerate_preserved,
    record_managed_json_error,
    skipped,
)

log = get_logger(__name__)

_PYTHON_GATE_HINT = (
    "Set force_python_quality_rule=true in .tapps-mcp.yaml to install on non-Python repos."
)
_INFRA_GATE_HINT = (
    "Set force_python_quality_rule=true, or add a Dockerfile/docker-compose file, to install."
)


@dataclass(frozen=True)
class Gate:
    """A language/infra precondition. When ``not ok`` the component is a no-op."""

    ok: bool
    message: str = ""
    hint: str = ""

    def as_component(self) -> Any:
        """The result value recorded when the gate refuses the component."""
        return {"action": self.message, "hint": self.hint} if self.hint else self.message


@dataclass(frozen=True)
class HookFlags:
    """Opt-in hook gates, as configured — and as resolved after auto-promotion."""

    destructive_guard: bool = True
    linear_enforce_gate: bool = False
    linear_enforce_cache_gate: str = "off"
    session_start_gate: str = "off"


@dataclass(frozen=True)
class HostContext:
    """Everything one host's component resolution needs, computed once per run."""

    project_root: Path
    result: dict[str, Any]
    dry_run: bool
    force: bool
    engagement_level: str
    skill_tier: str
    skip: set[str]
    python_ok: bool
    infra_ok: bool
    hook_flags: HookFlags

    @property
    def python_gate(self) -> Gate:
        return Gate(self.python_ok, "skipped (no python detected)", _PYTHON_GATE_HINT)

    @property
    def infra_gate(self) -> Gate:
        return Gate(
            self.python_ok or self.infra_ok,
            "skipped (no python or infra detected)",
            _INFRA_GATE_HINT,
        )


def resolve_component(
    ctx: HostContext,
    name: str,
    *,
    plan: Callable[[], Any],
    apply: Callable[[], Any],
    skip_key: str | None,
    gate: Gate | None = None,
) -> Any:
    """Record one component, choosing the write step and nothing else by ``dry_run``.

    ``skip_key`` is the ``upgrade_skip_files`` key guarding this component
    (``None`` for components the vocabulary does not cover). The skip and gate
    decisions above are identical in both modes — only the final line differs.
    """
    if skip_key is not None and skipped(skip_key, ctx.skip):
        value: Any = "skipped (upgrade_skip_files)"
    elif gate is not None and not gate.ok:
        value = gate.as_component()
    else:
        value = plan() if ctx.dry_run else apply()
    ctx.result["components"][name] = value
    return value


def record_hooks_parse_error(ctx: HostContext, exc: Any) -> None:
    """Isolate a malformed managed-JSON failure to the ``hooks`` component.

    A live run stashes it on ``component_errors`` so the orchestrator lifts it to
    the top level. A dry run reaches the top level through ``dry_run_summary``'s
    ``parse_errors`` instead, so stashing it there too would double-report the
    same parse failure.
    """
    if ctx.dry_run:
        ctx.result["components"]["hooks"] = {
            "action": "error",
            "error": str(exc),
            "hint": getattr(exc, "remediation", ""),
        }
    else:
        record_managed_json_error(ctx.result, "hooks", exc)


def docsmcp_gate(project_root: Path) -> Gate:
    """Docs-automation only ships where DocsMCP is wired in."""
    from tapps_mcp.pipeline.platform_docs_automation import detect_docsmcp

    return Gate(detect_docsmcp(project_root), "skipped (no docsmcp detected)")


def apply_docs_automation(ctx: HostContext, platform: str) -> Any:
    from tapps_mcp.pipeline.platform_docs_automation import generate_docs_automation

    return generate_docs_automation(ctx.project_root, platform, overwrite=True)


def plan_skills(ctx: HostContext, platform: str, catalogue: dict[str, Any]) -> dict[str, Any]:
    """Managed/preserved/pruned skill preview for one host."""
    from tapps_mcp.pipeline.platform_skills import CORE_SKILL_NAMES, prune_skills_for_tier

    all_skills = frozenset(catalogue.keys())
    managed_skills = (
        frozenset(name for name in catalogue if name in CORE_SKILL_NAMES)
        if ctx.skill_tier == "core"
        else all_skills
    )
    prune_preview = prune_skills_for_tier(
        ctx.project_root, platform, skill_tier=ctx.skill_tier, dry_run=True
    )
    skills_dir = ctx.project_root / f".{platform}" / "skills"
    return {
        "action": "would-write-managed-skills",
        "skill_tier": ctx.skill_tier,
        "managed_skills": sorted(managed_skills),
        "preserved_skills": enumerate_preserved(skills_dir, all_skills, is_dir_target=True),
        "would_prune": prune_preview.get("would_prune", []),
        "bytes_freed": prune_preview.get("bytes_freed", 0),
    }


def apply_skills(
    ctx: HostContext, platform: str, generate: Callable[[], dict[str, Any]]
) -> dict[str, Any]:
    """Write the managed skills, then prune the ones this tier no longer ships."""
    from tapps_mcp.pipeline.platform_skills import prune_skills_for_tier

    skills_result = generate()
    prune_result = prune_skills_for_tier(
        ctx.project_root, platform, skill_tier=ctx.skill_tier, dry_run=False
    )
    skills_result["pruned"] = prune_result.get("pruned", [])
    skills_result["bytes_freed"] = prune_result.get("bytes_freed", 0)
    return skills_result
