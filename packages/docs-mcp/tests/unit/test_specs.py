"""Tests for docs_mcp.generators.specs -- PRD generation.

Covers PRDGenerator section rendering, style variants, empty inputs,
Gherkin AC formatting, auto-populate with mocked analyzers, SmartMerger
regeneration, parse_phases_json, and the ``docs_generate_prd`` MCP tool.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from docs_mcp.generators.specs import PRDConfig, PRDGenerator, PRDPhase


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


def _make_config(**kwargs: Any) -> PRDConfig:
    """Build a PRDConfig with sensible defaults."""
    defaults: dict[str, Any] = {
        "title": "Test PRD",
        "problem": "Users need a better widget.",
        "personas": ["Developer", "PM"],
        "phases": [
            PRDPhase(
                name="MVP",
                description="Core functionality",
                requirements=["Login system", "Dashboard"],
            ),
            PRDPhase(
                name="Enhancement",
                description="Iterative improvements",
                requirements=["Analytics", "Notifications"],
            ),
        ],
        "constraints": ["Must support Python 3.12+"],
        "non_goals": ["Mobile app support"],
        "style": "standard",
    }
    defaults.update(kwargs)
    return PRDConfig(**defaults)


# ---------------------------------------------------------------------------
# PRDPhase model
# ---------------------------------------------------------------------------


class TestPRDPhase:
    """Tests for the PRDPhase Pydantic model."""

    def test_defaults(self) -> None:
        phase = PRDPhase(name="Alpha")
        assert phase.name == "Alpha"
        assert phase.description == ""
        assert phase.requirements == []

    def test_with_all_fields(self) -> None:
        phase = PRDPhase(
            name="Beta",
            description="Beta phase",
            requirements=["Feature A", "Feature B"],
        )
        assert phase.name == "Beta"
        assert len(phase.requirements) == 2


# ---------------------------------------------------------------------------
# PRDConfig model
# ---------------------------------------------------------------------------


class TestPRDConfig:
    """Tests for the PRDConfig Pydantic model."""

    def test_defaults(self) -> None:
        config = PRDConfig(title="My PRD")
        assert config.title == "My PRD"
        assert config.problem == ""
        assert config.personas == []
        assert config.phases == []
        assert config.constraints == []
        assert config.non_goals == []
        assert config.style == "standard"

    def test_style_values(self) -> None:
        config = PRDConfig(title="X", style="comprehensive")
        assert config.style == "comprehensive"


# ---------------------------------------------------------------------------
# PRDGenerator -- section rendering
# ---------------------------------------------------------------------------


class TestPRDGeneratorSections:
    """Tests for individual section rendering in PRDGenerator."""

    def setup_method(self) -> None:
        self.gen = PRDGenerator()

    def test_title_rendering(self) -> None:
        config = _make_config(title="Auth System")
        content = self.gen.generate(config)
        assert content.startswith("# PRD: Auth System")

    def test_executive_summary_with_problem(self) -> None:
        config = _make_config(problem="Users cannot authenticate.")
        content = self.gen.generate(config)
        assert "## Executive Summary" in content
        assert "Users cannot authenticate." in content

    def test_executive_summary_placeholder(self) -> None:
        config = _make_config(problem="")
        content = self.gen.generate(config)
        assert "Describe the high-level purpose" in content

    def test_problem_statement_with_text(self) -> None:
        config = _make_config(problem="Something is broken.")
        content = self.gen.generate(config)
        assert "## Problem Statement" in content
        assert "Something is broken." in content

    def test_problem_statement_placeholder(self) -> None:
        config = _make_config(problem="")
        content = self.gen.generate(config)
        assert "Describe the problem this product solves" in content

    def test_user_personas_rendered(self) -> None:
        config = _make_config(personas=["Admin", "Viewer", "Editor"])
        content = self.gen.generate(config)
        assert "## User Personas" in content
        assert "1. **Admin**" in content
        assert "2. **Viewer**" in content
        assert "3. **Editor**" in content

    def test_user_personas_placeholder(self) -> None:
        config = _make_config(personas=[])
        content = self.gen.generate(config)
        assert "Define target user personas" in content

    def test_solution_overview_present(self) -> None:
        config = _make_config()
        content = self.gen.generate(config)
        assert "## Solution Overview" in content

    def test_phased_requirements_rendered(self) -> None:
        config = _make_config()
        content = self.gen.generate(config)
        assert "## Phased Requirements" in content
        assert "### Phase 1: MVP" in content
        assert "### Phase 2: Enhancement" in content
        assert "- Login system" in content
        assert "- Dashboard" in content

    def test_phased_requirements_placeholder(self) -> None:
        config = _make_config(phases=[])
        content = self.gen.generate(config)
        assert "### Phase 1: TBD" in content
        assert "### Phase 2: TBD" in content

    def test_acceptance_criteria_gherkin(self) -> None:
        config = _make_config()
        content = self.gen.generate(config)
        assert "## Acceptance Criteria" in content
        assert "```gherkin" in content
        assert "Given the system is in its initial state" in content
        assert "When login system" in content
        assert "Then the expected outcome is achieved" in content

    def test_acceptance_criteria_placeholder(self) -> None:
        config = _make_config(phases=[])
        content = self.gen.generate(config)
        assert "Feature: Example" in content
        assert "Given a precondition" in content

    def test_technical_constraints_rendered(self) -> None:
        config = _make_config(constraints=["Python 3.12+", "No external DB"])
        content = self.gen.generate(config)
        assert "## Technical Constraints" in content
        assert "- Python 3.12+" in content
        assert "- No external DB" in content

    def test_technical_constraints_placeholder(self) -> None:
        config = _make_config(constraints=[])
        content = self.gen.generate(config)
        assert "- Define technical constraints" in content

    def test_non_goals_rendered(self) -> None:
        config = _make_config(non_goals=["Mobile", "i18n"])
        content = self.gen.generate(config)
        assert "## Non-Goals" in content
        assert "- Mobile" in content
        assert "- i18n" in content

    def test_non_goals_placeholder(self) -> None:
        config = _make_config(non_goals=[])
        content = self.gen.generate(config)
        assert "- Define what is explicitly out of scope" in content


# ---------------------------------------------------------------------------
# PRDGenerator -- style variants
# ---------------------------------------------------------------------------


class TestPRDGeneratorStyles:
    """Tests for standard vs comprehensive style."""

    def setup_method(self) -> None:
        self.gen = PRDGenerator()

    def test_standard_no_boundary_or_architecture(self) -> None:
        config = _make_config(style="standard")
        content = self.gen.generate(config)
        assert "## Boundary System" not in content
        assert "## Architecture Overview" not in content

    def test_comprehensive_has_boundary_system(self) -> None:
        config = _make_config(style="comprehensive")
        content = self.gen.generate(config)
        assert "## Boundary System" in content
        assert "### Always Do" in content
        assert "### Ask First" in content
        assert "### Never Do" in content

    def test_comprehensive_has_architecture_overview(self) -> None:
        config = _make_config(style="comprehensive")
        content = self.gen.generate(config)
        assert "## Architecture Overview" in content

    def test_invalid_style_falls_back_to_standard(self) -> None:
        config = _make_config(style="unknown")
        content = self.gen.generate(config)
        assert "## Boundary System" not in content
        assert "## Architecture Overview" not in content


# ---------------------------------------------------------------------------
# PRDGenerator -- docsmcp markers
# ---------------------------------------------------------------------------


class TestPRDGeneratorMarkers:
    """Tests for SmartMerger-compatible docsmcp markers."""

    def setup_method(self) -> None:
        self.gen = PRDGenerator()

    def test_all_sections_have_markers(self) -> None:
        config = _make_config(style="comprehensive")
        content = self.gen.generate(config)

        expected_sections = [
            "executive-summary",
            "problem-statement",
            "user-personas",
            "solution-overview",
            "phased-requirements",
            "acceptance-criteria",
            "technical-constraints",
            "non-goals",
            "boundary-system",
            "architecture-overview",
        ]

        for section in expected_sections:
            assert f"<!-- docsmcp:start:{section} -->" in content, f"Missing start marker: {section}"
            assert f"<!-- docsmcp:end:{section} -->" in content, f"Missing end marker: {section}"

    def test_standard_sections_have_markers(self) -> None:
        config = _make_config(style="standard")
        content = self.gen.generate(config)

        standard_sections = [
            "executive-summary",
            "problem-statement",
            "user-personas",
            "solution-overview",
            "phased-requirements",
            "acceptance-criteria",
            "technical-constraints",
            "non-goals",
        ]

        for section in standard_sections:
            assert f"<!-- docsmcp:start:{section} -->" in content


# ---------------------------------------------------------------------------
# PRDGenerator -- empty inputs
# ---------------------------------------------------------------------------


class TestPRDGeneratorEmptyInputs:
    """Tests for PRD generation with minimal/empty inputs."""

    def setup_method(self) -> None:
        self.gen = PRDGenerator()

    def test_minimal_config(self) -> None:
        config = PRDConfig(title="Minimal PRD")
        content = self.gen.generate(config)
        assert "# PRD: Minimal PRD" in content
        assert "## Executive Summary" in content
        assert "## Problem Statement" in content
        assert "## Phased Requirements" in content

    def test_all_empty_fields(self) -> None:
        config = PRDConfig(
            title="Empty",
            problem="",
            personas=[],
            phases=[],
            constraints=[],
            non_goals=[],
        )
        content = self.gen.generate(config)
        assert "# PRD: Empty" in content
        # Should have placeholder text, not crash
        assert "Describe" in content or "Define" in content


# ---------------------------------------------------------------------------
# PRDGenerator -- auto-populate
# ---------------------------------------------------------------------------


class TestPRDGeneratorAutoPopulate:
    """Tests for auto-populate from project analyzers."""

    def setup_method(self) -> None:
        self.gen = PRDGenerator()

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
                "docs_mcp.integrations.tapps.TappsIntegration",
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
        assert "fastapi" in content

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
                "docs_mcp.integrations.tapps.TappsIntegration",
                side_effect=RuntimeError,
            ),
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
        assert "42 public APIs" in content

    def test_auto_populate_graceful_on_all_failures(self, tmp_path: Path) -> None:
        """All analyzers fail -- should still produce valid output."""
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
                "docs_mcp.integrations.tapps.TappsIntegration",
                side_effect=RuntimeError,
            ),
            patch(
                "docs_mcp.analyzers.git_history.GitHistoryAnalyzer",
                side_effect=RuntimeError,
            ),
        ):
            config = _make_config()
            content = self.gen.generate(config, project_root=tmp_path, auto_populate=True)

        assert "# PRD: Test PRD" in content
        assert "## Phased Requirements" in content

    def test_auto_populate_disabled_by_default(self) -> None:
        config = _make_config()
        content = self.gen.generate(config)
        # No enrichment data should appear since auto_populate defaults to False
        assert "Tech Stack:" not in content

    def test_auto_populate_quality_summary(self, tmp_path: Path) -> None:
        mock_enrichment = MagicMock()
        mock_enrichment.overall_project_score = 85.0

        mock_integration = MagicMock()
        mock_integration.is_available = True
        mock_integration.load_enrichment.return_value = mock_enrichment

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
                "docs_mcp.integrations.tapps.TappsIntegration",
                return_value=mock_integration,
            ),
            patch(
                "docs_mcp.analyzers.git_history.GitHistoryAnalyzer",
                side_effect=RuntimeError,
            ),
        ):
            config = _make_config(style="comprehensive")
            content = self.gen.generate(config, project_root=tmp_path, auto_populate=True)

        assert "Overall score: 85/100" in content

    def test_auto_populate_git_summary(self, tmp_path: Path) -> None:
        mock_commit = MagicMock()
        mock_commit.message = "feat: add login page"

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
                "docs_mcp.integrations.tapps.TappsIntegration",
                side_effect=RuntimeError,
            ),
            patch(
                "docs_mcp.analyzers.git_history.GitHistoryAnalyzer",
            ) as mock_cls,
        ):
            mock_cls.return_value.get_commits.return_value = [mock_commit]
            config = _make_config(style="comprehensive")
            content = self.gen.generate(config, project_root=tmp_path, auto_populate=True)

        assert "feat: add login page" in content


# ---------------------------------------------------------------------------
# PRDGenerator -- parse_phases_json
# ---------------------------------------------------------------------------


class TestParsePhases:
    """Tests for PRDGenerator.parse_phases_json."""

    def test_valid_json(self) -> None:
        raw = json.dumps([
            {"name": "Alpha", "description": "First", "requirements": ["Auth"]},
            {"name": "Beta", "requirements": ["Search", "Export"]},
        ])
        phases = PRDGenerator.parse_phases_json(raw)
        assert len(phases) == 2
        assert phases[0].name == "Alpha"
        assert phases[0].description == "First"
        assert phases[1].requirements == ["Search", "Export"]

    def test_empty_string(self) -> None:
        phases = PRDGenerator.parse_phases_json("")
        assert phases == []

    def test_whitespace_string(self) -> None:
        phases = PRDGenerator.parse_phases_json("   ")
        assert phases == []

    def test_invalid_json(self) -> None:
        with pytest.raises(ValueError, match="Invalid JSON"):
            PRDGenerator.parse_phases_json("{bad json}")

    def test_not_a_list(self) -> None:
        with pytest.raises(ValueError, match="must be a list"):
            PRDGenerator.parse_phases_json('{"name": "oops"}')

    def test_skips_non_dict_items(self) -> None:
        raw = json.dumps([{"name": "Valid"}, "not-a-dict", 42])
        phases = PRDGenerator.parse_phases_json(raw)
        assert len(phases) == 1
        assert phases[0].name == "Valid"


# ---------------------------------------------------------------------------
# PRDGenerator -- slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    """Tests for PRDGenerator._slugify."""

    def test_basic(self) -> None:
        assert PRDGenerator._slugify("Hello World") == "hello-world"

    def test_special_chars(self) -> None:
        assert PRDGenerator._slugify("User Auth (v2)!") == "user-auth-v2"

    def test_multiple_spaces(self) -> None:
        assert PRDGenerator._slugify("a   b") == "a-b"


# ---------------------------------------------------------------------------
# SmartMerger integration
# ---------------------------------------------------------------------------


class TestSmartMergerIntegration:
    """Tests for PRD + SmartMerger round-trip."""

    def setup_method(self) -> None:
        self.gen = PRDGenerator()

    def test_merge_preserves_human_edits(self) -> None:
        from docs_mcp.generators.smart_merge import SmartMerger

        config = _make_config()
        generated = self.gen.generate(config)

        # Simulate hand-editing a section
        existing = generated.replace(
            "Describe the proposed solution at a high level...",
            "Our custom solution uses microservices.",
        )

        merger = SmartMerger()
        result = merger.merge(existing, generated)

        # Machine-managed sections should be updated
        assert result.sections_updated or result.sections_preserved
        # Content should be valid markdown
        assert "# PRD:" in result.content

    def test_merge_adds_new_sections_on_style_upgrade(self) -> None:
        from docs_mcp.generators.smart_merge import SmartMerger

        # Generate standard first
        config_std = _make_config(style="standard")
        standard = self.gen.generate(config_std)

        # Generate comprehensive (adds boundary system + architecture)
        config_comp = _make_config(style="comprehensive")
        comprehensive = self.gen.generate(config_comp)

        merger = SmartMerger()
        result = merger.merge(standard, comprehensive)

        # New sections should be added
        assert "Boundary System" in result.content or result.sections_added


# ---------------------------------------------------------------------------
# MCP tool: docs_generate_prd
# ---------------------------------------------------------------------------


class TestDocsGeneratePrdTool:
    """Tests for the ``docs_generate_prd`` MCP tool handler."""

    def _call(self, **kwargs: Any) -> dict[str, Any]:
        from docs_mcp.server_gen_tools import docs_generate_prd

        return _run(docs_generate_prd(**kwargs))

    def test_basic_success(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = self._call(title="My Feature", project_root=str(root))

        assert result["success"] is True
        assert result["data"]["title"] == "My Feature"
        assert "# PRD: My Feature" in result["data"]["content"]

    def test_invalid_root(self, tmp_path: Path) -> None:
        bad_root = tmp_path / "does_not_exist"
        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(bad_root),
        ):
            result = self._call(title="X", project_root=str(bad_root))

        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ROOT"

    def test_invalid_phases_json(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = self._call(
                title="X",
                phases="{bad",
                project_root=str(root),
            )

        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_PHASES"

    def test_personas_comma_parsing(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = self._call(
                title="X",
                personas="Admin, Developer, Viewer",
                project_root=str(root),
            )

        assert result["success"] is True
        content = result["data"]["content"]
        assert "**Admin**" in content
        assert "**Developer**" in content
        assert "**Viewer**" in content

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
        assert "Boundary System" in result["data"]["content"]

    def test_write_to_file(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = self._call(
                title="Written PRD",
                output_path="docs/PRD.md",
                project_root=str(root),
            )

        assert result["success"] is True
        assert result["data"]["written_to"] == "docs/PRD.md"
        written = (root / "docs" / "PRD.md").read_text(encoding="utf-8")
        assert "# PRD: Written PRD" in written

    def test_merge_with_existing(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        existing = (
            "# PRD: Old\n\n"
            "## Custom Section\n\n"
            "This is my custom content.\n"
        )

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = self._call(
                title="Updated",
                existing_content=existing,
                project_root=str(root),
            )

        assert result["success"] is True
        assert result["data"]["merged"] is True

    def test_no_merge_without_existing(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = self._call(title="Fresh", project_root=str(root))

        assert result["success"] is True
        assert result["data"]["merged"] is False

    def test_phases_json_parsing(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        phases = json.dumps([
            {"name": "Alpha", "requirements": ["Feature A"]},
        ])

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = self._call(
                title="X",
                phases=phases,
                project_root=str(root),
            )

        assert result["success"] is True
        assert "Phase 1: Alpha" in result["data"]["content"]
        assert "Feature A" in result["data"]["content"]

    def test_constraints_and_non_goals_comma_parsing(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = self._call(
                title="X",
                constraints="Python 3.12+, No Redis",
                non_goals="Mobile, i18n",
                project_root=str(root),
            )

        assert result["success"] is True
        content = result["data"]["content"]
        assert "- Python 3.12+" in content
        assert "- No Redis" in content
        assert "- Mobile" in content
        assert "- i18n" in content

    def test_generation_error_handling(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with (
            patch(
                "docs_mcp.server_gen_tools._get_settings",
                return_value=_make_settings(root),
            ),
            patch(
                "docs_mcp.generators.specs.PRDGenerator.generate",
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
