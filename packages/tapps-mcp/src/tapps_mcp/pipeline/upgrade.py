"""Upgrade pipeline for refreshing TappsMCP-generated files.

Provides :func:`upgrade_pipeline` which is called by the
``tapps_upgrade`` MCP tool. Reuses existing generators but operates
in ``upgrade_mode`` so custom command paths are never overwritten.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from tapps_core.common.file_operations import (
    AgentInstructions,
    FileManifest,
    FileOperation,
    WriteMode,
    detect_write_mode,
)
from tapps_core.common.logging import get_logger

log = get_logger(__name__)


def _upgrade_agents_md(
    project_root: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Validate and update AGENTS.md to the latest template.

    Returns a result dict with ``action`` and optional ``detail``.
    """
    from tapps_mcp.pipeline.agents_md import AgentsValidation, update_agents_md
    from tapps_mcp.prompts.prompt_loader import load_agents_template

    agents_path = project_root / "AGENTS.md"
    template_content = load_agents_template()

    if not agents_path.exists():
        if not dry_run:
            agents_path.write_text(template_content, encoding="utf-8")
        return {"action": "created"}

    validation = AgentsValidation(agents_path.read_text(encoding="utf-8"))
    if validation.is_up_to_date:
        return {"action": "up-to-date"}

    issues: list[str] = []
    if validation.sections_missing:
        issues.append(f"missing sections: {', '.join(validation.sections_missing)}")
    if validation.tools_missing:
        issues.append(f"missing tools: {', '.join(validation.tools_missing)}")
    detail = "; ".join(issues) or "version mismatch"

    if dry_run:
        return {"action": "needs-update", "detail": detail}
    action, merge_detail = update_agents_md(agents_path, template_content)
    return {"action": action, "detail": merge_detail or detail}


