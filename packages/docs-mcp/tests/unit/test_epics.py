"""Tests for docs_mcp.generators.epics -- Epic document generation.

Covers EpicGenerator section rendering, style variants, empty inputs,
auto-populate with mocked analyzers, parse_stories_json, and the
``docs_generate_epic`` MCP tool.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from docs_mcp.generators.epics import EpicConfig, EpicGenerator, EpicStoryStub
from tests.helpers import make_settings as _make_settings


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
        assert "Describe how **Test Epic** will change the system" in content

    def test_motivation_with_text(self) -> None:
        config = _make_config(motivation="Users lose context across sessions.")
        content = self.gen.generate(config)
        assert "## Motivation" in content
        assert "Users lose context across sessions." in content

    def test_motivation_placeholder(self) -> None:
        config = _make_config(motivation="")
        content = self.gen.generate(config)
        assert "Explain why **Test Epic** matters" in content

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
        assert "- [ ] Define verifiable criteria for **Test Epic**" in content

    def test_generate_with_timing_returns_phase_ms(self) -> None:
        config = _make_config()
        content, timing = self.gen.generate_with_timing(config)
        assert "## Stories" in content
        assert "total_ms" in timing
        assert "render_ms" in timing
        assert timing["total_ms"] >= timing["render_ms"]

    def test_generate_with_timing_auto_populate_breakdown(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "proj"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
        config = _make_config()
        _, timing = self.gen.generate_with_timing(
            config,
            project_root=tmp_path,
            auto_populate=True,
        )
        assert "auto_populate_ms" in timing
        assert "metadata_ms" in timing
        assert "render_ms" in timing

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
        # "Test Epic" has no matching keywords; suggestion engine falls back to generic stubs.
        config = _make_config(stories=[], number=10)
        content = self.gen.generate(config)
        assert "### 10.1 -- Foundation & Setup (suggested)" in content
        assert "### 10.2 -- Core Implementation (suggested)" in content

    def test_technical_notes_rendered(self) -> None:
        config = _make_config(technical_notes=["Use async/await", "SQLite WAL mode"])
        content = self.gen.generate(config)
        assert "## Technical Notes" in content
        assert "- Use async/await" in content
        assert "- SQLite WAL mode" in content

    def test_technical_notes_placeholder(self) -> None:
        config = _make_config(technical_notes=[])
        content = self.gen.generate(config)
        assert "- Document architecture decisions for **Test Epic**" in content

    def test_non_goals_rendered(self) -> None:
        config = _make_config(non_goals=["Mobile app", "i18n"])
        content = self.gen.generate(config)
        assert "## Out of Scope" in content
        assert "- Mobile app" in content
        assert "- i18n" in content

    def test_non_goals_placeholder(self) -> None:
        config = _make_config(non_goals=[])
        content = self.gen.generate(config)
        assert "- Define what is explicitly out of scope for **Test Epic**" in content


# ---------------------------------------------------------------------------
# Context-aware placeholder prose (Story 91.1)
# ---------------------------------------------------------------------------


class TestContextAwarePlaceholders:
    """Tests that placeholder text includes the epic title and context."""

    def setup_method(self) -> None:
        self.gen = EpicGenerator()

    def test_goal_placeholder_includes_title(self) -> None:
        config = _make_config(title="Auth Middleware Rewrite", goal="")
        content = self.gen.generate(config)
        assert "**Auth Middleware Rewrite**" in content
        assert "will change the system" in content

    def test_motivation_placeholder_includes_title(self) -> None:
        config = _make_config(title="Memory Federation", motivation="")
        content = self.gen.generate(config)
        assert "**Memory Federation**" in content
        assert "matters" in content

    def test_technical_notes_placeholder_includes_title(self) -> None:
        config = _make_config(title="Cache Layer", technical_notes=[])
        content = self.gen.generate(config)
        assert "architecture decisions for **Cache Layer**" in content

    def test_technical_notes_placeholder_includes_tech_stack(self, tmp_path: Path) -> None:
        """When auto_populate provides tech_stack, placeholder includes it."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "proj"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
        config = _make_config(title="Cache Layer", technical_notes=[])
        # Simulate enrichment with tech_stack via direct render call.
        lines = self.gen._render_technical_notes(config, {"tech_stack": "Python, Redis, FastAPI"})
        joined = "\n".join(lines)
        assert "**Cache Layer**" in joined
        assert "**Python, Redis, FastAPI**" in joined

    def test_non_goals_placeholder_includes_title(self) -> None:
        config = _make_config(title="Graph Query Engine", non_goals=[])
        content = self.gen.generate(config)
        assert "**Graph Query Engine**" in content

    def test_non_goals_keyword_hints_auth(self) -> None:
        config = _make_config(title="Auth Service Upgrade", non_goals=[])
        content = self.gen.generate(config)
        assert "Multi-factor authentication" in content

    def test_non_goals_keyword_hints_api(self) -> None:
        config = _make_config(title="API Gateway Redesign", non_goals=[])
        content = self.gen.generate(config)
        assert "Third-party API integrations" in content

    def test_non_goals_no_keyword_match(self) -> None:
        config = _make_config(title="Improve Documentation", non_goals=[])
        content = self.gen.generate(config)
        # Should still reference title but no keyword hints.
        assert "**Improve Documentation**" in content
        assert "out of scope" in content

    def test_acceptance_criteria_placeholder_includes_title(self) -> None:
        config = _make_config(title="Session Persistence", acceptance_criteria=[])
        content = self.gen.generate(config)
        assert "**Session Persistence**" in content
        assert "Define verifiable criteria" in content

    def test_empty_title_falls_back_to_generic_goal(self) -> None:
        config = _make_config(title="", goal="")
        content = self.gen.generate(config)
        assert "Describe the measurable outcome this epic achieves" in content

    def test_empty_title_falls_back_to_generic_motivation(self) -> None:
        config = _make_config(title="", motivation="")
        content = self.gen.generate(config)
        assert "Explain why this work matters" in content

    def test_empty_title_falls_back_to_generic_acceptance(self) -> None:
        config = _make_config(title="", acceptance_criteria=[])
        content = self.gen.generate(config)
        assert "Define verifiable acceptance criteria" in content

    def test_empty_title_falls_back_to_generic_technical_notes(self) -> None:
        config = _make_config(title="", technical_notes=[])
        content = self.gen.generate(config)
        assert "Document architecture decisions and key dependencies" in content

    def test_empty_title_falls_back_to_generic_non_goals(self) -> None:
        config = _make_config(title="", non_goals=[])
        content = self.gen.generate(config)
        assert "Define what is explicitly deferred" in content

    def test_whitespace_title_falls_back_to_generic(self) -> None:
        config = _make_config(title="   ", goal="", motivation="")
        content = self.gen.generate(config)
        assert "Describe the measurable outcome this epic achieves" in content
        assert "Explain why this work matters" in content


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

    def test_comprehensive_always_renders_performance_targets(self) -> None:
        """Performance targets section is always present in comprehensive epics (Story 91.5)."""
        config = _make_config(style="comprehensive")
        content = self.gen.generate(config)
        # Config-derived test coverage row is always included.
        assert "## Performance Targets" in content
        assert "Test coverage" in content

    def test_invalid_style_falls_back_to_standard(self) -> None:
        config = _make_config(style="unknown")
        content = self.gen.generate(config)
        assert "## Implementation Order" not in content
        assert "## Risk Assessment" not in content

    def test_minimal_style_reduced_output(self) -> None:
        """Explicit minimal style produces reduced output."""
        config = _make_config(style="minimal", stories=[])
        content = self.gen.generate(config)
        # Minimal includes: title, metadata, purpose, goal, motivation, AC, stories, DoD
        assert "## Goal" in content
        assert "## Acceptance Criteria" in content
        assert "## Definition of Done" in content
        # STORY-104.2: minimal now includes Motivation (validator requires it).
        assert "## Motivation" in content
        # Minimal omits: technical notes, non-goals
        assert "## Technical Notes" not in content
        assert "## Out of Scope" not in content
        # And never comprehensive sections
        assert "## Implementation Order" not in content
        assert "## Risk Assessment" not in content

    def test_inepic_story_stub_with_ac_passes_validator(self, tmp_path: Path) -> None:
        """STORY-104.3: in-epic story stubs with AC must pass validation.

        Before the fix, stories emitted `(N acceptance criteria)` as
        inline text, which the validator's AC-section parser ignored,
        raising a 'Missing acceptance criteria' error on every stub.
        """
        from docs_mcp.validators.epic_validator import EpicValidator

        config = _make_config(
            style="minimal",
            stories=[EpicStoryStub(title="Story with AC", points=3, ac_count=2)],
        )
        content = self.gen.generate(config)
        epic_file = tmp_path / "EPIC-42-test.md"
        epic_file.write_text(content, encoding="utf-8")

        report = EpicValidator().validate(epic_file)
        missing_ac = [
            i for i in report.issues
            if i.severity == "error" and "acceptance criteria" in i.message.lower()
        ]
        assert not missing_ac, (
            f"In-epic story stub with ac_count=2 still flagged: {missing_ac}"
        )
        # The heading itself must be present.
        assert "#### Acceptance Criteria" in content

    def test_minimal_style_passes_validator(self, tmp_path: Path) -> None:
        """STORY-104.2: minimal-style epics must pass docs_validate_epic.

        Before the fix, minimal style omitted ## Motivation — a required
        section per epic_validator — and every minimal epic raised an
        error on validation.
        """
        from docs_mcp.validators.epic_validator import EpicValidator

        config = _make_config(style="minimal", stories=[])
        content = self.gen.generate(config)
        epic_file = tmp_path / "EPIC-42-test.md"
        epic_file.write_text(content, encoding="utf-8")

        report = EpicValidator().validate(epic_file)
        missing_motivation = [
            i for i in report.issues
            if i.severity == "error" and "motivation" in i.message.lower()
        ]
        assert not missing_motivation, (
            f"Minimal-style epic still missing Motivation per validator: {missing_motivation}"
        )


