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
        expected = {"feature", "bugfix", "refactor", "security", "review", "epic", "release"}
        assert set(TASK_TOOL_MAP.keys()) == expected

    def test_epic_task(self):
        m = TASK_TOOL_MAP["epic"]
        assert "tapps_checklist" in m["required"]


class TestCallTracker:
    # Tests in this class assert against the medium TASK_TOOL_MAP. They were
    # written before the high/low maps existed and historically read engagement
    # from `load_settings().llm_engagement_level`. That coupling is order-
    # dependent on CI — sibling tests that monkeypatch TAPPS_MCP_LLM_ENGAGEMENT_LEVEL
    # or call tapps_set_engagement_level() can leak HIGH/LOW into the cached
    # settings. Pass engagement_level="medium" explicitly via the helper below
    # so these assertions are independent of global state.

    @staticmethod
    def _evaluate(task_type, **kwargs):
        return CallTracker.evaluate(task_type, engagement_level="medium", **kwargs)

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
        result = self._evaluate("feature")
        assert result.complete is True
        assert result.missing_required == []
        assert result.task_type == "feature"

    def test_evaluate_incomplete(self):
        result = self._evaluate("feature")
        assert result.complete is False
        assert "tapps_score_file" in result.missing_required
        assert "tapps_quality_gate" in result.missing_required

    def test_evaluate_partial(self):
        CallTracker.record("tapps_score_file")
        result = self._evaluate("feature")
        assert result.complete is False
        assert "tapps_quality_gate" in result.missing_required
        assert "tapps_score_file" not in result.missing_required

    def test_evaluate_unknown_task_defaults_to_review(self):
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_security_scan")
        CallTracker.record("tapps_quality_gate")
        result = self._evaluate("unknown_task")
        assert result.task_type == "unknown_task"
        assert result.complete is True
        assert result.policy_fallback is True
        assert result.resolved_policy_task_type == "review"

    def test_evaluate_unknown_task_strict_raises(self):
        with pytest.raises(ValueError, match="Unknown task_type"):
            self._evaluate(
                "not_a_real_task",
                strict_unknown_task_type=True,
            )

    def test_begin_session_filters_calls(self):
        CallTracker.record("tapps_score_file")
        CallTracker.begin_session()
        CallTracker.record("tapps_quality_gate")
        r = self._evaluate("feature")
        assert "tapps_score_file" not in r.called
        assert "tapps_quality_gate" in r.called

    def test_evaluate_includes_recommended(self):
        result = self._evaluate("feature")
        assert "tapps_security_scan" in result.missing_recommended

    def test_evaluate_includes_optional(self):
        result = self._evaluate("feature")
        assert "tapps_checklist" in result.missing_optional

    def test_evaluate_total_calls(self):
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_quality_gate")
        result = self._evaluate("feature")
        assert result.total_calls == 2

    def test_evaluate_called_sorted(self):
        CallTracker.record("tapps_quality_gate")
        CallTracker.record("tapps_score_file")
        result = self._evaluate("feature")
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


# ---------------------------------------------------------------------------
# Tests — linked headings and table-linked stories (Story 90.2)
# ---------------------------------------------------------------------------


