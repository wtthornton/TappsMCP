"""Agent-audience story sections.

Renders and validates the shape locked in ``docs/linear/AGENT_ISSUES.md``:
the 5-section implementable template, plus the decision and map-parent
bodies from TAP-5498. Split out of ``stories.py`` under TAP-5609.
"""

from __future__ import annotations

import structlog

from docs_mcp.generators.story_base import StoryGeneratorBase
from docs_mcp.generators.story_models import StoryConfig

logger = structlog.get_logger(__name__)


class AgentSectionsMixin(StoryGeneratorBase):
    """Agent-audience story sections (implementable, decision, map-parent)."""

    def _render_decision_template(self, config: StoryConfig) -> list[str]:
        """Render a decision ticket (TAP-5498): Question body, no fake AC."""
        self._validate_decision_config(config)
        question = (config.question or config.purpose_and_intent or config.description).strip()
        lines: list[str] = [f"# {config.title}", ""]
        lines.extend(["## Question", "", question, ""])
        why = (config.purpose_and_intent or config.description).strip()
        if why and why != question:
            lines.extend(["## Why", "", why, ""])
        lines.extend(self._render_agent_refs(config))
        return lines

    def _validate_decision_config(self, config: StoryConfig) -> None:
        """Raise ``ValueError`` if a decision ticket lacks a title or question."""
        errors: list[str] = []
        if not config.title.strip():
            errors.append("title is empty")
        elif len(config.title) > self._AGENT_TITLE_MAX:
            errors.append(f"title is {len(config.title)} chars (limit {self._AGENT_TITLE_MAX})")
        question = (config.question or config.purpose_and_intent or config.description).strip()
        if not question:
            errors.append("question/purpose_and_intent/description must provide ## Question body")
        if errors:
            joined = "; ".join(errors)
            raise ValueError(
                "audience='agent' issue_kind='decision' requires: "
                f"{joined}. Pass issue_kind='implementable' for the 5-section template."
            )

    def _render_map_parent_template(self, config: StoryConfig) -> list[str]:
        """Render a wayfind map parent body (TAP-5498)."""
        self._validate_map_parent_config(config)
        destination = (config.destination or config.purpose_and_intent or config.want).strip()
        lines: list[str] = [f"# {config.title}", ""]
        lines.extend(["## Destination", "", destination, ""])
        notes = (config.notes or config.description).strip()
        lines.extend(["## Notes", "", notes or "_None yet._", ""])
        lines.extend(
            ["## Decisions so far", "", (config.decisions_so_far or "_None yet._").strip(), ""]
        )
        lines.extend(
            ["## Not yet specified", "", (config.not_yet_specified or "_TBD._").strip(), ""]
        )
        lines.extend(["## Out of scope", "", (config.out_of_scope or "_None listed._").strip(), ""])
        lines.extend(self._render_agent_refs(config))
        return lines

    def _validate_map_parent_config(self, config: StoryConfig) -> None:
        """Raise ``ValueError`` if a map parent lacks a title or destination."""
        errors: list[str] = []
        if not config.title.strip():
            errors.append("title is empty")
        elif len(config.title) > self._AGENT_TITLE_MAX:
            errors.append(f"title is {len(config.title)} chars (limit {self._AGENT_TITLE_MAX})")
        destination = (config.destination or config.purpose_and_intent or config.want).strip()
        if not destination:
            errors.append("destination/purpose_and_intent/want must provide ## Destination")
        if errors:
            joined = "; ".join(errors)
            raise ValueError(f"audience='agent' issue_kind='map-parent' requires: {joined}.")

    def _render_agent_template(self, config: StoryConfig) -> list[str]:
        """Render a 5-section Linear-issue template.

        Emits the shape locked in ``docs/linear/AGENT_ISSUES.md`` and
        enforces the HIGH-severity rules from ``docs_lint_linear_issue``:
        title ≤80 chars, ≥1 ``file.ext:LINE`` anchor in files, ≥1
        acceptance-criterion checkbox. Violations raise ``ValueError`` so
        the MCP handler translates them to a structured error response.
        """
        self._validate_agent_config(config)

        lines: list[str] = [f"# {config.title}", ""]
        lines.extend(self._render_agent_what(config))
        lines.extend(self._render_agent_where(config))
        lines.extend(self._render_agent_why(config))
        lines.extend(self._render_agent_assertions(config))
        lines.extend(self._render_agent_acceptance(config))
        lines.extend(self._render_agent_refs(config))
        return lines

    def _validate_agent_config(self, config: StoryConfig) -> None:
        """Raise ``ValueError`` if inputs violate the locked agent template."""
        errors: list[str] = []
        if not config.title.strip():
            errors.append("title is empty")
        elif len(config.title) > self._AGENT_TITLE_MAX:
            errors.append(f"title is {len(config.title)} chars (limit {self._AGENT_TITLE_MAX})")
        if not self._has_file_anchor(config.files):
            errors.append("files[] must include at least one `path/to/file.ext:LINE-RANGE` anchor")
        if not config.acceptance_criteria:
            errors.append("acceptance_criteria[] must be non-empty")
        if errors:
            joined = "; ".join(errors)
            raise ValueError(
                "audience='agent' requires template-compliant inputs: "
                f"{joined}. Pass audience='human' for the scaffold shape."
            )

    def _has_file_anchor(self, files: list[str]) -> bool:
        return any(self._AGENT_FILE_ANCHOR_RE.search(f) for f in files)

    def _render_agent_what(self, config: StoryConfig) -> list[str]:
        what = self._derive_agent_what(config)
        return ["## What", "", what, ""]

    def _derive_agent_what(self, config: StoryConfig) -> str:
        if config.role.strip() and config.want.strip():
            return f"As a {config.role.strip()}, {config.want.strip()}."
        if config.description.strip():
            # Keep the full description — first-sentence truncation dropped
            # multi-sentence context that agents need (TAP-5357).
            return config.description.strip()
        return config.title

    def _render_agent_where(self, config: StoryConfig) -> list[str]:
        lines = ["## Where", ""]
        lines.extend(f"- `{path}`" for path in config.files)
        lines.append("")
        return lines

    def _render_agent_why(self, config: StoryConfig) -> list[str]:
        if not config.so_that.strip():
            return []
        return ["## Why", "", config.so_that.strip(), ""]

    def _render_agent_assertions(self, config: StoryConfig) -> list[str]:
        """Optional Assertions section (TAP-5541 validation-contract IDs)."""
        if not config.assertions:
            return []
        lines = ["## Assertions", ""]
        for item in config.assertions:
            text = item.strip()
            if not text:
                continue
            lines.append(f"- `{text}`" if not text.startswith("`") else f"- {text}")
        lines.append("")
        return lines

    def _render_agent_acceptance(self, config: StoryConfig) -> list[str]:
        lines = ["## Acceptance", ""]
        lines.extend(f"- [ ] {criterion}" for criterion in config.acceptance_criteria)
        lines.append("")
        return lines

    def _render_agent_refs(self, config: StoryConfig) -> list[str]:
        refs: list[str] = []
        # First, extract TAP-### refs from dependencies and description.
        sources: list[str] = [*config.dependencies, config.description]
        for source in sources:
            for ref in self._TAP_REF_RE.findall(source):
                if ref not in refs:
                    refs.append(ref)
        # Then, include any dependency that isn't a TAP-### ref verbatim.
        for dep in config.dependencies:
            dep_stripped = dep.strip()
            if (
                dep_stripped
                and not self._TAP_REF_RE.search(dep_stripped)
                and dep_stripped not in refs
            ):
                refs.append(dep_stripped)
        if config.epic_path.strip() and config.epic_path.strip() not in refs:
            refs.append(config.epic_path.strip())
        if not refs:
            return []
        return ["## Refs", "", ", ".join(refs), ""]
