# Epic 102: Unified Brain & Cross-Project Intelligence

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P1 - High
**Estimated LOE:** ~5-6 weeks (2 developers)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that learnings, patterns, and quality signals compound across projects. A fix once should prevent that bug everywhere.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Make tapps-brain the shared substrate that both tapps-mcp and docs-mcp read and write.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

tapps-mcp memory, docs-mcp context, and tapps-brain live in uncoordinated silos. Federation exists but neither server exploits it.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] docs-mcp writes architecture facts into tapps-brain
- [ ] tapps-mcp auto-recalls before validate_changed
- [ ] Cross-project search via shared client
- [ ] Hooks fire on session_start under 200ms
- [ ] Unified insight schema spans quality + docs + architecture
- [ ] Federation respects scopes
- [ ] Postgres path integrates cleanly

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 102.1 -- Shared insight schema and migration path

**Points:** 5

Describe what this story delivers...

**Tasks:**
- [ ] Implement shared insight schema and migration path
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Shared insight schema and migration path is implemented, tests pass, and documentation is updated.

---

### 102.2 -- docs-mcp write path for architecture facts

**Points:** 5

Describe what this story delivers...

**Tasks:**
- [ ] Implement docs-mcp write path for architecture facts
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** docs-mcp write path for architecture facts is implemented, tests pass, and documentation is updated.

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

### 102.5 -- Scope and confidentiality enforcement

**Points:** 3

Describe what this story delivers...

**Tasks:**
- [ ] Implement scope and confidentiality enforcement
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Scope and confidentiality enforcement is implemented, tests pass, and documentation is updated.

---

### 102.6 -- Federation UX explain recall provenance

**Points:** 3

Describe what this story delivers...

**Tasks:**
- [ ] Implement federation ux explain recall provenance
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Federation UX explain recall provenance is implemented, tests pass, and documentation is updated.

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

- Build on tapps-brain v2.0.4
- Extend tapps_core.memory bridge
- Version insight schema
- Reuse federation primitives
- Opt-in per-scope in .tapps-mcp.yaml

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Not a new memory store
- No LLM in hot path
- Not replacing session memory

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| 80%+ validate_changed includes recalled memory | - | - | - |
| Cross-project search <300ms p95 | - | - | - |
| Zero scope leaks | - | - | - |
| Fewer repeated-fix commits | - | - | - |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:stakeholders -->
## Stakeholders

| Role | Person | Responsibility |
|------|--------|----------------|
| tapps-brain maintainers | - | - |
| DocsMCP + TappsMCP users | - | - |
| Multi-project teams | - | - |

<!-- docsmcp:end:stakeholders -->

<!-- docsmcp:start:references -->
## References

- packages/docs-mcp/docs/epics/EPIC-43-tapps-brain-v3-postgres.md
- packages/tapps-core/src/tapps_core/memory/

<!-- docsmcp:end:references -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 102.1: Shared insight schema and migration path
2. Story 102.2: docs-mcp write path for architecture facts
3. Story 102.3: Auto-recall hook for tapps_validate_changed
4. Story 102.4: Cross-server client library in tapps-core
5. Story 102.5: Scope and confidentiality enforcement
6. Story 102.6: Federation UX explain recall provenance
7. Story 102.7: Postgres-backed brain performance benchmark

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Scope misconfig leaks | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| Postgres operational surface | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| Schema churn | Medium | High | Warning: Mitigation required - no automated recommendation available |

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
