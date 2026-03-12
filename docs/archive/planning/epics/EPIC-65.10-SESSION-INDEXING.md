# Epic 65.10: Session Indexing (2026 Best Practices)

**Status:** Complete
**Priority:** P2 | **LOE:** 1.5-2 weeks | **Source:** [EPIC-65-MEMORY-2026-BEST-PRACTICES](../EPIC-65-MEMORY-2026-BEST-PRACTICES.md)
**Dependencies:** Epic 23, 25, 34 (memory, retrieval)

## Problem Statement

By default, agents can only search explicit memory entries, not past conversations. OpenClaw's session indexing makes past conversations searchable. Trade-off: more coverage, more noise. Flush prompt quality becomes critical.

**Reference:** OpenClaw session indexing

## Stories

### Story 65.10.1: Session index storage

**Files:** `packages/tapps-core/src/tapps_core/memory/session_index.py` (new), `persistence.py`

1. Add session index table:
   - `session_id`, `chunk_index`, `content`, `created_at`, `embedding` (optional)
   - Or use MemoryEntry with `scope=session_index` and `branch=session_id`
2. Store session chunks (summaries or key facts per turn/day)
3. FTS5 index for text search; optional embeddings when semantic enabled
4. Config: `memory.session_index.enabled` (default: false)

**Acceptance criteria:**
- Session chunks persist and searchable
- Scope/tier distinguishes from main memory

### Story 65.10.2: Session index ingestion

**Files:** `packages/tapps-core/src/tapps_core/memory/session_index.py`

1. Add `index_session(session_id: str, chunks: list[str])`:
   - Called by auto-capture hook or manual `tapps_memory(action="index_session", ...)`
   - Chunks: summaries or key facts (extracted by rule or from context)
2. Limit: max 50 chunks per session; max 500 chars per chunk
3. TTL: optional expiry (e.g., 7 days) for session_index entries

**Acceptance criteria:**
- index_session stores chunks
- TTL optional

### Story 65.10.3: Search across memory + session index

**Files:** `packages/tapps-core/src/tapps_core/memory/retrieval.py`

1. Extend `search()` with `include_session_index: bool` (default: false)
2. When true: search memory entries + session index; merge and deduplicate
3. Result includes `source: "memory" | "session_index"` per hit
4. Filter: `include_sources`-style for session_index hits

**Acceptance criteria:**
- Search returns memory + session index when enabled
- Source distinguished
- Document trade-off: coverage vs noise

## Testing

- Unit: session index storage and retrieval
- Integration: search with include_session_index
