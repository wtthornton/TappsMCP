"""Bootstrap TAPPS pipeline files in a consuming project."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from tapps_mcp import __version__

if TYPE_CHECKING:
    from pathlib import Path

    from tapps_mcp.project.models import ProjectProfile, TechStack

from tapps_core.prompts.prompt_loader import (
    load_handoff_template,
    load_runlog_template,
)
from tapps_mcp.prompts.prompt_loader import (
    load_agents_template,
    load_platform_rules,
)

# Allowlist of packages that _run_server_verification may pip-install.
# install_hints come from hardcoded CHECKER_SPECS in tool_detection.py;
# this allowlist is defence-in-depth against unexpected hint values.
_ALLOWED_CHECKER_PACKAGES = {"ruff", "mypy", "bandit", "radon", "vulture", "pip-audit"}


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
    memory_capture: bool = False
    overwrite_tech_stack_md: bool = False
    destructive_guard: bool = False
    minimal: bool = False
    dry_run: bool = False
    verify_only: bool = False
    llm_engagement_level: str = "medium"
    scaffold_experts: bool = False


@dataclass
class _BootstrapState:
    """Mutable accumulator shared between sub-functions."""

    project_root: Path
    dry_run: bool = False
    created: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
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
        if not self.dry_run:
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
        if not self.dry_run:
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
        self.result["warnings"] = self.warnings
        self.result["success"] = len(self.errors) == 0
        return self.result


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
    warm_cache_from_tech_stack: bool = True,
    warm_expert_rag_from_tech_stack: bool = True,
    overwrite_platform_rules: bool = False,
    overwrite_agents_md: bool = False,
    overwrite_tech_stack_md: bool = False,
    agent_teams: bool = False,
    memory_capture: bool = False,
    destructive_guard: bool = False,
    minimal: bool = False,
    dry_run: bool = False,
    verify_only: bool = False,
    llm_engagement_level: str | None = None,
    scaffold_experts: bool = False,
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
        level = llm_engagement_level
        if level is None:
            from tapps_core.config.settings import load_settings

            level = load_settings().llm_engagement_level
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
            overwrite_tech_stack_md=overwrite_tech_stack_md,
            agent_teams=agent_teams,
            memory_capture=memory_capture,
            destructive_guard=destructive_guard,
            minimal=minimal,
            dry_run=dry_run,
            verify_only=verify_only,
            llm_engagement_level=level or "medium",
            scaffold_experts=scaffold_experts,
        )
    state = _BootstrapState(project_root=project_root.resolve(), dry_run=dry_run)

    _verify_server(cfg, state)
    if cfg.verify_only:
        return state.finalize()
    _detect_profile(cfg, state)
    _detect_docker_environment(state)
    _detect_docsmcp(state)
    _create_templates(cfg, state)
    if not cfg.dry_run:
        _setup_platform(cfg, state)
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

    _load_business_experts(cfg, state)

    return state.finalize()


async def _detect_docker() -> dict[str, Any]:
    """Detect Docker Desktop and MCP Toolkit availability."""
    import shutil

    result: dict[str, Any] = {
        "docker_available": False,
        "docker_mcp_available": False,
        "docker_version": None,
        "installed_servers": [],
    }

    # Check docker CLI
    if not shutil.which("docker"):
        return result

    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "info",
            "--format",
            "{{.ServerVersion}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode == 0 and stdout:
            result["docker_available"] = True
            result["docker_version"] = stdout.decode().strip()
    except (asyncio.TimeoutError, OSError):
        return result

    # Check docker mcp subcommand
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "mcp",
            "version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode == 0:
            result["docker_mcp_available"] = True
    except (asyncio.TimeoutError, OSError):
        pass

    return result


def _recommend_companions(
    docker_result: dict[str, Any],
    companions: list[str],
) -> dict[str, Any]:
    """Recommend missing companion MCP servers."""
    installed = set(docker_result.get("installed_servers", []))
    recommended = set(companions)
    missing = recommended - installed
    return {
        "installed": sorted(installed & recommended),
        "missing": sorted(missing),
        "install_commands": [
            f"docker mcp profile server add tapps-standard --server catalog://{s}"
            for s in sorted(missing)
        ],
    }


def _load_business_experts(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Load and optionally scaffold business experts from experts.yaml."""
    experts_yaml = state.project_root / ".tapps-mcp" / "experts.yaml"
    if not experts_yaml.exists():
        # Suggest auto-generation if profile has uncovered domains
        _suggest_auto_generate(state)
        return

    try:
        from tapps_core.experts.business_loader import load_and_register_business_experts

        load_result = load_and_register_business_experts(state.project_root)
    except Exception as exc:
        state.errors.append(f"Business expert loading failed: {exc}")
        state.result["business_experts"] = {"error": str(exc)}
        return

    summary: dict[str, Any] = {
        "loaded": load_result.loaded,
        "expert_ids": load_result.expert_ids,
        "knowledge_status": load_result.knowledge_status,
    }
    if load_result.errors:
        summary["errors"] = load_result.errors
        state.errors.extend(load_result.errors)
    if load_result.warnings:
        summary["warnings"] = load_result.warnings

    # Scaffold missing knowledge directories when requested.
    if cfg.scaffold_experts and not cfg.dry_run and load_result.loaded > 0:
        from tapps_core.experts.business_config import load_business_experts
        from tapps_core.experts.business_knowledge import scaffold_knowledge_directory

        try:
            experts = load_business_experts(state.project_root)
            scaffolded: list[str] = []
            for expert in experts:
                knowledge_status = load_result.knowledge_status.get(
                    expert.primary_domain, "missing"
                )
                if knowledge_status in ("missing", "empty"):
                    scaffold_knowledge_directory(state.project_root, expert)
                    scaffolded.append(expert.primary_domain)
            summary["scaffolded"] = scaffolded
        except Exception as exc:
            state.errors.append(f"Business expert scaffolding failed: {exc}")
            summary["scaffold_error"] = str(exc)

    state.result["business_experts"] = summary


