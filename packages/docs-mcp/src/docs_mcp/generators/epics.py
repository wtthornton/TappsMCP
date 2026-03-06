"""Epic document generation with stories, acceptance criteria, and risk assessment."""

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


class EpicStoryStub(BaseModel):
    """A story stub within an epic (title + optional points/description)."""

    title: str
    points: int = 0
    description: str = ""


class EpicConfig(BaseModel):
    """Configuration for epic generation."""

    title: str
    number: int = 0
    goal: str = ""
    motivation: str = ""
    status: str = "Proposed"
    priority: str = ""
    estimated_loe: str = ""
    dependencies: list[str] = []
    blocks: list[str] = []
    acceptance_criteria: list[str] = []
    stories: list[EpicStoryStub] = []
    technical_notes: list[str] = []
    risks: list[str] = []
    non_goals: list[str] = []
    style: str = "standard"  # "standard" or "comprehensive"


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class EpicGenerator:
    """Generates Epic planning documents with stories and acceptance criteria.

    Supports two styles:

    - **standard**: Core sections (metadata, goal, motivation, acceptance
      criteria, stories, technical notes, out of scope).
    - **comprehensive**: Adds implementation order, risk assessment,
      files affected table, and performance targets placeholder.

    Output includes ``<!-- docsmcp:start:section -->`` markers for SmartMerger
    compatibility.
    """

    VALID_STYLES: ClassVar[frozenset[str]] = frozenset({"standard", "comprehensive"})
    VALID_STATUSES: ClassVar[frozenset[str]] = frozenset({
        "Proposed",
        "In Progress",
        "Complete",
        "Blocked",
        "Cancelled",
    })

    def generate(
        self,
        config: EpicConfig,
        *,
        project_root: Path | None = None,
        auto_populate: bool = False,
    ) -> str:
        """Generate an epic document.

        Args:
            config: Epic configuration with title, stories, etc.
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
        lines.extend(self._render_metadata(config))
        lines.extend(self._render_goal(config, enrichment))
        lines.extend(self._render_motivation(config))
        lines.extend(self._render_acceptance_criteria(config))
        lines.extend(self._render_stories(config))
        lines.extend(self._render_technical_notes(config, enrichment))
        lines.extend(self._render_non_goals(config))

        if style == "comprehensive":
            lines.extend(self._render_implementation_order(config))
            lines.extend(self._render_risk_assessment(config, enrichment))
            lines.extend(self._render_files_affected(config))
            lines.extend(self._render_performance_targets())

        return "\n".join(lines)

    # -- section renderers --------------------------------------------------

    def _render_title(self, config: EpicConfig) -> list[str]:
        """Render the H1 title."""
        number_prefix = f"Epic {config.number}: " if config.number else ""
        return [f"# {number_prefix}{config.title}", ""]

    def _render_metadata(self, config: EpicConfig) -> list[str]:
        """Render the metadata block (status, priority, LOE, dependencies)."""
        lines = [
            "<!-- docsmcp:start:metadata -->",
        ]

        status = config.status if config.status in self.VALID_STATUSES else "Proposed"
        lines.append(f"**Status:** {status}")

        if config.priority:
            lines.append(f"**Priority:** {config.priority}")

        if config.estimated_loe:
            lines.append(f"**Estimated LOE:** {config.estimated_loe}")

        if config.dependencies:
            lines.append(f"**Dependencies:** {', '.join(config.dependencies)}")

        if config.blocks:
            lines.append(f"**Blocks:** {', '.join(config.blocks)}")

        lines.extend(["", "<!-- docsmcp:end:metadata -->", "", "---", ""])
        return lines

    def _render_goal(
        self,
        config: EpicConfig,
        enrichment: dict[str, Any],
    ) -> list[str]:
        """Render the Goal section."""
        lines = [
            "<!-- docsmcp:start:goal -->",
            "## Goal",
            "",
        ]

        if config.goal:
            lines.append(config.goal)
        else:
            lines.append(
                "Describe the measurable outcome this epic achieves. "
                "What will be different when this work is complete?"
            )

        tech_stack = enrichment.get("tech_stack")
        if tech_stack:
            lines.append("")
            lines.append(f"**Tech Stack:** {tech_stack}")

        lines.extend(["", "<!-- docsmcp:end:goal -->", ""])
        return lines

    def _render_motivation(self, config: EpicConfig) -> list[str]:
        """Render the Motivation section."""
        lines = [
            "<!-- docsmcp:start:motivation -->",
            "## Motivation",
            "",
        ]

        if config.motivation:
            lines.append(config.motivation)
        else:
            lines.append(
                "Explain why this work matters. What customer pain point, "
                "business opportunity, or technical risk does it address?"
            )

        lines.extend(["", "<!-- docsmcp:end:motivation -->", ""])
        return lines

    def _render_acceptance_criteria(self, config: EpicConfig) -> list[str]:
        """Render the Acceptance Criteria section as a checkbox list."""
        lines = [
            "<!-- docsmcp:start:acceptance-criteria -->",
            "## Acceptance Criteria",
            "",
        ]

        if config.acceptance_criteria:
            for criterion in config.acceptance_criteria:
                lines.append(f"- [ ] {criterion}")
        else:
            lines.append("- [ ] Define verifiable acceptance criteria...")
            lines.append("- [ ] All stories completed and passing tests")
            lines.append("- [ ] Documentation updated")

        lines.extend(["", "<!-- docsmcp:end:acceptance-criteria -->", ""])
        return lines

    def _render_stories(self, config: EpicConfig) -> list[str]:
        """Render the Stories section with numbered stubs."""
        lines = [
            "<!-- docsmcp:start:stories -->",
            "## Stories",
            "",
        ]

        epic_num = config.number if config.number else 0

        if config.stories:
            for i, story in enumerate(config.stories, 1):
                story_id = f"{epic_num}.{i}" if epic_num else str(i)
                points_str = f"**Points:** {story.points}" if story.points else "**Points:** TBD"
                lines.append(f"### {story_id} -- {story.title}")
                lines.append("")
                lines.append(points_str)
                lines.append("")
                if story.description:
                    lines.append(story.description)
                else:
                    lines.append("Describe what this story delivers...")
                lines.append("")
                lines.append("**Tasks:**")
                lines.append(f"- [ ] Implement {story.title.lower()}")
                lines.append("- [ ] Write unit tests")
                lines.append("- [ ] Update documentation")
                lines.append("")
                lines.append(f"**Definition of Done:** {story.title} is implemented, tests "
                             "pass, and documentation is updated.")
                lines.append("")
                lines.append("---")
                lines.append("")
        else:
            for i in range(1, 4):
                story_id = f"{epic_num}.{i}" if epic_num else str(i)
                lines.append(f"### {story_id} -- Story Title")
                lines.append("")
                lines.append("**Points:** TBD")
                lines.append("")
                lines.append("Describe what this story delivers...")
                lines.append("")
                lines.append("**Tasks:**")
                lines.append("- Define implementation tasks...")
                lines.append("")
                lines.append("**Definition of Done:** TBD")
                lines.append("")
                lines.append("---")
                lines.append("")

        lines.extend(["<!-- docsmcp:end:stories -->", ""])
        return lines

    def _render_technical_notes(
        self,
        config: EpicConfig,
        enrichment: dict[str, Any],
    ) -> list[str]:
        """Render the Technical Notes section."""
        lines = [
            "<!-- docsmcp:start:technical-notes -->",
            "## Technical Notes",
            "",
        ]

        if config.technical_notes:
            for note in config.technical_notes:
                lines.append(f"- {note}")
        else:
            lines.append("- Document architecture decisions and key dependencies...")

        module_summary = enrichment.get("module_summary")
        if module_summary:
            lines.append("")
            lines.append(f"**Project Structure:** {module_summary}")

        dependencies = enrichment.get("dependencies")
        if dependencies:
            lines.append("")
            lines.append(f"**Key Dependencies:** {', '.join(dependencies[:10])}")

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

    def _render_non_goals(self, config: EpicConfig) -> list[str]:
        """Render the Out of Scope / Future Considerations section."""
        lines = [
            "<!-- docsmcp:start:non-goals -->",
            "## Out of Scope / Future Considerations",
            "",
        ]

        if config.non_goals:
            for item in config.non_goals:
                lines.append(f"- {item}")
        else:
            lines.append("- Define what is explicitly deferred to prevent scope creep...")

        lines.extend(["", "<!-- docsmcp:end:non-goals -->", ""])
        return lines

    # -- comprehensive-only sections ----------------------------------------

    def _render_implementation_order(self, config: EpicConfig) -> list[str]:
        """Render the Implementation Order section (comprehensive only)."""
        lines = [
            "<!-- docsmcp:start:implementation-order -->",
            "## Implementation Order",
            "",
        ]

        if config.stories:
            epic_num = config.number if config.number else 0
            for i, story in enumerate(config.stories, 1):
                story_id = f"{epic_num}.{i}" if epic_num else str(i)
                lines.append(f"{i}. Story {story_id}: {story.title}")
        else:
            lines.append("Define the recommended story sequencing and dependency graph...")

        lines.extend(["", "<!-- docsmcp:end:implementation-order -->", ""])
        return lines

    def _render_risk_assessment(
        self, config: EpicConfig, enrichment: dict[str, Any] | None = None,
    ) -> list[str]:
        """Render the Risk Assessment section (comprehensive only)."""
        lines = [
            "<!-- docsmcp:start:risk-assessment -->",
            "## Risk Assessment",
            "",
            "| Risk | Probability | Impact | Mitigation |",
            "|---|---|---|---|",
        ]

        if config.risks:
            for risk in config.risks:
                lines.append(f"| {risk} | Low/Medium/High | Low/Medium/High "
                             "| Define mitigation strategy |")
        else:
            lines.append("| Describe potential risks... | Low/Medium/High | Low/Medium/High "
                         "| Define mitigation strategy |")

        # Add expert-identified risks from security/performance domains.
        expert_guidance: list[dict[str, str]] = (enrichment or {}).get("expert_guidance", [])
        risk_domains = {"security", "performance", "devops"}
        risk_items = [g for g in expert_guidance if g["domain"] in risk_domains]
        if risk_items:
            lines.append("")
            lines.append("**Expert-Identified Risks:**")
            lines.append("")
            for item in risk_items:
                lines.append(f"- **{item['expert']}**: {item['advice']}")

        lines.extend(["", "<!-- docsmcp:end:risk-assessment -->", ""])
        return lines

    def _render_files_affected(self, config: EpicConfig) -> list[str]:
        """Render the Files Affected table (comprehensive only)."""
        lines = [
            "<!-- docsmcp:start:files-affected -->",
            "## Files Affected",
            "",
            "| File | Story | Action |",
            "|---|---|---|",
            "| `path/to/file.py` | N.M | Create / Modify |",
            "",
            "<!-- docsmcp:end:files-affected -->",
            "",
        ]
        return lines

    def _render_performance_targets(self) -> list[str]:
        """Render the Performance Targets placeholder (comprehensive only)."""
        lines = [
            "<!-- docsmcp:start:performance-targets -->",
            "## Performance Targets",
            "",
            "| Metric | Target | Measurement Method |",
            "|---|---|---|",
            "| Response latency (p50) | < N ms | Load test with k6/locust |",
            "| Response latency (p99) | < N ms | Load test with k6/locust |",
            "| Throughput | > N req/s | Sustained load for 5 min |",
            "| Memory usage | < N MB | Profiling under peak load |",
            "",
            "<!-- docsmcp:end:performance-targets -->",
            "",
        ]
        return lines

    # -- auto-populate from analyzers ----------------------------------------

    def _auto_populate(
        self, project_root: Path, config: EpicConfig | None = None,
    ) -> dict[str, Any]:
        """Gather enrichment data from project analyzers and domain experts.

        Returns a dict with optional keys: tech_stack, module_summary,
        dependencies, git_summary, expert_guidance. Each key is only present
        when the corresponding analyzer/expert succeeds.
        """
        enrichment: dict[str, Any] = {}
        self._enrich_metadata(project_root, enrichment)
        self._enrich_module_map(project_root, enrichment)
        self._enrich_git(project_root, enrichment)
        if config:
            self._enrich_experts(config, enrichment)
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
            logger.debug("epic_auto_populate_metadata_failed", exc_info=True)

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
            logger.debug("epic_auto_populate_module_map_failed", exc_info=True)

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
            logger.debug("epic_auto_populate_git_failed", exc_info=True)

    # -- expert enrichment -------------------------------------------------

    # Maps expert domains to the epic sections they enrich.
    _EXPERT_DOMAINS: ClassVar[list[tuple[str, str]]] = [
        ("security", "What security considerations apply to: {context}?"),
        ("architecture", "What architecture recommendations apply to: {context}?"),
        ("testing", "What testing strategy is recommended for: {context}?"),
        ("performance", "What performance considerations apply to: {context}?"),
        ("devops", "What CI/CD and deployment considerations apply to: {context}?"),
        ("code-quality", "What code quality standards apply to: {context}?"),
        ("api-design", "What API design best practices apply to: {context}?"),
        ("observability", "What monitoring and observability should be set up for: {context}?"),
    ]

    @staticmethod
    def _enrich_experts(config: EpicConfig, enrichment: dict[str, Any]) -> None:
        """Enrich with guidance from TappsMCP domain experts."""
        try:
            from tapps_core.experts.engine import consult_expert
        except Exception:
            logger.debug("epic_expert_import_failed", exc_info=True)
            return

        context = config.title
        if config.goal:
            context = f"{config.title} - {config.goal}"

        guidance: list[dict[str, str]] = []
        for domain, question_template in EpicGenerator._EXPERT_DOMAINS:
            try:
                question = question_template.format(context=context)
                result = consult_expert(question, domain=domain, max_chunks=3,
                                        max_context_length=1500)
                if result.confidence >= 0.3 and result.answer:
                    # Extract first meaningful paragraph from the answer.
                    first_para = result.answer.strip().split("\n\n")[0].strip()
                    if first_para:
                        guidance.append({
                            "domain": result.domain,
                            "expert": result.expert_name,
                            "advice": first_para,
                            "confidence": f"{result.confidence:.0%}",
                        })
            except Exception:
                logger.debug("epic_expert_consult_failed", domain=domain, exc_info=True)

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

    @staticmethod
    def parse_stories_json(stories_json: str) -> list[EpicStoryStub]:
        """Parse a JSON string into a list of EpicStoryStub objects.

        Accepts a JSON array of objects with keys: title, points, description.

        Args:
            stories_json: JSON string representing story stubs.

        Returns:
            List of EpicStoryStub objects.

        Raises:
            ValueError: If the JSON is malformed or not a list.
        """
        if not stories_json.strip():
            return []

        try:
            raw = json.loads(stories_json)
        except json.JSONDecodeError as exc:
            msg = f"Invalid JSON for stories: {exc}"
            raise ValueError(msg) from exc

        if not isinstance(raw, list):
            msg = "Stories JSON must be a list of objects"
            raise ValueError(msg)

        stories: list[EpicStoryStub] = []
        for item in raw:
            if isinstance(item, dict):
                stories.append(
                    EpicStoryStub(
                        title=str(item.get("title", "Untitled")),
                        points=int(item.get("points", 0)),
                        description=str(item.get("description", "")),
                    )
                )
        return stories
