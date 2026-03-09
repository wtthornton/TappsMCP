# Epic 64: Cross-Project Memory Federation

**Status:** Complete
**Priority:** P3
**LOE:** ~3-4 weeks
**Dependencies:** Epic 23-25 (Memory Foundation/Intelligence/Retrieval), Epic 34 (BM25 Upgrade), Epic 58 (Consolidation)

---

## Problem Statement

TappsMCP's memory system stores knowledge in project-scoped SQLite databases at `{project_root}/.tapps-mcp/memory/memory.db`. Each project is an island — knowledge learned in one project (architectural patterns, debugging insights, library best practices) cannot be shared with sibling projects in the same monorepo or related repositories.

This is particularly painful for:
- **Monorepo packages** that share conventions, patterns, and architectural decisions
- **Microservice ecosystems** where the same team works across multiple repos
- **Library consumers** that could benefit from the library author's captured patterns
- **Organizational standards** (coding conventions, security policies) that apply across all projects

## Solution

Add a **federation layer** that enables memory sharing across projects:

1. **Federated memory hub** — a central SQLite store at `~/.tapps-mcp/memory/federated.db`
2. **Publish/subscribe model** — projects publish selected memories to the hub, others subscribe
3. **Scope extension** — new `shared` scope for memories intended for cross-project use
4. **Federated search** — query local + hub memories with project attribution
5. **Conflict resolution** — deterministic merge strategy when the same key exists in multiple projects

## Architecture

### Storage Layout

```
~/.tapps-mcp/
  memory/
    federated.db          ← Central hub (SQLite WAL + FTS5)
    federation.yaml       ← Project registry + subscription config

{project_root}/.tapps-mcp/
  memory/
    memory.db             ← Local project store (unchanged)
```

### Federation Model

```
Project A (local store)          Federated Hub            Project B (local store)
┌──────────────┐     publish     ┌──────────────┐     subscribe   ┌──────────────┐
│ memory.db    │ ───────────────→│ federated.db │←────────────────│ memory.db    │
│ scope=shared │                 │ project_id   │                 │ scope=shared │
└──────────────┘     subscribe   │ origin_key   │     publish     └──────────────┘
                 ←───────────────│ published_at │───────────────→
                                 └──────────────┘
```

### Module: `memory/federation.py` (new, in tapps-core)

Core classes:
- `FederationConfig` — Pydantic model for `federation.yaml`
- `FederatedStore` — manages hub SQLite with project namespacing
- `publish_memories()` — copies shared-scope memories to hub
- `subscribe_memories()` — pulls relevant memories from hub into local store
- `federated_search()` — searches both local and hub stores

---

## Stories

### Story 64.1: Federation Configuration & Registry

**File:** `packages/tapps-core/src/tapps_core/memory/federation.py`

Implement `FederationConfig` and project registry:

```yaml
# ~/.tapps-mcp/memory/federation.yaml
hub_path: ~/.tapps-mcp/memory/federated.db
projects:
  - project_id: "tappsmcp"
    project_root: "C:/cursor/TappMCP"
    registered_at: "2026-03-09T..."
    tags: ["python", "mcp", "quality-tools"]
  - project_id: "my-api"
    project_root: "C:/cursor/my-api"
    registered_at: "2026-03-09T..."
    tags: ["python", "fastapi", "api"]
subscriptions:
  - subscriber: "my-api"
    sources: ["tappsmcp"]           # Subscribe to specific projects
    tag_filter: ["python", "architecture"]  # Only matching tags
    min_confidence: 0.7
```

**Models:**
- `FederationProject`: project_id, project_root, registered_at, tags
- `FederationSubscription`: subscriber (project_id), sources (list), tag_filter (list), min_confidence (float)
- `FederationConfig`: hub_path, projects, subscriptions

**Functions:**
- `load_federation_config()` → `FederationConfig`
- `save_federation_config(config)`
- `register_project(project_id, project_root, tags)` — adds to registry
- `unregister_project(project_id)` — removes from registry
- `add_subscription(subscriber, sources, tag_filter, min_confidence)`

**Acceptance Criteria:**
- [ ] YAML config loads/saves correctly
- [ ] Project registration with validation (unique IDs, valid paths)
- [ ] Subscription management with source/tag filtering
- [ ] Config created on first use with sensible defaults
- [ ] Unit tests: 15+

### Story 64.2: Federated Hub Store

**File:** `packages/tapps-core/src/tapps_core/memory/federation.py`

Implement `FederatedStore` with hub-specific schema:

```sql
CREATE TABLE federated_memories (
    project_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    tier TEXT NOT NULL,
    confidence REAL NOT NULL,
    source TEXT NOT NULL,
    source_agent TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'shared',
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    published_at TEXT NOT NULL,
    origin_project_root TEXT NOT NULL,
    PRIMARY KEY (project_id, key)
);

CREATE VIRTUAL TABLE federated_fts USING fts5(
    key, value, tags, content=federated_memories, content_rowid=rowid
);

CREATE TABLE federation_meta (
    project_id TEXT PRIMARY KEY,
    last_sync TEXT NOT NULL,
    entry_count INTEGER NOT NULL DEFAULT 0
);
```

**Key design:**
- Composite PK `(project_id, key)` — same key can exist in different projects
- `published_at` tracks when memory was shared (not original creation time)
- `origin_project_root` for traceability
- FTS5 for cross-project search
- WAL mode for concurrent access

