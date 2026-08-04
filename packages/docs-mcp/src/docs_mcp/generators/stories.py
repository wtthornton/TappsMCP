"""User story document generation with acceptance criteria and task breakdown.

Split under TAP-5609 — ``StoryGenerator`` is now a composition over three
section mixins and a shared base:

* :mod:`docs_mcp.generators.story_models` — ``StoryTask`` / ``StoryConfig``.
* :mod:`docs_mcp.generators.story_base` — class-level config and the
  helpers the mixins share.
* :mod:`docs_mcp.generators.story_sections_agent` — the agent template.
* :mod:`docs_mcp.generators.story_sections_human` — the human template.
* :mod:`docs_mcp.generators.story_enrichment` — auto-population.

``markdown_relative_link``, ``StoryTask``, and ``StoryConfig`` are
re-exported here so existing imports keep resolving.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from docs_mcp.generators.story_enrichment import EnrichmentMixin
from docs_mcp.generators.story_models import StoryConfig as StoryConfig
from docs_mcp.generators.story_models import StoryTask as StoryTask
from docs_mcp.generators.story_models import (
    markdown_relative_link as markdown_relative_link,
)
from docs_mcp.generators.story_sections_agent import AgentSectionsMixin
from docs_mcp.generators.story_sections_human import HumanSectionsMixin

logger = structlog.get_logger(__name__)


class StoryGenerator(AgentSectionsMixin, HumanSectionsMixin, EnrichmentMixin):
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
            ac_title = title or "Feature"
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

        audience = config.audience if config.audience in self.VALID_AUDIENCES else "agent"
        if audience != config.audience:
            logger.warning(
                "invalid_audience_falling_back",
                audience=config.audience,
                fallback="agent",
            )

        # STORY-104.1 / TAP-5498: agent audience emits Linear templates.
        if audience == "agent":
            kind = (
                config.issue_kind
                if config.issue_kind in self.VALID_ISSUE_KINDS
                else "implementable"
            )
            if kind == "decision":
                return "\n".join(self._render_decision_template(config))
            if kind == "map-parent":
                return "\n".join(self._render_map_parent_template(config))
            return "\n".join(self._render_agent_template(config))

        style = config.style if config.style in self.VALID_STYLES else "standard"

        if style != config.style:
            logger.warning(
                "invalid_style_falling_back",
                style=config.style,
                fallback="standard",
            )

        enrichment = (
            self._auto_populate(project_root, config) if auto_populate and project_root else {}
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
