"""Tests for tools.checklist — session call tracking and epic validation."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from tapps_mcp.tools.checklist import (
    TASK_TOOL_MAP,
    TASK_TOOL_MAP_HIGH,
    TASK_TOOL_MAP_LOW,
    CallTracker,
    ChecklistResult,
    EpicChecklistResult,
    EpicValidation,
    ToolCallRecord,
    validate_epic_markdown,
)


class TestToolCallRecord:
    def test_creation(self):
        r = ToolCallRecord(tool_name="tapps_score_file")
        assert r.tool_name == "tapps_score_file"
        assert r.timestamp > 0


class TestTaskToolMap:
    def test_feature_task(self):
        m = TASK_TOOL_MAP["feature"]
        assert "tapps_score_file" in m["required"]
        assert "tapps_quality_gate" in m["required"]

    def test_bugfix_task(self):
        m = TASK_TOOL_MAP["bugfix"]
        assert "tapps_score_file" in m["required"]

    def test_refactor_task(self):
        m = TASK_TOOL_MAP["refactor"]
        assert "tapps_score_file" in m["required"]
        assert "tapps_quality_gate" in m["required"]

    def test_security_task(self):
        m = TASK_TOOL_MAP["security"]
        assert "tapps_security_scan" in m["required"]
        assert "tapps_quality_gate" in m["required"]

    def test_review_task(self):
        m = TASK_TOOL_MAP["review"]
        assert "tapps_score_file" in m["required"]
        assert "tapps_security_scan" in m["required"]
        assert "tapps_quality_gate" in m["required"]

    def test_all_task_types_present(self):
        expected = {"feature", "bugfix", "refactor", "security", "review", "epic"}
        assert set(TASK_TOOL_MAP.keys()) == expected

    def test_epic_task(self):
        m = TASK_TOOL_MAP["epic"]
        assert "tapps_checklist" in m["required"]


class TestCallTracker:
    def setup_method(self):
        CallTracker.reset()

    def test_record_and_get(self):
        CallTracker.record("tapps_score_file")
        assert "tapps_score_file" in CallTracker.get_called_tools()

    def test_total_calls(self):
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_quality_gate")
        assert CallTracker.total_calls() == 3

    def test_unique_tools(self):
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_score_file")
        called = CallTracker.get_called_tools()
        assert called == {"tapps_score_file"}

    def test_reset(self):
        CallTracker.record("tapps_score_file")
        CallTracker.reset()
        assert CallTracker.get_called_tools() == set()
        assert CallTracker.total_calls() == 0

    def test_evaluate_complete(self):
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_quality_gate")
        result = CallTracker.evaluate("feature")
        assert result.complete is True
        assert result.missing_required == []
        assert result.task_type == "feature"

    def test_evaluate_incomplete(self):
        result = CallTracker.evaluate("feature")
        assert result.complete is False
        assert "tapps_score_file" in result.missing_required
        assert "tapps_quality_gate" in result.missing_required

    def test_evaluate_partial(self):
        CallTracker.record("tapps_score_file")
        result = CallTracker.evaluate("feature")
        assert result.complete is False
        assert "tapps_quality_gate" in result.missing_required
        assert "tapps_score_file" not in result.missing_required

    def test_evaluate_unknown_task_defaults_to_review(self):
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_security_scan")
        CallTracker.record("tapps_quality_gate")
        result = CallTracker.evaluate("unknown_task")
        assert result.task_type == "unknown_task"
        assert result.complete is True
        assert result.policy_fallback is True
        assert result.resolved_policy_task_type == "review"

    def test_evaluate_unknown_task_strict_raises(self):
        with pytest.raises(ValueError, match="Unknown task_type"):
            CallTracker.evaluate(
                "not_a_real_task",
                strict_unknown_task_type=True,
            )

    def test_begin_session_filters_calls(self):
        CallTracker.record("tapps_score_file")
        CallTracker.begin_session()
        CallTracker.record("tapps_quality_gate")
        r = CallTracker.evaluate("feature")
        assert "tapps_score_file" not in r.called
        assert "tapps_quality_gate" in r.called

    def test_research_satisfies_consult_and_docs(self):
        from tapps_mcp.tools.checklist import _compute_effective_tools

        eff = _compute_effective_tools({"tapps_research"})
        assert "tapps_consult_expert" in eff
        assert "tapps_lookup_docs" in eff

    def test_evaluate_includes_recommended(self):
        result = CallTracker.evaluate("feature")
        assert "tapps_security_scan" in result.missing_recommended

    def test_evaluate_includes_optional(self):
        result = CallTracker.evaluate("feature")
        assert "tapps_checklist" in result.missing_optional

    def test_evaluate_total_calls(self):
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_quality_gate")
        result = CallTracker.evaluate("feature")
        assert result.total_calls == 2

    def test_evaluate_called_sorted(self):
        CallTracker.record("tapps_quality_gate")
        CallTracker.record("tapps_score_file")
        result = CallTracker.evaluate("feature")
        assert result.called == ["tapps_quality_gate", "tapps_score_file"]

    def test_evaluate_engagement_high_feature_requires_more(self):
        """High engagement: feature requires score, gate, security_scan."""
        result = CallTracker.evaluate("feature", engagement_level="high")
        assert "tapps_security_scan" in result.missing_required
        assert "tapps_score_file" in result.missing_required
        assert "tapps_quality_gate" in result.missing_required

    def test_evaluate_engagement_high_feature_complete_with_all(self):
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_quality_gate")
        CallTracker.record("tapps_security_scan")
        result = CallTracker.evaluate("feature", engagement_level="high")
        assert result.complete is True
        assert result.missing_required == []

    def test_evaluate_engagement_low_feature_requires_less(self):
        """Low engagement: feature only requires quality_gate."""
        result = CallTracker.evaluate("feature", engagement_level="low")
        assert "tapps_quality_gate" in result.missing_required
        assert "tapps_score_file" in result.missing_recommended

    def test_evaluate_engagement_low_feature_complete_with_gate_only(self):
        CallTracker.record("tapps_quality_gate")
        result = CallTracker.evaluate("feature", engagement_level="low")
        assert result.complete is True

    def test_engagement_maps_exist(self):
        assert set(TASK_TOOL_MAP_HIGH.keys()) == set(TASK_TOOL_MAP.keys())
        assert set(TASK_TOOL_MAP_LOW.keys()) == set(TASK_TOOL_MAP.keys())
        assert "tapps_security_scan" in TASK_TOOL_MAP_HIGH["feature"]["required"]
        assert "tapps_security_scan" not in TASK_TOOL_MAP_LOW["feature"]["required"]


class TestChecklistResult:
    def test_creation(self):
        r = ChecklistResult(task_type="feature", complete=True, total_calls=5)
        assert r.task_type == "feature"
        assert r.complete is True
        assert r.total_calls == 5
        assert r.called == []
        assert r.missing_required == []


# ---------------------------------------------------------------------------
# Epic checklist and validation tests
# ---------------------------------------------------------------------------

_WELL_FORMED_EPIC = dedent("""\
    # Epic 99: Test Epic

    ## Goal

    Test goal description.

    ## Motivation

    Test motivation.

    ## Acceptance Criteria

    - [ ] First AC
    - [ ] Second AC

    ## Stories

    ### Story 99.1: First Story

    **Points:** 2 | **Size:** S | **Priority:** P1

    **Files:**
    - `src/foo.py`
    - `src/bar.py`

    #### Tasks

    - [ ] Task one
    - [ ] Task two

    #### Acceptance Criteria

    - [ ] AC one
    - [ ] AC two

    ---

    ### Story 99.2: Second Story

    **Points:** 5 | **Size:** M | **Priority:** P2

    **Files:**
    - `src/baz.py`

    #### Tasks

    - [ ] Task A

    #### Acceptance Criteria

    - [ ] AC A
