# Epic 42: tapps_memory 2026 Enhancements

**Status:** Complete
**Priority:** P1
**Estimated LOE:** ~1.5–2 weeks
**Dependencies:** Epic 23, 24, 25, 34 (memory foundation, intelligence, retrieval, BM25/reinforce/gc)
**Blocks:** None

---

## Goal

Wire the existing tapps-core memory infrastructure into the MCP tool, expose ranked search with scores, implement the 4 missing actions (contradictions, reseed, import, export), shape responses for outcome-oriented agent use, and bring `server_memory_tools.py` above the quality gate.

## Current State (as of 2026-03-03)

All core infrastructure for this epic already exists and is tested in tapps-core. The work is primarily **MCP tool wiring**, not greenfield development.

| Component | Module | Status | Lines |
|-----------|--------|--------|-------|
| Ranked BM25 search | `tapps_core.memory.retrieval` (`MemoryRetriever`) | Implemented, tested, **NOT exposed** via MCP | 330 |
| Contradiction detection | `tapps_core.memory.contradictions` (`ContradictionDetector`) | Implemented, tested, **NOT exposed** via MCP | 248 |
| Profile-based seeding/reseed | `tapps_core.memory.seeding` (`reseed_from_profile`) | Implemented, tested, **NOT exposed** via MCP | 229 |
| Import/export | `tapps_core.memory.io` (`import_memories`, `export_memories`) | Implemented, tested, **NOT exposed** via MCP | 203 |
| MCP tool (7 actions) | `tapps_mcp.server_memory_tools` | save, get, list, delete, search, reinforce, gc | 396 |

**Current `_VALID_ACTIONS`:** `{save, get, list, delete, search, reinforce, gc}` — missing 4 actions documented in AGENTS.md.

**Current quality score:** 67.78/100 (gate threshold 70, **FAILS**). Complexity and maintainability are the weak categories.

**AGENTS.md gap:** Line 56 claims 11 actions including `contradictions, reseed, import, export` — these are not yet wired into the tool.

## Motivation

- **Gap:** MCP `tapps_memory search` uses FTS5-only; the ranked retrieval (BM25 + confidence + recency + frequency) exists in `MemoryRetriever` and is used only internally by `inject_memories`. Agents cannot see scores or stale flags.
- **Gap:** AGENTS.md documents actions `contradictions`, `reseed`, `import`, `export`; the tool only implements save, get, list, delete, search, reinforce, gc.
- **Opportunity:** 2026 MCP/RAG guidance (outcome-oriented tools, curated retrieval, no raw dumps) can improve trust and usefulness of memory.
- **Quality:** EPIC-38 self-review flagged memory (67.78 score, gate fail). Wiring new actions provides the opportunity to refactor the dispatch and improve the score.

## 2026 Research Applied

