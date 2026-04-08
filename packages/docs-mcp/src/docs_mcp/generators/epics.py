"""Epic document generation with stories, acceptance criteria, and risk assessment."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import time
from typing import TYPE_CHECKING, Any, ClassVar

import structlog
from pydantic import BaseModel

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger(__name__)

_MAX_COMMIT_DISPLAY_LEN = 50

# Keyword → out-of-scope suggestion for context-aware non-goals placeholder.
_NON_GOAL_KEYWORD_HINTS: dict[str, str] = {
    "auth": "Multi-factor authentication",
    "api": "Third-party API integrations",
    "database": "Database migration tooling",
    "db": "Database migration tooling",
    "ui": "Mobile responsive design",
    "frontend": "Mobile responsive design",
    "test": "Performance benchmarking",
    "deploy": "Multi-cloud deployment",
    "search": "Full-text search optimization",
    "security": "Penetration testing",
    "monitor": "Real-time alerting",
    "cache": "Distributed cache invalidation",
    "migration": "Cross-platform migration support",
    "performance": "Hardware-level optimization",
    "logging": "Log aggregation platform integration",
    "config": "Dynamic runtime reconfiguration",
}


def _derive_non_goal_hints(title: str) -> list[str]:
    """Extract boundary suggestions from title keywords.

    Returns up to 3 unique hints based on keyword matches in the title.
    """
    title_lower = title.lower()
    tokens = set(re.split(r"[\s\-_/]+", title_lower))
    seen: set[str] = set()
    hints: list[str] = []
    for keyword, hint in _NON_GOAL_KEYWORD_HINTS.items():
        if keyword in tokens or keyword in title_lower:
            if hint not in seen:
                seen.add(hint)
                hints.append(hint)
                if len(hints) >= 3:
                    break
    return hints


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class EpicStoryStub(BaseModel):
    """A story stub within an epic (title + optional points/description/tasks)."""

    title: str
    points: int = 0
    description: str = ""
    tasks: list[str] = []
    ac_count: int = 0


class EpicConfig(BaseModel):
    """Configuration for epic generation."""

    title: str
    number: int = 0
    purpose_and_intent: str = ""  # Required per design doc §2 (Epic 75.3)
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
    style: str = "standard"  # "minimal", "standard", "comprehensive", or "auto"
    success_metrics: list[str] = []
    stakeholders: list[str] = []
    references: list[str] = []
    files: list[str] = []
    link_stories: bool = False
    story_paths: dict[int, str] = {}


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class EpicGenerator:
    """Generates Epic planning documents with stories and acceptance criteria.

    Supports four styles:

    - **minimal**: Lightweight output (title, metadata, purpose, goal, AC,
      single story stub, DoD). Used for simple epics with few stories.
    - **standard**: Core sections (metadata, goal, motivation, acceptance
      criteria, stories, technical notes, out of scope).
    - **comprehensive**: Adds success metrics, stakeholders, references,
      implementation order, risk assessment, files affected table.
    - **auto**: Automatically selects minimal, standard, or comprehensive
      based on the number of stories, risks, files, and success metrics.

    Output includes ``<!-- docsmcp:start:section -->`` markers for SmartMerger
    compatibility.
    """

    VALID_STYLES: ClassVar[frozenset[str]] = frozenset({
        "minimal", "standard", "comprehensive", "auto",
    })
    VALID_STATUSES: ClassVar[frozenset[str]] = frozenset({
        "Proposed",
        "In Progress",
        "Complete",
        "Blocked",
        "Cancelled",
    })

    # Keyword → suggested story titles (keyword-to-pattern mapping for suggestion engine).
    _STORY_PATTERNS: ClassVar[dict[str, list[str]]] = {
        "auth": ["Data Models", "Auth Endpoints", "Session Management", "Tests"],
        "login": ["Data Models", "Auth Endpoints", "Session Management", "Tests"],
        "user": ["Data Models", "Auth Endpoints", "Session Management", "Tests"],
        "account": ["Data Models", "Auth Endpoints", "Session Management", "Tests"],
        "api": ["Schema & Models", "Endpoint Handlers", "Validation", "Client SDK", "Tests"],
        "endpoint": ["Schema & Models", "Endpoint Handlers", "Validation", "Client SDK", "Tests"],
        "rest": ["Schema & Models", "Endpoint Handlers", "Validation", "Client SDK", "Tests"],
        "graphql": ["Schema & Models", "Endpoint Handlers", "Validation", "Client SDK", "Tests"],
        "ui": ["Component Scaffold", "State Management", "Form Validation", "Styling", "Tests"],
        "frontend": ["Component Scaffold", "State Management", "Form Validation", "Styling", "Tests"],
        "page": ["Component Scaffold", "State Management", "Form Validation", "Styling", "Tests"],
        "form": ["Component Scaffold", "State Management", "Form Validation", "Styling", "Tests"],
        "database": ["Schema Design", "Migration Scripts", "Query Layer", "Seed Data", "Tests"],
        "migration": ["Schema Design", "Migration Scripts", "Query Layer", "Seed Data", "Tests"],
        "schema": ["Schema Design", "Migration Scripts", "Query Layer", "Seed Data", "Tests"],
        "deploy": ["Config Setup", "Build Pipeline", "Deploy Scripts", "Monitoring", "Tests"],
        "ci": ["Config Setup", "Build Pipeline", "Deploy Scripts", "Monitoring", "Tests"],
        "pipeline": ["Config Setup", "Build Pipeline", "Deploy Scripts", "Monitoring", "Tests"],
        "infra": ["Config Setup", "Build Pipeline", "Deploy Scripts", "Monitoring", "Tests"],
        "security": ["Threat Model", "Scanner Integration", "Remediation", "Policy Docs", "Tests"],
        "audit": ["Threat Model", "Scanner Integration", "Remediation", "Policy Docs", "Tests"],
        "scan": ["Threat Model", "Scanner Integration", "Remediation", "Policy Docs", "Tests"],
    }

    # Keyword → suggested risk descriptions.
    _RISK_PATTERNS: ClassVar[dict[str, list[str]]] = {
        "auth": ["Authentication bypass if token validation incomplete"],
        "security": ["Authentication bypass if token validation incomplete"],
        "api": ["Breaking API changes affecting existing clients"],
        "endpoint": ["Breaking API changes affecting existing clients"],
        "database": ["Data loss during migration if rollback path untested"],
        "migration": ["Data loss during migration if rollback path untested"],
        "deploy": ["Deployment downtime if blue-green not configured"],
        "infra": ["Deployment downtime if blue-green not configured"],
        "performance": ["Performance degradation under load without benchmarks"],
        "scale": ["Performance degradation under load without benchmarks"],
    }

    @classmethod
    def _suggest_stories(cls, title: str, goal: str) -> list[EpicStoryStub]:
        """Suggest story stubs from title/goal keywords.

        Scans the title and goal for known keyword patterns and returns a
        deduplicated list of relevant story stubs. Falls back to the generic
        3-story pattern when no keywords match.

        Returns:
            A list of :class:`EpicStoryStub` with ``(suggested)`` suffix on each title.
        """
        combined = (title + " " + goal).lower()
        tokens = set(re.split(r"[\s\-_/]+", combined))

        seen_patterns: set[int] = set()
        story_titles: list[str] = []

        for keyword, stories in cls._STORY_PATTERNS.items():
            pattern_id = id(stories)
            if pattern_id in seen_patterns:
                continue
            if keyword in tokens or keyword in combined:
                seen_patterns.add(pattern_id)
                story_titles = stories
                break  # First matching keyword group wins

        if not story_titles:
            story_titles = ["Foundation & Setup", "Core Implementation", "Testing & Documentation"]

        return [EpicStoryStub(title=f"{t} (suggested)") for t in story_titles]

    @classmethod
    def _suggest_risks(cls, title: str, goal: str) -> list[str]:
        """Suggest risk descriptions from title/goal keywords.

        Returns an empty list when no keywords match.
        """
        combined = (title + " " + goal).lower()
        tokens = set(re.split(r"[\s\-_/]+", combined))

        seen: set[str] = set()
        risks: list[str] = []

        for keyword, risk_list in cls._RISK_PATTERNS.items():
            if keyword in tokens or keyword in combined:
                for risk in risk_list:
                    if risk not in seen:
                        seen.add(risk)
                        risks.append(risk)

        return risks

    @staticmethod
    def _infer_quick_start_defaults(config: EpicConfig) -> EpicConfig:
        """Fill empty fields with title-derived defaults for quick-start mode.

        Explicit parameters are never overwritten -- only empty/default fields
        are populated.
        """
        title = config.title.strip()

        updates: dict[str, Any] = {}

        if not config.goal:
            updates["goal"] = (
                f"Implement {title} with full test coverage and documentation."
            )

        if not config.motivation:
            updates["motivation"] = (
                f"This epic addresses the need for {title} in the project."
            )

        if not config.acceptance_criteria:
            updates["acceptance_criteria"] = [
                "Core functionality implemented",
                "Unit tests passing with >= 80% coverage",
                "Documentation updated",
            ]

        if not config.stories:
            updates["stories"] = [
                EpicStoryStub(title="Foundation & Setup", points=2),
                EpicStoryStub(title="Core Implementation", points=5),
                EpicStoryStub(title="Testing & Documentation", points=3),
            ]

        if not config.priority:
            updates["priority"] = "P2 - Medium"

        if config.style == "standard":
            # Let auto-detect pick the best style for inferred content.
            updates["style"] = "auto"

        if updates:
            return config.model_copy(update=updates)
        return config

    def generate(
        self,
        config: EpicConfig,
        *,
        project_root: Path | None = None,
        auto_populate: bool = False,
        quick_start: bool = False,
    ) -> str:
        """Generate an epic document.

        Args:
            config: Epic configuration with title, stories, etc.
            project_root: Project root for auto-populate analyzers.
            auto_populate: When True, enrich sections from project analyzers.
            quick_start: When True, infer defaults from the title for empty
                fields. Explicit parameters are never overwritten.

        Returns:
            Rendered markdown content with docsmcp markers.
        """
        content, _timing = self.generate_with_timing(
            config,
            project_root=project_root,
            auto_populate=auto_populate,
            quick_start=quick_start,
        )
        return content

    def generate_with_timing(
        self,
        config: EpicConfig,
        *,
        project_root: Path | None = None,
        auto_populate: bool = False,
        quick_start: bool = False,
    ) -> tuple[str, dict[str, int]]:
        """Like :meth:`generate` but returns per-phase timings (milliseconds).

        Keys may include: ``metadata_ms``, ``module_map_ms``, ``git_ms``,
        ``experts_ms``, ``auto_populate_ms`` (wall-clock for populate),
        ``render_ms`` (markdown assembly and file-hint scans), ``total_ms``.
        """
        if quick_start:
            config = self._infer_quick_start_defaults(config)

        style = config.style if config.style in self.VALID_STYLES else "standard"

        if style != config.style:
            logger.warning(
                "invalid_style_falling_back",
                style=config.style,
                fallback="standard",
            )

        # Resolve "auto" to a concrete style based on config complexity.
        if style == "auto":
            style = self._auto_detect_style(config)

        timing: dict[str, int] = {}
        t_wall = time.perf_counter()
        enrichment: dict[str, Any] = {}
        if auto_populate and project_root:
            enrichment, ap_timings = self._auto_populate(project_root, config)
            timing.update(ap_timings)

        t_render = time.perf_counter()
        lines: list[str] = []

        if style == "minimal":
            lines.extend(self._render_title(config))
            lines.extend(self._render_metadata(config))
            lines.extend(self._render_purpose_and_intent(config))
            lines.extend(self._render_goal(config, enrichment))
            lines.extend(self._render_acceptance_criteria(config))
            lines.extend(self._render_stories(config))
            lines.extend(self._render_definition_of_done(config))
        else:
            lines.extend(self._render_title(config))
            lines.extend(self._render_metadata(config))
            lines.extend(self._render_purpose_and_intent(config))
            lines.extend(self._render_goal(config, enrichment))
            lines.extend(self._render_motivation(config))
            lines.extend(self._render_acceptance_criteria(config))
            lines.extend(self._render_stories(config))
            lines.extend(self._render_technical_notes(config, enrichment))
            lines.extend(self._render_non_goals(config))

            # File hints: render file-specific sections when files are provided
            if config.files and project_root:
                lines.extend(
                    self._render_file_hints(config.files, project_root, config)
                )
                lines.extend(
                    self._render_related_epics(config.files, project_root)
                )

            if style == "comprehensive":
                lines.extend(self._render_success_metrics(config))
                lines.extend(self._render_stakeholders(config))
                lines.extend(self._render_references(config))
                lines.extend(self._render_implementation_order(config))
                lines.extend(self._render_risk_assessment(config, enrichment))
                if not config.files:
                    # Only render generic files-affected when no file hints given
                    lines.extend(self._render_files_affected(config))
                lines.extend(self._render_performance_targets(enrichment, config))

        timing["render_ms"] = int((time.perf_counter() - t_render) * 1000)
        timing["total_ms"] = int((time.perf_counter() - t_wall) * 1000)
        return "\n".join(lines), timing

    # -- style detection ----------------------------------------------------

    @staticmethod
    def _auto_detect_style(config: EpicConfig) -> str:
        """Choose minimal, standard, or comprehensive based on config complexity.

        Rules:
        - comprehensive: stories > 5, or risks provided, or files > 3,
          or success_metrics provided.
        - minimal: stories <= 1 and no risks and no files.
        - standard: everything else.
        """
        if (
            len(config.stories) > 5
            or config.risks
            or len(config.files) > 3
            or config.success_metrics
        ):
            return "comprehensive"
        if len(config.stories) <= 1 and not config.risks and not config.files:
            return "minimal"
        return "standard"

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

    def _render_purpose_and_intent(self, config: EpicConfig) -> list[str]:
        """Render the Purpose & Intent section (required per design doc §2, Epic 75.3)."""
        lines = [
            "<!-- docsmcp:start:purpose-intent -->",
            "## Purpose & Intent",
            "",
        ]
        if config.purpose_and_intent and config.purpose_and_intent.strip():
            lines.append(config.purpose_and_intent.strip())
        else:
            lines.append(
                "We are doing this so that the goals below are achieved and "
                "acceptance criteria are met. Refine this paragraph to state "
                "the strategic intent and outcomes."
            )
        lines.extend(["", "<!-- docsmcp:end:purpose-intent -->", ""])
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
        elif config.title.strip():
            lines.append(
                f"Describe how **{config.title.strip()}** will change the system. "
                "What measurable outcome proves this epic is complete?"
            )
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
        elif config.title.strip():
            lines.append(
                f"Explain why **{config.title.strip()}** matters. "
                "What pain point or opportunity does it address?"
            )
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
        elif config.title.strip():
            lines.append(
                f"- [ ] Define verifiable criteria for **{config.title.strip()}**..."
            )
            lines.append("- [ ] All stories completed and passing tests")
            lines.append("- [ ] Documentation updated")
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

        epic_num = config.number

        if config.stories:
            for i, story in enumerate(config.stories, 1):
                story_id = f"{epic_num}.{i}"
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

                # Show AC count if available.
                if story.ac_count:
                    lines.append(f"({story.ac_count} acceptance criteria)")
                    lines.append("")

                # Story link if enabled.
                story_path = config.story_paths.get(i)
                if config.link_stories and story_path:
                    lines.append(f"-> [Full story]({story_path})")
                    lines.append("")

                # Use real tasks from story if available, otherwise generic.
                lines.append("**Tasks:**")
                if story.tasks:
                    max_tasks = 4
                    for task in story.tasks[:max_tasks]:
                        lines.append(f"- [ ] {task}")
                    remaining = len(story.tasks) - max_tasks
                    if remaining > 0:
                        lines.append(f"- ... and {remaining} more")
                else:
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
            # Use the suggestion engine to produce keyword-relevant story stubs.
            suggested = self._suggest_stories(config.title, config.goal)
            for i, story in enumerate(suggested, 1):
                story_id = f"{epic_num}.{i}"
                lines.append(f"### {story_id} -- {story.title}")
                lines.append("")
                lines.append("**Points:** TBD")
                lines.append("")
                lines.append("Describe what this story delivers...")
                lines.append("")
                lines.append("**Tasks:**")
                lines.append(f"- [ ] Implement {story.title.lower()}")
                lines.append("- [ ] Write unit tests")
                lines.append("- [ ] Update documentation")
                lines.append("")
                lines.append(f"**Definition of Done:** {story.title} is implemented, "
                             "tests pass, and documentation is updated.")
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
            tech_stack = enrichment.get("tech_stack")
            title = config.title.strip()
            if title and tech_stack:
                lines.append(
                    f"- Document architecture decisions for **{title}**. "
                    f"Key tech: **{tech_stack}**."
                )
            elif title:
                lines.append(
                    f"- Document architecture decisions for **{title}**..."
                )
            else:
                lines.append(
                    "- Document architecture decisions and key dependencies..."
                )

        module_summary = enrichment.get("module_summary")
        if module_summary:
            lines.append("")
            lines.append(f"**Project Structure:** {module_summary}")

        dependencies = enrichment.get("dependencies")
        if dependencies:
            lines.append("")
            lines.append(f"**Key Dependencies:** {', '.join(dependencies[:10])}")

        expert_guidance: list[dict[str, str]] = enrichment.get("expert_guidance", [])
        # Filter out low-quality expert guidance (Epic 18.3).
        rendered_guidance = self._filter_expert_guidance(expert_guidance)
        if rendered_guidance:
            lines.append("")
            lines.append("### Expert Recommendations")
            lines.append("")
            for item in rendered_guidance:
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
        elif config.title.strip():
            title = config.title.strip()
            # Derive boundary suggestions from title keywords.
            hints = _derive_non_goal_hints(title)
            if hints:
                lines.append(
                    f"- Define what is explicitly out of scope for "
                    f"**{title}**. Consider: {', '.join(hints)}"
                )
            else:
                lines.append(
                    f"- Define what is explicitly out of scope for **{title}**..."
                )
        else:
            lines.append(
                "- Define what is explicitly deferred to prevent scope creep..."
            )

        lines.extend(["", "<!-- docsmcp:end:non-goals -->", ""])
        return lines

    # -- minimal-only sections -----------------------------------------------

    def _render_definition_of_done(self, config: EpicConfig) -> list[str]:
        """Render a Definition of Done section (minimal style)."""
        lines = [
            "<!-- docsmcp:start:definition-of-done -->",
            "## Definition of Done",
            "",
            "- [ ] All acceptance criteria verified",
            "- [ ] All stories completed and tests passing",
            "- [ ] Documentation updated",
            "",
            "<!-- docsmcp:end:definition-of-done -->",
            "",
        ]
        return lines

    # -- comprehensive-only sections ----------------------------------------

    def _render_success_metrics(self, config: EpicConfig) -> list[str]:
        """Render the Success Metrics section (comprehensive only)."""
        lines = [
            "<!-- docsmcp:start:success-metrics -->",
            "## Success Metrics",
            "",
            "| Metric | Baseline | Target | Measurement |",
            "|--------|----------|--------|-------------|",
        ]

        if config.success_metrics:
            for metric in config.success_metrics:
                if "|" in metric:
                    # Pipe-delimited: "MTTR|4h|1h|PagerDuty"
                    parts = [p.strip() for p in metric.split("|")]
                    while len(parts) < 4:
                        parts.append("-")
                    lines.append(f"| {parts[0]} | {parts[1]} | {parts[2]} | {parts[3]} |")
                else:
                    lines.append(f"| {metric} | - | - | - |")
        else:
            # Derive suggestions from config.
            ac_count = len(config.acceptance_criteria)
            story_count = len(config.stories)
            if ac_count:
                lines.append(
                    f"| All {ac_count} acceptance criteria met "
                    f"| 0/{ac_count} | {ac_count}/{ac_count} | Checklist review |"
                )
            if story_count:
                lines.append(
                    f"| All {story_count} stories completed "
                    f"| 0/{story_count} | {story_count}/{story_count} | Sprint board |"
                )
            if not ac_count and not story_count:
                lines.append(
                    "| Define success metrics... | - | - | - |"
                )

        lines.extend(["", "<!-- docsmcp:end:success-metrics -->", ""])
        return lines

    def _render_stakeholders(self, config: EpicConfig) -> list[str]:
        """Render the Stakeholders section (comprehensive only).

        Omitted entirely when no stakeholders are provided.
        """
        if not config.stakeholders:
            return []

        lines = [
            "<!-- docsmcp:start:stakeholders -->",
            "## Stakeholders",
            "",
            "| Role | Person | Responsibility |",
            "|------|--------|----------------|",
        ]

        for stakeholder in config.stakeholders:
            if "|" in stakeholder:
                parts = [p.strip() for p in stakeholder.split("|")]
                while len(parts) < 3:
                    parts.append("-")
                lines.append(f"| {parts[0]} | {parts[1]} | {parts[2]} |")
            else:
                lines.append(f"| {stakeholder} | - | - |")

        lines.extend(["", "<!-- docsmcp:end:stakeholders -->", ""])
        return lines

    def _render_references(self, config: EpicConfig) -> list[str]:
        """Render the References section (comprehensive only).

        Omitted entirely when no references are provided.
        """
        if not config.references:
            return []

        lines = [
            "<!-- docsmcp:start:references -->",
            "## References",
            "",
        ]

        for ref in config.references:
            lines.append(f"- {ref}")

        lines.extend(["", "<!-- docsmcp:end:references -->", ""])
        return lines

    def _render_implementation_order(self, config: EpicConfig) -> list[str]:
        """Render the Implementation Order section (comprehensive only)."""
        lines = [
            "<!-- docsmcp:start:implementation-order -->",
            "## Implementation Order",
            "",
        ]

        if config.stories:
            epic_num = config.number
            for i, story in enumerate(config.stories, 1):
                story_id = f"{epic_num}.{i}"
                lines.append(f"{i}. Story {story_id}: {story.title}")
        else:
            lines.append("Define the recommended story sequencing and dependency graph...")

        lines.extend(["", "<!-- docsmcp:end:implementation-order -->", ""])
        return lines

    def _render_risk_assessment(
        self, config: EpicConfig, enrichment: dict[str, Any] | None = None,
    ) -> list[str]:
        """Render the Risk Assessment section (comprehensive only).

        Auto-classifies risk probability/impact from keywords and derives
        mitigations from expert advice when available.
        """
        from docs_mcp.generators.risk_classifier import RiskClassifier

        classifier = RiskClassifier()

        lines = [
            "<!-- docsmcp:start:risk-assessment -->",
            "## Risk Assessment",
            "",
            "| Risk | Probability | Impact | Mitigation |",
            "|---|---|---|---|",
        ]

        expert_guidance: list[dict[str, str]] = (enrichment or {}).get("expert_guidance", [])
        # Filter to risk-relevant experts.
        risk_domains = {"security", "performance", "devops"}
        risk_experts = {
            g["domain"]: g["advice"]
            for g in expert_guidance
            if g["domain"] in risk_domains and g.get("advice", "").strip()
        }

        if config.risks:
            for risk in config.risks:
                probability, impact, _score = classifier.classify(risk)
                # Try to find relevant expert advice for mitigation.
                mitigation = classifier.derive_mitigation(
                    risk, expert_advice=self._find_risk_expert_advice(risk, risk_experts),
                )
                lines.append(f"| {risk} | {probability} | {impact} | {mitigation} |")
        else:
            # Use the suggestion engine to produce keyword-relevant risk stubs.
            suggested_risks = self._suggest_risks(config.title, config.goal)
            if suggested_risks:
                for risk in suggested_risks:
                    probability, impact, _score = classifier.classify(risk)
                    mitigation = classifier.derive_mitigation(risk, expert_advice=None)
                    lines.append(f"| {risk} | {probability} | {impact} | {mitigation} |")
            else:
                lines.append(
                    "| No risks identified | - | - "
                    "| Consider adding risks during planning |"
                )

        # Add expert-identified risks from security/performance domains.
        rendered_experts = self._filter_expert_guidance(expert_guidance)
        risk_items = [g for g in rendered_experts if g["domain"] in risk_domains]
        if risk_items:
            lines.append("")
            lines.append("**Expert-Identified Risks:**")
            lines.append("")
            for item in risk_items:
                lines.append(f"- **{item['expert']}**: {item['advice']}")

        lines.extend(["", "<!-- docsmcp:end:risk-assessment -->", ""])
        return lines

    def _render_files_affected(self, config: EpicConfig) -> list[str]:
        """Render the Files Affected table (comprehensive only).

        Aggregates real file paths from story stubs when available.
        """
        lines = [
            "<!-- docsmcp:start:files-affected -->",
            "## Files Affected",
            "",
            "| File | Story | Action |",
            "|---|---|---|",
        ]

        epic_num = config.number

        # Collect file paths from story tasks.
        file_stories: dict[str, list[str]] = {}
        if config.stories:
            for i, story in enumerate(config.stories, 1):
                story_id = f"{epic_num}.{i}"
                for task in story.tasks:
                    # Extract file paths from task text (look for path-like patterns).
                    paths = re.findall(r"`([^`]+\.\w+)`", task)
                    for path in paths:
                        if path not in file_stories:
                            file_stories[path] = []
                        if story_id not in file_stories[path]:
                            file_stories[path].append(story_id)

        if file_stories:
            # Sort by directory then filename.
            sorted_files = sorted(file_stories.items())
            max_files = 20
            for file_path, story_ids in sorted_files[:max_files]:
                lines.append(
                    f"| `{file_path}` | {', '.join(story_ids)} | Modify |"
                )
            remaining = len(sorted_files) - max_files
            if remaining > 0:
                story_count = len(config.stories) if config.stories else 0
                lines.append("")
                lines.append(
                    f"*and {remaining} more files across {story_count} stories*"
                )
        else:
            lines.append(
                "| Files will be determined during story refinement "
                "| - | - |"
            )

        lines.extend(["", "<!-- docsmcp:end:files-affected -->", ""])
        return lines

    def _render_performance_targets(
        self,
        enrichment: dict[str, Any] | None = None,
        config: EpicConfig | None = None,
    ) -> list[str]:
        """Render the Performance Targets section (comprehensive only).

        Always renders at least a test coverage row.  When ``config`` is
        provided, additional rows are derived from EpicConfig signals:

        - AC count > 5  → acceptance criteria pass rate row
        - Files > 3     → quality gate score row
        - Stories > 3   → story completion rate row

        Expert-derived targets (when available via ``enrichment``) are
        rendered before the config-derived table and take precedence.
        """
        expert_guidance: list[dict[str, str]] = (enrichment or {}).get("expert_guidance", [])
        from docs_mcp.generators.expert_utils import parse_confidence

        perf_experts = [
            g for g in expert_guidance
            if g.get("domain") == "performance"
            and g.get("advice", "").strip()
            and parse_confidence(g.get("confidence", "0%")) >= 0.5
        ]

        # Derive config-signal targets: (metric, baseline, target, measurement)
        derived: list[tuple[str, str, str, str]] = [
            ("Test coverage", "baseline", ">= 80%", "pytest --cov"),
        ]
        if config is not None:
            if len(config.acceptance_criteria) > 5:
                derived.append(
                    ("Acceptance criteria pass rate", "0%", "100%", "CI pipeline"),
                )
            if len(config.files) > 3:
                derived.append(
                    ("Quality gate score", "N/A", ">= 70/100", "tapps_quality_gate"),
                )
            if len(config.stories) > 3:
                derived.append(
                    ("Story completion rate", "0%", "100%", "Sprint tracking"),
                )

        lines = [
            "<!-- docsmcp:start:performance-targets -->",
            "## Performance Targets",
            "",
        ]

        # Expert guidance rendered first (free-form advice takes precedence)
        for expert in perf_experts:
            lines.append(f"**{expert['expert']}:** {expert['advice']}")
            lines.append("")

        # Config-derived table (always present)
        lines.extend([
            "| Metric | Baseline | Target | Measurement |",
            "|--------|----------|--------|-------------|",
        ])
        for metric, baseline, target, measurement in derived:
            lines.append(f"| {metric} | {baseline} | {target} | {measurement} |")
        lines.append("")

        lines.extend(["<!-- docsmcp:end:performance-targets -->", ""])
        return lines

    # -- file hint renderers -------------------------------------------------

    def _render_file_hints(
        self,
        files: list[str],
        project_root: Path,
        config: EpicConfig,
    ) -> list[str]:
        """Render a Files Affected table with per-file analysis.

        For each file that exists, includes line count, recent git commits,
        and public symbols (for Python files). Also scans story descriptions
        for additional file paths not in the explicit list.
        """
        from pathlib import Path as _Path

        lines = [
            "<!-- docsmcp:start:files-affected -->",
            "## Files Affected",
            "",
            "| File | Lines | Recent Commits | Public Symbols |",
            "|------|-------|----------------|----------------|",
        ]

        # Collect explicit file paths
        all_paths: list[str] = [f.strip() for f in files if f.strip()]

        # Scan story descriptions for additional file references
        if config.stories:
            for story in config.stories:
                text = story.description
                for task in story.tasks:
                    text += " " + task
                # Match backtick-quoted paths and bare path-like strings
                found = re.findall(r"`([^`]+\.\w{1,5})`", text)
                for p in found:
                    if p not in all_paths:
                        all_paths.append(p)

        # Parallelize per-file analysis (git log + AST parsing) to avoid
        # sequential subprocess overhead, especially on Windows.
        from concurrent.futures import ThreadPoolExecutor

        resolvable: list[tuple[str, _Path]] = []
        for file_path in all_paths:
            resolved = _Path(project_root) / file_path
            if not resolved.is_file():
                lines.append(f"| `{file_path}` | *(not found)* | - | - |")
            else:
                resolvable.append((file_path, resolved))

        if resolvable:
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {
                    pool.submit(self._analyze_file, resolved, project_root): fp
                    for fp, resolved in resolvable
                }
                # Collect results keyed by display path
                results: dict[str, dict[str, str]] = {}
                for future in futures:
                    fp = futures[future]
                    results[fp] = future.result()

            # Maintain original order
            for fp, _resolved in resolvable:
                info = results[fp]
                lines.append(
                    f"| `{fp}` "
                    f"| {info['line_count']} "
                    f"| {info['commits_summary']} "
                    f"| {info['symbols_summary']} |"
                )

        lines.extend(["", "<!-- docsmcp:end:files-affected -->", ""])
        return lines

    @staticmethod
    def _analyze_file(
        file_path: Path,
        project_root: Path,
    ) -> dict[str, str]:
        """Analyze a single file for the file hints table.

        Returns dict with line_count, commits_summary, symbols_summary.
        """
        from pathlib import Path as _Path

        info: dict[str, str] = {
            "line_count": "-",
            "commits_summary": "-",
            "symbols_summary": "-",
        }

        # Line count
        try:
            text = _Path(file_path).read_text(encoding="utf-8", errors="replace")
            line_count = len(text.splitlines())
            info["line_count"] = str(line_count)
        except OSError:
            pass

        # Git log: last 5 commits touching this file
        try:
            rel = _Path(file_path).relative_to(project_root)
            result = subprocess.run(
                ["git", "log", "-5", "--oneline", "--", str(rel)],
                capture_output=True,
                text=True,
                cwd=str(project_root),
                timeout=10,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                commit_lines = result.stdout.strip().splitlines()
                # Show count + latest commit message
                latest = commit_lines[0]
                if len(latest) > _MAX_COMMIT_DISPLAY_LEN:
                    latest = latest[:_MAX_COMMIT_DISPLAY_LEN - 3] + "..."
                info["commits_summary"] = (
                    f"{len(commit_lines)} recent: {latest}"
                )
        except (subprocess.TimeoutExpired, OSError, ValueError):
            pass

        # Public symbols for Python files
        if str(file_path).endswith(".py"):
            try:
                source = _Path(file_path).read_text(
                    encoding="utf-8", errors="replace",
                )
                tree = ast.parse(source)
                funcs = 0
                classes = 0
                for node in ast.iter_child_nodes(tree):
                    if isinstance(
                        node, ast.FunctionDef | ast.AsyncFunctionDef,
                    ) and not node.name.startswith("_"):
                        funcs += 1
                    elif isinstance(
                        node, ast.ClassDef,
                    ) and not node.name.startswith("_"):
                        classes += 1
                parts: list[str] = []
                if classes:
                    parts.append(f"{classes} classes")
                if funcs:
                    parts.append(f"{funcs} functions")
                info["symbols_summary"] = ", ".join(parts) if parts else "0"
            except (SyntaxError, OSError):
                pass

        return info

    def _render_related_epics(
        self,
        files: list[str],
        project_root: Path,
    ) -> list[str]:
        """Scan existing epics for mentions of the same files.

        Looks in ``docs/planning/epics/`` for .md files that reference
        any of the given file paths.
        """
        from pathlib import Path as _Path

        epics_dir = _Path(project_root) / "docs" / "planning" / "epics"
        if not epics_dir.is_dir():
            return []

        file_set = {f.strip() for f in files if f.strip()}
        if not file_set:
            return []

        related: list[tuple[str, list[str]]] = []

        try:
            epic_files = sorted(epics_dir.glob("*.md"))
        except OSError:
            return []

        for epic_file in epic_files:
            try:
                content = epic_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            matched: list[str] = []
            for fp in file_set:
                # Check if file path appears in the epic content
                if fp in content:
                    matched.append(fp)

            if matched:
                related.append((epic_file.name, matched))

        if not related:
            return []

        lines = [
            "<!-- docsmcp:start:related-epics -->",
            "## Related Epics",
            "",
        ]

        for epic_name, matched_files in related:
            files_str = ", ".join(f"`{f}`" for f in sorted(matched_files))
            lines.append(f"- **{epic_name}** -- references {files_str}")

        lines.extend(["", "<!-- docsmcp:end:related-epics -->", ""])
        return lines

    # -- auto-populate from analyzers ----------------------------------------

    _AUTO_POPULATE_TIMEOUT_S: ClassVar[float] = 15.0

    def _auto_populate(
        self, project_root: Path, config: EpicConfig | None = None,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        """Gather enrichment data from project analyzers and domain experts.

        Returns a dict with optional keys: tech_stack, module_summary,
        dependencies, git_summary, expert_guidance. Each key is only present
        when the corresponding analyzer/expert succeeds.

        A wall-clock budget of 15 s is enforced.  If a step exhausts the
        budget the remaining steps are skipped and partial results returned.

        Second return value is per-step timings in milliseconds plus
        ``auto_populate_ms`` (wall-clock for the full populate phase).
        """
        enrichment: dict[str, Any] = {}
        timings: dict[str, int] = {}
        t_wall = time.perf_counter()
        budget = self._AUTO_POPULATE_TIMEOUT_S

        def _remaining() -> float:
            return budget - (time.perf_counter() - t_wall)

        steps: list[tuple[str, Any, list[Any]]] = [
            ("metadata_ms", self._enrich_metadata, [project_root, enrichment]),
            ("module_map_ms", self._enrich_module_map, [project_root, enrichment]),
            ("git_ms", self._enrich_git, [project_root, enrichment]),
        ]

        for key, fn, args in steps:
            if _remaining() <= 0:
                logger.warning("auto_populate_budget_exceeded", skipped=key)
                timings[key] = 0
                continue
            t0 = time.perf_counter()
            fn(*args)
            timings[key] = int((time.perf_counter() - t0) * 1000)

        if config and _remaining() > 0:
            t0 = time.perf_counter()
            self._enrich_experts(config, enrichment)
            timings["experts_ms"] = int((time.perf_counter() - t0) * 1000)
        elif config:
            logger.warning("auto_populate_budget_exceeded", skipped="experts_ms")
            timings["experts_ms"] = 0

        timings["auto_populate_ms"] = int((time.perf_counter() - t_wall) * 1000)
        return enrichment, timings

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
        """Enrich with module structure from ModuleMapAnalyzer.

        Uses a shallow depth (3) to avoid hanging on large projects.
        """
        try:
            from docs_mcp.analyzers.module_map import ModuleMapAnalyzer

            analyzer = ModuleMapAnalyzer()
            module_map = analyzer.analyze(project_root, depth=3)
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
        """No-op — expert system removed (EPIC-94).

        Previously enriched epics with TappsMCP domain expert guidance.
        Retained as a no-op to preserve the enrichment pipeline interface.
        """

    # -- expert filtering (Epic 18.3) ---------------------------------------

    @classmethod
    def _filter_expert_guidance(
        cls,
        guidance: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        """Filter expert guidance based on confidence and content quality."""
        from docs_mcp.generators.expert_utils import filter_expert_guidance

        return filter_expert_guidance(guidance)

    @staticmethod
    def _find_risk_expert_advice(
        risk_text: str,
        risk_experts: dict[str, str],
    ) -> str | None:
        """Find relevant expert advice for a specific risk."""
        text_lower = risk_text.lower()
        # Map risk keywords to expert domains.
        if any(kw in text_lower for kw in ("security", "auth", "encrypt", "credential")):
            return risk_experts.get("security")
        if any(kw in text_lower for kw in ("performance", "latency", "throughput", "scale")):
            return risk_experts.get("performance")
        if any(kw in text_lower for kw in ("deploy", "ci", "pipeline", "infrastructure")):
            return risk_experts.get("devops")
        return None

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
    def parse_stories_json(stories_json: str | list[Any]) -> list[EpicStoryStub]:
        """Parse a JSON string (or pre-parsed list) into EpicStoryStub objects.

        Accepts a JSON array of objects with keys: title, points, description,
        tasks, ac_count. Also accepts an already-parsed list (from MCP clients
        that may send typed values instead of JSON strings).

        Args:
            stories_json: JSON string or pre-parsed list of story dicts.

        Returns:
            List of EpicStoryStub objects.

        Raises:
            ValueError: If the JSON is malformed or not a list.
        """
        # Handle pre-parsed list (MCP clients may send typed values)
        if isinstance(stories_json, list):
            raw = stories_json
        else:
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
                tasks_raw = item.get("tasks", [])
                tasks = [str(t) for t in tasks_raw] if isinstance(tasks_raw, list) else []
                stories.append(
                    EpicStoryStub(
                        title=str(item.get("title", "Untitled")),
                        points=int(item.get("points", 0)),
                        description=str(item.get("description", "")),
                        tasks=tasks,
                        ac_count=int(item.get("ac_count", 0)),
                    )
                )
        return stories
