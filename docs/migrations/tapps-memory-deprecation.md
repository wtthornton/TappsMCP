# tapps_memory Deprecation Migration Table (TAP-1991)

**Status:** SUPPORTED — restored as a slim facade (TAP-3895, ADR-0016,
commit `7486cc34`, 2026-06-13). `tapps_memory` is **not deprecated and not
removed**. It is registered on the `nlt-memory` profile alongside four
other tools (`tapps_session_start`, `tapps_session_notes`,
`tapps_session_end`, `tapps_handoff_save`) — see
`TOOL_PROFILE_NLT_MEMORY` in
[`packages/tapps-mcp/src/tapps_mcp/server.py`](../../packages/tapps-mcp/src/tapps_mcp/server.py).
It is not registered on any other profile (`nlt-build`, `nlt-setup`, etc.).

There is no `mcp__tapps-brain__*` MCP surface to redirect to and there
never has been one. `tapps-brain` is bridge-only: agents call it through
`tapps_memory` / `BrainBridge`, never as a direct MCP server entry (see
[`.claude/rules/integration-hygiene.md`](../../.claude/rules/integration-hygiene.md)
and [ADR-0001](../adr/0001-in-process-agentbrain-via-brainbridge.md)). A
`tapps-brain` entry in `.mcp.json` is a regression, not a migration target;
`tapps_doctor` strips it.

The session-lifecycle handlers (`_handle_session_start_capture`,
`_handle_session_end_consolidate` in
[`server_memory_tools.py`](../../packages/tapps-mcp/src/tapps_mcp/server_memory_tools.py))
are reachable **only** through the `tapps_memory` dispatch table
(`action="session_start_capture"` / `action="session_end_consolidate"`).
They are not called from `tapps_session_start` / `tapps_session_end` — those
are separate tools on the same `nlt-memory` profile.

## What actually happened (Q2 2026)

The original 42-action catalog was migrated toward direct CLI / BrainBridge
calls, per the phase table below. That migration completed. Separately,
ADR-0016's needs-based taxonomy restored `tapps_memory` as a supported tool
on the `nlt-memory` profile (TAP-3895) — the tool was never permanently
removed from the shipped product; "Phase 3" below describes an internal
milestone in a prior plan that this restoration supersedes.

**Phase 1 (TAP-1991):** Description-embedded deprecation warnings added to
every sub-action so Claude's tool catalog signalled the (then-planned)
migration target. ✅ (superseded by ADR-0016 — the tool is no longer
deprecated)

**Phase 2 (TAP-1992):** Per-action call-count telemetry via
`brain_record_event` so adoption could be measured. ✅

**Phase 3 (TAP-1990/TAP-1994):** Historical: `tapps_memory` was removed from
older presets during this migration window. **Superseded by TAP-3895 /
ADR-0016**, which restored it as the `nlt-memory` profile's facade. Do not
treat this row as the current state.

---

## How to call tapps_memory today

`tapps_memory(action=..., ...)` is a normal MCP tool call — no redirect
needed. See the tool's docstring in `server_memory_tools.py` for the full
action list (`save`, `save_bulk`, `get`, `list`, `delete`, `search`,
`reinforce`, `session_start_capture`, `session_end_consolidate`, and more).
For scripted / CLI use outside an agent session, use
`uv run tapps-mcp memory search --query "..."` or `tapps-mcp memory save`,
which talk to `BrainBridge` directly without going through MCP.

## Timeline

- **2026-Q3:** All sub-actions marked DEPRECATED in tool catalog (TAP-1991) ✅ (later reverted)
- **2026-Q3:** Per-action call telemetry enabled (TAP-1992) ✅
- **2026-Q3:** Tool removed from some server presets during the 42-action migration (TAP-1993/1994) ✅ (historical)
- **2026-Q3:** `tapps_core/memory/` re-export shims deleted (TAP-1995) ✅
- **2026-06-13:** `tapps_memory` restored as a slim facade on the `nlt-memory`
  profile (TAP-3895, ADR-0016, commit `7486cc34`) ✅ — current state
