"""Bootstrap TAPPS pipeline files in a consuming project."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from tapps_mcp import __version__

if TYPE_CHECKING:
    from pathlib import Path

    from tapps_mcp.project.models import ProjectProfile, TechStack

from tapps_mcp.prompts.prompt_loader import (
    load_agents_template,
    load_handoff_template,
    load_platform_rules,
    load_runlog_template,
)


class _SafeWriter(Protocol):
    def __call__(self, rel_path: str, content: str) -> None: ...


@dataclass
class BootstrapConfig:
    """Configuration for ``bootstrap_pipeline`` to reduce parameter count."""

    create_handoff: bool = True
    create_runlog: bool = True
    create_agents_md: bool = True
    create_tech_stack_md: bool = True
    platform: str = ""
    verify_server: bool = True
    install_missing_checkers: bool = False
    warm_cache_from_tech_stack: bool = True
    warm_expert_rag_from_tech_stack: bool = True
    overwrite_platform_rules: bool = False
    overwrite_agents_md: bool = False
    agent_teams: bool = False


@dataclass
class _BootstrapState:
    """Mutable accumulator shared between sub-functions."""

    project_root: Path
    created: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)
    profile: ProjectProfile | None = None

    def safe_write(self, rel_path: str, content: str) -> None:
        """Write *content* to *rel_path* under project_root, safely."""
        target = (self.project_root / rel_path).resolve()
        try:
            target.relative_to(self.project_root)
        except ValueError:
            self.errors.append(f"{rel_path}: path escapes project root")
            return
        if target.exists():
            self.skipped.append(rel_path)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.created.append(rel_path)

    def safe_write_or_overwrite(self, rel_path: str, content: str) -> str:
        """Write or overwrite content. Returns 'created', 'updated', or 'skipped'."""
        target = (self.project_root / rel_path).resolve()
        try:
            target.relative_to(self.project_root)
        except ValueError:
            self.errors.append(f"{rel_path}: path escapes project root")
            return "skipped"
        existed = target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        if existed:
            return "updated"
        self.created.append(rel_path)
        return "created"

    def finalize(self) -> dict[str, Any]:
        """Return the final result dict."""
        self.result["created"] = self.created
        self.result["skipped"] = self.skipped
        self.result["errors"] = self.errors
        self.result["success"] = len(self.errors) == 0
        return self.result


def bootstrap_pipeline(
    project_root: Path,
    *,
    create_handoff: bool = True,
    create_runlog: bool = True,
    create_agents_md: bool = True,
    create_tech_stack_md: bool = True,
    platform: str = "",
    verify_server: bool = True,
    install_missing_checkers: bool = False,
    warm_cache_from_tech_stack: bool = True,
    warm_expert_rag_from_tech_stack: bool = True,
    overwrite_platform_rules: bool = False,
    overwrite_agents_md: bool = False,
    agent_teams: bool = False,
) -> dict[str, Any]:
    """Create pipeline template files in the project.

    Returns a summary dict with ``created``, ``skipped``, ``errors``, and
    subsystem result dicts.
    """
    cfg = BootstrapConfig(
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
        agent_teams=agent_teams,
    )
    state = _BootstrapState(project_root=project_root.resolve())

    _verify_server(cfg, state)
    _detect_profile(cfg, state)
    _create_templates(cfg, state)
    _setup_platform(cfg, state)
    _warm_caches(cfg, state)

    return state.finalize()


def _verify_server(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Run server verification and optional checker install."""
    if cfg.verify_server or cfg.install_missing_checkers:
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
        content = _render_tech_stack_md(state.profile)
        action = state.safe_write_or_overwrite("TECH_STACK.md", content)
        state.result["tech_stack_md"] = {"action": action}
    elif cfg.create_tech_stack_md:
        state.result["tech_stack_md"] = {"action": "skipped", "reason": "profile_failed"}
        state.errors.append("Could not create TECH_STACK.md: project profile detection failed")
    else:
        state.result["tech_stack_md"] = {"action": "skipped", "reason": "disabled"}


