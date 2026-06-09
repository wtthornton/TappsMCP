# Handoff → tapps-brain: capabilities needed to unblock the "migrate local state into brain" epic (TAP-1996)

**Status:** requested by tapps-mcp 2026-06-01; revised 2026-06-09 after brain-side review.
These are **tapps-brain** changes — they cannot be made from the tapps-mcp repo (see
`.claude/rules/agent-scope.md` / `.claude/rules/integration-hygiene.md`). File as issues in
the tapps-brain tracker.

## Write-path reality (corrected 2026-06-09)

`tapps-mcp` emits `brain_record_event` payloads with a rich **`experience_events.payload`**
dict (scores, durations, gate flags, timestamps). That **does persist** even when KG
side-effects are malformed.

Brain `EntitySpec` expects `entity_type` / `canonical_name` (not `type` / `id`). Brain
`EdgeSpec` expects pre-resolved entity UUIDs (not `src` / `dst` string paths). Since
tapps-brain 3.22.4, bad side-effects are skipped with warnings; the core event row still
commits.

**Implication:** "writes work" means **payload persistence**, not full KG linkage. Per-file
score history for dashboard migration should use **`brain_query_events` filtered on
`payload.file_path` / `subject_key`**, not `brain_get_neighbors`.

**Tapps-mcp fix (shipped 2026-06-09):** All `record_kg_event` call sites in
tapps-core / tapps-mcp now emit `entity_type` / `canonical_name` via
`kg_keys.entity_spec()`, set `subject_key` (and `file_path` where relevant) in
payloads, and omit malformed string-based edges. Event types:
`quality_metric`, `quality_gate_fail`, `validate_completed`, `security_finding`,
`checklist_outcome`, hive elevation, deprecated-tool telemetry.

## Tapps-mcp progress (TAP-1997)

| Phase | Status | Notes |
|-------|--------|-------|
| 1 — KG event + payload write | Done | Phase 1 + entity shapes on all emitters (2026-06-09) |
| 1.5 — `memory_save` workaround | Done | Interim read path; **remove after P0** |
| 2 — drop local JSONL by default | Blocked | Needs `brain_query_events` (P0 below) |

Set `TAPPS_METRICS_STORAGE=brain` to skip local JSONL (opt-in). Requires brain auth +
memory hydrate or, after P0, `brain_query_events`.

## Why

Epic TAP-1996 migrates three per-project local-state categories into brain:

- TAP-1997 — `metrics/` quality scores → experience events
- TAP-2000 — checklist outcomes → experience events (write-only today)
- TAP-1998 — `domain_weights.yaml` → profile-scoped KV

## Capability 1 — `brain_query_events` (P0, blocking TAP-1997 phase 2)

**Problem.** Metrics scalars live on `experience_events.payload`. `brain_get_neighbors`
returns KG edge structure only — not event payloads. Dashboard / `tapps_stats` aggregations
cannot drop local JSONL without an event read API.

**Do not** extend `brain_get_neighbors` to return payloads — wrong table, wrong scaling.

**Request.** Add MCP tool + REST route (mirror `feedback_query` vocabulary):

```
brain_query_events(
    event_type: str,           # required, e.g. "quality_metric"
    since?: str,              # ISO-8601 UTC
    until?: str,
    entity_id?: str,          # v1: match payload.file_path OR subject_key
    limit?: int = 100,        # cap 500 server-side
) -> {
    events: [{
        event_id: str,
        event_type: str,
        payload: dict,        # full write-time payload
        ts: str,              # event_time ISO-8601 UTC
        agent_id: str,
        session_id?: str,
    }],
    count: int,
}
```

**v1 `entity_id` filter:** `experience_events` stores `created_entity_id` (first entity
only). For metrics, filter on `payload->>'file_path'` and/or `subject_key` — tapps-mcp
sets both.

**Profiles:** `full`, `operator`, `reviewer` (same defer_loading pattern as
`brain_record_event`).

**Unblocks:** TAP-1997 dashboard read-back, TAP-2000 prior-outcome reads.

**Version:** tapps-brain **>=3.24.0** once shipped. Bump tapps-mcp floor after release.

## Capability 2 — entity identity (revised; not a P0 blocker for metrics)

**Reject UUIDv5 entity IDs (TAP-1949 as originally scoped).** Brain already provides
stable identity via `brain_resolve_entity(entity_type, canonical_name)` — same inputs →
same UUID, upsert on `(brain_id, entity_type, canonical_name_norm)`.

**Optional P0.5 (brain):** `EntitySpec` coercion for legacy `type`/`id` shorthands (same
pattern as existing `key` shorthand).

**Optional P2 (brain):** `entity_refs: [{entity_type, canonical_name}]` on
`brain_get_neighbors` for ergonomic graph walks.

**tapps-mcp actions (no brain release required):**

- Emit `entity_type` / `canonical_name` on all `record_kg_event` call sites
- Use `brain_resolve_entity` before graph queries when edges are needed
- Per-file **metrics** history via `brain_query_events`, not `get_neighbors`

## Capability 3 — profile KV (P2, TAP-1998)

**Problem.** No `brain_profile_set` / `brain_profile_get` for learned per-profile data
(domain weights).

**Request (v1, project-scoped — no federation yet):**

```
brain_profile_set(profile, key, value_json) -> {ok: bool}
brain_profile_get(profile, key) -> {ok: bool, value_json?: str}
```

Table: `(project_id, profile_name, data_key) → value_json`.

**Interim workaround (tapps-mcp):** `brain_remember` with key
`profile:{profile}:domain_weights` — same debt pattern as `metrics:tool_call:*`; remove
when P2 ships.

## Dependency order

```
Done (tapps-mcp):    all record_kg_event entity shapes + subject_key (2026-06-09)
P0 (tapps-brain):  brain_query_events + index + tests  ← waiting here
Then (tapps-mcp):  wire query_events consumer; drop JSONL + memory_save workaround
P2 (tapps-brain):  brain_profile_set/get
P2 (tapps-mcp):    TAP-1998 domain weights
```

**Critical path for TAP-1997 phase 2 = P0 only.**

## Version floor (tapps-mcp recommendation)

| When | Floor | Rationale |
|------|-------|-----------|
| Now | `>=3.22.4,<4` | Resilient side-effect writes; `brain_resolve_entity` |
| After P0 ships | `>=3.24.0,<4` | `brain_query_events` |

Current pin remains `>=3.18.0,<4` until ADR superseded.

## Note for non-Python consumers

Bash hooks cannot call brain async APIs. TAP-2000 dropped hook reads of
`.checklist-state.json`. TAP-1997 dashboard hooks need either a tapps-mcp-written local
cache derived from brain reads, or feature removal — tapps-mcp-side decision, not a brain
requirement.

## References (tapps-mcp)

- `packages/tapps-core/src/tapps_core/knowledge/kg_keys.py` — `entity_spec()` helper
- `packages/tapps-core/src/tapps_core/metrics/brain_telemetry.py` — `quality_metric` emit + `TAPPS_METRICS_STORAGE`
- `packages/tapps-core/src/tapps_core/brain_bridge.py` — `record_kg_event`, `query_events` scaffold
- Emitters: `server_scoring_tools.py`, `validate_changed.py`, `server.py`, `server_helpers.py`, `server_memory_tools.py`
- Linear: TAP-1996, TAP-1997, TAP-1998, TAP-2000