""")

_EPIC_MISSING_STORIES_SECTION = dedent("""\
    # Epic 100: No Stories

    ## Goal

    Some goal.

    ## Acceptance Criteria

    - [ ] Something
""")

_EPIC_STORY_NO_AC = dedent("""\
    # Epic 101: Story Without AC

    ## Goal

    Some goal.

    ## Acceptance Criteria

    - [ ] Something

    ## Stories

    ### Story 101.1: Missing AC Story

    **Points:** 3 | **Size:** M | **Priority:** P1

    **Files:**
    - `src/thing.py`

    #### Tasks

    - [ ] Do stuff
""")

_EPIC_SIZE_POINT_MISMATCH = dedent("""\
    # Epic 102: Size Mismatch

    ## Goal

    Some goal.

    ## Acceptance Criteria

    - [ ] Something

    ## Stories

    ### Story 102.1: Too Many Points for S

    **Points:** 8 | **Size:** S | **Priority:** P1

    **Files:**
    - `src/big.py`

    #### Tasks

    - [ ] Do stuff

    #### Acceptance Criteria

    - [ ] AC
""")

_EPIC_WITH_CYCLE = dedent("""\
    # Epic 103: Cyclic Dependencies

    ## Goal

    Some goal.

    ## Acceptance Criteria

    - [ ] Something

    ## Stories

    ### Story 103.1: Story A

    **Points:** 2 | **Size:** S | **Priority:** P1

    Dependencies: Story 103.2

    #### Tasks

    - [ ] Do A

    #### Acceptance Criteria

    - [ ] AC A

    ### Story 103.2: Story B

    **Points:** 2 | **Size:** S | **Priority:** P1

    Dependencies: Story 103.1

    #### Tasks

    - [ ] Do B

    #### Acceptance Criteria

    - [ ] AC B
