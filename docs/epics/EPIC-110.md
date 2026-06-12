# Epic 110: Cross-session handoff fidelity (TAP-3573 follow-up)

<!-- docsmcp:start:metadata -->
**Status:** Shipped (master `9963cee`)
**Priority:** High
**Estimated LOE:** M (2–3 weeks phased)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that HTTP-only brain consumers can reliably hand off work between chats without Postgres DSN, with a durable brain mirror that preserves full handoff markdown and a single atomic write path that passes TAP-3573 schema lint.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Close the gaps found in AgentForge evaluation of `/tapps-handoff-session` + brain mirror: fix broken `memory search` on HTTP-only setups, improve continue-session ergonomics, add doctor guidance, ship `tapps-mcp handoff write` (or MCP `tapps_handoff_save`), and improve session-end flywheel retrieval.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Canonical `.tapps-mcp/session-handoff.md` works and passes doctor lint (TAP-3573), but HTTP-only consumers hit `MemoryStore requires Postgres` on `memory search`, brain mirrors are often agent-compressed to one line while `.tapps-mcp/` is gitignored, and `tapps_session_end` session_search uses stale `session_start_iso` timestamps with empty results when sentinels are stale.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] `tapps-mcp memory search` routes through BrainBridge when `memory.brain_http_url` is set (no local DSN required)
- [ ] `tapps-continue-session` documents `memory recall --recall-key session-handoff` as primary supplement; `memory search` remains valid
- [ ] `tapps-handoff-session` mirrors **full markdown** to brain (`cat session-handoff.md`), not agent summaries
- [ ] `tapps doctor` advises HTTP-only consumers which memory CLI subcommands still need `TAPPS_BRAIN_DATABASE_URL`
- [ ] `tapps-mcp handoff write` (or `tapps_handoff_save`) atomically writes file + brain mirror + schema lint + optional session-end
- [ ] `tapps_session_end` session_search uses a retrievable query (not raw ISO sentinel) when sentinel is stale

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 110.1 — HTTP-safe memory search + continue-session ergonomics

**Points:** 3 | **Phase:** v1.0

Route `memory search` CLI through BrainBridge (like `recall`); update handoff/continue skills; add `check_memory_cli_http_mode` doctor row.

**Files:** `cli.py`, `platform_skills.py`, `doctor.py`, skill templates, `MEMORY_REFERENCE.md`

---

### 110.2 — Atomic `handoff write` CLI and MCP tool

**Points:** 5 | **Phase:** v1.0

Single command: write `.tapps-mcp/session-handoff.md`, mirror full body to brain (`session-handoff` key), attach metadata (`git_sha`, `git_branch`, `linear_p0`, `updated_at`), run `handoff_schema` lint (fail on P0/Open violations), optionally call session-end flywheel.

**Files:** new `handoff_write.py`, `cli.py`, `server_pipeline_tools.py`, tests

---

### 110.3 — session_end flywheel: retrievable session_search

**Points:** 3 | **Phase:** v1.1

When session_start sentinel is stale, degrade gracefully; use semantic session_search query (P0 / project id / summary tags) instead of raw `session_start_iso`; document `processed_events: 0` meaning in AGENTS.md.

**Files:** `session_end_helpers.py`, `server_pipeline_tools.py`, tests

---

### 110.4 — Brain mirror metadata and structured recall

**Points:** 2 | **Phase:** v1.2

Store handoff section pointers in memory entry metadata; `memory get` surfaces link back to Done/Open/P0 sections; clarify `memory_group: null` in save JSON output.

**Files:** `handoff_schema.py`, brain save payload, CLI output, docs

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:refs -->
## Refs

Linear: TAP-3790 (shipped `9963cee`)

- TAP-3573 (session-handoff schema lint)
- `packages/tapps-mcp/src/tapps_mcp/tools/handoff_schema.py`
- `.claude/skills/tapps-handoff-session`, `.claude/skills/tapps-continue-session`
- AgentForge evaluation (tapps-mcp 3.12.25, brain HTTP-only)

<!-- docsmcp:end:refs -->
