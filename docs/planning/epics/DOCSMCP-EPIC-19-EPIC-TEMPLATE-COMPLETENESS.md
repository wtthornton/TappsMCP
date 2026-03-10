# DocsMCP Epic 19 — Epic Template Completeness

> Status: Proposed | Priority: High | Package: docs-mcp
> Triggered by: [Epic 12 Review Feedback](../../epic-12-review-feedback.md) (TheStudio)
> Addresses: Review items #5, #6, #7, #8

---

## Goal

Add three missing structural sections to the epic template (Success Metrics, Stakeholders, OKR/References) and make story stubs in the epic meaningfully summarize their full story content. After this epic, the comprehensive epic template aligns with Saga's eight-part structure and Meridian's review checklist.

## Motivation

Meridian's review of TheStudio Epic 12 identified 4 GAPs against the standard Saga epic structure: no success metrics, no stakeholders, no OKR link, and hollow story stubs. These are structural gaps in the docs-mcp epic template itself — every epic generated will have these gaps until the template is enhanced. Success metrics and stakeholder sections are standard in 2026 planning frameworks (PMI, SAFe, Shape Up) and are required by Meridian's 7-point checklist.

## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Meridian checklist pass rate | 2/7 PASS, 1 PARTIAL, 4 GAP | 7/7 PASS | Run checklist on generated epic |
| Story stub task count | 3 generic tasks per story | ≥3 real tasks from full story | Compare stub tasks to full story tasks |
| Sections per comprehensive epic | 12 | 15 (+ Success Metrics, Stakeholders, References) | Count rendered sections |

## Non-Goals

- Auto-generating success metric values (caller must provide them)
- RACI matrix enforcement (just provide the section structure)
- Linking to external OKR tools via API
- Changing the standard (non-comprehensive) epic style

## Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Callers don't provide success metrics → section is empty | High | Medium | Provide 1-2 example metrics derived from acceptance criteria as starter suggestions |
| Stakeholder section adds noise for solo developers | Medium | Low | Only render in comprehensive style; omit when no stakeholders provided |
| Story stub summarization increases generation time | Low | Low | Summary is string truncation, not analysis |

## Dependencies

- DocsMCP Epics 1-17 complete (confirmed)
- Epic 18 (Never Emit Empty Content) — recommended to implement first for consistent suppression logic

## Acceptance Criteria

- [ ] AC1: Comprehensive epic template includes a "Success Metrics" section with table format (Metric | Baseline | Target | Measurement)
- [ ] AC2: When `success_metrics` parameter is empty, section shows 1-2 suggested metrics derived from acceptance criteria count and story count
- [ ] AC3: Comprehensive epic template includes a "Stakeholders" section with role/person/responsibility columns
- [ ] AC4: When `stakeholders` parameter is empty, section is omitted (not rendered with placeholders)
- [ ] AC5: Comprehensive epic template includes a "References" section for OKR/roadmap links
- [ ] AC6: When `references` parameter is empty, section is omitted
- [ ] AC7: Epic story stubs include the first 4 tasks from the full story (not generic "Implement X / Write tests / Update docs")
- [ ] AC8: Epic story stubs include the story's acceptance criteria count (e.g., "5 acceptance criteria")
- [ ] AC9: New parameters (`success_metrics`, `stakeholders`, `references`) are optional strings (comma-separated or JSON) on the MCP tool
- [ ] AC10: Standard style is unchanged (new sections are comprehensive-only)
- [ ] AC11: All existing tests continue to pass
- [ ] AC12: docsmcp markers are added for all new sections (SmartMerger compatible)

---

## Stories

### Story 19.1 — Success Metrics Section

**Size: M (5 points)**

As an epic author, I want a Success Metrics section in comprehensive epics so that stakeholders can evaluate completion quantitatively.

**Tasks:**
1. Add `success_metrics: list[str]` field to `EpicConfig` model (default empty)
2. Add `success_metrics: str = ""` parameter to `docs_generate_epic` MCP tool (comma-separated or JSON array)
3. Create `_render_success_metrics()` method in `EpicGenerator`:
   - Render table with columns: Metric | Baseline | Target | Measurement
   - Parse each metric string as pipe-delimited or render as single-column
   - When empty: derive 1-2 suggestions:
     - "All {N} acceptance criteria met" (from AC count)
     - "All {M} stories completed" (from story count)
   - Wrap in `<!-- docsmcp:start:success-metrics -->` markers
4. Insert after acceptance criteria section in comprehensive style
5. Write tests for provided metrics, derived suggestions, and marker rendering

