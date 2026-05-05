"""Tests for docs_mcp.generators.stories -- User Story document generation.

Covers StoryGenerator section rendering, style variants, criteria formats,
empty inputs, auto-populate with mocked analyzers, and the
``docs_generate_story`` MCP tool.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from docs_mcp.generators.stories import (
    StoryConfig,
    StoryGenerator,
    StoryTask,
    markdown_relative_link,
)
from tests.helpers import make_settings as _make_settings


def _make_config(**kwargs: Any) -> StoryConfig:
    """Build a StoryConfig with sensible defaults."""
    defaults: dict[str, Any] = {
        "title": "Test Story",
        "epic_number": 23,
        "story_number": 1,
        "role": "developer",
        "want": "to validate login credentials",
        "so_that": "invalid logins are rejected",
        "description": "Implement client-side validation for the login form.",
        "points": 3,
        "size": "M",
        "tasks": [
            StoryTask(description="Create validation module", file_path="src/validators.py"),
            StoryTask(description="Write unit tests"),
        ],
        "acceptance_criteria": ["Validation rejects empty fields", "Error messages displayed"],
        "test_cases": ["Test empty email", "Test invalid password format"],
        "dependencies": ["Story 23.0"],
        "files": ["src/validators.py", "tests/test_validators.py"],
        "technical_notes": ["Use Pydantic for validation"],
        "criteria_format": "checkbox",
        "style": "standard",
        # STORY-104.1: existing tests were written against the human-shape
        # output. The default flipped to "agent" but these tests still
        # assert on the rich product-review sections — keep them pointed
        # at the human renderer. New agent-audience tests live in
        # TestAgentAudience below.
        "audience": "human",
    }
    defaults.update(kwargs)
    return StoryConfig(**defaults)


# ---------------------------------------------------------------------------
# StoryTask model
# ---------------------------------------------------------------------------


class TestStoryTask:
    """Tests for the StoryTask Pydantic model."""

    def test_defaults(self) -> None:
        task = StoryTask(description="Do something")
        assert task.description == "Do something"
        assert task.file_path == ""

    def test_with_file_path(self) -> None:
        task = StoryTask(description="Create model", file_path="src/models.py")
        assert task.file_path == "src/models.py"


# ---------------------------------------------------------------------------
# StoryConfig model
# ---------------------------------------------------------------------------


class TestStoryConfig:
    """Tests for the StoryConfig Pydantic model."""

    def test_defaults(self) -> None:
        config = StoryConfig(title="My Story")
        assert config.title == "My Story"
        assert config.epic_number == 0
        assert config.story_number == 0
        assert config.role == ""
        assert config.want == ""
        assert config.points == 0
        assert config.tasks == []
        assert config.criteria_format == "checkbox"
        assert config.style == "standard"
        # STORY-104.1: audience now defaults to "agent".
        assert config.audience == "agent"

    def test_style_values(self) -> None:
        config = StoryConfig(title="X", style="comprehensive")
        assert config.style == "comprehensive"


# ---------------------------------------------------------------------------
# StoryGenerator -- section rendering
# ---------------------------------------------------------------------------


class TestStoryGeneratorSections:
    """Tests for individual section rendering in StoryGenerator."""

    def setup_method(self) -> None:
        self.gen = StoryGenerator()

    def test_title_with_epic_and_story_number(self) -> None:
        config = _make_config(title="Auth", epic_number=23, story_number=1)
        content = self.gen.generate(config)
        assert content.startswith("# Story 23.1 -- Auth")

    def test_title_with_story_number_only(self) -> None:
        config = _make_config(title="Auth", epic_number=0, story_number=5)
        content = self.gen.generate(config)
        assert content.startswith("# Story 5 -- Auth")

    def test_title_without_numbers(self) -> None:
        config = _make_config(title="Auth", epic_number=0, story_number=0)
        content = self.gen.generate(config)
        assert content.startswith("# Auth")

    def test_user_story_statement(self) -> None:
        config = _make_config()
        content = self.gen.generate(config)
        assert "**As a** developer" in content
        assert "**I want** to validate login credentials" in content
        assert "**so that** invalid logins are rejected" in content

    def test_user_story_statement_without_so_that(self) -> None:
        config = _make_config(role="admin", want="to manage users", so_that="")
        content = self.gen.generate(config)
        assert "**As a** admin" in content
        assert "**I want** to manage users" in content
        assert "**so that**" not in content

    def test_user_story_placeholder(self) -> None:
        config = _make_config(role="", want="")
        content = self.gen.generate(config)
        assert "**As a** [role]" in content

    def test_sizing_with_points_and_size(self) -> None:
        config = _make_config(points=5, size="L")
        content = self.gen.generate(config)
        assert "**Points:** 5" in content
        assert "**Size:** L" in content

    def test_sizing_placeholder(self) -> None:
        config = _make_config(points=0, size="")
        content = self.gen.generate(config)
        assert "**Points:** TBD" in content

    def test_description_with_text(self) -> None:
        config = _make_config(description="Build the feature.")
        content = self.gen.generate(config)
        assert "## Description" in content
        assert "Build the feature." in content

    def test_description_placeholder(self) -> None:
        # _make_config has title + role + want → context-aware placeholder
        config = _make_config(description="")
        content = self.gen.generate(config)
        assert "Describe how **Test Story** will enable" in content

    def test_markdown_relative_link_epic_from_nested_story(self) -> None:
        rel = markdown_relative_link(
            "docs/archive/planning/epics/EPIC-80-PARENT.md",
            "docs/archive/planning/epics/EPIC-80/story-80.1.md",
        )
        assert rel == "../EPIC-80-PARENT.md"

    def test_epic_path_rewritten_when_output_path_set(self) -> None:
        config = _make_config(
            epic_path="docs/archive/planning/epics/EPIC-80-PARENT.md",
            inherit_context=True,
        )
        content = self.gen.generate(
            config,
            output_path="docs/archive/planning/epics/EPIC-80/story-80.1.md",
        )
        assert "../EPIC-80-PARENT.md" in content
        assert "See [Epic 23](../EPIC-80-PARENT.md)" in content

    def test_files_section(self) -> None:
        config = _make_config(files=["src/main.py", "tests/test_main.py"])
        content = self.gen.generate(config)
        assert "## Files" in content
        assert "`src/main.py`" in content
        assert "`tests/test_main.py`" in content

    def test_files_section_hidden_when_empty(self) -> None:
        config = _make_config(files=[])
        content = self.gen.generate(config)
        assert "## Files" not in content

    def test_tasks_rendered(self) -> None:
        config = _make_config()
        content = self.gen.generate(config)
        assert "## Tasks" in content
        assert "- [ ] Create validation module (`src/validators.py`)" in content
        assert "- [ ] Write unit tests" in content

    def test_tasks_placeholder(self) -> None:
        # "Test Story" title matches "test" keyword → suggestion engine returns test tasks
        config = _make_config(tasks=[])
        content = self.gen.generate(config)
        assert "- [ ] Write unit tests for happy path" in content

    def test_checkbox_acceptance_criteria(self) -> None:
        config = _make_config(criteria_format="checkbox")
        content = self.gen.generate(config)
        assert "## Acceptance Criteria" in content
        assert "- [ ] Validation rejects empty fields" in content
        assert "- [ ] Error messages displayed" in content

    def test_gherkin_acceptance_criteria(self) -> None:
        # _make_config has role="developer" and want="to validate login credentials"
        # so derivation methods produce meaningful output (no bracket placeholders).
        config = _make_config(criteria_format="gherkin")
        content = self.gen.generate(config)
        assert "```gherkin" in content
        assert "Given a developer is ready to perform the action" in content
        assert "When the developer validate login credentials" in content
        assert "Validation rejects empty fields successfully" in content

    def test_acceptance_criteria_placeholder_checkbox(self) -> None:
        # _make_config has title="Test Story" → context-aware AC placeholder
        config = _make_config(acceptance_criteria=[], criteria_format="checkbox")
        content = self.gen.generate(config)
        assert "- [ ] Test Story works as specified" in content

    def test_acceptance_criteria_placeholder_gherkin(self) -> None:
        config = _make_config(acceptance_criteria=[], criteria_format="gherkin")
        content = self.gen.generate(config)
        assert "Feature: Example" in content

    def test_definition_of_done(self) -> None:
        # _make_config has title="Test Story" → context-aware DoD placeholder
        config = _make_config()
        content = self.gen.generate(config)
        assert "## Definition of Done" in content
        assert "- [ ] Test Story code reviewed and approved" in content
        assert "- [ ] Tests passing" in content


# ---------------------------------------------------------------------------
# StoryGenerator -- context-aware placeholders (Story 92.2)
# ---------------------------------------------------------------------------


class TestContextAwarePlaceholders:
    """Tests for context-interpolated placeholder text (Story 92.2).

    Verifies that description, task, AC, and DoD placeholders use the story's
    title (and role/want when available) instead of generic boilerplate.
    Falls back to generic text when title is empty/whitespace.
    """

    def setup_method(self) -> None:
        self.gen = StoryGenerator()

    # -- description --------------------------------------------------------

    def test_description_placeholder_with_title_role_want(self) -> None:
        config = _make_config(description="", role="developer", want="add search")
        content = self.gen.generate(config)
        assert "Describe how **Test Story** will enable **developer** to **add search**" in content

    def test_description_placeholder_with_title_only(self) -> None:
        config = _make_config(description="", role="", want="", so_that="")
        content = self.gen.generate(config)
        assert "Describe what **Test Story** delivers" in content

    def test_description_placeholder_empty_title_fallback(self) -> None:
        config = _make_config(title="", description="", role="", want="")
        content = self.gen.generate(config)
        assert "Describe what this story delivers and any important context" in content

    def test_description_placeholder_whitespace_title_fallback(self) -> None:
        config = _make_config(title="   ", description="", role="", want="")
        content = self.gen.generate(config)
        assert "Describe what this story delivers and any important context" in content

    # -- tasks --------------------------------------------------------------

    def test_tasks_placeholder_uses_title(self) -> None:
        # Clear description so keyword matching falls through to the
        # title-derived generic fallback ("Implement <title>").
        config = _make_config(tasks=[], title="Rate Limiter", description="")
        content = self.gen.generate(config)
        assert "- [ ] Implement rate limiter" in content

    def test_tasks_placeholder_empty_title_fallback(self) -> None:
        config = _make_config(tasks=[], title="")
        content = self.gen.generate(config)
        assert "- [ ] Define implementation tasks..." in content

    def test_tasks_placeholder_whitespace_title_fallback(self) -> None:
        config = _make_config(tasks=[], title="   ")
        content = self.gen.generate(config)
        assert "- [ ] Define implementation tasks..." in content

    # -- acceptance criteria ------------------------------------------------

    def test_ac_placeholder_uses_title(self) -> None:
        config = _make_config(acceptance_criteria=[], title="Auth Middleware")
        content = self.gen.generate(config)
        assert "- [ ] Auth Middleware works as specified" in content

    def test_ac_placeholder_empty_title_fallback(self) -> None:
        config = _make_config(acceptance_criteria=[], title="")
        content = self.gen.generate(config)
        assert "- [ ] Feature works as specified" in content

    def test_ac_placeholder_whitespace_title_fallback(self) -> None:
        config = _make_config(acceptance_criteria=[], title="   ")
        content = self.gen.generate(config)
        assert "- [ ] Feature works as specified" in content

    # -- definition of done -------------------------------------------------

    def test_dod_placeholder_uses_title(self) -> None:
        config = _make_config(tasks=[], title="Session Manager")
        content = self.gen.generate(config)
        assert "- [ ] Session Manager code reviewed and approved" in content

    def test_dod_placeholder_empty_title_fallback(self) -> None:
        config = _make_config(title="")
        content = self.gen.generate(config)
        assert "- [ ] Code reviewed and approved" in content

    def test_dod_placeholder_whitespace_title_fallback(self) -> None:
        config = _make_config(title="   ")
        content = self.gen.generate(config)
        assert "- [ ] Code reviewed and approved" in content


# ---------------------------------------------------------------------------
# StoryGenerator -- style variants
# ---------------------------------------------------------------------------


class TestStoryGeneratorStyles:
    """Tests for standard vs comprehensive style."""

    def setup_method(self) -> None:
        self.gen = StoryGenerator()

    def test_standard_no_extra_sections(self) -> None:
        config = _make_config(style="standard")
        content = self.gen.generate(config)
        assert "## Test Cases" not in content
        assert "## Technical Notes" not in content
        assert "## Dependencies" not in content
        assert "## INVEST Checklist" not in content

    def test_comprehensive_has_test_cases(self) -> None:
        config = _make_config(style="comprehensive")
        content = self.gen.generate(config)
        assert "## Test Cases" in content
        assert "Test empty email" in content

    def test_comprehensive_has_technical_notes(self) -> None:
        config = _make_config(style="comprehensive")
        content = self.gen.generate(config)
        assert "## Technical Notes" in content
        assert "Use Pydantic for validation" in content

    def test_comprehensive_has_dependencies(self) -> None:
        config = _make_config(style="comprehensive")
        content = self.gen.generate(config)
        assert "## Dependencies" in content
        assert "Story 23.0" in content

    def test_comprehensive_has_invest_checklist(self) -> None:
        config = _make_config(style="comprehensive")
        content = self.gen.generate(config)
        assert "## INVEST Checklist" in content
        assert "**I**ndependent" in content
        assert "**N**egotiable" in content
        assert "**V**aluable" in content
        assert "**E**stimable" in content
        assert "**S**mall" in content
        assert "**T**estable" in content

    def test_invalid_style_falls_back_to_standard(self) -> None:
        config = _make_config(style="unknown")
        content = self.gen.generate(config)
        assert "## INVEST Checklist" not in content


# ---------------------------------------------------------------------------
# StoryGenerator -- docsmcp markers
# ---------------------------------------------------------------------------


class TestStoryGeneratorMarkers:
    """Tests for SmartMerger-compatible docsmcp markers."""

    def setup_method(self) -> None:
        self.gen = StoryGenerator()

    def test_standard_sections_have_markers(self) -> None:
        config = _make_config(style="standard")
        content = self.gen.generate(config)

        expected = [
            "user-story",
            "sizing",
            "purpose-intent",
            "description",
            "files",
            "tasks",
            "acceptance-criteria",
            "definition-of-done",
        ]
        for section in expected:
            assert f"<!-- docsmcp:start:{section} -->" in content, f"Missing start: {section}"
            assert f"<!-- docsmcp:end:{section} -->" in content, f"Missing end: {section}"

    def test_comprehensive_has_extra_markers(self) -> None:
        config = _make_config(style="comprehensive")
        content = self.gen.generate(config)

        extra = [
            "test-cases",
            "technical-notes",
            "dependencies",
            "invest",
        ]
        for section in extra:
            assert f"<!-- docsmcp:start:{section} -->" in content, f"Missing start: {section}"
            assert f"<!-- docsmcp:end:{section} -->" in content, f"Missing end: {section}"


# ---------------------------------------------------------------------------
# StoryGenerator -- empty inputs
# ---------------------------------------------------------------------------


class TestStoryGeneratorEmptyInputs:
    """Tests for story generation with minimal/empty inputs."""

    def setup_method(self) -> None:
        self.gen = StoryGenerator()

    def test_minimal_config(self) -> None:
        # Human mode — agent mode rejects configs with no files or AC.
        config = StoryConfig(title="Minimal Story", audience="human")
        content = self.gen.generate(config)
        assert "# Minimal Story" in content
        assert "## Tasks" in content
        assert "## Acceptance Criteria" in content
        assert "## Definition of Done" in content

    def test_all_empty_fields(self) -> None:
        config = StoryConfig(
            title="Empty",
            role="",
            want="",
            description="",
            tasks=[],
            acceptance_criteria=[],
            audience="human",
        )
        content = self.gen.generate(config)
        assert "# Empty" in content
        assert "[role]" in content or "Define" in content


# ---------------------------------------------------------------------------
# StoryGenerator -- auto-populate
# ---------------------------------------------------------------------------


class TestStoryGeneratorAutoPopulate:
    """Tests for auto-populate from project analyzers."""

    def setup_method(self) -> None:
        self.gen = StoryGenerator()

    def test_auto_populate_enriches_tech_stack(self, tmp_path: Path) -> None:
        mock_metadata = MagicMock()
        mock_metadata.name = "my-project"
        mock_metadata.python_requires = ">=3.12"
        mock_metadata.dependencies = ["fastapi"]

        with (
            patch(
                "docs_mcp.generators.metadata.MetadataExtractor",
            ) as mock_cls,
            patch(
                "docs_mcp.analyzers.module_map.ModuleMapAnalyzer",
                side_effect=RuntimeError,
            ),
        ):
            mock_cls.return_value.extract.return_value = mock_metadata
            config = _make_config(inherit_context=False)
            content = self.gen.generate(config, project_root=tmp_path, auto_populate=True)

        assert "my-project" in content

    def test_auto_populate_graceful_on_all_failures(self, tmp_path: Path) -> None:
        with (
            patch(
                "docs_mcp.generators.metadata.MetadataExtractor",
                side_effect=RuntimeError,
            ),
            patch(
                "docs_mcp.analyzers.module_map.ModuleMapAnalyzer",
                side_effect=RuntimeError,
            ),
        ):
            config = _make_config()
            content = self.gen.generate(config, project_root=tmp_path, auto_populate=True)

        assert "# Story 23.1 -- Test Story" in content

    def test_auto_populate_disabled_by_default(self) -> None:
        config = _make_config()
        content = self.gen.generate(config)
        assert "Tech Stack:" not in content


# ---------------------------------------------------------------------------
# StoryGenerator -- expert enrichment
# ---------------------------------------------------------------------------


class TestStoryExpertEnrichmentNoOp:
    """Issue #82: _enrich_experts is a no-op after EPIC-94 removal."""

    def test_enrich_experts_is_noop(self) -> None:
        from docs_mcp.generators.stories import StoryConfig, StoryGenerator

        config = StoryConfig(epic_number=1, story_number=1, title="Test")
        enrichment: dict[str, Any] = {}
        StoryGenerator._enrich_experts(config, enrichment)
        assert "expert_guidance" not in enrichment


