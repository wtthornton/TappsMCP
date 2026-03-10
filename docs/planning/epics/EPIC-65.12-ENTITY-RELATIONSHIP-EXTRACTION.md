# Epic 65.12: Entity/Relationship Extraction in Consolidation (2026 Best Practices)

**Status:** Complete
**Priority:** P2 | **LOE:** 2-2.5 weeks | **Source:** [EPIC-65-MEMORY-2026-BEST-PRACTICES](../EPIC-65-MEMORY-2026-BEST-PRACTICES.md)
**Dependencies:** Epic 58 (consolidation)

## Problem Statement

Cognee and Mem0 Graph Memory store entities and relationships. TappMCP consolidation merges similar entries but has no explicit relationships. "Sarah manages backend" and "backend owns API" → "who handles API?" should resolve to Sarah. This epic adds optional entity/relationship extraction during consolidation.

**Reference:** Cognee entity extraction, Mem0 Graph Memory

## Stories

### Story 65.12.1: RelationEntry model

**Files:** `packages/tapps-core/src/tapps_core/memory/models.py`

1. Add `RelationEntry` or extend MemoryEntry:
   - `subject: str`, `predicate: str`, `object: str` (e.g., "Sarah", "manages", "backend")
   - `source_entry_keys: list[str]` (provenance)
   - `confidence: float`
2. Store in memory DB or separate `relations` table
3. Config: `memory.relations.enabled` (default: false)

**Acceptance criteria:**
- RelationEntry or equivalent model
- Persistence for relations

### Story 65.12.2: Rule-based entity/relationship extraction

**Files:** `packages/tapps-core/src/tapps_core/memory/relations.py` (new)

1. Add `extract_relations(entry: MemoryEntry) -> list[RelationEntry]`:
   - Rule-based: patterns like "X manages Y", "Y owns Z", "X handles Y"
   - Regex or simple NLP (spaCy optional)
   - Deterministic; no LLM
2. Call during consolidation when `memory.relations.enabled`
3. Store extracted relations
4. Limit: max 5 relations per entry

**Acceptance criteria:**
- extract_relations returns RelationEntry list
- Deterministic
- Pattern coverage for common relations (manages, owns, handles)

### Story 65.12.3: Integration with consolidation

**Files:** `packages/tapps-core/src/tapps_core/memory/consolidation.py`

1. After consolidating entries, call extract_relations on consolidated value
2. Persist relations with source_entry_keys pointing to consolidated + sources
3. Optional: merge relations when consolidating (deduplicate subject-predicate-object)

**Acceptance criteria:**
- Consolidation triggers relation extraction when enabled
- Relations persisted
- Provenance tracked

## Testing

- Unit: extract_relations correctness on sample text
- Integration: consolidation → relations stored
