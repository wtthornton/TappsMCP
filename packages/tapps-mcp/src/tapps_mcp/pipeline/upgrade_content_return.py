"""Content-return mode for the upgrade pipeline (Epic 87.3).

Extracted from :mod:`tapps_mcp.pipeline.upgrade` (TAP-6913).

When the filesystem is read-only (Docker) or ``TAPPS_WRITE_MODE=content`` is
set, the upgrade cannot write. It instead accumulates
:class:`~tapps_core.common.file_operations.FileOperation` objects into a
:class:`~tapps_core.common.file_operations.FileManifest` the calling agent
applies itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tapps_core.common.file_operations import (
    AgentInstructions,
    FileManifest,
    FileOperation,
)
from tapps_core.common.logging import get_logger
from tapps_mcp.pipeline.upgrade_signals import detect_platform, hosts_for_platform

log = get_logger(__name__)

# Components a narrow ``mcp_only=True`` content-return run does not plan for.
_MCP_ONLY_SKIPPED = [
    "agents_md",
    "claude_md",
    "platforms",
    "rules",
    "ci_workflows",
    "github_copilot",
    "github_templates",
    "governance",
]

_GITHUB_COMPONENTS = ("ci_workflows", "github_copilot", "github_templates", "governance")


def upgrade_agents_md_content_return(
    project_root: Path,
) -> tuple[FileOperation, dict[str, Any]]:
    """Generate a FileOperation for AGENTS.md upgrade in content-return mode.

    Returns ``(file_op, result_dict)`` with the appropriate mode
    (``"create"`` or ``"merge"``) depending on whether AGENTS.md exists.
    """
    from tapps_mcp.pipeline.agents_md import AgentsValidation, merge_agents_md
    from tapps_mcp.prompts.prompt_loader import load_agents_template

    agents_path = project_root / "AGENTS.md"
    template_content = load_agents_template()

    if not agents_path.exists():
        op = FileOperation(
            path="AGENTS.md",
            content=template_content,
            mode="create",
            description="AGENTS.md — AI assistant workflow and tool reference.",
            priority=1,
        )
        return op, {"action": "created"}

    existing = agents_path.read_text(encoding="utf-8")
    validation = AgentsValidation(existing)

    if validation.is_up_to_date:
        # Still return the file op so the agent has full context
        op = FileOperation(
            path="AGENTS.md",
            content=existing,
            mode="overwrite",
            description="AGENTS.md is already up-to-date (no changes needed).",
            priority=1,
        )
        return op, {"action": "up-to-date"}

    # Smart merge — produce merged content for the agent to write
    merged, changes = merge_agents_md(existing, template_content)
    op = FileOperation(
        path="AGENTS.md",
        content=merged,
        mode="merge",
        description=(
            "AGENTS.md — merged with latest template. "
            "User customizations are preserved; only managed sections updated."
        ),
        priority=1,
    )
    issues: list[str] = []
    if validation.sections_missing:
        issues.append(f"missing sections: {', '.join(validation.sections_missing)}")
    if validation.tools_missing:
        issues.append(f"missing tools: {', '.join(validation.tools_missing)}")
    detail = "; ".join(issues) or "version mismatch"
    return op, {"action": "merged", "detail": detail, "changes": changes}


def upgrade_platform_content_return(
    host: str,
    project_root: Path,
    *,
    force: bool = False,
    engagement_level: str = "medium",
) -> tuple[list[FileOperation], dict[str, Any]]:
    """Generate FileOperations for platform upgrade in content-return mode.

    Returns ``(file_ops, result_dict)`` with platform-specific file operations.
    """
    from tapps_mcp.prompts.prompt_loader import load_platform_rules

    ops: list[FileOperation] = []
    result: dict[str, Any] = {"host": host, "components": {}}

    if host == "claude-code":
        from tapps_mcp.pipeline.claude_md import merge_claude_md, render_fresh_claude_md

        content = load_platform_rules("claude", engagement_level=engagement_level)
        claude_md_path = project_root / "CLAUDE.md"
        if claude_md_path.exists() and not force:
            existing = claude_md_path.read_text(encoding="utf-8")
            merged, _changes = merge_claude_md(existing, content)
            payload = merged
            mode = "overwrite"
        else:
            payload = render_fresh_claude_md(content)
            mode = "overwrite" if force and claude_md_path.exists() else "create"
        ops.append(
            FileOperation(
                path="CLAUDE.md",
                content=payload,
                mode=mode,
                description="Claude Code platform rules with TappsMCP pipeline.",
                priority=2,
            )
        )
        result["components"]["claude_md"] = "content_return"

    elif host == "cursor":
        content = load_platform_rules("cursor", engagement_level=engagement_level)
        cursor_path = project_root / ".cursor" / "rules" / "tapps-pipeline.mdc"
        mode = "overwrite" if (cursor_path.exists() or force) else "create"
        ops.append(
            FileOperation(
                path=".cursor/rules/tapps-pipeline.mdc",
                content=content,
                mode=mode,
                description="Cursor platform rules with TappsMCP pipeline.",
                priority=2,
            )
        )
        result["components"]["cursor_rules"] = "content_return"

    elif host == "vscode":
        result["components"]["note"] = "no platform rules to upgrade"

    # Hooks, skills, agents, CI are skipped in content-return mode
    result["components"]["generators_skipped"] = {
        "reason": "content_return",
        "skipped": ["hooks", "skills", "agents", "mcp_config", "settings"],
        "hint": "Run 'tapps_upgrade' locally to generate these components.",
    }

    return ops, result


def build_upgrade_manifest(
    file_ops: list[FileOperation],
    version: str,
) -> FileManifest:
    """Build a :class:`FileManifest` for the upgrade pipeline."""
    return FileManifest(
        summary=(f"TappsMCP upgrade v{version}: {len(file_ops)} file(s) to write"),
        source_version=version,
        files=file_ops,
        agent_instructions=AgentInstructions(
            persona=(
                "You are a project upgrade assistant updating TappsMCP "
                "scaffolding to the latest version.  Write each file "
                "exactly as provided — do not modify content, add "
                "comments, or reformat."
            ),
            tool_preference=(
                "Use Write for files with mode 'create' or 'overwrite'.  "
                "For files with mode 'merge', read the existing file first, "
                "then replace the entire content with the merged version "
                "provided (merge has already been computed)."
            ),
            verification_steps=[
                "After writing all files, run 'git diff' to review changes.",
                "Verify AGENTS.md exists and has the expected sections.",
                "Check that no user customizations were lost in merged files.",
                "Run 'git status' to show the user what changed.",
            ],
            warnings=[
                "Backup your project before applying (git stash or git commit).",
                "AGENTS.md merge preserves user customizations — review the diff.",
                "Hooks, skills, and agents are not included — run "
                "'tapps_upgrade' locally to generate those.",
            ],
        ),
    )


def _plan_agents_md(
    project_root: Path, result: dict[str, Any], file_ops: list[FileOperation]
) -> None:
    """Append the AGENTS.md operation, recording a failure rather than raising."""
    try:
        agents_op, agents_result = upgrade_agents_md_content_return(project_root)
        file_ops.append(agents_op)
        result["components"]["agents_md"] = agents_result
    except Exception as exc:
        result["errors"].append(f"AGENTS.md: {exc}")
        result["components"]["agents_md"] = {"action": "error", "detail": str(exc)}


def _plan_hosts(
    project_root: Path,
    result: dict[str, Any],
    file_ops: list[FileOperation],
    *,
    detected: str,
    force: bool,
    engagement_level: str,
) -> None:
    """Append each detected host's platform operations."""
    platform_results: list[dict[str, Any]] = []
    for host in hosts_for_platform(detected):
        try:
            host_ops, host_result = upgrade_platform_content_return(
                host,
                project_root,
                force=force,
                engagement_level=engagement_level,
            )
            file_ops.extend(host_ops)
            platform_results.append(host_result)
        except Exception as exc:
            result["errors"].append(f"{host}: {exc}")
            platform_results.append({"host": host, "error": str(exc)})
    result["components"]["platforms"] = platform_results


