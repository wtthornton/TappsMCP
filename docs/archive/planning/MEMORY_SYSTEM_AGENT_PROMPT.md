# TappsMCP Shared Memory System — Agent Team Execution Prompt

Use this prompt to launch a new Claude Code session that builds the entire Shared Memory system (Epics 23, 24, 25) using agent teams.

---

## Prompt

```
You are the team lead for implementing the TappsMCP Shared Memory System — Epics 23, 24, and 25. This is a major feature adding persistent, project-scoped memory with time-based decay, contradiction detection, and retrieval-augmented expert responses.

## Project Context

- **Project root:** C:\cursor\TappMCP
- **What TappsMCP is:** An MCP server providing deterministic code quality tools to LLMs. Python 3.12+, Pydantic v2, mypy --strict, ruff, structlog, asyncio.
- **CLAUDE.md** is at the project root — read it first for dev commands, architecture, and conventions.
- **Epic docs are at:** docs/planning/epics/EPIC-23-SHARED-MEMORY-FOUNDATION.md, EPIC-24-MEMORY-INTELLIGENCE.md, EPIC-25-MEMORY-RETRIEVAL-INTEGRATION.md
- **Existing patterns to follow:** src/tapps_mcp/adaptive/persistence.py (file persistence), src/tapps_mcp/project/session_notes.py (in-memory store + singleton), src/tapps_mcp/knowledge/rag_safety.py (content safety filtering), src/tapps_mcp/server_scoring_tools.py (server module split pattern)

## TappsMCP Quality Pipeline (MANDATORY)

You and ALL teammates MUST use TappsMCP's own MCP tools throughout:

1. **First call every session:** `tapps_session_start()`
2. **Before using any library API:** `tapps_lookup_docs(library="sqlite3")`, `tapps_lookup_docs(library="pydantic")`, etc.
3. **After editing ANY Python file:** `tapps_quick_check(file_path="<path>")` — fix all issues before moving on
4. **Before declaring any story complete:** `tapps_validate_changed()` — ALL quality gates MUST pass
5. **Before declaring an epic complete:** `tapps_checklist(task_type="feature")` — verify completeness
6. **For security-sensitive code (persistence, path handling):** `tapps_security_scan(file_path="<path>")`
7. **For architecture questions:** `tapps_research(question="...")` or `tapps_consult_expert(question="...", domain="...")`

## Team Structure

Create a team called "memory-system" with yourself as lead. Spawn 3 implementation teammates:

### Teammate: "foundation" (general-purpose agent)
- **Scope:** Epic 23 — Models, SQLite persistence, MemoryStore, MCP tool, session notes compat
- **Works in a worktree** to avoid conflicts
- **Stories in order:** 23.1 → 23.2 → 23.3 → 23.4 → 23.5 → 23.6
- **Critical:** This is the foundation — nothing else can start until 23.1 (models) and 23.2 (persistence) are done

### Teammate: "intelligence" (general-purpose agent)
- **Scope:** Epic 24 — Decay engine, reinforcement, contradiction detection, GC, config
- **Works in a worktree** to avoid conflicts
- **Stories in order:** 24.1 → 24.2 → 24.3 → 24.4 → 24.5
- **Blocked until:** "foundation" completes stories 23.1 + 23.2 + 23.3 (needs models, persistence, and store)
- **Can start 24.1 (decay) and 24.3 (contradictions) in parallel** once unblocked — they are independent

### Teammate: "integration" (general-purpose agent)
- **Scope:** Epic 25 — Ranked retrieval, expert injection, profile seeding, import/export, pipeline integration
- **Works in a worktree** to avoid conflicts
- **Stories:** 25.3 (seeding) and 25.4 (import/export) can start once "foundation" finishes 23.3. 25.1 (ranked retrieval) needs 24.1 (decay). 25.2 (expert injection) needs 25.1. 25.5 and 25.6 are last.
- **Blocked until:** "foundation" completes 23.3 for early stories; "intelligence" completes 24.1 for retrieval

## Task Creation Plan

Create ALL tasks upfront with proper blocking dependencies. Use this structure:

### Epic 23 Tasks
1. "23.1: Create memory models (MemoryEntry, enums, validators)" — no blockers
2. "23.2: Build SQLite persistence layer (WAL, FTS5, schema versioning, JSONL audit)" — blocked by #1
3. "23.3: Build MemoryStore (in-memory cache + SQLite, CRUD, RAG safety, singleton)" — blocked by #2
4. "23.4: Register tapps_memory MCP tool in server_memory_tools.py" — blocked by #3
5. "23.5: Session notes compatibility and promote action" — blocked by #3
6. "23.6: Epic 23 integration tests, edge cases, and documentation updates" — blocked by #4, #5

### Epic 24 Tasks
7. "24.1: Build decay engine (exponential decay, tier half-lives, config)" — blocked by #3
8. "24.2: Build reinforcement system (reinforce action, decay clock reset)" — blocked by #7
9. "24.3: Build contradiction detector (tech stack drift, file existence, branch checks)" — blocked by #3
10. "24.4: Build GC and archival (archive criteria, archived_memories table)" — blocked by #7
11. "24.5: Memory config in settings.py and dashboard/stats integration" — blocked by #7, #8, #9, #10

### Epic 25 Tasks
12. "25.1: Build ranked retrieval (FTS5 BM25, composite scoring, ScoredMemory)" — blocked by #7
13. "25.2: Expert and research memory injection with RAG safety" — blocked by #12
14. "25.3: Profile seeding (auto-seed from tapps_project_profile)" — blocked by #3
15. "25.4: Import/export (JSON format, path validation, conflict resolution)" — blocked by #3
16. "25.5: Pipeline and init integration (config, session_start, AGENTS.md templates)" — blocked by #12, #13, #14, #15
17. "25.6: Epic 25 integration tests, lifecycle tests, documentation" — blocked by #16

## Your Role as Team Lead

1. **Create the team and all 17 tasks** with dependencies before spawning teammates
2. **Assign tasks** to the right teammate as they become unblocked
3. **Monitor quality:** When a teammate says they've finished a story, verify:
   - Did they run `tapps_quick_check` on every edited file?
   - Did they run `tapps_validate_changed` before declaring done?
   - Did they run the tests? (`uv run pytest tests/unit/test_memory*.py -v`)
4. **Merge worktrees:** When a teammate completes their epic, review their branch and merge into master
5. **Handle blockers:** If a teammate is stuck, help them or reassign
6. **Cross-epic integration:** After each epic completes, run the full test suite: `uv run pytest tests/ -v`
7. **Final validation:** After all 3 epics are merged:
   - `uv run pytest tests/ -v` (all tests pass)
   - `uv run mypy --strict src/tapps_mcp/` (type checking passes)
   - `uv run ruff check src/` (no lint errors)
   - `tapps_validate_changed()` on all new files
   - `tapps_checklist(task_type="feature")` for final sign-off

## Teammate Prompt Template

When spawning each teammate, include this context in their prompt:

---

You are the "{name}" teammate on the "memory-system" team building TappsMCP's Shared Memory System.

**Your scope:** {epic description}

**MANDATORY before writing any code:**
1. Read CLAUDE.md at the project root for conventions
2. Read your epic doc: docs/planning/epics/EPIC-{N}-{NAME}.md — this is your spec
3. Call `tapps_session_start()` to initialize the TappsMCP pipeline
4. Call `tapps_lookup_docs(library="sqlite3")` and `tapps_lookup_docs(library="pydantic")` before using their APIs

**MANDATORY during development:**
- After editing ANY Python file: `tapps_quick_check(file_path="<path>", fix=true)`
- For security-sensitive files (persistence.py, store.py): `tapps_security_scan(file_path="<path>")`
- Follow existing patterns: `from __future__ import annotations` at top of every file, `structlog` for logging, `pathlib.Path` for paths, type annotations everywhere
- All file I/O through `security/path_validator.py`

**MANDATORY before declaring a story complete:**
- Run tests: `uv run pytest tests/unit/test_memory*.py -v`
- Run type check: `uv run mypy --strict src/tapps_mcp/memory/`
- Run `tapps_validate_changed()` — all gates must pass
- Message the team lead with what you completed

**Existing code to study:**
- `src/tapps_mcp/project/session_notes.py` — SessionNoteStore pattern (your store follows this)
- `src/tapps_mcp/adaptive/persistence.py` — File persistence patterns
- `src/tapps_mcp/adaptive/models.py` — Pydantic model patterns with timestamps
- `src/tapps_mcp/knowledge/rag_safety.py` — Content safety filtering (use on memory writes)
- `src/tapps_mcp/server_scoring_tools.py` — Server module split pattern (for server_memory_tools.py)
- `src/tapps_mcp/server_helpers.py` — Singleton cache pattern (_get_scorer, _get_memory_store)
- `src/tapps_mcp/config/settings.py` — Settings model pattern (for memory config)
- `tests/conftest.py` — Cache reset pattern (add _reset_memory_store_cache)

**Check TaskList regularly** for newly unblocked work. Claim tasks in ID order.

---

## Parallelization Timeline

```
Week 1:
  foundation: 23.1 (models) → 23.2 (persistence) → 23.3 (store)
  intelligence: [blocked — reading epic docs, studying patterns]
  integration: [blocked — reading epic docs, studying patterns]

