# Post-v2.0.0 Roadmap Assessment

**Date:** 2026-04-07
**Assessed by:** Claude Code (automated dependency analysis)
**Release:** v2.0.0 (commit d651a14)

---

## Executive Summary

After shipping v2.0.0 (expert system removal, tool cleanup, mypy strict zero errors),
a dependency analysis of the planned Phase 4-6 epics reveals that **none are immediately
executable**. Each phase has unresolved prerequisites — missing code, untagged releases,
or references to non-existent infrastructure.

This document catalogs the blockers and recommends a corrected execution order.

---

## v2.0.0 Validation Baseline

| Package | Tests | mypy --strict | ruff |
|---------|-------|---------------|------|
| tapps-core | 959 | Clean | Clean |
| docs-mcp | 2,062 | Clean | Clean |
| tapps-mcp | 3,788 | Clean | Clean |
| **Total** | **6,809** | **350 files** | **Clean** |

---

## Phase 4: DocsMCP Agent Intelligence

### EPIC-11: Memory-Aware Agents

**Location:** `packages/docs-mcp/docs/epics/EPIC-11-memory-aware-agents.md`
**Declared dependencies:** EPIC-2 (hybrid matcher), tapps-brain v2.1+

| Blocker | Status | Resolution |
|---------|--------|------------|
| tapps-brain v2.1+ | Code exists (commit c82937f) but **no git tag** — TappsMCP pins `v2.0.4` | Tag v2.1.0 in tapps-brain, bump pin in `pyproject.toml` |
| EPIC-2 (hybrid matcher) | **No epic doc exists**, no matcher code in docs-mcp | Draft EPIC-2, implement hybrid matcher |
| Files-affected all `*(not found)*` | Epic references `backend/matcher/`, `backend/models/` — paths don't exist in docs-mcp | Remap to actual docs-mcp module paths or acknowledge this is greenfield |
| tapps-brain API readiness | v2.1.0 already has: `agent_scope`, `HiveStore.search()`, `RecallOrchestrator._search_hive()`, group membership | **Ready** once tagged |

**Assessment:** 3 of 6 stories (11.3, 11.6, partially 11.2) can use existing tapps-brain
v2.1.0 APIs. Stories 11.1, 11.4, 11.5 are docs-mcp integration work. The epic is
**actionable once tapps-brain v2.1.0 is tagged and EPIC-2 is resolved**.

### EPIC-12: Agent Catalog Governance

**Location:** `packages/docs-mcp/docs/epics/EPIC-12-catalog-governance.md`
**Declared dependencies:** EPIC-2 (hybrid matcher with embeddings)

| Blocker | Status | Resolution |
|---------|--------|------------|
| EPIC-2 (hybrid matcher) | Same as EPIC-11 — doesn't exist | Must be implemented first |
| Files-affected all `*(not found)*` | References `backend/api/routes/tasks.py`, `backend/matcher/proposer.py` | Same greenfield issue |
| Embedding infrastructure | No embedding model or vector store in docs-mcp | EPIC-2 must establish this |

**Assessment:** Entirely blocked by EPIC-2. All 5 stories depend on embedding similarity
scoring that doesn't exist yet.

---

## Phase 5: UI & Testing Infrastructure

### EPIC-58: Playwright Test Infrastructure

**Location:** `docs/epics/epic-58-playwright-test-infrastructure.md`
**Declared dependencies:** Epic 12 (original Playwright test rig) — **namespace collision**
with docs-mcp EPIC-12

| Blocker | Status | Resolution |
|---------|--------|------------|
| Style guide missing | `docs/design/07-THESTUDIO-UI-UX-STYLE-GUIDE.md` does not exist | Create or source the style guide |
| No Admin UI to test | No HTMX templates, no web frontend in TappsMCP or docs-mcp | EPIC-75 builds the UI, but EPIC-58 tests it — circular |
| "TheStudio" context | Epic references "48 packages, 789 modules" — not this repo | Epic was generated for a different project context |
| `tests/playwright/` empty | No existing Playwright test files | Greenfield, but needs a UI target |
| brain-visual dashboard | tapps-brain has a static HTML dashboard at `examples/brain-visual/` | Could be the test target, but epic doesn't reference it |

