# Epic 23: Shared Memory Foundation

**Status:** Proposed
**Priority:** P1 — High (enables cross-agent knowledge sharing, builds on existing session notes)
**Estimated LOE:** ~2-3 weeks (1 developer)
**Dependencies:** Epic 0 (Foundation), Epic 4 (Project Context — session notes, models)
**Blocks:** Epic 24 (Memory Intelligence), Epic 25 (Memory Retrieval & Integration)

---

## Goal

Build a persistent, project-scoped memory system that replaces ephemeral session notes with durable memories accessible to all MCP-connected agents. Memories are typed by tier (architectural, pattern, context), carry metadata (confidence, source, timestamps), and persist across sessions in `.tapps-mcp/memory/`. This epic delivers the storage layer, Pydantic models, the `tapps_memory` MCP tool, and the migration path from `tapps_session_notes`.

## Motivation

Today, `tapps_session_notes` is in-memory with crash-recovery persistence. When a session ends, knowledge is lost. Each agent (Claude Code, Cursor, Copilot) starts every session amnesiac about the project. A shared memory system means **the project remembers things, not the developer's tool**.

## 2026 Best Practices Applied

- **SQLite for primary storage** — `sqlite3` is in Python stdlib (zero new dependencies). Provides ACID transactions, built-in WAL-mode concurrent read/write, native filtering/querying, and no corrupt-snapshot recovery complexity. The leading open-source MCP memory server ([mcp-memory-service](https://github.com/doobidoo/mcp-memory-service)) uses SQLite as its default backend achieving 5ms retrieval. JSONL retained as an append-only audit log only.
- **Schema-versioned database** — A `schema_version` table tracks the memory DB schema version. On startup, `MemoryPersistence` checks the version and applies migrations forward. This prevents data loss when TappsMCP upgrades change the memory model.
- **RAG safety on stored content** — Memory values are user/agent-provided text that may later be injected into LLM prompts (via expert/research memory injection in Epic 25). All memory values pass through `knowledge/rag_safety.py` `check_content_safety()` on write. Flagged content is sanitised before storage.
- **Path-sandboxed** — All file I/O through `security/path_validator.py`, scoped to `TAPPS_MCP_PROJECT_ROOT`.
- **Pydantic v2 models** — All data structures validated, serializable, versioned.
- **Thread-safe** — `threading.Lock` for in-memory state (consistent with `SessionNoteStore`). SQLite WAL mode allows concurrent reads during writes.
- **Deterministic** — No LLM calls. Same input produces same output.
- **Project-scoped namespacing** — Memories are scoped to `project_root` to prevent cross-project data confusion (a known failure mode in multi-project MCP setups per 2026 benchmarks).

## Acceptance Criteria

- [ ] `MemoryEntry` Pydantic model with: key, value, tier, confidence, source, tags, created_at, updated_at, last_accessed, access_count
- [ ] `MemoryStore` class with CRUD operations: save, get, list, delete, search-by-tag
- [ ] Three memory tiers: `architectural` (slow decay), `pattern` (medium decay), `context` (fast decay)
- [ ] Confidence scores: 0.0-1.0, with source-based initial defaults (human=0.95, agent=0.6, inferred=0.4, system=0.9); ceilings enforced by Epic 24 DecayConfig (human=0.95, agent=0.85, inferred=0.70)
- [ ] Persistent storage at `{project_root}/.tapps-mcp/memory/`
- [ ] `tapps_memory` MCP tool with actions: save, get, list, delete, search
- [ ] `tapps_session_notes` preserved for backward compatibility (existing API unchanged)
- [ ] Memory entries include `source_agent` field (which agent/client wrote the memory)
- [ ] Memory entries include `scope` field: `project` (default), `branch`, `session`
- [ ] SQLite persistence with WAL mode at `{project_root}/.tapps-mcp/memory/memory.db`
- [ ] JSONL audit log at `{project_root}/.tapps-mcp/memory/memory_log.jsonl` (append-only, write events only)
- [ ] Schema versioning: `schema_version` table with forward-migration on startup
- [ ] Security: memory values pass through `rag_safety.py` on write (prompt injection prevention)
- [ ] Security: memories cannot contain file paths outside project root (path validation)
- [ ] Unit tests: ~50 tests (models ~8, store ~15, persistence ~12, MCP tool ~7, compatibility ~5, integration ~3)

---

## Stories

### 23.1 — Memory Models

**Points:** 3

Define the Pydantic v2 models for the memory subsystem.

**Tasks:**
- Create `src/tapps_mcp/memory/__init__.py`
- Create `src/tapps_mcp/memory/models.py` with:
  - `MemoryTier` enum: `architectural`, `pattern`, `context`
  - `MemorySource` enum: `human`, `agent`, `inferred`, `system`
  - `MemoryScope` enum: `project`, `branch`, `session`
  - `MemoryEntry` model:
    - `key: str` — unique identifier (slugified, max 128 chars)
    - `value: str` — the memory content (max 4096 chars)
    - `tier: MemoryTier` — decay classification
    - `confidence: float` — 0.0-1.0, source-based default
    - `source: MemorySource` — who created the memory
    - `source_agent: str` — agent identifier (e.g., "claude-code", "cursor", "copilot")
    - `scope: MemoryScope` — visibility scope
    - `tags: list[str]` — free-form tags for search (max 10)
    - `created_at: str` — ISO-8601 UTC
    - `updated_at: str` — ISO-8601 UTC
    - `last_accessed: str` — ISO-8601 UTC (updated on read)
    - `access_count: int` — incremented on read
    - `branch: str | None` — git branch (required when scope=branch)
    - `last_reinforced: str | None` — ISO-8601 UTC, reset by Epic 24 reinforce action (reserved, defaults to None)
    - `reinforce_count: int = 0` — total reinforcements (reserved for Epic 24)
    - `contradicted: bool = False` — set by Epic 24 contradiction detection (reserved)
    - `contradiction_reason: str | None = None` — reason for contradiction (reserved for Epic 24)
    - `seeded_from: str | None = None` — populated by Epic 25 profile seeding (reserved)
  - `MemorySnapshot` model for full-state serialization / export
  - Validators: key slug format, value length, tag count limit, branch required when scope=branch
- Write ~8 unit tests for model validation and defaults

**Definition of Done:** All models validate correctly. Source-based confidence defaults work. Validators reject invalid data.

---

### 23.2 — Memory Persistence Layer

**Points:** 5

Build the SQLite-backed persistence layer. SQLite is in Python's stdlib (`sqlite3`), adds zero dependencies, provides ACID transactions and built-in concurrent access via WAL mode, and eliminates the corrupt-snapshot-recovery complexity that JSONL-only approaches require.

**Tasks:**
- Create `src/tapps_mcp/memory/persistence.py` with:
  - `MemoryPersistence` class:
    - Storage directory: `{project_root}/.tapps-mcp/memory/`
    - `memory.db` — SQLite database with WAL journal mode for concurrent read/write
    - `memory_log.jsonl` — append-only audit log (writes/deletes only, for debugging/compliance)
    - Schema: `memories` table with columns matching `MemoryEntry` fields, plus indexes on `key`, `tier`, `scope`, `tags` (via a join table or JSON column)
    - `schema_version` table: `(version INTEGER, migrated_at TEXT)` — checked on startup, forward-migrations applied automatically
    - `save(entry: MemoryEntry)` — INSERT OR REPLACE with JSONL audit append
    - `get(key, scope, branch)` — SELECT with scope precedence (session > branch > project)
    - `list_all(tier, scope, tags)` — SELECT with WHERE filters
    - `delete(key)` — DELETE with JSONL audit append
    - `search(query)` — FTS5 full-text search (SQLite built-in) across key + value columns
    - `load_all()` — SELECT * for cold-start into in-memory cache
    - `count()` — SELECT COUNT(*)
  - SQLite configuration:
    - `PRAGMA journal_mode=WAL` — allows concurrent readers during writes
    - `PRAGMA busy_timeout=5000` — 5s retry on locked DB
    - `PRAGMA foreign_keys=ON`
    - Connection created per-thread (SQLite's `check_same_thread=False` with threading.Lock)
  - Schema migration v1 → v2 pattern: `_migrate_v1_to_v2()` etc., called on startup if `schema_version` < current
  - JSONL audit log: retained for append-only write history (not used for recovery — SQLite handles that). Auto-truncated at 10,000 lines.
- Write ~12 unit tests: save/load round-trip, FTS5 search, concurrent reads during write, schema migration, WAL mode verification, JSONL audit log, max-entries enforcement

**Definition of Done:** Memories persist in SQLite across server restarts. FTS5 search works. WAL mode enables concurrent access. Schema versioned with forward migration.

---

### 23.3 — Memory Store (In-Memory Cache + SQLite)

**Points:** 5

Build the `MemoryStore` class that provides fast in-memory reads backed by SQLite persistence, following the singleton pattern of `SessionNoteStore` and `CodeScorer`.

**Tasks:**
- Create `src/tapps_mcp/memory/store.py` with:
  - `MemoryStore` class:
    - Constructor: `__init__(project_root: Path)` — opens SQLite, loads entries into in-memory dict
    - `save(key, value, tier, source, source_agent, scope, tags, branch, confidence)` → `MemoryEntry`
      - **RAG safety check**: `value` passed through `rag_safety.check_content_safety()` before storage. If flagged with high match count, the value is sanitised. If blocked, save is rejected with a warning.
      - **Max entries enforcement**: if at 500 limit, evict lowest-confidence entry before inserting
    - `get(key, scope, branch)` → `MemoryEntry | None` — updates `last_accessed` and `access_count`
    - `list_all(tier, scope, tags)` → `list[MemoryEntry]` — filtered listing
    - `delete(key)` → `bool`
    - `search(query, tags, tier, scope)` → `list[MemoryEntry]` — delegates to SQLite FTS5
    - `update_fields(key, **fields)` → `MemoryEntry | None` — partial update of specific fields (confidence, contradicted, last_reinforced, etc.) without clobbering immutable fields like `created_at`. Used by Epic 24 decay/contradiction/reinforcement.
    - `count()` → `int`
    - `snapshot()` → `MemorySnapshot`
  - Key deduplication: saving to an existing key updates the entry (preserves `created_at`, updates `updated_at`)
  - Scope resolution: `get()` checks `session` → `branch` → `project` scope (most specific wins)
  - Thread-safe: `threading.Lock` on all state mutations, SQLite writes serialized
  - Write-through cache: every write updates both in-memory dict and SQLite synchronously (no debouncing — SQLite WAL mode is fast enough)
- Add `_get_memory_store()` singleton to `server_helpers.py` (following `_get_scorer()` pattern)
- Add `_reset_memory_store_cache()` for test isolation
- Add cache reset to `tests/conftest.py` autouse fixture
- Write ~15 unit tests: CRUD operations, scope resolution, key dedup, search via FTS5, thread safety, singleton behavior, RAG safety rejection, max entries eviction

**Definition of Done:** MemoryStore provides complete CRUD with scope resolution. Thread-safe. Write-through to SQLite. RAG safety on writes. Singleton via server_helpers.

---

### 23.4 — `tapps_memory` MCP Tool

**Points:** 5

Register the `tapps_memory` MCP tool that exposes the memory store to all MCP clients.

**Tasks:**
- Create `src/tapps_mcp/server_memory_tools.py` (following the established split pattern of `server_scoring_tools.py`, `server_pipeline_tools.py`, `server_metrics_tools.py` — the tool will grow to 8+ actions across Epics 23-25, justifying its own module)
- Register `tapps_memory` tool handler via `@mcp.tool()` on the shared `mcp` instance:
  - Parameters:
    - `action: str` — "save", "get", "list", "delete", "search"
    - `key: str` — memory key (required for save/get/delete)
    - `value: str` — memory content (required for save)
    - `tier: str` — "architectural", "pattern", "context" (default: "pattern", required for save)
    - `source: str` — "human", "agent", "inferred" (default: "agent")
    - `source_agent: str` — agent identifier (default: "unknown")
    - `scope: str` — "project", "branch", "session" (default: "project")
    - `tags: str` — comma-separated tags (optional)
    - `branch: str` — git branch name (optional, auto-detected if not provided)
    - `query: str` — search query (for search action)
    - `confidence: float` — override default confidence (optional)
  - Response includes: the memory entry (or list), store metadata (total count, tier breakdown)
  - Call `_record_call("tapps_memory")` for checklist tracking
- Add `tapps_memory` to the checklist task map in `tools/checklist.py`:
  - `recommended` for feature, refactor task types
  - `optional` for bugfix, security, review task types
- Add structured output schema to `output_schemas.py`
- Write ~7 unit tests for the MCP tool handler: each action, error cases, missing params

**Definition of Done:** `tapps_memory` tool works from any MCP client. All 5 actions function correctly. Registered in checklist.

---

### 23.5 — Session Notes Compatibility

**Points:** 2

Ensure `tapps_session_notes` continues to work unchanged while memories are available as the long-term alternative.

**Tasks:**
- `tapps_session_notes` remains unchanged — no breaking changes
- Add a `migration_hint` to `tapps_session_notes` responses suggesting `tapps_memory` for persistent storage
- Add helper: `promote_note_to_memory(key)` — copies a session note to memory store with `source=agent`, `tier=context`, `scope=session`
- Add `promote` action to `tapps_session_notes` tool (optional, non-breaking):
  - `action: "promote"`, `key: "mykey"`, `tier: "pattern"` → creates memory entry from session note
- Write ~5 unit tests for promotion and backward compatibility

**Definition of Done:** Existing `tapps_session_notes` behavior is unchanged. Promotion path to memory works.

---

### 23.6 — Tests & Documentation

**Points:** 2

Comprehensive test suite and documentation updates.

**Tasks:**
- Integration tests: full round-trip from MCP tool → store → persistence → reload
- Edge cases: empty store, max key length, max value length, max tags, invalid tier/scope
- Concurrency test: multiple saves to same key
- Update AGENTS.md tool reference to include `tapps_memory`
- Update README.md tools table
- Update CLAUDE.md module map with `memory/` package
- Add `tapps_memory` to platform rule templates (all engagement levels)

**Definition of Done:** ~50+ total tests pass (sum of story estimates: 8+12+15+7+5 = 47, plus integration/edge tests). Documentation updated. Tool visible in all platform templates.

---

## Performance Targets

| Operation | Target (p95) | Notes |
|---|---|---|
| `save` | < 15ms | In-memory + SQLite WAL write |
| `get` | < 5ms | In-memory lookup (SQLite for cache miss) |
| `list` | < 10ms | In-memory scan with filtering |
| `search` (FTS5) | < 20ms | SQLite FTS5 full-text search |
| `delete` | < 10ms | In-memory + SQLite WAL write |
| Cold start (load) | < 100ms | SQLite SELECT * into memory |

> **Note:** SQLite WAL mode benchmarks at ~5ms per write for small tables. The mcp-memory-service achieves 5ms retrieval latency with SQLite.

## Storage Limits

| Limit | Value | Rationale |
|---|---|---|
| Max memories per project | 500 | Prevent unbounded growth (enforced at store level, lowest-confidence evicted) |
| Max key length | 128 chars | Readable, slug-friendly |
| Max value length | 4,096 chars | One screen of content |
| Max tags per entry | 10 | Enough for categorization |
| JSONL audit log retention | 10,000 lines | ~6 months at moderate usage |
| SQLite DB size (typical) | < 5 MB | 500 entries with 4KB values |

## File Layout

```
src/tapps_mcp/
    server_memory_tools.py  # tapps_memory MCP tool handler (new, following server split pattern)

src/tapps_mcp/memory/
    __init__.py
    models.py          # MemoryEntry, MemoryTier, MemorySource, MemoryScope, MemorySnapshot
    persistence.py     # MemoryPersistence (SQLite + JSONL audit, schema versioning, FTS5)
    store.py           # MemoryStore (in-memory cache + SQLite, CRUD, search, RAG safety)
```

Storage layout on disk:
```
{project_root}/.tapps-mcp/memory/
    memory.db          # SQLite database (WAL mode, FTS5)
    memory.db-wal      # WAL journal (auto-managed by SQLite)
    memory.db-shm      # Shared memory file (auto-managed by SQLite)
    memory_log.jsonl   # Append-only audit log (writes/deletes only)
    archive.jsonl      # Archived memories (created by Epic 24 GC, append-only)
```

SQLite schema (v1):
```sql
-- Active memories
CREATE TABLE memories (...);  -- columns match MemoryEntry fields
CREATE VIRTUAL TABLE memories_fts USING fts5(key, value, tags);  -- FTS5 index

-- Reserved for Epic 24 GC
CREATE TABLE archived_memories (...);  -- same schema as memories + archived_at TEXT

-- Schema versioning
CREATE TABLE schema_version (version INTEGER, migrated_at TEXT);
```

## Key Dependencies
- Epic 0 (security/path_validator for sandboxed I/O, knowledge/rag_safety for content safety)
- Epic 4 (session_notes models pattern, server_helpers singleton pattern)
- `sqlite3` (Python stdlib — zero new dependencies)
- `filelock` not needed (SQLite WAL mode handles concurrency natively)

## Key Design Decisions

1. **SQLite over JSON+JSONL** — `sqlite3` is stdlib, provides ACID, WAL concurrent access, FTS5 full-text search, and schema migrations. Eliminates the corrupt-snapshot-recovery pattern and `filelock` dependency for the memory subsystem. JSONL retained only as an audit trail.
2. **RAG safety on write** — Memory values may later be injected into LLM prompts (Epic 25). Filtering on write (not read) ensures the store itself never contains adversarial content, preventing stored prompt injection attacks.
3. **Schema versioning** — Forward migrations prevent data loss across TappsMCP upgrades. Follows the pattern used by production MCP memory servers.
4. **FTS5 for search** — SQLite's built-in full-text search is significantly better than simple keyword matching for 500 entries. No external dependencies needed.

## Future Considerations (Not in Scope)

- **Memory consolidation** — Leading memory systems (mcp-memory-service) auto-consolidate related memories into summaries. Deferred to a future epic if usage data shows fragmentation.
- **Knowledge graph relationships** — Typed relationships between memories (causes, fixes, contradicts). Interesting but adds complexity without clear immediate value for code quality tooling.
- **Vector embeddings** — Hybrid BM25+vector retrieval. FTS5 is sufficient for 500 entries; vector adds a heavy dependency (sentence-transformers, faiss). Could follow the same optional-FAISS pattern from Epic 5 if needed later.
