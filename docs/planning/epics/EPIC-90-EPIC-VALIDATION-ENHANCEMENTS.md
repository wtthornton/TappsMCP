# Epic 90: Epic Validation & Story Parsing Enhancements

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P2 - Medium
**Estimated LOE:** ~1 week (1 developer)
**Dependencies:** None (builds on existing checklist infrastructure)
**GitHub Issue:** https://github.com/wtthornton/TappsMCP/issues/76

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this because `tapps_checklist` epic validation is too rigid to handle real-world epic formats. The Ralph PLANOPT session (2026-03-24) revealed three gaps: (1) `epic_file_path` requires absolute paths while every other tool resolves relative paths, (2) the story heading regex only matches `### Story X.Y:` and `### X.Y --` inline patterns but not table-linked story references like `| [Story title](file.md) |`, and (3) the validator cannot follow story file links to report cross-file completeness. Fixing these makes epic validation useful for projects that organize stories as separate linked files rather than inline headings.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Make `tapps_checklist` epic validation flexible enough to parse both inline story headings and table-linked story references, resolve file paths reliably, and report completeness across linked story files. The validator should handle any project's epic format without requiring structural changes to the epic document.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

- **Relative path failure:** `tapps_checklist(epic_file_path="docs/specs/epic.md")` failed with `[Errno 2] No such file or directory` because `evaluate_epic()` in `checklist.py` (line 722) calls `Path(file_path).read_text()` without resolving against `project_root` or cwd. Every other tool resolves relative paths.
- **Table-linked stories invisible:** The `_STORY_HEADING_RE` regex (line 802) matches `### Story X.Y:` and `### X.Y --` but not table-based references like `| PLANOPT-1 | [File dependency graph](story-file.md) |`. The validator reported "No stories found" for an epic with 5 well-defined stories linked via table rows.
- **Note on linked headings:** TappsMCP's own epics use `### [88.1](EPIC-88/story-88.1-slug.md) -- Title` format which also does not match the current regex (the `[` bracket before the number prevents the `\d+\.\d+` capture). This is an additional gap beyond the table format.
- **No cross-file validation:** When stories are in separate files, the validator only knows they exist (via link text) but cannot check whether the linked files contain acceptance criteria, tasks, or definitions of done. This limits the validator to "stories found: yes/no" without deeper quality checks.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] `epic_file_path` accepts relative paths resolved against `project_root` (from settings or parameter)
- [ ] `_STORY_HEADING_RE` matches linked heading format `### [X.Y](path) -- Title`
- [ ] Table-linked story references are parsed: `| ID | [Title](file.md) | ... |`
- [ ] Linked story files are optionally read and validated for structural completeness
- [ ] Response includes cross-file completeness summary (e.g., `"5/5 stories found, 3/5 have acceptance criteria"`)
- [ ] All existing tests pass; new tests cover each new format
- [ ] `mypy --strict` passes on all changed files
- [ ] `ruff check` and `ruff format --check` pass on all changed files

<!-- docsmcp:end:acceptance-criteria -->

---

<!-- docsmcp:start:stories -->
## Stories

### [90.1](EPIC-90/story-90.1-epic-file-path-relative-resolution.md) -- Resolve epic_file_path relative to project_root

**Points:** 2

