# Epic 25: Memory Retrieval & Integration

**Status:** Proposed
**Priority:** P2 — Important (closes the loop between memory and the rest of TappsMCP)
**Estimated LOE:** ~2-3 weeks (1 developer)
**Dependencies:** Epic 23 (Shared Memory Foundation), Epic 24 (Memory Intelligence), Epic 3 (Expert System — RAG), Epic 4 (Project Context — project profile)
**Blocks:** None (capstone epic for the memory system)

---

## Goal

Make memory a first-class participant in TappsMCP's tool ecosystem. Memories surface automatically in expert consultations and research queries. New projects get seeded with high-confidence memories from project profile detection. The expert RAG pipeline considers memory entries alongside curated knowledge files. Memory retrieval moves beyond simple keyword matching to semantic tag-based and scored ranking. This epic transforms memory from a standalone storage feature into the connective tissue that makes every TappsMCP tool smarter over time.

## Motivation

Epic 23 gives us a store. Epic 24 makes it trustworthy. This epic makes it *useful*. A memory system that only returns results when explicitly queried misses most of its value. The real payoff comes when an agent asks `tapps_consult_expert` about authentication and automatically receives "This project uses JWT with RS256 (confidence: 0.91, last reinforced 3 days ago)" alongside the expert's generic guidance.

## 2026 Best Practices Applied

- **Retrieval-augmented context** — Memory entries are injected into expert and research responses as additional context, clearly labeled with confidence and staleness. The consuming agent can weigh them against expert knowledge. Follows the pattern used by the mcp-memory-service and Mem0 MCP Server for cross-tool memory sharing.
- **Cold-start seeding** — New projects don't start with empty memory. `tapps_project_profile` results seed initial high-confidence architectural memories automatically. Addresses the cold-start problem identified in 2026 MCP memory benchmarks.
- **FTS5 + BM25-weighted ranking** — SQLite FTS5 provides built-in BM25 ranking (`bm25()` function) for full-text search, which is significantly better than simple word overlap for relevance scoring. Combined with confidence, recency, and access frequency for the final composite score. No external dependencies needed.
- **RAG safety on injection** — Memory values injected into expert/research responses pass through `rag_safety.py` as a defense-in-depth measure (first line of defense is on write in Epic 23, second is on read-for-injection here). Prevents stored prompt injection from reaching the LLM.
- **Opt-in enrichment** — Memory injection into expert/research is configurable per engagement level. Projects that don't want memory mixing can disable it.
- **Project namespacing** — All memory operations are scoped to `project_root`. The 2026 MCP memory benchmarks found that cross-project data confusion is the #1 failure mode in multi-project setups.

## Acceptance Criteria

- [ ] `tapps_memory search` returns results ranked by composite score (relevance + confidence + recency)
- [ ] `tapps_consult_expert` and `tapps_research` auto-inject relevant memories into responses
- [ ] Memory injection clearly labeled: "Project Memory (confidence: X.XX, tier: Y)"
- [ ] `tapps_project_profile` seeds initial memories on first run (if memory store is empty)
- [ ] Seeded memories: detected languages, frameworks, libraries, project type, test framework, CI system, package manager
- [ ] Seeded memories tagged with `auto-seeded` and `source=system`
- [ ] `tapps_memory import` action: bulk import from a JSON file (for team onboarding)
- [ ] `tapps_memory export` action: export all memories to JSON (for backup/sharing)
- [ ] Memory-aware `tapps_init`: include memory configuration in bootstrapped `.tapps-mcp.yaml`
- [ ] Engagement level integration: `high` = memories injected automatically, `medium` = memories available on request, `low` = memories stored but not injected
- [ ] Unit tests: ~35 tests (retrieval ~10, expert integration ~8, seeding ~7, import/export ~5, engagement ~5)

---

## Stories

### 25.1 — Ranked Retrieval

**Points:** 5

Upgrade memory search from simple keyword matching to scored, ranked retrieval using SQLite FTS5's built-in BM25 scoring combined with memory-specific signals.

**Tasks:**
- Create `src/tapps_mcp/memory/retrieval.py` with:
  - `MemoryRetriever` class:
    - `search(query: str, store: MemoryStore, config: DecayConfig, limit: int = 10) -> list[ScoredMemory]`
    - `ScoredMemory` model: `entry: MemoryEntry, score: float, effective_confidence: float, bm25_relevance: float, stale: bool`
  - Scoring formula (all components 0.0-1.0, weighted sum):
    - `bm25_relevance` (0.40 weight): SQLite FTS5 `bm25()` ranking function across key + value + tags. FTS5 handles tokenization, term frequency, and inverse document frequency natively. Bonus for exact key match (detected via separate `key = ?` check).
    - `effective_confidence` (0.30 weight): time-decayed confidence from decay engine
    - `recency` (0.15 weight): `1.0 / (1.0 + days_since_updated)` — more recent = higher
    - `access_frequency` (0.15 weight): `min(1.0, access_count / 20.0)` — frequently accessed = higher
  - SQL query pattern:
    ```sql
    SELECT m.*, fts.rank as bm25_score
    FROM memories m
    JOIN memories_fts fts ON m.key = fts.key
    WHERE memories_fts MATCH ?
    ORDER BY (0.4 * -fts.rank + 0.3 * m.confidence + 0.15 * recency + 0.15 * frequency)
    LIMIT ?
    ```
  - Filtering:
    - Exclude contradicted memories (unless explicitly requested via `include_contradicted=True`)
    - Exclude memories below confidence floor (0.1)
    - Scope filtering: match project → branch → session precedence
  - Result limit: default 10, max 50
  - Fallback: if FTS5 not available (rare edge case — some SQLite builds omit it), fall back to LIKE-based search with simple word overlap