def _refresh_karpathy_blocks(
    project_root: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Install or refresh the Karpathy guidelines block in AGENTS.md and CLAUDE.md.

    Appends between BEGIN/END markers, preserving content outside them.
    Files that don't exist are skipped (they aren't owned by this upgrade
    step; ``tapps_init`` creates them).
    """
    from tapps_mcp.pipeline import karpathy_block

    per_file: dict[str, str] = {}
    for rel in ("AGENTS.md", "CLAUDE.md"):
        target = project_root / rel
        if not target.exists():
            per_file[rel] = "skipped_file_missing"
            continue
        try:
            per_file[rel] = karpathy_block.install_or_refresh(target, dry_run=dry_run)
        except Exception as exc:
            per_file[rel] = f"error: {exc}"

    return {
        "source_sha": karpathy_block.KARPATHY_GUIDELINES_SOURCE_SHA,
        "files": per_file,
    }


def _upgrade_platform(
    host: str,
    project_root: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    engagement_level: str = "medium",
    skip_files: set[str] | None = None,
) -> dict[str, Any]:
    """Upgrade platform-specific files for a single host.

    Returns a result dict with per-component status.
    """
    from tapps_mcp.distribution.setup_generator import (
        _generate_config,
        _get_config_path,
        _get_servers_key,
        _validate_config_file,
    )
    from tapps_mcp.pipeline.init import (
        _bootstrap_claude,
        _bootstrap_claude_settings,
        _bootstrap_cursor,
    )
    from tapps_mcp.pipeline.platform_generators import (
        generate_claude_agent_scope_rule,
        generate_claude_hooks,
        generate_claude_python_quality_rule,
        generate_cursor_hooks,
        generate_cursor_rules,
        generate_skills,
        generate_subagent_definitions,
    )

    result: dict[str, Any] = {"host": host, "components": {}}
    _skip = skip_files or set()

    # MCP config check (upgrade_mode preserves command paths)
    config_path = _get_config_path(host, project_root)
    servers_key = _get_servers_key(host)
    error = _validate_config_file(config_path, servers_key)
    if error is not None:
        if not dry_run:
            _generate_config(host, project_root, force=True, upgrade_mode=True)
            result["components"]["mcp_config"] = "regenerated"
        else:
            result["components"]["mcp_config"] = f"needs-fix: {error}"
    else:
        result["components"]["mcp_config"] = "ok"

    # Platform rules and artifacts
    if host == "claude-code":
        if dry_run:
            result["components"]["claude_md"] = "would-refresh" if force else "check-needed"
            result["components"]["settings"] = "check-needed"
            result["components"]["hooks"] = "would-regenerate"
            result["components"]["agents"] = "would-regenerate"
            result["components"]["skills"] = "would-regenerate"
            result["components"]["python_quality_rule"] = "would-regenerate"
            result["components"]["agent_scope_rule"] = "would-regenerate"
        elif "CLAUDE.md" in _skip:
            result["components"]["claude_md"] = "skipped (upgrade_skip_files)"
        else:
            claude_action = _bootstrap_claude(project_root, overwrite=force)
            result["components"]["claude_md"] = claude_action

            settings_action = _bootstrap_claude_settings(
                project_root, engagement_level=engagement_level
            )
            result["components"]["settings"] = settings_action

            hooks_result = generate_claude_hooks(project_root)
            result["components"]["hooks"] = {
                "scripts_created": hooks_result.get("scripts_created", []),
                "hooks_added": hooks_result.get("hooks_added", 0),
            }

            agents_result = generate_subagent_definitions(project_root, "claude", overwrite=True)
            result["components"]["agents"] = agents_result

            skills_result = generate_skills(project_root, "claude", overwrite=True)
            result["components"]["skills"] = skills_result

            rule_result = generate_claude_python_quality_rule(
                project_root, engagement_level=engagement_level
            )
            result["components"]["python_quality_rule"] = rule_result

            scope_rule_result = generate_claude_agent_scope_rule(project_root)
            result["components"]["agent_scope_rule"] = scope_rule_result

            from tapps_mcp.pipeline.platform_bundles import generate_claude_pipeline_rule

            pipeline_rule_result = generate_claude_pipeline_rule(project_root)
            result["components"]["pipeline_rule"] = pipeline_rule_result

    elif host == "cursor":
        if dry_run:
            result["components"]["cursor_rules"] = "would-refresh" if force else "check-needed"
            result["components"]["hooks"] = "would-regenerate"
            result["components"]["agents"] = "would-regenerate"
            result["components"]["skills"] = "would-regenerate"
        else:
            cursor_action = _bootstrap_cursor(project_root, overwrite=force)
            result["components"]["cursor_rules"] = cursor_action

            hooks_result = generate_cursor_hooks(project_root)
            result["components"]["hooks"] = {
                "scripts_created": hooks_result.get("scripts_created", []),
                "hooks_added": hooks_result.get("hooks_added", 0),
            }

            agents_result = generate_subagent_definitions(project_root, "cursor", overwrite=True)
            result["components"]["agents"] = agents_result

            skills_result = generate_skills(project_root, "cursor", overwrite=True)
            result["components"]["skills"] = skills_result

            rules_result = generate_cursor_rules(project_root)
            result["components"]["cursor_rule_types"] = rules_result

    elif host == "vscode":
        result["components"]["note"] = "no platform rules to upgrade"

    return result


def _upgrade_agents_md_content_return(
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


def _upgrade_platform_content_return(
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
        content = load_platform_rules("claude", engagement_level=engagement_level)
        claude_md_path = project_root / "CLAUDE.md"
        mode = "overwrite" if (claude_md_path.exists() or force) else "create"
        ops.append(
            FileOperation(
                path="CLAUDE.md",
                content=content,
                mode=mode,
                description="Claude Code platform rules with TappsMCP pipeline.",
                priority=2,
            )
        )
        result["components"]["claude_md"] = "content_return"

    elif host == "cursor":
        content = load_platform_rules("cursor", engagement_level=engagement_level)
        cursor_path = project_root / ".cursor" / "rules" / "tapps-pipeline.md"
        mode = "overwrite" if (cursor_path.exists() or force) else "create"
        ops.append(
            FileOperation(
                path=".cursor/rules/tapps-pipeline.md",
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


def _build_upgrade_manifest(
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


def _upgrade_content_return(
    project_root: Path,
    *,
    platform: str = "",
    force: bool = False,
) -> dict[str, Any]:
    """Run upgrade pipeline in content-return mode (Epic 87.3).

    Instead of writing files, accumulates :class:`FileOperation` objects
    and returns a :class:`FileManifest` the AI client can apply.
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

    # AGENTS.md
    try:
        agents_op, agents_result = _upgrade_agents_md_content_return(project_root)
        file_ops.append(agents_op)
        result["components"]["agents_md"] = agents_result
    except Exception as exc:
        result["errors"].append(f"AGENTS.md: {exc}")
        result["components"]["agents_md"] = {"action": "error", "detail": str(exc)}

    # Detect platform
    detected = platform or _detect_platform(project_root)
    result["detected_platform"] = detected

    hosts: list[str] = []
    if detected in ("claude", "both"):
        hosts.append("claude-code")
    if detected in ("cursor", "both"):
        hosts.append("cursor")

    settings = load_settings()
    engagement_level = settings.llm_engagement_level

    # Per-host platform files
    platform_results: list[dict[str, Any]] = []
    for host in hosts:
        try:
            host_ops, host_result = _upgrade_platform_content_return(
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

    # GitHub artifacts skipped in content-return mode
    for component in ("ci_workflows", "github_copilot", "github_templates", "governance"):
        result["components"][component] = {"action": "skipped", "reason": "content_return"}

    # Build manifest
    manifest = _build_upgrade_manifest(file_ops, __version__)
    result["file_manifest"] = manifest.to_full_response_data()
    result["success"] = len(result["errors"]) == 0

    return result


def _detect_platform(project_root: Path) -> str:
    """Detect the platform from existing config files."""
    claude_dir = project_root / ".claude"
    cursor_dir = project_root / ".cursor"

    # Check for Claude Code config indicators
    has_claude = claude_dir.is_dir() or (project_root / "CLAUDE.md").exists()
    has_cursor = cursor_dir.is_dir()

    if has_claude and has_cursor:
        return "both"
    if has_claude:
        return "claude"
    if has_cursor:
        return "cursor"
    return ""


def _collect_upgrade_targets(project_root: Path) -> list[Path]:
    """Collect files that upgrade_pipeline will overwrite."""
    targets: list[Path] = []
    candidates = [
        project_root / "AGENTS.md",
        project_root / "CLAUDE.md",
        project_root / ".claude" / "settings.json",
        project_root / ".cursor" / "rules" / "tapps-pipeline.md",
        # Docker-related config files (Epic 46)
        project_root / ".tapps-mcp.yaml",
    ]
    # Hook scripts
    hooks_dir = project_root / ".claude" / "hooks"
    if hooks_dir.is_dir():
        for f in hooks_dir.iterdir():
            if f.name.startswith("tapps-"):
                targets.append(f)
    # Skills
    skills_dir = project_root / ".claude" / "skills"
    if skills_dir.is_dir():
        for f in skills_dir.iterdir():
            if f.is_dir() and f.name.startswith("tapps-"):
                skill_file = f / "SKILL.md"
                if skill_file.exists():
                    targets.append(skill_file)
    # Agents
    agents_dir = project_root / ".claude" / "agents"
    if agents_dir.is_dir():
        for f in agents_dir.iterdir():
            if f.name.startswith("tapps-"):
                targets.append(f)
    for c in candidates:
        if c.exists():
            targets.append(c)
    return targets


def upgrade_pipeline(
    project_root: Path,
    *,
    platform: str = "",
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Upgrade all TappsMCP-generated files in a project.

    This is the core function called by the ``tapps_upgrade`` MCP tool.
    It uses ``upgrade_mode=True`` internally so custom command paths
    (e.g. PyInstaller exe) are never overwritten.

    Args:
        project_root: Project root directory.
        platform: ``"claude"``, ``"cursor"``, ``"both"``, or ``""`` for
            auto-detection.
        force: If ``True``, overwrite all generated files.
        dry_run: If ``True``, report what would change without writing.

    Returns:
        Structured dict with per-component upgrade results.
    """
    from tapps_mcp import __version__

    log.info(
        "upgrade_pipeline",
        project_root=str(project_root),
        platform=platform,
        force=force,
        dry_run=dry_run,
    )

    # Epic 87: Detect write mode (content-return for Docker/read-only)
    write_mode = WriteMode.DIRECT_WRITE if dry_run else detect_write_mode(project_root)
    content_return = write_mode == WriteMode.CONTENT_RETURN

    if content_return:
        log.info(
            "content_return_mode",
            project_root=str(project_root),
            reason="read-only filesystem or TAPPS_WRITE_MODE=content",
        )
        return _upgrade_content_return(
            project_root,
            platform=platform,
            force=force,
        )

    result: dict[str, Any] = {
        "version": __version__,
        "dry_run": dry_run,
        "components": {},
        "errors": [],
    }

    # Pre-upgrade backup (skip in dry-run mode)
    if not dry_run:
        try:
            from tapps_mcp.distribution.rollback import BackupManager

            mgr = BackupManager(project_root)
            backup_targets = _collect_upgrade_targets(project_root)
            if backup_targets:
                backup_dir = mgr.create_backup(
                    backup_targets,
                    reason="pre-upgrade backup",
                    version=__version__,
                )
                result["backup"] = str(backup_dir)
                mgr.cleanup_old_backups(keep=5)
        except Exception as exc:
            # Backup failure should not block upgrade
            log.warning("backup_failed", error=str(exc))
            result["backup"] = f"failed: {exc}"

    # Resolve engagement level and Docker config from settings
    from tapps_core.config.settings import load_settings

    settings = load_settings()

    # Load skip list from settings (Issue #86)
    skip_files: set[str] = set(settings.upgrade_skip_files)
    if skip_files:
        result["skipped_files"] = sorted(skip_files)

    # AGENTS.md (platform-independent)
    if "AGENTS.md" in skip_files:
        result["components"]["agents_md"] = {"action": "skipped (upgrade_skip_files)"}
    else:
        try:
            agents_result = _upgrade_agents_md(project_root, dry_run=dry_run)
            result["components"]["agents_md"] = agents_result
        except Exception as exc:
            result["errors"].append(f"AGENTS.md: {exc}")
            result["components"]["agents_md"] = {"action": "error", "detail": str(exc)}

    # Detect platform if not specified
    detected = platform or _detect_platform(project_root)
    result["detected_platform"] = detected

    hosts: list[str] = []
    if detected in ("claude", "both"):
        hosts.append("claude-code")
    if detected in ("cursor", "both"):
        hosts.append("cursor")

    engagement_level = settings.llm_engagement_level

    # Per-host upgrades
    platform_results: list[dict[str, Any]] = []
    for host in hosts:
        try:
            host_result = _upgrade_platform(
                host,
                project_root,
                force=force,
                dry_run=dry_run,
                engagement_level=engagement_level,
                skip_files=skip_files,
            )
            platform_results.append(host_result)
        except Exception as exc:
            result["errors"].append(f"{host}: {exc}")
            platform_results.append(
                {
                    "host": host,
                    "error": str(exc),
                }
            )

    result["components"]["platforms"] = platform_results

    # Karpathy guidelines block — refresh in AGENTS.md and CLAUDE.md after
    # per-host upgrades have potentially created/updated CLAUDE.md.
    try:
        result["components"]["karpathy_guidelines"] = _refresh_karpathy_blocks(
            project_root,
            dry_run=dry_run,
        )
    except Exception as exc:
        result["errors"].append(f"Karpathy guidelines: {exc}")
        result["components"]["karpathy_guidelines"] = {"action": "error", "detail": str(exc)}

    # GitHub templates, CI, Copilot, governance, and issue/PR templates (platform-agnostic)
    if not dry_run:
        try:
            from tapps_mcp.pipeline.github_ci import generate_all_ci_workflows

            ci_result = generate_all_ci_workflows(project_root)
            result["components"]["ci_workflows"] = ci_result
        except Exception as exc:
            result["errors"].append(f"CI workflows: {exc}")

        try:
            from tapps_mcp.pipeline.github_copilot import generate_all_copilot_config

            copilot_result = generate_all_copilot_config(project_root)
            result["components"]["github_copilot"] = copilot_result
        except Exception as exc:
            result["errors"].append(f"Copilot config: {exc}")

        try:
            from tapps_mcp.pipeline.github_templates import generate_all_github_templates

            templates_result = generate_all_github_templates(project_root)
            result["components"]["github_templates"] = templates_result
        except Exception as exc:
            result["errors"].append(f"GitHub templates: {exc}")

        try:
            from tapps_mcp.pipeline.github_governance import generate_all_governance

            governance_result = generate_all_governance(project_root)
            result["components"]["governance"] = governance_result
        except Exception as exc:
            result["errors"].append(f"Governance: {exc}")
    else:
        result["components"]["ci_workflows"] = {"action": "would-regenerate"}
        result["components"]["github_copilot"] = {"action": "would-regenerate"}
        result["components"]["github_templates"] = {"action": "would-regenerate"}
        result["components"]["governance"] = {"action": "would-regenerate"}

    result["success"] = len(result["errors"]) == 0
    result["consumer_requirements"] = "docs/TAPPS_MCP_REQUIREMENTS.md"

    return result
