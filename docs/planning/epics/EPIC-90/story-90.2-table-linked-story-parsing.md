# Story 90.2: Parse table-linked and bracket-linked story references

<!-- docsmcp:start:metadata -->
**Epic:** [90 - Epic Validation Enhancements](../EPIC-90-EPIC-VALIDATION-ENHANCEMENTS.md)
**Points:** 5
**Priority:** P2 - Medium
**Status:** Proposed

<!-- docsmcp:end:metadata -->

## User Story

As an agent validating an epic, I need the validator to detect stories defined as table rows with markdown links or as bracket-linked headings, so that epics using these common formats don't report "No stories found."

## Description

The current `_STORY_HEADING_RE` regex (line 802 of `checklist.py`) matches only:
```
### Story X.Y: Title
### X.Y -- Title
```

Two additional formats are used in practice:

**1. Linked headings (TappsMCP's own epics):**
```markdown
### [88.1](EPIC-88/story-88.1-slug.md) -- Staleness-First Sort
```
The `[` bracket before the number prevents the `\d+\.\d+` capture.

**2. Table-linked stories (ralph-claude-code, other projects):**
```markdown
| PLANOPT-1 | [File dependency graph](story-planopt-1-file-dependency-graph.md) | Medium | Critical |
```
No heading at all -- stories are rows in a markdown table.

Both formats should produce `EpicStoryInfo` entries with the linked file path captured.

## Tasks

- [ ] Add `linked_file: str | None = None` field to `EpicStoryInfo` model
- [ ] Update `_STORY_HEADING_RE` to also match `### [X.Y](path) -- Title` via alternation
- [ ] Capture the file path in a named group from linked headings
- [ ] Add `_TABLE_STORY_RE` regex: `\|\s*(\S+)\s*\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|`
- [ ] Update `_parse_epic_markdown()` to:
  1. Try heading regex first (both original and linked formats)
  2. If no stories found via headings, try table regex
  3. Create `EpicStoryInfo` from table matches with ID, title, linked_file
- [ ] Extract size/priority from table columns when present
- [ ] Add tests:
  - Linked heading `### [X.Y](path) -- Title` parsed correctly
  - Table row `| ID | [Title](file.md) | Size | Priority |` parsed correctly
  - Mixed: some inline headings + some table rows
  - Table with missing columns (no size/priority)
  - Table with non-link cells (e.g., plain text title, no link)
  - TappsMCP Epic 88 format validates correctly
  - Ralph PLANOPT table format validates correctly

## Acceptance Criteria

- [ ] Linked headings produce `EpicStoryInfo` with `linked_file` set
- [ ] Table rows produce `EpicStoryInfo` with `linked_file` set
- [ ] Existing inline heading format continues to work unchanged
- [ ] `validate_epic_markdown()` on TappsMCP's own epics finds all stories
- [ ] `validate_epic_markdown()` on Ralph-style table epics finds all stories

## Definition of Done

Both linked-heading and table-linked story formats are parsed into `EpicStoryInfo` entries with file paths captured, enabling cross-file validation in Story 90.3.

## Technical Notes

- **Regex for linked headings:** `^###\s+\[(\d+\.\d+)\]\(([^)]+)\)\s*[:\u2014-]+\s*(.*)`
  - Group 1: story ID (e.g., `88.1`)
  - Group 2: file path (e.g., `EPIC-88/story-88.1-slug.md`)
  - Group 3: title
- **Regex for table rows:** `^\|\s*(\S+)\s*\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|(.*)$`
  - Group 1: story ID (e.g., `PLANOPT-1`)
  - Group 2: title
  - Group 3: file path
  - Group 4: remaining columns (parse for size/priority)
- Table story IDs may not follow `X.Y` numeric format (e.g., `PLANOPT-1`). Support alphanumeric IDs.
- Prefer trying heading regex first since it's more specific. Fall back to table parsing.
