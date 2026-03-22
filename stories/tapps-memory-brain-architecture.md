# How the TappsMCP Memory Brain Works

> A deep-dive technical reference for the `tapps_memory` subsystem - the persistent,
> cross-session knowledge store that gives TappsMCP a "brain."

---

## 1. High-Level Architecture

```
                         MCP Tool Layer
                   ┌──────────────────────┐
                   │  tapps_memory(action) │  28 actions
                   │  server_memory_tools  │
                   └──────────┬───────────┘
                              │
                   ┌──────────▼───────────┐
                   │     MemoryStore       │  In-memory dict + write-through
                   │   (tapps-core/memory  │
                   │      /store.py)       │
                   └──────────┬───────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
  ┌───────▼────────┐  ┌──────▼──────┐  ┌────────▼────────┐
  │MemoryPersistence│  │ Retrieval   │  │ Federation      │
  │  SQLite + WAL   │  │ BM25+Vector │  │ Hub (~/.tapps-  │
  │  FTS5 search    │  │ Reranking   │  │ mcp/memory/)    │
  │  Audit JSONL    │  │ Relations   │  │ federated.db    │
  └────────────────┘  └─────────────┘  └─────────────────┘
```

**Core principle:** The memory system is **fully deterministic** -- no LLM calls anywhere in
the pipeline. Same input always produces same output. All intelligence comes from algorithms:
BM25 ranking, exponential decay, similarity scoring, relation extraction.

**Storage:** SQLite with WAL journal mode (concurrent reads during writes), FTS5 for
full-text search, schema versioning with forward migrations (currently v4).

**Location:** `{project_root}/.tapps-mcp/memory/memory.db` (project-local) +
`~/.tapps-mcp/memory/federated.db` (cross-project hub).

---

## 2. Data Model

### MemoryEntry (Pydantic v2)

Source: [`packages/tapps-core/src/tapps_core/memory/models.py`](packages/tapps-core/src/tapps_core/memory/models.py)

| Field | Type | Description |
|---|---|---|
| `key` | `str` | Lowercase slug, 1-128 chars. Regex: `^[a-z0-9][a-z0-9._-]{0,127}$` |
| `value` | `str` | Content, max 4096 chars, non-empty |
| `tier` | `MemoryTier` | Decay classification (see below) |
| `confidence` | `float` | 0.0-1.0. `-1.0` means "use source default" |
| `source` | `MemorySource` | `human` / `agent` / `inferred` / `system` |
| `source_agent` | `str` | Agent identifier (e.g. "claude-code") |
| `scope` | `MemoryScope` | `project` / `branch` / `session` / `shared` |
| `tags` | `list[str]` | Free-form, max 10 |
| `branch` | `str?` | Required when scope=branch |
| `created_at` | `str` | ISO-8601 UTC |
| `updated_at` | `str` | ISO-8601 UTC |
| `last_accessed` | `str` | ISO-8601 UTC, updated on every `get()` |
| `access_count` | `int` | Incremented on every `get()` |
| `last_reinforced` | `str?` | Set by `reinforce` action |
| `reinforce_count` | `int` | Total reinforcements |
| `contradicted` | `bool` | Set by contradiction detection or consolidation |
| `contradiction_reason` | `str?` | Why it was marked contradicted |
| `seeded_from` | `str?` | Set by auto-seeding (e.g. "project_profile") |
| `embedding` | `list[float]?` | Optional vector for semantic search |

### ConsolidatedEntry (extends MemoryEntry)

| Field | Type | Description |
|---|---|---|
| `source_ids` | `list[str]` | Keys of entries that were consolidated |
| `consolidated_at` | `str` | ISO-8601 UTC when consolidation occurred |
| `consolidation_reason` | `ConsolidationReason` | `similarity` / `same_topic` / `supersession` / `manual` |
| `is_consolidated` | `bool` | Always `True` |

### Source-based confidence defaults

When `confidence=-1.0` (auto), the model validator applies:

