# Epic 24: Memory Intelligence

**Status:** Proposed
**Priority:** P1 — High (prevents stale/contradictory memories, enables trust in the memory system)
**Estimated LOE:** ~2-3 weeks (1 developer)
**Dependencies:** Epic 23 (Shared Memory Foundation), Epic 4 (Project Context — project profile), Epic 5 (Adaptive Learning — weight/confidence patterns)
**Blocks:** Epic 25 (Memory Retrieval & Integration)

---

## Goal

Add intelligence to the memory system: time-based decay that degrades memories at tier-appropriate rates, contradiction detection that flags memories invalidated by codebase changes, confidence scoring that strengthens memories through reinforcement and weakens them through neglect, and cross-validation against `tapps_project_profile` to auto-detect stale facts. Without this epic, the memory store is just a persistent key-value store. With it, the memory store becomes a self-maintaining knowledge base that the team can trust.

## Motivation

The most dangerous memory system is one that confidently serves stale information. An agent that says "we use SQLAlchemy" six months after a migration to Prisma causes more harm than an amnesiac agent. This epic ensures memories earn and lose trust based on evidence, not just recency.

## 2026 Best Practices Applied

- **Decay-on-read, not decay-on-timer** — No background threads or cron jobs. Confidence recalculation happens lazily when memories are accessed. This is simpler, more testable, and avoids the complexity of scheduled tasks in an MCP server. Aligns with research showing that access-based + time-based hybrid decay outperforms pure time-based approaches (ICLR 2026 MemAgents workshop findings).
- **Evidence-based confidence** — Confidence changes are always traceable to a specific event (access, reinforcement, contradiction, age). The SQLite audit log records every confidence mutation. This addresses the 2026 research finding that "importance-based approaches require reliable estimation of memory significance" — we ground significance in observable evidence, not heuristics.
- **Deterministic contradiction detection** — Contradictions are detected by comparing memory claims against observable project state (tech stack, file existence, import graph), not by LLM interpretation. Same project state always produces the same contradiction flags.
- **Graceful degradation** — A memory with decayed confidence is still returned, but with a `stale: true` flag and the original vs. current confidence. The consuming agent decides whether to trust it. This avoids the 2026 research concern that "time-based decay may prematurely remove infrequently accessed but important memories."
- **Intelligent forgetting, not aggressive pruning** — GC archives (never deletes) and only after sustained low confidence. Archived memories can be recovered. This addresses the known challenge that "access-based policies retain frequently used memories but may preserve outdated information" — contradiction detection handles that separately.

## Acceptance Criteria

- [ ] Decay engine recalculates confidence on read based on tier-specific half-lives
- [ ] Architectural memories: half-life of 180 days (6 months)
- [ ] Pattern memories: half-life of 60 days (2 months)
- [ ] Context memories: half-life of 14 days (2 weeks)
- [ ] Reinforcement: accessing a memory and confirming it (via `tapps_memory reinforce`) resets its decay clock
- [ ] Contradiction detector compares memories against `tapps_project_profile` output
- [ ] Contradicted memories are flagged with `contradicted: true` and `contradiction_reason`
- [ ] Confidence floor: memories never decay below 0.1 (they become very weak but are still findable)
- [ ] Confidence ceiling: human-sourced memories cap at 0.95, agent-sourced at 0.85
- [ ] `tapps_memory` tool gains `reinforce` and `contradictions` actions
- [ ] Decay and contradiction events logged to `memory_log.jsonl` for auditability
- [ ] Garbage collection: memories below confidence 0.1 for 30+ days are archived (moved to `memory_archive.jsonl`, removed from active store)
- [ ] Unit tests: ~35 tests (decay ~12, contradiction ~10, reinforcement ~5, GC ~5, integration ~3)

---

## Stories

### 24.1 — Decay Engine

**Points:** 5

Implement the time-based decay model that recalculates confidence on read.

