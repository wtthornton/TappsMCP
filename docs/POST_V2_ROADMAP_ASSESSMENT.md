# Post-v2.0.0 Roadmap Assessment

**Date:** 2026-04-07 (revised)
**Assessed by:** Claude Code (automated dependency analysis)
**Release:** v2.0.0 (commit d651a14)

---

## Executive Summary

After shipping v2.0.0 (expert system removal, tool cleanup, mypy strict zero errors),
a dependency analysis of the planned epics revealed that several were obsolete (already
completed by v2.0.0), misplaced (belong in AgentForge, not this repo), or blocked by
missing prerequisites.

This document records actions taken and the current state of the roadmap.

---

## v2.0.0 Validation Baseline

| Package | Tests | mypy --strict | ruff |
|---------|-------|---------------|------|
| tapps-core | 959 | Clean | Clean |
| docs-mcp | 2,130 | Clean | Clean |
| tapps-mcp | 3,788 | Clean | Clean |
| **Total** | **6,877** | **356 files** | **Clean** |

---

## Actions Taken (2026-04-07)

### Completed

| Action | Commit | Details |
|--------|--------|---------|
| Tagged tapps-brain v2.1.0 | pushed to origin | `git tag v2.1.0 c82937f` — was release commit without tag |
| Bumped tapps-brain pin | `86e75a3` | v2.0.4 -> v2.1.0 in pyproject.toml |
| EPIC-2: Hybrid Matcher | `86e75a3` | 5 stories implemented — AgentConfig, keyword matcher, embedding backend, HybridMatcher, 68 tests |

### Epics Removed or Closed

| Epic | Action | Reason |
|------|--------|--------|
| **EPIC-11** (Memory-Aware Agents) | **Deleted** | Belongs in AgentForge, not docs-mcp. References `backend/` paths, `compose_system_prompt`, agent execution loop — none of which exist here. |
| **EPIC-94** (Expert Extraction) | **Closed as superseded** | Expert system was fully deleted in v2.0.0 (23 modules, 184 knowledge files). No migration needed. |
| **EPIC-96** (Session/Profiling Dedup) | **Closed as superseded** | Tools it targeted (`tapps_project_profile`, `tapps_get_canonical_persona`, `tapps_research`) were deleted in v2.0.0. |

### Epics Updated

| Epic | Change |
|------|--------|
| **EPIC-12** (Catalog Governance) | Corrected files-affected from phantom `backend/` paths to actual docs-mcp paths. Dependency on EPIC-2 now resolved. |
| **EPIC-58** (Playwright Test Infra) | Marked **Blocked** — references TheStudio style guide and Admin UI that don't exist in this repo. |
| **EPIC-95** (Memory Extraction) | Status updated to **Partially blocked** — tapps-brain dependency resolved, but still requires AgentForge EPIC-14 coordination. |

---

## Current Epic Status

### Actionable

| Epic | Location | Status | Next step |
|------|----------|--------|-----------|
| **EPIC-2** | `packages/docs-mcp/docs/epics/EPIC-2-hybrid-matcher.md` | **Implemented** | Done — 68 tests pass |
| **EPIC-12** | `packages/docs-mcp/docs/epics/EPIC-12-catalog-governance.md` | **Unblocked** | Ready to implement — HybridMatcher + pairwise_similarity available |

### Blocked

| Epic | Location | Blocker |
|------|----------|---------|
| **EPIC-95** | `docs/epics/EPIC-95-memory-extraction.md` | AgentForge EPIC-14 (coordinated migration) |
| **EPIC-58** | `docs/epics/epic-58-playwright-test-infrastructure.md` | No Admin UI exists in this repo; TheStudio context mismatch |
| **EPIC-75** | `docs/epics/epic-75-plane-parity-admin-ui.md` | Depends on EPIC-58 |

### Closed / Obsolete

| Epic | Location | Reason |
|------|----------|--------|
| **EPIC-11** | deleted | Belongs in AgentForge repo |
| **EPIC-93** | `docs/epics/EPIC-93-full-code-review-and-fixes.md` | Completed in v2.0.0 |
| **EPIC-94** | `docs/epics/EPIC-94-expert-extraction.md` | Superseded by v2.0.0 expert deletion |
| **EPIC-96** | `docs/epics/EPIC-96-session-profiling-dedup.md` | Superseded by v2.0.0 tool cleanup |

### Independent / Deferred

| Epic | Location | Notes |
|------|----------|-------|
| **EPIC-86** | `stories/epic-86-zeek-telemetry-capture-health.md` | Different domain (Zeek). Schedule when Zeek work is prioritized. |
| **EPIC-91** | `docs/epics/EPIC-91-epic-generator-quality-gaps.md` | DocsMCP generator improvements |
| **EPIC-92** | `docs/epics/EPIC-92-story-generator-quality-gaps.md` | DocsMCP generator improvements |

---

## Recommended Next Steps

1. **EPIC-12: Catalog Governance** — Now unblocked. Embedding dedup gate, capability
   merge suggestions, catalog health, agent lifecycle, proposer overlap guard.

2. **EPIC-91/92: Generator Quality** — Independent DocsMCP improvements. No external
   dependencies.

3. **EPIC-95: Memory Extraction** — Wait for AgentForge EPIC-14 coordination.

4. **EPIC-58/75: UI & Testing** — Needs a decision on which UI to target (brain-visual
   dashboard, or defer until an Admin UI is built).
