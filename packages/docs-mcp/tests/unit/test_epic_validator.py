"""Tests for the EpicValidator (epic planning document validation)."""

from __future__ import annotations

from pathlib import Path

import pytest

from docs_mcp.validators.epic_validator import (
    CrossFileSummary,
    EpicValidationReport,
    EpicValidator,
    _check_point_size_consistency,
    _check_story_file_structure,
    _detect_cycle,
    _parse_implementation_order,
    _parse_story_heading,
    _parse_table_size_priority,
    _split_by_heading,
    StoryInfo,
)

# ---------------------------------------------------------------------------
# Fixtures — inline markdown strings
# ---------------------------------------------------------------------------

_WELL_FORMED_EPIC = """\
# Epic 99: Example Feature

## Goal

Deliver a well-structured feature with clear stories.

## Motivation

We need this feature to validate the epic validator itself.

## Acceptance Criteria

- [ ] All stories are complete
- [ ] Tests pass
- [ ] Documentation updated

## Stories

### Story 99.1: First Story

> **As a** developer, **I want** to do the first thing.

**Points:** 2 | **Size:** S | **Priority:** P1

**Files:**
- `src/foo.py`
- `tests/test_foo.py`

#### Tasks

- [ ] Implement foo
- [ ] Write tests

#### Acceptance Criteria

- [ ] Foo works
- [ ] Tests pass

---

### Story 99.2: Second Story

> **As a** developer, **I want** to do the second thing.

**Points:** 5 | **Size:** M | **Priority:** P2

**Files:**
- `src/bar.py`

#### Tasks

- [ ] Implement bar

#### Acceptance Criteria

- [ ] Bar works
- [ ] Integration tested
"""

_MISSING_GOAL_EPIC = """\
# Epic 100: No Goal

## Motivation

Some motivation here.

## Acceptance Criteria

- [ ] Something

## Stories

### Story 100.1: Only Story

**Points:** 1 | **Size:** S | **Priority:** P1

#### Acceptance Criteria

- [ ] Done
"""

_NO_AC_STORY_EPIC = """\
# Epic 101: Story Without AC

## Goal

Test missing acceptance criteria.

## Motivation

We need to catch this.

## Acceptance Criteria

- [ ] Validator catches missing AC

## Stories

### Story 101.1: Bad Story

**Points:** 3 | **Size:** M | **Priority:** P2

#### Tasks

- [ ] Do something
"""

_POINT_SIZE_MISMATCH_EPIC = """\
# Epic 102: Mismatch

## Goal

Test point/size mismatch detection.

## Motivation

Consistency matters.

## Acceptance Criteria

- [ ] Mismatch detected

## Stories

### Story 102.1: Mismatched Story

**Points:** 13 | **Size:** S | **Priority:** P1

#### Acceptance Criteria

- [ ] Done
"""

_EPIC_WITH_IMPL_ORDER = """\
# Epic 103: With Implementation Order

## Goal

Test implementation order parsing.

## Motivation

Order matters.

## Acceptance Criteria

- [ ] Order validated

## Stories

### Story 103.1: First

**Points:** 2 | **Size:** S | **Priority:** P1

#### Acceptance Criteria

- [ ] Done

### Story 103.2: Second

**Points:** 3 | **Size:** M | **Priority:** P2

#### Acceptance Criteria

- [ ] Done

### Story 103.3: Third

**Points:** 5 | **Size:** M | **Priority:** P2

#### Acceptance Criteria

- [ ] Done

## Implementation Order

- Story 103.2 depends on Story 103.1
- Story 103.3 depends on Story 103.2
"""

_EPIC_WITH_CYCLE = """\
# Epic 104: Dependency Cycle

## Goal

Test cycle detection.

## Motivation

Cycles are bad.

## Acceptance Criteria

- [ ] Cycle detected

## Stories

### Story 104.1: A

**Points:** 2 | **Size:** S | **Priority:** P1

#### Acceptance Criteria

- [ ] Done

### Story 104.2: B

**Points:** 2 | **Size:** S | **Priority:** P1

#### Acceptance Criteria

- [ ] Done

## Implementation Order

- Story 104.1 depends on Story 104.2
- Story 104.2 depends on Story 104.1
"""

