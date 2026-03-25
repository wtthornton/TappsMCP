"""User story document generation with acceptance criteria and task breakdown."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, ClassVar

import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


def markdown_relative_link(target: str, from_file: str) -> str:
    """Return ``target`` as a path relative to ``from_file``'s directory.

    Used so epic links in generated story files resolve correctly when the
    story lives in a subdirectory (e.g. ``EPIC-80/story-80.1.md`` → ``../EPIC.md``).
    """
    t = target.strip()
    f = from_file.strip()
    if not t or not f:
        return target
    if t.startswith(("http://", "https://", "mailto:")):
        return t
    try:
        return os.path.relpath(t, Path(f).parent).replace("\\", "/")
    except ValueError:
        return t.replace("\\", "/")


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
    purpose_and_intent: str = ""  # Required per design doc §2 (Epic 75.3)
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
    inherit_context: bool = True
    epic_path: str = ""


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

    # Keyword-to-task patterns for the task suggestion engine (Story 92.4).
    # Multiple keywords that share the same list object are deduplicated via id().
    # First matching keyword group wins.
    _model_tasks: ClassVar[list[str]] = [
        "Define data model fields and relationships",
        "Write migration script",
        "Add model validation",
    ]
    _api_tasks: ClassVar[list[str]] = [
        "Define request/response schema",
        "Implement endpoint handler",
        "Add input validation",
        "Add error responses",
    ]
    _test_tasks: ClassVar[list[str]] = [
        "Write unit tests for happy path",
        "Write edge case tests",
        "Add integration test",
    ]
    _ui_tasks: ClassVar[list[str]] = [
        "Create component scaffold",
        "Add form validation",
        "Add styling/CSS",
        "Add accessibility attributes",
    ]
    _validation_tasks: ClassVar[list[str]] = [
        "Define validation rules",
        "Implement validation logic",
        "Add validation error messages",
    ]
    _auth_tasks: ClassVar[list[str]] = [
        "Implement auth flow",
        "Add token generation/validation",
        "Add session management",
    ]
    _TASK_PATTERNS: ClassVar[dict[str, list[str]]] = {
        "model": _model_tasks,
        "schema": _model_tasks,
        "database": _model_tasks,
        "endpoint": _api_tasks,
        "api": _api_tasks,
        "route": _api_tasks,
        "test": _test_tasks,
        "coverage": _test_tasks,
        "ui": _ui_tasks,
        "component": _ui_tasks,
        "form": _ui_tasks,
        "validate": _validation_tasks,
        "validation": _validation_tasks,
        "auth": _auth_tasks,
        "login": _auth_tasks,
        "token": _auth_tasks,
    }

    @classmethod
    def _suggest_tasks(cls, config: StoryConfig) -> list[StoryTask]:
        """Suggest implementation tasks from title/description keywords.

        Scans the title and description for known keyword patterns and returns
        a deduplicated list of relevant task stubs. Falls back to a generic
        3-task pattern when no keywords match but title is non-empty. Returns
        an empty list when the title is empty/whitespace (preserve existing
        "Define implementation tasks..." placeholder).

        When ``config.files`` is provided, the first file path is associated
        with the first task stub.

        Returns:
            A list of :class:`StoryTask` with inferred descriptions.
        """
        title = config.title.strip()
        if not title:
            return []

        combined = (title + " " + (config.description or "")).lower()
        tokens = set(re.split(r"[\s\-_/]+", combined))

        task_descriptions: list[str] = []
        seen_patterns: set[int] = set()

        for keyword, task_list in cls._TASK_PATTERNS.items():
            pattern_id = id(task_list)
            if pattern_id in seen_patterns:
                continue
            if keyword in tokens or keyword in combined:
                seen_patterns.add(pattern_id)
                task_descriptions = task_list
                break  # First matching keyword group wins

        if not task_descriptions:
            # Generic fallback: title-derived implementation task
            task_descriptions = [
                f"Implement {title.lower()}",
                "Write unit tests",
                "Update documentation",
            ]

        # Associate first file path with the first task when files are provided.
        first_file = config.files[0] if config.files else ""
        tasks: list[StoryTask] = []
        for i, description in enumerate(task_descriptions):
            file_path = first_file if i == 0 and first_file else ""
            tasks.append(StoryTask(description=description, file_path=file_path))

        return tasks

    @staticmethod
    def _infer_story_defaults(config: StoryConfig) -> StoryConfig:
        """Fill empty fields with title-derived defaults for quick-start mode.

        Explicit parameters are never overwritten -- only empty/default fields
        are populated.

        Defaults applied when fields are empty/zero:
        - ``role`` → "developer"
        - ``want`` → "to {title.lower()}"
        - ``so_that`` → "the feature is delivered and tested"
        - ``points`` → 3
        - ``size`` → "M"
        - ``tasks`` → 3 stubs derived from title
        - ``acceptance_criteria`` → 3 items derived from title
        """
        title = config.title.strip()

        updates: dict[str, Any] = {}

        if not config.role:
            updates["role"] = "developer"

        if not config.want:
            updates["want"] = f"to {title.lower()}" if title else "to implement the feature"

        if not config.so_that:
            updates["so_that"] = "the feature is delivered and tested"

        if not config.points:
            updates["points"] = 3

        if not config.size:
            updates["size"] = "M"

        if not config.tasks:
            task_title = title.lower() if title else "the feature"
            updates["tasks"] = [
                StoryTask(description=f"Implement {task_title}"),
                StoryTask(description="Write unit tests"),
                StoryTask(description="Update documentation"),
            ]

        if not config.acceptance_criteria:
            ac_title = title if title else "Feature"
            updates["acceptance_criteria"] = [
                f"{ac_title} works as specified",
                "Unit tests pass",
                "Docs updated",
            ]

        if updates:
            return config.model_copy(update=updates)
        return config

    def generate(
        self,
        config: StoryConfig,
        *,
        project_root: Path | None = None,
        auto_populate: bool = False,
        quick_start: bool = False,
        output_path: str = "",
    ) -> str:
        """Generate a user story document.

        Args:
            config: Story configuration with title, tasks, criteria, etc.
            project_root: Project root for auto-populate analyzers.
            auto_populate: When True, enrich sections from project analyzers.
            quick_start: When True, infer defaults from the title alone --
                role, want, so_that, points, size, tasks, and acceptance
                criteria are filled in automatically. Explicit parameters
                always override quick-start defaults.
            output_path: When set (relative to project root), ``epic_path`` in
                config is rewritten as a markdown link relative to this file.

        Returns:
            Rendered markdown content with docsmcp markers.
        """
        if quick_start:
            config = self._infer_story_defaults(config)

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

        render_config = config
        if output_path.strip() and config.epic_path.strip():
            render_config = config.model_copy(
                update={
                    "epic_path": markdown_relative_link(
                        config.epic_path.strip(),
                        output_path.strip(),
                    ),
                },
            )

        lines: list[str] = []

        lines.extend(self._render_title(config))
        lines.extend(self._render_user_story_statement(config))
        lines.extend(self._render_sizing(config))
        lines.extend(self._render_purpose_and_intent(config))
        lines.extend(self._render_description(render_config, enrichment))
        lines.extend(self._render_files(config))
        lines.extend(self._render_tasks(config))
        lines.extend(self._render_acceptance_criteria(config))
        lines.extend(self._render_definition_of_done(render_config, enrichment))

        if style == "comprehensive":
            lines.extend(self._render_test_cases(config))
            lines.extend(self._render_technical_notes(config, enrichment))
            lines.extend(self._render_dependencies(config))
            lines.extend(self._render_invest_checklist(config))

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
                f"See [{label}]({config.epic_path}) for project context "
                "and shared definitions."
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

        for file_path in config.files:
            lines.append(f"- `{file_path}`")

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
            title = config.title.strip()
            if title:
                lines.append(f"- [ ] {title} works as specified")
            else:
                lines.append("- [ ] Feature works as specified")
            lines.append("- [ ] Unit tests added with adequate coverage")
            lines.append("- [ ] Documentation updated")

        lines.append("")
        return lines

    @staticmethod
    def _derive_given(role: str, ac_text: str) -> str:
        """Derive a Gherkin Given clause from the story role.

        Returns the derived clause text (without the ``Given`` keyword), or an
        empty string when the context is too ambiguous to produce useful output.
        Falls back to bracket placeholder in :meth:`_render_gherkin_criteria`.
        """
        role = role.strip()
        if not role:
            return ""
        return f"a {role} is ready to perform the action"

    @staticmethod
    def _derive_when(role: str, want: str, ac_text: str) -> str:
        """Derive a Gherkin When clause from want field or AC verb phrase.

        Priority: (1) ``want`` field, (2) first verb phrase extracted from
        ``ac_text``. Returns an empty string when neither is available.
        Falls back to bracket placeholder in :meth:`_render_gherkin_criteria`.
        """
        role = role.strip()
        want = want.strip()
        actor = f"the {role}" if role else "the user"

        if want:
            # Strip leading "to " so "to validate login" → "validate login".
            action = want[3:] if want.lower().startswith("to ") else want
            return f"{actor} {action}"

        ac_text = ac_text.strip()
        if ac_text:
            # Extract first verb + remainder as action phrase.
            words = ac_text.split()
            if words:
                verb = words[0].lower()
                rest = " ".join(words[1:]).lower() if len(words) > 1 else ""
                action = f"{verb} {rest}".strip() if rest else verb
                return f"{actor} {action}"

        return ""

    @staticmethod
    def _derive_then(ac_text: str, so_that: str) -> str:
        """Derive a Gherkin Then clause from AC text or so_that field.

        Returns the AC text with ``" successfully"`` appended when available.
        Falls back to ``so_that`` if AC is empty. Returns an empty string when
        both are empty (bracket placeholder used in caller).
        """
        ac_text = ac_text.strip()
        if ac_text:
            clean = ac_text.rstrip(".!?")
            return f"{clean} successfully"
        so_that = so_that.strip()
        if so_that:
            return so_that
        return ""

    def _render_gherkin_criteria(self, config: StoryConfig) -> list[str]:
        """Render acceptance criteria in Gherkin Given/When/Then format.

        When role/want context is available, derives meaningful Given/When/Then
        clauses from the story fields. Falls back to bracket placeholders when
        derivation produces empty strings.
        """
        lines: list[str] = []

        if config.acceptance_criteria:
            for criterion in config.acceptance_criteria:
                slug = self._slugify(criterion)
                given = self._derive_given(config.role, criterion)
                when = self._derive_when(config.role, config.want, criterion)
                then = self._derive_then(criterion, config.so_that)

                given_line = given if given else "[describe the precondition]"
                when_line = (
                    when if when
                    else f"[describe the action that triggers: {criterion.lower()}]"
                )
                then_line = then if then else "[describe the expected observable outcome]"

                lines.append(f"### AC: {criterion}")
                lines.append("")
                lines.append("```gherkin")
                lines.append(f"Feature: {slug}")
                lines.append(f"  Scenario: {criterion}")
                lines.append(f"    Given {given_line}")
                lines.append(f"    When {when_line}")
                lines.append(f"    Then {then_line}")
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
            lines.append(
                f"Definition of Done per [{label}]({config.epic_path})."
            )
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
            for note in config.technical_notes:
                lines.append(f"- {note}")
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
            for item in rendered_guidance:
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
            lines.append(
                f"- [{checked}] **{letter}**{name[1:]} -- {description}"
            )

        lines.extend(["", "<!-- docsmcp:end:invest -->", ""])
        return lines

    # -- auto-populate from analyzers ----------------------------------------

    _AUTO_POPULATE_TIMEOUT_S: ClassVar[float] = 15.0

    def _auto_populate(
        self, project_root: Path, config: StoryConfig | None = None,
    ) -> dict[str, Any]:
        """Gather enrichment data from project analyzers and domain experts.

        Returns a dict with optional keys: tech_stack, module_summary,
        expert_guidance. Each key is only present when the corresponding
        analyzer/expert succeeds.

        A wall-clock budget of 15 s is enforced.  If a step exhausts the
        budget the remaining steps are skipped and partial results returned.
        """
        enrichment: dict[str, Any] = {}
        t_wall = time.perf_counter()
        budget = self._AUTO_POPULATE_TIMEOUT_S

        def _remaining() -> float:
            return budget - (time.perf_counter() - t_wall)

        steps: list[tuple[str, Any, list[Any]]] = [
            ("metadata", self._enrich_metadata, [project_root, enrichment]),
            ("module_map", self._enrich_module_map, [project_root, enrichment]),
        ]

        for key, fn, args in steps:
            if _remaining() <= 0:
                logger.warning("story_auto_populate_budget_exceeded", skipped=key)
                continue
            fn(*args)

        if config and _remaining() > 0:
            self._enrich_experts(config, enrichment)
        elif config:
            logger.warning("story_auto_populate_budget_exceeded", skipped="experts")

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
        """Enrich with guidance from TappsMCP domain experts.

        Runs consultations in parallel using a thread pool to avoid
        sequential latency across all 4 domains.
        """
        try:
            from tapps_core.experts.engine import consult_expert
        except Exception:
            logger.debug("story_expert_import_failed", exc_info=True)
            return

        from concurrent.futures import ThreadPoolExecutor, as_completed

        context = config.title
        if config.description:
            context = f"{config.title} - {config.description}"

        def _consult_one(domain: str, question_template: str) -> dict[str, str] | None:
            try:
                question = question_template.format(context=context)
                result = consult_expert(
                    question, domain=domain, max_chunks=3, max_context_length=1500,
                )
                if result.confidence >= 0.3 and result.answer:
                    from docs_mcp.generators.expert_utils import extract_expert_advice

                    advice = extract_expert_advice(result.answer)
                    if advice:
                        return {
                            "domain": result.domain,
                            "expert": result.expert_name,
                            "advice": advice,
                            "confidence": f"{result.confidence:.0%}",
                        }
            except Exception:
                logger.debug("story_expert_consult_failed", domain=domain, exc_info=True)
            return None

        guidance: list[dict[str, str]] = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(_consult_one, domain, tmpl): domain
                for domain, tmpl in StoryGenerator._EXPERT_DOMAINS
            }
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    guidance.append(result)

        if guidance:
            from docs_mcp.generators.expert_utils import filter_expert_guidance

            enrichment["expert_guidance"] = filter_expert_guidance(guidance)

    # -- helpers -----------------------------------------------------------

    _STOPWORDS: ClassVar[frozenset[str]] = frozenset({
        "the", "and", "is", "are", "should", "that", "when", "then",
        "given", "a", "an", "of", "in", "to", "for", "with", "be",
        "has", "have", "it", "its",
    })

    _MAX_TEST_NAME_LEN: ClassVar[int] = 80

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert text to a URL-friendly slug."""
        slug = text.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = re.sub(r"-+", "-", slug)
        return slug.strip("-")

    @classmethod
    def generate_test_name(cls, criterion: str, *, index: int = 0) -> str:
        """Generate a valid Python test function name from an acceptance criterion.

        The result follows the pattern ``test_<verb>_<noun>_<qualifier>``
        (or ``test_ac<N>_<verb>_<noun>_<qualifier>`` when *index* > 0).
        It is guaranteed to:

        * be at most 80 characters,
        * never truncate mid-word,
        * be a valid Python identifier (``test_`` prefix, only ``[a-z0-9_]``),
        * have common stopwords removed.

        Args:
            criterion: Acceptance criterion text (e.g. "Validation rejects
                empty fields when the form is submitted").
            index: 1-based AC number.  When > 0, the name is prefixed with
                ``ac<index>_`` (e.g. ``test_ac1_validation_rejects``).

        Returns:
            A clean test function name such as ``test_validation_rejects_empty_fields``.
        """
        if not criterion or not criterion.strip():
            if index > 0:
                return f"test_ac{index}_story_acceptance"
            return "test_story_acceptance"

        # Lowercase and strip non-alphanumeric (keep spaces for splitting).
        text = criterion.lower().strip()
        text = re.sub(r"[^a-z0-9\s]", "", text)

        # Split into words, remove stopwords.
        words = [w for w in text.split() if w and w not in cls._STOPWORDS]

        if not words:
            if index > 0:
                return f"test_ac{index}_story_acceptance"
            return "test_story_acceptance"

        # Build prefix.
        prefix = f"test_ac{index}_" if index > 0 else "test_"

        # Assemble words into the name, respecting max length.
        parts: list[str] = []
        current_len = len(prefix)
        for word in words:
            # +1 for the underscore separator between words.
            needed = len(word) + (1 if parts else 0)
            if current_len + needed > cls._MAX_TEST_NAME_LEN:
                break
            parts.append(word)
            current_len += needed

        if not parts:
            # First word alone exceeds limit -- take it truncated to fit.
            available = cls._MAX_TEST_NAME_LEN - len(prefix)
            if available > 0:
                parts.append(words[0][:available])
            else:
                return prefix.rstrip("_")

        name = prefix + "_".join(parts)

        # Final safety: ensure valid Python identifier.
        if not name.isidentifier():
            name = re.sub(r"[^a-z0-9_]", "", name)
            if not name.startswith("test_"):
                name = "test_" + name

        return name
