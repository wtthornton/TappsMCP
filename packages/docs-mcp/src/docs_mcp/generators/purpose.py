"""Purpose/Intent architecture template generator (Epic 85.1).

Generates a purpose-and-intent section for architecture documentation,
including project purpose, design principles, key decisions, and
intended audience. Uses project metadata and module map analysis.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

import structlog
from pydantic import BaseModel

if TYPE_CHECKING:
    from docs_mcp.generators.metadata import ProjectMetadata

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class PurposeResult(BaseModel):
    """Result of purpose/intent template generation."""

    content: str
    sections: list[str]
    degraded: bool = False


class PurposeGenerator:
    """Generates purpose/intent architecture documentation.

    Produces a structured markdown template covering:
    - Project purpose and scope
    - Design principles (inferred from dependencies/structure)
    - Key architectural decisions
    - Intended audience
    - Quality attributes
    """

    # Dependency -> inferred design principle
    _PRINCIPLE_HINTS: ClassVar[dict[str, str]] = {
        "fastapi": "API-first design with automatic OpenAPI documentation",
        "flask": "Lightweight web framework with flexible routing",
        "django": "Batteries-included web framework with ORM and admin",
        "pydantic": "Data validation through type annotations and schemas",
        "sqlalchemy": "Database abstraction with ORM and raw SQL support",
        "celery": "Distributed task processing with message queues",
        "pytest": "Test-driven development with fixture-based testing",
        "structlog": "Structured logging for observability",
        "mcp": "Model Context Protocol for AI tool integration",
        "httpx": "Async HTTP client for external service communication",
        "typer": "CLI-first interface with type-safe arguments",
        "click": "Command-line interface with composable commands",
        "redis": "In-memory caching and message brokering",
        "docker": "Container-based deployment and isolation",
    }

    # Structure markers -> quality attributes
    _QUALITY_MARKERS: ClassVar[dict[str, str]] = {
        "tests": "Testability — dedicated test suite present",
        ".github": "CI/CD — GitHub Actions or workflows configured",
        "Dockerfile": "Deployability — containerized deployment",
        "pyproject.toml": "Maintainability — modern Python packaging",
        ".pre-commit-config.yaml": "Code quality — pre-commit hooks enabled",
        "docs": "Documentation — dedicated documentation directory",
        "mypy.ini": "Type safety — static type checking configured",
    }

    def generate(
        self,
        project_root: Path,
        *,
        metadata: ProjectMetadata | None = None,
        project_name: str = "",
    ) -> PurposeResult:
        """Generate a purpose/intent architecture template.

        Args:
            project_root: Root directory of the project.
            metadata: Optional pre-extracted project metadata.
            project_name: Override project name.

        Returns:
            PurposeResult with the markdown content.
        """
        if not project_root.is_dir():
            return PurposeResult(content="", sections=[], degraded=True)

        # Extract metadata if not provided
        if metadata is None:
            try:
                from docs_mcp.generators.metadata import MetadataExtractor

                extractor = MetadataExtractor()
                metadata = extractor.extract(project_root)
            except Exception:
                logger.warning("metadata_extraction_failed", root=str(project_root))
                metadata = None

        name = project_name or (metadata.name if metadata else project_root.name)
        description = metadata.description if metadata else ""

        sections: list[str] = []
        section_names: list[str] = []

        # 1. Purpose & Scope
        purpose_lines = [f"# {name} — Architecture Overview", ""]
        purpose_lines.append("## Purpose & Scope")
        purpose_lines.append("")
        if description:
            purpose_lines.append(f"> {description}")
            purpose_lines.append("")
        purpose_lines.append(
            f"**{name}** exists to [describe the core problem this project solves]. "
            "It provides [key capabilities] for [target users/systems]."
        )
        purpose_lines.append("")
        sections.append("\n".join(purpose_lines))
        section_names.append("purpose")

        # 2. Design Principles
        principles = self._infer_principles(project_root, metadata)
        principle_lines = ["## Design Principles", ""]
        if principles:
            for principle in principles:
                principle_lines.append(f"- {principle}")
        else:
            principle_lines.append("- [Add your project's core design principles]")
        principle_lines.append("")
        sections.append("\n".join(principle_lines))
        section_names.append("principles")

        # 3. Key Decisions
        decision_lines = ["## Key Architectural Decisions", ""]
        decisions = self._infer_decisions(project_root, metadata)
        if decisions:
            for decision in decisions:
                decision_lines.append(f"- {decision}")
        else:
            decision_lines.append("- [Document major technology choices and their rationale]")
        decision_lines.append("")
        decision_lines.append(
            "*For detailed decision records, generate ADRs with `docs_generate_adr`.*"
        )
        decision_lines.append("")
        sections.append("\n".join(decision_lines))
        section_names.append("decisions")

        # 4. Intended Audience
        audience_lines = ["## Intended Audience", ""]
        audience_lines.append("| Audience | What they need |")
        audience_lines.append("|---|---|")
        audience_lines.append("| Developers | API reference, setup guide, contribution guide |")
        audience_lines.append(
            "| Operators | Deployment guide, configuration reference, monitoring |"
        )
        audience_lines.append("| Users | Getting started, tutorials, FAQ |")
        audience_lines.append("")
        sections.append("\n".join(audience_lines))
        section_names.append("audience")

        # 5. Quality Attributes
        qualities = self._detect_quality_attributes(project_root)
        quality_lines = ["## Quality Attributes", ""]
        if qualities:
            for quality in qualities:
                quality_lines.append(f"- {quality}")
        else:
            quality_lines.append(
                "- [List quality attributes: performance, security, reliability, etc.]"
            )
        quality_lines.append("")
        sections.append("\n".join(quality_lines))
        section_names.append("quality_attributes")

        content = "\n".join(sections)
        return PurposeResult(content=content, sections=section_names)

    def _infer_principles(self, project_root: Path, metadata: ProjectMetadata | None) -> list[str]:
        """Infer design principles from project dependencies."""
        principles: list[str] = []
        if metadata and metadata.dependencies:
            for dep in metadata.dependencies:
                dep_name = dep.split("[")[0].split(">=")[0].split("==")[0].strip().lower()
                if dep_name in self._PRINCIPLE_HINTS:
                    principles.append(self._PRINCIPLE_HINTS[dep_name])
        return principles[:6]

    def _infer_decisions(self, project_root: Path, metadata: ProjectMetadata | None) -> list[str]:
        """Infer key decisions from project structure."""
        decisions: list[str] = []

        # Check for monorepo
        packages_dir = project_root / "packages"
        if packages_dir.is_dir():
            sub_pkgs = [
                d.name
                for d in packages_dir.iterdir()
                if d.is_dir() and (d / "pyproject.toml").exists()
            ]
            if sub_pkgs:
                decisions.append(
                    f"**Monorepo structure** with {len(sub_pkgs)} packages: "
                    f"{', '.join(sub_pkgs[:4])}"
                )

        # Check for src layout
        src_dir = project_root / "src"
        if src_dir.is_dir():
            decisions.append("**src layout** for clear separation of source and project files")

        # Check python version
        if metadata and metadata.python_requires:
            decisions.append(f"**Python {metadata.python_requires}** as minimum supported version")

        # Check for Docker
        if (project_root / "Dockerfile").exists() or (project_root / "docker-compose.yml").exists():
            decisions.append("**Docker** for containerized deployment")

        return decisions[:5]

    def _detect_quality_attributes(self, project_root: Path) -> list[str]:
        """Detect quality attributes from project structure."""
        qualities: list[str] = []
        for marker, description in self._QUALITY_MARKERS.items():
            if (project_root / marker).exists():
                qualities.append(description)
        return qualities
