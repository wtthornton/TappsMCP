# DESIGN — Unified cache substrate + context-retrieval layer

Date: 2026-07-01
Status: Draft (design-support for the cache-consolidation epic; not yet an ADR)
Related: ADR-0004 (deterministic tools), ADR-0016 (needs-based MCP taxonomy), ADR-0017 (Python-first call graph), ADR-0026 (TS call graph), ADR-0027 (shareable artifact), ADR-0028 (code-graph boundary)

## Why this exists

tapps-mcp answers two kinds of "knowledge" questions — **codebase questions** (call tree / impact / routes) and **research questions** (library docs via Context7). Both are implemented as *on-demand tool + on-disk cache + graceful degradation*. But the caching, staleness, warming, and metrics machinery is **implemented independently ~5 times**. This design captures the 2026 research that confirms the retrieval direction, the target architecture that unifies the substrate, and the full refactor/delete inventory.

## 1. 2026 research — direction is confirmed (structural graph, not vector RAG)

Grounding the architecture in current (2026) practice:

- **Structural graph beats vector RAG for code.** By 2026 the SWE-bench Verified leaders (>80%) do **not** use vector retrieval over the target repo; code relevance != text similarity, and naive RAG misses structural relationships. Hybrid = vector for *entry points* + graph for *traversal*. (mem0 State-of-Agent-Memory 2026; Kilo "AI Coding Assistants for Large Codebases 2026"; Grewal "AI Agents Don't Need Vector Search Anymore".)
- **Tree-sitter AST over SCIP/LSP is the 2026 consensus.** There is a live RFC to *remove SCIP and adopt tree-sitter file-incremental indexing*; tree-sitter re-parses one file where SCIP requires full-project analysis (~3 orders of magnitude faster incremental). LSP-style type resolution is the *hybrid enhancement* for untyped receivers. (sheeptechnologies RFC-001; Medium "Semantic Code Indexing with AST and Tree-sitter".)
- **The reference feature set = what tapps-mcp now has.** 2026 code-knowledge-graph reference designs extract "every function, class, method, import, call relationship, and HTTP route into a graph" + incremental updates. (arXiv 2603.27277 "Codebase-Memory"; DeusData "120x token cut with a code knowledge graph"; Cognee persistent codebase memory.)

**Implication:** the call-graph direction (ADR-0004/0017/0026 + the TS/route/incremental work) is *on-architecture* for 2026. Code intelligence should mirror the docs cache in **caching + on-demand-tool + degradation shape**, but **retrieval stays a deterministic graph — never vector RAG over the repo.**

## 2. The fragmentation (verified inventory)

Five parallel file-cache implementations, splitting into exactly two staleness models:

| # | Cache | File(s) | Staleness model | Provider | Metrics |
|---|---|---|---|---|---|
| 1 | Docs (KBCache) | `tapps_core/knowledge/cache.py` | TTL / clock (24h, per-lib overrides) | Context7 (network) + circuit breaker | `CacheStats` |
| 2 | Code graph | `tapps_mcp/project/call_graph_cache.py` | content fingerprint (per-file sha) | local tree-sitter/ast build | none |
| 3 | Per-file tool results | `tapps_mcp/tools/content_hash_cache.py` | SHA-256 content hash | local (scoring/gate/security) | none |
| 4 | Dependency scan | `tapps_mcp/tools/dependency_scan_cache.py` | session / TTL | local (pip-audit) | none |
| 5 | Linear snapshots | `tapps_mcp/server_linear_tools.py` + `tools/linear_list_gateway.py` + `docs-mcp/integrations/linear_gateway.py` | TTL (`cached_at`/`expires_at`) | agent-fetched | none |

Each re-implements atomic write, staleness check, and (where present) warming + metrics.

- **Fingerprint cluster:** #2 code graph, #3 content-hash → share `FingerprintStaleness`.
- **TTL cluster:** #1 docs, #4 dep-scan, #5 Linear → share `TTLStaleness`.
- **Metrics:** present on 1 of 5. **Warming:** `knowledge/warming.py` + `experts/rag_warming.py` + `_schedule_call_graph_rebuild` — 3 warmers.

**Not caches (leave alone):** `project/session_notes.py` (user KV store), the many `.tapps-mcp/*` state dirs (metrics/learning/sessions/etc. are event/state stores, not derived caches).

## 3. Target architecture

A thin shared substrate in `tapps_core.cache`; domain differences stay pluggable. **This is NOT "code becomes a KBCache provider"** — KBCache is a network-provider-fetch-with-TTL cache; the code graph is a local-deterministic-build-with-fingerprint cache. Only the primitive is common.