def _suggest_auto_generate(state: _BootstrapState) -> None:
    """Check if auto-generation would find useful expert suggestions."""
    try:
        profile_data = state.result.get("project_profile", {})
        tech_stack = profile_data.get("tech_stack", {})
        libraries = tech_stack.get("libraries", [])
        frameworks = tech_stack.get("frameworks", [])
        domains = tech_stack.get("domains", [])

        if not (libraries or frameworks):
            return

        from tapps_core.experts.auto_generator import analyze_expert_gaps

        suggestions = analyze_expert_gaps(
            libraries=libraries,
            frameworks=frameworks,
            domains=domains,
            project_root=state.project_root,
        )

        if suggestions:
            state.result["auto_expert_suggestions"] = {
                "available": True,
                "suggestion_count": len(suggestions),
                "domains": [s.domain for s in suggestions],
                "hint": (
                    "Run tapps_manage_experts(action='auto_generate') to create "
                    f"business experts for {len(suggestions)} uncovered domain(s)."
                ),
            }
    except Exception:
        pass  # Non-critical; don't block init


def _detect_docker_environment(state: _BootstrapState) -> None:
    """Detect Docker and MCP Toolkit, store results in state."""
    try:
        docker_result = asyncio.run(_detect_docker())
    except RuntimeError:
        # Already in an event loop — skip Docker detection.
        docker_result = {
            "docker_available": False,
            "docker_mcp_available": False,
            "docker_version": None,
            "installed_servers": [],
        }
    except Exception:
        docker_result = {
            "docker_available": False,
            "docker_mcp_available": False,
            "docker_version": None,
            "installed_servers": [],
        }

    state.result["docker"] = docker_result

    # Recommend companions when Docker MCP is available.
    if docker_result.get("docker_mcp_available"):
        from tapps_core.config.settings import load_settings

        settings = load_settings()
        companions = _recommend_companions(docker_result, settings.docker.companions)
        state.result["docker_companions"] = companions


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
        state.result["docsmcp_detected"] = True
        return True
    except ImportError:
        pass

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

        action = state.safe_write_or_overwrite(
            "docs/TAPPS_WORKFLOW.md", render_workflow_md()
        )
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


