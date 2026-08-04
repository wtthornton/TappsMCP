"""Tests for the agent-audience story renderers (TAP-5498 / TAP-5609).

`test_linear_issue_kinds.py` covers the generator → validator round trip.
These tests pin the renderer itself: the section shape each `issue_kind`
emits, and the ValueError raised when required inputs are missing.
"""

from __future__ import annotations

import pytest

from docs_mcp.generators.stories import StoryGenerator
from docs_mcp.generators.story_models import StoryConfig


def _sections(lines: list[str]) -> list[str]:
    return [line for line in lines if line.startswith("## ")]


class TestImplementableTemplate:
    def test_emits_the_locked_five_sections(self) -> None:
        config = StoryConfig(
            title="rate_limiter.py: per-tenant upload limit",
            description="Uploads are unbounded per tenant.",
            so_that="one tenant cannot exhaust shared capacity",
            files=["packages/api/src/rate_limiter.py:1-80"],
            acceptance_criteria=["Requests over the limit return 429"],
        )
        assert _sections(StoryGenerator()._render_agent_template(config)) == [
            "## What",
            "## Where",
            "## Why",
            "## Acceptance",
        ]

    def test_missing_file_anchor_is_rejected(self) -> None:
        config = StoryConfig(
            title="rate_limiter.py: per-tenant upload limit",
            files=["packages/api/src/rate_limiter.py"],
            acceptance_criteria=["Requests over the limit return 429"],
        )
        with pytest.raises(ValueError, match="LINE-RANGE"):
            StoryGenerator()._render_agent_template(config)


class TestDecisionTemplate:
    def test_question_body_replaces_where_and_acceptance(self) -> None:
        config = StoryConfig(
            title="Pick the cache eviction policy",
            issue_kind="decision",
            question="Do we evict by TTL or by LRU?",
            purpose_and_intent="The current policy is unstated, so callers guess.",
        )
        sections = _sections(StoryGenerator()._render_decision_template(config))
        assert sections == ["## Question", "## Why"]

    def test_purpose_stands_in_for_a_missing_question(self) -> None:
        config = StoryConfig(
            title="Pick the cache eviction policy",
            issue_kind="decision",
            purpose_and_intent="Do we evict by TTL or by LRU?",
        )
        lines = StoryGenerator()._render_decision_template(config)
        assert "Do we evict by TTL or by LRU?" in lines
        # Identical Question and Why would just be a repeat, so Why is dropped.
        assert "## Why" not in lines

    def test_no_question_anywhere_is_rejected(self) -> None:
        config = StoryConfig(title="Pick the cache eviction policy", issue_kind="decision")
        with pytest.raises(ValueError, match="## Question"):
            StoryGenerator()._render_decision_template(config)

    def test_overlong_title_is_rejected(self) -> None:
        config = StoryConfig(
            title="x" * 81,
            issue_kind="decision",
            question="Do we evict by TTL or by LRU?",
        )
        with pytest.raises(ValueError, match="limit 80"):
            StoryGenerator()._render_decision_template(config)


class TestMapParentTemplate:
    def test_emits_the_five_wayfind_sections(self) -> None:
        config = StoryConfig(
            title="Caching subsystem map",
            issue_kind="map-parent",
            destination="One cache substrate behind a single interface.",
        )
        assert _sections(StoryGenerator()._render_map_parent_template(config)) == [
            "## Destination",
            "## Notes",
            "## Decisions so far",
            "## Not yet specified",
            "## Out of scope",
        ]

    def test_unfilled_sections_get_explicit_placeholders(self) -> None:
        config = StoryConfig(
            title="Caching subsystem map",
            issue_kind="map-parent",
            destination="One cache substrate behind a single interface.",
        )
        lines = StoryGenerator()._render_map_parent_template(config)
        assert "_None yet._" in lines
        assert "_TBD._" in lines
        assert "_None listed._" in lines

    def test_no_destination_anywhere_is_rejected(self) -> None:
        config = StoryConfig(title="Caching subsystem map", issue_kind="map-parent")
        with pytest.raises(ValueError, match="## Destination"):
            StoryGenerator()._render_map_parent_template(config)


class TestGenerateDispatch:
    @pytest.mark.parametrize(
        ("issue_kind", "expected"),
        [("decision", "## Question"), ("map-parent", "## Destination")],
    )
    def test_generate_routes_on_issue_kind(self, issue_kind: str, expected: str) -> None:
        config = StoryConfig(
            title="Pick the cache eviction policy",
            issue_kind=issue_kind,
            question="Do we evict by TTL or by LRU?",
            destination="One cache substrate behind a single interface.",
        )
        assert expected in StoryGenerator().generate(config)

    def test_unknown_issue_kind_falls_back_to_implementable(self) -> None:
        config = StoryConfig(
            title="rate_limiter.py: per-tenant upload limit",
            issue_kind="nonsense",
            files=["packages/api/src/rate_limiter.py:1-80"],
            acceptance_criteria=["Requests over the limit return 429"],
        )
        assert "## Acceptance" in StoryGenerator().generate(config)
