# Epic 42: Memory Subsystem Design Review Runbook

**Purpose:** Repeatable design-review workflow for the tapps_memory stack. Run this when changing core memory behavior or as part of Epic 42 definition-of-done.

**References:** [EPIC-42-TAPPS-MEMORY-2026-ENHANCEMENTS.md](EPIC-42-TAPPS-MEMORY-2026-ENHANCEMENTS.md) (Story 42.5), [EPIC-38-TOP10-SELF-REVIEW-REMEDIATION.md](EPIC-38-TOP10-SELF-REVIEW-REMEDIATION.md).

---

## 1. Scope: Files to Review

### Primary (MCP tool + re-exports)

| File | Role |
|------|------|
| `packages/tapps-mcp/src/tapps_mcp/server_memory_tools.py` | MCP tool handler; gate target (strict 70+) |
| `packages/tapps-mcp/src/tapps_mcp/memory/__init__.py` | Re-exports (if any) |

### Core memory (tapps-core — canonical)

| File | Role |
|------|------|
| `packages/tapps-core/src/tapps_core/memory/store.py` | In-memory cache + SQLite write-through |
| `packages/tapps-core/src/tapps_core/memory/retrieval.py` | MemoryRetriever, BM25 composite scoring |
| `packages/tapps-core/src/tapps_core/memory/persistence.py` | SQLite + FTS5 + schema versioning |
| `packages/tapps-core/src/tapps_core/memory/injection.py` | inject_memories for expert/research |
| `packages/tapps-core/src/tapps_core/memory/decay.py` | Time-based confidence decay |
| `packages/tapps-core/src/tapps_core/memory/reinforcement.py` | reinforce() |
| `packages/tapps-core/src/tapps_core/memory/gc.py` | MemoryGarbageCollector |
| `packages/tapps-core/src/tapps_core/memory/contradictions.py` | ContradictionDetector |
| `packages/tapps-core/src/tapps_core/memory/seeding.py` | reseed_from_profile |
| `packages/tapps-core/src/tapps_core/memory/io.py` | import_memories, export_memories |
| `packages/tapps-core/src/tapps_core/memory/models.py` | MemoryEntry, enums, snapshot |
| `packages/tapps-core/src/tapps_core/memory/bm25.py` | BM25Scorer |

---

## 2. Commands (from repo root)

Assume `uv` and TappsMCP env (e.g. `TAPPS_MCP_PROJECT_ROOT` or run from TappMCP repo as project root).

### 2.1 Score and gate (per file)

```bash
# MCP tool module (primary gate target)
uv run tapps-mcp score-file packages/tapps-mcp/src/tapps_mcp/server_memory_tools.py
uv run tapps-mcp quality-gate packages/tapps-mcp/src/tapps_mcp/server_memory_tools.py --preset strict

# Core memory modules (tapps-core)
uv run tapps-mcp score-file packages/tapps-core/src/tapps_core/memory/store.py
uv run tapps-mcp quality-gate packages/tapps-core/src/tapps_core/memory/store.py --preset strict

uv run tapps-mcp score-file packages/tapps-core/src/tapps_core/memory/retrieval.py
uv run tapps-mcp quality-gate packages/tapps-core/src/tapps_core/memory/retrieval.py --preset strict

uv run tapps-mcp score-file packages/tapps-core/src/tapps_core/memory/persistence.py
uv run tapps-mcp quality-gate packages/tapps-core/src/tapps_core/memory/persistence.py --preset strict

uv run tapps-mcp score-file packages/tapps-core/src/tapps_core/memory/injection.py
uv run tapps-mcp quality-gate packages/tapps-core/src/tapps_core/memory/injection.py --preset strict
```

**Note:** If `tapps-mcp` CLI does not accept paths outside the configured project root, run from the package directory or set `TAPPS_MCP_PROJECT_ROOT` to the monorepo root and use paths relative to it (e.g. `packages/tapps-mcp/src/tapps_mcp/server_memory_tools.py`).

### 2.2 Batch validate changed (memory-related)

Ensure only memory files are in scope (e.g. by branching or stashing non-memory changes):

```bash
uv run tapps-mcp validate-changed --quick false
```

Or validate specific paths if the CLI supports it (otherwise run score-file + quality-gate on each file from §2.1).

### 2.3 Security scan

```bash
uv run tapps-mcp security-scan packages/tapps-mcp/src/tapps_mcp/server_memory_tools.py
uv run tapps-mcp security-scan packages/tapps-core/src/tapps_core/memory/
```

### 2.4 Dead code

```bash
uv run tapps-mcp dead-code --scope file --path packages/tapps-mcp/src/tapps_mcp/server_memory_tools.py
uv run tapps-mcp dead-code --scope file --path packages/tapps-core/src/tapps_core/memory/
```

### 2.5 Tests (memory)

```bash
# tapps-core memory tests
uv run pytest packages/tapps-core/tests/ -k memory -v

# tapps-mcp memory tests
uv run pytest packages/tapps-mcp/tests/ -k memory -v
```

---

## 3. Research-Backed Validation (optional)

Use TappsMCP tools to validate design decisions and record outcomes.

### 3.1 Expert / research (when MCP server is available)

- **Question (example):** “How should agent memory integrate with documentation lookup for validation?”
- **Tool:** `tapps_research` or `tapps_consult_expert` with domain e.g. `code-quality-analysis` or `software-architecture`.
- **Record:** Save a one-line summary or key decision in a session note or in memory (e.g. `tapps_memory save key="memory-doc-lookup-integration" value="..." tier="pattern"`).

### 3.2 Checklist before “done”

```bash
uv run tapps-mcp checklist --task-type feature
```

Fix any missing **required** steps before marking the memory change complete.

---

## 4. Recording Results

Run the steps above and fill in:

| Step | Result | Pass? |
|------|--------|------|
| Score `server_memory_tools.py` | Overall: ___ / 100 | |
| Gate `server_memory_tools.py` (strict) | Pass / Fail | |
| Score core memory (store, retrieval, persistence, injection) | Min overall: ___ | |
| Gate core memory files | All pass? Y / N | |
| Security scan | HIGH/CRITICAL: 0? Y / N | |
| Dead code | No high-confidence unused? Y / N | |
| `pytest -k memory` | All pass? Y / N | |
| Research/experts (if run) | Summary: ___ | |
| Checklist | Complete? Y / N | |

**Date run:** _______________  
**Run by / branch:** _______________

Store this table in the epic doc, in a comment on the relevant PR, or in `docs/planning/epics/EPIC-42-DESIGN-REVIEW-RESULTS.md` (one file per run or append).

---

## 5. Definition-of-Done (memory changes)

For any change that touches **core memory behavior** or **MCP memory tool surface**:

1. All tests in §2.5 pass.
2. At least one full design-review run (§2.1–2.4) has been executed and the results table (§4) filled and stored.
3. `server_memory_tools.py` either passes the strict quality gate (70+) or has a documented exception and a follow-up issue to reach 70+.
4. AGENTS.md and tool schema match implemented actions (no stale contradictions/reseed/import/export if implemented).

---

## 6. Quick One-Liner (score + gate only)

For a fast check of the MCP tool and one core module:

```bash
uv run tapps-mcp score-file packages/tapps-mcp/src/tapps_mcp/server_memory_tools.py && \
uv run tapps-mcp quality-gate packages/tapps-mcp/src/tapps_mcp/server_memory_tools.py --preset strict
```