# ---------------------------------------------------------------------------
# EpicGenerator -- auto style detection
# ---------------------------------------------------------------------------


class TestEpicAutoDetectStyle:
    """Tests for _auto_detect_style and style='auto' integration."""

    def setup_method(self) -> None:
        self.gen = EpicGenerator()

    def test_auto_detects_minimal_zero_stories(self) -> None:
        """Auto with 0 stories, no risks, no files -> minimal."""
        config = _make_config(style="auto", stories=[], risks=[], files=[])
        content = self.gen.generate(config)
        assert "## Definition of Done" in content
        # STORY-104.2: minimal includes Motivation (validator requires it).
        assert "## Motivation" in content
        assert "## Implementation Order" not in content

    def test_auto_detects_minimal_one_story(self) -> None:
        """Auto with 1 story, no risks, no files -> minimal."""
        config = _make_config(
            style="auto",
            stories=[EpicStoryStub(title="Single story")],
            risks=[],
            files=[],
        )
        content = self.gen.generate(config)
        assert "## Definition of Done" in content
        # STORY-104.2: minimal includes Motivation (validator requires it).
        assert "## Motivation" in content

    def test_auto_detects_standard_three_stories(self) -> None:
        """Auto with 3 stories -> standard."""
        config = _make_config(
            style="auto",
            stories=[EpicStoryStub(title=f"Story {i}") for i in range(3)],
            risks=[],
            files=[],
        )
        content = self.gen.generate(config)
        # Standard has motivation and tech notes but no comprehensive sections
        assert "## Motivation" in content
        assert "## Technical Notes" in content
        assert "## Implementation Order" not in content
        assert "## Definition of Done" not in content

    def test_auto_detects_comprehensive_six_stories(self) -> None:
        """Auto with 6 stories -> comprehensive."""
        config = _make_config(
            style="auto",
            stories=[EpicStoryStub(title=f"Story {i}") for i in range(6)],
        )
        content = self.gen.generate(config)
        assert "## Implementation Order" in content
        assert "## Risk Assessment" in content

    def test_auto_detects_comprehensive_with_risks(self) -> None:
        """Auto with risks provided -> comprehensive."""
        config = _make_config(
            style="auto",
            stories=[EpicStoryStub(title="S1")],
            risks=["Data loss risk"],
            files=[],
        )
        content = self.gen.generate(config)
        assert "## Implementation Order" in content

    def test_auto_detects_comprehensive_with_many_files(self) -> None:
        """Auto with files > 3 -> comprehensive."""
        config = _make_config(
            style="auto",
            stories=[],
            risks=[],
            files=["a.py", "b.py", "c.py", "d.py"],
        )
        content = self.gen.generate(config)
        assert "## Implementation Order" in content

    def test_auto_detects_comprehensive_with_success_metrics(self) -> None:
        """Auto with success_metrics -> comprehensive."""
        config = _make_config(
            style="auto",
            stories=[],
            risks=[],
            files=[],
            success_metrics=["MTTR|4h|1h|PagerDuty"],
        )
        content = self.gen.generate(config)
        assert "## Success Metrics" in content

    def test_explicit_comprehensive_always_comprehensive(self) -> None:
        """Explicit comprehensive overrides auto-detection."""
        config = _make_config(style="comprehensive", stories=[], risks=[], files=[])
        content = self.gen.generate(config)
        assert "## Implementation Order" in content
        assert "## Risk Assessment" in content

    def test_auto_detect_style_method_directly(self) -> None:
        """Unit test _auto_detect_style in isolation."""
        # minimal
        cfg = _make_config(stories=[], risks=[], files=[])
        assert self.gen._auto_detect_style(cfg) == "minimal"

        # standard
        cfg = _make_config(
            stories=[EpicStoryStub(title=f"S{i}") for i in range(3)],
            risks=[],
            files=[],
        )
        assert self.gen._auto_detect_style(cfg) == "standard"

        # comprehensive (stories > 5)
        cfg = _make_config(
            stories=[EpicStoryStub(title=f"S{i}") for i in range(6)],
        )
        assert self.gen._auto_detect_style(cfg) == "comprehensive"


