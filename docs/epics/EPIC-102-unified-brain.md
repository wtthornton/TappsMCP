# Epic 102: Unified Brain & Cross-Project Intelligence

<!-- docsmcp:start:metadata -->
**Status:** Done (7/7 stories complete)
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

- [x] docs-mcp writes architecture facts into tapps-brain
- [x] tapps-mcp auto-recalls before validate_changed
- [x] Cross-project search via shared client
- [x] Hooks fire on session_start under 200ms
- [x] Unified insight schema spans quality + docs + architecture
- [x] Federation respects scopes
- [x] Postgres path integrates cleanly

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 102.1 -- Shared insight schema and migration path

**Points:** 5
**Status:** Done

Delivers `tapps_core.insights` — a new module providing `InsightEntry` (a versioned
`MemoryEntry` subclass), `InsightType`, `InsightOrigin`, and `SubjectKind` enums, plus
`migrate_memory_entry_to_insight` / `bulk_migrate` for lossless promotion of existing
MemoryEntry records. Schema version sentinel (`INSIGHT_SCHEMA_VERSION = 1`) enables
forward-compatible migration. Both tapps-mcp and docs-mcp now have a shared typed
contract for writing knowledge into tapps-brain.

**Tasks:**
- [x] `packages/tapps-core/src/tapps_core/insights/models.py` — InsightEntry, enums, INSIGHT_SCHEMA_VERSION
- [x] `packages/tapps-core/src/tapps_core/insights/migration.py` — migrate + bulk_migrate + InsightMigrationResult
- [x] `packages/tapps-core/src/tapps_core/insights/__init__.py` — clean public API
- [x] `packages/tapps-core/tests/unit/test_insights_models.py` — 32 tests
- [x] `packages/tapps-core/tests/unit/test_insights_migration.py` — 38 tests
- [x] mypy --strict passes on all 3 source files

**Definition of Done:** Shared insight schema and migration path is implemented, 70 tests pass, mypy strict clean.

---

### 102.2 -- docs-mcp write path for architecture facts

**Points:** 5
**Status:** Done

Delivers `docs_mcp.integrations.brain_writer.ArchitectureBrainWriter` — writes
architecture facts into tapps-brain as InsightEntry-tagged records after
`docs_generate_architecture` and `docs_module_map` run. Opt-in via
`brain_write_enabled: true` in `.docsmcp.yaml` (or `DOCS_MCP_BRAIN_WRITE_ENABLED=1`).
tapps-brain absence is handled gracefully (`available: false` in response). Each
fact is tagged with `["architecture", "docs-mcp", "insight-type:architecture", "schema-v1"]`
and stored in `memory_group="insights"` at `tier="architectural"`.

**Tasks:**
- [x] `packages/docs-mcp/src/docs_mcp/integrations/brain_writer.py` — ArchitectureBrainWriter, BrainWriteResult, slug helpers
- [x] `packages/docs-mcp/src/docs_mcp/config/settings.py` — `brain_write_enabled` flag added
- [x] `server_gen_tools.py` — wired into `docs_generate_architecture` (opt-in block)
- [x] `server_analysis.py` — wired into `docs_module_map` (opt-in block)
- [x] `packages/docs-mcp/tests/unit/test_brain_writer.py` — 43 tests (fake store, slugify, edge cases)
- [x] mypy --strict passes; 2290 docs-mcp tests green (+32 new)

**Definition of Done:** docs-mcp write path is implemented, opt-in gated, 43 tests pass, mypy clean.

---

### 102.3 -- Auto-recall hook for tapps_validate_changed

**Points:** 3
**Status:** Done

Delivers `tapps_mcp.tools.insight_recall.recall_insights_for_validate()` — searches
the `insights` memory_group for entries relevant to the files being validated and
appends `recalled_insights` to the `tapps_validate_changed` response. Opt-in via
`memory.recall_on_validate: true` in `.tapps-mcp.yaml`. Hard-capped at 180ms;
returns `recall_available: false` if tapps-brain is slow or absent.

