"""Tests for tools.checklist_epic — epic markdown structural validation.

Split out of ``test_checklist.py`` alongside the source split (TAP-5733).
These import through ``tapps_mcp.tools.checklist`` on purpose: that is the
backward-compatible path the re-export block promises, so these tests also
guard it.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from tapps_mcp.tools.checklist import (
    TASK_TOOL_MAP_HIGH,
    TASK_TOOL_MAP_LOW,
    CallTracker,
    EpicChecklistResult,
    EpicValidation,
    validate_epic_markdown,
)

_EPIC_SAMPLES = Path(__file__).resolve().parents[1] / "fixtures" / "epic"


def _sample(name: str) -> str:
    """Load an epic markdown sample from tests/fixtures/epic/."""
    return (_EPIC_SAMPLES / f"{name}.md").read_text(encoding="utf-8")


_WELL_FORMED_EPIC = _sample("well_formed")
_EPIC_MISSING_STORIES_SECTION = _sample("missing_stories_section")
_EPIC_STORY_NO_AC = _sample("story_no_acceptance_criteria")
_EPIC_SIZE_POINT_MISMATCH = _sample("size_point_mismatch")
_EPIC_WITH_CYCLE = _sample("dependency_cycle")
_EPIC_FILES_TABLE_MISMATCH = _sample("files_table_mismatch")



class TestEpicChecklist:
    """Tests for task_type='epic' in the standard checklist."""

    def setup_method(self) -> None:
        CallTracker.reset()

    def test_epic_checklist_returns_items(self) -> None:
        result = CallTracker.evaluate("epic", engagement_level="medium")
        assert result.task_type == "epic"
        assert "tapps_checklist" in result.missing_required
        assert result.complete is False

    def test_epic_checklist_complete(self) -> None:
        CallTracker.record("tapps_checklist")
        result = CallTracker.evaluate("epic", engagement_level="medium")
        assert result.complete is True

    def test_epic_in_high_engagement(self) -> None:
        assert "epic" in TASK_TOOL_MAP_HIGH

    def test_epic_in_low_engagement(self) -> None:
        assert "epic" in TASK_TOOL_MAP_LOW


class TestValidateEpicMarkdown:
    """Tests for validate_epic_markdown structural validation."""

    def test_well_formed_epic_validates_clean(self) -> None:
        result = validate_epic_markdown(_WELL_FORMED_EPIC)
        assert result.valid is True
        assert len(result.findings) == 0
        assert len(result.stories) == 2
        assert "Goal" in result.sections_found
        assert "Acceptance Criteria" in result.sections_found
        assert "Stories" in result.sections_found

    def test_well_formed_story_fields(self) -> None:
        result = validate_epic_markdown(_WELL_FORMED_EPIC)
        s1 = result.stories[0]
        assert s1.story_id == "99.1"
        assert s1.title == "First Story"
        assert s1.points == 2
        assert s1.size == "S"
        assert s1.priority == "P1"
        assert s1.has_acceptance_criteria is True
        assert s1.has_tasks is True
        assert "src/foo.py" in s1.files
        assert "src/bar.py" in s1.files

    def test_missing_stories_section_flagged(self) -> None:
        result = validate_epic_markdown(_EPIC_MISSING_STORIES_SECTION)
        assert result.valid is False
        errors = [f for f in result.findings if f.severity == "error"]
        messages = [f.message for f in errors]
        assert any("Stories" in m for m in messages)
        assert any("No stories found" in m for m in messages)

    def test_story_without_ac_flagged(self) -> None:
        result = validate_epic_markdown(_EPIC_STORY_NO_AC)
        assert result.valid is False
        errors = [f for f in result.findings if f.severity == "error"]
        assert any("101.1" in f.message and "Acceptance Criteria" in f.message for f in errors)

    def test_point_size_mismatch_warning(self) -> None:
        result = validate_epic_markdown(_EPIC_SIZE_POINT_MISMATCH)
        # Mismatch is a warning, not an error
        warnings = [f for f in result.findings if f.severity == "warning"]
        assert any(
            "102.1" in f.message and "expects 1-2 points but has 8" in f.message for f in warnings
        )

    def test_point_size_mismatch_does_not_fail_valid(self) -> None:
        result = validate_epic_markdown(_EPIC_SIZE_POINT_MISMATCH)
        # Only warnings, so still valid
        assert result.valid is True

    def test_dependency_cycle_detected(self) -> None:
        result = validate_epic_markdown(_EPIC_WITH_CYCLE)
        assert result.valid is False
        errors = [f for f in result.findings if f.severity == "error"]
        assert any("cycle" in f.message.lower() for f in errors)

    def test_files_table_missing_entry_warning(self) -> None:
        result = validate_epic_markdown(_EPIC_FILES_TABLE_MISMATCH)
        warnings = [f for f in result.findings if f.severity == "warning"]
        assert any("src/beta.py" in f.message for f in warnings)

    def test_files_table_present_entry_no_warning(self) -> None:
        result = validate_epic_markdown(_EPIC_FILES_TABLE_MISMATCH)
        warnings = [f for f in result.findings if f.severity == "warning"]
        assert not any("src/alpha.py" in f.message for f in warnings)

    def test_missing_goal_section(self) -> None:
        content = dedent("""\
            # Epic 105: No Goal

            ## Acceptance Criteria

            - [ ] Something

            ## Stories

            ### Story 105.1: A Story

            **Points:** 1 | **Size:** S | **Priority:** P1

            #### Tasks

            - [ ] Task

            #### Acceptance Criteria

            - [ ] AC
        """)
        result = validate_epic_markdown(content)
        assert result.valid is False
        assert any("Goal" in f.message for f in result.findings)

    def test_missing_acceptance_criteria_section(self) -> None:
        content = dedent("""\
            # Epic 106: No AC Section

            ## Goal

            Test goal.

            ## Stories

            ### Story 106.1: A Story

            **Points:** 1 | **Size:** S | **Priority:** P1

            #### Tasks

            - [ ] Task

            #### Acceptance Criteria

            - [ ] AC
        """)
        result = validate_epic_markdown(content)
        assert result.valid is False
        assert any("Acceptance Criteria" in f.message for f in result.findings)

    def test_story_missing_points_warns(self) -> None:
        content = dedent("""\
            # Epic 107: Missing Points

            ## Goal

            Test.

            ## Acceptance Criteria

            - [ ] AC

            ## Stories

            ### Story 107.1: No Points

            **Size:** M | **Priority:** P1

            #### Tasks

            - [ ] Task

            #### Acceptance Criteria

            - [ ] AC
        """)
        result = validate_epic_markdown(content)
        warnings = [f for f in result.findings if f.severity == "warning"]
        assert any("107.1" in f.message and "Points" in f.message for f in warnings)


class TestEvaluateEpic:
    """Tests for CallTracker.evaluate_epic method."""

    def setup_method(self) -> None:
        CallTracker.reset()

    def test_evaluate_epic_without_file(self) -> None:
        result = CallTracker.evaluate_epic(engagement_level="medium")
        assert isinstance(result, EpicChecklistResult)
        assert result.task_type == "epic"
        assert result.epic_validation is None
        assert "tapps_checklist" in result.missing_required

    def test_evaluate_epic_with_file(self, tmp_path: Path) -> None:
        epic_file = tmp_path / "EPIC-99.md"
        epic_file.write_text(_WELL_FORMED_EPIC, encoding="utf-8")
        result = CallTracker.evaluate_epic(
            file_path=str(epic_file),
            engagement_level="medium",
        )
        assert result.epic_validation is not None
        assert result.epic_validation.valid is True
        assert len(result.epic_validation.stories) == 2

    def test_evaluate_epic_with_bad_file(self, tmp_path: Path) -> None:
        epic_file = tmp_path / "EPIC-BAD.md"
        epic_file.write_text(_EPIC_MISSING_STORIES_SECTION, encoding="utf-8")
        result = CallTracker.evaluate_epic(
            file_path=str(epic_file),
            engagement_level="medium",
        )
        assert result.epic_validation is not None
        assert result.epic_validation.valid is False

    def test_evaluate_epic_relative_path_with_project_root(self, tmp_path: Path) -> None:
        """Relative epic_file_path resolves against project_root."""
        docs = tmp_path / "docs" / "epics"
        docs.mkdir(parents=True)
        epic_file = docs / "EPIC-90.md"
        epic_file.write_text(_WELL_FORMED_EPIC, encoding="utf-8")
        result = CallTracker.evaluate_epic(
            file_path="docs/epics/EPIC-90.md",
            engagement_level="medium",
            project_root=tmp_path,
        )
        assert result.epic_validation is not None
        assert result.epic_validation.valid is True

    def test_evaluate_epic_relative_path_without_project_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Relative path without project_root falls back to cwd."""
        docs = tmp_path / "docs"
        docs.mkdir()
        epic_file = docs / "EPIC-CWD.md"
        epic_file.write_text(_WELL_FORMED_EPIC, encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        result = CallTracker.evaluate_epic(
            file_path="docs/EPIC-CWD.md",
            engagement_level="medium",
        )
        assert result.epic_validation is not None
        assert result.epic_validation.valid is True

    def test_evaluate_epic_absolute_path_unchanged(self, tmp_path: Path) -> None:
        """Absolute paths work regardless of project_root."""
        epic_file = tmp_path / "EPIC-ABS.md"
        epic_file.write_text(_WELL_FORMED_EPIC, encoding="utf-8")
        result = CallTracker.evaluate_epic(
            file_path=str(epic_file),
            engagement_level="medium",
            project_root=Path("/some/other/root"),
        )
        assert result.epic_validation is not None
        assert result.epic_validation.valid is True

    def test_evaluate_epic_nonexistent_file_error_message(self, tmp_path: Path) -> None:
        """Non-existent file gives clear error with resolved path."""
        with pytest.raises(
            FileNotFoundError, match=r"Epic file not found:.*no-such-epic\.md.*resolved from"
        ):
            CallTracker.evaluate_epic(
                file_path="no-such-epic.md",
                engagement_level="medium",
                project_root=tmp_path,
            )


class TestEpicWithRealFixtures:
    """Validate parsing against real epic files from the repository."""

    @pytest.fixture()
    def epics_dir(self) -> Path:
        """Return the epics directory, skip if not found."""
        candidates = [
            Path(__file__).resolve().parents[4] / "docs" / "planning" / "epics",
        ]
        for d in candidates:
            if d.is_dir():
                return d
        pytest.skip("epics directory not found")
        return Path()  # unreachable but satisfies mypy

    def test_real_epic_parses_without_crash(self, epics_dir: Path) -> None:
        """Every real epic file should parse without raising.

        Per `feedback_no_md_drafts_for_linear.md`, this repo stopped keeping
        epic markdown on disk — Linear is canonical. So an empty
        `docs/planning/epics/` is the steady-state, not a regression. Skip
        when there's nothing to parse instead of failing.
        """
        epic_files = sorted(epics_dir.glob("EPIC-*.md"))
        if not epic_files:
            pytest.skip(
                "No EPIC-*.md files in docs/planning/epics/ — epics live in "
                "Linear in this repo (see feedback_no_md_drafts_for_linear.md)."
            )
        for ef in epic_files[:5]:  # sample first 5 to keep fast
            content = ef.read_text(encoding="utf-8")
            result = validate_epic_markdown(content)
            assert isinstance(result, EpicValidation)

    def test_epic_1_has_stories(self, epics_dir: Path) -> None:
        """EPIC-1 should have multiple stories detected."""
        ep1 = epics_dir / "EPIC-1-CORE-QUALITY-MVP.md"
        if not ep1.exists():
            pytest.skip("EPIC-1 not found")
        content = ep1.read_text(encoding="utf-8")
        result = validate_epic_markdown(content)
        assert len(result.stories) > 0, "Expected stories in EPIC-1"