# ---------------------------------------------------------------------------
# EpicGenerator -- quick-start mode
# ---------------------------------------------------------------------------


class TestEpicQuickStart:
    """Tests for quick_start mode that infers defaults from title alone."""

    def setup_method(self) -> None:
        self.gen = EpicGenerator()

    def test_quick_start_title_only(self) -> None:
        """quick_start with just title produces complete epic."""
        config = EpicConfig(title="Auth System", number=10)
        content = self.gen.generate(config, quick_start=True)
        # Goal inferred
        assert "Implement Auth System with full test coverage" in content
        # Motivation inferred
        assert "addresses the need for Auth System" in content
        # 3 story stubs
        assert "10.1 -- Foundation & Setup" in content
        assert "10.2 -- Core Implementation" in content
        assert "10.3 -- Testing & Documentation" in content
        # AC inferred
        assert "Core functionality implemented" in content
        assert ">= 80% coverage" in content
        assert "Documentation updated" in content
        # Priority inferred
        assert "P2 - Medium" in content

    def test_quick_start_explicit_goal_not_overridden(self) -> None:
        """Explicit goal is preserved when quick_start=True."""
        config = EpicConfig(
            title="Auth System",
            number=5,
            goal="Build OAuth2 support.",
        )
        content = self.gen.generate(config, quick_start=True)
        assert "Build OAuth2 support." in content
        assert "Implement Auth System" not in content

    def test_quick_start_explicit_stories_not_overridden(self) -> None:
        """Explicit stories are preserved when quick_start=True."""
        config = EpicConfig(
            title="Auth System",
            number=5,
            stories=[EpicStoryStub(title="Custom Story", points=8)],
        )
        content = self.gen.generate(config, quick_start=True)
        assert "Custom Story" in content
        assert "Foundation & Setup" not in content

    def test_quick_start_explicit_priority_not_overridden(self) -> None:
        """Explicit priority is preserved when quick_start=True."""
        config = EpicConfig(
            title="Auth System",
            number=5,
            priority="P0 - Critical",
        )
        content = self.gen.generate(config, quick_start=True)
        assert "P0 - Critical" in content
        assert "P2 - Medium" not in content

    def test_quick_start_false_unchanged(self) -> None:
        """quick_start=False does not alter config behavior."""
        config = EpicConfig(title="Auth System", number=10)
        content_default = self.gen.generate(config)
        content_explicit = self.gen.generate(config, quick_start=False)
        assert content_default == content_explicit

    def test_quick_start_story_points(self) -> None:
        """Quick-start stories have expected point values."""
        config = EpicConfig(title="Auth System", number=7)
        content = self.gen.generate(config, quick_start=True)
        assert "**Points:** 2" in content
        assert "**Points:** 5" in content
        assert "**Points:** 3" in content


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
            "purpose-intent",
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
            "performance-targets",  # Story 91.5: always rendered with config-derived targets
        ]
        for section in always_present:
            assert f"<!-- docsmcp:start:{section} -->" in content, f"Missing start: {section}"
            assert f"<!-- docsmcp:end:{section} -->" in content, f"Missing end: {section}"
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