- Update `tapps_memory search` action to use ranked retrieval
- Write ~10 unit tests:
  - Exact key match ranks highest
  - High-confidence memory outranks low-confidence with same relevance
  - Recent memory outranks old memory with same confidence
  - Contradicted memories excluded by default
  - Scope filtering works correctly
  - Result limit respected
  - FTS5 tokenization handles multi-word queries
  - Fallback to LIKE-based search when FTS5 unavailable

**Definition of Done:** Search returns ranked results. Scoring formula produces intuitive ordering.

---

### 25.2 — Expert & Research Memory Injection

**Points:** 5

Automatically inject relevant memories into `tapps_consult_expert` and `tapps_research` responses.

**Tasks:**
- Add memory retrieval hook to `tapps_consult_expert` in `server.py` (the expert tool lives there):
  - After expert generates answer, run memory search with the user's question as query
  - **RAG safety check**: All memory values pass through `rag_safety.check_content_safety()` before injection (defense-in-depth — first filter is on write in 23.3, this is the second)
  - If relevant memories found (score > 0.3), append to response as a new section:
    ```
    ### Project Memory
    - **[key]** (confidence: X.XX, tier: Y, last reinforced: Z): value
    ```
  - Max 5 memories injected per response
  - Only inject if `memory.inject_into_experts: true` in config (default: true)
- Add same hook to `tapps_research` in `server_metrics_tools.py`:
  - Memory injection after expert + docs content
  - Same format and limits
- Engagement level gating:
  - `high`: always inject (up to 5 memories)
  - `medium`: inject only if confidence > 0.5 (up to 3 memories)
  - `low`: never inject (memories only available via direct `tapps_memory` tool)
- Add `memory_injected: int` field to expert/research tool response metadata
- Write ~8 unit tests:
  - Memories injected when relevant
  - No injection when no relevant memories
  - Engagement level gating works
  - Max injection limit respected
  - Contradicted memories not injected
  - Memory injection clearly labeled in response

**Definition of Done:** Expert and research responses enriched with relevant project memories. Configurable by engagement level.

---

### 25.3 — Project Profile Seeding

**Points:** 3

Automatically seed the memory store with facts from `tapps_project_profile` on first detection.

**Tasks:**
- Add seeding logic to `tapps_project_profile` handler (or as a post-hook):
  - Only seed if memory store is empty (first run) or if profile has changed significantly
  - Seeded memories:
    - `project-type`: "Project type is {type}" (tier: architectural, confidence: profile_confidence)
    - `languages`: one entry per detected language (tier: architectural, confidence: 0.9)
    - `frameworks`: one entry per framework (tier: architectural, confidence: 0.9)
    - `test-framework`: one entry per test framework (tier: pattern, confidence: 0.9)
    - `package-manager`: "Package manager is {pm}" (tier: pattern, confidence: 0.9)
    - `ci-system`: one entry per CI system (tier: architectural, confidence: 0.9)
    - `has-docker`: "Project uses Docker" (tier: architectural, confidence: 0.9) — only if true
  - All seeded memories: `source=system`, `source_agent=tapps-mcp`, tagged with `auto-seeded`
  - Seeded memories have a `seeded_from: str = "project_profile"` metadata indicator
- Add `reseed` action to `tapps_memory` tool:
  - Re-runs profile detection and updates seeded memories
  - Only updates memories tagged `auto-seeded` — never overwrites human/agent memories
- Write ~7 unit tests:
  - Empty store gets seeded on first profile
  - Non-empty store is not re-seeded automatically
  - Seeded memories have correct tier, confidence, source, tags
  - Reseed updates existing auto-seeded memories
  - Reseed does not touch non-seeded memories
  - Profile confidence propagated to memory confidence

**Definition of Done:** New projects get pre-populated memory from profile. Reseed updates only auto-seeded entries.

---

### 25.4 — Import & Export

**Points:** 3

Enable teams to share and back up project memories.

