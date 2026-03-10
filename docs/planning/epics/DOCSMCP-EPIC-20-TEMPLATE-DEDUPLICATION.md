# DocsMCP Epic 20 — Template Deduplication & Cross-References

> Status: Complete | Priority: Medium | Package: docs-mcp
> Triggered by: [Epic 12 Review Feedback](../../epic-12-review-feedback.md) (TheStudio)
> Addresses: Review items #3, #4, #10, #11, #12

---

## Goal

Eliminate redundant content repetition across generated epic and story documents. Inherited context (tech stack, project structure, Definition of Done) should appear once in the epic and be referenced — not copy-pasted — in stories. File impact tables in the epic should aggregate real paths from stories. Stories should link back to their epic file.

## Motivation

TheStudio's Epic 12 generation produced 9 documents (1 epic + 8 stories) where every document repeated "Tech Stack: thestudio, Python >=3.12" and "Project Structure: 3 packages, 114 modules, 641 public APIs". The same 6-item Definition of Done appeared identically in all 8 stories plus the epic. The epic's Files Affected table said "*see tasks*" in every row despite stories listing specific file paths. This clutter makes documents harder to scan and increases maintenance burden when project metadata changes.

2026 documentation generation best practices (DRY principle) mandate that generated document sets treat the epic as the single source of truth for shared context, with stories inheriting rather than duplicating.

## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Repeated context lines per story | 3+ lines of project metadata | 0 (inherited from epic) | Count of "Tech Stack:" / "Project Structure:" lines in story output |
| Files Affected specificity | "*see tasks*" in every row | Real file paths aggregated from stories | Count of "*see tasks*" in epic output |
| Cross-reference links | 0 | 1 per story (link to epic) + 1 per epic story stub (link to story file) | Count of relative path links |

## Non-Goals

- Changing the content of tech stack or project structure lines (just where they appear)
- Creating a shared template include system (too complex for this scope)
- Modifying the SmartMerger algorithm
- Supporting cross-epic story references

## Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Stories become unclear without inline context | Medium | Low | Add "See [Epic N](../epic-N.md) for project context" reference line |
| File aggregation produces overly long tables | Low | Medium | Cap at 20 unique files; show "and N more" |
| Link-stories requires knowing output paths at generation time | Medium | Medium | Only link when output_path is provided for both epic and stories |
| Backward compatibility — consumers parsing story metadata | Low | Medium | Add `inherit_context: bool = True` parameter (default True, set False to preserve old behavior) |

## Dependencies

- DocsMCP Epics 1-17 complete (confirmed)
- Epic 19 (Epic Template Completeness) — story stubs enrichment enables better cross-referencing

## Acceptance Criteria

- [ ] AC1: When `inherit_context=True` (default), stories do NOT include "Tech Stack:" or "Project Structure:" lines in description or technical notes
- [ ] AC2: Stories include a reference line "See [Epic {N}]({relative_path}) for project context and shared definitions" when epic path is known
- [ ] AC3: When `inherit_context=False`, stories include full metadata (backward compatible)
- [ ] AC4: Epic's Files Affected table aggregates unique file paths from all story stubs (when tasks include file_path)
- [ ] AC5: Files Affected table caps at 20 entries with "and N more files across stories" note
- [ ] AC6: When `link_stories=True` and story output paths are provided, epic story stubs include relative path links: `See [full story](stories/story-N.M-slug.md)`
- [ ] AC7: Definition of Done in stories shows "See epic-level Definition of Done" instead of repeating the 6-item checklist
- [ ] AC8: When stories are generated standalone (no epic context), full metadata and DoD are included (no regression)
- [ ] AC9: All existing tests continue to pass
- [ ] AC10: New `inherit_context` and `link_stories` parameters added to MCP tool signatures

---

## Stories

### Story 20.1 — Context Inheritance for Stories

**Size: M (5 points)**

As a story document consumer, I want project metadata to appear only in the epic so that stories are focused on implementation detail, not repeated boilerplate.

**Tasks:**
1. Add `inherit_context: bool = True` parameter to `docs_generate_story` MCP tool
2. Add `epic_path: str = ""` parameter to `docs_generate_story` for cross-referencing
3. Modify `StoryGenerator._render_description()`:
   - When `inherit_context=True`: skip "Tech Stack:" and "Project Structure:" enrichment lines
   - Add reference line: "See [Epic {N}]({epic_path}) for project context" when epic_path provided
