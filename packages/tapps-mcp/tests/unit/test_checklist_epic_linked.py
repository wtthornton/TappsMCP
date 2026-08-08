"""Tests for tools.checklist_epic — linked-heading and cross-file stories.

Covers the ``### [X.Y](path) -- Title`` and stories-table notations, plus the
cross-file validation that follows a story link to a separate markdown file.
Split from ``test_checklist_epic.py`` (TAP-5733) so neither file carries
enough lines to sink its maintainability index.

Imports through ``tapps_mcp.tools.checklist`` on purpose: that is the
backward-compatible path the re-export block promises.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from tapps_mcp.tools.checklist import validate_epic_markdown


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
