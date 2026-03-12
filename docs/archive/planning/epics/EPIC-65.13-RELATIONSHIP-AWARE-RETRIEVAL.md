# Epic 65.13: Relationship-Aware Retrieval (2026 Best Practices)

**Status:** Complete
**Priority:** P2 | **LOE:** 1-1.5 weeks | **Source:** [EPIC-65-MEMORY-2026-BEST-PRACTICES](../EPIC-65-MEMORY-2026-BEST-PRACTICES.md)
**Dependencies:** Epic 65.12 (entity/relationship extraction)

## Problem Statement

Query "who handles API?" → BM25/hybrid finds "backend owns API" and "Sarah manages backend" but cannot connect them. Relationship-aware retrieval traverses relations: API → backend → Sarah. This epic adds optional relation traversal for "who/what handles X" queries.

**Reference:** Cognee relationship retrieval, Mem0 graph traversal

## Stories

### Story 65.13.1: Relation query expansion

**Files:** `packages/tapps-core/src/tapps_core/memory/relations.py`

1. Add `expand_via_relations(query: str, relations: list[RelationEntry]) -> list[str]`:
   - Detect "who handles X", "who owns X", "who manages X"
   - Find relations: X → Y; Y → Z; return Z (or chain)
   - Return expanded query terms: ["API", "backend", "Sarah"]
2. Use expanded terms in BM25/hybrid search
3. Config: `memory.relations.expand_queries` (default: true when relations enabled)

**Acceptance criteria:**
- expand_via_relations returns related terms
- Handles 1-hop and 2-hop (API → backend → Sarah)

### Story 65.13.2: Retrieval integration

**Files:** `packages/tapps-core/src/tapps_core/memory/retrieval.py`

1. When relations enabled and query matches pattern:
   - Load relations for project
   - Expand query via relations
   - Run hybrid/BM25 with expanded terms
   - Optionally boost entries containing related entities
2. Fallback: standard search when no relations or no match

**Acceptance criteria:**
- Search uses relation expansion when applicable
- "who handles API?" returns Sarah-related memories

### Story 65.13.3: tapps_memory support

**Files:** `packages/tapps-mcp/src/tapps_mcp/server_memory_tools.py`

1. Add optional param `expand_relations: bool` (default: true when enabled) to search
2. Document: use for "who/what handles X" queries

**Acceptance criteria:**
- tapps_memory search supports expand_relations
- AGENTS.md updated

## Testing

- Unit: expand_via_relations correctness
- Integration: search "who handles API?" returns expected
