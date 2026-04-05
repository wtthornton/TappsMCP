"""Tests for docs_mcp.generators.stories -- User Story document generation.

Covers StoryGenerator section rendering, style variants, criteria formats,
empty inputs, auto-populate with mocked analyzers, and the
``docs_generate_story`` MCP tool.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

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
        config = StoryConfig(title="Minimal Story")
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


class TestStoryGeneratorExpertEnrichment:
    """Tests for expert system enrichment in story auto-populate."""

    def setup_method(self) -> None:
        self.gen = StoryGenerator()

    def _mock_consult_expert(
        self, domain: str = "security", answer: str = "Validate all inputs.",
        confidence: float = 0.8, expert_name: str = "Security Expert",
    ) -> MagicMock:
        result = MagicMock()
        result.domain = domain
        result.expert_name = expert_name
        result.answer = answer
        result.confidence = confidence
        return result

    def test_expert_guidance_in_technical_notes(self, tmp_path: Path) -> None:
        mock_result = self._mock_consult_expert()

        with (
            patch(
                "docs_mcp.generators.metadata.MetadataExtractor",
                side_effect=RuntimeError,
            ),
            patch(
                "docs_mcp.analyzers.module_map.ModuleMapAnalyzer",
                side_effect=RuntimeError,
            ),
            patch(
                "tapps_core.experts.engine.consult_expert",
                return_value=mock_result,
            ),
        ):
            config = _make_config(style="comprehensive")
            content = self.gen.generate(config, project_root=tmp_path, auto_populate=True)

        assert "### Expert Recommendations" in content
        assert "**Security Expert** (80%)" in content
        assert "Validate all inputs." in content

    def test_expert_low_confidence_excluded(self, tmp_path: Path) -> None:
        mock_result = self._mock_consult_expert(confidence=0.1)

        with (
            patch(
                "docs_mcp.generators.metadata.MetadataExtractor",
                side_effect=RuntimeError,
            ),
            patch(
                "docs_mcp.analyzers.module_map.ModuleMapAnalyzer",
                side_effect=RuntimeError,
            ),
            patch(
                "tapps_core.experts.engine.consult_expert",
                return_value=mock_result,
            ),
        ):
            config = _make_config(style="comprehensive")
            content = self.gen.generate(config, project_root=tmp_path, auto_populate=True)

        assert "Expert Recommendations" not in content

    def test_expert_failure_graceful(self, tmp_path: Path) -> None:
        with (
            patch(
                "docs_mcp.generators.metadata.MetadataExtractor",
                side_effect=RuntimeError,
            ),
            patch(
                "docs_mcp.analyzers.module_map.ModuleMapAnalyzer",
                side_effect=RuntimeError,
            ),
            patch(
                "tapps_core.experts.engine.consult_expert",
                side_effect=RuntimeError("expert unavailable"),
            ),
        ):
            config = _make_config(style="comprehensive")
            content = self.gen.generate(config, project_root=tmp_path, auto_populate=True)

        assert "# Story 23.1 -- Test Story" in content
        assert "Expert Recommendations" not in content

    def test_security_expert_adds_dod_item(self, tmp_path: Path) -> None:
        mock_result = self._mock_consult_expert(domain="security")

        with (
            patch(
                "docs_mcp.generators.metadata.MetadataExtractor",
                side_effect=RuntimeError,
            ),
            patch(
                "docs_mcp.analyzers.module_map.ModuleMapAnalyzer",
                side_effect=RuntimeError,
            ),
            patch(
                "tapps_core.experts.engine.consult_expert",
                return_value=mock_result,
            ),
        ):
            config = _make_config()
            content = self.gen.generate(config, project_root=tmp_path, auto_populate=True)

        assert "- [ ] Security review completed" in content

    def test_testing_expert_adds_dod_item(self, tmp_path: Path) -> None:
        mock_result = self._mock_consult_expert(
            domain="testing", expert_name="Testing Expert",
            answer="Write property-based tests.",
        )

        with (
            patch(
                "docs_mcp.generators.metadata.MetadataExtractor",
                side_effect=RuntimeError,
            ),
            patch(
                "docs_mcp.analyzers.module_map.ModuleMapAnalyzer",
                side_effect=RuntimeError,
            ),
            patch(
                "tapps_core.experts.engine.consult_expert",
                return_value=mock_result,
            ),
        ):
            config = _make_config()
            content = self.gen.generate(config, project_root=tmp_path, auto_populate=True)

        assert "- [ ] Test coverage meets quality gate" in content

    def test_expert_consults_4_domains(self, tmp_path: Path) -> None:
        calls: list[str] = []

        def _capture(question: str, **_: Any) -> MagicMock:
            calls.append(question)
            result = MagicMock()
            result.domain = "security"
            result.expert_name = "Expert"
            result.answer = ""
            result.confidence = 0.0
            return result

        with (
            patch(
                "docs_mcp.generators.metadata.MetadataExtractor",
                side_effect=RuntimeError,
            ),
            patch(
                "docs_mcp.analyzers.module_map.ModuleMapAnalyzer",
                side_effect=RuntimeError,
            ),
            patch(
                "tapps_core.experts.engine.consult_expert",
                side_effect=_capture,
            ),
        ):
            config = _make_config(title="Auth Login", description="OAuth2 flow")
            self.gen.generate(config, project_root=tmp_path, auto_populate=True)

        assert len(calls) == 4  # security, testing, architecture, code-quality
        for call in calls:
            assert "Auth Login - OAuth2 flow" in call


# ---------------------------------------------------------------------------
# StoryGenerator -- slugify
# ---------------------------------------------------------------------------


class TestStorySlugify:
    """Tests for StoryGenerator._slugify."""

    def test_basic(self) -> None:
        assert StoryGenerator._slugify("Hello World") == "hello-world"

    def test_special_chars(self) -> None:
        assert StoryGenerator._slugify("Story (v2)!") == "story-v2"


# ---------------------------------------------------------------------------
# MCP tool: docs_generate_story
# ---------------------------------------------------------------------------


class TestDocsGenerateStoryTool:
    """Tests for the ``docs_generate_story`` MCP tool handler."""

    async def _call(self, **kwargs: Any) -> dict[str, Any]:
        from docs_mcp.server_gen_tools import docs_generate_story

        return await docs_generate_story(**kwargs)

    async def test_basic_success(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = await self._call(
                title="My Story",
                epic_number=10,
                story_number=1,
                project_root=str(root),
            )

        assert result["success"] is True
        assert result["data"]["title"] == "My Story"
        assert result["data"]["epic_number"] == 10
        assert result["data"]["story_number"] == 1
        assert "# Story 10.1 -- My Story" in result["data"]["content"]

    async def test_invalid_root(self, tmp_path: Path) -> None:
        bad_root = tmp_path / "does_not_exist"
        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(bad_root),
        ):
            result = await self._call(title="X", project_root=str(bad_root))

        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ROOT"

    async def test_invalid_tasks_json(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = await self._call(
                title="X",
                tasks="{bad",
                project_root=str(root),
            )

        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_TASKS"

    async def test_tasks_json_not_a_list(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = await self._call(
                title="X",
                tasks='{"desc": "oops"}',
                project_root=str(root),
            )

        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_TASKS"

    async def test_user_story_statement(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = await self._call(
                title="X",
                role="developer",
                want="to test features",
                so_that="quality improves",
                project_root=str(root),
            )

        assert result["success"] is True
        content = result["data"]["content"]
        assert "**As a** developer" in content
        assert "**I want** to test features" in content
        assert "**so that** quality improves" in content

    async def test_gherkin_criteria_format(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = await self._call(
                title="X",
                acceptance_criteria="Login works, Logout works",
                criteria_format="gherkin",
                project_root=str(root),
            )

        assert result["success"] is True
        assert "```gherkin" in result["data"]["content"]
        assert result["data"]["criteria_format"] == "gherkin"

    async def test_comprehensive_style(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = await self._call(
                title="X",
                style="comprehensive",
                project_root=str(root),
            )

        assert result["success"] is True
        assert "## INVEST Checklist" in result["data"]["content"]

    async def test_write_to_file(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = await self._call(
                title="Written Story",
                epic_number=10,
                story_number=1,
                output_path="docs/stories/STORY-10-1.md",
                project_root=str(root),
            )

        assert result["success"] is True
        assert result["data"]["written_to"] == "docs/stories/STORY-10-1.md"
        written = (root / "docs" / "stories" / "STORY-10-1.md").read_text(encoding="utf-8")
        assert "# Story 10.1 -- Written Story" in written

    async def test_tasks_json_parsing(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        tasks = json.dumps([
            {"description": "Create model", "file_path": "src/models.py"},
            {"description": "Write tests"},
        ])

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = await self._call(
                title="X",
                tasks=tasks,
                project_root=str(root),
            )

        assert result["success"] is True
        assert result["data"]["task_count"] == 2
        content = result["data"]["content"]
        assert "Create model (`src/models.py`)" in content
        assert "Write tests" in content

    async def test_comma_separated_fields(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = await self._call(
                title="X",
                acceptance_criteria="AC1, AC2",
                files="src/a.py, src/b.py",
                dependencies="Story 1, Story 2",
                technical_notes="Note1, Note2",
                project_root=str(root),
            )

        assert result["success"] is True
        content = result["data"]["content"]
        assert "- [ ] AC1" in content
        assert "`src/a.py`" in content

    async def test_generation_error_handling(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with (
            patch(
                "docs_mcp.server_gen_tools._get_settings",
                return_value=_make_settings(root),
            ),
            patch(
                "docs_mcp.generators.stories.StoryGenerator.generate",
                side_effect=RuntimeError("boom"),
            ),
        ):
            result = await self._call(title="X", project_root=str(root))

        assert result["success"] is False
        assert result["error"]["code"] == "GENERATION_ERROR"

    async def test_elapsed_ms_present(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = await self._call(title="X", project_root=str(root))

        assert "elapsed_ms" in result
        assert isinstance(result["elapsed_ms"], int)


# ---------------------------------------------------------------------------
# StoryGenerator -- quick_start mode (Story 92.3)
# ---------------------------------------------------------------------------


class TestQuickStartMode:
    """Tests for quick_start mode in StoryGenerator (Story 92.3).

    Verifies that ``quick_start=True`` infers defaults from the title alone
    and that explicit parameters always override inferred defaults.
    """

    def setup_method(self) -> None:
        self.gen = StoryGenerator()

    # -- _infer_story_defaults unit tests ------------------------------------

    def test_infer_defaults_sets_role(self) -> None:
        config = StoryConfig(title="Login Validation")
        result = StoryGenerator._infer_story_defaults(config)
        assert result.role == "developer"

    def test_infer_defaults_sets_want_from_title(self) -> None:
        config = StoryConfig(title="Login Validation")
        result = StoryGenerator._infer_story_defaults(config)
        assert result.want == "to login validation"

    def test_infer_defaults_sets_so_that(self) -> None:
        config = StoryConfig(title="Login Validation")
        result = StoryGenerator._infer_story_defaults(config)
        assert result.so_that == "the feature is delivered and tested"

    def test_infer_defaults_sets_points(self) -> None:
        config = StoryConfig(title="Login Validation")
        result = StoryGenerator._infer_story_defaults(config)
        assert result.points == 3

    def test_infer_defaults_sets_size(self) -> None:
        config = StoryConfig(title="Login Validation")
        result = StoryGenerator._infer_story_defaults(config)
        assert result.size == "M"

    def test_infer_defaults_sets_tasks_from_title(self) -> None:
        config = StoryConfig(title="Login Validation")
        result = StoryGenerator._infer_story_defaults(config)
        descriptions = [t.description for t in result.tasks]
        assert "Implement login validation" in descriptions
        assert "Write unit tests" in descriptions
        assert "Update documentation" in descriptions

    def test_infer_defaults_sets_ac_from_title(self) -> None:
        config = StoryConfig(title="Login Validation")
        result = StoryGenerator._infer_story_defaults(config)
        assert "Login Validation works as specified" in result.acceptance_criteria
        assert "Unit tests pass" in result.acceptance_criteria
        assert "Docs updated" in result.acceptance_criteria

    def test_infer_defaults_does_not_overwrite_explicit_role(self) -> None:
        config = StoryConfig(title="Login Validation", role="admin")
        result = StoryGenerator._infer_story_defaults(config)
        assert result.role == "admin"

    def test_infer_defaults_does_not_overwrite_explicit_want(self) -> None:
        config = StoryConfig(title="Login Validation", want="to secure the system")
        result = StoryGenerator._infer_story_defaults(config)
        assert result.want == "to secure the system"

    def test_infer_defaults_does_not_overwrite_explicit_points(self) -> None:
        config = StoryConfig(title="Login Validation", points=8)
        result = StoryGenerator._infer_story_defaults(config)
        assert result.points == 8

    def test_infer_defaults_does_not_overwrite_explicit_size(self) -> None:
        config = StoryConfig(title="Login Validation", size="XL")
        result = StoryGenerator._infer_story_defaults(config)
        assert result.size == "XL"

    def test_infer_defaults_does_not_overwrite_explicit_tasks(self) -> None:
        existing_tasks = [StoryTask(description="My custom task")]
        config = StoryConfig(title="Login Validation", tasks=existing_tasks)
        result = StoryGenerator._infer_story_defaults(config)
        assert len(result.tasks) == 1
        assert result.tasks[0].description == "My custom task"

    def test_infer_defaults_does_not_overwrite_explicit_ac(self) -> None:
        config = StoryConfig(title="X", acceptance_criteria=["Custom criterion"])
        result = StoryGenerator._infer_story_defaults(config)
        assert result.acceptance_criteria == ["Custom criterion"]

    def test_infer_defaults_empty_title_fallback(self) -> None:
        config = StoryConfig(title="")
        result = StoryGenerator._infer_story_defaults(config)
        assert result.want == "to implement the feature"
        descriptions = [t.description for t in result.tasks]
        assert "Implement the feature" in descriptions

    # -- generate() with quick_start=True ------------------------------------

    def test_quick_start_produces_complete_story(self) -> None:
        config = StoryConfig(title="Login Validation", epic_number=91)
        content = self.gen.generate(config, quick_start=True)
        assert "**As a** developer" in content
        assert "**I want** to login validation" in content
        assert "**so that** the feature is delivered and tested" in content
        assert "**Points:** 3" in content
        assert "**Size:** M" in content
        assert "- [ ] Implement login validation" in content
        assert "- [ ] Login Validation works as specified" in content

    def test_quick_start_false_unchanged(self) -> None:
        """quick_start=False (default) should not change behavior."""
        config = StoryConfig(title="Login Validation")
        content_default = self.gen.generate(config)
        content_explicit_false = self.gen.generate(config, quick_start=False)
        assert content_default == content_explicit_false

    def test_quick_start_explicit_role_overrides(self) -> None:
        config = StoryConfig(title="Add Search", role="data analyst")
        content = self.gen.generate(config, quick_start=True)
        assert "**As a** data analyst" in content
        assert "**As a** developer" not in content

    def test_quick_start_explicit_want_overrides(self) -> None:
        config = StoryConfig(title="Add Search", want="to search documents quickly")
        content = self.gen.generate(config, quick_start=True)
        assert "to search documents quickly" in content
        assert "to add search" not in content


# ---------------------------------------------------------------------------
# StoryGenerator -- task suggestion engine (Story 92.4)
# ---------------------------------------------------------------------------


class TestTaskSuggestionEngine:
    """Tests for _suggest_tasks keyword-to-task mapping (Story 92.4).

    Verifies that title/description keywords map to relevant task stubs,
    that user-provided tasks override suggestions, and that the fallback
    is used when no keywords match.
    """

    def setup_method(self) -> None:
        self.gen = StoryGenerator()

    # -- keyword pattern tests -----------------------------------------------

    def test_model_keyword_suggests_model_tasks(self) -> None:
        config = StoryConfig(title="User Model Update", tasks=[])
        tasks = StoryGenerator._suggest_tasks(config)
        descriptions = [t.description for t in tasks]
        assert "Define data model fields and relationships" in descriptions
        assert "Write migration script" in descriptions
        assert "Add model validation" in descriptions

    def test_schema_keyword_suggests_model_tasks(self) -> None:
        config = StoryConfig(title="Schema Migration", tasks=[])
        tasks = StoryGenerator._suggest_tasks(config)
        descriptions = [t.description for t in tasks]
        assert "Define data model fields and relationships" in descriptions

    def test_database_keyword_suggests_model_tasks(self) -> None:
        config = StoryConfig(title="Database Indexing", tasks=[])
        tasks = StoryGenerator._suggest_tasks(config)
        descriptions = [t.description for t in tasks]
        assert "Write migration script" in descriptions

    def test_endpoint_keyword_suggests_api_tasks(self) -> None:
        config = StoryConfig(title="Add login endpoint", tasks=[])
        tasks = StoryGenerator._suggest_tasks(config)
        descriptions = [t.description for t in tasks]
        assert "Define request/response schema" in descriptions
        assert "Implement endpoint handler" in descriptions
        assert "Add input validation" in descriptions
        assert "Add error responses" in descriptions

    def test_api_keyword_suggests_api_tasks(self) -> None:
        config = StoryConfig(title="REST API rate limiting", tasks=[])
        tasks = StoryGenerator._suggest_tasks(config)
        descriptions = [t.description for t in tasks]
        assert "Implement endpoint handler" in descriptions

    def test_route_keyword_suggests_api_tasks(self) -> None:
        config = StoryConfig(title="Route Authorization", tasks=[])
        tasks = StoryGenerator._suggest_tasks(config)
        descriptions = [t.description for t in tasks]
        assert "Add input validation" in descriptions

    def test_coverage_keyword_suggests_test_tasks(self) -> None:
        config = StoryConfig(title="Improve test coverage", tasks=[])
        tasks = StoryGenerator._suggest_tasks(config)
        descriptions = [t.description for t in tasks]
        assert "Write unit tests for happy path" in descriptions
        assert "Write edge case tests" in descriptions
        assert "Add integration test" in descriptions

    def test_ui_keyword_suggests_ui_tasks(self) -> None:
        config = StoryConfig(title="Dashboard UI redesign", tasks=[])
        tasks = StoryGenerator._suggest_tasks(config)
        descriptions = [t.description for t in tasks]
        assert "Create component scaffold" in descriptions
        assert "Add styling/CSS" in descriptions
        assert "Add accessibility attributes" in descriptions

    def test_component_keyword_suggests_ui_tasks(self) -> None:
        config = StoryConfig(title="Header component", tasks=[])
        tasks = StoryGenerator._suggest_tasks(config)
        descriptions = [t.description for t in tasks]
        assert "Create component scaffold" in descriptions

    def test_form_keyword_suggests_ui_tasks(self) -> None:
        config = StoryConfig(title="Contact form", tasks=[])
        tasks = StoryGenerator._suggest_tasks(config)
        descriptions = [t.description for t in tasks]
        assert "Add form validation" in descriptions

    def test_validate_keyword_suggests_validation_tasks(self) -> None:
        config = StoryConfig(title="Validate user input", tasks=[])
        tasks = StoryGenerator._suggest_tasks(config)
        descriptions = [t.description for t in tasks]
        assert "Define validation rules" in descriptions
        assert "Implement validation logic" in descriptions
        assert "Add validation error messages" in descriptions

    def test_validation_keyword_suggests_validation_tasks(self) -> None:
        config = StoryConfig(title="Add input validation", tasks=[])
        tasks = StoryGenerator._suggest_tasks(config)
        descriptions = [t.description for t in tasks]
        assert "Define validation rules" in descriptions

    def test_auth_keyword_suggests_auth_tasks(self) -> None:
        config = StoryConfig(title="Auth middleware", tasks=[])
        tasks = StoryGenerator._suggest_tasks(config)
        descriptions = [t.description for t in tasks]
        assert "Implement auth flow" in descriptions
        assert "Add token generation/validation" in descriptions
        assert "Add session management" in descriptions

    def test_login_keyword_suggests_auth_tasks(self) -> None:
        config = StoryConfig(title="Add user login endpoint", tasks=[])
        tasks = StoryGenerator._suggest_tasks(config)
        descriptions = [t.description for t in tasks]
        # "endpoint" or "login" may match first, both produce relevant tasks
        assert len(tasks) >= 3

    def test_token_keyword_suggests_auth_tasks(self) -> None:
        config = StoryConfig(title="JWT token refresh", tasks=[])
        tasks = StoryGenerator._suggest_tasks(config)
        descriptions = [t.description for t in tasks]
        assert "Implement auth flow" in descriptions

    # -- fallback and edge cases ---------------------------------------------

    def test_no_keyword_match_fallback_to_generic(self) -> None:
        config = StoryConfig(title="Rate Limiter", tasks=[])
        tasks = StoryGenerator._suggest_tasks(config)
        descriptions = [t.description for t in tasks]
        assert "Implement rate limiter" in descriptions
        assert "Write unit tests" in descriptions
        assert "Update documentation" in descriptions

    def test_empty_title_returns_empty_list(self) -> None:
        config = StoryConfig(title="", tasks=[])
        tasks = StoryGenerator._suggest_tasks(config)
        assert tasks == []

    def test_whitespace_title_returns_empty_list(self) -> None:
        config = StoryConfig(title="   ", tasks=[])
        tasks = StoryGenerator._suggest_tasks(config)
        assert tasks == []

    # -- file_path association -----------------------------------------------

    def test_first_file_associated_with_first_task(self) -> None:
        config = StoryConfig(
            title="Rate Limiter",
            tasks=[],
            files=["src/rate_limiter.py", "tests/test_rate_limiter.py"],
        )
        tasks = StoryGenerator._suggest_tasks(config)
        assert len(tasks) >= 1
        assert tasks[0].file_path == "src/rate_limiter.py"
        # Subsequent tasks have no file_path
        assert tasks[1].file_path == ""

    def test_no_files_tasks_have_no_file_path(self) -> None:
        config = StoryConfig(title="Rate Limiter", tasks=[])
        tasks = StoryGenerator._suggest_tasks(config)
        for task in tasks:
            assert task.file_path == ""

    # -- integration with _render_tasks -------------------------------------

    def test_render_tasks_uses_suggestion_engine(self) -> None:
        config = StoryConfig(title="Database Migration", tasks=[])
        content = self.gen.generate(config)
        assert "## Tasks" in content
        assert "- [ ] Define data model fields and relationships" in content

    def test_render_tasks_empty_title_shows_placeholder(self) -> None:
        config = StoryConfig(title="", tasks=[])
        content = self.gen.generate(config)
        assert "- [ ] Define implementation tasks..." in content

    def test_user_provided_tasks_override_suggestions(self) -> None:
        custom_task = StoryTask(description="My custom task")
        config = StoryConfig(title="Database Migration", tasks=[custom_task])
        content = self.gen.generate(config)
        assert "- [ ] My custom task" in content
        assert "Define data model fields and relationships" not in content


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
        self, tmp_path: Path,
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
            )

        assert result["success"] is True
        assert result["data"]["quick_start"] is True
        content = result["data"]["content"]
        assert "**As a** developer" in content
        assert "**I want** to login validation" in content
        assert "**Points:** 3" in content
        assert "**Size:** M" in content

    async def test_quick_start_mcp_tool_explicit_role_overrides(
        self, tmp_path: Path,
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
            )

        assert result["success"] is True
        content = result["data"]["content"]
        assert "**As a** admin" in content
        assert "**As a** developer" not in content

    async def test_quick_start_false_in_response(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = await self._call(title="X", project_root=str(root))

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
