# Epic 101: Zero-Friction Quality Pipeline

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P0 - Critical
**Estimated LOE:** ~4-5 weeks (1-2 developers)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that using TappsMCP feels invisible — agents and humans get correct, fast, actionable feedback on every edit without reading 20 tool descriptions.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Collapse the 26 tapps-mcp tools into a frictionless edit → check → validate → done loop with smart defaults, aggressive speedups, and proactive nudges.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Session logs show agents frequently skip validate_changed, pass wrong arguments, or rerun expensive scans. Fixing ergonomics is higher-leverage than adding new checkers.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] tapps_quick_check under 2s single-file via caching
- [ ] tapps_validate_changed auto-detects safely capped at 30s
- [ ] Single tapps_pipeline orchestrator entry point
- [ ] Errors include exact next command
- [ ] Shared content-hash cache across scoring/gate/security
- [ ] Top-1 nudge selection
- [ ] next_steps under 3 items copy-pasteable

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 101.1 -- Shared content-hash cache for scoring + gate + security

**Points:** 5

Describe what this story delivers...

**Tasks:**
- [ ] Implement shared content-hash cache for scoring + gate + security
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Shared content-hash cache for scoring + gate + security is implemented, tests pass, and documentation is updated.

---

### 101.2 -- tapps_pipeline one-call orchestrator

**Points:** 5

Describe what this story delivers...

**Tasks:**
- [ ] Implement tapps_pipeline one-call orchestrator
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** tapps_pipeline one-call orchestrator is implemented, tests pass, and documentation is updated.

---

### 101.3 -- Safer tapps_validate_changed auto-detect with 30s cap

**Points:** 3

Describe what this story delivers...

**Tasks:**
- [ ] Implement safer tapps_validate_changed auto-detect with 30s cap
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Safer tapps_validate_changed auto-detect with 30s cap is implemented, tests pass, and documentation is updated.

---

### 101.4 -- Actionable error envelope with copy-paste next command

**Points:** 2

Describe what this story delivers...

**Tasks:**
- [ ] Implement actionable error envelope with copy-paste next command
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Actionable error envelope with copy-paste next command is implemented, tests pass, and documentation is updated.

---

### 101.5 -- Top-1 nudge selection with impact scoring

**Points:** 3

Describe what this story delivers...

**Tasks:**
- [ ] Implement top-1 nudge selection with impact scoring
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Top-1 nudge selection with impact scoring is implemented, tests pass, and documentation is updated.

---

### 101.6 -- Quick-mode performance budget and regression test

**Points:** 3

Describe what this story delivers...

**Tasks:**
- [ ] Implement quick-mode performance budget and regression test
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Quick-mode performance budget and regression test is implemented, tests pass, and documentation is updated.

---

### 101.7 -- Agent telemetry detect skipped validate_changed

**Points:** 3

Describe what this story delivers...

**Tasks:**
- [ ] Implement agent telemetry detect skipped validate_changed
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Agent telemetry detect skipped validate_changed is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- SHA-256 content hashing
- Cache in tapps_core.cache module
- Orchestrator short-circuits on security floor
- Honor staging/production presets
- Hook into doctor.py

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Not changing scoring model
- Not adding new checkers
- Not replacing AGENTS.md

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Median quick_check < 1.5s | - | - | - |
| Skipped validate rate < 5% | - | - | - |
| Tools-per-task down 30% | - | - | - |
| Zero new false positives | - | - | - |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:stakeholders -->
## Stakeholders

| Role | Person | Responsibility |
|------|--------|----------------|
| TappsMCP maintainers | - | - |
| Agent-driven CI users | - | - |
| Claude Code plugin users | - | - |

<!-- docsmcp:end:stakeholders -->

<!-- docsmcp:start:references -->
## References

- packages/tapps-mcp/src/tapps_mcp/common/nudges.py
- packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py
- packages/tapps-mcp/src/tapps_mcp/tools/checklist.py

<!-- docsmcp:end:references -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 101.1: Shared content-hash cache for scoring + gate + security
2. Story 101.2: tapps_pipeline one-call orchestrator
3. Story 101.3: Safer tapps_validate_changed auto-detect with 30s cap
4. Story 101.4: Actionable error envelope with copy-paste next command
5. Story 101.5: Top-1 nudge selection with impact scoring
6. Story 101.6: Quick-mode performance budget and regression test
7. Story 101.7: Agent telemetry detect skipped validate_changed

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Caching bugs mask regressions | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| Orchestrator drift | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| Telemetry privacy concerns | Medium | Medium | Warning: Mitigation required - no automated recommendation available |

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