| Source | Default Confidence |
|---|---|
| `human` | 0.95 |
| `system` | 0.90 |
| `agent` | 0.60 |
| `inferred` | 0.40 |

---

## 3. Memory Tiers & Decay

Source: [`packages/tapps-core/src/tapps_core/memory/decay.py`](packages/tapps-core/src/tapps_core/memory/decay.py)

### Exponential decay formula

```
effective_confidence = confidence * 0.5^(days / half_life)
```

Decay is **lazy** -- computed at read-time only. No background threads or timers.

| Tier | Half-life | Purpose | Confidence Ceiling (H/A/I/S) |
|---|---|---|---|
| `architectural` | 180 days | Project structure, design decisions | 0.95 / 0.85 / 0.70 / 0.95 |
| `pattern` | 60 days | Coding patterns, conventions | 0.95 / 0.85 / 0.70 / 0.95 |
| `procedural` | 30 days | Workflows, how-to steps | 0.95 / 0.85 / 0.70 / 0.95 |
| `context` | 14 days | Session-specific temporary context | 0.95 / 0.85 / 0.70 / 0.95 |

**Stale threshold:** 0.3 effective confidence (configurable).
**Confidence floor:** 0.1 (can't decay below this).
**Decay reference time:** Uses `last_reinforced` if set, otherwise `updated_at`.

---

## 4. Memory Scopes

| Scope | Behavior |
|---|---|
| `project` | Visible across the entire project (default) |
| `branch` | Scoped to a git branch (requires `branch` param) |
| `session` | Ephemeral, auto-GC'd after 7 days |
| `shared` | Eligible for cross-project federation |

**Scope resolution on `get()`:** session > branch > project (most specific wins).

---

## 5. The MemoryStore

Source: [`packages/tapps-core/src/tapps_core/memory/store.py`](packages/tapps-core/src/tapps_core/memory/store.py)

### Architecture

- **In-memory dict** (`self._entries: dict[str, MemoryEntry]`) for fast reads
- **Write-through** to SQLite on every mutation
- **Thread-safe** via `threading.Lock()` on all operations
- **Cold-start:** loads all entries from SQLite into memory on initialization

### Capacity & eviction

- **Max entries:** 500 per project (hardcoded `_MAX_ENTRIES`)
- **Eviction policy:** When full, evicts the entry with the lowest `confidence`
- The YAML config `max_memories: 1500` is the upper-bound intent but the store itself enforces 500

### Save flow

```
save(key, value, tier, source, ...)
  ├─ 1. Write rules validation (blocked keywords, min/max length)
  ├─ 2. RAG safety check (content_safety.check_content_safety)
  │     ├─ >= 3 matches → BLOCKED (returns error dict)
  │     └─ < 3 matches → sanitized value used
  ├─ 3. Build MemoryEntry (preserves created_at, access_count etc. on update)
  ├─ 4. Evict lowest-confidence entry if at capacity
  ├─ 5. Update in-memory dict
  ├─ 6. Compute embedding if semantic search enabled
  ├─ 7. Persist to SQLite
  └─ 8. Auto-consolidation check (if enabled and not already consolidating)
```

### Get flow

```
get(key, scope?, branch?)
  ├─ 1. Scope resolution if scope+branch provided (session > branch > project)
  ├─ 2. Update access metadata (last_accessed, access_count++)
  └─ 3. Persist updated metadata to SQLite
```

---

## 6. Persistence Layer

Source: [`packages/tapps-core/src/tapps_core/memory/persistence.py`](packages/tapps-core/src/tapps_core/memory/persistence.py)

### SQLite configuration

```python
PRAGMA journal_mode=WAL     # Concurrent reads during writes
PRAGMA busy_timeout=5000    # Wait up to 5s for locks
PRAGMA foreign_keys=ON
```

### Schema (v4)

| Table | Purpose |
|---|---|
| `memories` | Main entry store (PK: `key`) |
| `memories_fts` | FTS5 virtual table on key, value, tags |
| `archived_memories` | GC'd entries (no longer active) |
| `session_index` | Session chunks (PK: session_id + chunk_index) |
| `session_index_fts` | FTS5 on session chunks |
| `relations` | Entity/relationship triples (PK: subject + predicate + object) |
| `schema_version` | Migration tracking |

### FTS5 sync triggers

Three triggers keep `memories_fts` in sync with `memories`:
- `memories_ai` (AFTER INSERT)
- `memories_ad` (AFTER DELETE)
- `memories_au` (AFTER UPDATE - delete old + insert new)

Same pattern for `session_index_fts`.

### Audit log

Every `save` and `delete` appends a JSONL record to `memory_log.jsonl`:
```json
{"action": "save", "key": "project-type", "timestamp": "2026-03-18T..."}
```
Truncated to 10,000 lines when exceeded (keeps most recent).

### Schema migrations

Forward-only, applied sequentially:
- v1: Base schema (memories, memories_fts, archived_memories, triggers)
- v2: Added `embedding TEXT` column
- v3: Added `session_index` + `session_index_fts` tables
- v4: Added `relations` table

---

## 7. Retrieval & Ranking

Source: [`packages/tapps-core/src/tapps_core/memory/retrieval.py`](packages/tapps-core/src/tapps_core/memory/retrieval.py)

### MemoryRetriever

The retrieval engine uses a **3-tier fallback chain**:

```
1. FTS5 (via store.search) → candidates
   └─ Score candidates with BM25
2. Full corpus BM25 scan (if FTS5 returns nothing)
3. Word overlap (if BM25fails)
```

### Composite scoring formula

```
score = 0.40 * relevance + 0.30 * confidence + 0.15 * recency + 0.15 * frequency
```

| Signal | Weight | Formula |
|---|---|---|
| Relevance | 40% | `bm25_score / (bm25_score + 5.0)` (sigmoid normalization) |
| Confidence | 30% | Time-decayed effective confidence |
| Recency | 15% | `1.0 / (1.0 + days_since_updated)` |
| Frequency | 15% | `min(1.0, access_count / 20)` |

**Bonus:** +0.1 for exact key match (query slug matches entry key).

### BM25 engine

Source: [`packages/tapps-core/src/tapps_core/memory/bm25.py`](packages/tapps-core/src/tapps_core/memory/bm25.py)

- Okapi BM25 (k1=1.2, b=0.75)
- Preprocessing: lowercase, tokenize, stop-word removal (~50 words), suffix stripping
- IDF: `log((N - df + 0.5) / (df + 0.5) + 1)`
- Index auto-rebuilds when corpus fingerprint changes

### Hybrid search (optional)

When `semantic_search.enabled=true`:
1. Run BM25 and vector search **in parallel** (ThreadPoolExecutor)
2. Merge results via **Reciprocal Rank Fusion** (RRF, k=60)
3. RRF formula per document: `score = sum(1/(k + rank))` across both lists

Source: [`packages/tapps-core/src/tapps_core/memory/fusion.py`](packages/tapps-core/src/tapps_core/memory/fusion.py)

### Reranking (optional)

When enabled, takes top 20 BM25 candidates and reranks to top_k via pluggable provider.

Source: [`packages/tapps-core/src/tapps_core/memory/reranker.py`](packages/tapps-core/src/tapps_core/memory/reranker.py)

### Retrieval policy

Sensitive tags can be blocked from search results via `retrieval_policy.block_sensitive_tags`.

### Consolidated source filtering

By default, entries that were consolidated into other entries (marked with `contradicted=True` + reason containing "consolidated into") are filtered out of search results. Pass `include_sources=True` to see them.

---

## 8. Similarity & Consolidation

### Similarity detection

Source: [`packages/tapps-core/src/tapps_core/memory/similarity.py`](packages/tapps-core/src/tapps_core/memory/similarity.py)

Combined similarity = `0.4 * tag_similarity + 0.6 * text_similarity`

| Component | Algorithm |
|---|---|
| Tag similarity | Jaccard: `|A ∩ B| / |A ∪ B|` |
| Text similarity | TF-based cosine similarity after BM25 preprocessing |

**Threshold:** 0.7 (default) for consolidation trigger.

**Same-topic detection:** Binary signal -- returns 1.0 if same tier AND >= 50% tag overlap.

**Clustering:** Greedy algorithm for batch consolidation. For each unassigned entry, find all similar unassigned entries above threshold and form a group.

### Consolidation engine

Source: [`packages/tapps-core/src/tapps_core/memory/consolidation.py`](packages/tapps-core/src/tapps_core/memory/consolidation.py)

**Merging rules (deterministic, no LLM):**

| Aspect | Strategy |
|---|---|
| **Key** | Common prefix from source keys + MD5 hash suffix (8 chars) |
| **Value** | Newest entry's value + unique sentences from older entries (`[From key]:`) |
| **Confidence** | Weighted average with recency bias: weight = `0.5^position` (newest=1.0, next=0.5, ...) |
| **Tags** | Top 10 by frequency across sources, sorted by count desc then alpha |
| **Tier** | Most durable from sources (architectural > pattern > procedural > context) |
| **Scope** | Newest entry's scope |
| **Source entries** | Marked `contradicted=True` + reason="consolidated into {key}" but **retained** for provenance |

### Auto-consolidation

Source: [`packages/tapps-core/src/tapps_core/memory/auto_consolidation.py`](packages/tapps-core/src/tapps_core/memory/auto_consolidation.py)

**On save:** After saving a new entry, if config `enabled=true`:
- Find similar entries above threshold
- If >= `min_entries` matches, consolidate
- **Non-reentrant:** `_consolidation_in_progress` flag prevents infinite loops

**Periodic scan:** Runs at session start if >= 7 days since last scan:
- Finds consolidation groups across all active (non-contradicted) entries
- Consolidates each group
- Saves state to `.tapps-mcp/memory/consolidation-state.json`

### Unconsolidate

Reverses consolidation: restores source entries' `contradicted=False`, deletes the consolidated entry.

---

## 9. Entity Relations

Source: [`packages/tapps-core/src/tapps_core/memory/relations.py`](packages/tapps-core/src/tapps_core/memory/relations.py)

**Rule-based relation extraction** from memory values using regex patterns:

```
{Subject} manages/owns/handles/uses/depends on/creates/provides {Object}
```

- Max 5 relations per entry
- Min 2 chars per entity
- Stored in SQLite `relations` table as (subject, predicate, object_entity) triples

**Query expansion:** For queries like "who handles API", traverses the relation graph (up to 2 hops) to find connected entities and expand the search query.

---

## 10. Garbage Collection

Source: [`packages/tapps-core/src/tapps_core/memory/gc.py`](packages/tapps-core/src/tapps_core/memory/gc.py)

**Three archival criteria (any one triggers):**

| # | Criterion | Threshold |
|---|---|---|
| 1 | Effective confidence at floor | For 30+ consecutive days |
| 2 | Contradicted AND low confidence | confidence < 0.2 |
| 3 | Session-scoped AND expired | 7+ days since last update |

**Archive destination:** Moved to `archived_memories` SQLite table + appended to `memory_log.jsonl`.

**"Days at floor" calculation:** Solves the decay formula in reverse:
`days_to_floor = half_life * log2(confidence / floor)`

---

## 11. Reinforcement

Source: [`packages/tapps-core/src/tapps_core/memory/reinforcement.py`](packages/tapps-core/src/tapps_core/memory/reinforcement.py)

Reinforcing a memory:
1. Resets `last_reinforced` to now (resets the decay clock)
2. Increments `reinforce_count`
3. Optional confidence boost (0.0 to 0.2 max)
4. Clamped to source-based ceiling

---

## 12. Contradiction Detection

Source: [`packages/tapps-core/src/tapps_core/memory/contradictions.py`](packages/tapps-core/src/tapps_core/memory/contradictions.py)

Compares memories against **observable project state** (from `detect_project_profile()`):

| Check | Triggered by tags | What it compares |
|---|---|---|
| Tech stack | `library`, `framework`, `database`, etc. | Memory claims vs detected libraries/frameworks |
| File existence | `file`, `path`, `module` | Referenced file paths vs filesystem |
| Test frameworks | `test`, `testing`, `test-framework` | Mentioned frameworks vs detected ones |
| Package managers | `package-manager`, `build-tool` | Mentioned PMs vs detected ones |
| Branch existence | `branch`, `feature-branch` | Scoped branch vs `git branch --list` |

All detection is deterministic -- regex pattern matching against project profile data.

---

## 13. Memory Injection

Source: [`packages/tapps-core/src/tapps_core/memory/injection.py`](packages/tapps-core/src/tapps_core/memory/injection.py)

When `inject_into_experts=true`, relevant memories are injected into expert consultation and research responses:

1. Search memories by question using MemoryRetriever
2. Filter by minimum score (0.3) and engagement level limits
3. RAG safety check on each value (defense-in-depth)
4. Token budget enforcement (default: 2000 tokens, ~8000 chars)
5. Format as markdown `### Project Memory` section
6. Append to expert/research answer

| Engagement Level | Max Memories | Min Confidence |
|---|---|---|
| high | 5 | 0.3 |
| medium | 3 | 0.5 |
| low | 0 (disabled) | - |

---

## 14. Cross-Project Federation

Source: [`packages/tapps-core/src/tapps_core/memory/federation.py`](packages/tapps-core/src/tapps_core/memory/federation.py)

**All operations are explicit** -- no automatic sharing.

### Hub

- Location: `~/.tapps-mcp/memory/`
- Config: `federation.yaml` (projects, subscriptions)
- Database: `federated.db` (SQLite, FTS5)
- Composite PK: `(project_id, key)`
- Limits: 50 projects, 50 subscriptions

### Flow

```
Project A                      Hub                         Project B
    │                           │                              │
    ├─ register ───────────────►│◄──────────── register ───────┤
    │                           │                              │
    ├─ publish (shared scope) ─►│                              │
    │                           │◄── subscribe (tag/conf) ─────┤
    │                           │                              │
    │                           ├── sync (pull) ──────────────►│
    │                           │   (local always wins)        │
    │                           │                              │
    ├─ federated_search ───────►│◄──── federated_search ───────┤
    │   (1.2x local boost)     │                              │
```

### Conflict resolution

- **Local always wins** on key collision during sync
- Imported entries tagged with `federated` + `from:{source_id}`

---

## 15. Session Indexing

Source: [`packages/tapps-core/src/tapps_core/memory/session_index.py`](packages/tapps-core/src/tapps_core/memory/session_index.py)

Stores chunks of session text for searchability:
- Max 50 chunks per session, 500 chars each
- FTS5-searchable
- TTL-based cleanup (default 7 days)
- Stored in separate `session_index` table

---

## 16. Profile Seeding

Source: [`packages/tapps-core/src/tapps_core/memory/seeding.py`](packages/tapps-core/src/tapps_core/memory/seeding.py)

On first run (empty store), auto-populates memories from `detect_project_profile()`:
- Project type, languages, frameworks, test frameworks, package managers, CI systems, Docker
- All tagged `auto-seeded`, source=system, confidence=0.9
- `seeded_from` field set to "project_profile"
- `reseed` action deletes old auto-seeded entries and re-creates from current profile

---

## 17. Import/Export

Source: [`packages/tapps-core/src/tapps_core/memory/io.py`](packages/tapps-core/src/tapps_core/memory/io.py)

### Export formats

| Format | Features |
|---|---|
| JSON | Full Pydantic model dump with metadata envelope |
| Markdown | Obsidian-friendly with YAML frontmatter, groupable by tier/tag/none |

### Import

- JSON only (from export format)
- Max 500 entries per import
- Overwrite flag (default: skip existing keys)
- Imported entries marked with `(imported)` suffix on source_agent

---

## 18. The 23 MCP Actions

All dispatched through `tapps_memory(action, ...)` in `server_memory_tools.py`:

### CRUD (5)
| Action | Description |
|---|---|
| `save` | Create/update entry (with RAG safety + auto-consolidation) |
| `save_bulk` | Save up to 50 entries in one call |
| `get` | Retrieve by key with scope resolution + access tracking |
| `list` | List all entries with tier/scope/tag filters |
| `delete` | Remove entry by key |

### Search (1)
| Action | Description |
|---|---|
| `search` | FTS5 + BM25 ranked search with composite scoring |

### Intelligence (5)
| Action | Description |
|---|---|
| `reinforce` | Reset decay clock, optional confidence boost |
| `gc` | Archive stale memories (3 criteria) |
| `contradictions` | Detect memories contradicting project state |
| `reseed` | Re-populate from project profile |
| `maintain` | Combined: GC + consolidation scan + deduplication |

### Consolidation (2)
| Action | Description |
|---|---|
| `consolidate` | Merge 2+ related entries into one (supports dry-run) |
| `unconsolidate` | Undo consolidation, restore source entries |

### Import/Export (2)
| Action | Description |
|---|---|
| `import` | Load from JSON file (with overwrite flag) |
| `export` | Write to JSON or Markdown |

### Federation (6)
| Action | Description |
|---|---|
| `federate_register` | Register project in hub |
| `federate_publish` | Publish shared-scope memories to hub |
| `federate_subscribe` | Subscribe to memories from other projects |
| `federate_sync` | Pull subscribed memories into local store |
| `federate_search` | Search across local + hub (local gets 1.2x boost) |
| `federate_status` | Show hub stats, projects, subscriptions |

### Advanced (2)
| Action | Description |
|---|---|
| `index_session` | Store session chunks for search |
| `validate` | Check entries against authoritative docs |

---

## 19. Safety & Security

### RAG safety check
- Applied on every `save()` and before every injection
- Uses `check_content_safety()` from security module
- >= 3 pattern matches → content **blocked**
- < 3 matches → content **sanitized** (flagged patterns removed)

### Write rules
- Configurable blocked keywords list
- Min/max value length enforcement
- Toggled via `enforced` flag

### Path validation
- All file I/O goes through `PathValidator` (sandbox enforcement)
- Prevents path traversal attacks

### Retrieval policy
- `block_sensitive_tags` prevents tagged entries from appearing in search

---

## 20. Configuration

From [`packages/tapps-core/src/tapps_core/config/default.yaml`](packages/tapps-core/src/tapps_core/config/default.yaml):

```yaml
memory:
  enabled: true
  gc_enabled: true
  contradiction_check_on_start: true
  max_memories: 1500
  injection_max_tokens: 2000
  inject_into_experts: true

  decay:
    architectural_half_life_days: 180
    pattern_half_life_days: 60
    procedural_half_life_days: 30
    context_half_life_days: 14
    confidence_floor: 0.1

  semantic_search:
    enabled: false
    provider: sentence_transformers
    model: all-MiniLM-L6-v2

  session_index:
    enabled: false
    max_chunks_per_session: 50
    max_chars_per_chunk: 500
    ttl_days: 7
```

---

## 21. File Map (24 modules)

All in `packages/tapps-core/src/tapps_core/memory/`:

| Module | Purpose | Lines |
|---|---|---|
| `models.py` | Pydantic models (MemoryEntry, ConsolidatedEntry, enums) | 245 |
| `store.py` | In-memory cache + write-through (MemoryStore) | 456 |
| `persistence.py` | SQLite layer (WAL, FTS5, migrations, audit log) | 661 |
| `decay.py` | Exponential decay engine (lazy, read-time) | 158 |
| `retrieval.py` | Ranked retrieval (BM25 + hybrid + reranking) | 615 |
| `bm25.py` | Okapi BM25 scorer (pure Python) | 167 |
| `similarity.py` | Jaccard + TF-IDF cosine for consolidation | 316 |
| `consolidation.py` | Deterministic merging engine | 445 |
| `auto_consolidation.py` | On-save and periodic consolidation triggers | 366 |
| `gc.py` | Garbage collection (3-criteria archival) | 164 |
| `reinforcement.py` | Decay clock reset + confidence boost | 61 |
| `contradictions.py` | State-based contradiction detection | 248 |
| `relations.py` | Entity/relationship extraction + query expansion | 314 |
| `federation.py` | Cross-project sharing (hub, sync, search) | 760 |
| `injection.py` | Memory injection into expert responses | 184 |
| `seeding.py` | Auto-populate from project profile | 229 |
| `session_index.py` | Session chunk indexing + search | 98 |
| `io.py` | Import/export (JSON + Markdown) | 337 |
| `fusion.py` | Reciprocal Rank Fusion for hybrid search | 43 |
| `reranker.py` | Pluggable semantic reranker | ~80 |
| `embeddings.py` | Embedding provider (SentenceTransformer) | ~60 |
| `doc_validation.py` | Async validation against Context7 docs | ~80 |
| `extraction.py` | Memory extraction helpers | ~40 |
| `__init__.py` | Package exports | ~10 |

---

## 22. Key Design Patterns

1. **Lazy decay** -- No background jobs; confidence decayed at read-time only
2. **Write-through caching** -- In-memory dict synced with SQLite on every write
3. **Provenance preservation** -- Source entries never deleted on consolidation; marked contradicted
4. **Deterministic merging** -- No LLM calls; newest-wins + unique context extraction
5. **Thread safety** -- Single global lock on all mutations
6. **Fallback chain** -- FTS5 -> BM25 -> word overlap (graceful degradation)
7. **Composite scoring** -- Multiple signals (relevance, confidence, recency, frequency)
8. **Scope resolution** -- Explicit precedence (session > branch > project)
9. **Explicit federation** -- No auto-sharing; projects must register and subscribe
10. **Non-reentrant consolidation** -- Flag prevents infinite loops on save

---

## 23. Data Flow Diagrams

### Save + Auto-Consolidate

```
User/Agent
    │
    ▼
tapps_memory(action="save", key="...", value="...", tier="pattern")
    │
    ├─ Write rules check ──► BLOCK if keyword matched
    ├─ RAG safety check ───► BLOCK if >= 3 matches, SANITIZE if < 3
    │
    ▼
MemoryStore.save()
    ├─ Build MemoryEntry (Pydantic validation)
    ├─ Evict lowest-confidence if at 500 cap
    ├─ Update in-memory dict
    ├─ Compute embedding (if enabled)
    ├─ Persist to SQLite (INSERT OR REPLACE)
    │     └─ FTS5 triggers fire automatically
    ├─ Audit log append
    └─ Auto-consolidation check
         ├─ _consolidation_in_progress? → skip
         ├─ Find similar entries (Jaccard + TF-IDF)
         ├─ >= min_entries similar? → consolidate()
         │     ├─ Generate merged key
         │     ├─ Merge values (newest-wins + unique sentences)
         │     ├─ Calculate weighted confidence
         │     ├─ Save ConsolidatedEntry (skip_consolidation=True)
         │     └─ Mark source entries contradicted
         └─ Clear _consolidation_in_progress flag
```

### Search

```
User/Agent
    │
    ▼
tapps_memory(action="search", query="...")
    │
    ▼
MemoryRetriever.search()
    ├─ Expand query via relations (if enabled)
    │
    ├─ [semantic_enabled?]
    │     ├─ YES → Hybrid path
    │     │     ├─ BM25 search (parallel)
    │     │     ├─ Vector search (parallel)
    │     │     └─ RRF fusion
    │     └─ NO → BM25 path
    │           ├─ FTS5 candidates → BM25 scoring
    │           └─ Fallback: full BM25 scan → word overlap
    │
    ├─ Filter: contradicted, consolidated sources, low confidence
    ├─ Score: relevance(40%) + confidence(30%) + recency(15%) + frequency(15%)
    ├─ Apply retrieval policy tag filtering
    ├─ Sort by composite score
    ├─ Rerank top-20 (if enabled)
    └─ Return top-N ScoredMemory results
```