class TestEpicExpertEnrichmentNoOp:
    """Issue #82: _enrich_experts is a no-op after EPIC-94 removal."""

    def test_enrich_experts_is_noop(self) -> None:
        from docs_mcp.generators.epics import EpicConfig, EpicGenerator

        config = EpicConfig(number=1, title="Test")
        enrichment: dict[str, Any] = {}
        EpicGenerator._enrich_experts(config, enrichment)
        assert "expert_guidance" not in enrichment


# Note: TestEpicGeneratorExpertEnrichment was removed when the expert
# enrichment system was deleted (EPIC-94). The dead test class has been
# removed entirely rather than kept as commented-out code.


# ---------------------------------------------------------------------------
# Story 21.5: File hints in docs_generate_epic
# ---------------------------------------------------------------------------


class TestEpicFileHints:
    """Tests for file-specific auto-populate with file hints."""

    def setup_method(self) -> None:
        self.gen = EpicGenerator()

    def test_files_with_auto_populate_includes_table(self, tmp_path: Path) -> None:
        """Files parameter generates a Files Affected table with per-file info."""
        # Create test files
        setup_py = tmp_path / "setup.py"
        setup_py.write_text("def setup():\n    pass\n", encoding="utf-8")
        readme = tmp_path / "README.md"
        readme.write_text("# My Project\n", encoding="utf-8")

        config = _make_config(files=["setup.py", "README.md"])
        content = self.gen.generate(config, project_root=tmp_path)

        assert "## Files Affected" in content
        assert "`setup.py`" in content
        assert "`README.md`" in content
        # Should have the detailed table headers
        assert "Lines" in content
        assert "Recent Commits" in content
        assert "Public Symbols" in content

    def test_files_affected_table_shows_line_count(self, tmp_path: Path) -> None:
        """File analysis includes line count."""
        py_file = tmp_path / "module.py"
        py_file.write_text("line1\nline2\nline3\n", encoding="utf-8")

        config = _make_config(files=["module.py"])
        content = self.gen.generate(config, project_root=tmp_path)

        assert "## Files Affected" in content
        assert "`module.py`" in content
        assert "| 3 " in content  # 3 lines

    def test_files_python_public_symbols(self, tmp_path: Path) -> None:
        """Python files show public class and function counts."""
        py_file = tmp_path / "models.py"
        py_file.write_text(
            "class MyModel:\n    pass\n\n"
            "class _Internal:\n    pass\n\n"
            "def public_func():\n    pass\n\n"
            "def _private():\n    pass\n",
            encoding="utf-8",
        )

        config = _make_config(files=["models.py"])
        content = self.gen.generate(config, project_root=tmp_path)

        assert "1 classes" in content
        assert "1 functions" in content

    def test_nonexistent_file_skipped_gracefully(self, tmp_path: Path) -> None:
        """Non-existent files are listed but marked as not found."""
        config = _make_config(files=["nonexistent.py"])
        content = self.gen.generate(config, project_root=tmp_path)

        assert "## Files Affected" in content
        assert "`nonexistent.py`" in content
        assert "*(not found)*" in content

    def test_no_files_parameter_generic_metadata(self) -> None:
        """Without files parameter, existing generic behavior is preserved."""
        config = _make_config(files=[], style="comprehensive")
        content = self.gen.generate(config)

        # Should still have the generic files-affected section
        assert "## Files Affected" in content
        assert "Files will be determined during story refinement" in content

    def test_files_extracts_paths_from_story_descriptions(
        self,
        tmp_path: Path,
    ) -> None:
        """Story descriptions are scanned for additional file paths."""
        # Create the file referenced in story but not in explicit files list
        extra = tmp_path / "extra.py"
        extra.write_text("x = 1\n", encoding="utf-8")
        main = tmp_path / "main.py"
        main.write_text("# main\n", encoding="utf-8")

        stories = [
            EpicStoryStub(
                title="Feature",
                description="Modify `extra.py` for new feature.",
            ),
        ]
        config = _make_config(files=["main.py"], stories=stories)
        content = self.gen.generate(config, project_root=tmp_path)

        # Both explicit and discovered files should appear
        assert "`main.py`" in content
        assert "`extra.py`" in content

    def test_files_with_git_commits(self, tmp_path: Path) -> None:
        """Git commit history is included when available."""
        py_file = tmp_path / "app.py"
        py_file.write_text("print('hello')\n", encoding="utf-8")

        # Mock subprocess to simulate git output
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc1234 Add initial app\ndef5678 Fix bug\n"

        config = _make_config(files=["app.py"])
        with patch("docs_mcp.generators.epics.subprocess.run", return_value=mock_result):
            content = self.gen.generate(config, project_root=tmp_path)

        assert "2 recent" in content
        assert "Add initial app" in content

    def test_docsmcp_markers_present(self, tmp_path: Path) -> None:
        """Files affected section has docsmcp markers."""
        f = tmp_path / "a.py"
        f.write_text("x = 1\n", encoding="utf-8")

        config = _make_config(files=["a.py"])
        content = self.gen.generate(config, project_root=tmp_path)

        assert "<!-- docsmcp:start:files-affected -->" in content
        assert "<!-- docsmcp:end:files-affected -->" in content


