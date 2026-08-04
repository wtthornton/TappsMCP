"""Human-audience story sections (the full product-review shape).

Title, user-story statement, sizing, description, tasks, acceptance
criteria (checkbox and Gherkin), definition of done, test cases,
technical notes, dependencies, and the INVEST checklist. Split out of
``stories.py`` under TAP-5609.
"""

from __future__ import annotations

from typing import Any

import structlog

from docs_mcp.generators.story_criteria import CriteriaSectionsMixin
from docs_mcp.generators.story_models import StoryConfig

logger = structlog.get_logger(__name__)


class HumanSectionsMixin(CriteriaSectionsMixin):
    """Human-audience story sections (the full product-review shape)."""

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
            lines.append("> **As a** [role], **I want** [capability], **so that** [benefit]")
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

    def _render_purpose_and_intent(self, config: StoryConfig) -> list[str]:
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
                "This story exists so that the acceptance criteria below are met "
                "and the feature is delivered. Refine this paragraph to state "
                "why this story exists and what it enables."
            )
        lines.extend(["", "<!-- docsmcp:end:purpose-intent -->", ""])
        return lines

    def _render_description(
        self,
        config: StoryConfig,
        enrichment: dict[str, Any],
    ) -> list[str]:
        """Render the Description section.

        When ``inherit_context=True``, project metadata (Tech Stack, Project
        Structure) is suppressed since it belongs in the parent epic.
        """
        lines = [
            "<!-- docsmcp:start:description -->",
            "## Description",
            "",
        ]

        if config.description:
            lines.append(config.description)
        else:
            title = config.title.strip()
            if title and config.role and config.want:
                lines.append(
                    f"Describe how **{title}** will enable **{config.role}** "
                    f"to **{config.want}**..."
                )
            elif title:
                lines.append(f"Describe what **{title}** delivers and any important context...")
            else:
                lines.append("Describe what this story delivers and any important context...")

        # Epic cross-reference when inheriting context.
        if config.inherit_context and config.epic_path:
            lines.append("")
            epic_num = config.epic_number
            label = f"Epic {epic_num}" if epic_num else "parent epic"
            lines.append(
                f"See [{label}]({config.epic_path}) for project context and shared definitions."
            )

        # Only include project metadata when NOT inheriting from epic.
        if not config.inherit_context:
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

        lines.extend(f"- `{file_path}`" for file_path in config.files)

        lines.extend(["", "<!-- docsmcp:end:files -->", ""])
        return lines

    def _render_tasks(self, config: StoryConfig) -> list[str]:
        """Render the Tasks section.

        When ``config.tasks`` is empty, falls back to :meth:`_suggest_tasks`
        which maps title/description keywords to common implementation tasks.
        When the title is also empty, renders a generic placeholder.
        """
        lines = [
            "<!-- docsmcp:start:tasks -->",
            "## Tasks",
            "",
        ]

        if config.tasks:
            tasks_to_render = config.tasks
        else:
            suggested = self._suggest_tasks(config)
            if suggested:
                tasks_to_render = suggested
            else:
                # Empty title: show generic placeholder
                lines.append("- [ ] Define implementation tasks...")
                lines.extend(["", "<!-- docsmcp:end:tasks -->", ""])
                return lines

        for task in tasks_to_render:
            if task.file_path:
                lines.append(f"- [ ] {task.description} (`{task.file_path}`)")
            else:
                lines.append(f"- [ ] {task.description}")

        lines.extend(["", "<!-- docsmcp:end:tasks -->", ""])
        return lines

    def _render_definition_of_done(
        self,
        config: StoryConfig,
        enrichment: dict[str, Any] | None = None,
    ) -> list[str]:
        """Render the Definition of Done section.

        When ``inherit_context=True`` and ``epic_path`` is set, renders a
        reference to the epic-level DoD instead of repeating the checklist.
        """
        lines = [
            "<!-- docsmcp:start:definition-of-done -->",
            "## Definition of Done",
            "",
        ]

        # When inheriting from epic, reference the epic DoD instead of repeating.
        if config.inherit_context and config.epic_path:
            epic_num = config.epic_number
            label = f"Epic {epic_num}" if epic_num else "parent epic"
            lines.append(f"Definition of Done per [{label}]({config.epic_path}).")
            lines.extend(["", "<!-- docsmcp:end:definition-of-done -->", ""])
            return lines

        if config.tasks:
            lines.append("- [ ] All tasks completed")
        title = config.title.strip()
        if title:
            lines.append(f"- [ ] {title} code reviewed and approved")
        else:
            lines.append("- [ ] Code reviewed and approved")
        lines.append("- [ ] Tests passing (unit + integration)")
        lines.append("- [ ] Documentation updated")
        lines.append("- [ ] No regressions introduced")

        # Add expert-recommended DoD items from security/testing experts.
        expert_guidance: list[dict[str, str]] = (enrichment or {}).get(
            "expert_guidance",
            [],
        )
        security_items = [g for g in expert_guidance if g["domain"] == "security"]
        testing_items = [g for g in expert_guidance if g["domain"] == "testing"]
        if security_items:
            lines.append("- [ ] Security review completed")
        if testing_items:
            lines.append("- [ ] Test coverage meets quality gate")

        lines.extend(["", "<!-- docsmcp:end:definition-of-done -->", ""])
        return lines

    def _render_test_cases(self, config: StoryConfig) -> list[str]:
        """Render the Test Cases section (comprehensive only).

        When explicit ``test_cases`` are provided they are rendered as-is.
        Otherwise, test case stubs are auto-generated from acceptance criteria
        using :meth:`generate_test_name`.  When both are empty the section is
        omitted entirely (Epic 18.2).
        """
        # Omit section entirely when no test data exists.
        if not config.test_cases and not config.acceptance_criteria:
            return []

        lines = [
            "<!-- docsmcp:start:test-cases -->",
            "## Test Cases",
            "",
        ]

        if config.test_cases:
            for i, test in enumerate(config.test_cases, 1):
                lines.append(f"{i}. {test}")
        else:
            for i, ac in enumerate(config.acceptance_criteria, 1):
                name = self.generate_test_name(ac, index=i)
                lines.append(f"{i}. `{name}` -- {ac}")

        lines.extend(["", "<!-- docsmcp:end:test-cases -->", ""])
        return lines

    def _render_technical_notes(
        self,
        config: StoryConfig,
        enrichment: dict[str, Any],
    ) -> list[str]:
        """Render the Technical Notes section (comprehensive only).

        When ``inherit_context=True``, project structure metadata is suppressed.
        Expert guidance is filtered by confidence (Epic 18.3).
        """
        lines = [
            "<!-- docsmcp:start:technical-notes -->",
            "## Technical Notes",
            "",
        ]

        if config.technical_notes:
            lines.extend(f"- {note}" for note in config.technical_notes)
        else:
            lines.append("- Document implementation hints, API contracts, data formats...")

        # Only include project structure when NOT inheriting from epic.
        if not config.inherit_context:
            module_summary = enrichment.get("module_summary")
            if module_summary:
                lines.append("")
                lines.append(f"**Project Structure:** {module_summary}")

        expert_guidance: list[dict[str, str]] = enrichment.get("expert_guidance", [])
        # Filter by confidence and content quality (Epic 18.3).
        from docs_mcp.generators.expert_utils import filter_expert_guidance

        rendered_guidance = filter_expert_guidance(expert_guidance)
        if rendered_guidance:
            lines.append("")
            lines.append("### Expert Recommendations")
            lines.append("")
            lines.extend(
                f"- **{item['expert']}** ({item['confidence']}): {item['advice']}"
                for item in rendered_guidance
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
            lines.extend(f"- {dep}" for dep in config.dependencies)
        else:
            lines.append("- List stories or external dependencies that must complete first...")

        lines.extend(["", "<!-- docsmcp:end:dependencies -->", ""])
        return lines

    def _render_invest_checklist(self, config: StoryConfig | None = None) -> list[str]:
        """Render the INVEST checklist with auto-assessment (comprehensive only).

        When *config* is provided, auto-checks items based on story signals
        using :func:`~docs_mcp.generators.invest_assessor.assess_invest`.
        """
        from docs_mcp.generators.invest_assessor import assess_invest

        assessment = assess_invest(config) if config else {}

        items = [
            ("I", "Independent", "Can be developed and delivered independently"),
            ("N", "Negotiable", "Details can be refined during implementation"),
            ("V", "Valuable", "Delivers value to a user or the system"),
            ("E", "Estimable", "Team can estimate the effort"),
            ("S", "Small", "Completable within one sprint/iteration"),
            ("T", "Testable", "Has clear criteria to verify completion"),
        ]

        lines = [
            "<!-- docsmcp:start:invest -->",
            "## INVEST Checklist",
            "",
        ]

        for letter, name, description in items:
            checked = "x" if assessment.get(name, False) else " "
            lines.append(f"- [{checked}] **{letter}**{name[1:]} -- {description}")

        lines.extend(["", "<!-- docsmcp:end:invest -->", ""])
        return lines