`CallTracker.evaluate_epic()` (line 722 of `checklist.py`) calls `Path(file_path).read_text()` directly. When a relative path is provided (e.g., `docs/specs/epic.md`), it resolves against the process cwd (the MCP server's directory), not the target project. Add path resolution against `project_root`.

**Tasks:**
- [ ] In `evaluate_epic()`, resolve `file_path` against `project_root` when the path is relative
- [ ] Accept `project_root` from the `eval_kwargs` passed through from the MCP handler (already passed at line 1244 in `server.py`)
- [ ] Fall back to `Path.cwd()` if `project_root` is not available
- [ ] Add error message that includes the resolved path for better diagnostics
- [ ] Add tests: relative path with project_root, relative path without project_root, absolute path unchanged
- [ ] Verify existing tests still pass

**Definition of Done:** `tapps_checklist(epic_file_path="docs/specs/epic.md")` resolves the path against project_root and reads the file successfully.

---

### [90.2](EPIC-90/story-90.2-table-linked-story-parsing.md) -- Parse table-linked and bracket-linked story references

**Points:** 5

The `_STORY_HEADING_RE` regex (line 802) only matches two inline formats:
- `### Story X.Y: Title`
- `### X.Y -- Title`

It does NOT match:
- **Linked headings:** `### [88.1](path/to/story.md) -- Title` (used by TappsMCP's own epics)
- **Table rows:** `| PLANOPT-1 | [Title](story-file.md) | Size | Priority |` (used by ralph-claude-code)

Both formats are common in real projects. Add parsers for both.

**Tasks:**
- [ ] Update `_STORY_HEADING_RE` to also match `### [X.Y](path) -- Title` format (capture group for path)
- [ ] Add `_TABLE_STORY_RE` regex to match `| ID | [Title](file.md) | ... |` table row format
- [ ] Update `_parse_epic_markdown()` to try both heading regex and table regex
- [ ] For table stories, extract: story ID, title, linked file path, size/priority from table columns
- [ ] Create `EpicStoryInfo` entries from table matches with `linked_file` field
- [ ] Add `linked_file: str | None = None` field to `EpicStoryInfo` model
- [ ] Add tests: linked heading format, table format, mixed formats, table with missing columns
- [ ] Test against TappsMCP's own Epic 88 format (linked headings)
- [ ] Test against Ralph PLANOPT format (table rows with links)

**Definition of Done:** Both `### [X.Y](path) -- Title` and `| ID | [Title](file.md) | ... |` are parsed as stories with correct metadata extraction.

---

### [90.3](EPIC-90/story-90.3-cross-file-story-validation.md) -- Cross-file story completeness reporting

**Points:** 5

When stories are in separate files (linked via heading or table), the validator currently only knows they exist from the link text. It cannot verify whether the linked file contains acceptance criteria, tasks, or a definition of done. Add optional cross-file validation that reads linked story files and reports per-story structural completeness.

**Tasks:**
- [ ] When `EpicStoryInfo.linked_file` is set, resolve the path relative to the epic file's directory
- [ ] Read linked story file content (handle missing files gracefully with a finding)
- [ ] Apply story-level structural validation to linked file content (check for AC, tasks, DoD sections)
- [ ] Update `EpicStoryInfo` with validation results from linked file
- [ ] Add `cross_file_summary` to `EpicValidation` response: `"5/5 stories found, 3/5 have AC, 4/5 have tasks"`
- [ ] Add `validate_linked_stories: bool = True` parameter to control cross-file validation (default on)
- [ ] Handle circular references and self-links gracefully
- [ ] Add tests: all stories have AC, some missing, linked file not found, deeply nested story paths
- [ ] Add test with TappsMCP's EPIC-88 structure (separate story files in subdirectory)

**Definition of Done:** Epic validation follows story file links and reports per-story structural completeness with an aggregate summary.

<!-- docsmcp:end:stories -->

---

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- **Path resolution pattern:** Story 90.1 should follow the same pattern as other tools. `project_root` is already passed in `eval_kwargs` (line 1244 of `server.py`), but `evaluate_epic()` ignores it. Thread it through to `Path(file_path)` resolution.
- **Regex backward compatibility:** The existing `_STORY_HEADING_RE` must continue to match current formats. Add new patterns alongside, not replacing. Use `|` alternation or a separate regex.
- **Table parsing complexity:** Markdown tables vary widely. Use a focused regex for the `| ID | [Title](link) |` pattern rather than a full markdown table parser. Column order may vary between projects.
- **Linked heading regex:** `### \[(\d+\.\d+)\]\(([^)]+)\)\s*[:\u2014-]+\s*(.*)` captures: story ID, file path, title.
- **Cross-file resolution:** Story files linked as `story-89.1-slug.md` should resolve relative to the epic file's parent directory, not `project_root`. This matches how markdown relative links work.
- **Performance:** Cross-file validation reads additional files. For epics with 20+ stories in separate files, this could add latency. The `validate_linked_stories` parameter lets callers opt out.

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- **Story file generation** -- Creating story files from epic tables is a docs-mcp concern, not a validation concern.
- **Full markdown table parsing** -- Supporting arbitrary table formats beyond `| ID | [Title](link) |` is complexity without clear demand.
- **Story dependency graph** -- Parsing `depends_on` fields in story files and building a dependency DAG is useful but separate from structural validation.
- **Auto-fix for story format** -- Automatically converting between inline and table formats is a generation feature, not validation.

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Story detection for table-linked epics | 0 stories found | All stories found | Test with Ralph PLANOPT epic format |
| Story detection for linked-heading epics | 0 stories found (bracket format) | All stories found | Test with TappsMCP Epic 88 format |
| Epic file_path usability | Absolute path required | Relative paths work | Test with relative path |
| Cross-file completeness reporting | Not available | Summary in response | Verify summary string in output |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. **Story 90.1** -- Relative path resolution (foundation, unblocks testing of other stories)
2. **Story 90.2** -- Table-linked and bracket-linked story parsing (core value)
3. **Story 90.3** -- Cross-file completeness (builds on 90.2's linked_file data)

Stories must be implemented sequentially: 90.1 enables reliable file reading, 90.2 provides the linked file paths, 90.3 uses those paths for cross-file validation.

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Table regex too rigid for edge cases | Medium | Medium | Test against 3+ real epic formats; provide fallback to "unknown format" |
| Cross-file validation slow for large epics | Low | Low | `validate_linked_stories` parameter allows opt-out; typical epics have <10 stories |
| Linked file paths break on Windows vs Unix | Medium | Medium | Use `pathlib.Path` for all resolution; test on Windows paths |
| Regex changes break existing story parsing | Low | High | Keep existing regex intact; add new patterns alongside with tests |

<!-- docsmcp:end:risk-assessment -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Story | Action |
|---|---|---|
| `packages/tapps-mcp/src/tapps_mcp/tools/checklist.py` | 90.1, 90.2, 90.3 | Update -- path resolution, new regexes, cross-file validation |
| `packages/tapps-mcp/src/tapps_mcp/server.py` | 90.1 | Update -- thread project_root to evaluate_epic if needed |
| `packages/tapps-mcp/tests/unit/test_checklist.py` | 90.1, 90.2, 90.3 | Update -- new tests for all formats |
| `packages/tapps-mcp/tests/unit/test_epic_validation.py` | 90.2, 90.3 | New -- dedicated epic validation test suite |

<!-- docsmcp:end:files-affected -->