_MINIMAL_EPIC = """\
# Epic 105: Minimal

## Goal

Minimal epic.

## Motivation

Keep it simple.

## Acceptance Criteria

- [ ] Done

## Stories
"""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _write_epic(tmp_path: Path, content: str, name: str = "EPIC.md") -> Path:
    """Write epic content to a temp file and return the path."""
    fp = tmp_path / name
    fp.write_text(content, encoding="utf-8")
    return fp


# ---------------------------------------------------------------------------
# Tests — EpicValidator.validate()
# ---------------------------------------------------------------------------


class TestEpicValidatorWellFormed:
    """Tests for a well-formed epic document."""

    def test_score_100(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, _WELL_FORMED_EPIC)
        report = EpicValidator().validate(fp)

        assert report.score == 100
        assert report.passed is True
        assert report.total_stories == 2
        assert len(report.stories) == 2
        assert report.epic_title == "Epic 99: Example Feature"

    def test_stories_extracted(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, _WELL_FORMED_EPIC)
        report = EpicValidator().validate(fp)

        s1 = report.stories[0]
        assert s1.number == "99.1"
        assert s1.title == "First Story"
        assert s1.points == 2
        assert s1.size == "S"
        assert s1.priority == "P1"
        assert s1.has_acceptance_criteria is True
        assert s1.has_tasks is True
        assert s1.has_files is True
        assert s1.ac_count == 2
        assert s1.task_count == 2

        s2 = report.stories[1]
        assert s2.number == "99.2"
        assert s2.points == 5
        assert s2.size == "M"

    def test_no_errors(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, _WELL_FORMED_EPIC)
        report = EpicValidator().validate(fp)

        errors = [i for i in report.issues if i.severity == "error"]
        assert len(errors) == 0


class TestEpicValidatorMissingSections:
    """Tests for missing required sections."""

    def test_missing_goal(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, _MISSING_GOAL_EPIC)
        report = EpicValidator().validate(fp)

        errors = [i for i in report.issues if i.severity == "error"]
        goal_errors = [e for e in errors if "Goal" in e.message]
        assert len(goal_errors) == 1

    def test_score_deducted_for_missing_section(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, _MISSING_GOAL_EPIC)
        report = EpicValidator().validate(fp)

        assert report.score < 100


class TestEpicValidatorStoryCompleteness:
    """Tests for story completeness checks."""

    def test_missing_ac_is_error(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, _NO_AC_STORY_EPIC)
        report = EpicValidator().validate(fp)

        errors = [i for i in report.issues if i.severity == "error"]
        ac_errors = [e for e in errors if "acceptance criteria" in e.message.lower()]
        assert len(ac_errors) == 1
        assert ac_errors[0].location == "Story 101.1"

    def test_story_without_files_is_info(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, _NO_AC_STORY_EPIC)
        report = EpicValidator().validate(fp)

        infos = [i for i in report.issues if i.severity == "info"]
        file_infos = [i for i in infos if "files" in i.message.lower()]
        assert len(file_infos) == 1


class TestEpicValidatorPointSizeConsistency:
    """Tests for point/size mismatch warnings."""

    def test_mismatch_is_warning(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, _POINT_SIZE_MISMATCH_EPIC)
        report = EpicValidator().validate(fp)

        warnings = [i for i in report.issues if i.severity == "warning"]
        mismatch_warnings = [
            w for w in warnings if "inconsistent" in w.message.lower()
        ]
        assert len(mismatch_warnings) == 1
        assert "13" in mismatch_warnings[0].message
        assert "S" in mismatch_warnings[0].message

    def test_mismatch_deducts_5_points(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, _POINT_SIZE_MISMATCH_EPIC)
        report = EpicValidator().validate(fp)

        # Score should be less than 100 due to the warning
        # But also no files listed (info, no deduction) and the warning (-5)
        assert report.score <= 95


