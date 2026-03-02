# Epic Prioritization & Story Ranking

**Date:** 2026-03-02
**Scope:** All open/remaining epics and stories
**Method:** Prioritized by value delivery, dependency readiness, risk reduction, and effort efficiency

---

## Executive Summary

TappsMCP has completed 28 epics delivering 28 MCP tools, 4500+ tests, and a comprehensive quality pipeline. **6 epics remain** with approximately 15-22 weeks of work across ~45 stories. This document provides a prioritized execution order based on four criteria:

1. **Value delivery** -- Does this directly improve the product for consuming projects?
2. **Dependency readiness** -- Are all prerequisites satisfied?
3. **Risk reduction** -- Does this fix known problems or prevent regressions?
4. **Effort efficiency** -- What is the impact-to-effort ratio?

---

## Priority Tier Summary

| Tier | Epic | Priority | LOE | Rationale |
|------|------|----------|-----|-----------|
| **Tier 1: Do Now** | Epic 28 (Phases 2-5) | P0-P1 | ~7 days | Fix own quality gate failures; credibility risk |
| **Tier 2: Do Next** | Epic 36 | P1 | ~2-2.5 weeks | All dependencies met; expands hook coverage; low risk |
| **Tier 3: Do Next** | Epic 37 | P1 | ~2.5-3 weeks | Plugin distribution + onboarding; depends on Epic 36 |
| **Tier 4: Strategic** | Epic 30 | P1 | ~3-4 weeks | Validates core product hypothesis; foundational for 31-32 |
| **Tier 5: Strategic** | Epic 31 | P1 | ~3-4 weeks | Template optimization loop; depends on Epic 30 |
| **Tier 6: Deferred** | Epic 32 | P2 | ~3-4 weeks | Tool effectiveness benchmarking; depends on Epic 30 |

---

## Tier 1: Do Now -- Epic 28 Phases 2-5 (Quality Review Remediation)

### Why first?

- **Credibility risk**: TappsMCP is a code quality tool that fails its own quality gate on 6 files. Phase 1 fixed the files; Phases 2-5 address test coverage, architecture, security, and documentation.
- **All dependencies met**: Phase 1 is complete. No external blockers.
- **Effort efficient**: ~7 days for 18 remaining stories, many are small (0.25-0.5 day each).
- **Multiplier effect**: Better test coverage and architecture improvements de-risk all future epic work.

### Recommended Story Order

#### Phase 2: Test Coverage (~3 days) -- Start immediately

| Priority | Story | LOE | Impact |
|----------|-------|-----|--------|
| 1 | **28d.1**: Create `test_server_pipeline_tools.py` | 1 day | 6 MCP tools with zero tests; highest regression risk |
| 2 | **28d.2**: Create `test_server_scoring_tools.py` | 0.5 day | 3 core scoring tools with zero tests |
| 3 | **28d.3**: Create `test_platform_generators.py` | 1 day | Platform generation is complex; tests prevent regressions |
| 4 | **28a.4/28d.4**: Create `test_voting_engine.py` | 0.5 day | Adaptive system with zero tests |

#### Phase 3: Architecture (~2.5 days) -- After Phase 2

| Priority | Story | LOE | Impact |
|----------|-------|-----|--------|
| 5 | **28b.4**: Reduce `experts/engine.py` complexity | 0.5 day | CC=21 is a maintenance burden |
| 6 | **28b.5**: Reduce `pipeline/init.py` complexity | 0.5 day | CC=19, 2 security findings |
| 7 | **28b.1**: Decouple memory from knowledge/rag_safety | 0.5 day | Architectural improvement |
| 8 | **28b.2**: Create unified feature flags | 0.5 day | Cleans up scattered try/except imports |
| 9 | **28b.3**: Improve singleton cache test safety | 0.5 day | Prevents future test pollution bugs |

#### Phase 4: Security + Lint (~1 day) -- After Phase 3

| Priority | Story | LOE | Impact |
|----------|-------|-----|--------|
| 10 | **28c.1**: Replace try-except-pass (B110) | 0.25 day | 3 silent exception swallowing patterns |
| 11 | **28c.2**: Audit subprocess usage | 0.25 day | Low severity but worth verifying |
| 12 | **28f.1**: Fix checklist lint issues | 0.1 day | Quick win |
| 13 | **28f.2**: Fix pipeline tools lint issues | 0.25 day | Partially overlaps 28a.2 (done) |
| 14 | **28f.3**: Fix server.py ANN401 warnings | 0.1 day | Quick win |

