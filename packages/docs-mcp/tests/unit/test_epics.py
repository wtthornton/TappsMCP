"""Tests for docs_mcp.generators.epics -- Epic document generation.

Covers EpicGenerator section rendering, style variants, empty inputs,
auto-populate with mocked analyzers, parse_stories_json, and the
``docs_generate_epic`` MCP tool.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from docs_mcp.generators.epics import EpicConfig, EpicGenerator, EpicStoryStub


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro: Any) -> Any:
    """Run an async coroutine synchronously for testing."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_settings(root: Path) -> MagicMock:
    """Create a mock DocsMCPSettings pointing to *root*."""
    settings = MagicMock()
    settings.project_root = root
    settings.output_dir = "docs"
    settings.default_style = "standard"
    settings.default_format = "markdown"
    settings.include_toc = True
    settings.include_badges = True
    settings.changelog_format = "keep-a-changelog"
    settings.adr_format = "madr"
    settings.diagram_format = "mermaid"
    settings.git_log_limit = 100
    settings.log_level = "INFO"
    settings.log_json = False
    return settings


def _make_config(**kwargs: Any) -> EpicConfig:
    """Build an EpicConfig with sensible defaults."""
    defaults: dict[str, Any] = {
        "title": "Test Epic",
        "number": 42,
        "goal": "Deliver the feature.",
        "motivation": "Users need it.",
        "status": "Proposed",
        "priority": "P1 - High",
        "estimated_loe": "~2 weeks",
        "dependencies": ["Epic 0", "Epic 4"],
        "blocks": ["Epic 43"],
        "acceptance_criteria": ["Feature works", "Tests pass"],
        "stories": [
            EpicStoryStub(title="Data Models", points=3, description="Create Pydantic models."),
            EpicStoryStub(title="API Endpoints", points=5),
        ],
        "technical_notes": ["Use SQLite for storage"],
        "risks": ["Schema migration complexity"],
        "non_goals": ["Mobile support"],
        "style": "standard",
    }
    defaults.update(kwargs)
    return EpicConfig(**defaults)


# ---------------------------------------------------------------------------
# EpicStoryStub model
# ---------------------------------------------------------------------------


class TestEpicStoryStub:
    """Tests for the EpicStoryStub Pydantic model."""

    def test_defaults(self) -> None:
        stub = EpicStoryStub(title="My Story")
        assert stub.title == "My Story"
        assert stub.points == 0
        assert stub.description == ""

    def test_with_all_fields(self) -> None:
        stub = EpicStoryStub(title="Auth", points=5, description="Add authentication.")
        assert stub.title == "Auth"
        assert stub.points == 5
        assert stub.description == "Add authentication."


# ---------------------------------------------------------------------------
# EpicConfig model
# ---------------------------------------------------------------------------


class TestEpicConfig:
    """Tests for the EpicConfig Pydantic model."""

    def test_defaults(self) -> None:
        config = EpicConfig(title="My Epic")
        assert config.title == "My Epic"
        assert config.number == 0
        assert config.goal == ""
        assert config.stories == []
        assert config.style == "standard"

    def test_style_values(self) -> None:
        config = EpicConfig(title="X", style="comprehensive")
        assert config.style == "comprehensive"


# ---------------------------------------------------------------------------
# EpicGenerator -- section rendering
# ---------------------------------------------------------------------------