Week 1-2 (after 23.3 completes):
  foundation: 23.4 (MCP tool) → 23.5 (compat) → 23.6 (tests/docs)
  intelligence: 24.1 (decay) + 24.3 (contradictions) [parallel]
  integration: 25.3 (seeding) + 25.4 (import/export) [parallel]

Week 2-3 (after 24.1 completes):
  foundation: [done, available to help]
  intelligence: 24.2 (reinforcement) → 24.4 (GC) → 24.5 (config)
  integration: 25.1 (ranked retrieval) → 25.2 (expert injection)

Week 3 (after all stories complete):
  integration: 25.5 (pipeline) → 25.6 (tests/docs)
  lead: Final integration, merge, full test suite, checklist
```

## Definition of Done (Entire Feature)

- [ ] All 17 tasks completed and merged to master
- [ ] `uv run pytest tests/ -v` — all tests pass (existing + ~120 new)
- [ ] `uv run mypy --strict src/tapps_mcp/` — passes
- [ ] `uv run ruff check src/` — no errors
- [ ] `tapps_validate_changed()` — all gates pass
- [ ] `tapps_checklist(task_type="feature")` — passes
- [ ] CLAUDE.md module map updated with memory/ package
- [ ] AGENTS.md updated with tapps_memory tool
- [ ] README.md tools table updated
- [ ] Epic statuses in docs/planning/epics/README.md updated to "Complete"
- [ ] Memory in MEMORY.md updated with final status

## Start Now

1. Read CLAUDE.md
2. Read all three epic docs (23, 24, 25)
3. Call `tapps_session_start()`
4. Create the "memory-system" team via TeamCreate
5. Create all 17 tasks with dependencies via TaskCreate
6. Spawn the "foundation" teammate first (they have no blockers)
7. Spawn "intelligence" and "integration" teammates (they can start reading docs while blocked)
8. Begin orchestrating
```

---

## Usage

Copy the prompt above (between the triple backticks) and paste it into a new Claude Code session with the TappsMCP project open. The agent will create the team, spawn teammates, and begin executing.

## Prerequisites

- TappsMCP's own MCP server must be running and available in the session
- `uv sync` has been run (dependencies installed)
- Git working tree is clean (no uncommitted changes)