# Note: TestStoryGeneratorExpertEnrichment was removed when the expert
# enrichment system was deleted (EPIC-94). The dead test class has been
# removed entirely rather than kept as commented-out code.


# ---------------------------------------------------------------------------
# StoryGenerator -- improved Gherkin scaffolding (Story 92.5)
# ---------------------------------------------------------------------------


class TestImprovedGherkinScaffolding:
    """Tests for improved Gherkin Given/When/Then derivation (Story 92.5).

    Verifies that role/want/AC context produces meaningful Gherkin clauses
    and that missing context falls back to bracket placeholders.
    """

    def setup_method(self) -> None:
        self.gen = StoryGenerator()

    # -- _derive_given -------------------------------------------------------

    def test_derive_given_with_role(self) -> None:
        result = StoryGenerator._derive_given("developer", "Login validates credentials")
        assert result == "a developer is ready to perform the action"

    def test_derive_given_empty_role_returns_empty(self) -> None:
        result = StoryGenerator._derive_given("", "Login validates credentials")
        assert result == ""

    def test_derive_given_whitespace_role_returns_empty(self) -> None:
        result = StoryGenerator._derive_given("   ", "Login validates credentials")
        assert result == ""

    # -- _derive_when --------------------------------------------------------

    def test_derive_when_uses_want_field(self) -> None:
        result = StoryGenerator._derive_when("developer", "to validate login credentials", "AC")
        assert result == "the developer validate login credentials"

    def test_derive_when_strips_to_prefix(self) -> None:
        result = StoryGenerator._derive_when("admin", "to manage users", "AC")
        assert result == "the admin manage users"

    def test_derive_when_want_without_to_prefix(self) -> None:
        result = StoryGenerator._derive_when("user", "submits the form", "AC")
        assert result == "the user submits the form"

    def test_derive_when_no_role_uses_the_user(self) -> None:
        result = StoryGenerator._derive_when("", "to validate login", "AC")
        assert result == "the user validate login"

    def test_derive_when_falls_back_to_ac_verb(self) -> None:
        result = StoryGenerator._derive_when("developer", "", "Login validates credentials")
        # First word of AC text as verb
        assert result.startswith("the developer login")

    def test_derive_when_no_want_no_role_uses_ac(self) -> None:
        result = StoryGenerator._derive_when("", "", "Validation rejects empty fields")
        assert result == "the user validation rejects empty fields"

    def test_derive_when_empty_want_and_ac_returns_empty(self) -> None:
        result = StoryGenerator._derive_when("", "", "")
        assert result == ""

    # -- _derive_then --------------------------------------------------------

    def test_derive_then_uses_ac_text(self) -> None:
        result = StoryGenerator._derive_then("Login validates credentials", "")
        assert result == "Login validates credentials successfully"

    def test_derive_then_strips_trailing_punctuation(self) -> None:
        result = StoryGenerator._derive_then("Feature works correctly.", "")
        assert result == "Feature works correctly successfully"

    def test_derive_then_falls_back_to_so_that(self) -> None:
        result = StoryGenerator._derive_then("", "invalid logins are rejected")
        assert result == "invalid logins are rejected"

    def test_derive_then_empty_returns_empty(self) -> None:
        result = StoryGenerator._derive_then("", "")
        assert result == ""

    # -- _render_gherkin_criteria with context --------------------------------

    def test_gherkin_with_role_and_want(self) -> None:
        config = _make_config(
            role="developer",
            want="to validate login credentials",
            acceptance_criteria=["Login validates credentials"],
            criteria_format="gherkin",
        )
        content = self.gen.generate(config)
        assert "Given a developer is ready to perform the action" in content
        assert "When the developer validate login credentials" in content
        assert "Login validates credentials successfully" in content

    def test_gherkin_fallback_without_role(self) -> None:
        config = _make_config(
            role="",
            want="",
            acceptance_criteria=["Feature works"],
            criteria_format="gherkin",
        )
        content = self.gen.generate(config)
        # Given falls back to bracket (no role)
        assert "Given [describe the precondition]" in content

    def test_gherkin_then_always_derived_from_ac(self) -> None:
        config = _make_config(
            acceptance_criteria=["Rate limit enforced"],
            criteria_format="gherkin",
        )
        content = self.gen.generate(config)
        assert "Then Rate limit enforced successfully" in content

    def test_gherkin_empty_criteria_unchanged(self) -> None:
        """Empty criteria case still renders the example block."""
        config = _make_config(acceptance_criteria=[], criteria_format="gherkin")
        content = self.gen.generate(config)
        assert "Feature: Example" in content
        assert "Given a precondition" in content