- **`AtomicJsonCache`** — the one read/write/atomic-replace primitive (kills 5 `_write_atomic` copies).
- **`StalenessStrategy` protocol** — `TTLStaleness` | `FingerprintStaleness` | `VersionStaleness` (`INDEX_VERSION`). Pluggable, because the models are irreconcilable by nature.
- **Unified `CacheStats`** — every cache reports hit-rate into one surface (`tapps_stats` / `server_metrics_tools`).
- **One session-start warmer** that schedules docs + code + (optionally) others.
- **Degradation contract** — stale/absent -> domain fallback (docs: serve-stale+refresh; code: local rebuild; ADR-0027 derived-cache boundary).

Retrieval mechanisms stay separate and domain-specific. Per 2026: code stays a deterministic graph.

### The longer arc (Phase 3) — unified context-retrieval layer

Once the substrate exists, the three retrieval sources — **code graph (structural)**, **docs (external/semantic)**, **brain (episodic/cross-session)** — front a common on-demand *retrieval-provider* protocol, matching the 2026 layered-memory model (graph + semantic + episodic). This is where the redundant per-cache implementations are **migrated and deleted**.

## 4. Refactor / delete inventory (rolled into Phase 3; pulled earlier only where prereq)

| Item | Action | Phase | Note |
|---|---|---|---|
| 5x `_write_atomic` copies | delete 4, keep shared primitive | P1 (pilot) + P3 (rest) | pilot proves the primitive |
| `call_graph_cache` staleness | re-base on `FingerprintStaleness` | **P1 pilot** ("needed earlier" — proves substrate) | cleanest fingerprint case |
| `content_hash_cache` | re-base on `FingerprintStaleness` | P3 | second fingerprint consumer |
| `KBCache` staleness | re-base on `TTLStaleness` (keep provider/breaker) | P3 | mature; migrate carefully |
| `dependency_scan_cache` | re-base on `TTLStaleness` | P3 | |
| Linear snapshot cache (3 sites) | re-base on `TTLStaleness`; collapse the 3 gateways | P3 | 3 impls -> 1 |
| code-graph / dep-scan / Linear metrics | add unified `CacheStats` | P2 | metrics on 5/5 |
| 3 warmers | one session-start warmer scheduling all | P2 | |
| `tapps_mcp/knowledge/cache.py` + `warming.py` shims | keep (back-compat) or delete at a major | P3 (optional) | 7-9 line re-exports; low value |
| retrieval-provider protocol (code+docs+brain) | build the unified layer | P3 | the 2026 layered-memory target |

**Guard rails (from the 2026 review + the over-build lesson):**
- Success metric for P1-P3 = **net code goes DOWN**. If the abstraction adds more than it removes, stop.
- Never collapse the two staleness models into one; never route code through TTL or vector RAG.
- Each phase is a separate go/no-go; P3 (unified layer) only proceeds if P1-P2 prove the substrate earns its keep.

## 5. Phase map

- **P0** — decision ADR: ratify the substrate boundary; rule out "code-as-KBCache-provider" and "vector-RAG-over-code". *(keystone; nothing built until approved)*
- **P1** — extract `AtomicJsonCache` + `StalenessStrategy`; **pilot-migrate `call_graph_cache`** (byte-equivalent; the "needed earlier" prereq that proves the substrate).
- **P2** — unified `CacheStats` (metrics on all caches) + one session-start warmer.
- **P3** — migrate remaining caches (content-hash, KBCache, dep-scan, Linear x3) onto the substrate, **delete the redundant per-cache impls**, and build the unified context-retrieval layer (code + docs + brain). Carries the refactor/delete inventory above.

## References

1. mem0 — State of AI Agent Memory 2026: https://mem0.ai/blog/state-of-ai-agent-memory-2026
2. Kilo — AI Coding Assistants for Large Codebases (2026): https://blog.kilo.ai/p/ai-coding-assistants-for-large-codebases
3. Grewal — AI Agents Don't Need Vector Search Anymore (2026): https://buzzgrewal.medium.com/ai-agents-dont-need-vector-search-anymore-inside-the-agentic-search-stack-replacing-rag-in-2026-58efcabe4f6f
4. sheeptechnologies RFC-001 — Remove SCIP, adopt tree-sitter incremental: https://github.com/orgs/sheeptechnologies/discussions/4
5. arXiv 2603.27277 — Codebase-Memory: Tree-Sitter Knowledge Graphs via MCP: https://arxiv.org/html/2603.27277v1
6. DeusData — 120x token cut with a code knowledge graph: https://dev.to/deusdata/how-i-cut-my-ai-coding-agents-token-usage-by-120x-with-a-code-knowledge-graph-4a3d
7. Cognee — Persistent Codebase Memory for Coding Agents 2026: https://www.cognee.ai/blog/guides/ai-coding-agent-persistent-codebase-memory
