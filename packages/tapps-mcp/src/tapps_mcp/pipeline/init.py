"""Bootstrap TAPPS pipeline files in a consuming project."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from tapps_mcp import __version__

if TYPE_CHECKING:
    from pathlib import Path

    from tapps_mcp.project.models import ProjectProfile, TechStack

from tapps_core.common.file_operations import (
    AgentInstructions,
    FileManifest,
    FileOperation,
    WriteMode,
    detect_write_mode,
)
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
_ALLOWED_CHECKER_PACKAGES = {
    "ruff",
    "mypy",
    "bandit",
    "radon",
    "vulture",
    "pip-audit",
    "pylint",
    "perflint",
}


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
    warm_cache_from_tech_stack: bool = False
    warm_expert_rag_from_tech_stack: bool = False
    overwrite_platform_rules: bool = False
    overwrite_agents_md: bool = False
    agent_teams: bool = False
    memory_capture: bool = False
    memory_auto_recall: bool = False
    memory_auto_capture: bool = False
    overwrite_tech_stack_md: bool = False
    destructive_guard: bool = False
    linear_enforce_gate: bool = False
    minimal: bool = False
    dry_run: bool = False
    verify_only: bool = False
    llm_engagement_level: str = "medium"
    scaffold_experts: bool = False
    docs_automation: bool = True
    include_karpathy: bool = True

    @classmethod
    def from_params(
        cls,
        *,
        llm_engagement_level: str | None = None,
        **kwargs: Any,
    ) -> BootstrapConfig:
        """Construct with optional ``llm_engagement_level`` fallback.

        When *llm_engagement_level* is ``None``, reads the value from
        :func:`~tapps_core.config.settings.load_settings`.  All other
        keyword arguments are forwarded to the dataclass constructor.
        """
        if llm_engagement_level is None:
            from tapps_core.config.settings import load_settings

            llm_engagement_level = load_settings().llm_engagement_level
        return cls(llm_engagement_level=llm_engagement_level or "medium", **kwargs)


@dataclass
class _BootstrapState:
    """Mutable accumulator shared between sub-functions."""

    project_root: Path
    dry_run: bool = False
    write_mode: WriteMode = WriteMode.DIRECT_WRITE
    created: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)
    profile: ProjectProfile | None = None
    file_ops: list[FileOperation] = field(default_factory=list)

    @property
    def content_return(self) -> bool:
        """Whether this run is in content-return mode (Epic 87)."""
        return self.write_mode == WriteMode.CONTENT_RETURN

    def safe_write(self, rel_path: str, content: str) -> None:
        """Write *content* to *rel_path* under project_root, safely."""
        target = (self.project_root / rel_path).resolve()
        try:
            target.relative_to(self.project_root)
        except ValueError:
            self.errors.append(f"{rel_path}: path escapes project root")
            return
        if self.content_return:
            self.file_ops.append(
                FileOperation(
                    path=rel_path,
                    content=content,
                    mode="create",
                    description=f"Template file: {rel_path}",
                )
            )
            self.created.append(rel_path)
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
        if self.content_return:
            mode = "overwrite" if target.exists() else "create"
            self.file_ops.append(
                FileOperation(
                    path=rel_path,
                    content=content,
                    mode=mode,
                    description=f"Template file: {rel_path}",
                )
            )
            if mode == "create":
                self.created.append(rel_path)
            return "created" if mode == "create" else "updated"
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

    def build_manifest(self) -> FileManifest:
        """Build a :class:`FileManifest` from accumulated file operations.

        Called when ``content_return`` is ``True`` to package all generated
        files into a structured response the AI client can apply.
        """
        return FileManifest(
            summary=(f"TappsMCP init v{__version__}: {len(self.file_ops)} file(s) to write"),
            source_version=__version__,
            files=self.file_ops,
            agent_instructions=AgentInstructions(
                persona=(
                    "You are a project scaffolding assistant setting up TappsMCP "
                    "for the first time.  Write each file exactly as provided — "
                    "do not modify content, add comments, or reformat."
                ),
                tool_preference=(
                    "Use the Write tool for all files.  These are new files in a "
                    "fresh project setup.  Create parent directories as needed."
                ),
                verification_steps=[
                    "After writing all files, run 'git status' to show the user what changed.",
                    "Verify AGENTS.md exists at the project root.",
                    "If .tapps-mcp.yaml was written, confirm it contains the expected preset.",
                    "On Unix/macOS: remind the user to run 'chmod +x' on any .sh files.",
                ],
                warnings=[
                    "CLAUDE.md and AGENTS.md may need project-specific "
                    "customization after writing.",
                    "Hook scripts (.sh) require execute permission on Unix.",
                    "Review generated CI workflows before committing.",
                ],
            ),
        )


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
    memory_auto_capture: bool = False,
    memory_auto_recall: bool = False,
    destructive_guard: bool = False,
    linear_enforce_gate: bool = False,
    minimal: bool = False,
    dry_run: bool = False,
    verify_only: bool = False,
    llm_engagement_level: str | None = None,
    scaffold_experts: bool = False,
    include_karpathy: bool = True,
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
        cfg = BootstrapConfig.from_params(
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
            memory_auto_recall=memory_auto_recall,
            memory_auto_capture=memory_auto_capture,
            destructive_guard=destructive_guard,
            linear_enforce_gate=linear_enforce_gate,
            minimal=minimal,
            dry_run=dry_run,
            verify_only=verify_only,
            llm_engagement_level=llm_engagement_level,
            scaffold_experts=scaffold_experts,
            include_karpathy=include_karpathy,
        )
    # Determine write mode: direct (local) or content-return (Docker/read-only)
    resolved_root = project_root.resolve()
    write_mode = detect_write_mode(resolved_root) if not cfg.dry_run else WriteMode.DIRECT_WRITE

    state = _BootstrapState(
        project_root=resolved_root,
        dry_run=cfg.dry_run,
        write_mode=write_mode,
    )

    # Content-return mode: generate files without writing (Epic 87)
    if state.content_return and not cfg.verify_only:
        import structlog

        structlog.get_logger(__name__).info(
            "content_return_mode",
            project_root=str(project_root),
            reason="read-only filesystem or TAPPS_WRITE_MODE=content",
        )

    _verify_server(cfg, state)
    if cfg.verify_only:
        return state.finalize()
    _detect_profile(cfg, state)
    _detect_docsmcp(state)
    _create_templates(cfg, state)
    if state.content_return:
        # Content-return mode (Epic 87): generate platform files as
        # FileOperations instead of writing them directly.  Platform
        # generators write to disk, so we generate the key files from
        # template loaders and skip side-effects (cache warming, etc.).
        _generate_platform_file_ops(cfg, state)
        state.result["cache_warming"] = {
            "warmed": 0,
            "attempted": 0,
            "skipped": "content_return",
            "libraries": [],
        }
        state.result["expert_rag_warming"] = {
            "warmed": 0,
            "attempted": 0,
            "skipped": "content_return",
            "domains": [],
        }
    elif not cfg.dry_run:
        _setup_platform(cfg, state)
        _install_karpathy_blocks(cfg, state)
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

    if state.content_return:
        manifest = state.build_manifest()
        result = state.finalize()
        result["file_manifest"] = manifest.to_full_response_data()
        result["content_return"] = True
        return result

    return state.finalize()


def _load_business_experts(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Expert system removed (EPIC-94). No-op."""