#### Phase 5: Documentation (~0.75 day) -- Final polish

| Priority | Story | LOE | Impact |
|----------|-------|-----|--------|
| 15 | **28e.1**: Update CLAUDE.md module map | 0.25 day | Developer experience |
| 16 | **28e.2**: Verify all tools documented | 0.25 day | Accuracy |
| 17 | **28e.3**: Add .venv exclusion to tapps_report | 0.25 day | Prevents misleading results |

---

## Tier 2: Do Next -- Epic 36 (Hook & Platform Expansion)

### Why second?

- **All dependencies met**: Epics 33, 8, and 18 are all complete.
- **High value, moderate effort**: Expands hook coverage from 7 to 10 events, adds intelligent prompt hooks, and introduces engagement-level enforcement.
- **User-facing improvement**: Consuming projects get better quality enforcement, especially at `high` engagement.
- **Enables Epic 37**: Plugin builder needs the expanded hook set.

### Recommended Story Order

| Priority | Story | Points | LOE | Rationale |
|----------|-------|--------|-----|-----------|
| 1 | **36.5**: Engagement-level blocking hooks | 5 | ~2 days | Core value prop: high engagement enforces quality gates |
| 2 | **36.6**: Engagement-level hook set selection | 2 | ~1 day | Wires 36.5 into init/upgrade; required for all other hooks |
| 3 | **36.1**: SubagentStop quality hook | 3 | ~1 day | Covers subagent workflow gap |
| 4 | **36.2**: SessionEnd summary hook | 3 | ~1 day | Quality summary + optional memory capture |
| 5 | **36.3**: PostToolUseFailure diagnostics | 2 | ~0.5 day | Smallest story; quick diagnostic improvement |
| 6 | **36.4**: Prompt-type quality hook | 5 | ~2 days | Opt-in Haiku-based judgment; save for last (most novel) |

**Rationale for order**: Start with the blocking hook infrastructure (36.5 + 36.6) since it delivers the highest user value and establishes the engagement-level hook framework. Then add the three new event hooks (36.1-36.3) which are straightforward. Save prompt hooks (36.4) for last since they're opt-in and the most complex.

---

## Tier 3: Do Next -- Epic 37 (Pipeline Onboarding & Distribution)

### Why third?

- **Depends on Epic 36**: Plugin builder needs the expanded hook templates from Epic 36.
- **High strategic value**: Plugin packaging targets the 9,000+ Claude Code plugin marketplace, dramatically expanding distribution reach.
- **Improves first-run experience**: Interactive wizard reduces onboarding friction for new users.
- **Safety improvement**: Upgrade rollback prevents configuration loss.

### Recommended Story Order

| Priority | Story | Points | LOE | Rationale |
|----------|-------|--------|-----|-----------|
| 1 | **37.3**: Upgrade rollback mechanism | 5 | ~2 days | Risk reduction; prevents upgrade damage; no dependencies |
| 2 | **37.1**: Interactive first-run wizard | 5 | ~2 days | Onboarding UX improvement; uses existing elicitation |
| 3 | **37.2**: Plugin package builder | 8 | ~3 days | Largest story; strategic importance for distribution |
| 4 | **37.5**: Gate failure weighting | 3 | ~1 day | Quality improvement; thematically misplaced but valuable |
| 5 | **37.4**: Knowledge cache eviction | 3 | ~1 day | QoL improvement; thematically misplaced but valuable |
| 6 | **37.6**: Tests & documentation | 2 | ~1 day | Integration tests across all new features |

**Note on 37.4 and 37.5**: As the epic document itself notes, these stories are thematically misplaced. Consider moving them to a dedicated "Quality of Life" or "Cache & Performance" epic during backlog refinement.

---

## Tier 4: Strategic -- Epic 30 (Benchmark Infrastructure)

### Why fourth?