class TestEpicValidatorImplOrder:
    """Tests for implementation order validation."""

    def test_valid_order_no_issues(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, _EPIC_WITH_IMPL_ORDER)
        report = EpicValidator().validate(fp)

        cycle_errors = [
            i for i in report.issues if "cycle" in i.message.lower()
        ]
        assert len(cycle_errors) == 0

    def test_cycle_detected(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, _EPIC_WITH_CYCLE)
        report = EpicValidator().validate(fp)

        cycle_errors = [
            i for i in report.issues if "cycle" in i.message.lower()
        ]
        assert len(cycle_errors) == 1
        assert cycle_errors[0].severity == "error"


_DOCSMCP_STUB_EPIC = """\
# Epic 80: Consumer Init

## Goal

Close bootstrap gaps.

## Motivation

Adoption.

## Acceptance Criteria

- [ ] Done

## Stories

### 80.1 -- Fix hooks

**Points:** 2 | **Size:** S | **Priority:** P1

#### Tasks

- [ ] Implement

#### Acceptance Criteria

- [ ] Scripts exist

---
"""


class TestEpicValidatorDocsMcpStoryHeadings:
    """docs_generate_epic uses ### N -- Title; validator must recognize it."""

    def test_parse_story_heading_docsmcp_format(self) -> None:
        assert _parse_story_heading("### 80.1 -- Fix hooks") == ("80.1", "Fix hooks")
        assert _parse_story_heading("### Story 99.1: Classic") == ("99.1", "Classic")

    def test_validator_counts_docsmcp_style_stories(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, _DOCSMCP_STUB_EPIC)
        report = EpicValidator().validate(fp)

        assert report.total_stories == 1
        assert report.stories[0].number == "80.1"
        assert "hooks" in report.stories[0].title.lower()


class TestEpicValidatorEdgeCases:
    """Tests for edge cases."""

    def test_empty_file(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, "")
        report = EpicValidator().validate(fp)

        assert report.score == 0
        assert report.passed is False
        assert len(report.issues) > 0

    def test_whitespace_only_file(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, "   \n\n   \n")
        report = EpicValidator().validate(fp)

        assert report.score == 0
        assert report.passed is False

    def test_file_not_found(self, tmp_path: Path) -> None:
        fp = tmp_path / "nonexistent.md"
        report = EpicValidator().validate(fp)

        assert report.score == 0
        assert report.passed is False
        assert any("does not exist" in i.message for i in report.issues)

    def test_minimal_epic_no_stories(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, _MINIMAL_EPIC)
        report = EpicValidator().validate(fp)

        assert report.total_stories == 0
        assert report.score == 100  # No stories = no story issues
        assert report.passed is True

    def test_report_is_pydantic_model(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, _WELL_FORMED_EPIC)
        report = EpicValidator().validate(fp)

        assert isinstance(report, EpicValidationReport)
        data = report.model_dump()
        assert "file_path" in data
        assert "stories" in data
        assert "issues" in data
        assert "score" in data


# ---------------------------------------------------------------------------
# Tests — helper functions
# ---------------------------------------------------------------------------


