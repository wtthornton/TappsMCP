# Epic 102: Unified Brain & Cross-Project Intelligence

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P1 - High
**Estimated LOE:** ~5-6 weeks (2 developers)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that learnings, patterns, and quality signals compound across projects instead of being trapped in per-repo memory. A fix once should prevent that bug everywhere.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Make tapps-brain the shared substrate that both tapps-mcp and docs-mcp read and write — quality insights, doc patterns, architecture classifications, and expert enrichments flow through a single federated knowledge layer.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Today tapps-mcp memory, docs-mcp context, and tapps-brain live in adjacent but uncoordinated silos. Consumers re-learn the same project every session. Federation exists in tapps-brain but neither server exploits it for proactive recall.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] docs-mcp writes architecture classifications and API surface changes into tapps-brain
- [ ] tapps-mcp auto-recalls relevant memories before every validate_changed
- [ ] Cross-project search works from either server via a shared client
- [ ] Memory hooks fire on session_start with < 200ms overhead
- [ ] A unified 'insight' schema spans quality scores + doc metrics + architecture facts
- [ ] Federation respects project scopes and confidentiality
- [ ] tapps-brain v3 Postgres path (EPIC-43) integrates cleanly

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 102.1 -- Shared insight schema + migration path

**Points:** 5

Describe what this story delivers...

**Tasks:**
- [ ] Implement shared insight schema + migration path
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Shared insight schema + migration path is implemented, tests pass, and documentation is updated.

---

### 102.2 -- docs-mcp → tapps-brain write path for architecture facts

**Points:** 5

Describe what this story delivers...

**Tasks:**
- [ ] Implement docs-mcp → tapps-brain write path for architecture facts
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** docs-mcp → tapps-brain write path for architecture facts is implemented, tests pass, and documentation is updated.

---

### 102.3 -- Auto-recall hook for tapps_validate_changed

**Points:** 3

Describe what this story delivers...

**Tasks:**
- [ ] Implement auto-recall hook for tapps_validate_changed
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Auto-recall hook for tapps_validate_changed is implemented, tests pass, and documentation is updated.

---

### 102.4 -- Cross-server client library in tapps-core

**Points:** 5

Describe what this story delivers...

**Tasks:**
- [ ] Implement cross-server client library in tapps-core
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Cross-server client library in tapps-core is implemented, tests pass, and documentation is updated.

---

### 102.5 -- Scope + confidentiality enforcement

**Points:** 3

Describe what this story delivers...

**Tasks:**
- [ ] Implement scope + confidentiality enforcement
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Scope + confidentiality enforcement is implemented, tests pass, and documentation is updated.

---

### 102.6 -- Federation UX: explain where recalled memory came from

**Points:** 3

Describe what this story delivers...

**Tasks:**
- [ ] Implement federation ux: explain where recalled memory came from
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Federation UX: explain where recalled memory came from is implemented, tests pass, and documentation is updated.

---

### 102.7 -- Postgres-backed brain performance benchmark

**Points:** 5

Describe what this story delivers...

**Tasks:**
- [ ] Implement postgres-backed brain performance benchmark
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Postgres-backed brain performance benchmark is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Build on tapps-brain v2.0.4 client
- Extend tapps_core.memory injection bridge instead of duplicating
- Insight schema must version explicitly for future migrations
- Reuse federation primitives from tapps-brain rather than reinventing
- Privacy: opt-in per-scope with explicit enumeration in .tapps-mcp.yaml

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Not building a new memory store (use tapps-brain)
- Not adding LLM-based summarization in the hot path
- Not replacing per-session memory

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| 80%+ of validate_changed calls include at least one relevant recalled memory | - | - | - |
| Cross-project search returns in < 300ms p95 | - | - | - |
| Zero cross-scope leaks in audit | - | - | - |
| Measurable reduction in repeated-fix commits | - | - | - |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:stakeholders -->
## Stakeholders

| Role | Person | Responsibility |
|------|--------|----------------|
| tapps-brain maintainers | - | - |
| TappsMCP + DocsMCP users | - | - |
| Multi-project teams | - | - |

<!-- docsmcp:end:stakeholders -->

<!-- docsmcp:start:references -->
## References

- packages/docs-mcp/docs/epics/EPIC-43-tapps-brain-v3-postgres.md
- packages/tapps-core/src/tapps_core/memory/
- https://github.com/wtthornton/tapps-brain

<!-- docsmcp:end:references -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 102.1: Shared insight schema + migration path
2. Story 102.2: docs-mcp → tapps-brain write path for architecture facts
3. Story 102.3: Auto-recall hook for tapps_validate_changed
4. Story 102.4: Cross-server client library in tapps-core
5. Story 102.5: Scope + confidentiality enforcement
6. Story 102.6: Federation UX: explain where recalled memory came from
7. Story 102.7: Postgres-backed brain performance benchmark

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Federation may leak project data if scopes misconfigured | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| Postgres migration adds operational surface | High | High | Warning: Mitigation required - no automated recommendation available |
| Schema churn could break consumer dashboards | Medium | High | Warning: Mitigation required - no automated recommendation available |

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
