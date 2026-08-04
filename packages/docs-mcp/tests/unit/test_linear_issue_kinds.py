"""TAP-5497 / TAP-5498: decision + map-parent issue kinds and generators."""

from __future__ import annotations

from docs_mcp.generators.stories import StoryConfig, StoryGenerator
from docs_mcp.linters.linear_issue import lint_issue
from docs_mcp.validators.linear_issue import validate_issue


class TestDecisionKindLint:
    def test_decision_with_question_is_agent_ready(self) -> None:
        result = lint_issue(
            title="Should we cache X?",
            description="## Question\nDo we cache X across restarts?\n",
            priority=2,
            estimate=1.0,
            issue_kind="decision",
        )
        assert result.agent_ready is True
        assert not any(f.rule == "missing-file-anchor" for f in result.findings)
        assert not any(f.rule == "missing-acceptance" for f in result.findings)

    def test_decision_missing_question_blocks(self) -> None:
        result = lint_issue(
            title="Should we cache X?",
            description="## What\nSome prose without Question heading.\n",
            priority=2,
            estimate=1.0,
            issue_kind="decision",
        )
        assert result.agent_ready is False
        assert any(f.rule == "missing-question" for f in result.findings)

    def test_implementable_question_only_still_blocks(self) -> None:
        """Default implementable kind still requires AC + file anchors."""
        result = lint_issue(
            title="Should we cache X?",
            description="## Question\nDo we cache X?\n",
            priority=2,
            estimate=1.0,
            issue_kind="implementable",
        )
        assert result.agent_ready is False
        assert any(f.rule == "missing-file-anchor" for f in result.findings)
        assert any(f.rule == "missing-acceptance" for f in result.findings)


class TestMapParentKindLint:
    def test_map_parent_with_destination_passes(self) -> None:
        result = lint_issue(
            title="Wayfind: auth rewrite",
            description=(
                "## Destination\nShip OAuth2 refresh.\n\n"
                "## Decisions so far\n_None yet._\n\n"
                "## Not yet specified\nProvider choice.\n\n"
                "## Out of scope\nMobile SDK.\n"
            ),
            priority=2,
            estimate=3.0,
            issue_kind="map-parent",
        )
        assert result.agent_ready is True

    def test_map_parent_missing_sections_blocks(self) -> None:
        result = lint_issue(
            title="Wayfind: auth rewrite",
            description="## What\nNo map sections here.\n",
            priority=2,
            estimate=3.0,
            issue_kind="map-parent",
        )
        assert result.agent_ready is False
        assert any(f.rule == "missing-map-sections" for f in result.findings)


class TestDecisionMapGeneratorsRoundTrip:
    def test_decision_generator_validates(self) -> None:
        body = StoryGenerator().generate(
            StoryConfig(
                title="Should we use Redis?",
                audience="agent",
                issue_kind="decision",
                question="Do we introduce Redis for session cache?",
            )
        )
        # Strip leading H1 — Linear description is body-only for validate.
        desc = body.split("\n", 2)[-1] if body.startswith("# ") else body
        report = validate_issue(
            title="Should we use Redis?",
            description=desc,
            priority=2,
            estimate=1.0,
            issue_kind="decision",
        )
        assert report.agent_ready is True
        assert "## Question" in body
        assert "## Acceptance" not in body

    def test_map_parent_generator_validates(self) -> None:
        body = StoryGenerator().generate(
            StoryConfig(
                title="Wayfind: session tenure",
                audience="agent",
                issue_kind="map-parent",
                destination="Agents resume foggy work via wayfind maps.",
                notes="Chart before orchestration-prompt.",
                decisions_so_far="Linear remains SoT.",
                not_yet_specified="Brain resume pack schema.",
                out_of_scope="New MCP wayfind tools.",
            )
        )
        desc = body.split("\n", 2)[-1] if body.startswith("# ") else body
        report = validate_issue(
            title="Wayfind: session tenure",
            description=desc,
            priority=2,
            estimate=2.0,
            issue_kind="map-parent",
        )
        assert report.agent_ready is True
        assert "## Destination" in body
        assert "## Decisions so far" in body
        assert "## Not yet specified" in body
        assert "## Out of scope" in body
