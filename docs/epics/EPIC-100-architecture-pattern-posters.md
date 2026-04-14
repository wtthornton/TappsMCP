# Epic 100: Architecture Pattern Recognition & Poster Diagrams

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P1 - High
**Estimated LOE:** ~3-4 weeks (1 developer)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that consumers of docs-mcp get at-a-glance, publication-quality architecture visuals that name the pattern their codebase follows — not just raw import graphs. The current output is accurate but dense; the goal is to make architecture diagrams feel like the Amigoscode pattern poster: one page, one insight, zero scrolling.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Extend docs-mcp's diagram and architecture generators to classify a project into a known architectural archetype (layered, hexagonal, monolith, microservice, event-driven, pipeline) and render compact, semantic-colored "poster" diagrams alongside the existing deep reports.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Today docs_generate_architecture emits a long HTML scroll and docs_generate_diagram produces renderer-specific code with ad-hoc coloring and no legend. Naming the shape is more valuable than drawing every edge.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Pattern classifier returns archetype with confidence
- [ ] pattern_card diagram type renders single-page SVG
- [ ] Semantic role-based color palette
- [ ] Legend blocks in SVG and Mermaid
- [ ] Archetype label in HTML hero section
- [ ] Poster auto-selected for small projects
- [ ] Zero regressions in existing tests

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 100.1 -- Architecture pattern classifier

**Points:** 5

Describe what this story delivers...

**Tasks:**
- [ ] Implement architecture pattern classifier
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Architecture pattern classifier is implemented, tests pass, and documentation is updated.

---

### 100.2 -- Semantic role palette across diagram renderers

**Points:** 3

Describe what this story delivers...

**Tasks:**
- [ ] Implement semantic role palette across diagram renderers
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Semantic role palette across diagram renderers is implemented, tests pass, and documentation is updated.

---

### 100.3 -- Poster / pattern_card diagram type

**Points:** 5

Describe what this story delivers...

**Tasks:**
- [ ] Implement poster / pattern_card diagram type
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Poster / pattern_card diagram type is implemented, tests pass, and documentation is updated.

---

### 100.4 -- Legend blocks for SVG and Mermaid output

**Points:** 2

Describe what this story delivers...

**Tasks:**
- [ ] Implement legend blocks for svg and mermaid output
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Legend blocks for SVG and Mermaid output is implemented, tests pass, and documentation is updated.

---

### 100.5 -- Hero-section archetype label in architecture HTML

**Points:** 2

Describe what this story delivers...

**Tasks:**
- [ ] Implement hero-section archetype label in architecture html
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Hero-section archetype label in architecture HTML is implemented, tests pass, and documentation is updated.

---

### 100.6 -- Auto-select poster variant for small projects

**Points:** 2

Describe what this story delivers...

**Tasks:**
- [ ] Implement auto-select poster variant for small projects
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Auto-select poster variant for small projects is implemented, tests pass, and documentation is updated.

---

### 100.7 -- ADR cross-link from detected pattern

**Points:** 3

Describe what this story delivers...

**Tasks:**
- [ ] Implement adr cross-link from detected pattern
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** ADR cross-link from detected pattern is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Build classifier on ModuleMap + ImportGraph
- Heuristics for hexagonal/microservice/event-driven/layered
- Extend _group_into_layers in architecture.py
- Keep classifier deterministic
- Poster SVG < 50 nodes

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Not replacing detailed diagrams
- Not a GUI editor
- Not auto-generating ADRs

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| 40% faster time-to-understand | - | - | - |
| Poster fits README without scrolling for <15 package projects | - | - | - |
| 80%+ classifier accuracy | - | - | - |
| Zero regressions | - | - | - |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:stakeholders -->
## Stakeholders

| Role | Person | Responsibility |
|------|--------|----------------|
| docs-mcp maintainers | - | - |
| TappsMCP consumers | - | - |

<!-- docsmcp:end:stakeholders -->

<!-- docsmcp:start:references -->
## References

- packages/docs-mcp/src/docs_mcp/generators/diagrams.py
- packages/docs-mcp/src/docs_mcp/generators/architecture.py
- https://blog.amigoscode.com/p/software-architectural-patterns-you

<!-- docsmcp:end:references -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 100.1: Architecture pattern classifier
2. Story 100.2: Semantic role palette across diagram renderers
3. Story 100.3: Poster / pattern_card diagram type
4. Story 100.4: Legend blocks for SVG and Mermaid output
5. Story 100.5: Hero-section archetype label in architecture HTML
6. Story 100.6: Auto-select poster variant for small projects
7. Story 100.7: ADR cross-link from detected pattern

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Hybrid architectures may mislabel | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| SVG hand-rolling maintenance burden | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| Palette conflicts with consumer brand | Medium | Medium | Warning: Mitigation required - no automated recommendation available |

<!-- docsmcp:end:risk-assessment -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Story | Action |
|---|---|---|
| Files will be determined during story refinement | - | - |

<!-- docsmcp:end:files-affected -->

<!-- docsmcp:start:performance-targets -->
## Performance Targets

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Test coverage | baseline | >= 80% | pytest --cov |
| Acceptance criteria pass rate | 0% | 100% | CI pipeline |
| Story completion rate | 0% | 100% | Sprint tracking |

<!-- docsmcp:end:performance-targets -->