# ---------------------------------------------------------------------------
# MCP tool: docs_generate_story -- quick_start
# ---------------------------------------------------------------------------


class TestDocsGenerateStoryQuickStart:
    """Tests for quick_start parameter in ``docs_generate_story`` MCP tool."""

    async def _call(self, **kwargs: Any) -> dict[str, Any]:
        from docs_mcp.server_gen_tools import docs_generate_story

        return await docs_generate_story(**kwargs)

    async def test_quick_start_mcp_tool_produces_complete_story(
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
                title="Login Validation",
                epic_number=91,
                quick_start=True,
                project_root=str(root),
                audience="human",
                write_to_disk=True,
            )

        assert result["success"] is True
        assert result["data"]["quick_start"] is True
        assert "written_to" in result["data"]
        root = tmp_path / "proj"
        content = (root / result["data"]["written_to"]).read_text(encoding="utf-8")
        assert "**As a** developer" in content
        assert "**I want** to login validation" in content
        assert "**Points:** 3" in content
        assert "**Size:** M" in content

    async def test_quick_start_mcp_tool_explicit_role_overrides(
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
                title="Login Validation",
                epic_number=91,
                role="admin",
                quick_start=True,
                project_root=str(root),
                audience="human",
                write_to_disk=True,
            )

        assert result["success"] is True
        assert "written_to" in result["data"]
        root = tmp_path / "proj"
        content = (root / result["data"]["written_to"]).read_text(encoding="utf-8")
        assert "**As a** admin" in content
        assert "**As a** developer" not in content

    async def test_quick_start_false_in_response(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = await self._call(title="X", project_root=str(root), audience="human")

        assert result["success"] is True
        assert result["data"]["quick_start"] is False


# ---------------------------------------------------------------------------
# StoryGenerator -- generate_test_name
# ---------------------------------------------------------------------------


class TestGenerateTestName:
    """Tests for StoryGenerator.generate_test_name."""

    def test_long_ac_truncated_to_80_chars(self) -> None:
        long_ac = (
            "The upgrade pipeline calls generate_all_github_templates and generates "
            "CI workflows and governance files and security policies for the project"
        )
        name = StoryGenerator.generate_test_name(long_ac)
        assert len(name) <= 80

    def test_no_mid_word_truncation(self) -> None:
        long_ac = (
            "Results stored in result components github templates and governance "
            "files with proper validation and error handling for edge cases"
        )
        name = StoryGenerator.generate_test_name(long_ac)
        # Every segment between underscores should be a complete word.
        parts = name.split("_")
        for part in parts:
            assert part.isalnum(), f"Part {part!r} is not a complete alphanumeric word"
        assert len(name) <= 80

    def test_valid_python_identifier(self) -> None:
        name = StoryGenerator.generate_test_name("Validation rejects empty fields!")
        assert name.isidentifier()
        assert name.startswith("test_")

    def test_stopwords_removed(self) -> None:
        name = StoryGenerator.generate_test_name(
            "The user should be able to login with a valid password"
        )
        assert "_the_" not in name
        assert "_should_" not in name
        assert "_be_" not in name
        assert "_a_" not in name
        # Key content words should survive.
        assert "user" in name
        assert "login" in name
        assert "valid" in name
        assert "password" in name

    def test_numbered_ac_gets_index_prefix(self) -> None:
        name = StoryGenerator.generate_test_name("Generates templates", index=1)
        assert name.startswith("test_ac1_")
        assert "generates" in name
        assert "templates" in name

    def test_numbered_ac_index_3(self) -> None:
        name = StoryGenerator.generate_test_name("Error handling works", index=3)
        assert name.startswith("test_ac3_")

    def test_empty_ac_fallback(self) -> None:
        name = StoryGenerator.generate_test_name("")
        assert name == "test_story_acceptance"

    def test_empty_ac_with_index_fallback(self) -> None:
        name = StoryGenerator.generate_test_name("", index=2)
        assert name == "test_ac2_story_acceptance"

    def test_whitespace_only_fallback(self) -> None:
        name = StoryGenerator.generate_test_name("   ")
        assert name == "test_story_acceptance"

    def test_all_stopwords_fallback(self) -> None:
        name = StoryGenerator.generate_test_name("the and is are should")
        assert name == "test_story_acceptance"

    def test_special_characters_stripped(self) -> None:
        name = StoryGenerator.generate_test_name("Login (v2) works -- correctly!")
        assert name.isidentifier()
        assert "login" in name
        assert "v2" in name
        assert "works" in name
        assert "correctly" in name
        # No parentheses, dashes, or exclamation marks.
        assert "(" not in name
        assert ")" not in name
        assert "-" not in name
        assert "!" not in name

    def test_only_lowercase_and_underscores(self) -> None:
        name = StoryGenerator.generate_test_name("API Returns JSON Response")
        assert name == name.lower()
        assert re.match(r"^[a-z0-9_]+$", name)

    def test_short_ac_preserved(self) -> None:
        name = StoryGenerator.generate_test_name("Login works")
        assert name == "test_login_works"

    def test_render_test_cases_uses_generate_test_name(self) -> None:
        """Comprehensive style auto-generates test names from AC."""
        gen = StoryGenerator()
        config = _make_config(
            style="comprehensive",
            test_cases=[],
            acceptance_criteria=["Validation rejects empty fields", "Error messages displayed"],
        )
        content = gen.generate(config)
        assert "## Test Cases" in content
        assert "`test_ac1_validation_rejects_empty_fields`" in content
        assert "`test_ac2_error_messages_displayed`" in content


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

    def test_refs_collects_TAP_ids_from_dependencies(self) -> None:
        config = self._agent_config(dependencies=["TAP-496", "TAP-834"])
        content = self.gen.generate(config)
        assert "TAP-496" in content
        assert "TAP-834" in content

    def test_why_omitted_when_so_that_empty(self) -> None:
        config = self._agent_config(so_that="")
        content = self.gen.generate(config)
        assert "## Why" not in content

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
