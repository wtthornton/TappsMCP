# tapps_memory Deprecation Migration Table (TAP-1991)

**Status:** REMOVED — v3.12.0 (TAP-1994, Phase 3 complete 2026-Q2).
The `tapps_memory` MCP tool is no longer registered in any server preset.
Session-lifecycle helpers (`_handle_session_start_capture`,
`_handle_session_end_consolidate`) survive as internal Python functions called
from `tapps_session_start` / `tapps_session_end`; they are not public MCP tools.

**Phase 1 (TAP-1991):** Description-embedded deprecation warnings added to every
sub-action so Claude's tool catalog signals the migration target. ✅

**Phase 2 (TAP-1992):** Per-action call-count telemetry via `brain_record_event` so
adoption can be measured. ✅

**Phase 3 (TAP-1990/TAP-1994):** `tapps_memory` removed from MCP catalog;
`register()` in `server_memory_tools.py` is now a no-op for this tool. ✅

---

## Migration Table

| `tapps_memory` action | Replacement brain tool | Notes |
|---|---|---|
| `save` | `mcp__tapps-brain__brain_remember` | Direct key/value write |
| `save_bulk` | `mcp__tapps-brain__brain_remember` | Call in a loop or use brain's batch endpoint |
| `get` | `mcp__tapps-brain__brain_recall` | Recall by key |
| `list` | `mcp__tapps-brain__brain_recall` | Recall with broad query; filter client-side |
| `delete` | `mcp__tapps-brain__brain_recall` | No direct delete tool; use brain HTTP API |
| `search` | `mcp__tapps-brain__memory_search` | Full-text search |
| `reinforce` | `mcp__tapps-brain__brain_remember` | Re-save with updated confidence |
| `gc` | `mcp__tapps-brain__brain_status` | Housekeeping via brain status/health probe |
| `contradictions` | `mcp__tapps-brain__brain_status` | Contradiction detection is brain-side |
| `reseed` | `mcp__tapps-brain__brain_status` | Profile reseed is a brain operation |
| `import` | `mcp__tapps-brain__brain_remember` | Batch-save imported entries |
| `export` | `mcp__tapps-brain__brain_recall` | Recall all, serialize locally |
| `consolidate` | `mcp__tapps-brain__brain_recall` | Consolidation is brain-side logic |
| `unconsolidate` | `mcp__tapps-brain__brain_recall` | Undo consolidation via brain API |
| `validate` | `mcp__tapps-brain__brain_status` | Validation delegates to brain |
| `maintain` | `mcp__tapps-brain__brain_status` | Maintenance is a brain-side operation |
| `safety_check` | `mcp__tapps-brain__brain_status` | Safety checks run in brain |
| `verify_integrity` | `mcp__tapps-brain__brain_status` | Integrity checks run in brain |
| `health` | `mcp__tapps-brain__brain_status` | Direct health probe |
| `profile_info` | `mcp__tapps-brain__brain_status` | Profile metadata from brain status |
| `profile_list` | `mcp__tapps-brain__brain_status` | Profile list from brain status |
| `profile_switch` | `mcp__tapps-brain__brain_status` | Profile switching is a brain operation |
| `federate_register` | `mcp__tapps-brain__brain_status` | Federation state in brain |
| `federate_publish` | `mcp__tapps-brain__brain_status` | Publish via brain federation API |
| `federate_subscribe` | `mcp__tapps-brain__brain_status` | Subscribe via brain federation API |
| `federate_sync` | `mcp__tapps-brain__brain_status` | Sync via brain federation API |
| `federate_search` | `mcp__tapps-brain__hive_search` | Federated search → hive_search |
| `federate_status` | `mcp__tapps-brain__brain_status` | Federation status from brain |
| `hive_status` | `mcp__tapps-brain__brain_status` | Hive status from brain |
| `hive_search` | `mcp__tapps-brain__hive_search` | Direct hive search |
| `hive_propagate` | `mcp__tapps-brain__brain_status` | Propagation is brain-side |
| `agent_register` | `mcp__tapps-brain__brain_status` | Agent registration in brain |
| `related` | `mcp__tapps-brain__memory_find_related` | Knowledge graph traversal |
| `relations` | `mcp__tapps-brain__memory_find_related` | Explicit relation listing |
| `neighbors` | `mcp__tapps-brain__brain_get_neighbors` | N-hop neighbor lookup |
| `explain_connection` | `mcp__tapps-brain__brain_explain_connection` | Graph path explanation |
| `recall_many` | `mcp__tapps-brain__brain_recall` | Batch recall (loop or batch endpoint) |
| `reinforce_many` | `mcp__tapps-brain__brain_remember` | Batch reinforce |
| `rate` | `mcp__tapps-brain__brain_remember` | Feedback via brain remember |
| `index_session` | `mcp__tapps-brain__brain_remember` | Session indexing via brain |
| `search_sessions` | `mcp__tapps-brain__memory_search` | Session search via memory_search |
| `session_end` | `mcp__tapps-brain__brain_status` | Session finalization in brain |

---

## How to migrate

1. Replace any `tapps_memory(action="X", ...)` call with the corresponding
   `mcp__tapps-brain__<tool>` call shown above.
2. Pass `key=` and `value=` directly to `brain_remember(fact="key: value")` or
   use the structured `brain_recall(query="key")` for reads.
3. For searches, use `memory_search(query="...")` directly.
4. For knowledge graph operations, use the dedicated `brain_get_neighbors`,
   `memory_find_related`, or `brain_explain_connection` tools.

## Timeline

- **2026-Q3:** All sub-actions marked DEPRECATED in tool catalog (TAP-1991) ✅
- **2026-Q3:** Per-action call telemetry enabled (TAP-1992) ✅
- **2026-Q3:** Reduced to lifecycle-only actions, refusal envelope added (TAP-1993) ✅
- **2026-Q3:** `tapps_core/memory/` re-export shims deleted (TAP-1995) ✅
- **2026-Q4 / v3.12.0:** Tool removed from MCP catalog (TAP-1994) ✅
- **2026-Q4 / v3.12.0:** Migration guide and playbook reference finalized (TAP-1990) ✅