**Assessment:** Not actionable against this repo. The epic describes testing infrastructure
for an Admin UI that doesn't exist here. The only existing UI is tapps-brain's static
`brain-visual` dashboard. **Needs complete rethink** — either:
- Retarget to test brain-visual dashboard
- Defer until EPIC-75 (Admin UI) is built
- Move to a consuming project where the Admin UI lives

### EPIC-75: Plane-Parity Admin UI

**Location:** `docs/epics/epic-75-plane-parity-admin-ui.md`
**Declared dependencies:** EPIC-58

**Assessment:** Blocked by EPIC-58. Also unclear which project this UI is for.

---

## Phase 6: Infrastructure

### EPIC-86: Zeek Telemetry

**Location:** `stories/epic-86-zeek-telemetry-capture-health.md`
**Assessment:** Independent domain. No Zeek code in this repo. Schedule when Zeek work
is prioritized.

---

## Corrected Execution Order

### Immediate (no blockers)

1. **Tag tapps-brain v2.1.0** — Code exists at commit c82937f, just needs `git tag v2.1.0`
   and push. Then bump `pyproject.toml` pin from `v2.0.4` to `v2.1.0`.

2. **Post-release hygiene** — Commit untracked documentation files, verify 6,809 tests
   still pass.

### Short-term (after tagging)

3. **EPIC-2: Hybrid Matcher** — New epic needed for docs-mcp. Establishes embedding-based
   agent matching infrastructure. Unblocks both EPIC-11 and EPIC-12. See
   `packages/docs-mcp/docs/epics/EPIC-2-hybrid-matcher.md` (to be created).

### Medium-term (after EPIC-2)

4. **EPIC-11: Memory-Aware Agents** — tapps-brain integration into agent execution.
   Files-affected section needs correction to actual docs-mcp paths.

5. **EPIC-12: Catalog Governance** — Deduplication and lifecycle management.

### Deferred (needs clarification)

6. **EPIC-58/75** — Retarget to brain-visual dashboard, or defer until a web UI exists.

7. **EPIC-86** — Schedule with Zeek work.

---

## tapps-brain v2.1.0 API Availability

Features EPIC-11 needs that **already exist** in tapps-brain v2.1.0:

| Feature | Module | Method |
|---------|--------|--------|
| Agent scope parameter | `store.py` | `MemoryStore.save(agent_scope="domain")` |
| Hive search | `hive.py` | `HiveStore.search()`, `search_with_groups()` |
| Hive recall in orchestrator | `recall.py` | `RecallOrchestrator._search_hive()` |
| Agent scope validation | `agent_scope.py` | `normalize_agent_scope()` |
| Group membership | `hive.py` | `get_agent_groups()`, `create_group()` |
| Profile/promotion | `profile.py`, `promotion.py` | `MemoryProfile`, `PromotionEngine` |
| Namespace listing | `hive.py` | `list_namespaces()` |

**Gap:** docs-mcp integration layer (preamble template, AgentConfig.memory_profile,
identity injection, catalog publisher). These are docs-mcp work, not tapps-brain work.

---

## Epic Quality Issues

Both EPIC-11 and EPIC-12 have "Files Affected" sections where every file shows
`*(not found)*`. These reference a `backend/` directory structure that doesn't exist
in docs-mcp. The epics were likely generated from a template that assumed a different
project layout. The files-affected sections should be corrected to reference actual
docs-mcp paths (which are greenfield — the modules don't exist yet and need to be created).

EPIC-58 references "TheStudio" style guide and "48 packages, 789 modules" which don't
match TappsMCP (3 packages). The epic was generated with incorrect project context.
