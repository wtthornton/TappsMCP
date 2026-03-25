# Epic 91: Epic Generator - Close LLM Quality Gaps

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P1 - High
**Estimated LOE:** ~2-3 weeks (1 developer)
**Dependencies:** None
**Blocks:** Epic 92

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that `docs_generate_epic` produces output competitive with raw LLM-generated epics on prose quality, creative ideation, and usability -- while retaining its structural, deterministic, and code-grounded advantages. The current 3/10 prose score and 2/10 ideation score make the tool feel like a skeleton generator rather than a complete planning tool.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Close the quality gap between DocsMCP-generated epics and raw LLM output. Target: raise Prose Quality from 3/10 to 7/10, Creative Ideation from 2/10 to 6/10, Adaptive Detail from 5/10 to 8/10, and Speed for One-offs from 5/10 to 8/10.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

The comparative analysis showed that while `docs_generate_epic` dominates on structure (10/10), consistency (10/10), determinism (10/10), and code-grounding (9/10), it scores poorly on prose quality (3/10), creative ideation (2/10), adaptive detail (5/10), and one-off speed (5/10). Teams using both tools together get the best results, but the epic generator should be useful standalone without requiring an LLM to fill in every placeholder. These gaps also make the tool feel incomplete to first-time users who compare its output to what ChatGPT produces.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Context-aware placeholders use project metadata and epic title/goal to generate specific hint text instead of generic prompts
- [ ] Quick-start mode generates a complete epic from just a title (all other fields inferred or defaulted intelligently)
- [ ] Adaptive style auto-selects standard vs comprehensive based on input complexity (story count, risk count, file count)
- [ ] Risk and story suggestion engine proposes candidate stories/risks from title+goal when none provided
- [ ] All existing 145 epic tests continue to pass
- [ ] New features have >= 90% test coverage
- [ ] `auto_populate` performance stays within 15s budget

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 91.1 -- Context-Aware Placeholder Prose

**Points:** 5

Replace generic placeholder text with context-specific hints derived from the epic title, goal, and project metadata. For example, instead of "Describe the measurable outcome..." generate "Describe how the User Authentication System will improve login security and reduce unauthorized access attempts."

(5 acceptance criteria)

**Tasks:**
- [ ] Refactor `_render_goal` to interpolate title/goal into placeholder text
- [ ] Refactor `_render_motivation` to generate context-aware prompt from title
- [ ] Refactor `_render_technical_notes` placeholders to reference detected tech stack
- [ ] Update `_render_non_goals` to suggest scope boundaries from title keywords

**Definition of Done:** Context-Aware Placeholder Prose is implemented, tests pass, and documentation is updated.

---

### 91.2 -- Quick-Start Mode

**Points:** 3

Add a `quick_start` parameter that generates a complete epic from minimal input (just title). Auto-infers goal from title, generates 3 default story stubs based on common patterns (setup, core implementation, testing/docs), sets sensible defaults for all metadata fields.

(4 acceptance criteria)

**Tasks:**
- [ ] Add `quick_start` bool parameter to `docs_generate_epic` tool handler
- [ ] Implement `_infer_defaults()` method on `EpicGenerator`
- [ ] Generate default story stubs from title keyword analysis
- [ ] Auto-set priority, LOE, and status defaults

**Definition of Done:** Quick-Start Mode is implemented, tests pass, and documentation is updated.

---

### 91.3 -- Adaptive Detail Level

**Points:** 3

Auto-select standard vs comprehensive style based on input complexity instead of requiring explicit style parameter. When stories > 5 or risks provided or files > 3, auto-upgrade to comprehensive. Add a "minimal" style for single-story epics.

(4 acceptance criteria)

**Tasks:**
- [ ] Add `minimal` to `VALID_STYLES` with reduced section set
- [ ] Implement `_auto_detect_style()` based on input signals
- [ ] Add `style="auto"` option that delegates to auto-detection
- [ ] Render minimal style (title, goal, AC, single story, DoD only)