class TestPointSizeConsistency:
    """Tests for _check_point_size_consistency."""

    def test_s_2pts_ok(self) -> None:
        story = StoryInfo(number="1.1", title="X", points=2, size="S")
        assert _check_point_size_consistency(story) is None

    def test_s_1pt_ok(self) -> None:
        story = StoryInfo(number="1.1", title="X", points=1, size="S")
        assert _check_point_size_consistency(story) is None

    def test_s_5pts_mismatch(self) -> None:
        story = StoryInfo(number="1.1", title="X", points=5, size="S")
        issue = _check_point_size_consistency(story)
        assert issue is not None
        assert issue.severity == "warning"

    def test_m_3pts_ok(self) -> None:
        story = StoryInfo(number="1.1", title="X", points=3, size="M")
        assert _check_point_size_consistency(story) is None

    def test_l_8pts_ok(self) -> None:
        story = StoryInfo(number="1.1", title="X", points=8, size="L")
        assert _check_point_size_consistency(story) is None

    def test_none_points_skip(self) -> None:
        story = StoryInfo(number="1.1", title="X", points=None, size="S")
        assert _check_point_size_consistency(story) is None

    def test_none_size_skip(self) -> None:
        story = StoryInfo(number="1.1", title="X", points=2, size=None)
        assert _check_point_size_consistency(story) is None


class TestSplitByHeading:
    """Tests for _split_by_heading."""

    def test_split_h2(self) -> None:
        lines = [
            "# Title",
            "",
            "## Section A",
            "content a",
            "",
            "## Section B",
            "content b",
        ]
        sections = _split_by_heading(lines, 2)
        assert len(sections) >= 2
        headings = [name for name, _ in sections if name]
        assert "Section A" in headings
        assert "Section B" in headings

    def test_no_headings(self) -> None:
        lines = ["just some text", "more text"]
        sections = _split_by_heading(lines, 2)
        assert len(sections) == 1
        assert sections[0][0] == ""


class TestImplOrderParsing:
    """Tests for _parse_implementation_order."""

    def test_depends_on(self) -> None:
        lines = ["- Story 1.2 depends on Story 1.1"]
        edges = _parse_implementation_order(lines)
        assert len(edges) == 1
        assert edges[0][0] == "1.2"
        assert "1.1" in edges[0][1]

    def test_arrow_notation(self) -> None:
        lines = ["- 2.1 -> 1.1"]
        edges = _parse_implementation_order(lines)
        assert len(edges) == 1

    def test_no_deps(self) -> None:
        lines = ["- Story 1.1: Do something"]
        edges = _parse_implementation_order(lines)
        assert len(edges) == 0


class TestCycleDetection:
    """Tests for _detect_cycle."""

    def test_no_cycle(self) -> None:
        edges = [("1.2", ["1.1"]), ("1.3", ["1.2"])]
        assert _detect_cycle(edges) is None

    def test_simple_cycle(self) -> None:
        edges = [("1.1", ["1.2"]), ("1.2", ["1.1"])]
        cycle = _detect_cycle(edges)
        assert cycle is not None
        assert len(cycle) >= 2

    def test_empty_edges(self) -> None:
        assert _detect_cycle([]) is None


# ---------------------------------------------------------------------------
# Tests — MCP tool registration
# ---------------------------------------------------------------------------


class TestDocsValidateEpicTool:
    """Tests for the docs_validate_epic MCP tool handler."""

    @pytest.mark.asyncio
    async def test_missing_file_path(self) -> None:
        from docs_mcp.server_val_tools import docs_validate_epic

        result = await docs_validate_epic(file_path="", project_root="")
        assert result["success"] is False
        assert result["error"]["code"] == "MISSING_FILE"

    @pytest.mark.asyncio
    async def test_file_not_found(self, tmp_path: Path) -> None:
        from docs_mcp.server_val_tools import docs_validate_epic

        fp = str(tmp_path / "nonexistent.md")
        result = await docs_validate_epic(file_path=fp, project_root=str(tmp_path))
        assert result["success"] is False
        assert result["error"]["code"] == "FILE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_valid_epic(self, tmp_path: Path) -> None:
        from docs_mcp.server_val_tools import docs_validate_epic

        fp = _write_epic(tmp_path, _WELL_FORMED_EPIC)
        result = await docs_validate_epic(
            file_path=str(fp), project_root=str(tmp_path)
        )
        assert result["success"] is True
        assert result["data"]["score"] == 100
        assert result["data"]["total_stories"] == 2

    @pytest.mark.asyncio
    async def test_relative_path(self, tmp_path: Path) -> None:
        from docs_mcp.server_val_tools import docs_validate_epic

        _write_epic(tmp_path, _WELL_FORMED_EPIC, name="EPIC.md")
        result = await docs_validate_epic(
            file_path="EPIC.md", project_root=str(tmp_path)
        )
        assert result["success"] is True
        assert result["data"]["score"] == 100


