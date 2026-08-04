"""Tests for the human-audience story section renderers (TAP-5609).

``stories.py`` was split into per-concern mixins. These tests pin each human
section's rendered shape directly, independent of the ``generate()``
composition that assembles them.
"""

from __future__ import annotations

from docs_mcp.generators.stories import StoryGenerator
from docs_mcp.generators.story_models import StoryConfig


def _config(**overrides: object) -> StoryConfig:
    base: dict[str, object] = {
        "title": "Add rate limiting to the upload endpoint",
        "role": "platform operator",
        "want": "uploads to be rate limited per tenant",
        "so_that": "one tenant cannot exhaust shared capacity",
        "acceptance_criteria": ["Requests over the limit return 429"],
    }
    base.update(overrides)
    return StoryConfig(**base)  # type: ignore[arg-type]


class TestTitle:
    def test_plain_title_when_unnumbered(self) -> None:
        gen = StoryGenerator()
        assert gen._render_title(_config())[0] == "# Add rate limiting to the upload endpoint"

    def test_epic_and_story_number_compose_a_story_id(self) -> None:
        gen = StoryGenerator()
        config = _config(epic_number=80, story_number=3)
        assert gen._render_title(config)[0].startswith("# Story 80.3 -- ")

    def test_story_number_alone_omits_the_epic_prefix(self) -> None:
        gen = StoryGenerator()
        assert gen._render_title(_config(story_number=3))[0].startswith("# Story 3 -- ")


class TestUserStoryStatement:
    def test_role_and_want_render_the_full_statement(self) -> None:
        gen = StoryGenerator()
        lines = gen._render_user_story_statement(_config())
        statement = next(line for line in lines if line.startswith(">"))
        assert "**As a** platform operator" in statement
        assert "**so that** one tenant cannot exhaust shared capacity" in statement

    def test_missing_role_falls_back_to_the_placeholder(self) -> None:
        gen = StoryGenerator()
        lines = gen._render_user_story_statement(_config(role="", want=""))
        assert any("[role]" in line for line in lines)

    def test_statement_is_wrapped_in_smart_merge_markers(self) -> None:
        gen = StoryGenerator()
        lines = gen._render_user_story_statement(_config())
        assert lines[0] == "<!-- docsmcp:start:user-story -->"
        assert "<!-- docsmcp:end:user-story -->" in lines


class TestSizing:
    def test_points_and_size_are_joined(self) -> None:
        gen = StoryGenerator()
        lines = gen._render_sizing(_config(points=5, size="M"))
        assert "**Points:** 5 | **Size:** M" in lines

    def test_unset_sizing_renders_tbd(self) -> None:
        gen = StoryGenerator()
        assert "**Points:** TBD" in gen._render_sizing(_config())

    def test_size_outside_the_valid_set_is_dropped(self) -> None:
        gen = StoryGenerator()
        lines = gen._render_sizing(_config(points=3, size="XXL"))
        assert "**Points:** 3" in lines
        assert not any("XXL" in line for line in lines)


class TestPurposeAndIntent:
    def test_supplied_purpose_is_used_verbatim(self) -> None:
        gen = StoryGenerator()
        lines = gen._render_purpose_and_intent(_config(purpose_and_intent="Protect shared quota."))
        assert "Protect shared quota." in lines

    def test_missing_purpose_falls_back_to_guidance(self) -> None:
        gen = StoryGenerator()
        lines = gen._render_purpose_and_intent(_config())
        assert any("Refine this paragraph" in line for line in lines)


class TestDependencies:
    def test_dependencies_are_listed(self) -> None:
        gen = StoryGenerator()
        lines = gen._render_dependencies(_config(dependencies=["TAP-1234", "TAP-5678"]))
        assert any("TAP-1234" in line for line in lines)
        assert any("TAP-5678" in line for line in lines)

    def test_no_dependencies_renders_the_scaffold_prompt(self) -> None:
        gen = StoryGenerator()
        lines = gen._render_dependencies(_config())
        assert "## Dependencies" in lines
        assert any("must complete first" in line for line in lines)
