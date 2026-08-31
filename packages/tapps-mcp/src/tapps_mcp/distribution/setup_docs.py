"""Platform scaffolding: rules, hooks, agents, skills, and core docs.

Everything ``init``/``upgrade`` writes *besides* the MCP server config —
CLAUDE.md, ``.cursor/rules/``, hooks, subagents, skills, AGENTS.md,
TECH_STACK.md — plus the ``.tapps-mcp.yaml`` knobs those generators read.
Split out of ``setup_generator`` (TAP-5733).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

_ENGAGEMENT_LEVELS = ("high", "medium", "low")
_DEFAULT_ENGAGEMENT_LEVEL = "medium"


def _echo_gen_result(kind: str, result: dict[str, Any]) -> None:
    """Print a summary line for a generation result."""
    created = result.get("created") or result.get("scripts_created") or []
    if created:
        click.echo(click.style(f"  Generated {kind}: {', '.join(created)}", fg="green"))
    else:
        click.echo(f"  {kind.capitalize()} already up to date (skipped)")


def _echo_bootstrap_action(action: str, label: str) -> None:
    """Print the created/updated/skipped line for a bootstrap step."""
    if action == "created":
        click.echo(click.style(f"  Created {label}", fg="green"))
    elif action == "updated":
        click.echo(click.style(f"  Updated {label}", fg="green"))
    elif action == "skipped":
        click.echo(f"  {label} already exists (skipped)")


def _generate_claude_scaffolding(project_root: Path, engagement_level: str) -> None:
    """Write CLAUDE.md, settings, hooks, agents, and skills for Claude Code."""
    from tapps_mcp.pipeline.init import _bootstrap_claude, _bootstrap_claude_settings
    from tapps_mcp.pipeline.platform_generators import (
        generate_claude_hooks,
        generate_copilot_instructions,
        generate_skills,
        generate_subagent_definitions,
    )

    action = _bootstrap_claude(project_root, engagement_level=engagement_level)
    if action == "skipped":
        click.echo("  CLAUDE.md already contains TAPPS rules (skipped)")
    else:
        _echo_bootstrap_action(action, "CLAUDE.md with TAPPS pipeline rules")

    settings_action = _bootstrap_claude_settings(project_root)
    if settings_action == "skipped":
        click.echo("  .claude/settings.json already has TappsMCP permissions (skipped)")
    else:
        _echo_bootstrap_action(settings_action, ".claude/settings.json with permissions")

    _echo_gen_result(
        "hooks", generate_claude_hooks(project_root, engagement_level=engagement_level)
    )
    _echo_gen_result("agents", generate_subagent_definitions(project_root, "claude"))
    _echo_gen_result(
        "skills",
        generate_skills(project_root, "claude", engagement_level=engagement_level),
    )
    generate_copilot_instructions(project_root)
    click.echo(click.style("  Generated .github/copilot-instructions.md", fg="green"))


def _generate_cursor_scaffolding(project_root: Path, engagement_level: str) -> None:
    """Write Cursor rules, hooks, agents, skills, and BUGBOT.md."""
    from tapps_mcp.pipeline.init import _bootstrap_cursor
    from tapps_mcp.pipeline.platform_generators import (
        generate_bugbot_rules,
        generate_copilot_instructions,
        generate_cursor_hooks,
        generate_cursor_rules,
        generate_skills,
        generate_subagent_definitions,
    )

    action = _bootstrap_cursor(project_root, engagement_level=engagement_level)
    _echo_bootstrap_action(action, ".cursor/rules/tapps-pipeline.md")

    _echo_gen_result(
        "hooks", generate_cursor_hooks(project_root, engagement_level=engagement_level)
    )
    _echo_gen_result("agents", generate_subagent_definitions(project_root, "cursor"))
    _echo_gen_result(
        "skills",
        generate_skills(project_root, "cursor", engagement_level=engagement_level),
    )
    _echo_gen_result("cursor rules", generate_cursor_rules(project_root))
    generate_bugbot_rules(project_root)
    click.echo(click.style("  Generated .cursor/BUGBOT.md", fg="green"))
    generate_copilot_instructions(project_root)
    click.echo(click.style("  Generated .github/copilot-instructions.md", fg="green"))


def _generate_vscode_scaffolding(project_root: Path) -> None:
    """Write the Copilot instructions file (the only VS Code scaffolding)."""
    from tapps_mcp.pipeline.platform_generators import generate_copilot_instructions

    generate_copilot_instructions(project_root)
    click.echo(click.style("  Generated .github/copilot-instructions.md", fg="green"))


def _generate_rules(
    host: str,
    project_root: Path,
    engagement_level: str | None = None,
    *,
    overwrite_tech_stack: bool = False,
) -> None:
    """Generate platform rule files, hooks, agents, and skills for the given host.

    Delegates to ``_bootstrap_claude`` and ``_bootstrap_cursor`` from
    ``tapps_mcp.pipeline.init``, and uses ``platform_generators`` for hooks,
    subagents, and skills. When *engagement_level* is None, reads from
    project_root/.tapps-mcp.yaml or defaults to ``"medium"``.
    """
    if engagement_level is None:
        engagement_level = _read_engagement_level_from_project(project_root)
    if engagement_level not in _ENGAGEMENT_LEVELS:
        engagement_level = _DEFAULT_ENGAGEMENT_LEVEL

    # Always generate AGENTS.md and TECH_STACK.md (core bootstrap files).
    _generate_core_docs(
        project_root,
        engagement_level=engagement_level,
        overwrite_tech_stack=overwrite_tech_stack,
    )

    if host == "claude-code":
        _generate_claude_scaffolding(project_root, engagement_level)
    elif host == "cursor":
        _generate_cursor_scaffolding(project_root, engagement_level)
    elif host == "vscode":
        _generate_vscode_scaffolding(project_root)


def _write_agents_md(project_root: Path, level: str) -> None:
    """Create or smart-merge AGENTS.md from the engagement-level template."""
    from tapps_mcp.pipeline.agents_md import update_agents_md
    from tapps_mcp.prompts.prompt_loader import load_agents_template

    agents_path = project_root / "AGENTS.md"
    template_content = load_agents_template(level)

    if not agents_path.exists():
        agents_path.write_text(template_content, encoding="utf-8")
        click.echo(click.style("  Created AGENTS.md", fg="green"))
        return

    try:
        action, _detail = update_agents_md(agents_path, template_content, overwrite=False)
    except Exception:
        click.echo("  AGENTS.md update failed (skipped)")
        return
    if action == "validated":
        click.echo("  AGENTS.md is up to date (skipped)")
    else:
        click.echo(click.style(f"  AGENTS.md: {action}", fg="green"))


def _write_tech_stack_md(project_root: Path, *, overwrite_tech_stack: bool) -> None:
    """Render TECH_STACK.md from the detected project profile when needed."""
    tech_stack_path = project_root / "TECH_STACK.md"
    if not overwrite_tech_stack and tech_stack_path.exists():
        click.echo("  TECH_STACK.md already exists (skipped)")
        return

    existed = tech_stack_path.exists()
    try:
        from tapps_mcp.pipeline.init import _render_tech_stack_md
        from tapps_mcp.project.profiler import detect_project_profile

        content = _render_tech_stack_md(detect_project_profile(project_root))
        tech_stack_path.write_text(content, encoding="utf-8")
        verb = "Overwrote" if existed else "Created"
        click.echo(click.style(f"  {verb} TECH_STACK.md", fg="green"))
    except Exception:
        click.echo("  TECH_STACK.md generation failed (skipped)")


def _generate_core_docs(
    project_root: Path,
    *,
    engagement_level: str | None = None,
    overwrite_tech_stack: bool = False,
) -> None:
    """Generate AGENTS.md and TECH_STACK.md if they don't already exist.

    Called from ``_generate_rules`` so that CLI ``init`` produces the same
    core docs that the MCP ``tapps_init`` tool creates. When
    *overwrite_tech_stack* is True, an existing TECH_STACK.md is regenerated
    from the detected project profile.
    """
    level = engagement_level or _read_engagement_level_from_project(project_root)
    _write_agents_md(project_root, level)
    _write_tech_stack_md(project_root, overwrite_tech_stack=overwrite_tech_stack)


# Files each host's scaffolding would create, for ``--dry-run`` reporting.
_PREVIEW_FILES_BY_HOST: dict[str, tuple[str, ...]] = {
    "claude-code": (
        "CLAUDE.md",
        ".claude/settings.json",
        ".claude/hooks/ (tapps-session-start, tapps-stop, ...)",
        ".claude/agents/ (tapps-reviewer, tapps-validator, ...)",
        ".claude/skills/ (tapps-score, tapps-validate, ...)",
        ".github/copilot-instructions.md",
    ),
    "cursor": (
        ".cursor/rules/tapps-pipeline.md",
        ".cursor/hooks/ (tapps-before-mcp, ...)",
        ".cursor/agents/ (tapps-reviewer, tapps-validator, ...)",
        ".cursor/skills/ (tapps-score, tapps-validate, ...)",
        ".cursor/rules/ (tapps-quality, ...)",
        ".cursor/BUGBOT.md",
        ".github/copilot-instructions.md",
    ),
    "vscode": (
        ".github/copilot-instructions.md",
    ),
}

# Common files generated by bootstrap_pipeline (via MCP tool or upgrade).
_PREVIEW_COMMON_FILES: tuple[str, ...] = ("AGENTS.md", "TECH_STACK.md")


def _preview_rules(host: str) -> None:
    """Preview which rule/hook/agent/skill files would be generated (dry-run).

    Enumerates the same files as :func:`_generate_rules` without writing
    anything, so ``--dry-run`` output is complete.
    """
    files = [*_PREVIEW_FILES_BY_HOST.get(host, ()), *_PREVIEW_COMMON_FILES]
    if files:
        click.echo(click.style("[DRY-RUN] Would also create/update:", fg="cyan"))
        for f in files:
            click.echo(f"  - {f}")


# ---------------------------------------------------------------------------
# .tapps-mcp.yaml knobs
# ---------------------------------------------------------------------------


def _read_engagement_level_from_project(project_root: Path) -> str:
    """Read llm_engagement_level from project_root/.tapps-mcp.yaml if present."""
    import yaml

    config_path = project_root / ".tapps-mcp.yaml"
    if not config_path.exists():
        return _DEFAULT_ENGAGEMENT_LEVEL
    try:
        with config_path.open(encoding="utf-8-sig") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        return _DEFAULT_ENGAGEMENT_LEVEL
    if not isinstance(data, dict):
        return _DEFAULT_ENGAGEMENT_LEVEL
    level = data.get("llm_engagement_level", _DEFAULT_ENGAGEMENT_LEVEL)
    return level if level in _ENGAGEMENT_LEVELS else _DEFAULT_ENGAGEMENT_LEVEL


def _write_engagement_level_to_yaml(project_root: Path, level: str) -> None:
    """Write or merge llm_engagement_level into project_root/.tapps-mcp.yaml."""
    import yaml

    config_path = project_root / ".tapps-mcp.yaml"
    data: dict[str, Any] = {}
    if config_path.exists():
        try:
            with config_path.open(encoding="utf-8-sig") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            data = {}
    if not isinstance(data, dict):
        data = {}
    data["llm_engagement_level"] = level
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def _write_mcp_transport_to_yaml(project_root: Path, transport: str) -> None:
    """Persist ``mcp_transport`` to ``.tapps-mcp.yaml``.

    Called when the transport is chosen explicitly or resolves to ``http`` so
    the generated host config and the yaml source-of-truth stay consistent.
    """
    import yaml

    config_path = project_root / ".tapps-mcp.yaml"
    data: dict[str, Any] = {}
    if config_path.is_file():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    data["mcp_transport"] = transport
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as handle:
        yaml.dump(data, handle, default_flow_style=False, sort_keys=False)


def _ensure_project_yaml_defaults(project_root: Path) -> None:
    """Merge tapps-managed defaults into ``.tapps-mcp.yaml`` during init/upgrade."""
    from tapps_mcp.pipeline.init import _ensure_cursor_stop_completion_gate_config

    _ensure_cursor_stop_completion_gate_config(project_root)