def _setup_platform(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Bootstrap platform-specific rule files, hooks, agents, and skills."""
    if not cfg.platform:
        return

    platform_action: str | None = None
    engagement = cfg.llm_engagement_level
    if cfg.platform == "claude":
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
        if settings_action == "created":
            state.created.append(".claude/settings.json")
        if not cfg.minimal:
            from tapps_mcp.pipeline.platform_generators import (
                generate_agent_teams_hooks,
                generate_ci_workflow,
                generate_claude_hooks,
                generate_claude_python_quality_rule,
                generate_copilot_instructions,
                generate_skills,
                generate_subagent_definitions,
            )

            state.result["hooks"] = generate_claude_hooks(
                state.project_root,
                engagement_level=engagement,
                destructive_guard=cfg.destructive_guard,
            )
            state.result["agents"] = generate_subagent_definitions(
                state.project_root, "claude"
            )
            state.result["skills"] = generate_skills(
                state.project_root, "claude", engagement_level=engagement
            )
            state.result["python_quality_rule"] = generate_claude_python_quality_rule(
                state.project_root, engagement_level=engagement
            )
            if cfg.agent_teams:
                state.result["agent_teams"] = generate_agent_teams_hooks(
                    state.project_root
                )
            if cfg.memory_capture:
                from tapps_mcp.pipeline.platform_hooks import generate_memory_capture_hook

                state.result["memory_capture"] = generate_memory_capture_hook(
                    state.project_root
                )
            state.result["ci_workflow"] = generate_ci_workflow(state.project_root)
            state.result["copilot_instructions"] = generate_copilot_instructions(
                state.project_root,
            )
    elif cfg.platform == "cursor":
        platform_action = _bootstrap_cursor(
            state.project_root, cfg.overwrite_platform_rules, engagement_level=engagement
        )
        if platform_action in {"created", "updated"}:
            state.created.append(".cursor/rules/tapps-pipeline.md")
        elif platform_action == "skipped":
            state.skipped.append(".cursor/rules/tapps-pipeline.md")
        if not cfg.minimal:
            from tapps_mcp.pipeline.platform_generators import (
                generate_bugbot_rules,
                generate_ci_workflow,
                generate_copilot_instructions,
                generate_cursor_hooks,
                generate_cursor_rules,
                generate_skills,
                generate_subagent_definitions,
            )

            state.result["hooks"] = generate_cursor_hooks(
                state.project_root, engagement_level=engagement
            )
            state.result["agents"] = generate_subagent_definitions(
                state.project_root, "cursor"
            )
            state.result["skills"] = generate_skills(
                state.project_root, "cursor", engagement_level=engagement
            )
            state.result["cursor_rules"] = generate_cursor_rules(state.project_root)
            state.result["bugbot_rules"] = generate_bugbot_rules(state.project_root)
            state.result["ci_workflow"] = generate_ci_workflow(state.project_root)
            state.result["copilot_instructions"] = generate_copilot_instructions(
                state.project_root,
            )
    else:
        state.errors.append(f"Unknown platform: {cfg.platform!r}. Use 'claude' or 'cursor'.")

    state.result["platform_rules"] = {
        "platform": cfg.platform,
        "action": platform_action or "skipped",
    }

    if not cfg.minimal:
        _setup_github_templates(state)
        _setup_github_ci(state)
        _setup_github_copilot(state)
        _setup_github_governance(state)


def _setup_github_templates(state: _BootstrapState) -> None:
    """Generate GitHub Issue forms, PR template, and Dependabot config."""
    try:
        from tapps_mcp.pipeline.github_templates import generate_all_github_templates

        result = generate_all_github_templates(state.project_root)
        state.result["github_templates"] = result
    except Exception as exc:
        state.errors.append(f"GitHub templates: {exc}")
        state.result["github_templates"] = {"error": str(exc)}


def _setup_github_ci(state: _BootstrapState) -> None:
    """Generate enhanced CI workflows."""
    try:
        from tapps_mcp.pipeline.github_ci import generate_all_ci_workflows

        result = generate_all_ci_workflows(state.project_root)
        state.result["ci_workflows"] = result
    except Exception as exc:
        state.errors.append(f"CI workflows: {exc}")
        state.result["ci_workflows"] = {"error": str(exc)}


def _setup_github_copilot(state: _BootstrapState) -> None:
    """Generate Copilot agent profiles and path-scoped instructions."""
    try:
        from tapps_mcp.pipeline.github_copilot import generate_all_copilot_config

        result = generate_all_copilot_config(state.project_root)
        state.result["github_copilot"] = result
    except Exception as exc:
        state.errors.append(f"Copilot config: {exc}")
        state.result["github_copilot"] = {"error": str(exc)}


def _setup_github_governance(state: _BootstrapState) -> None:
    """Generate governance files (SECURITY.md, CODEOWNERS, rulesets, guide)."""
    try:
        from tapps_mcp.pipeline.github_governance import generate_all_governance

        result = generate_all_governance(state.project_root)
        state.result["governance"] = result
    except Exception as exc:
        state.errors.append(f"Governance: {exc}")
        state.result["governance"] = {"error": str(exc)}


def _warm_caches(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Warm Context7 cache and expert RAG indices."""
    if cfg.warm_cache_from_tech_stack and state.profile is not None:
        cache_result = _run_cache_warming(
            state.project_root,
            state.profile.tech_stack.context7_priority,
        )
        state.result["cache_warming"] = cache_result
        if cache_result.get("skipped") == "no_api_key":
            warning = (
                "Cache warming skipped: CONTEXT7_API_KEY not set. "
                "Add it to your MCP server env config for documentation lookup."
            )
            cache_result["warning"] = warning
            state.warnings.append(warning)
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
        rag_result = _run_expert_rag_warming(
            state.project_root,
            state.profile.tech_stack,
        )
        state.result["expert_rag_warming"] = rag_result
        failed = rag_result.get("failed_domains") or []
        if failed:
            state.errors.append(f"Expert RAG failed for domains: {', '.join(failed)}")
    else:
        state.result["expert_rag_warming"] = {
            "warmed": 0,
            "attempted": 0,
            "skipped": "disabled" if not cfg.warm_expert_rag_from_tech_stack else "profile_failed",
            "domains": [],
        }


def _extract_pip_package(hint: str) -> str | None:
    """Extract package name from a 'pip install X' hint, or None if not allowed."""
    if not hint or not hint.startswith("pip install "):
        return None
    pkg = hint.replace("pip install ", "").strip()
    if pkg not in _ALLOWED_CHECKER_PACKAGES:
        return None
    return pkg


def _install_missing_checkers(
    install_hints: list[str],
    project_root: Path,
) -> None:
    """Attempt to pip-install allowed missing checker packages."""
    import contextlib
    import subprocess
    import sys

    for hint in install_hints:
        pkg = _extract_pip_package(hint)
        if pkg is not None:
            with contextlib.suppress(subprocess.TimeoutExpired, FileNotFoundError, OSError):
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", pkg],
                    capture_output=True,
                    timeout=60,
                    check=False,
                    cwd=project_root,
                )


