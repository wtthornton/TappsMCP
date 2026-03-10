# Epic 65.7: Optional Vector/Embedding Provider (2026 Best Practices)

**Status:** Proposed
**Priority:** P1 | **LOE:** 1.5-2 weeks | **Source:** [EPIC-65-MEMORY-2026-BEST-PRACTICES](../EPIC-65-MEMORY-2026-BEST-PRACTICES.md)
**Dependencies:** Epic 23, 25, 34 (memory, retrieval, BM25)

## Problem Statement

TappMCP retrieval is BM25-only. Hybrid search (BM25 + vector) yields 30-40% better retrieval. Mem0 uses vector DB + graph + KV. This epic adds an optional pluggable embedding provider so semantic search can be enabled.

**Reference:** Mem0 vector store, hybrid search 2025

## Stories

### Story 65.7.1: Embedding provider protocol

**Files:** `packages/tapps-core/src/tapps_core/memory/embeddings.py` (new)

1. Define `EmbeddingProvider` protocol:
   - `embed(text: str) -> list[float]`
   - `embed_batch(texts: list[str]) -> list[list[float]]`
   - `dimension: int`
2. Implementations (optional deps via feature_flags):
   - `SentenceTransformerProvider` (sentence-transformers)
   - `OpenAIEmbeddingProvider` (API)
   - `NoopProvider` (placeholder when disabled)
3. `get_embedding_provider() -> EmbeddingProvider | None` (returns None when disabled)

**Acceptance criteria:**
- Protocol defined
- At least one implementation (NoopProvider always available)
- Feature flag: `memory.semantic_search.enabled` (default: false)

### Story 65.7.2: Embedding storage in persistence

**Files:** `packages/tapps-core/src/tapps_core/memory/persistence.py`, `models.py`

1. Add optional `embedding` column to memory table (BLOB or JSON array)
2. Schema migration: add column; existing rows null
3. On save: compute embedding when semantic enabled, store
4. On load: load embedding with entry
5. Backward compatible: embedding optional

**Acceptance criteria:**
- Schema supports embedding column
- Migration applies cleanly
- Existing stores work without embedding

### Story 65.7.3: Config and feature flag

**Files:** `packages/tapps-core/src/tapps_core/config/settings.py`, `feature_flags.py`, `default.yaml`

1. Add to config:
   ```yaml
   memory:
     semantic_search:
       enabled: false
       provider: "sentence_transformers"  # or "openai"
       model: "all-MiniLM-L6-v2"  # for sentence-transformers
   ```
2. Feature flag: `feature_flags.memory_semantic_search`
3. Document: optional dependency `sentence-transformers` or `openai` for semantic

**Acceptance criteria:**
- Config loads semantic_search settings
- Feature flag gates semantic path
- Docs: optional deps, setup instructions

## Testing

- Unit: NoopProvider returns zeros; protocol compliance
- Unit: persistence stores/loads embedding
- Integration: optional sentence-transformers when installed
