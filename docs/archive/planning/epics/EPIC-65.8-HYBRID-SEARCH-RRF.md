# Epic 65.8: Hybrid Search with Reciprocal Rank Fusion (2026 Best Practices)

**Status:** Complete
**Priority:** P1 | **LOE:** 2-2.5 weeks | **Source:** [EPIC-65-MEMORY-2026-BEST-PRACTICES](../EPIC-65-MEMORY-2026-BEST-PRACTICES.md)
**Dependencies:** Epic 23, 25, 34, 65.7 (memory, retrieval, BM25, vector provider)

## Problem Statement

BM25-only retrieval misses semantic matches. Vector-only misses exact matches. Hybrid search (BM25 + vector + RRF) yields 30-40% improvement. This epic implements Reciprocal Rank Fusion to merge BM25 and vector results.

**Reference:** Elasticsearch RRF, Azure AI Search hybrid ranking, k=60

## Stories

### Story 65.8.1: RRF fusion implementation

**Files:** `packages/tapps-core/src/tapps_core/memory/fusion.py` (new) or `retrieval.py`

1. Implement `reciprocal_rank_fusion(
     bm25_ranked: list[str],
     vector_ranked: list[str],
     k: int = 60
   ) -> list[tuple[str, float]]`:
   - For each doc: `score = sum(1/(k + rank))` across lists
   - Deduplicate; sort by fused score descending
   - k=60 typical default
2. Run BM25 and vector search in parallel (top-20 each when semantic enabled)
3. Merge with RRF; return unified ranking

**Acceptance criteria:**
- RRF formula: `1/(k+rank)`
- Deduplication and ordering correct
- Configurable k

### Story 65.8.2: Hybrid retrieval in MemoryRetriever

**Files:** `packages/tapps-core/src/tapps_core/memory/retrieval.py`

1. When `memory.semantic_search.enabled`:
   - Run BM25 search (top-20)
   - Run vector similarity search (top-20)
   - Merge with RRF
   - Return top N
2. When semantic disabled: BM25-only (current behavior, unchanged)
3. Config: `memory.hybrid.top_bm25`, `memory.hybrid.top_vector`, `memory.hybrid.rrf_k`

**Acceptance criteria:**
- Hybrid path when semantic enabled
- BM25-only fallback when semantic disabled
- No regression for BM25-only

### Story 65.8.3: Vector similarity search

**Files:** `packages/tapps-core/src/tapps_core/memory/retrieval.py`, `embeddings.py`

1. Add `_vector_search(query: str, store: MemoryStore, limit: int) -> list[tuple[str, float]]`:
   - Embed query
   - Compute cosine similarity with stored embeddings
   - Return top N (entry key, score)
2. Use stored embeddings from persistence
3. Handle: entries without embeddings (skip or fallback to BM25 only for those)

**Acceptance criteria:**
- Vector search returns ranked results
- Graceful handling of missing embeddings

## Testing

- Unit: RRF fusion correctness (known inputs)
- Unit: hybrid retrieval returns combined results
- Integration: hybrid search vs BM25-only (recall comparison)