class TestEpicRelatedEpics:
    """Tests for related epics cross-referencing."""

    def setup_method(self) -> None:
        self.gen = EpicGenerator()

    def test_related_epics_found(self, tmp_path: Path) -> None:
        """Related epics are listed when they mention the same files."""
        epics_dir = tmp_path / "docs" / "planning" / "epics"
        epics_dir.mkdir(parents=True)
        (epics_dir / "EPIC-10-AUTH.md").write_text(
            "# Epic 10\nModify `auth.py` for login.\n",
            encoding="utf-8",
        )
        (epics_dir / "EPIC-11-API.md").write_text(
            "# Epic 11\nUpdate `api.py` routes.\n",
            encoding="utf-8",
        )

        config = _make_config(files=["auth.py"])
        content = self.gen.generate(config, project_root=tmp_path)

        assert "## Related Epics" in content
        assert "EPIC-10-AUTH.md" in content
        assert "EPIC-11-API.md" not in content  # doesn't mention auth.py

    def test_no_related_epics_section_omitted(self, tmp_path: Path) -> None:
        """Related Epics section is omitted when no matches found."""
        epics_dir = tmp_path / "docs" / "planning" / "epics"
        epics_dir.mkdir(parents=True)
        (epics_dir / "EPIC-10-AUTH.md").write_text(
            "# Epic 10\nSome content.\n",
            encoding="utf-8",
        )

        config = _make_config(files=["unrelated.py"])
        content = self.gen.generate(config, project_root=tmp_path)

        assert "## Related Epics" not in content

    def test_no_epics_dir_no_error(self, tmp_path: Path) -> None:
        """Missing epics directory doesn't cause errors."""
        f = tmp_path / "a.py"
        f.write_text("x = 1\n", encoding="utf-8")

        config = _make_config(files=["a.py"])
        content = self.gen.generate(config, project_root=tmp_path)

        # Should not have Related Epics but should not error
        assert "## Related Epics" not in content
        assert "## Files Affected" in content

    def test_related_epics_markers(self, tmp_path: Path) -> None:
        """Related epics section has docsmcp markers."""
        epics_dir = tmp_path / "docs" / "planning" / "epics"
        epics_dir.mkdir(parents=True)
        (epics_dir / "EPIC-5.md").write_text(
            "Modify `target.py`\n",
            encoding="utf-8",
        )

        config = _make_config(files=["target.py"])
        content = self.gen.generate(config, project_root=tmp_path)

        assert "<!-- docsmcp:start:related-epics -->" in content
        assert "<!-- docsmcp:end:related-epics -->" in content


class TestEpicFileHintsMCPTool:
    """Tests for the docs_generate_epic MCP tool with files parameter."""

    @staticmethod
    async def _call(**kwargs: Any) -> dict[str, Any]:
        from docs_mcp.server_gen_tools import docs_generate_epic

        return await docs_generate_epic(**kwargs)

    async def test_tool_with_files_parameter(self, tmp_path: Path) -> None:
        """MCP tool accepts files parameter and passes to generator."""
        setup_py = tmp_path / "setup.py"
        setup_py.write_text("def setup():\n    pass\n", encoding="utf-8")

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(tmp_path),
        ):
            result = await self._call(
                title="File Hints Epic",
                files="setup.py",
                project_root=str(tmp_path),
            )

        assert "written_to" in result["data"]
        content = (tmp_path / result["data"]["written_to"]).read_text(encoding="utf-8")
        assert "## Files Affected" in content
        assert "`setup.py`" in content

    async def test_tool_without_files_backward_compat(self, tmp_path: Path) -> None:
        """MCP tool without files parameter preserves existing behavior."""
        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(tmp_path),
        ):
            result = await self._call(
                title="No Files Epic",
                project_root=str(tmp_path),
            )

        # Should not have file-hint style table
        assert "written_to" in result["data"]
        content = (tmp_path / result["data"]["written_to"]).read_text(encoding="utf-8")
        assert "Public Symbols" not in content

    async def test_tool_files_without_auto_populate(self, tmp_path: Path) -> None:
        """Files parameter works even without auto_populate=True."""
        readme = tmp_path / "README.md"
        readme.write_text("# Readme\n", encoding="utf-8")

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(tmp_path),
        ):
            result = await self._call(
                title="Files Only Epic",
                files="README.md",
                project_root=str(tmp_path),
            )

        assert "written_to" in result["data"]
        content = (tmp_path / result["data"]["written_to"]).read_text(encoding="utf-8")
        assert "## Files Affected" in content
        assert "`README.md`" in content


# ---------------------------------------------------------------------------
# Story 91.4 -- Suggestion Engine
# ---------------------------------------------------------------------------


