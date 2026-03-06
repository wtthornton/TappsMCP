# Epic 58: Memory Consolidation

**Status:** Proposed
**Priority:** P2 — Important (prevents context bloat, improves retrieval quality)
**Estimated LOE:** ~2 weeks (1 developer)
**Dependencies:** Epic 23-25, Epic 34 (Memory Foundation/Intelligence/Retrieval) — Complete

---

## Problem Statement

The TappsMCP memory system (`tapps_memory`) stores individual entries that accumulate over time. As projects evolve, related memories fragment across many entries:

- Multiple decisions about the same architectural component
- Incremental learnings about a library's quirks
- Repeated patterns that could be consolidated into a single "rule"

This fragmentation causes:
1. **Context bloat** — More tokens consumed when injecting memory context
2. **Retrieval noise** — Multiple similar results instead of one authoritative answer
3. **Stale accumulation** — Old entries persist even when superseded

Leading memory systems (e.g., mcp-memory-service) address this with auto-consolidation.

---

## Goals

1. Automatically detect related memories that can be consolidated
2. Merge related memories into summary entries with provenance tracking
3. Preserve original entries as "sources" while surfacing consolidated view
4. Provide manual consolidation controls via `tapps_memory` tool

## Non-Goals

- Changing the memory storage schema fundamentally
- LLM-based summarization (this epic uses deterministic consolidation)
- Cross-project memory federation (separate epic)

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Memory count reduction for mature projects (100+ entries) | 30-50% |
| Retrieval result deduplication | 80%+ reduction in near-duplicate results |
| Consolidation false positives | < 5% (measured by user undo rate) |
| Test coverage | 80%+ for new modules |

---

## Technical Approach

### Consolidation Triggers

1. **Similarity threshold** — Entries with Jaccard similarity > 0.7 on tags + key terms
2. **Same-topic clustering** — Entries with identical `tier` and overlapping `tags`
3. **Supersession detection** — Newer entry explicitly references older entry's key
4. **Manual trigger** — User calls `tapps_memory(action="consolidate", ...)`

### Consolidation Algorithm

```python
def consolidate(entries: list[MemoryEntry]) -> ConsolidatedEntry:
    # 1. Extract common tags (intersection)
    common_tags = set.intersection(*[set(e.tags) for e in entries])
    
    # 2. Merge values (newest takes precedence for conflicts)
    merged_value = merge_values([e.value for e in sorted(entries, key=lambda x: x.updated_at)])
    
    # 3. Compute confidence (weighted average by recency)
    confidence = weighted_average([e.confidence for e in entries], weights=recency_weights)
    
    # 4. Track provenance
    source_ids = [e.id for e in entries]
    
    return ConsolidatedEntry(
        key=generate_consolidated_key(entries),
        value=merged_value,
        tags=list(common_tags),
        confidence=confidence,
        source_ids=source_ids,
        consolidated_at=datetime.utcnow(),
    )
```

### Storage Model

```python
class ConsolidatedEntry(MemoryEntry):
    source_ids: list[str]  # Original entry IDs that were consolidated
    consolidated_at: datetime
    consolidation_reason: str  # "similarity" | "same_topic" | "supersession" | "manual"
```

Original entries are marked `consolidated: true` but retained for provenance.

---

## Stories

### 58.1 — Similarity Detection

**Points:** 3

Implement similarity detection for memory entries:
- Jaccard similarity on tags
- TF-IDF similarity on key + value text
- Combined score with configurable weights
- `find_similar(entry: MemoryEntry, threshold: float) -> list[MemoryEntry]`

**Acceptance Criteria:**
- [ ] `find_similar` returns entries above threshold
- [ ] Both tag and text similarity considered
- [ ] Configurable threshold (default 0.7)
- [ ] 20+ unit tests

### 58.2 — Consolidation Engine

**Points:** 5

Implement the consolidation logic:
- `consolidate(entries: list[MemoryEntry]) -> ConsolidatedEntry`
- Value merging with newest-wins for conflicts
- Confidence weighted average
- Provenance tracking via `source_ids`

**Acceptance Criteria:**
- [ ] Consolidation produces valid `ConsolidatedEntry`
- [ ] Original entries marked `consolidated: true`
- [ ] Provenance chain traceable
- [ ] 25+ unit tests

### 58.3 — Auto-Consolidation Triggers

**Points:** 3

Add automatic consolidation triggers:
- On `tapps_memory(action="save")` — check for similar existing entries
- On `tapps_session_start` — periodic consolidation scan (if enabled)
- Configurable: `memory_auto_consolidate: true/false`

**Acceptance Criteria:**
- [ ] Auto-consolidation on save when similar entry exists
- [ ] Periodic scan respects configuration
- [ ] Logging shows consolidation decisions
- [ ] 15+ unit tests

### 58.4 — Manual Consolidation Action

**Points:** 2

Add `tapps_memory(action="consolidate", ...)`:
- `entry_ids: list[str]` — specific entries to consolidate
- `query: str` — consolidate search results matching query
- `dry_run: bool` — preview without applying

**Acceptance Criteria:**
- [ ] `action="consolidate"` works with entry_ids
- [ ] `action="consolidate"` works with query
- [ ] `dry_run` returns preview without persisting
- [ ] 10+ unit tests

### 58.5 — Retrieval Deduplication

**Points:** 3

Update retrieval to prefer consolidated entries:
- `tapps_memory(action="search")` returns consolidated entry instead of sources
- `include_sources: bool` parameter to also return source entries
- Consolidated entries ranked higher than fragments

**Acceptance Criteria:**
- [ ] Search returns consolidated entries by default
- [ ] `include_sources=True` returns full provenance
- [ ] Ranking prefers consolidated over fragments
- [ ] 15+ unit tests

### 58.6 — Undo & Provenance

**Points:** 2

Implement undo for consolidation:
- `tapps_memory(action="unconsolidate", entry_id="...")` 
- Restores source entries, removes consolidated entry
- Provenance view: show consolidation history for an entry

**Acceptance Criteria:**
- [ ] Unconsolidate restores original entries
- [ ] Provenance chain viewable
- [ ] 10+ unit tests

### 58.7 — Documentation

**Points:** 1

Update documentation:
- AGENTS.md: Document consolidation behavior
- Memory tool docs: New action and parameters

**Acceptance Criteria:**
- [ ] AGENTS.md mentions auto-consolidation
- [ ] Tool reference updated

---

## Configuration

```yaml
# .tapps-mcp.yaml
memory_auto_consolidate: true          # Enable auto-consolidation
memory_consolidation_threshold: 0.7    # Similarity threshold
memory_consolidation_min_entries: 3    # Minimum entries to trigger
memory_consolidation_scan_interval: 7  # Days between periodic scans
```

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Incorrect consolidation (false positives) | Medium | Medium | Conservative threshold; undo capability; dry_run preview |
| Loss of nuance in merged entries | Medium | Low | Preserve sources; allow unconsolidation |
| Performance impact on large memory stores | Low | Medium | Incremental consolidation; background processing |

---

## Open Questions

1. Should consolidation use LLM for smarter merging, or stay deterministic?
2. Should consolidated entries decay differently than regular entries?
3. Should there be a maximum consolidation depth (consolidate consolidated entries)?

---

## References

- Epic 23: Shared Memory Foundation
- Epic 24: Memory Intelligence (decay, contradictions)
- Epic 25: Memory Retrieval & Integration
- Epic 34: Memory Retrieval Upgrade (BM25 scoring)
- [mcp-memory-service](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) — reference implementation