class TestLinkedHeadingParsing:
    """Tests for ### [X.Y](path) -- Title format in checklist epic parser."""

    def test_linked_heading_parsed(self) -> None:
        content = dedent("""\
        # Epic 88: Test

        ## Goal

        Test linked headings.

        ## Acceptance Criteria

        - [ ] Done

        ## Stories

        ### [88.1](EPIC-88/story-88.1-slug.md) -- Staleness-First Sort

        **Points:** 3 | **Size:** M | **Priority:** P1

        #### Acceptance Criteria

        - [ ] Works

        #### Tasks

        - [ ] Implement

        ### [88.2](EPIC-88/story-88.2-slug.md) -- Response Truncation

        **Points:** 5 | **Size:** M | **Priority:** P2

        #### Acceptance Criteria

        - [ ] Works

        #### Tasks

        - [ ] Implement
        """)
        result = validate_epic_markdown(content)
        assert len(result.stories) == 2
        assert result.stories[0].story_id == "88.1"
        assert result.stories[0].linked_file == "EPIC-88/story-88.1-slug.md"
        assert result.stories[0].title == "Staleness-First Sort"
        assert result.stories[1].story_id == "88.2"
        assert result.stories[1].linked_file == "EPIC-88/story-88.2-slug.md"

    def test_mixed_inline_and_linked(self) -> None:
        content = dedent("""\
        # Epic 90: Mixed

        ## Goal

        Test mixed formats.

        ## Acceptance Criteria

        - [ ] Done

        ## Stories

        ### Story 90.1: Inline Story

        **Points:** 2 | **Size:** S | **Priority:** P1

        #### Acceptance Criteria

        - [ ] Works

        #### Tasks

        - [ ] Do it

        ### [90.2](EPIC-90/story-90.2.md) -- Linked Story

        **Points:** 3 | **Size:** M | **Priority:** P2

        #### Acceptance Criteria

        - [ ] Works

        #### Tasks

        - [ ] Do it
        """)
        result = validate_epic_markdown(content)
        assert len(result.stories) == 2
        ids = {s.story_id for s in result.stories}
        assert "90.1" in ids
        assert "90.2" in ids
        linked = next(s for s in result.stories if s.story_id == "90.2")
        assert linked.linked_file == "EPIC-90/story-90.2.md"
        inline = next(s for s in result.stories if s.story_id == "90.1")
        assert inline.linked_file is None


class TestTableLinkedStoryParsing:
    """Tests for table-linked story rows in checklist epic parser."""

    def test_table_stories_parsed(self) -> None:
        content = dedent("""\
        # Epic: Plan Optimization

        ## Goal

        Faster planning.

        ## Acceptance Criteria

        - [ ] Done

        ## Stories

        | ID | Story | Size | Priority |
        |---|---|---|---|
        | PLANOPT-1 | [File dependency graph](story-planopt-1.md) | M | P1 |
        | PLANOPT-2 | [Parallel execution](story-planopt-2.md) | L | P2 |
        """)
        result = validate_epic_markdown(content)
        assert len(result.stories) == 2
        assert result.stories[0].story_id == "PLANOPT-1"
        assert result.stories[0].title == "File dependency graph"
        assert result.stories[0].linked_file == "story-planopt-1.md"
        assert result.stories[0].size == "M"
        assert result.stories[0].priority == "P1"
        assert result.stories[1].story_id == "PLANOPT-2"
        assert result.stories[1].size == "L"

    def test_table_missing_size_priority(self) -> None:
        content = dedent("""\
        # Epic: Minimal Table

        ## Goal

        Test.

        ## Acceptance Criteria

        - [ ] Done

        ## Stories

        | ID | Story |
        |---|---|
        | T-1 | [First](story-t1.md) |
        """)
        result = validate_epic_markdown(content)
        assert len(result.stories) == 1
        assert result.stories[0].story_id == "T-1"
        assert result.stories[0].linked_file == "story-t1.md"
        assert result.stories[0].size is None
        assert result.stories[0].priority is None

    def test_table_plain_text_ignored(self) -> None:
        """Table rows without markdown links are not matched."""
        content = dedent("""\
        # Epic: Plain

        ## Goal

        Test.

        ## Acceptance Criteria

        - [ ] Done

        ## Stories

        | ID | Story | Size |
        |---|---|---|
        | PT-1 | No link here | M |
        | PT-2 | [Linked](story-pt2.md) | L |
        """)
        result = validate_epic_markdown(content)
        assert len(result.stories) == 1
        assert result.stories[0].story_id == "PT-2"

    def test_heading_stories_preferred_over_table(self) -> None:
        """When heading-based stories exist, table rows are not parsed."""
        content = dedent("""\
        # Epic 95: Mixed

        ## Goal

        Test.

        ## Acceptance Criteria

        - [ ] Done

        ## Stories

        ### Story 95.1: Heading Story

        **Points:** 2 | **Size:** S | **Priority:** P1

        #### Acceptance Criteria

        - [ ] Works

        #### Tasks

        - [ ] Implement

        | T-1 | [Table story](story-t1.md) | M | P2 |
        """)
        result = validate_epic_markdown(content)
        # Only heading story should be found; table is not parsed when headings exist
        assert len(result.stories) == 1
        assert result.stories[0].story_id == "95.1"