def _create_agents_md(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Create or update AGENTS.md."""
    agents_path = state.project_root / "AGENTS.md"
    template_content = load_agents_template()
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


def _setup_platform(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Bootstrap platform-specific rule files, hooks, agents, and skills."""
    if not cfg.platform:
        return

    from tapps_mcp.pipeline.platform_generators import (
        generate_agent_teams_hooks,
        generate_bugbot_rules,
        generate_ci_workflow,
        generate_claude_hooks,
        generate_copilot_instructions,
        generate_cursor_hooks,
        generate_cursor_rules,
        generate_skills,
        generate_subagent_definitions,
    )

    platform_action: str | None = None
    if cfg.platform == "claude":
        platform_action = _bootstrap_claude(state.project_root, cfg.overwrite_platform_rules)
        if platform_action == "created":
            state.created.append("CLAUDE.md")
        settings_action = _bootstrap_claude_settings(state.project_root)
        state.result["claude_settings"] = {"action": settings_action}
        if settings_action == "created":
            state.created.append(".claude/settings.json")
        # Hooks, agents, skills
        state.result["hooks"] = generate_claude_hooks(state.project_root)
        state.result["agents"] = generate_subagent_definitions(state.project_root, "claude")
        state.result["skills"] = generate_skills(state.project_root, "claude")
        # Agent Teams (opt-in)
        if cfg.agent_teams:
            state.result["agent_teams"] = generate_agent_teams_hooks(state.project_root)
        # CI workflow (generated for all platforms)
        state.result["ci_workflow"] = generate_ci_workflow(state.project_root)
        # VS Code Copilot instructions (generated for all platforms)
        state.result["copilot_instructions"] = generate_copilot_instructions(
            state.project_root,
        )
    elif cfg.platform == "cursor":
        platform_action = _bootstrap_cursor(state.project_root, cfg.overwrite_platform_rules)
        if platform_action in {"created", "updated"}:
            state.created.append(".cursor/rules/tapps-pipeline.md")
        elif platform_action == "skipped":
            state.skipped.append(".cursor/rules/tapps-pipeline.md")
        # Hooks, agents, skills, enhanced rules
        state.result["hooks"] = generate_cursor_hooks(state.project_root)
        state.result["agents"] = generate_subagent_definitions(state.project_root, "cursor")
        state.result["skills"] = generate_skills(state.project_root, "cursor")
        state.result["cursor_rules"] = generate_cursor_rules(state.project_root)
        # BugBot rules (Cursor-specific)
        state.result["bugbot_rules"] = generate_bugbot_rules(state.project_root)
        # CI workflow (generated for all platforms)
        state.result["ci_workflow"] = generate_ci_workflow(state.project_root)
        # VS Code Copilot instructions (generated for all platforms)
        state.result["copilot_instructions"] = generate_copilot_instructions(
            state.project_root,
        )
    else:
        state.errors.append(f"Unknown platform: {cfg.platform!r}. Use 'claude' or 'cursor'.")

    state.result["platform_rules"] = {
        "platform": cfg.platform,
        "action": platform_action or "skipped",
    }


def _warm_caches(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Warm Context7 cache and expert RAG indices."""
    if cfg.warm_cache_from_tech_stack and state.profile is not None:
        cache_result = _run_cache_warming(
            state.project_root,
            state.profile.tech_stack.context7_priority,
        )
        state.result["cache_warming"] = cache_result
        if cache_result.get("error"):
            state.errors.append(f"Cache warming failed: {cache_result['error']}")
    else:
        state.result["cache_warming"] = {
            "warmed": 0,
            "attempted": 0,
            "skipped": "disabled" if not cfg.warm_cache_from_tech_stack else "profile_failed",
            "libraries": [],
        }

    if cfg.warm_expert_rag_from_tech_stack and state.profile is not None:
        state.result["expert_rag_warming"] = _run_expert_rag_warming(
            state.project_root,
            state.profile.tech_stack,
        )
    else:
        state.result["expert_rag_warming"] = {
            "warmed": 0,
            "attempted": 0,
            "skipped": "disabled" if not cfg.warm_expert_rag_from_tech_stack else "profile_failed",
            "domains": [],
        }


def _run_server_verification(
    project_root: Path,
    *,
    install_missing: bool = False,
) -> dict[str, Any]:
    """Verify server info and optionally install missing checkers."""
    from tapps_mcp.tools.tool_detection import detect_installed_tools

    installed = detect_installed_tools()
    missing = [t for t in installed if not t.available]
    missing_names = [t.name for t in missing]
    install_hints = [t.install_hint for t in missing if t.install_hint]

    result: dict[str, Any] = {
        "ok": len(missing) == 0,
        "missing_checkers": missing_names,
        "installed": [t.name for t in installed if t.available],
        "install_hints": install_hints,
        "checker_install_attempted": False,
    }

    if install_missing and missing:
        result["checker_install_attempted"] = True
        import contextlib
        import subprocess
        import sys

        for hint in install_hints:
            if hint and hint.startswith("pip install "):
                pkg = hint.replace("pip install ", "").strip()
                with contextlib.suppress(subprocess.TimeoutExpired, FileNotFoundError, OSError):
                    subprocess.run(
                        [sys.executable, "-m", "pip", "install", pkg],
                        capture_output=True,
                        timeout=60,
                        check=False,
                        cwd=project_root,
                    )

        # Re-detect after install
        installed_after = detect_installed_tools()
        result["ok"] = all(t.available for t in installed_after)
        result["installed"] = [t.name for t in installed_after if t.available]
        result["missing_checkers"] = [t.name for t in installed_after if not t.available]

    return result


def _render_tech_stack_md(profile: ProjectProfile) -> str:
    """Render TECH_STACK.md content from project profile."""
    ts = profile.tech_stack
    lines = [
        "# Tech Stack",
        "",
        "## Project Type",
        f"- **Type:** {profile.project_type or 'unknown'}",
        f"- **Confidence:** {profile.project_type_confidence:.2f}",
        f"- **Reason:** {profile.project_type_reason or 'N/A'}",
        "",
        "## Languages",
    ]
    for lang in ts.languages or ["(none detected)"]:
        lines.append(f"- {lang}")
    lines.extend(["", "## Frameworks"])
    for fw in ts.frameworks or ["(none detected)"]:
        lines.append(f"- {fw}")
    lines.extend(["", "## Libraries"])
    for lib in ts.libraries or ["(none detected)"]:
        lines.append(f"- {lib}")
    lines.extend(["", "## Domains"])
    for d in ts.domains or ["(none detected)"]:
        lines.append(f"- {d}")
    lines.extend(["", "## Context7 Priority (for doc lookups)"])
    for p in ts.context7_priority or []:
        lines.append(f"- {p}")
    ci_str = "Yes (" + ", ".join(profile.ci_systems) + ")" if profile.has_ci else "No"
    tests_str = "Yes (" + ", ".join(profile.test_frameworks) + ")" if profile.has_tests else "No"
    lines.extend(
        [
            "",
            "## Infrastructure",
            f"- **CI:** {ci_str}",
            f"- **Docker:** {'Yes' if profile.has_docker else 'No'}",
            f"- **Tests:** {tests_str}",
            f"- **Package managers:** {', '.join(profile.package_managers) or 'N/A'}",
            "",
            "## Recommendations",
        ]
    )
    for rec in profile.quality_recommendations or ["(none)"]:
        lines.append(f"- {rec}")
    lines.append("")
    return "\n".join(lines)


def _run_cache_warming(
    project_root: Path,
    libraries: list[str],
) -> dict[str, Any]:
    """Run cache warming for libraries from tech stack."""
    import asyncio

    from tapps_mcp.config.settings import load_settings
    from tapps_mcp.knowledge.cache import KBCache
    from tapps_mcp.knowledge.warming import warm_cache

    settings = load_settings()
    api_key = settings.context7_api_key

    if not api_key or not api_key.get_secret_value():
        return {
            "warmed": 0,
            "attempted": 0,
            "skipped": "no_api_key",
            "libraries": libraries[:20],
        }

    if not libraries:
        return {
            "warmed": 0,
            "attempted": 0,
            "skipped": "no_libraries",
            "libraries": [],
        }

    cache_dir = project_root / ".tapps-mcp-cache"
    cache = KBCache(cache_dir)

    error: str | None = None
    try:
        warmed = asyncio.run(
            warm_cache(
                project_root,
                cache,
                api_key=api_key,
                libraries=libraries[:20],
                max_libraries=20,
            )
        )
    except Exception as exc:  # pragma: no cover - defensive guardrail
        warmed = 0
        error = f"{type(exc).__name__}: {exc}"

    return {
        "warmed": warmed,
        "attempted": min(len(libraries), 20),
        "skipped": None,
        "error": error,
        "libraries": libraries[:20],
    }


def _run_expert_rag_warming(
    project_root: Path,
    tech_stack: TechStack,
) -> dict[str, Any]:
    """Pre-build expert RAG indices for domains relevant to tech stack."""
    from tapps_mcp.experts.rag_warming import warm_expert_rag_indices

    index_base = project_root / ".tapps-mcp" / "rag_index"
    return warm_expert_rag_indices(
        tech_stack,
        max_domains=10,
        index_base_dir=index_base,
    )


def _bootstrap_claude(
    project_root: Path,
    overwrite: bool = False,
) -> str:
    """Create or update CLAUDE.md with TAPPS pipeline reference.

    Returns ``'created'``, ``'updated'``, or ``'skipped'``.
    """
    claude_md = project_root / "CLAUDE.md"
    content = load_platform_rules("claude")

    if claude_md.exists():
        existing = claude_md.read_text(encoding="utf-8")
        if "TAPPS" in existing and not overwrite:
            # Already has TAPPS reference
            return "skipped"
        # Append to existing file (or refresh content when overwrite=True)
        if overwrite:
            new_content = existing.rstrip() + "\n\n" + content
        else:
            new_content = existing.rstrip() + "\n\n" + content
        claude_md.write_text(new_content, encoding="utf-8")
        return "updated"

    claude_md.write_text(content, encoding="utf-8")
    return "created"


def _bootstrap_claude_settings(project_root: Path) -> str:
    """Create or update ``.claude/settings.json`` with permission wildcard.

    Ensures ``"mcp__tapps-mcp__*"`` is in ``permissions.allow`` so that
    Claude Code auto-approves all TappsMCP tools without user prompts.

    Returns ``'created'``, ``'updated'``, or ``'skipped'``.
    """
    import json
    from pathlib import Path as _Path

    settings_dir = _Path(project_root) / ".claude"
    settings_file = settings_dir / "settings.json"
    wildcard = "mcp__tapps-mcp__*"

    if not settings_file.exists():
        settings_dir.mkdir(parents=True, exist_ok=True)
        config: dict[str, Any] = {"permissions": {"allow": [wildcard]}}
        settings_file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        return "created"

    raw = settings_file.read_text(encoding="utf-8")
    config = json.loads(raw) if raw.strip() else {}

    permissions = config.setdefault("permissions", {})
    allow_list: list[str] = permissions.setdefault("allow", [])

    if wildcard in allow_list:
        return "skipped"

    allow_list.append(wildcard)
    settings_file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return "updated"


def _bootstrap_cursor(
    project_root: Path,
    overwrite: bool = False,
) -> str:
    """Create or update Cursor pipeline rule file.

    Returns ``'created'``, ``'updated'``, or ``'skipped'``.
    """
    content = load_platform_rules("cursor")
    rules_path = project_root / ".cursor" / "rules" / "tapps-pipeline.md"
    rules_path.parent.mkdir(parents=True, exist_ok=True)

    if rules_path.exists() and not overwrite:
        return "skipped"

    action = "updated" if rules_path.exists() else "created"
    rules_path.write_text(content, encoding="utf-8")
    return action