class TestEpicGeneratorSections:
    """Tests for individual section rendering in EpicGenerator."""

    def setup_method(self) -> None:
        self.gen = EpicGenerator()

    def test_title_with_number(self) -> None:
        config = _make_config(title="Auth System", number=23)
        content = self.gen.generate(config)
        assert content.startswith("# Epic 23: Auth System")

    def test_title_without_number(self) -> None:
        config = _make_config(title="Auth System", number=0)
        content = self.gen.generate(config)
        assert content.startswith("# Auth System")

    def test_metadata_block(self) -> None:
        config = _make_config()
        content = self.gen.generate(config)
        assert "**Status:** Proposed" in content
        assert "**Priority:** P1 - High" in content
        assert "**Estimated LOE:** ~2 weeks" in content
        assert "**Dependencies:** Epic 0, Epic 4" in content
        assert "**Blocks:** Epic 43" in content

    def test_goal_with_text(self) -> None:
        config = _make_config(goal="Build a memory system.")
        content = self.gen.generate(config)
        assert "## Goal" in content
        assert "Build a memory system." in content

    def test_goal_placeholder(self) -> None:
        config = _make_config(goal="")
        content = self.gen.generate(config)
        assert "Describe the measurable outcome" in content

    def test_motivation_with_text(self) -> None:
        config = _make_config(motivation="Users lose context across sessions.")
        content = self.gen.generate(config)
        assert "## Motivation" in content
        assert "Users lose context across sessions." in content

    def test_motivation_placeholder(self) -> None:
        config = _make_config(motivation="")
        content = self.gen.generate(config)
        assert "Explain why this work matters" in content

    def test_acceptance_criteria_rendered(self) -> None:
        config = _make_config(acceptance_criteria=["AC1", "AC2", "AC3"])
        content = self.gen.generate(config)
        assert "## Acceptance Criteria" in content
        assert "- [ ] AC1" in content
        assert "- [ ] AC2" in content
        assert "- [ ] AC3" in content

    def test_acceptance_criteria_placeholder(self) -> None:
        config = _make_config(acceptance_criteria=[])
        content = self.gen.generate(config)
        assert "- [ ] Define verifiable acceptance criteria" in content

    def test_stories_rendered(self) -> None:
        config = _make_config()
        content = self.gen.generate(config)
        assert "## Stories" in content
        assert "### 42.1 -- Data Models" in content
        assert "**Points:** 3" in content
        assert "Create Pydantic models." in content
        assert "### 42.2 -- API Endpoints" in content
        assert "**Points:** 5" in content
        # Tasks should be contextual, not generic
        assert "- [ ] Implement data models" in content
        assert "- [ ] Write unit tests" in content

    def test_stories_placeholder(self) -> None:
        config = _make_config(stories=[], number=10)
        content = self.gen.generate(config)
        assert "### 10.1 -- Story Title" in content
        assert "### 10.2 -- Story Title" in content

    def test_technical_notes_rendered(self) -> None:
        config = _make_config(technical_notes=["Use async/await", "SQLite WAL mode"])
        content = self.gen.generate(config)
        assert "## Technical Notes" in content
        assert "- Use async/await" in content
        assert "- SQLite WAL mode" in content

    def test_technical_notes_placeholder(self) -> None:
        config = _make_config(technical_notes=[])
        content = self.gen.generate(config)
        assert "- Document architecture decisions" in content

    def test_non_goals_rendered(self) -> None:
        config = _make_config(non_goals=["Mobile app", "i18n"])
        content = self.gen.generate(config)
        assert "## Out of Scope" in content
        assert "- Mobile app" in content
        assert "- i18n" in content

    def test_non_goals_placeholder(self) -> None:
        config = _make_config(non_goals=[])
        content = self.gen.generate(config)
        assert "- Define what is explicitly deferred" in content


# ---------------------------------------------------------------------------
# EpicGenerator -- style variants
# ---------------------------------------------------------------------------


class TestEpicGeneratorStyles:
    """Tests for standard vs comprehensive style."""

    def setup_method(self) -> None:
        self.gen = EpicGenerator()

    def test_standard_no_extra_sections(self) -> None:
        config = _make_config(style="standard")
        content = self.gen.generate(config)
        assert "## Implementation Order" not in content
        assert "## Risk Assessment" not in content
        assert "## Files Affected" not in content
        assert "## Performance Targets" not in content

    def test_comprehensive_has_implementation_order(self) -> None:
        config = _make_config(style="comprehensive")
        content = self.gen.generate(config)
        assert "## Implementation Order" in content
        assert "Story 42.1: Data Models" in content
        assert "Story 42.2: API Endpoints" in content

    def test_comprehensive_has_risk_assessment(self) -> None:
        config = _make_config(style="comprehensive")
        content = self.gen.generate(config)
        assert "## Risk Assessment" in content
        assert "Schema migration complexity" in content
        # Risk auto-classification replaces "Define mitigation strategy"
        assert "High" in content  # "migration" keyword -> High impact

    def test_comprehensive_has_files_affected(self) -> None:
        config = _make_config(style="comprehensive")
        content = self.gen.generate(config)
        assert "## Files Affected" in content

    def test_comprehensive_omits_performance_targets_without_expert(self) -> None:
        """Performance targets are only rendered when performance expert advice exists."""
        config = _make_config(style="comprehensive")
        content = self.gen.generate(config)
        # Without auto_populate/expert advice, performance targets are omitted.
        assert "## Performance Targets" not in content

    def test_invalid_style_falls_back_to_standard(self) -> None:
        config = _make_config(style="unknown")
        content = self.gen.generate(config)
        assert "## Implementation Order" not in content
        assert "## Risk Assessment" not in content