class TestSuggestionEngineStories:
    """Unit tests for EpicGenerator._suggest_stories()."""

    def test_auth_keyword_in_title_produces_auth_stories(self) -> None:
        """Title 'User Authentication' yields auth-related story stubs."""
        gen = EpicGenerator()
        stubs = gen._suggest_stories("User Authentication", "")
        titles = [s.title for s in stubs]
        assert any("(suggested)" in t for t in titles), "All stubs must have (suggested) suffix"
        assert any("Auth Endpoints" in t or "Session Management" in t for t in titles)

    def test_api_keyword_produces_api_stories(self) -> None:
        """Title 'API Gateway' yields API-related story stubs."""
        gen = EpicGenerator()
        stubs = gen._suggest_stories("API Gateway", "")
        titles = [s.title for s in stubs]
        assert any("Endpoint Handlers" in t or "Validation" in t for t in titles)

    def test_database_keyword_produces_db_stories(self) -> None:
        """Title 'Database Migration' yields database-related story stubs."""
        gen = EpicGenerator()
        stubs = gen._suggest_stories("Database Migration Tool", "")
        titles = [s.title for s in stubs]
        assert any("Schema Design" in t or "Migration Scripts" in t for t in titles)

    def test_ui_keyword_produces_frontend_stories(self) -> None:
        """Title 'UI Component Library' yields frontend-related story stubs."""
        gen = EpicGenerator()
        stubs = gen._suggest_stories("UI Component Library", "")
        titles = [s.title for s in stubs]
        assert any("Component Scaffold" in t or "State Management" in t for t in titles)

    def test_deploy_keyword_produces_infra_stories(self) -> None:
        """Title 'Deploy Pipeline' yields CI/CD-related story stubs."""
        gen = EpicGenerator()
        stubs = gen._suggest_stories("Deploy Pipeline Setup", "")
        titles = [s.title for s in stubs]
        assert any("Build Pipeline" in t or "Deploy Scripts" in t for t in titles)

    def test_security_keyword_produces_security_stories(self) -> None:
        """Title 'Security Audit' yields security-related story stubs."""
        gen = EpicGenerator()
        stubs = gen._suggest_stories("Security Audit", "")
        titles = [s.title for s in stubs]
        assert any("Threat Model" in t or "Scanner Integration" in t for t in titles)

    def test_no_matching_keywords_fallback_to_generic(self) -> None:
        """Title with no matching keywords falls back to 3 generic story stubs."""
        gen = EpicGenerator()
        stubs = gen._suggest_stories("Widget Refactor", "")
        titles = [s.title for s in stubs]
        assert len(stubs) == 3
        assert any("Foundation" in t for t in titles)
        assert any("Core Implementation" in t for t in titles)
        assert any("Testing" in t for t in titles)

    def test_all_stubs_have_suggested_suffix(self) -> None:
        """All suggested stubs have '(suggested)' suffix to distinguish from user-provided."""
        gen = EpicGenerator()
        for title in ("User Auth", "API Gateway", "No Match Epic"):
            stubs = gen._suggest_stories(title, "")
            for stub in stubs:
                assert stub.title.endswith("(suggested)"), (
                    f"Expected '(suggested)' suffix on stub title, got: {stub.title!r}"
                )

    def test_keyword_in_goal_also_matches(self) -> None:
        """Keyword match in goal text (not just title) triggers suggestion."""
        gen = EpicGenerator()
        stubs = gen._suggest_stories("Onboarding Epic", "Build auth endpoints for new users")
        titles = [s.title for s in stubs]
        assert any("Auth Endpoints" in t or "Session Management" in t for t in titles)


class TestSuggestionEngineRisks:
    """Unit tests for EpicGenerator._suggest_risks()."""

    def test_auth_keyword_produces_auth_risk(self) -> None:
        gen = EpicGenerator()
        risks = gen._suggest_risks("User Authentication", "")
        assert any("Authentication bypass" in r for r in risks)

    def test_api_keyword_produces_breaking_change_risk(self) -> None:
        gen = EpicGenerator()
        risks = gen._suggest_risks("API Gateway", "")
        assert any("Breaking API changes" in r for r in risks)

    def test_database_keyword_produces_data_loss_risk(self) -> None:
        gen = EpicGenerator()
        risks = gen._suggest_risks("Database Migration", "")
        assert any("Data loss during migration" in r for r in risks)

    def test_deploy_keyword_produces_downtime_risk(self) -> None:
        gen = EpicGenerator()
        risks = gen._suggest_risks("Deploy Pipeline", "")
        assert any("Deployment downtime" in r for r in risks)

    def test_performance_keyword_produces_perf_risk(self) -> None:
        gen = EpicGenerator()
        risks = gen._suggest_risks("Performance Optimization", "")
        assert any("Performance degradation" in r for r in risks)

    def test_no_matching_keywords_returns_empty(self) -> None:
        gen = EpicGenerator()
        risks = gen._suggest_risks("Widget Refactor", "")
        assert risks == []

    def test_deduplication_across_matching_keywords(self) -> None:
        """Matching multiple keywords in same group produces no duplicate risks."""
        gen = EpicGenerator()
        # Both 'auth' and 'security' map to the same risk text.
        risks = gen._suggest_risks("Security Auth Module", "")
        unique_risks = list(dict.fromkeys(risks))
        assert risks == unique_risks