def upgrade_content_return(
    project_root: Path,
    *,
    platform: str = "",
    force: bool = False,
    mcp_only: bool = False,
) -> dict[str, Any]:
    """Run upgrade pipeline in content-return mode (Epic 87.3).

    Instead of writing files, accumulates :class:`FileOperation` objects
    and returns a :class:`FileManifest` the AI client can apply.

    TAP-690: ``mcp_only=True`` mirrors the direct-write narrow install —
    AGENTS.md, per-host platform files, and rule regeneration are all
    skipped; only MCP config + settings operations land in the manifest.
    """
    from tapps_core.config.settings import load_settings
    from tapps_mcp import __version__

    file_ops: list[FileOperation] = []
    result: dict[str, Any] = {
        "version": __version__,
        "dry_run": False,
        "content_return": True,
        "components": {},
        "errors": [],
    }

    if mcp_only:
        result["components"]["mcp_only_skipped"] = {
            "reason": "mcp_only=True",
            "skipped": list(_MCP_ONLY_SKIPPED),
        }
    else:
        _plan_agents_md(project_root, result, file_ops)

    # Detected even for the narrow install, for diagnostic completeness.
    detected = platform or detect_platform(project_root)
    result["detected_platform"] = detected

    if not mcp_only:
        settings = load_settings(project_root=project_root)
        _plan_hosts(
            project_root,
            result,
            file_ops,
            detected=detected,
            force=force,
            engagement_level=settings.llm_engagement_level,
        )
        # GitHub artifacts are skipped in content-return mode.
        for component in _GITHUB_COMPONENTS:
            result["components"][component] = {"action": "skipped", "reason": "content_return"}

    manifest = build_upgrade_manifest(file_ops, __version__)
    result["file_manifest"] = manifest.to_full_response_data()
    result["success"] = len(result["errors"]) == 0
    return result