**Test Cases:**
- `test_success_metrics_provided` — 3 metrics provided → table with 3 rows
- `test_success_metrics_empty_derives_suggestions` — No metrics, 5 ACs, 3 stories → 2 suggested rows
- `test_success_metrics_standard_style_omitted` — Standard style → section not present
- `test_success_metrics_markers` — Output contains docsmcp start/end markers
- `test_success_metrics_pipe_delimited` — "MTTR|4h|1h|PagerDuty" → 4-column row

**Files:**
- `packages/docs-mcp/src/docs_mcp/generators/epics.py` (add model field, renderer, integration)
- `packages/docs-mcp/src/docs_mcp/server_gen_tools.py` (add parameter)
- `packages/docs-mcp/tests/unit/test_epics.py` (add tests)

---

### Story 19.2 — Stakeholders Section

**Size: S (3 points)**

As an epic author, I want a Stakeholders section so that ownership and review responsibilities are documented.

**Tasks:**
1. Add `stakeholders: list[str]` field to `EpicConfig` model (default empty)
2. Add `stakeholders: str = ""` parameter to `docs_generate_epic` MCP tool
3. Create `_render_stakeholders()` method in `EpicGenerator`:
   - Render table with columns: Role | Person | Responsibility
   - Parse each stakeholder string as pipe-delimited
   - When empty: omit section entirely (per Epic 18 "never emit empty" principle)
   - Wrap in docsmcp markers
4. Insert after Success Metrics section in comprehensive style
5. Write tests

**Test Cases:**
- `test_stakeholders_provided` — 2 stakeholders → table with 2 rows
- `test_stakeholders_empty_omitted` — No stakeholders → section absent from output
- `test_stakeholders_standard_style_omitted` — Standard style → section not present
- `test_stakeholders_pipe_delimited` — "Owner|Alice|Implementation" → 3-column row

**Files:**
- `packages/docs-mcp/src/docs_mcp/generators/epics.py`
- `packages/docs-mcp/src/docs_mcp/server_gen_tools.py`
- `packages/docs-mcp/tests/unit/test_epics.py`

---

### Story 19.3 — OKR/References Section

**Size: S (2 points)**

As an epic author, I want a References section so that epics link to OKRs, roadmap items, or related documents.

**Tasks:**
1. Add `references: list[str]` field to `EpicConfig` model (default empty)
2. Add `references: str = ""` parameter to `docs_generate_epic` MCP tool
3. Create `_render_references()` method in `EpicGenerator`:
   - Render as bulleted list of links/text
   - Auto-detect markdown links vs plain text
   - When empty: omit section entirely
   - Wrap in docsmcp markers
4. Insert after Stakeholders section (or after Success Metrics if Stakeholders omitted)
5. Write tests

**Test Cases:**
- `test_references_provided` — 3 references → bulleted list with 3 items
- `test_references_empty_omitted` — No references → section absent
- `test_references_markdown_links` — "[OKR](http://...)" preserved as clickable link
- `test_references_standard_style_omitted` — Standard style → not present

**Files:**
- `packages/docs-mcp/src/docs_mcp/generators/epics.py`
- `packages/docs-mcp/src/docs_mcp/server_gen_tools.py`
- `packages/docs-mcp/tests/unit/test_epics.py`

---

### Story 19.4 — Rich Story Stubs in Epic

**Size: M (5 points)**

As an epic reader, I want story stubs to summarize real task content so that reading just the epic gives an accurate view of story scope.

**Tasks:**
1. Extend `EpicStoryStub` model with optional `tasks: list[str]` and `ac_count: int` fields
2. Modify `EpicGenerator._render_stories()`:
   - When story stub has `tasks`: render first 4 tasks (not generic "Implement X")
   - When story stub has `ac_count`: show "(N acceptance criteria)" after description
   - When tasks list is empty: fall back to current generic behavior (backward compat)
3. Modify `parse_stories_json()` to accept tasks and ac_count from JSON input
4. Update `docs_generate_epic` tool's `stories` parameter documentation
5. Write tests for rich stubs, truncation to 4 tasks, and backward compatibility

**Test Cases:**
- `test_story_stub_with_tasks` — 6 tasks provided → first 4 rendered in epic
- `test_story_stub_with_ac_count` — ac_count=5 → "(5 acceptance criteria)" shown
- `test_story_stub_no_tasks_backward_compat` — No tasks → generic tasks (existing behavior)
- `test_story_stub_json_parsing` — JSON with tasks array parsed correctly
- `test_story_stub_truncation` — 8 tasks → 4 shown + "and 4 more..."

**Files:**
- `packages/docs-mcp/src/docs_mcp/generators/epics.py` (model, renderer, parser)
- `packages/docs-mcp/tests/unit/test_epics.py` (add tests)