- **Validates core product hypothesis**: "Do TappsMCP-generated AGENTS.md files help agents?" The answer to this question determines the product's credibility.
- **Foundation for Epics 31-32**: Both optimization epics depend on benchmark infrastructure.
- **High effort**: 3-4 weeks for 7 stories (30 story points total). Requires Docker, HuggingFace datasets, and statistical analysis.
- **Dependency on Epic 28**: Benchmark infrastructure should run against a codebase that passes its own quality gates.

### Recommended Story Order

| Priority | Story | Points | LOE | Rationale |
|----------|-------|--------|-----|-----------|
| 1 | **30.1**: Benchmark models & config | 3 | ~2 days | Foundation: data models and configuration |
| 2 | **30.2**: Dataset loader | 3 | ~2 days | Enables loading AGENTBench data |
| 3 | **30.7**: Fixture dataset & integration tests | 3 | ~2 days | Enables testing without Docker/API access |
| 4 | **30.3**: Context injection engine | 5 | ~3 days | Core mechanism: inject AGENTS.md into repos |
| 5 | **30.5**: Results aggregation & reporting | 5 | ~3 days | Statistical analysis and comparison reports |
| 6 | **30.4**: Docker evaluation runner | 8 | ~5 days | Largest story; requires Docker SDK integration |
| 7 | **30.6**: CLI integration | 3 | ~2 days | Wire everything into CLI commands |

**Rationale for order**: Build data models and loaders first (30.1, 30.2), then create test fixtures (30.7) so everything after can be tested. Context injection (30.3) and reporting (30.5) can be developed and tested with mock data before the Docker runner (30.4) is ready. Docker evaluation (30.4) is the riskiest story -- save it for when all other pieces are in place.

---

## Tier 5: Strategic -- Epic 31 (Template Self-Optimization)

### Why fifth?

- **Depends on Epic 30**: Cannot optimize templates without benchmark data.
- **High strategic value**: Transforms TappsMCP from "generates context files" to "generates *validated* context files."
- **Complex**: 3-4 weeks for 7 stories (31 points). Involves statistical testing, ablation studies, and feedback loops.

### Recommended Story Order

| Priority | Story | Points | LOE | Rationale |
|----------|-------|--------|-----|-----------|
| 1 | **31.1**: Template version tracker | 5 | ~3 days | Foundation: versioning and score tracking |
| 2 | **31.2**: Redundancy analyzer (enhanced) | 5 | ~3 days | Per-section redundancy scoring |
| 3 | **31.6**: Template promotion gate | 3 | ~2 days | Quality gate for template changes |
| 4 | **31.3**: Section ablation runner | 5 | ~3 days | Measures per-section value |
| 5 | **31.4**: Engagement level calibrator | 5 | ~3 days | Data-driven engagement level recommendation |
| 6 | **31.5**: Failure analysis & optimization | 5 | ~3 days | Closes the feedback loop |
| 7 | **31.7**: CLI commands & MCP tool | 3 | ~2 days | Expose everything via CLI |

**Rationale for order**: Build the version tracker (31.1) and redundancy analyzer (31.2) first since they have no benchmark dependencies. Add the promotion gate (31.6) early to establish quality control. Then build the analysis tools (31.3-31.5) that require benchmark runs. CLI (31.7) comes last.

---

## Tier 6: Deferred -- Epic 32 (MCP Tool Effectiveness Benchmarking)

### Why last?

- **Depends on Epic 30**: Needs benchmark infrastructure.
- **P2 priority**: Lower priority than all P1 epics (36, 37, 30, 31).
- **Highest effort**: 3-4 weeks for 7 stories (39 points). Creating 20+ evaluation tasks is labor-intensive.
- **Nice-to-have**: While measuring tool effectiveness is valuable, TappsMCP's tools already have strong adoption signals through 4500+ tests and organic usage patterns.
- **Can run parallel with Epic 31**: Epics 31 and 32 are independent after Epic 30. If resources allow, they can be parallelized.

### Recommended Story Order (when started)