# ---------------------------------------------------------------------------
# Fixtures — linked headings and table-linked stories (Story 90.2)
# ---------------------------------------------------------------------------

_LINKED_HEADING_EPIC = """\
# Epic 88: Freshness & Response Size

## Goal

Manage staleness and response sizes.

## Motivation

Performance.

## Acceptance Criteria

- [ ] All stories complete

## Stories

### [88.1](EPIC-88/story-88.1-staleness-first-sort.md) -- Staleness-First Sort

**Points:** 3 | **Size:** M | **Priority:** P1

#### Tasks

- [ ] Implement sort

#### Acceptance Criteria

- [ ] Stale items sorted first

---

### [88.2](EPIC-88/story-88.2-response-truncation.md) -- Response Truncation

**Points:** 5 | **Size:** M | **Priority:** P2

#### Tasks

- [ ] Implement truncation

#### Acceptance Criteria

- [ ] Large responses truncated
"""

_TABLE_STORY_EPIC = """\
# Epic: Plan Optimization

## Goal

Faster planning.

## Motivation

Speed.

## Acceptance Criteria

- [ ] All stories done

## Stories

| ID | Story | Size | Priority |
|---|---|---|---|
| PLANOPT-1 | [File dependency graph](story-planopt-1-file-dependency-graph.md) | M | P1 |
| PLANOPT-2 | [Parallel execution](story-planopt-2-parallel-execution.md) | L | P2 |
| PLANOPT-3 | [Cache invalidation](story-planopt-3-cache-invalidation.md) | S | P1 |
"""

_TABLE_STORY_MISSING_COLS_EPIC = """\
# Epic: Minimal Table

## Goal

Test.

## Motivation

Test.

## Acceptance Criteria

- [ ] Done

## Stories

| ID | Story |
|---|---|
| T-1 | [First task](story-t1.md) |
| T-2 | [Second task](story-t2.md) |
"""

_TABLE_PLAIN_TEXT_EPIC = """\
# Epic: Plain Table

## Goal

Test.

## Motivation

Test.

## Acceptance Criteria

- [ ] Done

## Stories

| ID | Story | Size |
|---|---|---|
| PT-1 | No link here | M |
| PT-2 | [Linked story](story-pt2.md) | L |
"""

_MIXED_HEADING_EPIC = """\
# Epic 90: Mixed Formats

## Goal

Test mixed heading and inline stories.

## Motivation

Coverage.

## Acceptance Criteria

- [ ] Done

## Stories

### Story 90.1: Inline Story

**Points:** 2 | **Size:** S | **Priority:** P1

#### Acceptance Criteria

- [ ] Works

### [90.2](EPIC-90/story-90.2.md) -- Linked Story

**Points:** 3 | **Size:** M | **Priority:** P2

#### Acceptance Criteria

- [ ] Works
"""


# ---------------------------------------------------------------------------
# Tests — linked heading and table-linked story parsing (Story 90.2)
# ---------------------------------------------------------------------------