- **Outcome-oriented tools** — Expose high-level outcomes (e.g. "search with relevance and confidence") and return curated, scored results instead of raw dumps ([MCP best practices](https://www.philschmid.de/mcp-best-practices)).
- **Flatten arguments; avoid data dumps** — Curate retrieval results (top-N with scores and one-line summaries); prevent context-window bloat ([Knit: RAG and Agent Memory with MCP](https://www.getknit.dev/blog/powering-rag-and-agent-memory-with-mcp)).
- **Agent memory primitives** — Align with MCP memory patterns: persistent context, long-term personalization, clear separation from session-only state ([Memory MCP Server](https://playbooks.com/mcp/modelcontextprotocol/servers/memory)).

## Acceptance Criteria

- [ ] `tapps_memory search` supports optional ranked mode and returns composite score, effective_confidence, stale per result.
- [ ] `tapps_memory` implements `contradictions`, `reseed`, `import`, `export`; AGENTS.md and tool schema aligned with actual behavior.
- [ ] Search/list responses are curated (top-N, summaries, scores) to avoid raw dumps; structure supports outcome-oriented agent use.
- [ ] Memory modules pass quality gate (server_memory_tools.py ≥ 70); EPIC-38 remediation addressed via dispatch refactoring.
- [ ] Design review run on memory modules (score, gate, validate_changed) and results captured as DoD evidence.

## Stories

### 42.1 — Expose Ranked Search in tapps_memory

**Priority:** High | **Points:** 3

Wire `MemoryRetriever` into the MCP `search` action and return scores so agents can see why a memory ranked and whether it is stale.

**Context:** `MemoryRetriever` (tapps_core.memory.retrieval) already implements composite scoring: relevance (40%) + confidence (30%) + recency (15%) + frequency (15%), with BM25 indexing, stale detection, and `ScoredMemory` return type. This story wires it into the MCP tool.

**Tasks:**
- Add optional parameter `ranked: bool = True` to `tapps_memory` for the search action (default True for backward-friendly improvement).
- When `ranked=True`, call `MemoryRetriever.search(..., store, limit=...)` instead of `store.search(query)`; return list of entries with `score`, `effective_confidence`, `stale` per item.
- Response shape: `action: "search"`, `results: [{ "entry": {...}, "score": float, "effective_confidence": float, "stale": bool }]`, `count`, `query`, `store_metadata`.
- When `ranked=False`, keep current FTS5-only behavior (no scores).
- Update `_VALID_ACTIONS` and tool description; add `ranked` to schema.
- Write ~8 unit tests: ranked returns scores, stale true when decayed, ranked=false matches current behavior, limit respected, contradicted excluded when appropriate.

**Definition of Done:** Agents receive composite score and stale flag for search results. Default is ranked.

---

### 42.2 — Wire Missing Actions: contradictions, reseed, import, export

**Priority:** High | **Points:** 5

Wire the four already-implemented tapps-core functions into the MCP tool so behavior matches AGENTS.md documentation.

**Context:** All four functions are fully implemented and tested in tapps-core:
- `ContradictionDetector.detect_contradictions()` in `tapps_core.memory.contradictions`
- `reseed_from_profile()` in `tapps_core.memory.seeding`
- `import_memories()` / `export_memories()` in `tapps_core.memory.io`

This story adds dispatch entries and parameter mapping — not building from scratch.

**Tasks:**
- **contradictions** — Add `contradictions` action: call `ContradictionDetector.detect_contradictions(memories, profile)` using current project profile; return list of contradicted entries with reason; optionally call `store.update_fields` to set contradicted flag (idempotent).
- **reseed** — Add `reseed` action: call `reseed_from_profile(store, profile)`; update only entries with auto-seeded tag; do not overwrite human/agent memories.
- **import** — Add `import` action: accept `file_path: str`, optional `overwrite: bool`; delegate to `import_memories(store, path, validator, overwrite=...)`.
- **export** — Add `export` action: accept optional `file_path`, optional filters `tier`, `scope`, `min_confidence`; delegate to `export_memories(store, path, validator, ...)`.
- Add all four to `_VALID_ACTIONS`; update tool description.
- Write ~10 unit tests: contradictions returns list and updates store; reseed only touches seeded entries; import validates and respects overwrite; export produces valid JSON and respects filters; path validation enforced.

**Definition of Done:** contradictions, reseed, import, export work from MCP client. `_VALID_ACTIONS` has 11 entries matching AGENTS.md.

---

### 42.3 — Outcome-Oriented Search/List Responses (Curated, No Dumps)

**Priority:** Medium | **Points:** 3

Shape search and list responses so agents get curated, outcome-oriented payloads instead of raw dumps.

**Tasks:**
- For `search`: already improved in 42.1 (scores, stale). Add optional `summary: bool = True`: when True, include a one-line summary per result (e.g. first 80 chars of value or key + tier).
- For `list`: add optional `limit: int = 50` and `include_summary: bool = True`; return `entries` with optional short summary; add `total_count` and `returned_count` so agent knows if truncated.
- Document in tool description that results are curated; avoid returning full value for every hit when count is large (e.g. when limit > 20, return full value only for top 5, rest with summary).
- Write ~4 unit tests: summary present when requested; limit enforced; total_count vs returned_count.

**Definition of Done:** Search and list support limits and summaries; responses stay bounded and useful for agent context.

---

### 42.4 — Documentation, AGENTS.md, and Quality Gate Alignment

**Priority:** High | **Points:** 3

Align all documentation with implemented behavior and improve memory module quality to pass the gate.

**Tasks:**
- Update AGENTS.md memory section: list all 11 actions (save, get, list, delete, search, reinforce, gc, contradictions, reseed, import, export) with one-line when-to-use; remove stale claims.
- Update README/CLAUDE.md memory references to mention ranked search and new actions.
- Address quality gate failure for server_memory_tools.py (67.78, gate fail): refactor dispatch to reduce cyclomatic complexity (e.g. extract action handlers into a dispatch map pattern, reduce branching). Adding 4 new actions provides the opportunity to restructure.
- Run `tapps_score_file`, `tapps_quality_gate`, `tapps_validate_changed` on memory-related files and capture results as DoD evidence.
- Ensure `tapps_memory` is listed in checklist and pipeline rules with correct task types.

**Definition of Done:** AGENTS.md and README/CLAUDE accurate; server_memory_tools.py passes quality gate (≥ 70); design review results captured.

---

## Future Considerations

### Context7-Assisted Memory Validation/Enrichment (Deferred)

Optional integration with doc lookup (Context7) to validate or enrich memories that reference a library. Deferred because:

- **Heuristic limitation:** Without an LLM in the path, "validation" is keyword matching — fragile and prone to false positives. TappsMCP's core principle is deterministic tools (no LLM in the tool chain).
- **Latency concern:** Adding async doc lookup to the save path introduces latency and failure modes for uncertain benefit.
- **Inspiration:** [QMD](https://github.com/tobi/qmd) demonstrates that doc-backed memory enrichment is valuable, but QMD achieves quality through local LLM models (embedding, reranker, query expansion ~2GB). Without equivalent intelligence, the approach is less effective.
- **When to revisit:** This becomes viable if TappsMCP ever adopts optional LLM-backed validation, or if a lightweight deterministic approach to doc-memory linking is designed. The enrichment side (attaching a doc snippet as evidence) is more defensible than the validation side (detecting contradictions via keywords).

If implemented, scope would be:
- Config `memory.context7_validate_on_save: bool = false` (default off)
- When saving a memory with a `library:*` tag, optionally fetch a doc snippet via existing lookup path
- Attach as `evidence_snippet` or `validation_warning` in response
- No new required dependencies; no LLM in hot path

---

## Performance Targets

| Operation           | Target (p95) | Notes                          |
|--------------------|-------------|---------------------------------|
| Search (ranked)    | < 100ms     | Retriever + FTS5 + BM25        |
| Contradictions     | < 500ms     | Profile load + full scan        |
| Reseed             | < 200ms     | Profile + conditional updates   |
| Import (100 entries)| < 300ms    | Parse + validate + save         |
| Export (500 entries)| < 200ms    | Snapshot + write                |

## File Layout

```
packages/tapps-core/src/tapps_core/memory/
    (existing: models, persistence, store, decay, reinforcement, retrieval, bm25, gc, contradictions, injection, io, seeding)

packages/tapps-mcp/src/tapps_mcp/
    server_memory_tools.py   # extended to 11 actions, ranked search, dispatch refactor
```

## Key Dependencies

- Epic 23 (Shared Memory Foundation)
- Epic 24 (Memory Intelligence — contradictions, decay, reinforce, gc)
- Epic 25 (Memory Retrieval & Integration — seeding, import/export spec)
- Epic 34 (BM25, reinforce/gc in tool)
- Epic 32 (optional: tool-effectiveness tasks for memory)
- EPIC-38 (quality gate targets for server_memory_tools.py)

## References

- **[EPIC-42-MEMORY-DESIGN-REVIEW.md](EPIC-42-MEMORY-DESIGN-REVIEW.md)** — Runbook for score, gate, validate_changed, security, dead-code, and tests on memory modules; use for DoD evidence (Story 42.4).
- [MCP Best Practices (outcome-oriented, no dumps)](https://www.philschmid.de/mcp-best-practices)
- [Powering RAG and Agent Memory with MCP](https://www.getknit.dev/blog/powering-rag-and-agent-memory-with-mcp)
- [Memory MCP Server (playbooks)](https://playbooks.com/mcp/modelcontextprotocol/servers/memory)
- [QMD — local hybrid search engine](https://github.com/tobi/qmd) (inspiration for future Context7 enrichment)
- EPIC-23, EPIC-24, EPIC-25, EPIC-34 (this repo)
- EPIC-38 (Top-10 Self-Review Remediation — memory 67.78, gate fail)
