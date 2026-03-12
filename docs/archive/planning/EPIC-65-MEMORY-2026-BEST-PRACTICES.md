# Epic 65: Memory 2026 Best Practices Implementation Plan

**Status:** Proposed
**Priority:** P1 — High
**Estimated LOE:** ~12-16 weeks (phased implementation)
**Dependencies:** Epic 23, 24, 25, 34, 58, 64 (all complete)
**Blocks:** None

---

## Executive Summary

This plan implements high- and medium-impact memory improvements for TappMCP based on 2026 research from Zylos, Neuronex, Mem0, Cognee, and hybrid RAG best practices. It updates the original recommendations with new insights and adds research-driven enhancements.

**Research sources:**
- Zylos AI Agent Memory Systems 2026
- Neuronex: Agent Memory Without Creepy or Wrong
- Mem0 architecture (vector + graph + KV, 26% accuracy boost, 90% token savings)
- Cognee vs Mem0 comparison (relationship-focused vs scalable personalization)
- Hybrid search: BM25 + Vector + Reciprocal Rank Fusion (30-40% better retrieval)
- A-Mem (Zettelkasten): 85-93% token reduction via atomic notes
- OpenClaw auto-recall/auto-capture hook patterns
- RAG best practices: multi-stage retrieval, reranking, context engineering

---

## Revised & New Recommendations

### Changes from Original Analysis

| Original Recommendation | Research Update | Change |
|-------------------------|-----------------|--------|
| Optional semantic search | Hybrid search (BM25 + vector + RRF) is production standard; 30-40% better than either alone | **Upgrade:** Implement hybrid with RRF fusion, not vector-only add-on |
| Auto-capture/recall hooks | `before_prompt_build` + `after response` is established pattern (OpenClaw, Kumiho, recall-echo) | **Refine:** Use hook names aligned with platform (e.g., PreCompact, Stop) |
| Relationship-aware consolidation | Mem0 Graph Memory + Cognee knowledge graphs; relationships critical for "who owns X" queries | **Expand:** Add optional entity/relationship extraction to consolidation |
| Memory stats in dashboard | Low-effort quick win; aligns with "observability" best practice | **Keep** |
| Write rules / capture prompt | "Store understanding, not action sequences"; structured objects; test: "if it doesn't change future decisions, don't store it" | **Add:** Configurable write rules and capture prompt in config |
| Session indexing | More coverage but more noise; flush prompt quality becomes critical | **Keep** |
| Export for manual curation | Markdown export for Obsidian; aligns with "human-in-the-loop" best practice | **Keep** |

### New Recommendations from Research

| New Recommendation | Source | Rationale |
|--------------------|--------|-----------|
| **Procedural memory type** | Zylos, Neuronex | Add procedural tier: "how to do" (workflows, steps). Enables few-shot learning via similar past situations. |
| **Memory retrieval policy** | Neuronex | Formal policy: block sensitive categories, prefer high-confidence, show what was used, retrieve only when needed. |
| **RRF (Reciprocal Rank Fusion)** | Hybrid search research | Use `score = 1/(k + rank)` to merge BM25 + vector; k=60 typical; parameter-free, stable across score distributions. |
| **Optional reranking** | RAG best practices | Cross-encoder rerank (Cohere, BGE) on top candidates for precision; optional, configurable. |
| **Scoped retrieval (user/session/agent)** | Zylos, Mem0 | Mem0 uses hierarchical user/session/agent scoping; TappMCP has project/branch/session—extend for multi-user MCP. |
| **Memory maintenance pipeline** | JoelClaw, Zylos | Nightly/weekly: deduplication, consolidation, pruning; time-decay ranking. TappMCP has gc, consolidation—formalize schedule. |
| **Write rules validation** | Neuronex | "Only store: validated, non-sensitive, improves outcomes, will matter later." Add optional validation gate. |
| **Verification-before-acting** | Neuronex | When memory affects actions, prefer live tool reads over stale memory. Document in retrieval policy. |
| **Atomic notes / Zettelkasten** | A-Mem, Zylos | Atomic notes with links; 85-93% token reduction. Consider consolidation producing atomic summaries. |
| **Context budgeting** | RAG 2025 | Budget tokens for memory injection; retrieve only highly relevant; avoid context bloat. |

