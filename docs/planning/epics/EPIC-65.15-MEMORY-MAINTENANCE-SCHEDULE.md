# Epic 65.15: Memory Maintenance Schedule (2026 Best Practices)

**Status:** Proposed
**Priority:** P2 | **LOE:** 3-5 days | **Source:** [EPIC-65-MEMORY-2026-BEST-PRACTICES](../EPIC-65-MEMORY-2026-BEST-PRACTICES.md)
**Dependencies:** Epic 23, 24, 58 (memory, gc, consolidation)

## Problem Statement

JoelClaw/Zylos: "Nightly maintenance: deduplication, consolidation, pruning." TappMCP has gc and auto-consolidation. This epic formalizes a maintenance schedule and adds `tapps_memory(action="maintain")` or triggers in `tapps_session_start` when idle.

**Reference:** JoelClaw observation pipeline, Zylos memory maintenance

## Stories

### Story 65.15.1: maintain action

**Files:** `packages/tapps-mcp/src/tapps_mcp/server_memory_tools.py`

1. Add `tapps_memory(action="maintain")`:
   - Run gc (archive decayed entries)
   - Run auto-consolidation scan (Epic 58)
   - Optionally: deduplication (merge exact duplicates)
   - Return summary: `{gc_archived, consolidated, deduplicated}`
2. Add to `_VALID_ACTIONS` and dispatch

**Acceptance criteria:**
- tapps_memory(action="maintain") runs gc + consolidation
- Returns summary
- Idempotent

### Story 65.15.2: Optional maintain on session_start

**Files:** `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py`

1. Config: `memory.maintenance.on_session_start: bool` (default: false)
2. When true and memory > 80% capacity: run maintain before returning session_start
3. Or: run maintain only when `last_maintain` > 24h (avoid every session)
4. Config: `memory.maintenance.interval_hours: 24`

**Acceptance criteria:**
- Optional auto-maintain on session_start
- Configurable interval

### Story 65.15.3: Documentation

**Files:** AGENTS.md, docs

1. Document maintain action
2. Document maintenance schedule best practices (nightly/weekly)
3. CLI: `tapps-mcp memory maintain` (if CLI parity)

**Acceptance criteria:**
- AGENTS.md includes maintain
- Best practices documented