class TestLinkedHeadingParsing:
    """Tests for ### [X.Y](path) -- Title format."""

    def test_parse_linked_heading(self) -> None:
        result = _parse_story_heading(
            "### [88.1](EPIC-88/story-88.1-staleness-first-sort.md) -- Staleness-First Sort"
        )
        assert result is not None
        assert len(result) == 3
        assert result[0] == "88.1"
        assert result[1] == "Staleness-First Sort"
        assert result[2] == "EPIC-88/story-88.1-staleness-first-sort.md"

    def test_linked_heading_epic_validates(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, _LINKED_HEADING_EPIC)
        report = EpicValidator().validate(fp)

        assert report.total_stories == 2
        assert report.stories[0].number == "88.1"
        assert report.stories[0].linked_file == "EPIC-88/story-88.1-staleness-first-sort.md"
        assert report.stories[1].number == "88.2"
        assert report.stories[1].linked_file == "EPIC-88/story-88.2-response-truncation.md"

    def test_linked_heading_metadata_extracted(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, _LINKED_HEADING_EPIC)
        report = EpicValidator().validate(fp)

        s1 = report.stories[0]
        assert s1.points == 3
        assert s1.size == "M"
        assert s1.priority == "P1"
        assert s1.has_acceptance_criteria is True
        assert s1.has_tasks is True

    def test_classic_heading_still_works(self) -> None:
        assert _parse_story_heading("### Story 99.1: Classic") == ("99.1", "Classic")

    def test_docsmcp_heading_still_works(self) -> None:
        assert _parse_story_heading("### 80.1 -- Fix hooks") == ("80.1", "Fix hooks")


class TestTableLinkedStoryParsing:
    """Tests for table-linked story rows."""

    def test_table_story_epic_validates(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, _TABLE_STORY_EPIC)
        report = EpicValidator().validate(fp)

        assert report.total_stories == 3
        assert report.stories[0].number == "PLANOPT-1"
        assert report.stories[0].title == "File dependency graph"
        assert report.stories[0].linked_file == "story-planopt-1-file-dependency-graph.md"

    def test_table_size_priority_extracted(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, _TABLE_STORY_EPIC)
        report = EpicValidator().validate(fp)

        assert report.stories[0].size == "M"
        assert report.stories[0].priority == "P1"
        assert report.stories[1].size == "L"
        assert report.stories[1].priority == "P2"
        assert report.stories[2].size == "S"

    def test_table_missing_columns(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, _TABLE_STORY_MISSING_COLS_EPIC)
        report = EpicValidator().validate(fp)

        assert report.total_stories == 2
        assert report.stories[0].number == "T-1"
        assert report.stories[0].linked_file == "story-t1.md"
        assert report.stories[0].size is None
        assert report.stories[0].priority is None

    def test_table_plain_text_not_matched(self, tmp_path: Path) -> None:
        """Table rows without markdown links should not be matched."""
        fp = _write_epic(tmp_path, _TABLE_PLAIN_TEXT_EPIC)
        report = EpicValidator().validate(fp)

        # Only PT-2 has a link, PT-1 is plain text
        assert report.total_stories == 1
        assert report.stories[0].number == "PT-2"

    def test_parse_table_size_priority_helper(self) -> None:
        size, prio = _parse_table_size_priority(" M | P1 |")
        assert size == "M"
        assert prio == "P1"

        size, prio = _parse_table_size_priority(" Critical |")
        assert size is None
        assert prio is None

        size, prio = _parse_table_size_priority("")
        assert size is None
        assert prio is None


class TestMixedFormats:
    """Tests for epics with mixed inline and linked headings."""

    def test_mixed_heading_epic(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, _MIXED_HEADING_EPIC)
        report = EpicValidator().validate(fp)

        assert report.total_stories == 2
        numbers = {s.number for s in report.stories}
        assert "90.1" in numbers
        assert "90.2" in numbers

    def test_mixed_inline_has_no_linked_file(self, tmp_path: Path) -> None:
        fp = _write_epic(tmp_path, _MIXED_HEADING_EPIC)
        report = EpicValidator().validate(fp)

        inline = next(s for s in report.stories if s.number == "90.1")
        linked = next(s for s in report.stories if s.number == "90.2")
        assert inline.linked_file is None
        assert linked.linked_file == "EPIC-90/story-90.2.md"


# ---------------------------------------------------------------------------
# Tests — cross-file story validation (Story 90.3)
# ---------------------------------------------------------------------------

