"""User story document generation with acceptance criteria and task breakdown."""

from __future__ import annotations

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


class StoryTask(BaseModel):
    """A single implementation task within a story."""

    description: str
    file_path: str = ""


class StoryConfig(BaseModel):
    """Configuration for user story generation."""

    title: str
    epic_number: int = 0
    story_number: int = 0
    role: str = ""
    want: str = ""
    so_that: str = ""
    description: str = ""
    points: int = 0
    size: str = ""  # "S", "M", "L", "XL"
    tasks: list[StoryTask] = []
    acceptance_criteria: list[str] = []
    test_cases: list[str] = []
    dependencies: list[str] = []
    files: list[str] = []
    technical_notes: list[str] = []
    criteria_format: str = "checkbox"  # "checkbox" or "gherkin"
    style: str = "standard"  # "standard" or "comprehensive"


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class StoryGenerator:
    """Generates user story documents with acceptance criteria and tasks.

    Supports two styles:

    - **standard**: Core sections (user story statement, description, tasks,
      acceptance criteria, definition of done).
    - **comprehensive**: Adds technical notes, test cases, file manifest,
      dependencies, and INVEST checklist.

    Acceptance criteria can be rendered as checkbox lists (default, best for
    technical stories) or Gherkin Given/When/Then format (best for
    user-facing behavior).

    Output includes ``<!-- docsmcp:start:section -->`` markers for SmartMerger
    compatibility.
    """

    VALID_STYLES: ClassVar[frozenset[str]] = frozenset({"standard", "comprehensive"})
    VALID_SIZES: ClassVar[frozenset[str]] = frozenset({"S", "M", "L", "XL", ""})
    VALID_CRITERIA_FORMATS: ClassVar[frozenset[str]] = frozenset({"checkbox", "gherkin"})

    def generate(
        self,
        config: StoryConfig,
        *,
        project_root: Path | None = None,
        auto_populate: bool = False,
    ) -> str:
        """Generate a user story document.

        Args:
            config: Story configuration with title, tasks, criteria, etc.
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

        enrichment = (
            self._auto_populate(project_root, config)
            if auto_populate and project_root
            else {}
        )

        lines: list[str] = []

        lines.extend(self._render_title(config))
        lines.extend(self._render_user_story_statement(config))
        lines.extend(self._render_sizing(config))
        lines.extend(self._render_description(config, enrichment))
        lines.extend(self._render_files(config))
        lines.extend(self._render_tasks(config))
        lines.extend(self._render_acceptance_criteria(config))
        lines.extend(self._render_definition_of_done(config, enrichment))

        if style == "comprehensive":
            lines.extend(self._render_test_cases(config))
            lines.extend(self._render_technical_notes(config, enrichment))
            lines.extend(self._render_dependencies(config))
            lines.extend(self._render_invest_checklist())

        return "\n".join(lines)

    # -- section renderers --------------------------------------------------

    def _render_title(self, config: StoryConfig) -> list[str]:
        """Render the title with story numbering."""
        if config.epic_number and config.story_number:
            story_id = f"{config.epic_number}.{config.story_number}"
            return [f"# Story {story_id} -- {config.title}", ""]
        if config.story_number:
            return [f"# Story {config.story_number} -- {config.title}", ""]
        return [f"# {config.title}", ""]

    def _render_user_story_statement(self, config: StoryConfig) -> list[str]:
        """Render the 'As a / I want / So that' user story statement."""
        lines = [
            "<!-- docsmcp:start:user-story -->",
        ]

        if config.role and config.want:
            lines.append("")
            statement = f"> **As a** {config.role}, **I want** {config.want}"
            if config.so_that:
                statement += f", **so that** {config.so_that}"
            lines.append(statement)
            lines.append("")
        else:
            lines.append("")
            lines.append("> **As a** [role], **I want** [capability], "
                         "**so that** [benefit]")
            lines.append("")

        lines.extend(["<!-- docsmcp:end:user-story -->", ""])
        return lines

    def _render_sizing(self, config: StoryConfig) -> list[str]:
        """Render the points/size metadata."""
        lines = ["<!-- docsmcp:start:sizing -->"]

        parts: list[str] = []
        if config.points:
            parts.append(f"**Points:** {config.points}")
        if config.size and config.size in self.VALID_SIZES:
            parts.append(f"**Size:** {config.size}")

        if parts:
            lines.append(" | ".join(parts))
        else:
            lines.append("**Points:** TBD")

        lines.extend(["", "<!-- docsmcp:end:sizing -->", ""])
        return lines

    def _render_description(
        self,
        config: StoryConfig,
        enrichment: dict[str, Any],
    ) -> list[str]:
        """Render the Description section."""
        lines = [
            "<!-- docsmcp:start:description -->",
            "## Description",
            "",
        ]

        if config.description:
            lines.append(config.description)
        else:
            lines.append("Describe what this story delivers and any important context...")

        tech_stack = enrichment.get("tech_stack")
        if tech_stack:
            lines.append("")
            lines.append(f"**Tech Stack:** {tech_stack}")

        lines.extend(["", "<!-- docsmcp:end:description -->", ""])
        return lines

    def _render_files(self, config: StoryConfig) -> list[str]:
        """Render the Files section listing affected files."""
        if not config.files:
            return []

        lines = [
            "<!-- docsmcp:start:files -->",
            "## Files",
            "",
        ]

        for file_path in config.files:
            lines.append(f"- `{file_path}`")

        lines.extend(["", "<!-- docsmcp:end:files -->", ""])
        return lines

    def _render_tasks(self, config: StoryConfig) -> list[str]:
        """Render the Tasks section."""
        lines = [
            "<!-- docsmcp:start:tasks -->",
            "## Tasks",
            "",
        ]

        if config.tasks:
            for task in config.tasks:
                if task.file_path:
                    lines.append(f"- [ ] {task.description} (`{task.file_path}`)")
                else:
                    lines.append(f"- [ ] {task.description}")
        else:
            lines.append("- [ ] Define implementation tasks...")
            lines.append("- [ ] Write unit tests")
            lines.append("- [ ] Update documentation")

        lines.extend(["", "<!-- docsmcp:end:tasks -->", ""])
        return lines

    def _render_acceptance_criteria(self, config: StoryConfig) -> list[str]:
        """Render the Acceptance Criteria section in the chosen format."""
        fmt = (
            config.criteria_format
            if config.criteria_format in self.VALID_CRITERIA_FORMATS
            else "checkbox"
        )

        lines = [
            "<!-- docsmcp:start:acceptance-criteria -->",
            "## Acceptance Criteria",
            "",
        ]

        if fmt == "gherkin":
            lines.extend(self._render_gherkin_criteria(config))
        else:
            lines.extend(self._render_checkbox_criteria(config))

        lines.extend(["<!-- docsmcp:end:acceptance-criteria -->", ""])
        return lines

    def _render_checkbox_criteria(self, config: StoryConfig) -> list[str]:
        """Render acceptance criteria as checkbox list."""
        lines: list[str] = []

        if config.acceptance_criteria:
            for criterion in config.acceptance_criteria:
                lines.append(f"- [ ] {criterion}")
        else:
            lines.append("- [ ] Feature works as specified")
            lines.append("- [ ] Unit tests added with adequate coverage")
            lines.append("- [ ] Documentation updated")

        lines.append("")
        return lines

    def _render_gherkin_criteria(self, config: StoryConfig) -> list[str]:
        """Render acceptance criteria in Gherkin Given/When/Then format."""
        lines: list[str] = []

        if config.acceptance_criteria:
            for criterion in config.acceptance_criteria:
                slug = self._slugify(criterion)
                lines.append(f"### AC: {criterion}")
                lines.append("")
                lines.append("```gherkin")
                lines.append(f"Feature: {slug}")
                lines.append(f"  Scenario: {criterion}")
                lines.append("    Given [describe the precondition]")
                lines.append(f"    When [describe the action that triggers: {criterion.lower()}]")
                lines.append("    Then [describe the expected observable outcome]")
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

        return lines

    def _render_definition_of_done(
        self, config: StoryConfig, enrichment: dict[str, Any] | None = None,
    ) -> list[str]:
        """Render the Definition of Done section."""
        lines = [
            "<!-- docsmcp:start:definition-of-done -->",
            "## Definition of Done",
            "",
        ]

        if config.tasks:
            lines.append("- [ ] All tasks completed")
        lines.append("- [ ] Code reviewed and approved")
        lines.append("- [ ] Tests passing (unit + integration)")
        lines.append("- [ ] Documentation updated")
        lines.append("- [ ] No regressions introduced")

        # Add expert-recommended DoD items from security/testing experts.
        expert_guidance: list[dict[str, str]] = (enrichment or {}).get(
            "expert_guidance", [],
        )
        security_items = [g for g in expert_guidance if g["domain"] == "security"]
        testing_items = [g for g in expert_guidance if g["domain"] == "testing"]
        if security_items:
            lines.append("- [ ] Security review completed")
        if testing_items:
            lines.append("- [ ] Test coverage meets quality gate")

        lines.extend(["", "<!-- docsmcp:end:definition-of-done -->", ""])
        return lines

    # -- comprehensive-only sections ----------------------------------------

    def _render_test_cases(self, config: StoryConfig) -> list[str]:
        """Render the Test Cases section (comprehensive only)."""
        lines = [
            "<!-- docsmcp:start:test-cases -->",
            "## Test Cases",
            "",
        ]

        if config.test_cases:
            for i, test in enumerate(config.test_cases, 1):
                lines.append(f"{i}. {test}")
        else:
            lines.append("1. Test happy path...")
            lines.append("2. Test edge cases...")
            lines.append("3. Test error handling...")

        lines.extend(["", "<!-- docsmcp:end:test-cases -->", ""])
        return lines

    def _render_technical_notes(
        self,
        config: StoryConfig,
        enrichment: dict[str, Any],
    ) -> list[str]:
        """Render the Technical Notes section (comprehensive only)."""
        lines = [
            "<!-- docsmcp:start:technical-notes -->",
            "## Technical Notes",
            "",
        ]

        if config.technical_notes:
            for note in config.technical_notes:
                lines.append(f"- {note}")
        else:
            lines.append("- Document implementation hints, API contracts, data formats...")

        module_summary = enrichment.get("module_summary")
        if module_summary:
            lines.append("")
            lines.append(f"**Project Structure:** {module_summary}")

        expert_guidance: list[dict[str, str]] = enrichment.get("expert_guidance", [])
        if expert_guidance:
            lines.append("")
            lines.append("### Expert Recommendations")
            lines.append("")
            for item in expert_guidance:
                lines.append(
                    f"- **{item['expert']}** ({item['confidence']}): "
                    f"{item['advice']}"
                )

        lines.extend(["", "<!-- docsmcp:end:technical-notes -->", ""])
        return lines

    def _render_dependencies(self, config: StoryConfig) -> list[str]:
        """Render the Dependencies section (comprehensive only)."""
        lines = [
            "<!-- docsmcp:start:dependencies -->",
            "## Dependencies",
            "",
        ]

        if config.dependencies:
            for dep in config.dependencies:
                lines.append(f"- {dep}")
        else:
            lines.append("- List stories or external dependencies that must complete first...")

        lines.extend(["", "<!-- docsmcp:end:dependencies -->", ""])
        return lines

    def _render_invest_checklist(self) -> list[str]:
        """Render the INVEST checklist (comprehensive only)."""
        return [
            "<!-- docsmcp:start:invest -->",
            "## INVEST Checklist",
            "",
            "- [ ] **I**ndependent -- Can be developed and delivered independently",
            "- [ ] **N**egotiable -- Details can be refined during implementation",
            "- [ ] **V**aluable -- Delivers value to a user or the system",
            "- [ ] **E**stimable -- Team can estimate the effort",
            "- [ ] **S**mall -- Completable within one sprint/iteration",
            "- [ ] **T**estable -- Has clear criteria to verify completion",
            "",
            "<!-- docsmcp:end:invest -->",
            "",
        ]

    # -- auto-populate from analyzers ----------------------------------------

    def _auto_populate(
        self, project_root: Path, config: StoryConfig | None = None,
    ) -> dict[str, Any]:
        """Gather enrichment data from project analyzers and domain experts.

        Returns a dict with optional keys: tech_stack, module_summary,
        expert_guidance. Each key is only present when the corresponding
        analyzer/expert succeeds.
        """
        enrichment: dict[str, Any] = {}
        self._enrich_metadata(project_root, enrichment)
        self._enrich_module_map(project_root, enrichment)
        if config:
            self._enrich_experts(config, enrichment)
        return enrichment

    @staticmethod
    def _enrich_metadata(project_root: Path, enrichment: dict[str, Any]) -> None:
        """Enrich with tech stack from MetadataExtractor."""
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
        except Exception:
            logger.debug("story_auto_populate_metadata_failed", exc_info=True)

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
            logger.debug("story_auto_populate_module_map_failed", exc_info=True)

    # -- expert enrichment -------------------------------------------------

    _EXPERT_DOMAINS: ClassVar[list[tuple[str, str]]] = [
        ("security", "What security considerations apply to: {context}?"),
        ("testing", "What testing strategy is recommended for: {context}?"),
        ("architecture", "What architecture considerations apply to: {context}?"),
        ("code-quality", "What code quality standards apply to: {context}?"),
    ]

    @staticmethod
    def _enrich_experts(config: StoryConfig, enrichment: dict[str, Any]) -> None:
        """Enrich with guidance from TappsMCP domain experts."""
        try:
            from tapps_core.experts.engine import consult_expert
        except Exception:
            logger.debug("story_expert_import_failed", exc_info=True)
            return

        context = config.title
        if config.description:
            context = f"{config.title} - {config.description}"

        guidance: list[dict[str, str]] = []
        for domain, question_template in StoryGenerator._EXPERT_DOMAINS:
            try:
                question = question_template.format(context=context)
                result = consult_expert(question, domain=domain, max_chunks=3,
                                        max_context_length=1500)
                if result.confidence >= 0.3 and result.answer:
                    # Skip markdown headers to get actual advice content.
                    first_para = ""
                    for para in result.answer.strip().split("\n\n"):
                        cleaned = para.strip()
                        if cleaned and not cleaned.startswith("#"):
                            first_para = cleaned
                            break
                    if first_para:
                        guidance.append({
                            "domain": result.domain,
                            "expert": result.expert_name,
                            "advice": first_para,
                            "confidence": f"{result.confidence:.0%}",
                        })
            except Exception:
                logger.debug("story_expert_consult_failed", domain=domain, exc_info=True)

        if guidance:
            enrichment["expert_guidance"] = guidance

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert text to a URL-friendly slug."""
        slug = text.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = re.sub(r"-+", "-", slug)
        return slug.strip("-")