# ---------------------------------------------------------------------------
# EpicGenerator -- docsmcp markers
# ---------------------------------------------------------------------------


class TestEpicGeneratorMarkers:
    """Tests for SmartMerger-compatible docsmcp markers."""

    def setup_method(self) -> None:
        self.gen = EpicGenerator()

    def test_standard_sections_have_markers(self) -> None:
        config = _make_config(style="standard")
        content = self.gen.generate(config)

        expected = [
            "metadata",
            "goal",
            "motivation",
            "acceptance-criteria",
            "stories",
            "technical-notes",
            "non-goals",
        ]
        for section in expected:
            assert f"<!-- docsmcp:start:{section} -->" in content, f"Missing start: {section}"
            assert f"<!-- docsmcp:end:{section} -->" in content, f"Missing end: {section}"

    def test_comprehensive_has_extra_markers(self) -> None:
        config = _make_config(style="comprehensive")
        content = self.gen.generate(config)

        # These sections are always present in comprehensive mode.
        always_present = [
            "success-metrics",
            "implementation-order",
            "risk-assessment",
            "files-affected",
        ]
        for section in always_present:
            assert f"<!-- docsmcp:start:{section} -->" in content, f"Missing start: {section}"
            assert f"<!-- docsmcp:end:{section} -->" in content, f"Missing end: {section}"
        # performance-targets is only present when expert advice exists.
        # stakeholders and references are only present when provided.


# ---------------------------------------------------------------------------
# EpicGenerator -- empty inputs
# ---------------------------------------------------------------------------


class TestEpicGeneratorEmptyInputs:
    """Tests for epic generation with minimal/empty inputs."""

    def setup_method(self) -> None:
        self.gen = EpicGenerator()

    def test_minimal_config(self) -> None:
        config = EpicConfig(title="Minimal Epic")
        content = self.gen.generate(config)
        assert "# Minimal Epic" in content
        assert "## Goal" in content
        assert "## Stories" in content
        assert "## Acceptance Criteria" in content

    def test_all_empty_fields(self) -> None:
        config = EpicConfig(
            title="Empty",
            goal="",
            motivation="",
            acceptance_criteria=[],
            stories=[],
            technical_notes=[],
            non_goals=[],
        )
        content = self.gen.generate(config)
        assert "# Empty" in content
        assert "Describe" in content or "Define" in content


# ---------------------------------------------------------------------------
# EpicGenerator -- auto-populate
# ---------------------------------------------------------------------------


class TestEpicGeneratorAutoPopulate:
    """Tests for auto-populate from project analyzers."""

    def setup_method(self) -> None:
        self.gen = EpicGenerator()

    def test_auto_populate_enriches_tech_stack(self, tmp_path: Path) -> None:
        mock_metadata = MagicMock()
        mock_metadata.name = "my-project"
        mock_metadata.python_requires = ">=3.12"
        mock_metadata.dependencies = ["fastapi", "pydantic"]

        with (
            patch(
                "docs_mcp.generators.metadata.MetadataExtractor",
            ) as mock_cls,
            patch(
                "docs_mcp.analyzers.module_map.ModuleMapAnalyzer",
                side_effect=RuntimeError,
            ),
            patch(
                "docs_mcp.analyzers.git_history.GitHistoryAnalyzer",
                side_effect=RuntimeError,
            ),
        ):
            mock_cls.return_value.extract.return_value = mock_metadata
            config = _make_config()
            content = self.gen.generate(config, project_root=tmp_path, auto_populate=True)

        assert "my-project" in content
        assert "Python >=3.12" in content

    def test_auto_populate_enriches_module_summary(self, tmp_path: Path) -> None:
        mock_module_map = MagicMock()
        mock_module_map.total_packages = 5
        mock_module_map.total_modules = 20
        mock_module_map.public_api_count = 42

        with (
            patch(
                "docs_mcp.generators.metadata.MetadataExtractor",
                side_effect=RuntimeError,
            ),
            patch(
                "docs_mcp.analyzers.module_map.ModuleMapAnalyzer",
            ) as mock_cls,
            patch(
                "docs_mcp.analyzers.git_history.GitHistoryAnalyzer",
                side_effect=RuntimeError,
            ),
        ):
            mock_cls.return_value.analyze.return_value = mock_module_map
            config = _make_config()
            content = self.gen.generate(config, project_root=tmp_path, auto_populate=True)

        assert "5 packages" in content
        assert "20 modules" in content

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
            patch(
                "docs_mcp.analyzers.git_history.GitHistoryAnalyzer",
                side_effect=RuntimeError,
            ),
        ):
            config = _make_config()
            content = self.gen.generate(config, project_root=tmp_path, auto_populate=True)

        assert "# Epic 42: Test Epic" in content

    def test_auto_populate_disabled_by_default(self) -> None:
        config = _make_config()
        content = self.gen.generate(config)
        assert "Tech Stack:" not in content


