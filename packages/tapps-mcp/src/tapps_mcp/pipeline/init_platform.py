"""Platform-specific bootstrap: rules, hooks, agents, skills, and file-op mode.

Split out of :mod:`~tapps_mcp.pipeline.init` (TAP-5733).  ``_setup_platform``
was a single 237-line function at cyclomatic complexity 27; it is decomposed
here into an orchestrator plus per-platform and per-concern helpers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tapps_core.common.file_operations import FileOperation
from tapps_mcp.pipeline.init_claude_md import _bootstrap_claude, _bootstrap_cursor
from tapps_mcp.pipeline.init_config_yaml import (
    _ensure_cursor_stop_completion_gate_config,
    _ensure_memory_hooks_config,
    _persist_skill_tier,
)
from tapps_mcp.pipeline.init_github import (
    _setup_github_ci,
    _setup_github_copilot,
    _setup_github_governance,
    _setup_github_templates,
)
from tapps_mcp.pipeline.init_permissions import _bootstrap_claude_settings
from tapps_mcp.prompts.prompt_loader import load_platform_rules

if TYPE_CHECKING:
    from pathlib import Path

    from tapps_mcp.pipeline.init_state import BootstrapConfig, _BootstrapState


def _karpathy_primary_home(project_root: Path) -> str | None:
    """Return the single Karpathy home filename, preferring AGENTS.md."""
    if (project_root / "AGENTS.md").exists():
        return "AGENTS.md"
    if (project_root / "CLAUDE.md").exists():
        return "CLAUDE.md"
    return None


def _install_karpathy_blocks(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Install or refresh Karpathy guidelines into a single primary home.

    Prefers ``AGENTS.md`` when present, otherwise ``CLAUDE.md``. Content
    outside BEGIN/END markers is preserved. Does not newly dual-write.
    When ``.cursor/rules/`` exists, also installs the Cursor ``.mdc`` rule.
    """
    if not cfg.include_karpathy:
        state.result["karpathy_guidelines"] = {"action": "skipped", "reason": "disabled"}
        return
    if state.content_return:
        state.result["karpathy_guidelines"] = {"action": "skipped", "reason": "content_return"}
        return

    from tapps_mcp.pipeline import karpathy_block

    primary = _karpathy_primary_home(state.project_root)
    per_file: dict[str, str] = {}
    if primary is None:
        state.result["karpathy_guidelines"] = {
            "source_sha": karpathy_block.KARPATHY_GUIDELINES_SOURCE_SHA,
            "files": {"AGENTS.md": "skipped_file_missing", "CLAUDE.md": "skipped_file_missing"},
            "primary": None,
            "cursor_rule": karpathy_block.install_or_refresh_cursor_rule(
                state.project_root, dry_run=cfg.dry_run
            ),
        }
        return

    for rel in ("AGENTS.md", "CLAUDE.md"):
        target = state.project_root / rel
        if not target.exists():
            per_file[rel] = "skipped_file_missing"
            continue
        if rel != primary:
            per_file[rel] = "skipped (single-home)"
            continue
        try:
            per_file[rel] = karpathy_block.install_or_refresh(target, dry_run=cfg.dry_run)
        except Exception as exc:
            per_file[rel] = "error"
            state.errors.append(f"Karpathy guidelines install failed for {rel}: {exc}")

    cursor_action = "skipped_no_cursor"
    try:
        cursor_action = karpathy_block.install_or_refresh_cursor_rule(
            state.project_root, dry_run=cfg.dry_run
        )
    except Exception as exc:
        cursor_action = "error"
        state.errors.append(f"Karpathy Cursor rule install failed: {exc}")

    state.result["karpathy_guidelines"] = {
        "source_sha": karpathy_block.KARPATHY_GUIDELINES_SOURCE_SHA,
        "files": per_file,
        "primary": primary,
        "cursor_rule": cursor_action,
    }


def _skill_engagement_note(engagement_level: str) -> str:
    if engagement_level == "high":
        return "*Engagement: MANDATORY for high-enforcement projects.*\n\n"
    if engagement_level == "low":
        return "*Engagement: Optional for low-enforcement projects.*\n\n"
    return ""


