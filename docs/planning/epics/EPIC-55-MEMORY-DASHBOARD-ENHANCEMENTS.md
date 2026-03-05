# Epic 55: Memory & Dashboard Enhancements

**Priority:** P3 | **LOE:** ~3-4 days | **Source:** Consumer feedback v2 (ENH-6, ENH-7)

## Problem Statement

Two quality-of-life improvements for the memory subsystem and dashboard:

1. **Bulk memory save** (ENH-6): Seeding multiple memories requires N separate `tapps_memory(action="save")` calls. While each call is fast (~15ms), the overhead of N sequential MCP round-trips is significant in agent context (13 memories = 13 MCP calls).

2. **Memory stats in dashboard** (ENH-7): `tapps_dashboard` shows tool usage, alerts, and coverage metrics but has no memory section. Memory is a core subsystem but invisible in the dashboard. Users can't see total entries, tier breakdown, stale count, or decay patterns without calling `tapps_memory(action="list")` separately.

## Stories

### Story 55.1: Bulk memory save action

**Files:** `server_memory_tools.py`, `memory/store.py`

1. Add `save_bulk` to `_VALID_ACTIONS` in `server_memory_tools.py`
2. Accept a new `entries` parameter (JSON string of array):
   ```python
   entries: str = ""  # JSON array of {key, value, tier?, tags?, scope?} objects
   ```
3. Parse entries, validate each, and call `store.save()` in a loop
4. Return summary: `{"saved": N, "skipped": M, "errors": [...]}`
5. Each entry inherits defaults from the top-level parameters (tier, scope, source) unless overridden
6. Cap at 50 entries per call to prevent abuse
7. Transactional: all-or-nothing within a single SQLite transaction

**Acceptance criteria:**
- `tapps_memory(action="save_bulk", entries='[{"key":"a","value":"b"},...]')` saves all entries
- Errors in individual entries don't block others (partial success with error list)
- Cap of 50 entries enforced with clear error message
- 13 memories saved in 1 MCP call instead of 13

### Story 55.2: Memory metrics in dashboard

**Files:** `metrics/dashboard.py`, `server_metrics_tools.py`

1. Add `memory_metrics` section to dashboard:
   ```python
   {
     "memory_metrics": {
       "total_entries": 42,
       "by_tier": {"architectural": 5, "pattern": 30, "context": 7},
       "by_scope": {"project": 38, "branch": 3, "session": 1},
       "stale_count": 3,
       "avg_confidence": 0.72,
       "last_gc": "2026-03-01T10:00:00Z",
       "storage_size_kb": 156,
       "capacity_pct": 8.4
     }
   }
   ```
2. Add `"memory_metrics"` to the valid sections list in `tapps_dashboard`
3. Collect stats from `MemoryStore` (count, tier breakdown, stale entries, confidence distribution)
4. Include in default dashboard output (no extra opt-in needed)
5. Add memory capacity warning to dashboard alerts when usage > 80%

**Acceptance criteria:**
- `tapps_dashboard` includes memory_metrics section by default
- All listed fields are populated from live MemoryStore data
- Dashboard alerts include memory capacity warnings
- Memory section appears in both JSON and markdown output formats

### Story 55.3: Memory stats in session_start

**Files:** `server_pipeline_tools.py`

1. Enrich the existing `memory_status` in `tapps_session_start` response with:
   - `by_tier` breakdown
   - `avg_confidence`
   - `capacity_pct` (current entries / max_memories)
2. Keep backward-compatible (add fields, don't remove existing ones)

**Acceptance criteria:**
- `tapps_session_start` response includes enriched memory stats
- Existing fields (enabled, total, stale, contradicted) unchanged
- New fields added alongside existing ones

## Dependencies

- None (memory subsystem and dashboard are mature)

## Testing

- Unit test: save_bulk with valid entries, partial errors, cap exceeded
- Unit test: dashboard memory_metrics section shape and values
- Unit test: session_start enriched memory stats
- Integration test: save_bulk → list verifies all entries saved