# ---------------------------------------------------------------------------
# EpicGenerator -- expert enrichment
# ---------------------------------------------------------------------------


class TestEpicGeneratorExpertEnrichment:
    """Tests for expert system enrichment in auto-populate."""

    def setup_method(self) -> None:
        self.gen = EpicGenerator()

    def _mock_consult_expert(
        self, domain: str = "security", answer: str = "Use input validation.",
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
                "docs_mcp.analyzers.git_history.GitHistoryAnalyzer",
                side_effect=RuntimeError,
            ),
            patch(
                "tapps_core.experts.engine.consult_expert",
                return_value=mock_result,
            ),
        ):
            config = _make_config()
            content = self.gen.generate(config, project_root=tmp_path, auto_populate=True)

        assert "### Expert Recommendations" in content
        assert "**Security Expert** (80%)" in content
        assert "Use input validation." in content

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
                "docs_mcp.analyzers.git_history.GitHistoryAnalyzer",
                side_effect=RuntimeError,
            ),
            patch(
                "tapps_core.experts.engine.consult_expert",
                return_value=mock_result,
            ),
        ):
            config = _make_config()
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
                "docs_mcp.analyzers.git_history.GitHistoryAnalyzer",
                side_effect=RuntimeError,
            ),
            patch(
                "tapps_core.experts.engine.consult_expert",
                side_effect=RuntimeError("expert unavailable"),
            ),
        ):
            config = _make_config()
            content = self.gen.generate(config, project_root=tmp_path, auto_populate=True)

        assert "# Epic 42: Test Epic" in content
        assert "Expert Recommendations" not in content

    def test_expert_risks_in_comprehensive(self, tmp_path: Path) -> None:
        mock_result = self._mock_consult_expert(
            domain="security", answer="SQL injection risk in user input handling.",
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
                "docs_mcp.analyzers.git_history.GitHistoryAnalyzer",
                side_effect=RuntimeError,
            ),
            patch(
                "tapps_core.experts.engine.consult_expert",
                return_value=mock_result,
            ),
        ):
            config = _make_config(style="comprehensive")
            content = self.gen.generate(config, project_root=tmp_path, auto_populate=True)

        assert "Expert-Identified Risks" in content
        assert "SQL injection risk" in content

    def test_expert_import_failure_graceful(self, tmp_path: Path) -> None:
        """When tapps_core is not available, expert enrichment is skipped."""
        import importlib

        original_import = importlib.import_module

        def _block_tapps_core(name: str, *args: Any, **kwargs: Any) -> Any:
            if "tapps_core" in name:
                raise ImportError("no tapps_core")
            return original_import(name, *args, **kwargs)

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
                "docs_mcp.analyzers.git_history.GitHistoryAnalyzer",
                side_effect=RuntimeError,
            ),
            patch(
                "tapps_core.experts.engine.consult_expert",
                side_effect=ImportError("no tapps_core"),
            ),
        ):
            config = _make_config()
            # Should not raise — expert enrichment is optional.
            content = self.gen.generate(config, project_root=tmp_path, auto_populate=True)

        assert "# Epic 42: Test Epic" in content

    def test_expert_uses_goal_in_context(self, tmp_path: Path) -> None:
        calls: list[str] = []

        def _capture_consult(question: str, **_: Any) -> MagicMock:
            calls.append(question)
            result = MagicMock()
            result.domain = "security"
            result.expert_name = "Security Expert"
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
                "docs_mcp.analyzers.git_history.GitHistoryAnalyzer",
                side_effect=RuntimeError,
            ),
            patch(
                "tapps_core.experts.engine.consult_expert",
                side_effect=_capture_consult,
            ),
        ):
            config = _make_config(title="Auth System", goal="Implement OAuth2")
            self.gen.generate(config, project_root=tmp_path, auto_populate=True)

        assert len(calls) == 8  # 8 expert domains
        for call in calls:
            assert "Auth System - Implement OAuth2" in call