# ---------------------------------------------------------------------------
# Cross-file story validation (Story 90.3)
# ---------------------------------------------------------------------------


class TestCrossFileStoryValidation:
    """Tests for cross-file story validation in validate_epic_markdown."""

    def _make_epic_with_stories(
        self,
        tmp_path: Path,
        story_files: dict[str, str],
    ) -> Path:
        """Create an epic file with linked stories and write story files."""
        epic_dir = tmp_path / "epics"
        epic_dir.mkdir(exist_ok=True)
        stories_dir = epic_dir / "stories"
        stories_dir.mkdir(exist_ok=True)

        story_lines = []
        for i, (fname, _) in enumerate(story_files.items(), 1):
            story_lines.append(f"| S{i} | [{fname}](stories/{fname}) | M | P1 |")

        epic_content = (
            dedent("""\
        # Epic 96: Cross-File Test

        ## Goal

        Test.

        ## Acceptance Criteria

        - [ ] Done

        ## Stories

        | ID | Story | Size | Priority |
        |---|---|---|---|
        """)
            + "\n".join(story_lines)
            + "\n"
        )

        fp = epic_dir / "EPIC-96.md"
        fp.write_text(epic_content, encoding="utf-8")

        for fname, content in story_files.items():
            (stories_dir / fname).write_text(content, encoding="utf-8")

        return fp

    def test_all_present_full_structure(self, tmp_path: Path) -> None:
        full = dedent("""\
        ## Acceptance Criteria
        - [ ] Works

        ## Tasks
        - [ ] Do it

        ## Definition of Done
        Done.

        **Points:** 3 | **Size:** M
        """)
        fp = self._make_epic_with_stories(tmp_path, {"s1.md": full, "s2.md": full})
        content = fp.read_text(encoding="utf-8")
        result = validate_epic_markdown(content, epic_file_path=fp)

        assert result.cross_file_summary is not None
        s = result.cross_file_summary
        assert s.files_found == 2
        assert s.files_missing == 0
        assert s.with_acceptance_criteria == 2
        assert s.with_tasks == 2
        assert s.with_definition_of_done == 2

    def test_missing_story_file(self, tmp_path: Path) -> None:
        epic_dir = tmp_path / "epics"
        epic_dir.mkdir(exist_ok=True)

        epic_content = dedent("""\
        # Epic 97: Missing File

        ## Goal
        Test.

        ## Acceptance Criteria
        - [ ] Done

        ## Stories

        | ID | Story | Size | Priority |
        |---|---|---|---|
        | S1 | [missing.md](stories/missing.md) | S | P1 |
        """)
        fp = epic_dir / "EPIC-97.md"
        fp.write_text(epic_content, encoding="utf-8")

        content = fp.read_text(encoding="utf-8")
        result = validate_epic_markdown(content, epic_file_path=fp)

        assert result.cross_file_summary is not None
        assert result.cross_file_summary.files_missing == 1
        assert result.cross_file_summary.files_found == 0

        warnings = [
            f for f in result.findings if f.severity == "warning" and "not found" in f.message
        ]
        assert len(warnings) >= 1

    def test_no_epic_file_path_skips_cross_file(self) -> None:
        content = dedent("""\
        # Epic 98: No Path

        ## Goal
        Test.

        ## Acceptance Criteria
        - [ ] Done

        ## Stories

        | ID | Story | Size | Priority |
        |---|---|---|---|
        | S1 | [story.md](story.md) | M | P1 |
        """)
        result = validate_epic_markdown(content)
        assert result.cross_file_summary is None

    def test_validate_linked_stories_false(self, tmp_path: Path) -> None:
        full = "## Acceptance Criteria\n- [ ] Works\n## Tasks\n- [ ] Do\n"
        fp = self._make_epic_with_stories(tmp_path, {"s1.md": full})
        content = fp.read_text(encoding="utf-8")
        result = validate_epic_markdown(
            content,
            epic_file_path=fp,
            validate_linked_stories=False,
        )
        assert result.cross_file_summary is None

    def test_story_without_ac_gets_info_finding(self, tmp_path: Path) -> None:
        no_ac = "## Tasks\n- [ ] Do it\n"
        fp = self._make_epic_with_stories(tmp_path, {"s1.md": no_ac})
        content = fp.read_text(encoding="utf-8")
        result = validate_epic_markdown(content, epic_file_path=fp)

        assert result.cross_file_summary is not None
        assert result.cross_file_summary.with_acceptance_criteria == 0
        info_findings = [
            f
            for f in result.findings
            if f.severity == "info" and "Acceptance Criteria" in f.message
        ]
        assert len(info_findings) >= 1

    def test_summary_string(self, tmp_path: Path) -> None:
        full = "## Acceptance Criteria\n- [ ] AC\n## Tasks\n- [ ] T\n"
        fp = self._make_epic_with_stories(tmp_path, {"s1.md": full})
        content = fp.read_text(encoding="utf-8")
        result = validate_epic_markdown(content, epic_file_path=fp)

        assert result.cross_file_summary is not None
        s = result.cross_file_summary.summary
        assert "1 stories" in s
        assert "files found" in s