| Priority | Story | Points | Rationale |
|----------|-------|--------|-----------|
| 1 | **32.1**: Tool evaluation task suite | 8 | Foundation: 20+ deterministic tasks |
| 2 | **32.2**: Tool impact evaluator | 8 | Core measurement engine |
| 3 | **32.3**: Call pattern analyzer | 5 | Identifies over/under-calling |
| 4 | **32.4**: Checklist calibrator | 5 | Data-driven tier classification |
| 5 | **32.5**: Expert & memory trackers | 5 | Domain-specific effectiveness |
| 6 | **32.6**: Adaptive weight feedback loop | 5 | Closes the optimization loop |
| 7 | **32.7**: Dashboard integration | 3 | Visibility into tool effectiveness |

---

## Dependency Graph (Open Epics Only)

```
Epic 28 (Phases 2-5)          <- No blockers (Phase 1 complete)
  |
  v
Epic 36 (Hook Expansion)      <- Epic 33 (complete), Epic 8 (complete), Epic 18 (complete)
  |
  v
Epic 37 (Onboarding)          <- Epic 36, Epic 33 (complete), Epic 6 (complete)

Epic 28 (Phases 2-5)
  |
  v
Epic 30 (Benchmark Infra)     <- Epic 8 (complete), Epic 18 (complete), Epic 28
  |
  +---> Epic 31 (Template Optimization)  <- Epic 30, Epic 5 (complete)
  |
  +---> Epic 32 (Tool Effectiveness)     <- Epic 30, Epic 7 (complete)
```

### Critical Path

```
Epic 28 (7d) -> Epic 36 (2.5w) -> Epic 37 (3w) = ~7.5 weeks
Epic 28 (7d) -> Epic 30 (4w) -> Epic 31 (4w) = ~9.5 weeks
                              -> Epic 32 (4w) = ~5.5 weeks (parallel with 31)
```

### Parallelization Opportunities

With 2 developers:
- **Dev A**: Epic 28 (Phases 2-5) -> Epic 36 -> Epic 37
- **Dev B**: Epic 28 (Phases 2-3, shared) -> Epic 30 -> Epic 31

With 1 developer:
- Epic 28 -> Epic 36 -> Epic 37 -> Epic 30 -> Epic 31 -> Epic 32
- Total: ~20-24 weeks sequential

---

## Quick Wins (Can Be Done Anytime)

These stories are small, independent, and deliver immediate value regardless of epic ordering:

| Story | LOE | Value |
|-------|-----|-------|
| 28f.1: Fix checklist lint | 0.1 day | Zero lint in checklist.py |
| 28f.3: Fix server.py ANN401 | 0.1 day | Zero ANN401 warnings |
| 28e.3: Add .venv exclusion | 0.25 day | Accurate report results |
| 28c.2: Audit subprocess usage | 0.25 day | Security verification |
| 37.5: Gate failure weighting | 1 day | Better user feedback on gate failures |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Epic 30 Docker complexity delays | Medium | High | Story 30.7 (fixtures) enables testing without Docker |
| Epic 32 task creation is labor-intensive | High | Medium | Start with 10 tasks, expand incrementally |
| Epic 37 plugin spec changes | Low | Medium | Plugin system is stable (9,000+ plugins exist) |
| Epic 36 prompt hook adoption | Medium | Low | Prompt hooks are opt-in; command hooks are fallback |
| Epic 28 Phase 2 test creation reveals bugs | Medium | Medium | Actually a benefit -- better to find bugs now |

---

## Recommendations

1. **Start Epic 28 Phases 2-5 immediately**. The credibility gap of a quality tool failing its own gates is the highest-priority issue. Phase 2 (test coverage) is the most impactful sub-phase.

2. **Execute Epic 36 as soon as Phase 2 of Epic 28 is complete**. Hook expansion has all dependencies met and delivers direct user value.

3. **Execute Epic 37 after Epic 36**. Plugin packaging is strategically important for distribution and marketplace presence.

4. **Defer Epics 30-32 until the "do now" and "do next" tiers are complete**. Benchmarking is valuable but not urgent -- the product is already shipping with strong test coverage (4500+ tests).

5. **Consider splitting Epic 37**: Stories 37.4 (cache eviction) and 37.5 (gate weighting) are thematically misplaced. Move them to a "Quality of Life" mini-epic or attach them to Epic 28's architecture phase.

6. **Track Epic 31 and 32 parallelization**: If a second developer becomes available after Epic 30, Epics 31 and 32 can run simultaneously since they share no dependencies beyond Epic 30.