**Definition of Done:** Adaptive Detail Level is implemented, tests pass, and documentation is updated.

---

### 91.4 -- Story and Risk Suggestion Engine

**Points:** 5

When stories list is empty, auto-suggest 3-5 candidate story stubs by analyzing the epic title and goal keywords against common software development patterns (data model, API layer, UI, testing, docs, security, deployment). When risks list is empty in comprehensive mode, auto-suggest risks from the same keyword analysis.

(5 acceptance criteria)

**Tasks:**
- [ ] Create `_suggest_stories()` method with keyword-to-pattern mapping
- [ ] Create `_suggest_risks()` method with domain-risk mapping
- [ ] Integrate suggestions into `_render_stories` when story list empty
- [ ] Integrate risk suggestions into `_render_risk_assessment` when risks empty
- [ ] Map title keywords to common development story patterns
- [ ] Add unit tests for suggestion engine

**Definition of Done:** Story and Risk Suggestion Engine is implemented, tests pass, and documentation is updated.

---

### 91.5 -- Performance Targets Section Enhancement

**Points:** 2

Improve the performance targets section to auto-derive meaningful targets from epic context rather than requiring expert enrichment. Use story count, file count, and AC count to suggest test coverage targets, response time budgets, and quality gate thresholds.

(3 acceptance criteria)

**Tasks:**
- [ ] Enhance `_render_performance_targets` to derive from config signals
- [ ] Add test coverage target derivation from AC count
- [ ] Add quality gate threshold suggestion from file count

**Definition of Done:** Performance Targets Section Enhancement is implemented, tests pass, and documentation is updated.

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- All changes are in `packages/docs-mcp/src/docs_mcp/generators/epics.py` and `server_gen_tools.py`
- Context-aware placeholders must remain deterministic (no LLM calls)
- Quick-start inference should use keyword matching, not ML
- Suggestion engine maps to the same pattern vocabulary used by expert domains
- Must maintain backward compatibility -- all existing parameters work unchanged

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Embedding an LLM in the generation pipeline
- Replacing the deterministic architecture with generative AI
- Multi-language support beyond Python for code analysis
- Interactive refinement or conversational epic building

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Action |
|------|--------|
| `packages/docs-mcp/src/docs_mcp/generators/epics.py` | Modify -- add context-aware placeholders, quick-start, adaptive style, suggestion engine |
| `packages/docs-mcp/src/docs_mcp/server_gen_tools.py` | Modify -- add quick_start param, style="auto" option |
| `packages/docs-mcp/tests/unit/test_epics.py` | Modify -- add tests for all new features |

<!-- docsmcp:end:files-affected -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Prose Quality Score | 3/10 | 7/10 | Manual comparison test |
| Creative Ideation Score | 2/10 | 6/10 | Manual comparison test |
| Adaptive Detail Score | 5/10 | 8/10 | Style auto-detection accuracy |
| Speed for One-offs Score | 5/10 | 8/10 | Time-to-first-epic benchmark |
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

1. **91.1** Context-Aware Placeholder Prose (foundation for all other stories)
2. **91.3** Adaptive Detail Level (minimal style needed before quick-start)
3. **91.2** Quick-Start Mode (depends on 91.1 context-aware + 91.3 auto style)
4. **91.4** Story and Risk Suggestion Engine (independent, can parallel with 91.2)
5. **91.5** Performance Targets Enhancement (independent, lowest priority)

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Keyword-based story suggestions may produce irrelevant stubs for unusual epic titles | Medium | Medium | Provide clear "suggested" labels; make suggestions overridable |
| Auto-style detection heuristics may not match user expectations | Low | Medium | Allow explicit style to always override auto-detection |
| Context-aware placeholders could become stale if project metadata changes | Low | Low | Placeholders re-derive on each generation; no caching |

<!-- docsmcp:end:risk-assessment -->
