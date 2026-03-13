# Epic 82: Diataxis Content Classification & Validation

<!-- docsmcp:start:metadata -->
**Status:** Complete
**Priority:** P1 - High
**Estimated LOE:** ~2 weeks (1 developer)
**Dependencies:** Epic 7 (Doc Validation)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that DocsMCP becomes the first MCP documentation tool to enforce the Diataxis content organization framework -- automatically identifying documentation imbalances and guiding projects toward the content mix that produces the clearest, most usable docs.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

DocsMCP automatically classifies documentation into the four Diataxis quadrants (Tutorials, How-to Guides, Reference, Explanation), validates coverage balance, and recommends missing content types -- the first MCP tool to enforce the gold-standard content organization framework.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Diataxis is the 2026 gold standard for doc organization, adopted by Django, NumPy, Cloudflare, and Gatsby. Mixing content modes creates confusing docs. No existing MCP tool classifies or validates against Diataxis. Adding this makes DocsMCP uniquely valuable -- projects get automated feedback on documentation balance without a technical writer audit.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] New `docs_classify_content` tool classifies markdown files into Diataxis quadrants
- [ ] New `docs_check_diataxis` validator scores documentation balance across all four quadrants
- [ ] Classification uses deterministic heuristics (no LLM calls)
- [ ] Each document receives a primary quadrant and confidence score
- [ ] `docs_check_diataxis` returns a coverage map showing percentage per quadrant
- [ ] Missing quadrant recommendations generated with specific content suggestions
- [ ] `docs_check_completeness` enhanced to include Diataxis balance as a scoring factor
- [ ] Frontmatter `diataxis_type` field supported for manual override
- [ ] Unit tests cover classification accuracy on representative document samples

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### [82.1](EPIC-82/story-82.1-diataxis-content-classifier.md) -- Diataxis Content Classifier

**Points:** 8

Deterministic classifier categorizing markdown docs into Diataxis quadrants via heading patterns, content indicators, and structural heuristics.

**Tasks:**
- [ ] Create `analyzers/diataxis.py` with `DiataxisClassifier` class
- [ ] Implement heading-pattern heuristics per quadrant (Tutorial: "Getting Started", "Step N"; How-to: "How to", imperative verbs; Reference: API signatures, parameter tables; Explanation: "Why", "Background", "Architecture")
- [ ] Implement content-indicator scoring (keyword density, structural patterns)
- [ ] Support frontmatter `diataxis_type` override
- [ ] Return `DiataxisResult` with quadrant, confidence, indicators list
- [ ] Handle mixed-mode documents (flag with primary/secondary quadrants)
- [ ] Add comprehensive test suite with representative docs for each quadrant

**Definition of Done:** Diataxis Content Classifier is implemented, tests pass, and documentation is updated.

---

### [82.2](EPIC-82/story-82.2-diataxis-balance-validator.md) -- Diataxis Balance Validator

**Points:** 5

New `docs_check_diataxis` MCP tool scanning all markdown files, classifying each, producing coverage report with recommendations.

**Tasks:**
- [ ] Create `validators/diataxis.py` with `DiataxisValidator` class
- [ ] Implement project-wide scan and classification aggregation
- [ ] Calculate balance score (0-100) based on quadrant distribution
- [ ] Generate recommendations for underrepresented quadrants
- [ ] Return structured result with per-file classifications and overall balance
- [ ] Register `docs_check_diataxis` in `server_val_tools.py`
- [ ] Add tests for balanced and imbalanced project fixtures

**Definition of Done:** Diataxis Balance Validator is implemented, tests pass, and documentation is updated.

---

### [82.3](EPIC-82/story-82.3-completeness-integration-init.md) -- Completeness Integration & Init Support

**Points:** 3

Integrate Diataxis balance into `docs_check_completeness` and add awareness to init/upgrade AGENTS.md.

**Tasks:**
- [ ] Add `diataxis_balance` as optional factor in completeness scoring
- [ ] Update completeness result to include diataxis section when available
- [ ] Add `docs_check_diataxis` to AGENTS.md template tool reference
- [ ] Update docs-mcp CLAUDE.md with Diataxis tool documentation
- [ ] Add integration tests

**Definition of Done:** Completeness Integration & Init Support is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Classification must be fully deterministic (no LLM calls) to match TappsMCP's core principle
- Heading-pattern heuristics are surprisingly accurate -- Django's own Diataxis migration used similar patterns
- The Diataxis axes are: learning-oriented vs task-oriented (vertical) and practical vs theoretical (horizontal)
- Mixed-mode documents should be flagged but not penalized -- some mixing is unavoidable in READMEs
- Balance scoring should weight by project type: libraries need more Reference; apps need more How-to

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- LLM-based classification (violates deterministic principle)
- Auto-generating missing quadrant content (generation is separate from classification)
- Enforcing Diataxis as mandatory (validator reports balance but does not gate)

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Classification accuracy | N/A | 85% | manual audit of 50 sample documents |
| Validator adoption | 0 | 20 | monthly docs_check_diataxis calls |
| Completeness improvement | existing | +5pts | average across projects using Diataxis |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 82.1: Diataxis Content Classifier
2. Story 82.2: Diataxis Balance Validator
3. Story 82.3: Completeness Integration & Init Support

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Heuristic classification false positives on ambiguous docs | Medium | Medium | Confidence scores + manual `diataxis_type` override |
| Some projects legitimately need imbalanced docs | Medium | Low | Weight scoring by project type; no hard gate |

<!-- docsmcp:end:risk-assessment -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Story | Action |
|---|---|---|
| `packages/docs-mcp/src/docs_mcp/analyzers/diataxis.py` | 82.1 | New file: DiataxisClassifier |
| `packages/docs-mcp/src/docs_mcp/validators/diataxis.py` | 82.2 | New file: DiataxisValidator |
| `packages/docs-mcp/src/docs_mcp/server_val_tools.py` | 82.2 | Register docs_check_diataxis |
| `packages/docs-mcp/src/docs_mcp/validators/completeness.py` | 82.3 | Add diataxis_balance factor |

<!-- docsmcp:end:files-affected -->