def _append_skill_file_ops(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Emit platform skill templates as FileOperations for content-return mode."""
    if cfg.minimal or not cfg.platform:
        return

    from tapps_mcp.pipeline.platform_skills import CLAUDE_SKILLS, CURSOR_SKILLS
    from tapps_mcp.pipeline.skill_managed_block import prepend_below_frontmatter

    if cfg.platform == "claude":
        templates = CLAUDE_SKILLS
        prefix = ".claude/skills"
    elif cfg.platform == "cursor":
        templates = CURSOR_SKILLS
        prefix = ".cursor/skills"
    else:
        return

    note = _skill_engagement_note(cfg.llm_engagement_level)
    created_skills: list[str] = []
    for skill_name, content in templates.items():
        rel_path = f"{prefix}/{skill_name}/SKILL.md"
        state.file_ops.append(
            FileOperation(
                path=rel_path,
                content=prepend_below_frontmatter(content, note),
                mode="create",
                description=f"TappsMCP skill template: {skill_name}",
                priority=3,
            )
        )
        state.created.append(rel_path)
        created_skills.append(skill_name)

    state.result["skills"] = {
        "action": "content_return",
        "created": created_skills,
    }


def _generate_platform_file_ops(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Generate platform files as FileOperations for content-return mode (Epic 87).

    Instead of writing files directly (which requires filesystem access),
    generate the key platform files from template loaders and add them as
    :class:`FileOperation` entries in ``state.file_ops``.

    Skills are included in the manifest; hooks, sub-agents, CI, and GitHub
    templates still require a follow-up ``tapps_upgrade`` on the host.
    """
    engagement = cfg.llm_engagement_level
    platform = cfg.platform

    if not platform:
        state.result["platform_rules"] = {
            "platform": "(none)",
            "action": "content_return",
        }
        return

    # CLAUDE.md or Cursor rules
    if platform == "claude":
        content = load_platform_rules("claude", engagement_level=engagement)
        state.file_ops.append(
            FileOperation(
                path="CLAUDE.md",
                content=content,
                mode="merge",
                description=(
                    "TappsMCP pipeline section for CLAUDE.md. "
                    "Append to existing file (do not overwrite). "
                    "If a '# TAPPS Quality Pipeline' section already exists, replace only that section."
                ),
                priority=2,
            )
        )
        state.created.append("CLAUDE.md")
    elif platform == "cursor":
        content = load_platform_rules("cursor", engagement_level=engagement)
        state.file_ops.append(
            FileOperation(
                path=".cursor/rules/tapps-pipeline.mdc",
                content=content,
                mode="create",
                description="Cursor platform rules with TappsMCP pipeline reference.",
                priority=2,
            )
        )
        state.created.append(".cursor/rules/tapps-pipeline.mdc")

    state.result["platform_rules"] = {
        "platform": platform,
        "action": "content_return",
    }

    _append_skill_file_ops(cfg, state)

    required_handoff = ("tapps-handoff-session", "tapps-continue-session")
    manifest_paths = {op.path for op in state.file_ops}
    missing_handoff = [
        name
        for name in required_handoff
        if not any(f"/{name}/SKILL.md" in p for p in manifest_paths)
    ]
    if missing_handoff:
        state.warnings.append(
            "Content-return manifest missing session handoff skills: " + ", ".join(missing_handoff)
        )
        state.result["session_handoff_skills"] = {
            "ok": False,
            "message": f"Missing from manifest: {', '.join(missing_handoff)}",
            "detail": "Apply file_manifest via tapps-apply-files skill",
        }
    else:
        state.result["session_handoff_skills"] = {
            "ok": True,
            "message": "tapps-handoff-session + tapps-continue-session in file_manifest",
            "detail": None,
        }

    # Hooks, sub-agents, CI workflows, and GitHub templates still write to disk
    # or need host-specific wiring — run upgrade after applying the manifest.
    state.result["platform_generators_skipped"] = {
        "reason": "content_return",
        "skipped_components": [
            "hooks",
            "sub-agents",
            "ci_workflows",
            "github_templates",
            "copilot_config",
            "governance",
        ],
        "included_components": ["skills"],
        "hint": (
            "Run 'tapps_upgrade' after writing these files to generate "
            "hooks, sub-agents, and CI configuration."
        ),
    }


def _record_session_handoff_skill_check(state: _BootstrapState) -> None:
    """Verify session-transfer skills landed after ``generate_skills``.

    Keeps init/upgrade at parity with what ``tapps doctor`` reports.
    """
    from tapps_mcp.distribution.doctor import check_session_handoff_skills

    check = check_session_handoff_skills(state.project_root)
    state.result["session_handoff_skills"] = {
        "ok": check.ok,
        "message": check.message,
        "detail": check.detail,
    }
    if not check.ok:
        state.warnings.append(
            f"Session handoff skills incomplete: {check.message}. "
            "Run tapps-mcp upgrade --force to refresh all skill templates."
        )


def _ensure_project_yaml_defaults(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Seed ``.tapps-mcp.yaml`` defaults that platform wiring depends on."""
    mh_action = _ensure_memory_hooks_config(
        state.project_root,
        cfg.llm_engagement_level,
        dry_run=cfg.dry_run,
        warnings=state.warnings,
    )
    state.result["memory_hooks_config"] = {"action": mh_action}
    gate_action = _ensure_cursor_stop_completion_gate_config(
        state.project_root, dry_run=cfg.dry_run, warnings=state.warnings
    )
    state.result["cursor_stop_completion_gate_config"] = {"action": gate_action}


def _install_claude_optional_integrations(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Install the opt-in Claude integrations: git hooks, Linear SDLC, Report Studio, judges."""
    if cfg.install_git_hooks:
        from tapps_mcp.pipeline.git_hooks import install_git_pre_commit

        state.result["git_hooks"] = install_git_pre_commit(
            state.project_root,
            dry_run=state.dry_run,
            content_return=state.content_return,
        )
        if state.result["git_hooks"].get("installed"):
            state.created.append(".githooks/pre-commit")

    if cfg.linear_sdlc:
        from tapps_mcp.pipeline.linear_sdlc import LinearSDLCConfig
        from tapps_mcp.pipeline.linear_sdlc.installer import install_linear_sdlc

        sdlc_config = LinearSDLCConfig(
            issue_prefix=cfg.linear_issue_prefix,
            team_id=cfg.linear_team_id,
            project_id=cfg.linear_project_id,
        )
        state.result["linear_sdlc"] = install_linear_sdlc(
            state.project_root,
            sdlc_config,
            dry_run=state.dry_run,
            content_return=state.content_return,
        )
        state.created.extend(state.result["linear_sdlc"].get("files_written", []))

    if cfg.with_report_studio:
        from tapps_mcp.pipeline.report_studio.installer import install_report_studio

        scaffold_name = cfg.report_studio_scaffold.strip() or None
        state.result["report_studio"] = install_report_studio(
            state.project_root,
            tag=cfg.report_studio_tag,
            report_name=scaffold_name,
            template_id=cfg.report_studio_template,
            dry_run=state.dry_run,
            content_return=state.content_return,
        )
        state.created.extend(state.result["report_studio"].get("files_written", []))

    from tapps_mcp.pipeline.document_judges import (
        is_document_consumer,
        merge_document_judges_into_yaml,
        merge_document_memory_profile,
    )

    if is_document_consumer(state.project_root):
        state.result["document_judges"] = merge_document_judges_into_yaml(
            state.project_root,
            dry_run=state.dry_run,
        )
        state.result["document_memory_profile"] = merge_document_memory_profile(
            state.project_root,
            dry_run=state.dry_run,
        )


def _generate_claude_scoped_rules(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Generate the per-concern Claude rule files.

    TAP-978: init runs only when the user signals intent, so these are
    generated unconditionally — matching the python_quality_rule pattern.
    ``upgrade.py`` is where language gating is applied.
    """
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

    root = state.project_root
    state.result["python_quality_rule"] = generate_claude_python_quality_rule(
        root, engagement_level=cfg.llm_engagement_level
    )
    state.result["agent_scope_rule"] = generate_claude_agent_scope_rule(root)
    state.result["agent_to_agent_rule"] = generate_claude_agent_to_agent_rule(root)
    state.result["autonomy_rule"] = generate_claude_autonomy_rule(root)
    state.result["linear_standards_rule"] = generate_claude_linear_standards_rule(root)
    state.result["integration_hygiene_rule"] = generate_claude_integration_hygiene_rule(root)
    state.result["security_rule"] = generate_claude_security_rule(root)
    state.result["test_quality_rule"] = generate_claude_test_quality_rule(root)
    state.result["config_files_rule"] = generate_claude_config_files_rule(root)


def _generate_project_scripts(state: _BootstrapState) -> None:
    """Generate project-root scaffolded scripts (TAP-6884).

    ``scripts/measure.py`` and ``scripts/gitfacts.sh`` live at the project
    root, not under ``.claude/`` — host-agnostic like the scoped rule files,
    generated unconditionally to match that pattern.
    """
    from tapps_mcp.pipeline.platform_project_scripts import (
        generate_gitfacts_script,
        generate_measure_script,
    )

    root = state.project_root
    state.result["measure_script"] = generate_measure_script(root)
    state.result["gitfacts_script"] = generate_gitfacts_script(root)


def _generate_docs_automation(state: _BootstrapState, platform: str) -> None:
    """Generate doc-automation wiring when DocsMCP is detected (Epic 86)."""
    from tapps_mcp.pipeline.platform_docs_automation import generate_docs_automation

    state.result["docs_automation"] = generate_docs_automation(state.project_root, platform)


def _generate_claude_components(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Generate the non-minimal Claude component set."""
    from tapps_mcp.pipeline.platform_generators import (
        generate_agent_teams_hooks,
        generate_claude_hooks,
        generate_skills,
        generate_subagent_definitions,
    )
    from tapps_mcp.pipeline.platform_hooks import wire_memory_hooks

    engagement = cfg.llm_engagement_level
    state.result["hooks"] = generate_claude_hooks(
        state.project_root,
        engagement_level=engagement,
        destructive_guard=cfg.destructive_guard,
        linear_enforce_gate=cfg.linear_enforce_gate,
        linear_enforce_cache_gate=cfg.linear_enforce_cache_gate,
        session_start_gate=cfg.session_start_gate,
    )
    _install_claude_optional_integrations(cfg, state)
    state.result["agents"] = generate_subagent_definitions(state.project_root, "claude")
    state.result["skills"] = generate_skills(
        state.project_root,
        "claude",
        engagement_level=engagement,
        skill_tier=cfg.skill_tier,
    )
    _persist_skill_tier(state.project_root, cfg.skill_tier, dry_run=cfg.dry_run)
    _generate_claude_scoped_rules(cfg, state)
    _generate_project_scripts(state)

    if cfg.docs_automation and state.result.get("docsmcp_detected", False):
        _generate_docs_automation(state, "claude")
    if cfg.agent_teams:
        state.result["agent_teams"] = generate_agent_teams_hooks(state.project_root)

    # Epic 65.4/65.6: wire auto-recall and auto-capture from config or explicit param
    state.result.update(
        wire_memory_hooks(
            state.project_root,
            platform="claude",
            memory_auto_recall=cfg.memory_auto_recall,
            memory_auto_capture=cfg.memory_auto_capture,
        )
    )


def _setup_claude_platform(cfg: BootstrapConfig, state: _BootstrapState) -> str:
    """Bootstrap CLAUDE.md, settings, and (unless minimal) the component set."""
    engagement = cfg.llm_engagement_level
    platform_action = _bootstrap_claude(
        state.project_root, cfg.overwrite_platform_rules, engagement_level=engagement
    )
    if platform_action == "created":
        state.created.append("CLAUDE.md")

    settings_action = _bootstrap_claude_settings(
        state.project_root,
        engagement_level=engagement,
        docsmcp_detected=state.result.get("docsmcp_detected", False),
    )
    state.result["claude_settings"] = {"action": settings_action}
    if settings_action in {"created", "updated"}:
        state.warnings.append(
            "MCP servers are only connected at session start. "
            "Restart your Claude Code session for tapps-mcp tools to become available."
        )
    if settings_action == "created":
        state.created.append(".claude/settings.json")

    if not cfg.minimal:
        _generate_claude_components(cfg, state)
    return platform_action


def _setup_cursor_platform(cfg: BootstrapConfig, state: _BootstrapState) -> str:
    """Bootstrap the Cursor rule file and (unless minimal) the component set."""
    from tapps_mcp.pipeline.platform_generators import (
        generate_bugbot_rules,
        generate_cursor_hooks,
        generate_cursor_rules,
        generate_skills,
        generate_subagent_definitions,
    )
    from tapps_mcp.pipeline.platform_hooks import wire_memory_hooks

    engagement = cfg.llm_engagement_level
    platform_action = _bootstrap_cursor(
        state.project_root, cfg.overwrite_platform_rules, engagement_level=engagement
    )
    if platform_action in {"created", "updated"}:
        state.created.append(".cursor/rules/tapps-pipeline.mdc")
    elif platform_action == "skipped":
        state.skipped.append(".cursor/rules/tapps-pipeline.mdc")

    if not cfg.minimal:
        state.result["hooks"] = generate_cursor_hooks(
            state.project_root, engagement_level=engagement
        )
        state.result.update(
            wire_memory_hooks(
                state.project_root,
                platform="cursor",
                memory_auto_recall=cfg.memory_auto_recall,
            )
        )
        state.result["agents"] = generate_subagent_definitions(state.project_root, "cursor")
        state.result["skills"] = generate_skills(
            state.project_root,
            "cursor",
            engagement_level=engagement,
            skill_tier=cfg.skill_tier,
        )
        _persist_skill_tier(state.project_root, cfg.skill_tier, dry_run=cfg.dry_run)
        if cfg.docs_automation and state.result.get("docsmcp_detected", False):
            _generate_docs_automation(state, "cursor")
        state.result["cursor_rules"] = generate_cursor_rules(state.project_root)
        state.result["bugbot_rules"] = generate_bugbot_rules(state.project_root)
    return platform_action


def _setup_start_program_script(state: _BootstrapState) -> None:
    """Place ``scripts/start-program.sh``, the multi-session program kickoff (TAP-6885)."""
    try:
        from tapps_mcp.pipeline.platform_skill_orchestration import (
            generate_start_program_script,
        )

        state.result["start_program_script"] = generate_start_program_script(state.project_root)
    except Exception as exc:
        state.errors.append(f"start-program.sh: {exc}")
        state.result["start_program_script"] = {"error": str(exc)}


def _finalize_platform_setup(
    cfg: BootstrapConfig, state: _BootstrapState, platform_action: str | None
) -> None:
    """Record the platform result and run the shared post-platform steps."""
    state.result["platform_rules"] = {
        "platform": cfg.platform,
        "action": platform_action or "skipped",
    }

    if not cfg.minimal and not cfg.dry_run and cfg.platform in {"claude", "cursor"}:
        _record_session_handoff_skill_check(state)

    if not cfg.minimal:
        _setup_github_templates(state)
        _setup_github_ci(state)
        _setup_github_copilot(state)
        _setup_github_governance(state)
        if not cfg.dry_run:
            _setup_start_program_script(state)


def _setup_platform(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Bootstrap platform-specific rule files, hooks, agents, and skills."""
    if not cfg.platform:
        return

    _ensure_project_yaml_defaults(cfg, state)

    platform_action: str | None = None
    if cfg.platform == "claude":
        platform_action = _setup_claude_platform(cfg, state)
    elif cfg.platform == "cursor":
        platform_action = _setup_cursor_platform(cfg, state)
    else:
        state.errors.append(f"Unknown platform: {cfg.platform!r}. Use 'claude' or 'cursor'.")

    _finalize_platform_setup(cfg, state, platform_action)