4. Modify `StoryGenerator._render_technical_notes()`: same suppression of inherited lines
5. Add `inherit_context` and `epic_path` to `StoryConfig` model
6. Write tests for inheritance on/off, reference rendering, standalone behavior

**Test Cases:**
- `test_inherit_context_suppresses_metadata` — inherit=True → no "Tech Stack:" in output
- `test_inherit_context_false_preserves_metadata` — inherit=False → metadata present (backward compat)
- `test_epic_reference_rendered` — epic_path="epic-12.md" → reference line in description
- `test_standalone_story_full_metadata` — No epic context → full metadata included
- `test_inherit_context_default_true` — Default parameter value is True

**Files:**
- `packages/docs-mcp/src/docs_mcp/generators/stories.py` (model, renderers)
- `packages/docs-mcp/src/docs_mcp/server_gen_tools.py` (add parameters)
- `packages/docs-mcp/tests/unit/test_stories.py` (add tests)

---

### Story 20.2 — Files Affected Aggregation in Epic

**Size: M (5 points)**

As an epic reader, I want the Files Affected table to show real file paths from stories so that I can assess the scope and blast radius at a glance.

**Tasks:**
1. Modify `EpicGenerator._render_files_affected()`:
   - Collect file paths from all `EpicStoryStub.tasks` (when tasks have file_path)
   - Deduplicate and sort by directory
   - Render table with columns: File | Stories | Change Type
   - Map story number to each file
   - Cap at 20 unique files; show "and N more files across M stories"
2. When no story stubs have file paths: show "Files will be determined during story refinement" (not "*see tasks*")
3. Write tests for aggregation, deduplication, capping, and empty fallback

**Test Cases:**
- `test_files_aggregated_from_stubs` — 3 stories with 5 files each → deduplicated table
- `test_files_deduplication` — Same file in 2 stories → 1 row, both story numbers listed
- `test_files_cap_at_20` — 30 files → 20 shown + "and 10 more" note
- `test_files_no_paths_fallback` — No file paths → informative message (not "*see tasks*")
- `test_files_sorted_by_directory` — Files grouped by parent directory

**Files:**
- `packages/docs-mcp/src/docs_mcp/generators/epics.py` (modify `_render_files_affected`)
- `packages/docs-mcp/tests/unit/test_epics.py` (add tests)

---

### Story 20.3 — Story-to-Epic Linking

**Size: S (3 points)**

As a documentation navigator, I want story stubs in the epic to link to full story files so that I can drill down without searching.

**Tasks:**
1. Add `link_stories: bool = False` parameter to `docs_generate_epic` MCP tool
2. Add `story_paths: dict[int, str]` optional parameter (story_number → relative path)
3. Modify `EpicGenerator._render_stories()`:
   - When `link_stories=True` and story path exists: append "→ [Full story]({path})" after title
   - When path not provided for a story: no link (graceful degradation)
4. Add to `EpicConfig` model
5. Write tests

**Test Cases:**
- `test_story_links_rendered` — link_stories=True, paths provided → links in output
- `test_story_links_disabled` — link_stories=False → no links (default behavior)
- `test_story_links_partial` — Only some story paths → links for those, none for others
- `test_story_link_relative_path` — Relative path preserved correctly

**Files:**
- `packages/docs-mcp/src/docs_mcp/generators/epics.py` (model, renderer)
- `packages/docs-mcp/src/docs_mcp/server_gen_tools.py` (add parameters)
- `packages/docs-mcp/tests/unit/test_epics.py` (add tests)

---

### Story 20.4 — Definition of Done Deduplication

**Size: S (2 points)**

As a story consumer, I want the Definition of Done to reference the epic rather than repeating an identical checklist in every story.

**Tasks:**
1. Modify `StoryGenerator._render_definition_of_done()`:
   - When `inherit_context=True` and `epic_path` is set: render "Definition of Done per [Epic {N}]({path})" instead of 6-item checklist
   - When standalone (no epic): render full DoD checklist (preserve current behavior)
2. Write tests

**Test Cases:**
- `test_dod_inherited_from_epic` — inherit=True, epic_path set → reference line only
- `test_dod_standalone_full` — No epic context → full 6-item checklist
- `test_dod_inherit_false_full` — inherit=False → full checklist regardless

**Files:**
- `packages/docs-mcp/src/docs_mcp/generators/stories.py` (modify `_render_definition_of_done`)
- `packages/docs-mcp/tests/unit/test_stories.py` (add tests)