def _suggest_auto_generate(state: _BootstrapState) -> None:
    """Expert system removed (EPIC-94). No-op."""


def _memory_hooks_defaults_for_engagement(engagement_level: str) -> dict[str, Any]:
    """Return memory_hooks section defaults by engagement (Epic 65.6).

    high: both auto_recall and auto_capture enabled
    medium: auto_recall only
    low: both disabled
    """
    if engagement_level == "high":
        return {
            "auto_recall": {"enabled": True, "max_results": 5, "min_score": 0.3},
            "auto_capture": {"enabled": True, "max_facts": 5},
        }
    if engagement_level == "medium":
        return {
            "auto_recall": {"enabled": True, "max_results": 5, "min_score": 0.3},
            "auto_capture": {"enabled": False, "max_facts": 5},
        }
    return {
        "auto_recall": {"enabled": False, "max_results": 5, "min_score": 0.3},
        "auto_capture": {"enabled": False, "max_facts": 5},
    }


def _ensure_memory_hooks_config(
    project_root: Path,
    engagement_level: str,
    *,
    dry_run: bool = False,
) -> str:
    """Merge memory_hooks section into .tapps-mcp.yaml with engagement defaults (Epic 65.6).

    Adds or updates memory_hooks only; other keys preserved.
    Returns 'created', 'updated', or 'skipped'.
    """
    import yaml

    yaml_path = project_root / ".tapps-mcp.yaml"
    defaults = _memory_hooks_defaults_for_engagement(engagement_level)

    if dry_run:
        return "skipped"

    existing: dict[str, Any] = {}
    if yaml_path.exists():
        try:
            raw = yaml_path.read_text(encoding="utf-8-sig")
            existing = yaml.safe_load(raw) or {}
        except Exception:
            return "skipped"

    if "memory_hooks" not in existing:
        existing["memory_hooks"] = defaults
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        yaml_path.write_text(yaml.dump(existing, default_flow_style=False), encoding="utf-8")
        return "created"

    mh = existing["memory_hooks"]
    if not isinstance(mh, dict):
        mh = {}
    updated = False
    for key in ("auto_recall", "auto_capture"):
        sub_defaults = defaults.get(key, {})
        if not isinstance(sub_defaults, dict):
            continue
        sub = mh.get(key)
        if not isinstance(sub, dict):
            mh[key] = sub_defaults.copy()
            updated = True
        else:
            for k, v in sub_defaults.items():
                if k not in sub:
                    sub[k] = v
                    updated = True
    existing["memory_hooks"] = mh
    if updated:
        yaml_path.write_text(yaml.dump(existing, default_flow_style=False), encoding="utf-8")
        return "updated"
    return "skipped"


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

        action = state.safe_write_or_overwrite("docs/TAPPS_WORKFLOW.md", render_workflow_md())
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


