"""Tests for docs_mcp.generators.stories -- human-vs-agent audience output.

Split from test_stories.py (TAP-5622): covers the ``audience="agent"``
locked Linear-issue template, agent-readiness enforcement, the human-shape
renderer, the MCP handler's audience path, and criteria/what-section
composition. Gherkin scaffolding and the quick_start MCP-tool path live in
test_stories_scaffolding.py; content generation itself (section rendering,
styles, markers, empty inputs, auto-populate, expert enrichment) stays in
test_stories.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from tests.helpers import make_settings as _make_settings
from tests.helpers import make_story_config as _make_config

from docs_mcp.generators.stories import StoryConfig, StoryGenerator

# ---------------------------------------------------------------------------
# STORY-104.1: agent audience is the default — 5-section Linear template
# ---------------------------------------------------------------------------


class TestAgentAudience:
    """The default audience='agent' emits the locked Linear-issue template."""

    def setup_method(self) -> None:
        self.gen = StoryGenerator()

    def _agent_config(self, **overrides: Any) -> StoryConfig:
        """Build a valid agent-audience config."""
        defaults: dict[str, Any] = {
            "title": "upgrade.py: _has_python_signals rglob traverses node_modules",
            "role": "maintainer",
            "want": "prune vendor dirs before rglob",
            "so_that": "upgrade scans don't traverse node_modules",
            "files": [
                "packages/tapps-mcp/src/tapps_mcp/pipeline/upgrade.py:92-116",
            ],
            "acceptance_criteria": [
                "rglob is replaced with a pruning walk",
                "`pytest packages/tapps-mcp/tests/unit/test_upgrade.py` passes",
            ],
            "dependencies": ["TAP-496"],
        }
        defaults.update(overrides)
        return StoryConfig(**defaults)

    def test_agent_is_default(self) -> None:
        config = StoryConfig(
            title="foo.py: bar",
            files=["foo.py:1"],
            acceptance_criteria=["done"],
        )
        assert config.audience == "agent"

    def test_emits_five_section_template(self) -> None:
        config = self._agent_config()
        content = self.gen.generate(config)
        assert "## What" in content
        assert "## Where" in content
        assert "## Why" in content
        assert "## Acceptance" in content
        assert "## Refs" in content

    def test_omits_human_sections(self) -> None:
        """Agent mode must NOT emit human-review vocabulary."""
        config = self._agent_config()
        content = self.gen.generate(config)
        assert "## User Story Statement" not in content
        assert "## Purpose & Intent" not in content
        assert "## Sizing" not in content
        assert "## Tasks" not in content
        assert "## Definition of Done" not in content
        assert "## INVEST" not in content

    def test_round_trip_passes_validator(self) -> None:
        """Agent-mode output must pass docs_validate_linear_issue."""
        from docs_mcp.validators.linear_issue import validate_issue

        config = self._agent_config()
        content = self.gen.generate(config)

        # Extract title + body for the validator (H1 line is the title).
        lines = content.split("\n", 1)
        h1_line = lines[0].lstrip("# ").strip()
        body = lines[1] if len(lines) > 1 else ""

        report = validate_issue(
            title=h1_line,
            description=body,
            priority=2,
            estimate=2.0,
        )
        assert report.agent_ready is True, f"Missing: {report.missing}"
        assert report.score == 100

    def test_refs_collects_tap_ids_from_dependencies(self) -> None:
        config = self._agent_config(dependencies=["TAP-496", "TAP-834"])
        content = self.gen.generate(config)
        assert "TAP-496" in content
        assert "TAP-834" in content

    def test_why_omitted_when_so_that_empty(self) -> None:
        config = self._agent_config(so_that="")
        content = self.gen.generate(config)
        assert "## Why" not in content

    def test_assertions_section_renders_ids(self) -> None:
        """TAP-5541: optional Assertions section with stable VAL- IDs."""
        config = self._agent_config(assertions=["VAL-AUTH-001", "VAL-API-002"])
        content = self.gen.generate(config)
        assert "## Assertions" in content
        assert "`VAL-AUTH-001`" in content
        assert "`VAL-API-002`" in content
        # Assertions sit between Why and Acceptance.
        assert content.index("## Assertions") < content.index("## Acceptance")

    def test_assertions_omitted_when_empty(self) -> None:
        config = self._agent_config(assertions=[])
        content = self.gen.generate(config)
        assert "## Assertions" not in content

    def test_refs_omitted_when_no_refs(self) -> None:
        config = self._agent_config(dependencies=[], description="")
        content = self.gen.generate(config)
        assert "## Refs" not in content


class TestAgentAudienceEnforcement:
    """audience='agent' raises ValueError on template violations."""

    def setup_method(self) -> None:
        self.gen = StoryGenerator()

    def test_missing_file_anchor_raises(self) -> None:
        config = StoryConfig(
            title="foo.py: x",
            files=["foo.py"],  # no :LINE suffix
            acceptance_criteria=["done"],
        )
        try:
            self.gen.generate(config)
        except ValueError as exc:
            assert "file.ext:LINE" in str(exc) or "anchor" in str(exc).lower()
        else:
            raise AssertionError("expected ValueError for missing file anchor")

    def test_empty_acceptance_criteria_raises(self) -> None:
        config = StoryConfig(
            title="foo.py: x",
            files=["foo.py:1"],
            acceptance_criteria=[],
        )
        try:
            self.gen.generate(config)
        except ValueError as exc:
            assert "acceptance_criteria" in str(exc)
        else:
            raise AssertionError("expected ValueError for empty acceptance_criteria")

    def test_title_too_long_raises(self) -> None:
        config = StoryConfig(
            title="x" * 100,
            files=["foo.py:1"],
            acceptance_criteria=["done"],
        )
        try:
            self.gen.generate(config)
        except ValueError as exc:
            assert "title" in str(exc).lower()
            assert "80" in str(exc)
        else:
            raise AssertionError("expected ValueError for long title")

    def test_empty_title_raises(self) -> None:
        config = StoryConfig(
            title="",
            files=["foo.py:1"],
            acceptance_criteria=["done"],
        )
        try:
            self.gen.generate(config)
        except ValueError as exc:
            assert "title" in str(exc).lower()
        else:
            raise AssertionError("expected ValueError for empty title")


class TestHumanAudience:
    """audience='human' preserves the legacy product-review shape."""

    def setup_method(self) -> None:
        self.gen = StoryGenerator()

    def test_human_audience_emits_rich_shape(self) -> None:
        config = _make_config(audience="human")  # helper already sets this
        content = self.gen.generate(config)
        # Must emit the rich human-review sections.
        assert "**As a**" in content  # blockquoted user-story statement
        assert "## Purpose & Intent" in content
        assert "## Tasks" in content
        assert "## Acceptance Criteria" in content
        assert "## Definition of Done" in content
        # Must NOT emit the terse agent template as the primary shape.
        # (## Acceptance is agent; ## Acceptance Criteria is human.)
        assert "## What\n" not in content


class TestAgentAudienceViaMCPHandler:
    """The MCP handler surfaces ValueError as INPUT_INVALID."""

    async def _call(self, **kwargs: Any) -> dict[str, Any]:
        from docs_mcp.server_gen_tools import docs_generate_story

        return await docs_generate_story(**kwargs)

    async def test_agent_default_missing_files_returns_input_invalid(
        self,
        tmp_path: Path,
    ) -> None:
        root = tmp_path / "proj"
        root.mkdir()
        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = await self._call(
                title="foo.py: something",
                acceptance_criteria="done",
                project_root=str(root),
            )
        assert result["success"] is False
        assert result["error"]["code"] == "INPUT_INVALID"
        assert "anchor" in result["error"]["message"].lower()

    async def test_agent_default_with_valid_inputs_succeeds(
        self,
        tmp_path: Path,
    ) -> None:
        root = tmp_path / "proj"
        root.mkdir()
        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = await self._call(
                title="foo.py: something",
                files="foo.py:12-20",
                acceptance_criteria="criterion one, criterion two",
                project_root=str(root),
                write_to_disk=True,
            )
        assert result["success"] is True
        assert result["data"]["audience"] == "agent"
        content = (root / result["data"]["written_to"]).read_text(encoding="utf-8")
        assert "## What" in content
        assert "## Acceptance" in content


# ---------------------------------------------------------------------------
# TAP-5357: criteria list parsing + What-section description fidelity
# ---------------------------------------------------------------------------


class TestTap5357CriteriaAndWhat:
    """Comma-safe AC splitting, multi-line checkboxes, full description in What."""

    def test_split_criteria_keeps_commas_in_one_item(self) -> None:
        from docs_mcp.server_gen_tools import _split_criteria_list

        criterion = (
            "A written decision records where credential refresh belongs: "
            "AgentForge runtime, consumer repo, or explicitly out of scope "
            "with a stated reason"
        )
        assert _split_criteria_list(criterion) == [criterion]

    def test_split_criteria_splits_newlines_not_commas(self) -> None:
        from docs_mcp.server_gen_tools import _split_criteria_list

        raw = (
            "either X, Y, or Z is documented\n"
            "- [ ] second criterion with, commas\n"
            "* [ ] third criterion"
        )
        assert _split_criteria_list(raw) == [
            "either X, Y, or Z is documented",
            "second criterion with, commas",
            "third criterion",
        ]

    async def test_generate_story_comma_criterion_one_checkbox(
        self,
        tmp_path: Path,
    ) -> None:
        from docs_mcp.server_gen_tools import docs_generate_story

        root = tmp_path / "proj"
        root.mkdir()
        criterion = (
            "A written decision records where credential refresh belongs: "
            "AgentForge runtime, consumer repo, or explicitly out of scope "
            "with a stated reason"
        )
        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = await docs_generate_story(
                title="auth.py: decide OAuth refresh ownership",
                files="auth.py:10-20",
                acceptance_criteria=criterion,
                description=(
                    "Research and discussion spike. Map consumer vs AgentForge "
                    "ownership. Record the decision in an ADR."
                ),
                project_root=str(root),
                write_to_disk=True,
            )
        assert result["success"] is True
        content = (root / result["data"]["written_to"]).read_text(encoding="utf-8")
        checkbox_lines = [
            line for line in content.splitlines() if line.startswith("- [ ] ")
        ]
        assert len(checkbox_lines) == 1
        assert criterion in checkbox_lines[0]
        assert "- [ ] consumer repo" not in content

    async def test_generate_story_multiline_each_checkbox(
        self,
        tmp_path: Path,
    ) -> None:
        from docs_mcp.server_gen_tools import docs_generate_story

        root = tmp_path / "proj"
        root.mkdir()
        criteria = "first criterion\nsecond criterion\nthird criterion"
        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = await docs_generate_story(
                title="foo.py: multiline acceptance",
                files="foo.py:1-5",
                acceptance_criteria=criteria,
                project_root=str(root),
                write_to_disk=True,
            )
        assert result["success"] is True
        content = (root / result["data"]["written_to"]).read_text(encoding="utf-8")
        checkbox_lines = [
            line for line in content.splitlines() if line.startswith("- [ ] ")
        ]
        assert checkbox_lines == [
            "- [ ] first criterion",
            "- [ ] second criterion",
            "- [ ] third criterion",
        ]

    def test_agent_what_keeps_multi_sentence_description(self) -> None:
        gen = StoryGenerator()
        config = StoryConfig(
            title="foo.py: research spike",
            description=(
                "Research and discussion spike. Map ownership boundaries. "
                "Write down the decision."
            ),
            files=["foo.py:1"],
            acceptance_criteria=["done"],
        )
        content = gen.generate(config)
        what_idx = content.index("## What")
        where_idx = content.index("## Where")
        what_block = content[what_idx:where_idx]
        assert "Research and discussion spike." in what_block
        assert "Map ownership boundaries." in what_block