**FederatedStore methods:**
- `publish(project_id, entries: list[MemoryEntry])` — upserts to hub
- `unpublish(project_id, keys: list[str])` — removes from hub
- `search(query, project_ids=None, tags=None, min_confidence=None)` → list
- `get_project_entries(project_id)` → list
- `get_stats()` → dict with per-project counts

**Acceptance Criteria:**
- [ ] Hub SQLite created at `~/.tapps-mcp/memory/federated.db`
- [ ] Publish/unpublish with composite key
- [ ] FTS5 search across all projects
- [ ] Project-scoped queries
- [ ] Thread-safe with mutex
- [ ] Unit tests: 20+

### Story 64.3: Scope Extension & Publish Flow

**File:** `packages/tapps-core/src/tapps_core/memory/models.py`, `store.py`, `federation.py`

Extend `MemoryScope` enum:
```python
class MemoryScope(str, Enum):
    project = "project"
    branch = "branch"
    session = "session"
    shared = "shared"      # NEW: eligible for federation
```

Implement publish flow:
- When a memory is saved with `scope="shared"`, it's stored locally AND queued for publishing
- `sync_to_hub(store, federated_store, project_id)` — publishes all shared-scope memories
- Publishing is explicit (called by MCP tool), not automatic (avoids surprise data sharing)
- Memories retain their original key in the hub, namespaced by project_id

Implement subscribe flow:
- `sync_from_hub(store, federated_store, project_id, subscriptions)` — pulls matching memories
- Imported memories get `source_agent="federated:{origin_project}"` tag
- Imported memories get `seeded_from="federation:{origin_project}"` for traceability
- Conflict resolution: skip if local key exists (local always wins), unless hub entry is newer AND higher confidence

**Acceptance Criteria:**
- [ ] `shared` scope added to MemoryScope enum
- [ ] Shared memories published to hub on explicit sync
- [ ] Subscribe pulls matching memories based on subscription config
- [ ] Conflict resolution: local wins by default
- [ ] Provenance tracking via source_agent and seeded_from
- [ ] Unit tests: 15+

### Story 64.4: Federated Search

**File:** `packages/tapps-core/src/tapps_core/memory/federation.py`

Implement cross-project search that queries both local and hub:

```python
async def federated_search(
    query: str,
    local_store: MemoryStore,
    federated_store: FederatedStore,
    project_id: str,
    include_local: bool = True,
    include_hub: bool = True,
    max_results: int = 20,
) -> list[FederatedSearchResult]
```

`FederatedSearchResult`:
- entry: MemoryEntry
- source: "local" | "federated"
- project_id: str
- relevance_score: float (BM25-based)

**Ranking:** Local results get 1.2x boost (prefer local knowledge). Results deduplicated by key (local wins on collision). Sorted by composite score.

**Acceptance Criteria:**
- [ ] Searches both local and hub stores
- [ ] Local results boosted in ranking
- [ ] Deduplication on key collision
- [ ] Project attribution in results
- [ ] Respects subscription filters
- [ ] Unit tests: 15+

### Story 64.5: MCP Tool Integration

**File:** `packages/tapps-mcp/src/tapps_mcp/server_memory_tools.py`

Add federation actions to `tapps_memory`:

1. **`federate_register`** — Register current project in federation hub
   - Params: `tags: list[str]` (optional, auto-detected from profile)
   - Creates federation config if needed, adds project entry

2. **`federate_publish`** — Publish shared-scope memories to hub
   - Params: `keys: list[str]` (optional, publishes all shared if omitted)
   - Returns: published count, skipped count

3. **`federate_subscribe`** — Subscribe to memories from other projects
   - Params: `sources: list[str]` (project IDs), `tag_filter: list[str]`, `min_confidence: float`
   - Saves subscription config

4. **`federate_sync`** — Pull subscribed memories from hub into local store
   - Returns: imported count, skipped count, conflict count

5. **`federate_search`** — Search across local + federated memories
   - Params: `query: str`, `include_hub: bool = True`
   - Returns: ranked results with project attribution

6. **`federate_status`** — Show federation state
   - Returns: registered projects, subscriptions, hub stats

**Acceptance Criteria:**
- [ ] All 6 federation actions work correctly
- [ ] Structured responses with counts and attribution
- [ ] Error handling for missing hub, unregistered projects
- [ ] Integration tests: 15+

### Story 64.6: Session Start Integration

**File:** `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py`

During `tapps_session_start`:
- If federation is configured and project is registered
- Auto-sync subscribed memories from hub (non-blocking)
- Report federation status in session start result
- Include federated memory count in session info

**Acceptance Criteria:**
- [ ] Session start detects federation config
- [ ] Auto-sync on session start (best-effort, non-blocking)
- [ ] Federation status in session result
- [ ] Tests: 5+

---

## Non-Goals

- Real-time sync (federation is explicit pull/push, not live replication)
- Network-based federation (all projects must be on same filesystem)
- Encryption of federated memories (relies on filesystem permissions)
- Memory merging/consolidation across projects (kept separate with attribution)
- Automatic publishing (always explicit to prevent accidental data sharing)

## Security Considerations

- Federation hub at `~/.tapps-mcp/` is user-scoped (no cross-user sharing)
- All published memories pass RAG safety checks before entering hub
- Path validation ensures hub path is within user home directory
- No secrets should be stored in memories (content safety checks apply)

## Testing Strategy

- Unit tests for config, hub store, publish/subscribe, search
- Integration tests for MCP tool actions
- Fixture-based multi-project scenarios
- Verify conflict resolution and deduplication
- Test federation with 2-3 simulated projects

## Estimated Test Count: 85+