def _install_karpathy_blocks(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Install or refresh the Karpathy guidelines block in AGENTS.md and CLAUDE.md.

    Both files are only ever appended-to (between BEGIN/END markers); content
    outside the markers is preserved. Skips files that don't exist — this
    function runs after ``_create_templates`` (which may create AGENTS.md)
    and ``_setup_platform`` (which may create CLAUDE.md), so whichever
    file(s) the consumer's project has will be covered.
    """
    if not cfg.include_karpathy:
        state.result["karpathy_guidelines"] = {"action": "skipped", "reason": "disabled"}
        return
    if state.content_return:
        state.result["karpathy_guidelines"] = {"action": "skipped", "reason": "content_return"}
        return

    from tapps_mcp.pipeline import karpathy_block

    per_file: dict[str, str] = {}
    for rel in ("AGENTS.md", "CLAUDE.md"):
        target = state.project_root / rel
        if not target.exists():
            per_file[rel] = "skipped_file_missing"
            continue
        try:
            per_file[rel] = karpathy_block.install_or_refresh(target, dry_run=cfg.dry_run)
        except Exception as exc:
            per_file[rel] = "error"
            state.errors.append(f"Karpathy guidelines install failed for {rel}: {exc}")

    state.result["karpathy_guidelines"] = {
        "source_sha": karpathy_block.KARPATHY_GUIDELINES_SOURCE_SHA,
        "files": per_file,
    }


def _generate_platform_file_ops(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Generate platform files as FileOperations for content-return mode (Epic 87).

    Instead of writing files directly (which requires filesystem access),
    generate the key platform files from template loaders and add them as
    :class:`FileOperation` entries in ``state.file_ops``.

    This covers the essential files; hooks, skills, sub-agents, CI, and
    GitHub templates are generated from platform_generators which write
    directly.  A future story will refactor those generators to also support
    content-return mode.
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
                path=".cursor/rules/tapps-pipeline.md",
                content=content,
                mode="create",
                description="Cursor platform rules with TappsMCP pipeline reference.",
                priority=2,
            )
        )
        state.created.append(".cursor/rules/tapps-pipeline.md")

    state.result["platform_rules"] = {
        "platform": platform,
        "action": "content_return",
    }

    # Note: hooks, skills, sub-agents, CI workflows, and GitHub templates
    # are generated by platform_generators which write files directly.
    # These will be added to content-return mode in a future story.
    state.result["platform_generators_skipped"] = {
        "reason": "content_return",
        "skipped_components": [
            "hooks",
            "skills",
            "sub-agents",
            "ci_workflows",
            "github_templates",
            "copilot_config",
            "governance",
        ],
        "hint": (
            "Run 'tapps_upgrade' after writing these files to generate "
            "hooks, skills, and CI configuration."
        ),
    }


def _setup_platform(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Bootstrap platform-specific rule files, hooks, agents, and skills."""
    if not cfg.platform:
        return

    platform_action: str | None = None
    engagement = cfg.llm_engagement_level

    # Epic 65.6: Ensure memory_hooks in .tapps-mcp.yaml with engagement defaults
    mh_action = _ensure_memory_hooks_config(state.project_root, engagement, dry_run=cfg.dry_run)
    state.result["memory_hooks_config"] = {"action": mh_action}
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
        if settings_action in ("created", "updated"):
            state.warnings.append(
                "MCP servers are only connected at session start. "
                "Restart your Claude Code session for tapps-mcp tools to become available."
            )
        if settings_action == "created":
            state.created.append(".claude/settings.json")
        if not cfg.minimal:
            from tapps_mcp.pipeline.platform_generators import (
                generate_agent_teams_hooks,
                generate_claude_agent_scope_rule,
                generate_claude_autonomy_rule,
                generate_claude_config_files_rule,
                generate_claude_hooks,
                generate_claude_linear_standards_rule,
                generate_claude_python_quality_rule,
                generate_claude_security_rule,
                generate_claude_test_quality_rule,
                generate_copilot_instructions,
                generate_skills,
                generate_subagent_definitions,
            )

            state.result["hooks"] = generate_claude_hooks(
                state.project_root,
                engagement_level=engagement,
                destructive_guard=cfg.destructive_guard,
                linear_enforce_gate=cfg.linear_enforce_gate,
            )
            state.result["agents"] = generate_subagent_definitions(state.project_root, "claude")
            state.result["skills"] = generate_skills(
                state.project_root, "claude", engagement_level=engagement
            )
            state.result["python_quality_rule"] = generate_claude_python_quality_rule(
                state.project_root, engagement_level=engagement
            )
            state.result["agent_scope_rule"] = generate_claude_agent_scope_rule(
                state.project_root,
            )
            state.result["autonomy_rule"] = generate_claude_autonomy_rule(
                state.project_root,
            )
            state.result["linear_standards_rule"] = generate_claude_linear_standards_rule(
                state.project_root,
            )
            # TAP-978: scoped quality rules. Init runs only when user
            # signals intent, so generate unconditionally — matches the
            # python_quality_rule pattern. Upgrade.py applies language
            # gating.
            state.result["security_rule"] = generate_claude_security_rule(
                state.project_root,
            )
            state.result["test_quality_rule"] = generate_claude_test_quality_rule(
                state.project_root,
            )
            state.result["config_files_rule"] = generate_claude_config_files_rule(
                state.project_root,
            )
            # Epic 86: Doc automation when DocsMCP is detected
            if cfg.docs_automation and state.result.get("docsmcp_detected", False):
                from tapps_mcp.pipeline.platform_docs_automation import (
                    generate_docs_automation,
                )

                state.result["docs_automation"] = generate_docs_automation(
                    state.project_root, "claude"
                )
            if cfg.agent_teams:
                state.result["agent_teams"] = generate_agent_teams_hooks(state.project_root)
            if cfg.memory_capture:
                from tapps_mcp.pipeline.platform_hooks import generate_memory_capture_hook

                state.result["memory_capture"] = generate_memory_capture_hook(state.project_root)
            # Epic 65.4/65.6: Wire auto-recall and auto-capture hooks from config or explicit param
            try:
                from tapps_core.config.settings import load_settings

                settings = load_settings(project_root=state.project_root)
                mh = settings.memory_hooks
                if cfg.memory_auto_recall or mh.auto_recall.enabled:
                    from tapps_mcp.pipeline.platform_hooks import (
                        generate_memory_auto_recall_hook,
                    )

                    state.result["memory_auto_recall"] = generate_memory_auto_recall_hook(
                        state.project_root,
                        max_results=mh.auto_recall.max_results,
                        min_score=mh.auto_recall.min_score,
                        min_prompt_length=mh.auto_recall.min_prompt_length,
                    )
                if mh.auto_capture.enabled:
                    from tapps_mcp.pipeline.platform_hooks import (
                        generate_memory_auto_capture_hook,
                    )

                    state.result["memory_auto_capture"] = generate_memory_auto_capture_hook(
                        state.project_root
                    )
            except (AttributeError, ImportError, OSError) as exc:
                import structlog

                structlog.get_logger(__name__).warning(
                    "memory_hooks_probe_failed", error=str(exc)
                )
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
                generate_copilot_instructions,
                generate_cursor_hooks,
                generate_cursor_rules,
                generate_skills,
                generate_subagent_definitions,
            )

            state.result["hooks"] = generate_cursor_hooks(
                state.project_root, engagement_level=engagement
            )
            state.result["agents"] = generate_subagent_definitions(state.project_root, "cursor")
            state.result["skills"] = generate_skills(
                state.project_root, "cursor", engagement_level=engagement
            )
            # Epic 86: Doc automation when DocsMCP is detected
            if cfg.docs_automation and state.result.get("docsmcp_detected", False):
                from tapps_mcp.pipeline.platform_docs_automation import (
                    generate_docs_automation,
                )

                state.result["docs_automation"] = generate_docs_automation(
                    state.project_root, "cursor"
                )
            state.result["cursor_rules"] = generate_cursor_rules(state.project_root)
            state.result["bugbot_rules"] = generate_bugbot_rules(state.project_root)
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


