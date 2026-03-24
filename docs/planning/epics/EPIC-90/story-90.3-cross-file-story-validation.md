# Story 90.3: Cross-file story completeness reporting

<!-- docsmcp:start:metadata -->
**Epic:** [90 - Epic Validation Enhancements](../EPIC-90-EPIC-VALIDATION-ENHANCEMENTS.md)
**Points:** 5
**Priority:** P3 - Low
**Status:** Proposed
**Depends On:** Story 90.1 (path resolution), Story 90.2 (linked_file extraction)

<!-- docsmcp:end:metadata -->

## User Story

As an agent validating an epic with separate story files, I need the validator to follow story file links and report per-story structural completeness, so that I get a meaningful quality assessment beyond just "stories found: yes/no."

## Description

When stories are defined in separate files (linked via heading or table), the current validator only extracts metadata from the link text (ID, title). It cannot determine whether the linked file actually contains acceptance criteria, tasks, sizing, or a definition of done. This limits the validator's value for projects that organize stories as separate documents.

Add cross-file validation that reads linked story files, checks their structure, and reports aggregate completeness.

## Tasks

- [ ] When `EpicStoryInfo.linked_file` is set, resolve the path relative to the epic file's parent directory
- [ ] Read the linked file content (handle `FileNotFoundError` gracefully with a warning finding)
- [ ] Apply story-level structural validation:
  - Check for acceptance criteria section
  - Check for tasks section (with checkbox items)
  - Check for definition of done section
  - Check for sizing/points
- [ ] Update `EpicStoryInfo` fields from linked file content (merge with any inline metadata)
- [ ] Add `cross_file_summary` to `EpicValidation`:
  ```
  "cross_file_summary": {
    "total_stories": 5,
    "stories_with_files": 5,
    "files_found": 4,
    "files_missing": 1,
    "with_acceptance_criteria": 3,
    "with_tasks": 4,
    "with_definition_of_done": 3,
    "summary": "5 stories, 4/5 files found, 3/5 have AC, 4/5 have tasks"
  }
  ```
- [ ] Add `validate_linked_stories: bool = True` parameter to `validate_epic_markdown()`
- [ ] Add findings for: missing linked files, stories without AC, stories without tasks
- [ ] Handle edge cases: circular links, self-referencing files, deeply nested paths
- [ ] Add tests:
  - All story files present with full structure
  - Some story files missing
  - Story files without AC/tasks sections
  - Deeply nested story file paths
  - Test with TappsMCP EPIC-88 structure (real story files in subdirectory)
  - `validate_linked_stories=False` skips cross-file validation

## Acceptance Criteria

- [ ] Linked story files are read and validated for structural sections
- [ ] `cross_file_summary` provides aggregate completeness metrics
- [ ] Missing linked files produce warning findings (not errors)
- [ ] `validate_linked_stories=False` disables cross-file reading
- [ ] Performance is acceptable for epics with up to 20 story files

## Definition of Done

Epic validation follows story file links, validates their internal structure, and reports a human-readable cross-file completeness summary like "5 stories, 4/5 files found, 3/5 have AC, 4/5 have tasks."

## Technical Notes

- Resolve linked file paths relative to the **epic file's parent directory**, not project_root. This matches markdown relative link semantics.
- Story files may use different section heading conventions (e.g., `## Acceptance Criteria` vs `### AC` vs `**Acceptance Criteria:**`). Reuse or extend the existing `_has_subsection()` helper.
- The `EpicFinding` model already supports severity levels. Use `warning` for missing files (non-blocking) and `info` for structural gaps.
- Consider caching file reads if the same story file is referenced multiple times (unlikely but defensive).
