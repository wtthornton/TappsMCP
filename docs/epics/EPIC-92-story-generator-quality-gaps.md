# Epic 92: Story Generator - Performance Parity and Quality Gaps

<!-- docsmcp:start:metadata -->
**Status:** Done (closed 2026-04-22; all 5 stories implemented — confirmed by the [EPIC-103 generator review](../reviews/EPIC-103-REVIEW-generators.md))
**Priority:** P1 - High
**Estimated LOE:** ~1.5-2 weeks (1 developer)
**Dependencies:** Epic 91 (shared patterns for context-aware prose and quick-start)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that `docs_generate_story` matches the epic generator's performance fixes and closes the same quality gaps identified in the LLM comparison. The story generator currently has unbounded module map walks, sequential expert consultations, and the same generic placeholder problem -- plus it lacks task brainstorming and better Gherkin scaffolding.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Bring the story generator to performance and quality parity with the epic generator. Apply the same perf fixes (depth cap, parallel experts, wall-clock timeout), raise Prose Quality from 3/10 to 7/10, and add task suggestion and improved Gherkin scaffolding.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

The story generator shares the same architecture as the epic generator but was not included in the performance fix commit (31237f1). It still has unbounded module map depth (default 10), sequential expert consultations (4 domains), and no wall-clock budget. The quality comparison also showed the same prose weakness (3/10) and lack of creative ideation (2/10 for task brainstorming). Since stories are generated more frequently than epics (typically 3-8 per epic), the cumulative impact of these issues is higher.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Module map depth capped to 3 in story generator `_enrich_module_map`
- [ ] Expert consultations parallelized via `ThreadPoolExecutor` in story `_enrich_experts`
- [ ] Wall-clock budget of 15s enforced in story `_auto_populate` with partial fallback
- [ ] Context-aware placeholder prose uses story title, role, and description
- [ ] Quick-start mode generates complete story from just title + epic_number
- [ ] Task suggestion engine proposes implementation tasks from description keywords
- [ ] Gherkin AC scaffolding generates meaningful Given/When/Then from AC text, not just placeholders
- [ ] All existing story tests continue to pass
- [ ] New features have >= 90% test coverage

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 92.1 -- Port Performance Fixes to Story Generator

**Points:** 3

Apply the same three performance fixes from epic generator commit 31237f1: cap module map depth to 3, parallelize expert consultations with `ThreadPoolExecutor(max_workers=4)`, and add 15s wall-clock budget to `_auto_populate` with partial enrichment fallback.

(4 acceptance criteria)

**Tasks:**
- [ ] Cap `_enrich_module_map` to `depth=3` in `stories.py`
- [ ] Refactor `_enrich_experts` to use `ThreadPoolExecutor` with `as_completed`
- [ ] Add `_AUTO_POPULATE_TIMEOUT_S` ClassVar and budget checking loop
- [ ] Update `_auto_populate` to skip remaining steps when budget exceeded

**Definition of Done:** Story generator `auto_populate` completes within 15s on large projects; expert consultations run in parallel.

---

### 92.2 -- Context-Aware Story Placeholders

**Points:** 3

Replace generic placeholder text in story sections with context-derived hints. Use story title, role, want, and so_that fields to generate specific prompts. For example, instead of "Describe what this story delivers..." generate "Describe how Add Login Form Validation will enable developers to validate login credentials so that invalid logins are rejected."

(4 acceptance criteria)

**Tasks:**
- [ ] Refactor `_render_description` placeholder to interpolate title/role/want
- [ ] Refactor `_render_tasks` placeholder to suggest tasks from title keywords
- [ ] Refactor `_render_acceptance_criteria` placeholder to derive from want/so_that
- [ ] Update Definition of Done placeholder with story-specific items

**Definition of Done:** All placeholder sections reflect story-specific context when title/role/want are provided.

---

### 92.3 -- Quick-Start Story Mode

**Points:** 3

Add `quick_start` parameter that generates a complete story from minimal input (title + epic_number). Auto-infers role from epic context, generates default tasks (implement, test, document), sets sensible sizing defaults, and creates basic acceptance criteria from the title.

(4 acceptance criteria)

**Tasks:**
- [ ] Add `quick_start` bool parameter to `docs_generate_story` tool handler
- [ ] Implement `_infer_story_defaults()` on `StoryGenerator`
- [ ] Auto-generate role/want/so_that from title parsing
- [ ] Auto-set points and size based on task count heuristic

