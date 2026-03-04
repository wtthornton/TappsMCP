"""Product Requirements Document (PRD) generation with phased requirements."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, ClassVar

import structlog
from pydantic import BaseModel

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PRDPhase(BaseModel):
    """A single phase in the phased requirements roadmap."""

    name: str
    description: str = ""
    requirements: list[str] = []


class PRDConfig(BaseModel):
    """Configuration for PRD generation."""

    title: str
    problem: str = ""
    personas: list[str] = []
    phases: list[PRDPhase] = []
    constraints: list[str] = []
    non_goals: list[str] = []
    style: str = "standard"  # "standard" or "comprehensive"
    existing_content: str = ""


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class PRDGenerator:
    """Generates Product Requirements Documents with phased requirements.

    Supports two styles:
    - **standard**: Core sections only (Executive Summary, Problem Statement,
      User Personas, Solution Overview, Phased Requirements, Acceptance
      Criteria, Technical Constraints, Non-Goals).
    - **comprehensive**: Adds Boundary System ("Always do" / "Ask first" /
      "Never do") and Architecture Overview sections.

    Output includes ``<!-- docsmcp:start:section -->`` markers for SmartMerger
    compatibility.
    """

    VALID_STYLES: ClassVar[frozenset[str]] = frozenset({"standard", "comprehensive"})

    def generate(
        self,
        config: PRDConfig,
        *,
        project_root: Path | None = None,
        auto_populate: bool = False,
    ) -> str:
        """Generate a PRD document.

        Args:
            config: PRD configuration with title, problem, phases, etc.
            project_root: Project root for auto-populate analyzers.
            auto_populate: When True, enrich sections from project analyzers.

        Returns:
            Rendered markdown content with docsmcp markers.
        """
        style = config.style if config.style in self.VALID_STYLES else "standard"

        if style != config.style:
            logger.warning(
                "invalid_style_falling_back",
                style=config.style,
                fallback="standard",
            )

        enrichment = self._auto_populate(project_root) if auto_populate and project_root else {}

        lines: list[str] = []

        lines.extend(self._render_title(config.title))
        lines.extend(self._render_executive_summary(config, enrichment))
        lines.extend(self._render_problem_statement(config))
        lines.extend(self._render_user_personas(config))
        lines.extend(self._render_solution_overview(config, enrichment))
        lines.extend(self._render_phased_requirements(config))
        lines.extend(self._render_acceptance_criteria(config))
        lines.extend(self._render_technical_constraints(config, enrichment))
        lines.extend(self._render_non_goals(config))

        if style == "comprehensive":
            lines.extend(self._render_boundary_system())
            lines.extend(self._render_architecture_overview(enrichment))

        return "\n".join(lines)

    # -- section renderers --------------------------------------------------

    def _render_title(self, title: str) -> list[str]:
        """Render the H1 title."""
        return [f"# PRD: {title}", ""]

    def _render_executive_summary(
        self,
        config: PRDConfig,
        enrichment: dict[str, Any],
    ) -> list[str]:
        """Render the Executive Summary section."""
        lines = [
            "<!-- docsmcp:start:executive-summary -->",
            "## Executive Summary",
            "",
        ]

        if config.problem:
            lines.append(config.problem)
        else:
            lines.append("Describe the high-level purpose and value proposition of this product.")

        # Enrich with tech stack if available
        tech_stack = enrichment.get("tech_stack")
        if tech_stack:
            lines.append("")
            lines.append(f"**Tech Stack:** {tech_stack}")

        lines.extend(["", "<!-- docsmcp:end:executive-summary -->", ""])
        return lines

    def _render_problem_statement(self, config: PRDConfig) -> list[str]:
        """Render the Problem Statement section."""
        lines = [
            "<!-- docsmcp:start:problem-statement -->",
            "## Problem Statement",
            "",
        ]

        if config.problem:
            lines.append(config.problem)
        else:
            lines.append("Describe the problem this product solves...")

        lines.extend(["", "<!-- docsmcp:end:problem-statement -->", ""])
        return lines

    def _render_user_personas(self, config: PRDConfig) -> list[str]:
        """Render the User Personas section."""
        lines = [
            "<!-- docsmcp:start:user-personas -->",
            "## User Personas",
            "",
        ]

        if config.personas:
            for i, persona in enumerate(config.personas, 1):
                lines.append(f"{i}. **{persona}**")
        else:
            lines.append("Define target user personas...")

        lines.extend(["", "<!-- docsmcp:end:user-personas -->", ""])
        return lines

    def _render_solution_overview(
        self,
        config: PRDConfig,
        enrichment: dict[str, Any],
    ) -> list[str]:
        """Render the Solution Overview section."""
        lines = [
            "<!-- docsmcp:start:solution-overview -->",
            "## Solution Overview",
            "",
        ]

        lines.append("Describe the proposed solution at a high level...")

        # Enrich with module structure if available
        module_summary = enrichment.get("module_summary")
        if module_summary:
            lines.append("")
            lines.append(f"**Project Structure:** {module_summary}")

        lines.extend(["", "<!-- docsmcp:end:solution-overview -->", ""])
        return lines

    def _render_phased_requirements(self, config: PRDConfig) -> list[str]:
        """Render the Phased Requirements section."""
        lines = [
            "<!-- docsmcp:start:phased-requirements -->",
            "## Phased Requirements",
            "",
        ]

        if config.phases:
            for i, phase in enumerate(config.phases, 1):
                lines.append(f"### Phase {i}: {phase.name}")
                lines.append("")
                if phase.description:
                    lines.append(phase.description)
                    lines.append("")
                if phase.requirements:
                    for req in phase.requirements:
                        lines.append(f"- {req}")
                    lines.append("")
        else:
            for i in range(1, 4):
                lines.append(f"### Phase {i}: TBD")
                lines.append("")
                lines.append("- Define requirements for this phase...")
                lines.append("")

        lines.extend(["<!-- docsmcp:end:phased-requirements -->", ""])
        return lines

    def _render_acceptance_criteria(self, config: PRDConfig) -> list[str]:
        """Render the Acceptance Criteria section in Gherkin format."""
        lines = [
            "<!-- docsmcp:start:acceptance-criteria -->",
            "## Acceptance Criteria",
            "",
        ]

        if config.phases:
            for phase in config.phases:
                if phase.requirements:
                    for req in phase.requirements:
                        slug = self._slugify(req)[:40]
                        lines.append(f"### AC: {req[:60]}")
                        lines.append("")
                        lines.append("```gherkin")
                        lines.append(f"Feature: {slug}")
                        lines.append(f"  Scenario: {req[:60]}")
                        lines.append("    Given the system is in its initial state")
                        lines.append(f"    When {req.lower()}")
                        lines.append("    Then the expected outcome is achieved")
                        lines.append("```")
                        lines.append("")
        else:
            lines.append("```gherkin")
            lines.append("Feature: Example")
            lines.append("  Scenario: Define acceptance criteria")
            lines.append("    Given a precondition")
            lines.append("    When an action is performed")
            lines.append("    Then the expected result occurs")
            lines.append("```")
            lines.append("")

        lines.extend(["<!-- docsmcp:end:acceptance-criteria -->", ""])
        return lines

    def _render_technical_constraints(
        self,
        config: PRDConfig,
        enrichment: dict[str, Any],
    ) -> list[str]:
        """Render the Technical Constraints section."""
        lines = [
            "<!-- docsmcp:start:technical-constraints -->",
            "## Technical Constraints",
            "",
        ]

        if config.constraints:
            for constraint in config.constraints:
                lines.append(f"- {constraint}")
        else:
            lines.append("- Define technical constraints...")

        # Enrich with dependencies if available
        dependencies = enrichment.get("dependencies")
        if dependencies:
            lines.append("")
            lines.append(f"**Key Dependencies:** {', '.join(dependencies[:10])}")

        lines.extend(["", "<!-- docsmcp:end:technical-constraints -->", ""])
        return lines

    def _render_non_goals(self, config: PRDConfig) -> list[str]:
        """Render the Non-Goals section."""
        lines = [
            "<!-- docsmcp:start:non-goals -->",
            "## Non-Goals",
            "",
        ]

        if config.non_goals:
            for item in config.non_goals:
                lines.append(f"- {item}")
        else:
            lines.append("- Define what is explicitly out of scope...")

        lines.extend(["", "<!-- docsmcp:end:non-goals -->", ""])
        return lines

    def _render_boundary_system(self) -> list[str]:
        """Render the three-tier Boundary System section (comprehensive only)."""
        lines = [
            "<!-- docsmcp:start:boundary-system -->",
            "## Boundary System",
            "",
            "### Always Do",
            "",
            "- Define actions that should always be taken...",
            "",
            "### Ask First",
            "",
            "- Define actions that require confirmation before proceeding...",
            "",
            "### Never Do",
            "",
            "- Define actions that are explicitly prohibited...",
            "",
            "<!-- docsmcp:end:boundary-system -->",
            "",
        ]
        return lines

    def _render_architecture_overview(
        self,
        enrichment: dict[str, Any],
    ) -> list[str]:
        """Render the Architecture Overview section (comprehensive only)."""
        lines = [
            "<!-- docsmcp:start:architecture-overview -->",
            "## Architecture Overview",
            "",
        ]

        module_summary = enrichment.get("module_summary")
        if module_summary:
            lines.append(module_summary)
        else:
            lines.append("Describe the high-level architecture...")

        quality_summary = enrichment.get("quality_summary")
        if quality_summary:
            lines.append("")
            lines.append(f"**Quality:** {quality_summary}")

        git_summary = enrichment.get("git_summary")
        if git_summary:
            lines.append("")
            lines.append(f"**Recent Activity:** {git_summary}")

        lines.extend(["", "<!-- docsmcp:end:architecture-overview -->", ""])
        return lines

    # -- auto-populate from analyzers ----------------------------------------

    def _auto_populate(self, project_root: Path) -> dict[str, Any]:
        """Gather enrichment data from project analyzers.

        Returns a dict with optional keys: tech_stack, module_summary,
        dependencies, quality_summary, git_summary. Each key is only
        present when the corresponding analyzer succeeds.
        """
        enrichment: dict[str, Any] = {}
        self._enrich_metadata(project_root, enrichment)
        self._enrich_module_map(project_root, enrichment)
        self._enrich_quality(project_root, enrichment)
        self._enrich_git(project_root, enrichment)
        return enrichment

    @staticmethod
    def _enrich_metadata(project_root: Path, enrichment: dict[str, Any]) -> None:
        """Enrich with tech stack and dependencies from MetadataExtractor."""
        try:
            from docs_mcp.generators.metadata import MetadataExtractor

            extractor = MetadataExtractor()
            metadata = extractor.extract(project_root)
            parts: list[str] = []
            if metadata.name:
                parts.append(metadata.name)
            if metadata.python_requires:
                parts.append(f"Python {metadata.python_requires}")
            if parts:
                enrichment["tech_stack"] = ", ".join(parts)
            if metadata.dependencies:
                enrichment["dependencies"] = metadata.dependencies
        except Exception:
            logger.debug("prd_auto_populate_metadata_failed", exc_info=True)

    @staticmethod
    def _enrich_module_map(project_root: Path, enrichment: dict[str, Any]) -> None:
        """Enrich with module structure from ModuleMapAnalyzer."""
        try:
            from docs_mcp.analyzers.module_map import ModuleMapAnalyzer

            analyzer = ModuleMapAnalyzer()
            module_map = analyzer.analyze(project_root)
            enrichment["module_summary"] = (
                f"{module_map.total_packages} packages, "
                f"{module_map.total_modules} modules, "
                f"{module_map.public_api_count} public APIs"
            )
        except Exception:
            logger.debug("prd_auto_populate_module_map_failed", exc_info=True)

    @staticmethod
    def _enrich_quality(project_root: Path, enrichment: dict[str, Any]) -> None:
        """Enrich with quality scores from TappsIntegration."""
        try:
            from docs_mcp.integrations.tapps import TappsIntegration

            integration = TappsIntegration(project_root)
            if integration.is_available:
                enrichment_data = integration.load_enrichment()
                if enrichment_data.overall_project_score is not None:
                    enrichment["quality_summary"] = (
                        f"Overall score: {enrichment_data.overall_project_score:.0f}/100"
                    )
        except Exception:
            logger.debug("prd_auto_populate_tapps_failed", exc_info=True)

    @staticmethod
    def _enrich_git(project_root: Path, enrichment: dict[str, Any]) -> None:
        """Enrich with recent git context from GitHistoryAnalyzer."""
        try:
            from docs_mcp.analyzers.git_history import GitHistoryAnalyzer

            git_analyzer = GitHistoryAnalyzer(project_root)
            commits = git_analyzer.get_commits(limit=5)
            if commits:
                enrichment["git_summary"] = (
                    f"{len(commits)} recent commits, "
                    f"latest: {commits[0].message[:50]}"
                )
        except Exception:
            logger.debug("prd_auto_populate_git_failed", exc_info=True)

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert text to a URL-friendly slug."""
        slug = text.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = re.sub(r"-+", "-", slug)
        return slug.strip("-")

    @staticmethod
    def parse_phases_json(phases_json: str) -> list[PRDPhase]:
        """Parse a JSON string into a list of PRDPhase objects.

        Accepts a JSON array of objects with keys: name, description,
        requirements.

        Args:
            phases_json: JSON string representing phases.

        Returns:
            List of PRDPhase objects.

        Raises:
            ValueError: If the JSON is malformed or not a list.
        """
        if not phases_json.strip():
            return []

        try:
            raw = json.loads(phases_json)
        except json.JSONDecodeError as exc:
            msg = f"Invalid JSON for phases: {exc}"
            raise ValueError(msg) from exc

        if not isinstance(raw, list):
            msg = "Phases JSON must be a list of objects"
            raise ValueError(msg)

        phases: list[PRDPhase] = []
        for item in raw:
            if isinstance(item, dict):
                phases.append(
                    PRDPhase(
                        name=str(item.get("name", "Unnamed")),
                        description=str(item.get("description", "")),
                        requirements=[str(r) for r in item.get("requirements", [])],
                    )
                )
        return phases