_CROSS_FILE_EPIC = """\
# Epic 93: Cross-File Test

## Goal

Test cross-file story validation.

## Motivation

We need linked story files to be validated.

## Acceptance Criteria

- [ ] All linked files validated

## Stories

### [93.1](stories/story-93.1.md) -- Full Story

**Points:** 3 | **Size:** M | **Priority:** P1

### [93.2](stories/story-93.2.md) -- Partial Story

**Points:** 2 | **Size:** S | **Priority:** P2

### [93.3](stories/story-93.3-missing.md) -- Missing Story

**Points:** 1 | **Size:** S | **Priority:** P3
"""

_FULL_STORY_FILE = """\
# Story 93.1: Full Story

## Acceptance Criteria

- [ ] Works correctly
- [ ] Tests pass

## Tasks

- [ ] Implement feature
- [ ] Write tests

## Definition of Done

All tests passing, code reviewed.

**Points:** 5 | **Size:** M
"""

_PARTIAL_STORY_FILE = """\
# Story 93.2: Partial Story

## Tasks

- [ ] Do the thing

No AC or DoD sections here.
"""


def _setup_cross_file_epic(tmp_path: Path) -> Path:
    """Create an epic with linked story files for testing."""
    epic_dir = tmp_path / "epics"
    epic_dir.mkdir()
    stories_dir = epic_dir / "stories"
    stories_dir.mkdir()

    epic_path = epic_dir / "EPIC-93.md"
    epic_path.write_text(_CROSS_FILE_EPIC, encoding="utf-8")

    (stories_dir / "story-93.1.md").write_text(_FULL_STORY_FILE, encoding="utf-8")
    (stories_dir / "story-93.2.md").write_text(_PARTIAL_STORY_FILE, encoding="utf-8")
    # story-93.3-missing.md intentionally not created

    return epic_path


class TestCheckStoryFileStructure:
    """Tests for _check_story_file_structure helper."""

    def test_full_structure(self) -> None:
        has_ac, has_tasks, has_dod, points, size = _check_story_file_structure(
            _FULL_STORY_FILE
        )
        assert has_ac is True
        assert has_tasks is True
        assert has_dod is True
        assert points == 5
        assert size == "M"

    def test_partial_structure(self) -> None:
        has_ac, has_tasks, has_dod, points, size = _check_story_file_structure(
            _PARTIAL_STORY_FILE
        )
        assert has_ac is False
        assert has_tasks is True
        assert has_dod is False
        assert points is None
        assert size is None

    def test_bold_section_names(self) -> None:
        content = "**Acceptance Criteria:**\n- works\n\n**Tasks:**\n- do it"
        has_ac, has_tasks, has_dod, _, _ = _check_story_file_structure(content)
        assert has_ac is True
        assert has_tasks is True
        assert has_dod is False


