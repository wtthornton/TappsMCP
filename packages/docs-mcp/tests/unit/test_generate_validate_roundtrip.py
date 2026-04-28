"""Generator-validator round-trip tests (TAP-1083).

Locks in the contract that ``docs_generate_story`` and ``docs_generate_epic``
either refuse with a structured error or produce output that
``docs_validate_linear_issue`` accepts as ``agent_ready: true``. The audit
cases that motivated TAP-1083 (empty ``files`` and empty ``acceptance_criteria``)
silently produced validator-failing bodies before the relevant fixes landed.

Story (audience="agent", the default) raises ValueError on missing required
inputs. Epic falls back to title-derived placeholder checkboxes, but those
placeholders must still satisfy the ``is_epic=True`` validator rules.
"""

from __future__ import annotations

import pytest

from docs_mcp.generators.epics import EpicConfig, EpicGenerator
from docs_mcp.generators.stories import StoryConfig, StoryGenerator
from docs_mcp.validators.linear_issue import validate_issue


@pytest.fixture
def story_generator() -> StoryGenerator:
    return StoryGenerator()


@pytest.fixture
def epic_generator() -> EpicGenerator:
    return EpicGenerator()


class TestStoryRefusesInvalidInputs:
    def test_empty_files_raises_value_error(self, story_generator: StoryGenerator) -> None:
        config = StoryConfig(
            title="foo.py: bug",
            acceptance_criteria=["fix the bug"],
            files=[],
            audience="agent",
        )
        with pytest.raises(ValueError, match="files"):
            story_generator.generate(config)

    def test_empty_acceptance_criteria_raises_value_error(
        self,
        story_generator: StoryGenerator,
    ) -> None:
        config = StoryConfig(
            title="foo.py: bug",
            acceptance_criteria=[],
            files=["packages/foo/foo.py:1-50"],
            audience="agent",
        )
        with pytest.raises(ValueError, match="acceptance_criteria"):
            story_generator.generate(config)


class TestStoryAgentModePassesValidator:
    def test_minimal_valid_inputs_round_trip(self, story_generator: StoryGenerator) -> None:
        config = StoryConfig(
            title="foo.py: handle empty input",
            description="The handler crashes on empty payloads.",
            acceptance_criteria=["empty payload returns 400"],
            files=["packages/foo/foo.py:42-58"],
            audience="agent",
        )
        body = story_generator.generate(config)
        report = validate_issue(
            title=config.title,
            description=body,
            priority=3,
            estimate=2.0,
        )
        assert report.agent_ready is True, report.missing
        assert report.score >= 90


class TestEpicPassesValidator:
    def test_minimal_valid_inputs_round_trip(self, epic_generator: EpicGenerator) -> None:
        config = EpicConfig(
            title="EPIC-X: harden the foo subsystem",
            purpose_and_intent="We are doing this so that foo stops failing.",
            goal="ship the hardening",
            motivation="incidents are piling up",
            acceptance_criteria=[
                "no foo incidents for 14 days post-rollout",
                "foo p99 latency < 200ms",
            ],
        )
        body = epic_generator.generate(config)
        report = validate_issue(
            title=config.title,
            description=body,
            priority=2,
            is_epic=True,
        )
        assert report.agent_ready is True, report.missing
        assert report.score >= 90

    def test_empty_acceptance_falls_back_to_placeholders_that_pass_validator(
        self,
        epic_generator: EpicGenerator,
    ) -> None:
        """Closes the BambuStudio audit cases (acceptance-empty)."""
        config = EpicConfig(
            title="EPIC-Y: tighten the bar subsystem",
            goal="raise reliability",
            motivation="audit found gaps",
            acceptance_criteria=[],
        )
        body = epic_generator.generate(config)
        report = validate_issue(
            title=config.title,
            description=body,
            priority=2,
            is_epic=True,
        )
        assert report.agent_ready is True, report.missing
        assert report.score >= 90
