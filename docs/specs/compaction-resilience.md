# Compaction Resilience Spec

**Status:** Active  
**Created:** 2026-05-23  
**Refs:** [Anthropic Issue #54393](https://github.com/anthropics/claude-code/issues/54393) (2026-04-28)

---

## Overview

Context compaction in Claude Code is a lossy event: when the context window fills, the
runtime summarizes the conversation and discards the raw transcript. Any agent state that
exists only in the context window — in-flight decisions, partially-written plans,
in-memory scoring results — is gone after compaction. This spec documents the failure mode,
the mitigations shipped in Claude Code 2.1.105+, and how TappsMCP uses tapps-brain as the
durable backing store to survive compaction.

---

## Background: Anthropic Issue #54393 (2026-04-28)

Issue #54393, filed 2026-04-28, catalogued **12 multi-agent coordination bugs** triggered
during extended autonomous sessions. The dominant failure class was **post-compaction
memory loss**: agent loops that appeared to be making progress silently reset to an earlier
state after context compaction, re-executing work already done, re-filing duplicate Linear
issues, and diverging from their own prior decisions.

The root cause in all 12 cases was the same: durable intent (what task am I on? what have I
committed?) was stored only in Claude's context window, not in a backing store. Compaction
is not an error — it is an expected event in any session long enough to produce real output.
Treating it as a rare failure leads to fragile agent designs.

---

## The Two Memory Tiers

Understanding compaction resilience requires distinguishing two fundamentally different
memory tiers:

| Tier | Storage | Survives compaction? | Survives restart? |
|---|---|---|---|
| **Context memory** | Claude's active context window | ❌ No | ❌ No |
| **Brain memory** | tapps-brain (Postgres in Docker) | ✅ Yes | ✅ Yes |

**Context memory** includes everything the agent has read in the current session: file
contents, tool results, decisions made, partially-written plans. It is authoritative while
intact and requires no I/O — but it is ephemeral. Compaction silently discards it.

**Brain memory** is persisted to tapps-brain's Postgres store and survives compaction,
restarts, and machine reboots. Writes happen via `tapps_memory(action="save")` or the
`memory_index_session` tool; reads via `tapps_memory(action="get")` or `action="search"`.
Brain memory is the durable backing store that agents should write to any state they would
not want to repeat if compaction occurred.

---

## PreCompact Hook (Claude Code 2.1.105+)

Claude Code 2.1.105 shipped a **PreCompact** hook — a script that runs immediately before
the context window is compacted. The hook:

- Receives the full current context as stdin (or via `_session_state.json`)
- Runs synchronously; compaction is deferred until the hook completes
- Cannot block or cancel compaction (exit code 2 is ignored; compaction proceeds)
- Is the correct place to flush in-flight state to durable storage

TappsMCP registers a PreCompact hook at `tapps_init` time
(`.claude/hooks/tapps-pre-compact.sh`). The generated hook calls `tapps_session_start` to
trigger consolidation and garbage collection before context is lost, and is also an
appropriate place to call `tapps_memory(action="index_session")` to snapshot the session
transcript into tapps-brain.

### `_session_state.json` rehydration surface

Claude Code writes session state to `_session_state.json` before compaction. The
PreCompact hook can read this file to extract structured context — current tool call
history, pending outputs, session metadata — that would otherwise be lost.
`_session_state.json` is also read by Claude Code on session resume to rehydrate local
state; it bridges the compaction boundary for Claude Code's own internal bookkeeping but is
**not** a substitute for explicit writes to tapps-brain for cross-session agent memory.

---

## `memory_index_session` as Durable Backing Store

tapps-brain's `memory_index_session` tool (exposed via
`tapps_memory(action="index_session", session_id=..., chunks=[...])`) indexes session
transcript chunks into the brain's vector store. Indexed chunks survive compaction and are
available to future sessions via semantic search.

This is distinct from scalar key/value writes (`action="save"`). `index_session` is for
bulk session transcript indexing where BM25-style retrieval is more appropriate than exact
key lookup. The brain maintains these indices in Postgres and surfaces them through the
search actions.

**Design principle:** Any agent state that must survive compaction must be written to
tapps-brain *before* compaction occurs. The PreCompact hook is the safety net; explicit
`tapps_memory` writes after every significant decision are the primary defense.

---

## Defense-in-Depth Pattern

Resilient agent loops use three layers:

```
1. Explicit writes (primary)
   After each significant decision, call:
     tapps_memory(action="save", key="...", value="...", tier="procedural")
   This captures the decision durably, independent of any hook timing.

2. PreCompact hook (safety net)
   .claude/hooks/tapps-pre-compact.sh flushes in-flight state to brain
   just before context is compacted. Catches anything missed by layer 1.

3. Session rehydration (recovery)
   tapps_session_start re-injects brain state on session start / resume.
   SessionStart hook with matcher "compact" fires after compaction, giving
   the agent a fresh context injection from durable storage.
```

The SessionStart hook with the `compact` matcher (configured in
`.claude/settings.json` → `hooks.SessionStart`) fires immediately after compaction
completes. TappsMCP's generated `tapps-session-start.sh` hook calls `tapps_session_start`
at this point to re-inject project context, memory summaries, and server info.

---

## Failure Modes Avoided

With this pattern in place, the 12 failure classes from Issue #54393 are addressed:

| Failure class | Root cause | Defense |
|---|---|---|
| Duplicate task execution | Task-in-progress state only in context | Write task ID to brain at task start |
| Re-filing duplicate issues | Linear write intent only in context | Check brain for "filed" key before writing |
| Decision divergence | Prior decisions only in context | Write decisions to brain at decision time |
| Repeated tool calls | Tool results only in context | Cache results in brain with TTL |
| Orphaned in-progress state | Linear status update only in context | Mark In Progress in Linear AND write to brain |
| Loss of multi-step plan | Plan only in context | Write plan/checkpoint to brain at each step |

---

## Related Documents

- [ARCHITECTURE.md — Memory Architecture section](../ARCHITECTURE.md#memory-architecture)
- [MEMORY_REFERENCE.md](../MEMORY_REFERENCE.md)
- [ADR-0001: In-process AgentBrain via BrainBridge](../adr/0001-in-process-agentbrain-via-brainbridge.md)
- [EPIC-65.4: Auto-recall hook](../archive/planning/epics/EPIC-65.4-AUTO-RECALL-HOOK.md)
- [EPIC-65.5: Auto-capture hook](../archive/planning/epics/EPIC-65.5-AUTO-CAPTURE-HOOK.md)
- Anthropic Issue #54393: `github.com/anthropics/claude-code/issues/54393`