def _build_verification_result(installed: list[Any]) -> dict[str, Any]:
    """Build verification result dict from tool detection output."""
    missing = [t for t in installed if not t.available]
    return {
        "ok": len(missing) == 0,
        "missing_checkers": [t.name for t in missing],
        "installed": [t.name for t in installed if t.available],
        "install_hints": [t.install_hint for t in missing if t.install_hint],
        "checker_install_attempted": False,
    }


def _run_server_verification(
    project_root: Path,
    *,
    install_missing: bool = False,
) -> dict[str, Any]:
    """Verify server info and optionally install missing checkers."""
    from tapps_mcp.tools.tool_detection import detect_installed_tools

    installed = detect_installed_tools()
    result = _build_verification_result(installed)

    if install_missing and result["missing_checkers"]:
        result["checker_install_attempted"] = True
        _install_missing_checkers(result["install_hints"], project_root)

        # Reset cache so re-detection actually probes for newly installed tools
        from tapps_mcp.tools.tool_detection import _reset_tools_cache

        _reset_tools_cache()
        installed_after = detect_installed_tools()
        result.update(_build_verification_result(installed_after))
        result["checker_install_attempted"] = True

    return result


def _render_list_section(
    heading: str, items: list[str] | None, fallback: str = "(none detected)"
) -> list[str]:
    """Render a markdown section with a heading and bullet list."""
    lines = ["", f"## {heading}"]
    for item in items or [fallback]:
        lines.append(f"- {item}")
    return lines