""")

_EPIC_FILES_TABLE_MISMATCH = dedent("""\
    # Epic 104: Files Table

    ## Goal

    Some goal.

    ## Acceptance Criteria

    - [ ] Something

    ## Stories

    ### Story 104.1: Has Files

    **Points:** 2 | **Size:** S | **Priority:** P1

    **Files:**
    - `src/alpha.py`
    - `src/beta.py`

    #### Tasks

    - [ ] Task

    #### Acceptance Criteria

    - [ ] AC

    ## Files-Affected

    | File | Change |
    |---|---|
    | `src/alpha.py` | Modified |
""")


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
        assert any(
            "101.1" in f.message and "Acceptance Criteria" in f.message
            for f in errors
        )

    def test_point_size_mismatch_warning(self) -> None:
        result = validate_epic_markdown(_EPIC_SIZE_POINT_MISMATCH)
        # Mismatch is a warning, not an error
        warnings = [f for f in result.findings if f.severity == "warning"]
        assert any(
            "102.1" in f.message and "expects 1-2 points but has 8" in f.message
            for f in warnings
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
            file_path=str(epic_file), engagement_level="medium",
        )
        assert result.epic_validation is not None
        assert result.epic_validation.valid is True
        assert len(result.epic_validation.stories) == 2

    def test_evaluate_epic_with_bad_file(self, tmp_path: Path) -> None:
        epic_file = tmp_path / "EPIC-BAD.md"
        epic_file.write_text(_EPIC_MISSING_STORIES_SECTION, encoding="utf-8")
        result = CallTracker.evaluate_epic(
            file_path=str(epic_file), engagement_level="medium",
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

    def test_evaluate_epic_relative_path_without_project_root(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
        with pytest.raises(FileNotFoundError, match=r"Epic file not found:.*no-such-epic\.md.*resolved from"):
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
        """Every real epic file should parse without raising."""
        epic_files = sorted(epics_dir.glob("EPIC-*.md"))
        assert len(epic_files) > 0, "Expected at least one epic file"
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