---

## Implementation Plan Overview

### Phase 1: Quick Wins (2-3 weeks)

**Epic 65.1 — Memory Stats in Dashboard**
- **LOE:** 3-5 days
- Add memory subsection to `tapps_dashboard`: total entries, tier breakdown, stale count, confidence distribution, consolidation stats, federation stats
- Wire to `MemoryStore` and federation hub
- **Files:** `metrics/dashboard.py`, `server_metrics_tools.py`

**Epic 65.2 — Markdown Export & Curation**
- **LOE:** 3-5 days
- Extend `tapps_memory(action="export")` with `format="markdown"`
- Group by tier/tag; optional Obsidian frontmatter (tags, created_at, confidence)
- **Files:** `memory/io.py`, `server_memory_tools.py`

**Epic 65.3 — Configurable Capture Prompt & Write Rules**
- **LOE:** 4-6 days
- Add to `.tapps-mcp.yaml`:
  - `memory.capture_prompt`: Configurable prompt for what to store (default: durable memories, architectural/pattern/context criteria)
  - `memory.write_rules`: Optional validation (non-sensitive, improves outcomes, will matter later)
- Document in AGENTS.md and platform rules
- **Files:** `config/settings.py`, `default.yaml`, platform templates

---

### Phase 2: Auto-Capture & Auto-Recall Hooks (3-4 weeks)

**Epic 65.4 — Auto-Recall Hook**
- **LOE:** 1-1.5 weeks
- Add hook template: runs before agent prompt build (or PreCompact); calls `MemoryRetriever.search()`, injects top results as XML/structured block
- Config: `max_results` (1-10), `min_score` (0-1), `min_prompt_length` (skip for short prompts)
- Platform: Claude Code (`PreCompact`, `SessionStart`), Cursor (`beforeMCPExecution` or equivalent)
- **Files:** `pipeline/platform_hook_templates.py`, `platform_rules.py`
- **Reference:** OpenClaw Memory Auto-Recall, Kumiho zero-latency prefetch

**Epic 65.5 — Auto-Capture Hook**
- **LOE:** 1.5-2 weeks
- Add hook template: runs on Stop/session end; scans context (or passed content) for durable facts; calls `tapps_memory(action="save_bulk", entries=[...])`
- Uses `memory.capture_prompt` from config
- Optional: extraction via lightweight model or rule-based (entities, decisions)
- **Files:** `pipeline/platform_hook_templates.py`, `memory/extraction.py` (new)
- **Reference:** Mem0 extraction phase, OpenClaw memoryFlush

**Epic 65.6 — Hook Integration in tapps_init**
- **LOE:** 2-3 days
- Wire auto-recall and auto-capture hooks into `tapps_init` output; add to engagement-level templates
- Document trade-offs (coverage vs noise, flush prompt quality)

---

### Phase 3: Hybrid Search & Semantic Retrieval (4-5 weeks)

**Epic 65.7 — Optional Vector/Embedding Provider**
- **LOE:** 1.5-2 weeks
- Add pluggable embedding provider protocol (sentence-transformers, OpenAI, etc.)
- Feature flag: `memory.semantic_search.enabled` (default: false)
- Store embeddings alongside entries (new column or separate table)
- **Files:** `memory/embeddings.py` (new), `memory/persistence.py`, `config/feature_flags.py`
- **Reference:** Mem0 vector store, feature_flags pattern for optional deps

**Epic 65.8 — Hybrid Search with RRF**
- **LOE:** 2-2.5 weeks
- When semantic enabled: run BM25 and vector search in parallel (top-20 each)
- Fusion: Reciprocal Rank Fusion `score = 1/(k + rank)`, k=60
- Deduplicate, return unified ranking
- Fallback: BM25-only when semantic disabled (current behavior)
- **Files:** `memory/retrieval.py`, `memory/bm25.py`, `memory/embeddings.py`
- **Reference:** Elasticsearch RRF, Azure AI Search hybrid ranking