def _render_infrastructure_section(profile: ProjectProfile) -> list[str]:
    """Render the Infrastructure section of TECH_STACK.md."""
    ci_str = "Yes (" + ", ".join(profile.ci_systems) + ")" if profile.has_ci else "No"
    tests_str = "Yes (" + ", ".join(profile.test_frameworks) + ")" if profile.has_tests else "No"
    docker_str = "Yes" if profile.has_docker else "No"
    pkg_str = ", ".join(profile.package_managers) or "N/A"
    return [
        "",
        "## Infrastructure",
        f"- **CI:** {ci_str}",
        f"- **Docker:** {docker_str}",
        f"- **Tests:** {tests_str}",
        f"- **Package managers:** {pkg_str}",
    ]


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
    ]
    lines.extend(_render_list_section("Languages", ts.languages))
    lines.extend(_render_list_section("Frameworks", ts.frameworks))
    lines.extend(_render_list_section("Libraries", ts.libraries))
    lines.extend(_render_list_section("Domains", ts.domains))
    # Context7 priority renders no fallback text when empty
    lines.extend(["", "## Context7 Priority (for doc lookups)"])
    for p in ts.context7_priority or []:
        lines.append(f"- {p}")
    lines.extend(_render_infrastructure_section(profile))
    lines.extend(
        _render_list_section("Recommendations", profile.quality_recommendations, fallback="(none)")
    )
    lines.append("")
    return "\n".join(lines)