class TestSuggestionEngineIntegration:
    """Integration tests -- suggestions appear in rendered output."""

    def test_render_stories_empty_uses_suggestions(self) -> None:
        """_render_stories falls back to suggestion engine when config.stories is empty."""
        gen = EpicGenerator()
        config = _make_config(title="User Authentication", stories=[], number=7)
        result = "\n".join(gen._render_stories(config))
        # Auth-related titles should appear (with (suggested) suffix)
        assert "(suggested)" in result
        assert "Auth Endpoints (suggested)" in result or "Session Management (suggested)" in result

    def test_render_stories_user_provided_overrides_suggestions(self) -> None:
        """User-provided stories are used as-is; no suggestions mixed in."""
        gen = EpicGenerator()
        config = _make_config(
            title="User Authentication",
            stories=[EpicStoryStub(title="My Custom Story", points=3)],
            number=7,
        )
        result = "\n".join(gen._render_stories(config))
        assert "My Custom Story" in result
        assert "(suggested)" not in result

    def test_render_risk_assessment_empty_uses_suggestions(self) -> None:
        """_render_risk_assessment uses suggestion engine when config.risks is empty."""
        gen = EpicGenerator()
        config = _make_config(
            title="API Gateway",
            risks=[],
            style="comprehensive",
        )
        result = "\n".join(gen._render_risk_assessment(config, {}))
        # API risk should appear
        assert "Breaking API changes" in result
        # Placeholder should NOT appear when suggestions found
        assert "No risks identified" not in result

    def test_render_risk_assessment_no_keywords_shows_placeholder(self) -> None:
        """No-keyword title falls back to 'No risks identified' placeholder."""
        gen = EpicGenerator()
        config = _make_config(
            title="Widget Refactor",
            risks=[],
            style="comprehensive",
        )
        result = "\n".join(gen._render_risk_assessment(config, {}))
        assert "No risks identified" in result

    def test_full_generate_auth_epic_has_suggested_stories(self) -> None:
        """End-to-end: generate with auth title and no stories produces suggested stubs."""
        gen = EpicGenerator()
        config = EpicConfig(
            title="User Authentication",
            number=10,
            stories=[],
            style="standard",
        )
        output = gen.generate(config)
        assert "(suggested)" in output

    def test_full_generate_no_stories_no_keyword_fallback(self) -> None:
        """End-to-end: generate with unrecognized title falls back to generic stubs."""
        gen = EpicGenerator()
        config = EpicConfig(
            title="Miscellaneous Tasks",
            number=99,
            stories=[],
            style="standard",
        )
        output = gen.generate(config)
        assert "(suggested)" in output
        assert "Foundation & Setup (suggested)" in output