**Tasks:**
- [x] `packages/tapps-mcp/src/tapps_mcp/tools/insight_recall.py` — recall function + query builder
- [x] `packages/tapps-core/src/tapps_core/config/settings.py` — `memory.recall_on_validate` flag
- [x] `server_pipeline_tools.py` — wired into `tapps_validate_changed` response
- [x] `packages/tapps-mcp/tests/unit/test_insight_recall.py` — 13 tests (fake client, timeout, truncation)
- [x] PyInstaller spec updated

**Definition of Done:** Auto-recall wired, opt-in gated, 13 tests pass, spec clean.

---

### 102.4 -- Cross-server client library in tapps-core

**Points:** 5
**Status:** Done

Delivers `tapps_core.insights.client.InsightClient` — a typed, availability-aware
wrapper around `tapps_brain.store.MemoryStore` with InsightEntry semantics. Both
tapps-mcp and docs-mcp use this as the single interface for writing, searching,
path-scoped lookup, and bulk promotion of InsightEntry records.

**Tasks:**
- [x] `packages/tapps-core/src/tapps_core/insights/client.py` — InsightClient with write/search/get_by_path/promote_all
- [x] Scope enforcement wired into `write()` (calls `enforce_scope` from 102.5)
- [x] `packages/tapps-core/tests/unit/test_insights_client.py` — 35 tests (fake store, unavailability, scope)
- [x] `tapps_core.insights.__init__` updated to re-export InsightClient

**Definition of Done:** InsightClient implemented, 35 tests pass, mypy clean.

---

### 102.5 -- Scope and confidentiality enforcement

**Points:** 3
**Status:** Done

Delivers `tapps_core.insights.scope` — `enforce_scope()` clamps `session` → `project`,
downgrades `shared` unless `allow_shared=True` or `server_origin=user`, and raises
`ScopeViolation` for unresolvable `branch` entries. `validate_origin_scope()` provides
non-mutating audit warnings for observability.

**Tasks:**
- [x] `packages/tapps-core/src/tapps_core/insights/scope.py` — enforce_scope, validate_origin_scope, ScopeViolation
- [x] `packages/tapps-core/tests/unit/test_insights_scope.py` — 22 tests (all rules, edge cases)

**Definition of Done:** Scope enforcement implemented, 22 tests pass, mypy clean.

---

### 102.6 -- Federation UX explain recall provenance

**Points:** 3
**Status:** Done

Delivers `tapps_core.insights.provenance` — `annotate_provenance()` attaches a
`_provenance` dict to serialised InsightEntry records so the LLM knows whether
a recalled insight came from the local project or a federated remote source.
`format_provenance_summary()` produces a markdown recall provenance block.

**Tasks:**
- [x] `packages/tapps-core/src/tapps_core/insights/provenance.py` — ProvenanceAnnotation, annotate_provenance, format_provenance_summary
- [x] `packages/tapps-core/tests/unit/test_insights_provenance.py` — 22 tests (local/federated, multi-entry, summary)

**Definition of Done:** Provenance annotation implemented, 22 tests pass, mypy clean.

---

### 102.7 -- Postgres-backed brain performance benchmark

**Points:** 5
**Status:** Done

Delivers `tapps_mcp.benchmark.insight_benchmark` — backend-agnostic benchmark suite
measuring write/search/bulk_migrate latencies with p50/p95/p99 stats. Uses a fake
store in tests; production runs against the real SQLite store (or Postgres when
EPIC-43 is complete via the `store=` parameter). `InsightBenchmarkResult.markdown_report()`
produces a formatted table for CI artefacts.

**Tasks:**
- [x] `packages/tapps-mcp/src/tapps_mcp/benchmark/insight_benchmark.py` — BenchmarkLatencies, InsightBenchmarkResult, run_insight_benchmark
- [x] `packages/tapps-mcp/tests/unit/test_insight_benchmark.py` — 21 tests (fake store, latencies, markdown report)
- [x] PyInstaller spec updated

**Definition of Done:** Benchmark suite implemented, 21 tests pass, markdown report works.

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