**Definition of Done:** `docs_generate_story(title="Add login validation", epic_number=91, quick_start=True)` produces a complete, well-structured story document.

---

### 92.4 -- Task Suggestion Engine

**Points:** 5

When tasks list is empty, auto-suggest 3-6 implementation tasks by analyzing the story title, description, and files list. Map keywords to common development task patterns (create model, add endpoint, write tests, update docs, add validation, handle errors). Include `file_path` hints when files are provided.

(4 acceptance criteria)

**Tasks:**
- [ ] Create `_suggest_tasks()` method with keyword-to-task mapping
- [ ] Map story title keywords to development task patterns
- [ ] Include `file_path` association when files list provided
- [ ] Integrate into `_render_tasks` when task list empty
- [ ] Ensure suggested tasks are specific, not generic

**Definition of Done:** Empty tasks list produces 3-6 relevant, title-derived task suggestions instead of generic "Define implementation tasks..." placeholder.

---

### 92.5 -- Improved Gherkin Scaffolding

**Points:** 3

Upgrade Gherkin AC generation from generic placeholder text to meaningful Given/When/Then derived from the AC text, role, and want fields. Parse AC keywords to generate specific preconditions, actions, and outcomes instead of "[describe the precondition]" placeholders.

(3 acceptance criteria)

**Tasks:**
- [ ] Parse AC text to extract subject/verb/object for Gherkin mapping
- [ ] Use role field as the Given actor context
- [ ] Use want field to derive When action
- [ ] Derive Then clause from AC text or so_that field

**Definition of Done:** Gherkin output uses role/want/AC text to produce readable scenarios instead of bracket placeholders.

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Story generator lives at `packages/docs-mcp/src/docs_mcp/generators/stories.py`, shares architecture with `epics.py`
- Perf fixes should mirror `epics.py` exactly for consistency
- Task suggestion must remain deterministic -- keyword mapping, not ML
- Gherkin improvement uses NLP-lite parsing (regex + keyword extraction), not full NLP
- The story generator has 4 expert domains (security, testing, architecture, code-quality) vs the epic generator's 8

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Full NLP or LLM-based task generation
- Gherkin step definition generation (only scenario scaffolding)
- Cross-story dependency resolution
- Story splitting recommendations

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Action |
|------|--------|
| `packages/docs-mcp/src/docs_mcp/generators/stories.py` | Modify -- perf fixes, context-aware prose, quick-start, task suggestions, Gherkin |
| `packages/docs-mcp/src/docs_mcp/server_gen_tools.py` | Modify -- add quick_start param to story handler |
| `packages/docs-mcp/tests/unit/test_stories.py` | Modify -- add tests for all new features |

<!-- docsmcp:end:files-affected -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| auto_populate wall time | unbounded | < 15s | perf_counter timing |
| Story Prose Quality | 3/10 | 7/10 | Manual comparison |
| Task Suggestion Relevance | 0/10 | 6/10 | Manual review |
| Gherkin Quality | 3/10 | 7/10 | Manual comparison |
| Test Coverage | 85% | 95% | pytest --cov |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:stakeholders -->
## Stakeholders

| Role | Name | Responsibility |
|------|------|---------------|
| Owner | DocsMCP Team | Implementation |
| Reviewer | TappsMCP Team | Code Review |
| Consumer | AI Coding Assistants | Integration Testing |

<!-- docsmcp:end:stakeholders -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. **92.1** Port Performance Fixes (P0 -- unblocks safe `auto_populate` usage)
2. **92.2** Context-Aware Story Placeholders (foundation for other quality improvements)
3. **92.3** Quick-Start Story Mode (depends on 92.2 for context-aware defaults)
4. **92.4** Task Suggestion Engine (independent, can parallel with 92.3)
5. **92.5** Improved Gherkin Scaffolding (independent, lowest coupling)

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Task suggestion keywords may not cover domain-specific terminology | Medium | Medium | Provide extensible keyword map; fall back to generic tasks |
| Gherkin auto-generation may produce grammatically awkward scenarios | Medium | Low | Keep bracket placeholders as fallback for unparseable AC text |
| Performance fixes may change existing test behavior for auto_populate tests | Low | Medium | Run full test suite after each change; match epic generator patterns exactly |

<!-- docsmcp:end:risk-assessment -->