**Tasks:**
- Create `src/tapps_mcp/memory/decay.py` with:
  - `DecayConfig` model:
    - `architectural_half_life_days: int = 180`
    - `pattern_half_life_days: int = 60`
    - `context_half_life_days: int = 14`
    - `confidence_floor: float = 0.1`
    - `human_confidence_ceiling: float = 0.95`
    - `agent_confidence_ceiling: float = 0.85`
    - `inferred_confidence_ceiling: float = 0.70`
  - `calculate_decayed_confidence(entry: MemoryEntry, config: DecayConfig) -> float`:
    - Uses exponential decay: `confidence * (0.5 ^ (days_since_last_reinforced / half_life))`
    - `days_since_last_reinforced` = days since `updated_at` (or `last_reinforced` if reinforced)
    - Clamp to `[confidence_floor, source_ceiling]`
  - `is_stale(entry: MemoryEntry, config: DecayConfig, threshold: float = 0.3) -> bool`
  - `get_effective_confidence(entry: MemoryEntry, config: DecayConfig) -> tuple[float, bool]`:
    - Returns `(decayed_confidence, is_stale)` — the read-time confidence
- Add `last_reinforced: str | None` field to `MemoryEntry` model (Epic 23)
- Add `effective_confidence: float | None` and `stale: bool` to tool response (computed, not stored)
- Integrate into `MemoryStore.get()` and `MemoryStore.list_all()` — all reads return decayed confidence
- Decay config loaded from `.tapps-mcp.yaml` (new `memory.decay` section) with sensible defaults
- Write ~12 unit tests:
  - Fresh memory returns original confidence
  - Memory at half-life returns ~50% confidence
  - Memory at double half-life returns ~25% confidence
  - Confidence floor prevents zero
  - Ceiling enforcement per source type
  - Different tiers decay at different rates
  - Stale threshold detection

**Definition of Done:** All reads return time-decayed confidence. Tier-specific half-lives work. Configurable via YAML.

---

### 24.2 — Reinforcement

**Points:** 3

Enable agents and humans to reinforce memories, resetting the decay clock.

**Tasks:**
- Add `reinforce` action to `tapps_memory` tool:
  - Parameters: `key`, optional `confidence_boost: float` (default 0.0, max 0.2)
  - Behavior:
    - Sets `last_reinforced` to now
    - Optionally increases base confidence by `confidence_boost` (capped at source ceiling)
    - Logs reinforcement event to `memory_log.jsonl`
  - Response: updated memory entry with new effective confidence
- Implicit reinforcement: `tapps_memory get` increments `access_count` and optionally touches `last_accessed` (but does NOT reset decay — only explicit reinforce does)
- Add reinforcement tracking fields to `MemoryEntry`:
  - `last_reinforced: str | None` — ISO-8601 UTC
  - `reinforce_count: int = 0` — total reinforcements
- Write ~5 unit tests:
  - Reinforce resets decay clock
  - Confidence boost respects ceiling
  - Multiple reinforcements accumulate count
  - Implicit access does not reset decay
  - Reinforcement logged to JSONL

**Definition of Done:** Reinforcement resets decay. Confidence boost works within bounds. Audit logged.

---

### 24.3 — Contradiction Detection

**Points:** 5

Detect memories that contradict observable project state.

**Tasks:**
- Create `src/tapps_mcp/memory/contradictions.py` with:
  - `ContradictionDetector` class:
    - `detect_contradictions(memories: list[MemoryEntry], profile: ProjectProfile) -> list[Contradiction]`
    - `Contradiction` model: `memory_key, reason, evidence, detected_at`
  - Detection rules (deterministic, no LLM):
    - **Tech stack drift**: Memory mentions a library/framework not in `profile.tech_stack.libraries` or `profile.tech_stack.frameworks`
      - E.g., memory says "we use SQLAlchemy" but profile shows no SQLAlchemy
      - Only triggers for memories with tags containing "library", "framework", "database", "orm", or where value contains the library name as a word boundary match
    - **File existence**: Memory references a specific file path that no longer exists
      - Only for memories with tags containing "file", "path", "module"
      - Check via `Path.exists()` within project root (sandboxed)
    - **Test framework drift**: Memory mentions a test framework not in `profile.test_frameworks`
    - **Package manager drift**: Memory mentions a package manager not in `profile.package_managers`
    - **Branch existence**: Branch-scoped memories where the branch no longer exists (check via `git branch --list`)
  - **Security note**: Memory values read during contradiction detection are not re-filtered for prompt injection — safety is guaranteed by the write-time RAG check in Epic 23.3. Contradiction detection only compares memory metadata (tags, key) against project profile facts; it does not interpret or forward raw memory values to an LLM.
  - Flagging behavior:
    - Contradicted memories get `contradicted: true` and `contradiction_reason: str` fields via `store.update_fields(key, contradicted=True, contradiction_reason=...)` (partial update from Epic 23.3)
    - Confidence is halved on first contradiction detection via `store.update_fields(key, confidence=current/2)`
    - Subsequent detections of the same contradiction do not halve again (idempotent — check `contradicted` flag first)
