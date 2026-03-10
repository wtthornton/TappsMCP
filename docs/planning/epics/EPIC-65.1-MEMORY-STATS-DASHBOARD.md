# Epic 65.1: Memory Stats in Dashboard (2026 Best Practices)

**Status:** Proposed
**Priority:** P1 | **LOE:** 3-5 days | **Source:** [EPIC-65-MEMORY-2026-BEST-PRACTICES](../EPIC-65-MEMORY-2026-BEST-PRACTICES.md)
**Dependencies:** Epic 23, 55 (memory foundation, dashboard enhancements — both complete)

## Problem Statement

Epic 55 added basic `memory_metrics` to `tapps_dashboard`. This epic extends it with 2026 observability best practices:

- **Consolidation stats** — Entries consolidated, provenance count (Epic 58)
- **Federation stats** — Cross-project memory sharing status (Epic 64)
- **Enriched tier/confidence breakdown** — Align with Zylos/Neuronex "scoped retrieval" observability

## Stories

### Story 65.1.1: Consolidation stats in memory_metrics

**Files:** `packages/tapps-core/src/tapps_core/metrics/dashboard.py`

1. Extend `_build_memory_metrics` to include:
   - `consolidated_count`: Number of consolidated entries
   - `source_entries_count`: Number of source entries (consolidated into others)
   - `consolidation_groups`: Number of consolidation groups
2. Query `MemoryStore` for consolidated entries (entries with `is_consolidated=True` or `contradiction_reason` containing "consolidated into")
3. Add to existing `memory_metrics` section

**Acceptance criteria:**
- `tapps_dashboard` memory_metrics includes `consolidated_count`, `source_entries_count`, `consolidation_groups`
- Values derived from live MemoryStore

### Story 65.1.2: Federation stats in memory_metrics

**Files:** `packages/tapps-core/src/tapps_core/metrics/dashboard.py`, `packages/tapps-core/src/tapps_core/memory/federation.py`

1. Add `federation` subsection to `memory_metrics` (when federation available):
   - `hub_registered`: Whether project is registered
   - `published_count`: Memories published to hub
   - `subscribed_projects`: Count of subscribed projects
   - `synced_count`: Memories synced from hub
2. Use `FederationHub` / `load_federation_config()` if available
3. Graceful fallback when federation not configured (omit or empty)

**Acceptance criteria:**
- `tapps_dashboard` memory_metrics includes optional `federation` object
- No errors when federation not configured

### Story 65.1.3: Memory stats in session_start

**Files:** `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py`

1. Enrich `tapps_session_start` memory_status with consolidation and federation hints when applicable
2. Keep backward-compatible

**Acceptance criteria:**
- `tapps_session_start` response includes consolidation/federation hints
- Existing memory_status fields unchanged

## Testing

- Unit: dashboard memory_metrics shape with consolidation and federation
- Unit: session_start enriched stats
- Integration: dashboard with real MemoryStore containing consolidated entries