**Tasks:**
- Add `import` action to `tapps_memory` tool:
  - Parameters: `file_path: str` — path to JSON file
  - JSON format: `{"memories": [MemoryEntry, ...], "exported_at": "...", "source_project": "..."}`
  - Validation: all entries validated through `MemoryEntry` model
  - Conflict resolution: skip keys that already exist (don't overwrite), or `overwrite: bool` param
  - Security: file path validated through `security/path_validator.py`
  - Imported memories get `source_agent` updated to include "(imported)" suffix
  - Max import size: 500 entries (matching store limit)
- Add `export` action to `tapps_memory` tool:
  - Parameters: `file_path: str` (optional — defaults to `{project_root}/.tapps-mcp/memory/export.json`)
  - Optional filters: `tier`, `scope`, `min_confidence`
  - Exports include metadata: export timestamp, project root, entry count, TappsMCP version
  - Security: output path validated through `security/path_validator.py`
- Write ~5 unit tests:
  - Export creates valid JSON
  - Import loads entries correctly
  - Import skips existing keys (no overwrite)
  - Import with overwrite replaces existing
  - Path validation enforced on both import and export

**Definition of Done:** Teams can export memories from one project and import into another. Path-sandboxed.

---

### 25.5 — Pipeline & Init Integration

**Points:** 3

Wire memory into the TappsMCP pipeline workflow and project bootstrapping.

**Tasks:**
- Update `tapps_init` to include memory configuration in generated `.tapps-mcp.yaml`:
  ```yaml
  memory:
    enabled: true
    gc_enabled: true
    contradiction_check_on_start: true
    max_memories: 500
    inject_into_experts: true
    decay:
      architectural_half_life_days: 180
      pattern_half_life_days: 60
      context_half_life_days: 14
  ```
- Update `tapps_session_start` to include memory status in response:
  - `memory_status: {enabled: true, total: N, stale: N, contradicted: N}`
  - Run GC if enabled (from Epic 24.4)
  - Run contradiction check if enabled (from Epic 24.3)
- Update pipeline stage tools mapping:
  - `discover` stage: add `tapps_memory` (list/search to recall context)
  - `verify` stage: add `tapps_memory` (save learnings for next session)
- Update AGENTS.md templates (all 3 engagement levels):
  - `high`: "REQUIRED: Check tapps_memory at session start for project context"
  - `medium`: "RECOMMENDED: Check tapps_memory for relevant project decisions"
  - `low`: "OPTIONAL: Use tapps_memory to persist findings across sessions"
- Update platform rule templates (Claude, Cursor) with memory tool guidance
- Write ~5 unit tests:
  - Init generates memory config
  - Session start includes memory status
  - Pipeline stages include memory tool

**Definition of Done:** Memory is part of the standard TappsMCP pipeline. New projects get memory config. Session start reports memory health.

---

### 25.6 — Tests & Documentation

**Points:** 2

Final test suite and comprehensive documentation.

**Tasks:**
- Integration tests:
  - Full lifecycle: seed → use → reinforce → decay → contradict → archive
  - Expert injection with real expert engine (mocked knowledge)
  - Import/export round-trip between two project roots
- Edge cases:
  - Memory store at max capacity (500) — oldest low-confidence entry evicted on save
  - Search with no results
  - Expert injection with empty memory store
  - Seeding with minimal profile (only language detected)
- Update all documentation:
  - README.md: add Memory section to tools reference
  - AGENTS.md: tool description and workflow integration
  - CLAUDE.md: update module map, add memory to caching patterns section
  - Add memory system to TAPPS_HANDOFF.md template
- Write migration guide: "Moving from session notes to shared memory"

**Definition of Done:** ~35+ tests pass. Documentation complete. Migration guide written.

---

## Performance Targets

| Operation | Target (p95) | Notes |
|---|---|---|
| Ranked search (500 entries) | < 100ms | SQLite FTS5 query + in-memory score weighting |
| Expert memory injection | < 50ms | Search + format, added to expert response time |
| Profile seeding | < 100ms | One-time, creates ~10-15 entries |
| Import (500 entries) | < 500ms | Validate + persist |
| Export (500 entries) | < 200ms | Read + serialize |

## File Layout

```
src/tapps_mcp/memory/
    retrieval.py        # MemoryRetriever, ScoredMemory, FTS5+BM25 ranking
    seeding.py          # ProfileSeeder, seed_from_profile(), reseed logic
    io.py               # MemoryImporter, MemoryExporter, JSON format
```

## Key Dependencies
- Epic 23 (Memory Foundation — store, models, persistence)
- Epic 24 (Memory Intelligence — decay, contradictions, GC)
- Epic 3 (Expert System — expert engine for injection hook)
- Epic 4 (Project Context — project profile for seeding)
- Epic 8 (Pipeline Orchestration — pipeline stage integration)
- Epic 18 (Engagement Level — gating memory injection by level)

## Engagement Level Behavior Summary

| Feature | High | Medium | Low |
|---|---|---|---|
| Memory storage | Always | Always | Always |
| Memory injection into experts | Automatic (up to 5) | Confidence > 0.5 (up to 3) | Never |
| Profile seeding | Automatic | Automatic | On request |
| Contradiction check at start | Automatic | Automatic | On request |
| GC at session start | Automatic | Automatic | On request |
| Checklist requirement | Recommended | Optional | Optional |
