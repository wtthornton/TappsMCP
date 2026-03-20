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

from docs_mcp.generators.stories import StoryConfig, StoryGenerator, StoryTask
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
        config = _make_config(description="")
        content = self.gen.generate(config)
        assert "Describe what this story delivers" in content

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
        config = _make_config(tasks=[])
        content = self.gen.generate(config)
        assert "- [ ] Define implementation tasks" in content

    def test_checkbox_acceptance_criteria(self) -> None:
        config = _make_config(criteria_format="checkbox")
        content = self.gen.generate(config)
        assert "## Acceptance Criteria" in content
        assert "- [ ] Validation rejects empty fields" in content
        assert "- [ ] Error messages displayed" in content

    def test_gherkin_acceptance_criteria(self) -> None:
        config = _make_config(criteria_format="gherkin")
        content = self.gen.generate(config)
        assert "```gherkin" in content
        assert "Given [describe the precondition]" in content
        assert "Then [describe the expected observable outcome]" in content

    def test_acceptance_criteria_placeholder_checkbox(self) -> None:
        config = _make_config(acceptance_criteria=[], criteria_format="checkbox")
        content = self.gen.generate(config)
        assert "- [ ] Feature works as specified" in content

    def test_acceptance_criteria_placeholder_gherkin(self) -> None:
        config = _make_config(acceptance_criteria=[], criteria_format="gherkin")
        content = self.gen.generate(config)
        assert "Feature: Example" in content

    def test_definition_of_done(self) -> None:
        config = _make_config()
        content = self.gen.generate(config)
        assert "## Definition of Done" in content
        assert "- [ ] Code reviewed and approved" in content
        assert "- [ ] Tests passing" in content


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