class TestCrossFileStoryValidation:
    """Tests for cross-file story validation (Story 90.3)."""

    def test_all_files_present_full_structure(self, tmp_path: Path) -> None:
        """When all story files exist and have full structure."""
        epic_dir = tmp_path / "epics"
        epic_dir.mkdir()
        stories_dir = epic_dir / "stories"
        stories_dir.mkdir()

        epic_content = """\
# Epic 94: All Present

## Goal
Test.

## Motivation
Test.

## Acceptance Criteria
- [ ] Done

## Stories

### [94.1](stories/s1.md) -- Story One

### [94.2](stories/s2.md) -- Story Two
"""
        full_story = """\
## Acceptance Criteria
- [ ] Works

## Tasks
- [ ] Do it

## Definition of Done
Done when tests pass.

**Points:** 3 | **Size:** M
"""
        fp = epic_dir / "EPIC-94.md"
        fp.write_text(epic_content, encoding="utf-8")
        (stories_dir / "s1.md").write_text(full_story, encoding="utf-8")
        (stories_dir / "s2.md").write_text(full_story, encoding="utf-8")

        report = EpicValidator().validate(fp)
        assert report.cross_file_summary is not None
        summary = report.cross_file_summary
        assert summary.total_stories == 2
        assert summary.files_found == 2
        assert summary.files_missing == 0
        assert summary.with_acceptance_criteria == 2
        assert summary.with_tasks == 2
        assert summary.with_definition_of_done == 2

    def test_some_files_missing(self, tmp_path: Path) -> None:
        """Missing linked files produce warning findings."""
        fp = _setup_cross_file_epic(tmp_path)
        report = EpicValidator().validate(fp)

        assert report.cross_file_summary is not None
        summary = report.cross_file_summary
        assert summary.total_stories == 3
        assert summary.files_found == 2
        assert summary.files_missing == 1

        # Check warning finding for missing file
        missing_findings = [
            i for i in report.issues
            if "not found" in i.message and "93.3" in i.message
        ]
        assert len(missing_findings) == 1
        assert missing_findings[0].severity == "warning"

    def test_story_files_without_ac(self, tmp_path: Path) -> None:
        """Story files without AC section produce info findings."""
        fp = _setup_cross_file_epic(tmp_path)
        report = EpicValidator().validate(fp)

        # Story 93.2 has no AC section
        ac_findings = [
            i for i in report.issues
            if "Acceptance Criteria" in i.message and "93.2" in i.location
        ]
        assert len(ac_findings) >= 1

    def test_linked_file_merges_metadata(self, tmp_path: Path) -> None:
        """Linked file metadata merges into story info."""
        fp = _setup_cross_file_epic(tmp_path)
        report = EpicValidator().validate(fp)

        s1 = next(s for s in report.stories if s.number == "93.1")
        # Full story file has AC and tasks
        assert s1.has_acceptance_criteria is True
        assert s1.has_tasks is True
        # Points from inline (3) stays since it was set first
        assert s1.points == 3

    def test_deeply_nested_paths(self, tmp_path: Path) -> None:
        """Story files in deeply nested directories are resolved."""
        epic_dir = tmp_path / "docs" / "epics"
        epic_dir.mkdir(parents=True)
        nested = epic_dir / "deep" / "nested" / "stories"
        nested.mkdir(parents=True)

        epic = """\
# Epic 95: Nested

## Goal
Test.

## Motivation
Test.

## Acceptance Criteria
- [ ] Done

## Stories

### [95.1](deep/nested/stories/s1.md) -- Deep Story
"""
        story = """\
## Acceptance Criteria
- [ ] Works

## Tasks
- [ ] Do it

## Definition of Done
Done.
"""
        fp = epic_dir / "EPIC-95.md"
        fp.write_text(epic, encoding="utf-8")
        (nested / "s1.md").write_text(story, encoding="utf-8")

        report = EpicValidator().validate(fp)
        assert report.cross_file_summary is not None
        assert report.cross_file_summary.files_found == 1
        assert report.cross_file_summary.files_missing == 0

    def test_validate_linked_stories_false_skips(self, tmp_path: Path) -> None:
        """validate_linked_stories=False disables cross-file validation."""
        fp = _setup_cross_file_epic(tmp_path)
        report = EpicValidator().validate(fp, validate_linked_stories=False)
        assert report.cross_file_summary is None

    def test_summary_string_format(self, tmp_path: Path) -> None:
        """Summary string has expected format."""
        fp = _setup_cross_file_epic(tmp_path)
        report = EpicValidator().validate(fp)

        assert report.cross_file_summary is not None
        s = report.cross_file_summary.summary
        assert "3 stories" in s
        assert "2/3 files found" in s
        assert "have AC" in s
        assert "have tasks" in s

    def test_no_linked_files_no_summary(self, tmp_path: Path) -> None:
        """Epic with no linked files produces no cross_file_summary."""
        fp = _write_epic(tmp_path, _WELL_FORMED_EPIC)
        report = EpicValidator().validate(fp)
        assert report.cross_file_summary is None