- Add `contradictions` action to `tapps_memory` tool:
  - Runs contradiction detection against current project profile
  - Returns list of contradicted memories with reasons
- Integration with `tapps_session_start`: optionally run contradiction detection at session start (configurable, default: true)
- Write ~10 unit tests:
  - Tech stack drift detected
  - Missing file detected
  - Non-matching memory tags not flagged (avoid false positives)
  - Contradiction halves confidence (once)
  - Idempotent re-detection
  - Branch-scoped memory with deleted branch

**Definition of Done:** Contradictions detected deterministically. Confidence reduced. Flagged in tool responses.

---

### 24.4 — Garbage Collection & Archival

**Points:** 3

Archive memories that have decayed below usefulness and clean up the active store.

**Tasks:**
- Create `src/tapps_mcp/memory/gc.py` with:
  - `MemoryGarbageCollector` class:
    - `collect(store: MemoryStore, config: DecayConfig) -> GCResult`
    - `GCResult` model: `archived_count, remaining_count, archived_keys`
  - Archive criteria:
    - Effective confidence < `confidence_floor` (0.1) for 30+ consecutive days
    - OR: contradicted AND effective confidence < 0.2
    - OR: session-scoped AND session ended 7+ days ago
  - Archive behavior:
    - Move to `archived_memories` table in `memory.db` (same schema + `archived_at` column)
    - Additionally append to `{project_root}/.tapps-mcp/memory/archive.jsonl` for external visibility
    - Remove from active `memories` table
    - Log GC event to `memory_log.jsonl`
  - Trigger: called during `tapps_session_start` (lazy, at most once per session)
  - Configurable: `memory.gc_enabled: bool = true` in `.tapps-mcp.yaml`
- Add `gc` action to `tapps_memory` tool (manual trigger):
  - Returns GC result with what was archived
- Write ~5 unit tests:
  - Deeply decayed memory gets archived
  - Contradicted low-confidence memory gets archived
  - Above-threshold memory survives GC
  - Archived memories appear in archive.jsonl
  - GC disabled via config skips collection

**Definition of Done:** Stale memories auto-archive. Active store stays clean. Configurable.

---

### 24.5 — Configuration & Observability

**Points:** 2

Make the memory intelligence layer configurable and observable.

**Tasks:**
- Add `memory` section to `.tapps-mcp.yaml` schema (in `config/settings.py`):
  ```yaml
  memory:
    enabled: true
    gc_enabled: true
    contradiction_check_on_start: true
    max_memories: 500
    inject_into_experts: true        # configured in Epic 25, declared here for schema completeness
    decay:
      architectural_half_life_days: 180
      pattern_half_life_days: 60
      context_half_life_days: 14
      confidence_floor: 0.1
  ```
- Add memory metrics to `tapps_dashboard`:
  - Total memories by tier
  - Average confidence by tier
  - Contradiction count
  - GC archive count (last 30 days)
  - Most-accessed memories (top 10)
  - Least-accessed memories (candidates for GC)
- Add memory stats to `tapps_stats`:
  - `memory_total`, `memory_by_tier`, `memory_avg_confidence`, `memory_contradictions`
- Write ~3 integration tests: config loading, dashboard inclusion, stats inclusion

**Definition of Done:** Memory behavior fully configurable via YAML. Metrics visible in dashboard and stats.

---

## Performance Targets

| Operation | Target (p95) | Notes |
|---|---|---|
| Decay calculation (per entry) | < 1ms | Pure math, no I/O |
| Contradiction detection (full scan) | < 500ms | Profile comparison + file existence checks |
| GC run | < 200ms | In-memory scan + file archive |
| Reinforcement | < 50ms | In-memory update + persist |

## File Layout

```
src/tapps_mcp/memory/
    decay.py            # DecayConfig, calculate_decayed_confidence, is_stale
    contradictions.py   # ContradictionDetector, Contradiction model
    gc.py               # MemoryGarbageCollector, GCResult
```

## Key Dependencies
- Epic 23 (Memory Foundation — models, store, persistence)
- Epic 4 (Project Context — ProjectProfile for contradiction detection)
- Epic 5 (Adaptive Learning — confidence/weight adjustment patterns)
- Epic 7 (Metrics & Dashboard — dashboard/stats integration)