**Epic 65.9 — Optional Reranking**
- **LOE:** 1 week
- When configured: pass top-N (e.g., 20) from hybrid to cross-encoder (Cohere Rerank, BGE) for final top-5/10
- Config: `memory.reranker.enabled`, `memory.reranker.provider`, `memory.reranker.top_k`
- **Files:** `memory/retrieval.py`, `config/settings.py`
- **Reference:** RAG production pipeline, Cohere/BGE rerankers

---

### Phase 4: Session Indexing & Procedural Memory (2-3 weeks)

**Epic 65.10 — Session Indexing**
- **LOE:** 1.5-2 weeks
- Persist session summaries or key facts to searchable store
- New scope or tier: `session_index` (ephemeral, linked to session ID)
- Index via FTS5 + optional embeddings
- Search returns memory entries + session chunks; `include_sources`-style filtering
- **Files:** `memory/session_index.py` (new), `memory/store.py`, `memory/retrieval.py`

**Epic 65.11 — Procedural Memory Tier**
- **LOE:** 1 week
- Add `MemoryTier.procedural` = "how to do" (workflows, steps)
- Decay config: between pattern and context
- Consolidation can produce procedural templates (few-shot patterns)
- **Files:** `memory/models.py`, `memory/decay.py`, `memory/consolidation.py`

---

### Phase 5: Relationship-Aware Consolidation (3-4 weeks)

**Epic 65.12 — Entity/Relationship Extraction in Consolidation**
- **LOE:** 2-2.5 weeks
- During consolidation: optional entity extraction (people, teams, components)
- Store relationship metadata: `(Sarah, manages, backend)`, `(backend, owns, API)`
- Rule-based or lightweight NER; no heavy LLM dependency for extraction
- **Files:** `memory/consolidation.py`, `memory/models.py` (extend MemoryEntry or new RelationEntry)
- **Reference:** Cognee entity extraction, Mem0 Graph Memory

**Epic 65.13 — Relationship-Aware Retrieval**
- **LOE:** 1-1.5 weeks
- Query "who handles API?" → expand via relationships: backend → Sarah
- Optional graph backend (Neo4j, Memgraph) or in-memory adjacency for small scale
- **Files:** `memory/retrieval.py`, `memory/relations.py` (new)
- **Reference:** Cognee relationship retrieval, Mem0 graph traversal

---

### Phase 6: Policy & Maintenance (1-2 weeks)

**Epic 65.14 — Memory Retrieval Policy**
- **LOE:** 3-5 days
- Formalize in config and docs:
  - Block sensitive categories unless explicitly needed
  - Prefer high-confidence memories
  - Show what memory was used (debug trace)
  - Retrieve only when task requires it
- Optional: retrieval policy enforcement in `MemoryRetriever.search()`
- **Files:** `config/settings.py`, `memory/retrieval.py`, AGENTS.md

**Epic 65.15 — Memory Maintenance Schedule**
- **LOE:** 3-5 days
- Document and optionally automate: nightly/weekly deduplication, consolidation, gc
- `tapps_memory(action="maintain")` or integrate into `tapps_session_start` when idle
- **Files:** `memory/gc.py`, `memory/auto_consolidation.py`, `server_memory_tools.py`

---

### Phase 7: Context Budgeting & Write Validation (1 week)

**Epic 65.16 — Context Budget for Memory Injection**
- **LOE:** 2-3 days
- Config: `memory.injection_max_tokens` (default: 2000)
- Truncate/summarize injected memories to stay within budget
- **Files:** `memory/injection.py`, `config/settings.py`

**Epic 65.17 — Optional Write Rules Validation**
- **LOE:** 2-3 days
- Before save: optional check against write rules (non-sensitive, improves outcomes)
- Can use keyword blocklist or lightweight classifier
- **Files:** `memory/store.py`, `config/settings.py`

---

## Epic Dependency Graph

