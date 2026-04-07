# Epic 95: Memory System Extraction — Become tapps-brain Client

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P1 - High
**Estimated LOE:** ~2 weeks (1 developer)
**Dependencies:** tapps-brain v2.1+ (must support all 33 action equivalents), AgentForge EPIC-14 (Memory Consolidation — coordinated migration)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that tapps-mcp stops maintaining its own SQLite memory store (.tapps-mcp/memory/) and instead becomes a thin client to tapps-brain. Currently tapps_memory has 33 actions with its own persistence, tiering, scoping, GC, consolidation, federation, and hive operations — duplicating what tapps-brain provides as a dedicated service. This extraction eliminates ~2000+ lines of memory infrastructure code and ensures all memory consumers (tapps-mcp, AgentForge, other MCP clients) share one source of truth.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Replace tapps-mcp's internal SQLite memory store with tapps-brain API calls. The tapps_memory tool interface stays the same (33 actions) but the backend changes from local SQLite to tapps-brain. Remove local persistence code, GC logic, consolidation engine, and hive implementation in favor of tapps-brain's native capabilities.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

tapps-mcp maintains a full memory subsystem: SQLite database, tiered storage (architectural/pattern/context), scoped entries (project/branch/session), garbage collection, consolidation, contradiction detection, federation, hive operations, import/export, and health checks. tapps-brain provides all of these capabilities as a dedicated service. Running both means: (1) memories saved via tapps-mcp are invisible to AgentForge and other consumers, (2) hive operations in tapps-mcp may conflict with tapps-brain's hive, (3) two codebases implement the same tier/scope/TTL semantics with potential drift, (4) GC runs in two places with different schedules.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] All 33 tapps_memory actions work via tapps-brain backend
- [ ] Local SQLite database (.tapps-mcp/memory/*.db) no longer created or written to
- [ ] Memory auto_recall and auto_capture hooks use tapps-brain API
- [ ] Session notes (tapps_session_notes) persist via tapps-brain with scope=session
- [ ] Hive operations delegate to tapps-brain's native HiveStore
- [ ] Graceful degradation: if tapps-brain is unavailable the tool returns a clear error rather than silently failing
- [ ] Migration script converts existing local SQLite entries to tapps-brain
- [ ] No change to the tapps_memory tool interface — all 33 actions retain their signatures

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 95.1 -- tapps-brain Client Adapter

**Points:** 5

Create a BrainAdapter class that implements the same interface as the current SQLite MemoryStore but delegates all operations to tapps-brain's API. Maps tapps_memory's 33 actions to tapps-brain equivalents: save→MemoryStore.save, search→MemoryStore.search, hive_search→HiveStore.search, etc.

**Tasks:**
- [ ] Implement tapps-brain client adapter
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** tapps-brain Client Adapter is implemented, tests pass, and documentation is updated.

---

### 95.2 -- Replace SQLite Persistence Layer

**Points:** 5

Swap the SQLite-backed MemoryStore with BrainAdapter throughout the codebase. Remove SQLite connection management, schema creation, migration logic, and WAL configuration. Update all callers to use the new adapter.

**Tasks:**
- [ ] Implement replace sqlite persistence layer
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Replace SQLite Persistence Layer is implemented, tests pass, and documentation is updated.

---

### 95.3 -- Migrate GC, Consolidation, and Health to tapps-brain

**Points:** 3

Remove local GC scheduling, consolidation engine, contradiction detection, and health check logic. These are now tapps-brain's responsibility. The tapps_memory actions (gc, consolidate, verify_integrity, safety_check) become pass-through calls to tapps-brain.

**Tasks:**
- [ ] Implement migrate gc, consolidation, and health to tapps-brain
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Migrate GC, Consolidation, and Health to tapps-brain is implemented, tests pass, and documentation is updated.

---

### 95.4 -- Hive Operations Delegation

**Points:** 3

Remove local hive implementation (hive_status, hive_search, hive_propagate, agent_register). These delegate directly to tapps-brain's HiveStore API. Remove any local hive state or caching.

**Tasks:**
- [ ] Implement hive operations delegation
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Hive Operations Delegation is implemented, tests pass, and documentation is updated.

---

### 95.5 -- Memory Hooks Migration (auto_recall, auto_capture)

**Points:** 3

Update the memory_hooks system (auto_recall before turns, auto_capture on session end) to use BrainAdapter instead of local SQLite. Hook configuration in .tapps-mcp.yaml stays the same — only the backend changes.

**Tasks:**
- [ ] Implement memory hooks migration (auto_recall, auto_capture)
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Memory Hooks Migration (auto_recall, auto_capture) is implemented, tests pass, and documentation is updated.

---

### 95.6 -- Data Migration Script and Rollback

**Points:** 2

Create a migration script that reads .tapps-mcp/memory/*.db and imports all entries into tapps-brain with correct tier/scope/metadata mapping. Include dry-run mode, validation report, and rollback to restore local SQLite if needed.

**Tasks:**
- [ ] Implement data migration script and rollback
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Data Migration Script and Rollback is implemented, tests pass, and documentation is updated.

---

### 95.7 -- Graceful Degradation and Error Handling

**Points:** 2

When tapps-brain is unreachable, tapps_memory returns structured errors with clear messaging (not silent failures). Read operations can optionally fall back to a read-only local cache if one exists from a previous migration export.

**Tasks:**
- [ ] Implement graceful degradation and error handling
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Graceful Degradation and Error Handling is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- The BrainAdapter must be async-compatible since tapps-mcp runs in an asyncio event loop
- tapps-brain connection string should be configurable in .tapps-mcp.yaml (brain_url or similar)
- The 33 action interface is preserved — this is a backend swap not an API change
- Session notes (tapps_session_notes) should map to tapps-brain scope=session entries
- Federation actions may need tapps-brain support for cross-project queries — verify API coverage
- Import/export actions change semantics: export from tapps-brain and import to tapps-brain instead of local files

### Cross-repo Coordination with AgentForge EPIC-14

AgentForge EPIC-14 research findings that affect this epic:

- **Invocation log stays in SQLite:** AgentForge descoped invocation_log migration (story 14.4) because stats.py requires SQL aggregation (GROUP BY, SUM, AVG). tapps-mcp's equivalent metrics data should similarly stay in a SQL-friendly format, not move to semantic search. Story 95.2 should scope which tables move and which don't.
- **Conversation data has wrong access pattern:** Ordered sequential retrieval (session turns, ordered logs) is relational, not semantic. If tapps-mcp has any ordered-access data, keep it in SQLite.
- **Dual-write migration phase:** AgentForge uses dual-write → shadow-read → cutover → remove. Story 95.6 should follow the same pattern for data safety. Don't jump straight from local to brain.
- **TTL tier split:** AgentForge revised tier mapping:
  - Stable preferences → architectural (180d)
  - Dynamic facts (schedule, contact) → procedural (30d) not 14d
  - Temporary context → context (14d)
  tapps-mcp's tier mapping should align to avoid divergence.
- **Cache implementation:** Use `cachetools.TTLCache` with `asyncio.Lock` for any read cache, NOT `functools.lru_cache` (synchronous, no TTL).
- **Circuit breaker:** AgentForge integrates its CircuitBreaker with BrainBridge calls. tapps-mcp should add similar circuit breaking to the BrainAdapter (story 95.7) with 2s connect timeout for fast degradation detection.
- **Source of truth:** Once both repos migrate to tapps-brain, it becomes the single authority. MEMORY.md becomes a read-optimized projection (not bidirectional sync). Coordinate this with AgentForge EPIC-14.5.

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Changing tapps-brain's API or adding features to it
- Modifying the tapps_memory tool interface (33 actions stay the same)
- Removing tapps_memory as a tool — it stays but with a different backend

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| All 8 acceptance criteria met | 0/8 | 8/8 | Checklist review |
| All 7 stories completed | 0/7 | 7/7 | Sprint board |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 95.1: tapps-brain Client Adapter
2. Story 95.2: Replace SQLite Persistence Layer
3. Story 95.3: Migrate GC, Consolidation, and Health to tapps-brain
4. Story 95.4: Hive Operations Delegation
5. Story 95.5: Memory Hooks Migration (auto_recall, auto_capture)
6. Story 95.6: Data Migration Script and Rollback
7. Story 95.7: Graceful Degradation and Error Handling

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| tapps-brain API may not have 1:1 equivalents for all 33 actions — gap analysis needed before starting | Medium | High | Run gap analysis before story 95.1. Document which actions have direct equivalents, which need adaptation, and which are unsupported. |
| Network latency: local SQLite reads are ~1ms vs tapps-brain API calls ~10-50ms — may need caching strategy | Medium | Medium | Use cachetools.TTLCache with asyncio.Lock for read cache. Deployment topology matters: in-process SDK ~1-5ms, local HTTP ~3-15ms, remote HTTP borderline. Add circuit breaker with 2s connect timeout. |
| Data migration: existing local memories must not be lost — dry-run validation is critical | High | High | Follow dual-write → shadow-read → cutover → remove pattern (aligned with AgentForge EPIC-14). Dry-run mode validates before cutover. Rollback capability in story 95.6. |
| Coordinated rollout with AgentForge EPIC-14 — both repos changing memory backends simultaneously | Medium | Medium | Align tier mapping (preferences→180d, dynamic→30d, context→14d). Coordinate source-of-truth resolution: tapps-brain is authority, MEMORY.md becomes projection. |
| Ordered/relational data has wrong access pattern for semantic search | Medium | High | Not all data should migrate. Metrics, logs, and ordered-access data should stay in SQLite. Scope story 95.2 to explicitly exclude relational data. |

<!-- docsmcp:end:risk-assessment -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Story | Action |
|---|---|---|
| Files will be determined during story refinement | - | - |

<!-- docsmcp:end:files-affected -->

<!-- docsmcp:start:performance-targets -->
## Performance Targets

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Test coverage | baseline | >= 80% | pytest --cov |
| Acceptance criteria pass rate | 0% | 100% | CI pipeline |
| Story completion rate | 0% | 100% | Sprint tracking |

<!-- docsmcp:end:performance-targets -->
