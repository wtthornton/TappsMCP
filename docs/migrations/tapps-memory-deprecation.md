# tapps_memory: status and history (TAP-1991…TAP-3895)

**Status:** SUPPORTED — restored as a slim facade (TAP-3895, ADR-0016,
commit `7486cc34`, 2026-06-13). `tapps_memory` is **not deprecated and not
removed**. It is registered on the `nlt-memory` profile alongside four
other tools (`tapps_session_start`, `tapps_session_notes`,
`tapps_session_end`, `tapps_handoff_save`) — see
`TOOL_PROFILE_NLT_MEMORY` in
[`packages/tapps-mcp/src/tapps_mcp/server.py`](../../packages/tapps-mcp/src/tapps_mcp/server.py).
It is not registered on any other profile (`nlt-build`, `nlt-setup`, etc.).

Agents must never call `mcp__tapps-brain__*` directly, and `.mcp.json` must
never carry a `tapps-brain` entry — `tapps-brain` does expose a live MCP tool
surface (`brain_recall`, `brain_remember`, …;
[`docs/handoff/BRAIN-322-integration-review.md`](../handoff/BRAIN-322-integration-review.md),
`_BRIDGE_USED_TOOLS` in `brain_bridge.py`), but it is bridge-only: agents call
it through `tapps_memory` / `BrainBridge`, never as a direct MCP server entry (see
[`.claude/rules/integration-hygiene.md`](../../.claude/rules/integration-hygiene.md)
and [ADR-0001](../adr/0001-in-process-agentbrain-via-brainbridge.md)). A
`tapps-brain` entry in `.mcp.json` is a regression, not a migration target.
`tapps_doctor` reports it as a failed check (`check_brain_mcp_entry` in
`doctor_mcp.py`); `tapps_upgrade` (and `tapps_init` / `setup_generator`) are
what actually strip it, via `strip_brain_mcp_entries`.

The session-lifecycle handlers (`_handle_session_start_capture`,
`_handle_session_end_consolidate` in
[`server_memory_tools.py`](../../packages/tapps-mcp/src/tapps_mcp/server_memory_tools.py))
are reachable **only** through the `tapps_memory` dispatch table
(`action="session_start_capture"` / `action="session_end_consolidate"`).
They are not called from `tapps_session_start` / `tapps_session_end` — those
are separate tools on the same `nlt-memory` profile.

## What actually happened (Q2 2026)

The catalog held 42 actions when the migration began; TAP-1993 then added the
two session-lifecycle actions (`session_start_capture`,
`session_end_consolidate`), so today's `_VALID_ACTIONS` holds
<!-- count:valid-actions -->44<!-- /count -->. Every count below is derived
from that set. That catalog was migrated toward direct CLI / BrainBridge
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

Over MCP, `tapps_memory(action=..., ...)` accepts **exactly** these
<!-- count:mcp-actions -->7<!-- /count --> actions
(`NLT_MEMORY_SLIM_ACTIONS ∪ _LIFECYCLE_ACTIONS` in `server_memory_tools.py`):

<!-- mcp-actions:start -->
- `search`
- `save`
- `get`
- `health`
- `related`
- `session_start_capture`
- `session_end_consolidate`
<!-- mcp-actions:end -->

Separately, the CLI (`tapps-mcp memory <command>`) offers **exactly** these
<!-- count:cli-commands -->10<!-- /count --> commands
(`@memory_group.command(...)` in `cli_memory.py`):

<!-- cli-commands:start -->
- `list`
- `save`
- `get`
- `recall`
- `search`
- `promote-instincts`
- `delete`
- `import-file`
- `export-file`
- `reseed`
<!-- cli-commands:end -->

These are independent implementations that call `BrainBridge` /
`MemoryStore` directly — they do not dispatch through the `tapps_memory`
action table above, so "CLI command X" does not imply "MCP action X is
reachable via the CLI". Only <!-- count:name-matched -->3<!-- /count --> catalog
actions outside the MCP surface happen to share a name with a CLI command:
`list`, `delete`, `reseed`.

An MCP call is refused in one of two ways, both without dispatching:

- an `action` outside `_VALID_ACTIONS` entirely (the full historical
  catalog) is refused with `invalid_action`;
- an `action` inside `_VALID_ACTIONS` but outside
  `NLT_MEMORY_SLIM_ACTIONS ∪ _LIFECYCLE_ACTIONS` is refused with
  `action_not_on_nlt_memory`.

Every other `_VALID_ACTIONS` entry — i.e. `_VALID_ACTIONS` minus the
<!-- count:mcp-actions -->7<!-- /count --> MCP actions above, minus the
<!-- count:name-matched -->3<!-- /count --> name-matched CLI commands
(`list`, `delete`, `reseed`) — is **unreachable in this release**: refused
over MCP and not exposed by any CLI command. That is
<!-- count:unreachable -->34<!-- /count --> actions:

<!-- unreachable-actions:start -->
`agent_register`, `consolidate`, `contradictions`, `explain_connection`,
`export`, `federate_publish`, `federate_register`, `federate_search`,
`federate_status`, `federate_subscribe`, `federate_sync`, `gc`,
`hive_propagate`, `hive_search`, `hive_status`, `import`, `index_session`,
`maintain`, `neighbors`, `profile_info`, `profile_list`, `profile_switch`,
`rate`, `recall_many`, `reinforce`, `reinforce_many`, `relations`,
`safety_check`, `save_bulk`, `search_sessions`, `session_end`,
`unconsolidate`, `validate`, `verify_integrity`
<!-- unreachable-actions:end -->

(`import`/`export` are distinct from the `import-file`/`export-file` CLI
commands: those call `tapps_brain.io.import_memories` / `export_memories`
against a local `MemoryStore`, not the `tapps_memory` dispatch table, so they
do not make the `import`/`export` actions reachable.)

So pick the surface by what you need. Over MCP, call `tapps_memory` with one
of the entries in the mcp-actions block above. On the command line, invoke one
of the entries in the cli-commands block above — for example
`uv run tapps-mcp memory search --query "..."` or `tapps-mcp memory save`,
which talk to `BrainBridge` / `MemoryStore` directly without going through
MCP. Neither surface reaches the other's entries.

## Timeline

- **2026-05-22:** All sub-actions marked DEPRECATED in tool catalog (TAP-1991) ✅ (later reverted)
- **2026-05-22:** Per-action call telemetry enabled (TAP-1992) ✅
- **2026-05-26:** Tool removed from some server presets during the 42-action migration (TAP-1993/1994) ✅ (historical)
- **2026-05-26:** `tapps_core/memory/` re-export shims deleted (TAP-1995) ✅
- **2026-06-01:** Migration marked complete — status set to REMOVED, all
  three phases marked ✅ (TAP-1990, commit `861d269c`) ✅ (superseded by
  TAP-3895 below)
- **2026-06-13:** `tapps_memory` restored as a slim facade on the `nlt-memory`
  profile (TAP-3895, ADR-0016, commit `7486cc34`) ✅ — current state
