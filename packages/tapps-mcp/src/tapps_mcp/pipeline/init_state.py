"""Shared configuration and mutable state for the bootstrap pipeline.

This is a leaf module: it imports nothing from its ``init_*`` siblings, so
every slice of the split can depend on it without an import cycle back
through :mod:`~tapps_mcp.pipeline.init` (TAP-5733).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from tapps_core.common.file_operations import (
    AgentInstructions,
    FileManifest,
    FileOperation,
    WriteMode,
)
from tapps_mcp import __version__
from tapps_mcp.distribution.nlt_mcp_config import DEFAULT_NLT_BUNDLE

if TYPE_CHECKING:
    from pathlib import Path

    from tapps_mcp.project.models import ProjectProfile


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
    memory_auto_recall: bool = False
    memory_auto_capture: bool = False
    overwrite_tech_stack_md: bool = False
    destructive_guard: bool = True
    linear_enforce_gate: bool = False
    linear_enforce_cache_gate: str = "off"
    session_start_gate: str = "off"
    install_git_hooks: bool = False
    linear_sdlc: bool = False
    with_report_studio: bool = False
    report_studio_tag: str = "v0.1.3"
    report_studio_scaffold: str = ""
    report_studio_template: str = "architecture_theory"
    linear_issue_prefix: str = "TAP"
    linear_team_id: str = ""
    linear_project_id: str = ""
    minimal: bool = False
    dry_run: bool = False
    verify_only: bool = False
    llm_engagement_level: str = "medium"
    skill_tier: str = "full"
    scaffold_experts: bool = False
    docs_automation: bool = True
    include_karpathy: bool = True
    mcp_bundle: str = DEFAULT_NLT_BUNDLE

    @classmethod
    def from_params(
        cls,
        *,
        llm_engagement_level: str | None = None,
        skill_tier: str | None = None,
        **kwargs: Any,
    ) -> BootstrapConfig:
        """Construct with optional ``llm_engagement_level`` / ``skill_tier`` fallback.

        When *llm_engagement_level* or *skill_tier* is ``None``, reads the
        value from :func:`~tapps_core.config.settings.load_settings`.  All
        other keyword arguments are forwarded to the dataclass constructor.
        """
        if llm_engagement_level is None or skill_tier is None:
            from tapps_core.config.settings import load_settings

            settings = load_settings()
            if llm_engagement_level is None:
                llm_engagement_level = settings.llm_engagement_level
            if skill_tier is None:
                skill_tier = settings.skill_tier
        return cls(
            llm_engagement_level=llm_engagement_level or "medium",
            skill_tier=skill_tier if skill_tier in {"core", "full"} else "full",
            **kwargs,
        )


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
