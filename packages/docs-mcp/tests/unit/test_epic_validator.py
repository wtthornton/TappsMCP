"""Tests for the EpicValidator (epic planning document validation)."""

from __future__ import annotations

from pathlib import Path

import pytest

from docs_mcp.validators.epic_validator import (
    EpicValidationReport,
    EpicValidator,
    _check_point_size_consistency,
    _detect_cycle,
    _parse_implementation_order,
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
