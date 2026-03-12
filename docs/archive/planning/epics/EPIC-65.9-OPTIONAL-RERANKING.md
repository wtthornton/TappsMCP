# Epic 65.9: Optional Reranking (2026 Best Practices)

**Status:** Complete
**Priority:** P2 | **LOE:** 1 week | **Source:** [EPIC-65-MEMORY-2026-BEST-PRACTICES](../EPIC-65-MEMORY-2026-BEST-PRACTICES.md)
**Dependencies:** Epic 65.8 (hybrid search)

## Problem Statement

RAG 2025: after hybrid retrieval, cross-encoder reranking improves precision. Pass top-20 candidates to reranker (Cohere, BGE) to get final top-5/10. Optional, configurable.

**Reference:** Cohere Rerank, BGE Reranker, RAG production pipeline

## Stories

### Story 65.9.1: Reranker protocol

**Files:** `packages/tapps-core/src/tapps_core/memory/reranker.py` (new)

1. Define `Reranker` protocol:
   - `rerank(query: str, candidates: list[tuple[str, str]], top_k: int) -> list[tuple[str, float]]`
   - Input: query, (entry_key, value) pairs; output: top_k ranked by relevance
2. Implementations (optional deps):
   - `NoopReranker` (passthrough)
   - `CohereReranker` (API)
   - `BGEReranker` (local model)
3. Feature flag: `memory.reranker.enabled` (default: false)

**Acceptance criteria:**
- Protocol defined
- NoopReranker always available (passthrough)

### Story 65.9.2: Reranking in retrieval pipeline

**Files:** `packages/tapps-core/src/tapps_core/memory/retrieval.py`

1. When reranker enabled: after hybrid/BM25 retrieval, pass top-20 to reranker
2. Return reranker's top-k (default 10)
3. Config: `memory.reranker.provider`, `memory.reranker.top_k`, `memory.reranker.api_key` (if API)

**Acceptance criteria:**
- Reranking applied when enabled
- Configurable top_k
- Graceful fallback when reranker fails

### Story 65.9.3: Config and documentation

**Files:** `config/settings.py`, `default.yaml`, AGENTS.md

1. Add reranker config
2. Document: optional; API cost for Cohere; local model for BGE

**Acceptance criteria:**
- Config loads reranker settings
- Docs updated
