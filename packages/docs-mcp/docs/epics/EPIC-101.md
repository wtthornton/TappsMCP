# Epic 101: Zero-Friction Quality Pipeline

<!-- docsmcp:start:metadata -->
**Status:** Complete
**Priority:** P0 - Critical
**Estimated LOE:** ~4-5 weeks (1-2 developers)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that using TappsMCP feels invisible — agents and humans get correct, fast, actionable feedback on every edit without reading 20 tool descriptions. Today the pipeline is powerful but requires discipline; we want it to be the path of least resistance.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Collapse the 26 tapps-mcp tools into a frictionless edit → check → validate → done loop with smart defaults, aggressive speedups, and proactive nudges, so agents rarely need to choose which tool to call.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Internal telemetry and session logs show agents frequently skip tapps_validate_changed, pass wrong arguments (e.g. omit file_paths), or rerun expensive scans. Each skipped step erodes trust. Fixing the ergonomics is higher-leverage than adding new checkers.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] tapps_quick_check runs in under 2 seconds on a single file via aggressive caching
- [ ] tapps_validate_changed auto-detects changed files safely and caps runtime at 30s in quick mode
- [ ] A single tapps_pipeline entry point orchestrates session_start→quick_check→validate_changed→checklist
- [ ] Error messages always include the exact next command to run
- [ ] Content-hash cache shared across tapps_score_file / tapps_quality_gate / tapps_security_scan
- [ ] nudges.py suggestions reduced from N to the top-1 highest-impact action
- [ ] Every tool response next_steps is under 3 items and copy-pasteable

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 101.1 -- Shared content-hash cache for scoring + gate + security

**Points:** 5 | **Status:** ✅ Done (v2.7.1)

SHA-256 content-hash cache shared across `tapps_score_file`, `tapps_quality_gate`, and `tapps_security_scan`. Unchanged files are served from cache without re-invoking the scorer.

**Tasks:**
- [x] Implement shared content-hash cache for scoring + gate + security
- [x] Write unit tests
- [x] Update documentation

---

### 101.2 -- tapps_pipeline: one-call orchestrator

**Points:** 5 | **Status:** ✅ Done (v2.7.0)

Single `tapps_pipeline` entry point that orchestrates session_start → quick_check → validate_changed → checklist in one call, short-circuiting on security floor failure.

**Tasks:**
- [x] Implement tapps_pipeline: one-call orchestrator
- [x] Write unit tests
- [x] Update documentation

---

### 101.3 -- Safer tapps_validate_changed auto-detect with 30s cap

**Points:** 3 | **Status:** ✅ Done (v2.7.2)

Auto-detect mode caps at 30 s in quick mode so agents cannot hang waiting for a large repo scan.

**Tasks:**
- [x] Implement safer tapps_validate_changed auto-detect with 30s cap
- [x] Write unit tests
- [x] Update documentation

---

### 101.4 -- Actionable error envelope with copy-paste next command

**Points:** 2 | **Status:** ✅ Done (v2.7.3)

Every error response now includes an exact copy-paste command in `next_steps` so agents always know what to run next.

**Tasks:**
- [x] Implement actionable error envelope with copy-paste next command
- [x] Write unit tests
- [x] Update documentation

---

### 101.5 -- Top-1 nudge selection with impact scoring

**Points:** 3 | **Status:** ✅ Done

`_MAX_NUDGES` reduced from 3 to 1. Each nudge rule carries an impact score; `compute_next_steps()` collects all matching rules, sorts by impact, and returns only the highest-impact action.

**Tasks:**
- [x] Implement top-1 nudge selection with impact scoring
- [x] Write unit tests
- [x] Update documentation

---

### 101.6 -- Quick-mode performance budget + regression test

**Points:** 3 | **Status:** ✅ Done

`QUICK_CHECK_BUDGET_MS = 2000` constant defined. Regression tests verify the cache-hit path skips the scorer and returns well within the 2-second budget.

**Tasks:**
- [x] Implement quick-mode performance budget + regression test
- [x] Write unit tests
- [x] Update documentation

---

### 101.7 -- Agent telemetry: detect skipped validate_changed and surface

**Points:** 3 | **Status:** ✅ Done

New nudge rule on `tapps_checklist`: when the checklist passes but `tapps_validate_changed`/`tapps_pipeline` was never called (and files were scored this session), surfaces a WARNING directing the agent to run `validate_changed`.

**Tasks:**
- [x] Implement agent telemetry: detect skipped validate_changed and surface
- [x] Write unit tests
- [x] Update documentation

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Use SHA-256 content hashing (see everything-claude-code:content-hash-cache-pattern)
- Cache layer lives in tapps_core.metrics or new tapps_core.cache module
- Pipeline orchestrator must short-circuit on security floor failure
- Honor existing preset configs (staging/production)
- Hook into distribution/doctor.py to surface cache health

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Not changing the 7-category scoring model
- Not adding new quality checkers
- Not replacing AGENTS.md guidance

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Median tapps_quick_check latency < 1.5s | - | - | - |
| Skipped validate_changed rate < 5% in session telemetry | - | - | - |
| Mean tools-per-task drops by 30% | - | - | - |
| Zero new false positives vs. baseline | - | - | - |

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
- packages/tapps-mcp/src/tapps_mcp/distribution/doctor.py

<!-- docsmcp:end:references -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 101.1: Shared content-hash cache for scoring + gate + security
2. Story 101.2: tapps_pipeline: one-call orchestrator
3. Story 101.3: Safer tapps_validate_changed auto-detect with 30s cap
4. Story 101.4: Actionable error envelope with copy-paste next command
5. Story 101.5: Top-1 nudge selection with impact scoring
6. Story 101.6: Quick-mode performance budget + regression test
7. Story 101.7: Agent telemetry: detect skipped validate_changed and surface

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Caching bugs can mask real regressions | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| Orchestrator adds a layer that must stay in sync with individual tools | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| Telemetry may raise privacy concerns for on-prem users | Medium | Medium | Warning: Mitigation required - no automated recommendation available |

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
