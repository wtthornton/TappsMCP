# tapps_memory Deprecation Migration

**Status:** Phase 2 complete (TAP-1993, 2026-05-26)

## Summary

`tapps_memory` is being retired in favour of direct `mcp__tapps-brain__*` tool calls.
The migration is split into two phases so callers have time to update before the tool
is removed.

---

## Phase 1 — Deprecation notices + telemetry (TAP-1991 / TAP-1992)

**Shipped in:** 3.21.x

- Every action in `_VALID_ACTIONS` gained a `[DEPRECATED 2026-Q3 — use mcp__tapps-brain__<tool>]`
  prefix in the `tapps_memory` docstring so Claude's tool catalog signals the migration target.
- Every `tapps_memory` invocation fires a best-effort `brain_record_event("deprecated_tool_call",
  "tapps_memory:<action>")` so removal timing is data-driven.

### How to find Phase 1 telemetry

```
tapps_memory(action="health")   # brain → check_events for deprecated_tool_call
```

---

## Phase 2 — Refused-envelope redirect (TAP-1993)

**Shipped in:** 3.22.x

All `tapps_memory` actions except the two **lifecycle** actions now return a structured
refused envelope instead of executing:

```json
{
  "refused": true,
  "use": "mcp__tapps-brain__<tool>",
  "action": "<original-action>",
  "hint": "tapps_memory(action='<action>') has been retired. Call <brain-tool> directly instead."
}
```

The envelope is returned as `success=True` so agents can inspect `data.refused` and
self-correct by switching to the `use` tool — no error-path handling required.

### The two surviving lifecycle actions

| Action | Brain primitive | Purpose |
|---|---|---|
| `session_start_capture` | `brain_remember` (index_session) | Index session start into brain memory |
| `session_end_consolidate` | `brain_status` (session_end) | Finalize and consolidate session in brain |

These are **not deprecated** — they are the canonical way to call the session-lifecycle
primitives through tapps-mcp. All other 42 actions redirect.

### Action → brain tool redirect map

| tapps_memory action | Redirect to |
|---|---|
| `save`, `save_bulk`, `reinforce`, `reinforce_many`, `import`, `rate`, `index_session` | `mcp__tapps-brain__brain_remember` |
| `get`, `list`, `delete`, `export`, `consolidate`, `unconsolidate`, `recall_many` | `mcp__tapps-brain__brain_recall` |
| `search`, `search_sessions` | `mcp__tapps-brain__memory_search` |
| `related`, `relations` | `mcp__tapps-brain__memory_find_related` |
| `neighbors` | `mcp__tapps-brain__brain_get_neighbors` |
| `explain_connection` | `mcp__tapps-brain__brain_explain_connection` |
| `federate_search`, `hive_search` | `mcp__tapps-brain__hive_search` |
| everything else | `mcp__tapps-brain__brain_status` |

---

## Migration guide

### Before (tapps_memory)

```python
# Save a memory
tapps_memory(action="save", key="my-key", value="my value", tier="pattern")

# Search memories
tapps_memory(action="search", query="relevant query")

# Get brain health
tapps_memory(action="health")
```

### After (direct brain tools)

```python
# Save a memory
mcp__tapps-brain__brain_remember(fact="my value", key="my-key")

# Search memories
mcp__tapps-brain__memory_search(query="relevant query")

# Get brain health
mcp__tapps-brain__brain_status()
```

### Session lifecycle (unchanged interface)

```python
# Start of session — still goes through tapps_memory
tapps_memory(action="session_start_capture", value="Session intent: ...")

# End of session — still goes through tapps_memory
tapps_memory(action="session_end_consolidate", value="Session summary: ...")
```

---

## Phase 3 — Planned removal

After telemetry confirms non-lifecycle call volume has reached zero (or all known
callers have migrated), `tapps_memory` will be removed entirely in a future release.
The two lifecycle actions will be promoted to first-class MCP tools at that point.

Track progress in Linear project **TappsMCP Platform** under the TAP-1993 epic.
