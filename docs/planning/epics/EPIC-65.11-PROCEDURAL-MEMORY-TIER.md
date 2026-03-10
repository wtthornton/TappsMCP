# Epic 65.11: Procedural Memory Tier (2026 Best Practices)

**Status:** Complete
**Priority:** P2 | **LOE:** 1 week | **Source:** [EPIC-65-MEMORY-2026-BEST-PRACTICES](../EPIC-65-MEMORY-2026-BEST-PRACTICES.md)
**Dependencies:** Epic 23, 24, 25, 58 (memory, decay, retrieval, consolidation)

## Problem Statement

Zylos/Neuronex: three memory types—episodic (what happened when), semantic (what I know), procedural (how to do). TappMCP has architectural/pattern/context (semantic/episodic). Add procedural tier for workflows, steps, and few-shot patterns.

**Reference:** Zylos procedural templates, Neuronex "how to do"

## Stories

### Story 65.11.1: MemoryTier.procedural

**Files:** `packages/tapps-core/src/tapps_core/memory/models.py`

1. Add `MemoryTier.procedural = "procedural"` (how to do; workflows, steps)
2. Update validators, serialization, FTS5
3. Migration: existing entries unchanged; new tier valid for save

**Acceptance criteria:**
- MemoryTier.procedural exists
- Save accepts tier="procedural"
- Backward compatible

### Story 65.11.2: Decay config for procedural

**Files:** `packages/tapps-core/src/tapps_core/memory/decay.py`

1. Add procedural to `DecayConfig` / tier config:
   - Decay rate: between pattern and context (e.g., 0.08)
   - Half-life: ~14 days
   - min_confidence_to_keep: 0.45
2. Procedural entries decay; gc exempt days: 14

**Acceptance criteria:**
- Decay applied to procedural tier
- Config documented

### Story 65.11.3: Consolidation and list/search

**Files:** `packages/tapps-core/src/tapps_core/memory/consolidation.py`, `retrieval.py`, `store.py`

1. Consolidation can produce procedural templates (merge related steps)
2. `list(tier="procedural")`, `search` with tier filter includes procedural
3. Default tier counts in dashboard include procedural

**Acceptance criteria:**
- Procedural in consolidation and retrieval
- Dashboard shows procedural count

## Testing

- Unit: procedural tier save, list, search, decay
- Unit: consolidation with procedural entries