class TestPerformanceTargets:
    """Unit tests for EpicGenerator._render_performance_targets() (Story 91.5)."""

    def test_no_enrichment_no_config_renders_test_coverage(self) -> None:
        """With no enrichment and no config, test coverage row always present."""
        gen = EpicGenerator()
        lines = gen._render_performance_targets()
        output = "\n".join(lines)
        assert "## Performance Targets" in output
        assert "Test coverage" in output
        assert ">= 80%" in output
        assert "pytest --cov" in output

    def test_section_markers_always_present(self) -> None:
        """docsmcp markers wrap the section regardless of inputs."""
        gen = EpicGenerator()
        lines = gen._render_performance_targets()
        output = "\n".join(lines)
        assert "<!-- docsmcp:start:performance-targets -->" in output
        assert "<!-- docsmcp:end:performance-targets -->" in output

    def test_ac_count_above_threshold_adds_row(self) -> None:
        """AC count > 5 adds acceptance criteria pass rate row."""
        gen = EpicGenerator()
        config = EpicConfig(
            title="Big Epic",
            acceptance_criteria=[f"AC{i}" for i in range(6)],
        )
        lines = gen._render_performance_targets(config=config)
        output = "\n".join(lines)
        assert "Acceptance criteria pass rate" in output
        assert "CI pipeline" in output

    def test_ac_count_at_threshold_omits_row(self) -> None:
        """AC count == 5 does NOT add acceptance criteria row (threshold is > 5)."""
        gen = EpicGenerator()
        config = EpicConfig(
            title="Medium Epic",
            acceptance_criteria=[f"AC{i}" for i in range(5)],
        )
        lines = gen._render_performance_targets(config=config)
        output = "\n".join(lines)
        assert "Acceptance criteria pass rate" not in output

    def test_files_above_threshold_adds_quality_gate_row(self) -> None:
        """Files > 3 adds quality gate score row."""
        gen = EpicGenerator()
        config = EpicConfig(
            title="Multi-file Epic",
            files=["a.py", "b.py", "c.py", "d.py"],
        )
        lines = gen._render_performance_targets(config=config)
        output = "\n".join(lines)
        assert "Quality gate score" in output
        assert "tapps_quality_gate" in output
        assert ">= 70/100" in output

    def test_files_at_threshold_omits_quality_gate_row(self) -> None:
        """Files == 3 does NOT add quality gate row (threshold is > 3)."""
        gen = EpicGenerator()
        config = EpicConfig(
            title="Small Epic",
            files=["a.py", "b.py", "c.py"],
        )
        lines = gen._render_performance_targets(config=config)
        output = "\n".join(lines)
        assert "Quality gate score" not in output

    def test_stories_above_threshold_adds_completion_rate_row(self) -> None:
        """Stories > 3 adds story completion rate row."""
        gen = EpicGenerator()
        config = EpicConfig(
            title="Large Epic",
            stories=[
                EpicStoryStub(number=1, title="S1"),
                EpicStoryStub(number=2, title="S2"),
                EpicStoryStub(number=3, title="S3"),
                EpicStoryStub(number=4, title="S4"),
            ],
        )
        lines = gen._render_performance_targets(config=config)
        output = "\n".join(lines)
        assert "Story completion rate" in output
        assert "Sprint tracking" in output

    def test_stories_at_threshold_omits_completion_rate_row(self) -> None:
        """Stories == 3 does NOT add story completion rate row (threshold is > 3)."""
        gen = EpicGenerator()
        config = EpicConfig(
            title="Small Epic",
            stories=[
                EpicStoryStub(number=1, title="S1"),
                EpicStoryStub(number=2, title="S2"),
                EpicStoryStub(number=3, title="S3"),
            ],
        )
        lines = gen._render_performance_targets(config=config)
        output = "\n".join(lines)
        assert "Story completion rate" not in output

    def test_expert_guidance_rendered_before_derived_table(self) -> None:
        """Expert guidance appears before config-derived table rows."""
        gen = EpicGenerator()
        enrichment = {
            "expert_guidance": [
                {
                    "expert": "Performance Expert",
                    "domain": "performance",
                    "advice": "Keep p99 latency under 200ms.",
                    "confidence": "80%",
                }
            ]
        }
        config = EpicConfig(title="Perf Epic")
        lines = gen._render_performance_targets(enrichment=enrichment, config=config)
        output = "\n".join(lines)
        # Expert advice present
        assert "Performance Expert" in output
        assert "p99 latency" in output
        # Config-derived table still present
        assert "Test coverage" in output
        # Expert text appears before the table
        expert_pos = output.index("Performance Expert")
        table_pos = output.index("Test coverage")
        assert expert_pos < table_pos

    def test_expert_low_confidence_omitted(self) -> None:
        """Expert guidance below 50% confidence is not rendered."""
        gen = EpicGenerator()
        enrichment = {
            "expert_guidance": [
                {
                    "expert": "Uncertain Expert",
                    "domain": "performance",
                    "advice": "Maybe optimize the DB.",
                    "confidence": "30%",
                }
            ]
        }
        lines = gen._render_performance_targets(enrichment=enrichment)
        output = "\n".join(lines)
        assert "Uncertain Expert" not in output
        # Config-derived table still renders
        assert "Test coverage" in output

    def test_comprehensive_epic_includes_performance_targets(self) -> None:
        """End-to-end: comprehensive epic always has Performance Targets section."""
        gen = EpicGenerator()
        config = EpicConfig(
            title="Comprehensive Test Epic",
            number=42,
            style="comprehensive",
            goal="Ship it.",
        )
        output = gen.generate(config)
        assert "## Performance Targets" in output
        assert "Test coverage" in output

    def test_non_performance_expert_domain_excluded(self) -> None:
        """Expert guidance with a non-performance domain is not shown."""
        gen = EpicGenerator()
        enrichment = {
            "expert_guidance": [
                {
                    "expert": "Security Expert",
                    "domain": "security",
                    "advice": "Use TLS everywhere.",
                    "confidence": "90%",
                }
            ]
        }
        lines = gen._render_performance_targets(enrichment=enrichment)
        output = "\n".join(lines)
        assert "Security Expert" not in output
        assert "Test coverage" in output


# ---------------------------------------------------------------------------
# STORY-104.4: ## Refs section (auto-extracted TAP-### cross-refs)
# ---------------------------------------------------------------------------


class TestEpicRefsSection:
    """Auto-extracted TAP-### refs surface as a `## Refs` section."""

    def setup_method(self) -> None:
        self.gen = EpicGenerator()

    def test_refs_extracted_from_dependencies(self) -> None:
        config = _make_config(dependencies=["TAP-496", "Epic 4"])
        content = self.gen.generate(config)
        assert "## Refs" in content
        assert "TAP-496" in content

    def test_refs_extracted_from_motivation_prose(self) -> None:
        config = _make_config(
            motivation="Follow-up from TAP-834 (memory shim retirement).",
        )
        content = self.gen.generate(config)
        assert "## Refs" in content
        # Ref appears in both the motivation body and the Refs list.
        assert content.count("TAP-834") >= 2

    def test_refs_deduped(self) -> None:
        config = _make_config(
            dependencies=["TAP-496"],
            motivation="See TAP-496 for context.",
        )
        content = self.gen.generate(config)
        # Ref appears in Refs section exactly once.
        refs_idx = content.index("## Refs")
        refs_body = content[refs_idx:]
        # Count inside the refs section only.
        assert refs_body.count("TAP-496") == 1

    def test_refs_omitted_when_no_tap_refs(self) -> None:
        config = _make_config(
            dependencies=["Epic 4", "some-external-service"],
            motivation="No TAP references here.",
            blocks=["Epic 43"],
        )
        content = self.gen.generate(config)
        assert "## Refs" not in content

    def test_refs_emitted_for_minimal_style(self) -> None:
        config = _make_config(
            style="minimal",
            stories=[],
            motivation="Prior: TAP-100.",
        )
        content = self.gen.generate(config)
        assert "## Refs" in content
        assert "TAP-100" in content

    def test_refs_emitted_for_comprehensive_style(self) -> None:
        config = _make_config(
            style="comprehensive",
            dependencies=["TAP-200"],
            risks=["Regression in TAP-201 area"],
        )
        content = self.gen.generate(config)
        assert "## Refs" in content
        assert "TAP-200" in content
        assert "TAP-201" in content
