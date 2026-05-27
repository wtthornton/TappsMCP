# Compaction Resilience

**TAP-2017** — `memory_index_session` at compaction boundary + verify load on rehydration

## Problem

Anthropic Claude Code Issue #54393 (2026-04-28) catalogued a class of multi-agent
coordination failures rooted in **post-compaction memory loss**: when Claude Code
compacts the context window, the model's recent operator directives — settled
decisions, task state, editing rules — are summarized and the original text is
discarded.  The post-compact agent re-litigates everything from the summary, which
may lose detail.

The root cause is the absence of a persistent backing store that survives
compaction.  `tapps-brain`'s `memory_index_session` / `memory_search_sessions`
tools are the natural solution for tapps-mcp projects.

## Fix (Claude Code 2.1.105+ PreCompact hook)

Claude Code 2.1.105 introduced the `PreCompact` hook event, which fires **before**
the context window is compacted.  This gives hooks an opportunity to persist the
about-to-be-lost context.

TappsMCP wires this up in two parts:

### Part 1 — PreCompact hook (`tapps-pre-compact.sh`)

The hook calls `tapps-mcp compact-index --project-root "$PROJECT_DIR"` with the
pre-compact payload piped via stdin.  The CLI command:

1. Extracts (or generates) a `session_id` from the payload.
2. Builds a small set of indexable text chunks from the payload's `summary`,
   `context`, and `trigger` fields.
3. Calls `memory_index_session(session_id, chunks)` on the brain bridge so the
   pre-compact state is searchable via `memory_search_sessions` in subsequent
   sessions.
4. Writes `.tapps-mcp/compaction-marker.json` with `{session_id, compacted_at,
   chunks, indexed_in_brain}` so `tapps_session_start` can detect the compaction
   on the next invocation.

The hook is best-effort: if the brain is unavailable, the marker file is still
written (for operator inspection), and the hook exits 0 so compaction proceeds
normally.

**Escape hatch:** set `TAPPS_MCP_COMPACTION_REHYDRATE=false` to disable all
indexing and marker writes.

### Part 2 — Session-start rehydration (`tapps_session_start`)

When `tapps_session_start` runs after a compaction, it calls
`_check_compaction_rehydration(project_root)` which:

1. Checks for `.tapps-mcp/compaction-marker.json`.  If absent, returns `None`
   (no compaction detected).
2. Reads the `session_id` and `indexed_in_brain` flag from the marker.
3. Deletes the marker file to prevent stale rehydration on subsequent calls.
4. If `indexed_in_brain=True`, calls `bridge.search_sessions("compaction_boundary:
   <session_id>", limit=5)` to retrieve the indexed chunks.
5. Returns a `compaction_rehydration` dict that is included in the
   `tapps_session_start` response under `data.compaction_rehydration`.

The agent sees the rehydration data as part of the first `tapps_session_start`
call after a compaction and can act on it (e.g. re-read summarised decisions,
check prior task state).

## Data flow

```
Claude Code (pre-compact)
  → tapps-pre-compact.sh
    → tapps-mcp compact-index
      → compact_index.py::run_compact_index()
        ├── bridge.index_session(session_id, chunks)  ← brain
        └── write .tapps-mcp/compaction-marker.json

Claude Code (post-compact, next tapps_session_start call)
  → tapps_session_start()
    → _check_compaction_rehydration(project_root)
      ├── read .tapps-mcp/compaction-marker.json
      ├── unlink marker (prevent re-surface)
      └── bridge.search_sessions("compaction_boundary:<id>", limit=5)  ← brain
    → data["compaction_rehydration"] = {session_id, compacted_at, prior_chunks}
```

## Key files

| File | Purpose |
|---|---|
| `.claude/hooks/tapps-pre-compact.sh` | PreCompact hook; calls `tapps-mcp compact-index` |
| `packages/tapps-mcp/src/tapps_mcp/memory/compact_index.py` | Core logic: extract, index, write marker |
| `packages/tapps-mcp/src/tapps_mcp/cli.py` | `compact-index` CLI command |
| `packages/tapps-mcp/src/tapps_mcp/tools/session_start_helpers.py` | `_check_compaction_rehydration()` |
| `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py` | Wire rehydration into `tapps_session_start` |
| `packages/tapps-core/src/tapps_core/brain_bridge.py` | `HttpBrainBridge.index_session()` / `.search_sessions()` |

## Operator guidance

- **No action required** when the brain is running: the hook and session-start
  wiring activate automatically.
- **Disable rehydration** by adding `TAPPS_MCP_COMPACTION_REHYDRATE=false` to
  the MCP server's env block in `.mcp.json`.
- **Inspect the last compact payload** at `.tapps-mcp/pre-compact-context.json`
  (written by the hook as a disk fallback; not deleted by session-start).
- **Brain unavailable**: the marker file is still written with
  `indexed_in_brain: false`.  Session-start detects it, logs the compaction
  event, but has no chunks to return — the agent sees
  `compaction_rehydration.prior_chunks: []`.

## References

- Anthropic Claude Code Issue #54393 — post-compaction memory loss
- `tapps-brain` `memory_index_session` / `memory_search_sessions` — session
  indexing and search tools
- Claude Code 2.1.105+ PreCompact hook release notes
- TAP-2013 parent epic: Hive promotion safety + post-compaction memory defense