_TECH_STACK_LOW_CONFIDENCE_THRESHOLD = 0.6


def _render_tech_stack_md(profile: ProjectProfile) -> str:
    """Render TECH_STACK.md content from project profile."""
    ts = profile.tech_stack
    low_conf = profile.project_type_confidence < _TECH_STACK_LOW_CONFIDENCE_THRESHOLD
    lines = [
        "# Tech Stack",
        "",
    ]
    if low_conf:
        lines.extend(
            [
                "> **Low confidence:** Auto-detected project type may be wrong (e.g. docs-only root "
                "with code in a subfolder). Confirm or edit sections below; optionally add "
                "`pyproject.toml` / `package.json` where the real code lives.",
                "",
            ]
        )
    lines.extend(
        [
            "## Project Type",
            f"- **Type:** {profile.project_type or 'unknown'}",
            f"- **Confidence:** {profile.project_type_confidence:.2f}",
            f"- **Reason:** {profile.project_type_reason or 'N/A'}",
        ]
    )
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
    """Expert RAG removed (EPIC-94). Returns empty result."""
    return {"status": "removed", "note": "Expert RAG warming removed (EPIC-94)"}


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

_CLAUDE_DENY_RULES: list[str] = [
    "Bash(rm -rf *)",
    "Bash(git push --force *)",
    "Bash(git reset --hard *)",
    "Read(.env)",
    "Read(.env.*)",
]

_CLAUDE_SETTINGS_SCHEMA = "https://json.schemastore.org/claude-code-settings.json"


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

    # 2026 best practice: JSON schema reference
    config.setdefault("$schema", _CLAUDE_SETTINGS_SCHEMA)

    # 2026 best practice: enable project MCP servers
    config.setdefault("enableAllProjectMcpServers", True)

    # 2026 best practice: agent teams at high engagement
    if engagement_level == "high":
        env: dict[str, str] = config.setdefault("env", {})
        env.setdefault("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")

    # Permissions: allow list
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

    # Permissions: deny list (safety guardrails)
    deny_list: list[str] = permissions.setdefault("deny", [])
    for entry in _CLAUDE_DENY_RULES:
        if entry not in deny_list:
            deny_list.append(entry)

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