def _run_cache_warming(
    project_root: Path,
    libraries: list[str],
) -> dict[str, Any]:
    """Run cache warming for libraries from tech stack.

    Normally called from a worker thread (via ``asyncio.to_thread`` in
    ``tapps_init``), so ``asyncio.run()`` is safe.  The ``RuntimeError``
    guard handles the edge case where this is called from an already-
    running event loop.
    """
    import asyncio

    import structlog

    from tapps_core.config.settings import load_settings
    from tapps_core.knowledge.cache import KBCache
    from tapps_core.knowledge.warming import warm_cache

    logger = structlog.get_logger(__name__)

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
    except RuntimeError as exc:
        # asyncio.run() raises RuntimeError when called from an already-
        # running event loop.  This should not happen when the caller uses
        # asyncio.to_thread(), but guard defensively and log a warning.
        warmed = 0
        error = f"RuntimeError: {exc}"
        logger.warning(
            "cache_warming_event_loop_conflict",
            error=str(exc),
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
    from tapps_core.experts.rag_warming import warm_expert_rag_indices

    index_base = project_root / ".tapps-mcp" / "rag_index"
    return warm_expert_rag_indices(
        tech_stack,
        max_domains=10,
        index_base_dir=index_base,
    )


def _bootstrap_claude(
    project_root: Path,
    overwrite: bool = False,
    engagement_level: str = "medium",
) -> str:
    """Create or update CLAUDE.md with TAPPS pipeline reference.

    Returns ``'created'``, ``'updated'``, or ``'skipped'``.
    """
    claude_md = project_root / "CLAUDE.md"
    content = load_platform_rules("claude", engagement_level=engagement_level)

    if claude_md.exists():
        existing = claude_md.read_text(encoding="utf-8")
        if "TAPPS" in existing and not overwrite:
            # Already has TAPPS reference
            return "skipped"
        if overwrite and "# TAPPS Quality Pipeline" in existing:
            # Replace existing TAPPS section with updated content
            new_content = _replace_tapps_section(existing, content)
        elif "TAPPS" not in existing:
            # No TAPPS content yet - append
            new_content = existing.rstrip() + "\n\n" + content
        else:
            # overwrite=True but no heading marker found - replace whole TAPPS block
            new_content = _replace_tapps_section(existing, content)
        claude_md.write_text(new_content, encoding="utf-8")
        return "updated"

    claude_md.write_text(content, encoding="utf-8")
    return "created"


def _split_by_h1_headings(content: str) -> list[tuple[str, str]]:
    """Split Markdown content by ``# `` (H1) headings.

    Returns a list of ``(heading_line, body)`` tuples.  Content before the
    first H1 heading is captured with an empty ``heading_line``.  Only
    top-level ``# `` headings act as boundaries -- ``##``, ``###`` etc.
    are treated as regular body content.

    The *heading_line* includes the trailing newline (if present) so that
    reassembly via simple concatenation preserves the original whitespace.
    """
    import re

    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_lines: list[str] = []

    for line in content.splitlines(keepends=True):
        if re.match(r"^# ", line):
            # Flush previous section
            if current_lines or current_heading:
                sections.append((current_heading, "".join(current_lines)))
            current_heading = line
            current_lines = []
        else:
            current_lines.append(line)

    # Flush last section
    if current_lines or current_heading:
        sections.append((current_heading, "".join(current_lines)))

    return sections


def _replace_tapps_section(existing: str, new_tapps_content: str) -> str:
    """Replace the TAPPS section in an existing CLAUDE.md.

    Finds the ``# TAPPS Quality Pipeline`` heading and replaces everything
    from that heading to the next top-level heading (or end of file) with
    *new_tapps_content*.

    Uses :func:`_split_by_h1_headings` for robust heading-based splitting
    instead of fragile regex matching.
    """
    sections = _split_by_h1_headings(existing)

    tapps_idx: int | None = None
    for idx, (heading, _body) in enumerate(sections):
        if heading.startswith("# TAPPS Quality Pipeline"):
            tapps_idx = idx
            break

    if tapps_idx is None:
        # No TAPPS heading found -- append fresh content
        return existing.rstrip() + "\n\n" + new_tapps_content

    # Rebuild: sections before TAPPS + new content + sections after TAPPS
    before_parts: list[str] = []
    for heading, body in sections[:tapps_idx]:
        before_parts.append(heading + body)
    before = "".join(before_parts).rstrip()

    after_parts: list[str] = []
    for heading, body in sections[tapps_idx + 1 :]:
        after_parts.append(heading + body)
    after = "".join(after_parts).lstrip("\n")

    parts = [before, new_tapps_content] if before else [new_tapps_content]
    if after:
        parts.append(after)
    return "\n\n".join(parts)


# Both entries needed for Claude Code permissions: bare match is the reliable
# fallback (issue #3107), wildcard is the official syntax from v2.0.70+.
_CLAUDE_PERMISSION_ENTRIES = ["mcp__tapps-mcp", "mcp__tapps-mcp__*"]

# DocsMCP permission entries — added when DocsMCP is detected.
_DOCSMCP_PERMISSION_ENTRIES = ["mcp__docs-mcp", "mcp__docs-mcp__*"]

# TappsPlatform (combined server) permission entries — added when DocsMCP is detected.
_PLATFORM_PERMISSION_ENTRIES = ["mcp__tapps-platform", "mcp__tapps-platform__*"]

# Extra permissions granted at high engagement level so the LLM can
# auto-run quality checkers without user confirmation.
_CLAUDE_HIGH_ENGAGEMENT_PERMISSIONS = [
    "Bash(uv run ruff *)",
    "Bash(uv run mypy *)",
]


def generate_permission_settings(
    project_root: Path,
    engagement_level: str = "medium",
    existing_settings: dict[str, Any] | None = None,
    *,
    docsmcp_detected: bool = False,
) -> dict[str, Any]:
    """Generate ``.claude/settings.json`` content with permission rules.

    Builds the base MCP permission entries and, at ``high`` engagement,
    appends extra ``Bash(...)`` entries so the LLM can auto-run checkers.

    Merges into *existing_settings* when provided (preserving all user
    keys and deduplicating the ``permissions.allow`` list).

    Args:
        project_root: Target project root (unused today but reserved
            for future per-project customisation).
        engagement_level: ``"high"``, ``"medium"`` (default), or ``"low"``.
        existing_settings: Parsed contents of an existing ``settings.json``.
            ``None`` starts from an empty dict.
        docsmcp_detected: When True, include DocsMCP permission entries.

    Returns:
        The merged settings dict ready to be serialised to JSON.
    """
    import copy

    config: dict[str, Any] = copy.deepcopy(existing_settings) if existing_settings else {}
    permissions: dict[str, Any] = config.setdefault("permissions", {})
    allow_list: list[str] = permissions.setdefault("allow", [])

    desired: list[str] = list(_CLAUDE_PERMISSION_ENTRIES)
    if docsmcp_detected:
        desired.extend(_DOCSMCP_PERMISSION_ENTRIES)
        desired.extend(_PLATFORM_PERMISSION_ENTRIES)
    if engagement_level == "high":
        desired.extend(_CLAUDE_HIGH_ENGAGEMENT_PERMISSIONS)

    for entry in desired:
        if entry not in allow_list:
            allow_list.append(entry)

    return config


def _bootstrap_claude_settings(
    project_root: Path,
    engagement_level: str = "medium",
    *,
    docsmcp_detected: bool = False,
) -> str:
    """Create or update ``.claude/settings.json`` with permission entries.

    Adds **both** ``"mcp__tapps-mcp"`` (bare server match - confirmed
    working in Claude Code issue #3107) and ``"mcp__tapps-mcp__*"``
    (wildcard match - added in Claude Code 2.0.70) to ``permissions.allow``.
    Using both syntaxes works around a known Claude Code bug where the
    wildcard variant is sometimes not honoured (issues #13077, #14730,
    #27139).

    At ``high`` engagement, also adds ``Bash(uv run ruff *)`` and
    ``Bash(uv run mypy *)`` so the LLM can auto-run quality checkers.

    When *docsmcp_detected* is True, also adds DocsMCP permission entries.

    Returns ``'created'``, ``'updated'``, or ``'skipped'``.
    """
    import json
    from pathlib import Path as _Path

    settings_dir = _Path(project_root) / ".claude"
    settings_file = settings_dir / "settings.json"

    if not settings_file.exists():
        settings_dir.mkdir(parents=True, exist_ok=True)
        config = generate_permission_settings(
            project_root,
            engagement_level=engagement_level,
            docsmcp_detected=docsmcp_detected,
        )
        settings_file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        return "created"

    raw = settings_file.read_text(encoding="utf-8")
    try:
        existing: dict[str, Any] = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        # Malformed JSON — leave the file untouched rather than corrupting it.
        return "skipped"

    merged = generate_permission_settings(
        project_root,
        engagement_level=engagement_level,
        existing_settings=existing,
        docsmcp_detected=docsmcp_detected,
    )

    if merged == existing:
        return "skipped"

    settings_file.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return "updated"


def _bootstrap_cursor(
    project_root: Path,
    overwrite: bool = False,
    engagement_level: str = "medium",
) -> str:
    """Create or update Cursor pipeline rule file.

    Returns ``'created'``, ``'updated'``, or ``'skipped'``.
    """
    content = load_platform_rules("cursor", engagement_level=engagement_level)
    rules_path = project_root / ".cursor" / "rules" / "tapps-pipeline.md"
    rules_path.parent.mkdir(parents=True, exist_ok=True)

    if rules_path.exists() and not overwrite:
        return "skipped"

    action = "updated" if rules_path.exists() else "created"
    rules_path.write_text(content, encoding="utf-8")
    return action
