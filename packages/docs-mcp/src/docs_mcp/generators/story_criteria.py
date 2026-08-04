"""Acceptance-criteria rendering for story generation.

Checkbox and Gherkin criteria, plus the Given/When/Then derivation that
turns a plain criterion into a behavioural clause. Split out of
``story_sections_human.py`` under TAP-5609.
"""

from __future__ import annotations

import structlog

from docs_mcp.generators.story_base import StoryGeneratorBase
from docs_mcp.generators.story_models import StoryConfig

logger = structlog.get_logger(__name__)


class CriteriaSectionsMixin(StoryGeneratorBase):
    """Checkbox and Gherkin acceptance-criteria rendering."""

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
            lines.extend(f"- [ ] {criterion}" for criterion in config.acceptance_criteria)
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
    def _derive_given(role: str) -> str:
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
                given = self._derive_given(config.role)
                when = self._derive_when(config.role, config.want, criterion)
                then = self._derive_then(criterion, config.so_that)

                given_line = given or "[describe the precondition]"
                when_line = when or f"[describe the action that triggers: {criterion.lower()}]"
                then_line = then or "[describe the expected observable outcome]"

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