# ---------------------------------------------------------------------------
# EpicGenerator -- parse_stories_json
# ---------------------------------------------------------------------------


class TestParseStoriesJson:
    """Tests for EpicGenerator.parse_stories_json."""

    def test_valid_json(self) -> None:
        raw = json.dumps([
            {"title": "Models", "points": 3, "description": "Create models."},
            {"title": "API", "points": 5},
        ])
        stories = EpicGenerator.parse_stories_json(raw)
        assert len(stories) == 2
        assert stories[0].title == "Models"
        assert stories[0].points == 3
        assert stories[1].title == "API"

    def test_empty_string(self) -> None:
        stories = EpicGenerator.parse_stories_json("")
        assert stories == []

    def test_whitespace_string(self) -> None:
        stories = EpicGenerator.parse_stories_json("   ")
        assert stories == []

    def test_invalid_json(self) -> None:
        with pytest.raises(ValueError, match="Invalid JSON"):
            EpicGenerator.parse_stories_json("{bad json}")

    def test_not_a_list(self) -> None:
        with pytest.raises(ValueError, match="must be a list"):
            EpicGenerator.parse_stories_json('{"title": "oops"}')

    def test_skips_non_dict_items(self) -> None:
        raw = json.dumps([{"title": "Valid"}, "not-a-dict", 42])
        stories = EpicGenerator.parse_stories_json(raw)
        assert len(stories) == 1
        assert stories[0].title == "Valid"


# ---------------------------------------------------------------------------
# EpicGenerator -- slugify
# ---------------------------------------------------------------------------


class TestEpicSlugify:
    """Tests for EpicGenerator._slugify."""

    def test_basic(self) -> None:
        assert EpicGenerator._slugify("Hello World") == "hello-world"

    def test_special_chars(self) -> None:
        assert EpicGenerator._slugify("Epic (v2)!") == "epic-v2"


# ---------------------------------------------------------------------------
# EpicGenerator -- status validation
# ---------------------------------------------------------------------------


class TestEpicStatusValidation:
    """Tests for status field behavior."""

    def setup_method(self) -> None:
        self.gen = EpicGenerator()

    def test_valid_statuses(self) -> None:
        for status in ["Proposed", "In Progress", "Complete", "Blocked", "Cancelled"]:
            config = _make_config(status=status)
            content = self.gen.generate(config)
            assert f"**Status:** {status}" in content

    def test_invalid_status_defaults_to_proposed(self) -> None:
        config = _make_config(status="Invalid")
        content = self.gen.generate(config)
        assert "**Status:** Proposed" in content


# ---------------------------------------------------------------------------
# MCP tool: docs_generate_epic
# ---------------------------------------------------------------------------