# ---------------------------------------------------------------------------
# TAP-476: TDD stage validation
# ---------------------------------------------------------------------------


class TestCheckTDDStages:
    """Tests for check_tdd_stages and helpers."""

    @pytest.mark.asyncio
    async def test_no_git_returns_skipped(self, tmp_path: Path) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from tapps_mcp.tools.checklist import check_tdd_stages

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch(
            "tapps_mcp.tools.subprocess_runner.run_command_async",
            new=AsyncMock(return_value=mock_result),
        ):
            result = await check_tdd_stages(tmp_path)

        stages = {c.stage: c.result for c in result.checks}
        assert stages["red"] == "skipped"
        assert stages["green"] == "skipped"

    @pytest.mark.asyncio
    async def test_red_commit_found(self, tmp_path: Path) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from tapps_mcp.tools.checklist import check_tdd_stages

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "abc1234 test: add failing test for auth\ndef5678 fix: implement auth\n"
        )
        with patch(
            "tapps_mcp.tools.subprocess_runner.run_command_async",
            new=AsyncMock(return_value=mock_result),
        ):
            result = await check_tdd_stages(tmp_path)

        stages = {c.stage: c.result for c in result.checks}
        assert stages["red"] == "passed"
        assert stages["green"] == "passed"

    @pytest.mark.asyncio
    async def test_missing_red_commit_fails(self, tmp_path: Path) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from tapps_mcp.tools.checklist import check_tdd_stages

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc1234 fix: implement auth\n"
        with patch(
            "tapps_mcp.tools.subprocess_runner.run_command_async",
            new=AsyncMock(return_value=mock_result),
        ):
            result = await check_tdd_stages(tmp_path)

        stages = {c.stage: c.result for c in result.checks}
        assert stages["red"] == "failed"
        assert result.passed is False

    def test_coverage_xml_parsed(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.checklist import _check_coverage

        (tmp_path / "coverage.xml").write_text(
            '<?xml version="1.0" ?>\n<coverage line-rate="0.92" branch-rate="0.0"></coverage>\n'
        )
        check = _check_coverage(tmp_path)
        assert check.result == "passed"
        assert "92.0%" in check.message

    def test_coverage_below_threshold_fails(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.checklist import _check_coverage

        (tmp_path / "coverage.xml").write_text(
            '<?xml version="1.0" ?>\n<coverage line-rate="0.55" branch-rate="0.0"></coverage>\n'
        )
        check = _check_coverage(tmp_path)
        assert check.result == "failed"

    def test_no_coverage_file_skipped(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.checklist import _check_coverage

        check = _check_coverage(tmp_path)
        assert check.result == "skipped"

    def test_compile_time_red_flags_syntax_error(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.checklist import _check_compile_time_red

        (tmp_path / "bad.py").write_text("def foo(\n  # unclosed\n")
        check = _check_compile_time_red(tmp_path)
        assert check.result == "failed"
        assert check.stage == "red_state"

    def test_valid_python_passes_compile_check(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.checklist import _check_compile_time_red

        (tmp_path / "good.py").write_text("def foo(): pass\n")
        check = _check_compile_time_red(tmp_path)
        assert check.result == "passed"