```
Epic 23, 24, 25, 34, 58, 64 (complete)
    │
    ├── 65.1 Memory Stats in Dashboard ────────────────────────►
    ├── 65.2 Markdown Export ──────────────────────────────────►
    ├── 65.3 Configurable Capture Prompt ──────────────────────►
    │       │
    │       ├── 65.4 Auto-Recall Hook ─────────────────────────►
    │       ├── 65.5 Auto-Capture Hook ────────────────────────►
    │       └── 65.6 Hook Integration ─────────────────────────►
    │
    ├── 65.7 Optional Vector Provider ────► 65.8 Hybrid RRF ───►
    │                                              │
    │                                              └── 65.9 Optional Reranking
    │
    ├── 65.10 Session Indexing ───────────────────────────────►
    ├── 65.11 Procedural Memory Tier ─────────────────────────►
    │
    ├── 65.12 Entity/Relationship Extraction ──► 65.13 Relation-Aware Retrieval
    │
    ├── 65.14 Memory Retrieval Policy ────────────────────────►
    ├── 65.15 Memory Maintenance Schedule ─────────────────────►
    ├── 65.16 Context Budget ──────────────────────────────────►
    └── 65.17 Write Rules Validation ──────────────────────────►
```

---

## Acceptance Criteria Summary

| Epic | Key Deliverables |
|------|------------------|
| 65.1 | Memory stats in `tapps_dashboard` (entries, tiers, stale, consolidation, federation) |
| 65.2 | `tapps_memory(action="export", format="markdown")` with Obsidian-style output |
| 65.3 | `memory.capture_prompt` and `memory.write_rules` in config; documented |
| 65.4 | Auto-recall hook template; injects memory before prompt |
| 65.5 | Auto-capture hook template; extracts and saves on session stop |
| 65.6 | Hooks wired in `tapps_init`; engagement-level config |
| 65.7 | Pluggable embedding provider; optional semantic storage |
| 65.8 | Hybrid BM25 + vector search with RRF fusion |
| 65.9 | Optional cross-encoder reranking |
| 65.10 | Session indexing; searchable past sessions |
| 65.11 | `MemoryTier.procedural`; decay and consolidation support |
| 65.12 | Entity/relationship extraction in consolidation |
| 65.13 | Relationship-aware retrieval for "who owns X" queries |
| 65.14 | Memory retrieval policy documented and optionally enforced |
| 65.15 | Maintenance schedule; `maintain` action or auto-trigger |
| 65.16 | `memory.injection_max_tokens`; truncation in injection |
| 65.17 | Optional write rules validation gate |

---

## Research References

1. **Zylos** — AI Agent Memory Systems 2026: episodic/semantic/procedural; A-Mem Zettelkasten; Mem0/Letta/A-Mem/MIRIX
2. **Neuronex** — Agent Memory Without Creepy or Wrong: semantic vs episodic; write rules; retrieval policy; verification before acting
3. **Mem0** — 26% accuracy boost; vector + graph + KV; extraction/update phases; auto-capture/auto-recall
4. **Cognee** — Knowledge graph; entity/relationship extraction; ECL pipeline
5. **Cognee vs Mem0** — Cognee: relationship-focused; Mem0: scalable personalization
6. **Hybrid Search** — BM25 + vector + RRF; 30-40% improvement; production standard
7. **RAG 2025** — Multi-stage retrieval; reranking; context budgeting; content optimization
8. **OpenClaw** — memoryFlush; session indexing; Qdrant; Mem0 plugin; Cognee integration
9. **Hook Patterns** — before_prompt_build (auto-recall); after response (auto-capture); recall-echo rules-file
10. **RRF** — Reciprocal Rank Fusion: `1/(k+rank)`, k=60; OpenSearch, Azure AI Search, Elasticsearch

---

## Out of Scope (Future Epics)

- Full graph database backend (Neo4j, Memgraph) — optional extension
- LLM-based extraction for auto-capture — keep deterministic-first; optional later
- Multi-user/scoped retrieval (user-level) — MCP is project-scoped; extend if multi-tenant
- A-Mem–style atomic notes with explicit linking — consolidation produces summaries; explicit links later
- Temporal knowledge graphs — time as first-class; advanced future work