class TestDocsGenerateEpicTool:
    """Tests for the ``docs_generate_epic`` MCP tool handler."""

    def _call(self, **kwargs: Any) -> dict[str, Any]:
        from docs_mcp.server_gen_tools import docs_generate_epic

        return _run(docs_generate_epic(**kwargs))

    def test_basic_success(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = self._call(title="My Feature", number=10, project_root=str(root))

        assert result["success"] is True
        assert result["data"]["title"] == "My Feature"
        assert result["data"]["number"] == 10
        assert "# Epic 10: My Feature" in result["data"]["content"]

    def test_invalid_root(self, tmp_path: Path) -> None:
        bad_root = tmp_path / "does_not_exist"
        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(bad_root),
        ):
            result = self._call(title="X", project_root=str(bad_root))

        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ROOT"

    def test_invalid_stories_json(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = self._call(
                title="X",
                stories="{bad",
                project_root=str(root),
            )

        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_STORIES"

    def test_comma_separated_fields(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = self._call(
                title="X",
                dependencies="Epic 0, Epic 4",
                blocks="Epic 43",
                acceptance_criteria="AC1, AC2",
                technical_notes="Note1, Note2",
                non_goals="NG1, NG2",
                project_root=str(root),
            )

        assert result["success"] is True
        content = result["data"]["content"]
        assert "Epic 0, Epic 4" in content
        assert "- [ ] AC1" in content
        assert "- [ ] AC2" in content
        assert "- Note1" in content
        assert "- NG1" in content

    def test_comprehensive_style(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = self._call(
                title="X",
                style="comprehensive",
                project_root=str(root),
            )

        assert result["success"] is True
        assert "## Implementation Order" in result["data"]["content"]

    def test_write_to_file(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = self._call(
                title="Written Epic",
                number=99,
                output_path="docs/epics/EPIC-99.md",
                project_root=str(root),
            )

        assert result["success"] is True
        assert result["data"]["written_to"] == "docs/epics/EPIC-99.md"
        written = (root / "docs" / "epics" / "EPIC-99.md").read_text(encoding="utf-8")
        assert "# Epic 99: Written Epic" in written

    def test_stories_json_parsing(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        stories = json.dumps([
            {"title": "Data Models", "points": 3},
            {"title": "API", "points": 5},
        ])

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = self._call(
                title="X",
                number=10,
                stories=stories,
                project_root=str(root),
            )

        assert result["success"] is True
        assert result["data"]["story_count"] == 2
        assert "### 10.1 -- Data Models" in result["data"]["content"]
        assert "### 10.2 -- API" in result["data"]["content"]

    def test_generation_error_handling(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with (
            patch(
                "docs_mcp.server_gen_tools._get_settings",
                return_value=_make_settings(root),
            ),
            patch(
                "docs_mcp.generators.epics.EpicGenerator.generate",
                side_effect=RuntimeError("boom"),
            ),
        ):
            result = self._call(title="X", project_root=str(root))

        assert result["success"] is False
        assert result["error"]["code"] == "GENERATION_ERROR"

    def test_elapsed_ms_present(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = self._call(title="X", project_root=str(root))

        assert "elapsed_ms" in result
        assert isinstance(result["elapsed_ms"], int)


# ---------------------------------------------------------------------------
# Epic 18: Risk auto-classification
# ---------------------------------------------------------------------------

class TestEpicRiskAutoClassification:
    """Tests for risk auto-classification in comprehensive mode."""

    def setup_method(self) -> None:
        self.gen = EpicGenerator()

    def test_risk_auto_classifies_keywords(self) -> None:
        config = _make_config(style="comprehensive", risks=["Authentication bypass vulnerability"])
        content = self.gen.generate(config)
        assert "## Risk Assessment" in content
        assert "High" in content  # auth -> High impact

    def test_risk_no_placeholder_mitigation(self) -> None:
        config = _make_config(style="comprehensive", risks=["General risk"])
        content = self.gen.generate(config)
        assert "Define mitigation strategy" not in content
        assert "Mitigation required" in content

    def test_risk_empty_list_no_placeholder(self) -> None:
        config = _make_config(style="comprehensive", risks=[])
        content = self.gen.generate(config)
        assert "## Risk Assessment" in content
        assert "No risks identified" in content


# ---------------------------------------------------------------------------
# Epic 18: Expert filtering
# ---------------------------------------------------------------------------

class TestEpicExpertFiltering:
    """Tests for expert guidance filtering (Epic 18.3)."""

    def setup_method(self) -> None:
        self.gen = EpicGenerator()

    def test_filter_below_30_suppressed(self) -> None:
        guidance = [{"domain": "security", "expert": "X", "advice": "Real advice", "confidence": "25%"}]
        result = EpicGenerator._filter_expert_guidance(guidance)
        assert len(result) == 0

    def test_filter_30_to_50_flagged(self) -> None:
        guidance = [{"domain": "security", "expert": "X", "advice": "Real advice", "confidence": "40%"}]
        result = EpicGenerator._filter_expert_guidance(guidance)
        assert len(result) == 1
        assert "Expert review recommended" in result[0]["advice"]

    def test_filter_above_50_rendered(self) -> None:
        guidance = [{"domain": "security", "expert": "X", "advice": "Use input validation.", "confidence": "85%"}]
        result = EpicGenerator._filter_expert_guidance(guidance)
        assert len(result) == 1
        assert result[0]["advice"] == "Use input validation."

    def test_filter_no_knowledge_suppressed(self) -> None:
        guidance = [{"domain": "security", "expert": "X", "advice": "No specific knowledge found for this domain.", "confidence": "30%"}]
        result = EpicGenerator._filter_expert_guidance(guidance)
        assert len(result) == 0

    def test_filter_empty_advice_suppressed(self) -> None:
        guidance = [{"domain": "security", "expert": "X", "advice": "", "confidence": "85%"}]
        result = EpicGenerator._filter_expert_guidance(guidance)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Epic 18.5: Performance targets suppression
# ---------------------------------------------------------------------------

class TestEpicPerformanceTargetsSuppression:
    """Tests for performance targets section suppression."""

    def setup_method(self) -> None:
        self.gen = EpicGenerator()

    def test_omitted_without_expert(self) -> None:
        config = _make_config(style="comprehensive")
        content = self.gen.generate(config)
        assert "## Performance Targets" not in content

    def test_rendered_with_high_confidence_expert(self) -> None:
        enrichment = {
            "expert_guidance": [
                {"domain": "performance", "expert": "Perf Expert", "advice": "Use caching.", "confidence": "70%"}
            ]
        }
        result = self.gen._render_performance_targets(enrichment)
        rendered = "\n".join(result)
        assert "## Performance Targets" in rendered
        assert "Use caching." in rendered

    def test_omitted_with_low_confidence_expert(self) -> None:
        enrichment = {
            "expert_guidance": [
                {"domain": "performance", "expert": "Perf Expert", "advice": "Maybe cache.", "confidence": "25%"}
            ]
        }
        result = self.gen._render_performance_targets(enrichment)
        assert result == []


# ---------------------------------------------------------------------------
# Epic 19: Success Metrics
# ---------------------------------------------------------------------------

class TestEpicSuccessMetrics:
    """Tests for success metrics section (Epic 19.1)."""

    def setup_method(self) -> None:
        self.gen = EpicGenerator()

    def test_success_metrics_provided(self) -> None:
        config = _make_config(style="comprehensive", success_metrics=["All tests pass", "Latency < 200ms"])
        content = self.gen.generate(config)
        assert "## Success Metrics" in content
        assert "All tests pass" in content

    def test_success_metrics_pipe_delimited(self) -> None:
        config = _make_config(style="comprehensive", success_metrics=["MTTR|4h|1h|PagerDuty"])
        content = self.gen.generate(config)
        assert "MTTR" in content
        assert "4h" in content
        assert "1h" in content
        assert "PagerDuty" in content

    def test_success_metrics_derives_suggestions(self) -> None:
        config = _make_config(style="comprehensive", success_metrics=[], acceptance_criteria=["AC1", "AC2", "AC3"])
        content = self.gen.generate(config)
        assert "## Success Metrics" in content
        assert "All 3 acceptance criteria met" in content

    def test_success_metrics_standard_style_omitted(self) -> None:
        config = _make_config(style="standard", success_metrics=["Metric 1"])
        content = self.gen.generate(config)
        assert "## Success Metrics" not in content

    def test_success_metrics_markers(self) -> None:
        config = _make_config(style="comprehensive")
        content = self.gen.generate(config)
        assert "<!-- docsmcp:start:success-metrics -->" in content
        assert "<!-- docsmcp:end:success-metrics -->" in content


# ---------------------------------------------------------------------------
# Epic 19: Stakeholders
# ---------------------------------------------------------------------------

class TestEpicStakeholders:
    """Tests for stakeholders section (Epic 19.2)."""

    def setup_method(self) -> None:
        self.gen = EpicGenerator()

    def test_stakeholders_provided(self) -> None:
        config = _make_config(style="comprehensive", stakeholders=["Owner|Alice|Implementation", "Reviewer|Bob|Code review"])
        content = self.gen.generate(config)
        assert "## Stakeholders" in content
        assert "Alice" in content
        assert "Bob" in content

    def test_stakeholders_empty_omitted(self) -> None:
        config = _make_config(style="comprehensive", stakeholders=[])
        content = self.gen.generate(config)
        assert "## Stakeholders" not in content

    def test_stakeholders_standard_style_omitted(self) -> None:
        config = _make_config(style="standard", stakeholders=["Owner|Alice|Implementation"])
        content = self.gen.generate(config)
        assert "## Stakeholders" not in content


# ---------------------------------------------------------------------------
# Epic 19: References
# ---------------------------------------------------------------------------

class TestEpicReferences:
    """Tests for references section (Epic 19.3)."""

    def setup_method(self) -> None:
        self.gen = EpicGenerator()

    def test_references_provided(self) -> None:
        config = _make_config(style="comprehensive", references=["[OKR Q1](http://okr.example.com)", "Roadmap item 42"])
        content = self.gen.generate(config)
        assert "## References" in content
        assert "[OKR Q1](http://okr.example.com)" in content

    def test_references_empty_omitted(self) -> None:
        config = _make_config(style="comprehensive", references=[])
        content = self.gen.generate(config)
        assert "## References" not in content


# ---------------------------------------------------------------------------
# Epic 19.4: Rich story stubs
# ---------------------------------------------------------------------------

class TestEpicRichStoryStubs:
    """Tests for rich story stubs with real tasks (Epic 19.4)."""

    def setup_method(self) -> None:
        self.gen = EpicGenerator()

    def test_story_stub_with_tasks(self) -> None:
        stories = [EpicStoryStub(title="Auth", tasks=["Create login endpoint", "Add JWT validation", "Write auth tests", "Update docs", "Add rate limiting", "Integration test"])]
        config = _make_config(style="standard", stories=stories)
        content = self.gen.generate(config)
        # Should show first 4 tasks.
        assert "Create login endpoint" in content
        assert "Add JWT validation" in content
        assert "Write auth tests" in content
        assert "Update docs" in content
        # Should indicate more exist.
        assert "and 2 more" in content

    def test_story_stub_with_ac_count(self) -> None:
        stories = [EpicStoryStub(title="Auth", ac_count=5)]
        config = _make_config(style="standard", stories=stories)
        content = self.gen.generate(config)
        assert "(5 acceptance criteria)" in content

    def test_story_stub_no_tasks_generic(self) -> None:
        stories = [EpicStoryStub(title="Auth")]
        config = _make_config(style="standard", stories=stories)
        content = self.gen.generate(config)
        assert "Implement auth" in content  # generic fallback


# ---------------------------------------------------------------------------
# Epic 20.2: Files aggregation
# ---------------------------------------------------------------------------

class TestEpicFilesAggregation:
    """Tests for files affected aggregation from story stubs (Epic 20.2)."""

    def setup_method(self) -> None:
        self.gen = EpicGenerator()

    def test_files_aggregated_from_tasks(self) -> None:
        stories = [
            EpicStoryStub(title="Models", tasks=["Create `src/models.py` with schemas", "Update `src/db.py`"]),
            EpicStoryStub(title="API", tasks=["Add endpoints in `src/api.py`"]),
        ]
        config = _make_config(style="comprehensive", stories=stories)
        content = self.gen.generate(config)
        assert "`src/models.py`" in content
        assert "`src/api.py`" in content
        # Should NOT have "see tasks" placeholder.
        assert "*see tasks*" not in content

    def test_files_no_paths_fallback(self) -> None:
        stories = [EpicStoryStub(title="Models", tasks=["Create schemas"])]
        config = _make_config(style="comprehensive", stories=stories)
        content = self.gen.generate(config)
        assert "Files will be determined during story refinement" in content


# ---------------------------------------------------------------------------
# Epic 20.3: Story linking
# ---------------------------------------------------------------------------

class TestEpicStoryLinking:
    """Tests for story-to-epic linking (Epic 20.3)."""

    def setup_method(self) -> None:
        self.gen = EpicGenerator()

    def test_story_links_rendered(self) -> None:
        stories = [EpicStoryStub(title="Auth")]
        config = _make_config(
            style="standard",
            stories=stories,
            link_stories=True,
            story_paths={1: "stories/story-42.1-auth.md"},  # type: ignore[arg-type]
        )
        # Need to set these on the config directly since _make_config uses **kwargs
        config.link_stories = True
        config.story_paths = {1: "stories/story-42.1-auth.md"}
        content = self.gen.generate(config)
        assert "[Full story](stories/story-42.1-auth.md)" in content

    def test_story_links_disabled(self) -> None:
        stories = [EpicStoryStub(title="Auth")]
        config = _make_config(style="standard", stories=stories, link_stories=False)
        content = self.gen.generate(config)
        assert "Full story" not in content


# ---------------------------------------------------------------------------
# parse_stories_json with new fields
# ---------------------------------------------------------------------------

class TestParseStoriesJsonExtended:
    """Tests for parse_stories_json with tasks and ac_count."""

    def test_json_with_tasks(self) -> None:
        import json
        raw = json.dumps([{"title": "Auth", "tasks": ["Create login", "Add tests"]}])
        stories = EpicGenerator.parse_stories_json(raw)
        assert len(stories) == 1
        assert stories[0].tasks == ["Create login", "Add tests"]

    def test_json_with_ac_count(self) -> None:
        import json
        raw = json.dumps([{"title": "Auth", "ac_count": 5}])
        stories = EpicGenerator.parse_stories_json(raw)
        assert stories[0].ac_count == 5
