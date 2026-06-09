# Handoff — tapps-mcp consumer migration (brain EPIC-074/075 shipped)

Paste this into a tapps-mcp session (or a Linear comment on TAP-1997 / TAP-1998).

## Context

tapps-brain shipped EPIC-074 and EPIC-075 in commit `1e8b5d3` on tapps-brain `main`.
**Do not modify tapps-brain** — consume these APIs from tapps-mcp only.

## Brain deploy prerequisite (human/ops)

1. Deploy tapps-brain build containing `1e8b5d3` (or later).
2. Run private migration 024 (`profile_scoped_data`) — `make brain-migrate` or migrate sidecar.
3. Confirm `GET http://<brain>:8080/v1/skill` returns `{name, version, body}` with version matching the deployed image.

---

## Task A — TAP-1997: Retire local metrics JSONL reads (phase 2)

**Goal:** Stop reading `.tapps-mcp/metrics/*.jsonl` for tool-call quality data; read from brain instead.

### Brain surfaces (already live)

- **MCP:** `brain_query_events(event_type, since?, until?, entity_id?, limit?)`
- **REST:** `POST /v1/experience:query`
  - Headers: `X-Project-Id`, auth per existing brain bridge
  - Body: `{"event_type": "quality_metric", "entity_id": "<file_path>", "limit": 100}`
  - Returns: `{"events": [{"event_id", "event_type", "payload", "ts", "agent_id", ...}], "count"}`

Writes already work via `brain_record_event` with `EntitySpec` accepting `{type, id}` shorthand
(e.g. `{"type":"file","id":"src/foo.py"}`).

### tapps-mcp changes

1. Find every code path that reads `.tapps-mcp/metrics/*.jsonl` (likely `tapps_stats`, dashboard, checklist history).
2. Replace with `brain_query_events` filtered by `event_type` (`quality_metric`, `quality_gate_fail`, `checklist_outcome`) and `entity_id = file path` when scoping per-file.
3. Map payload fields: `score`, `duration_ms`, `gate_passed`, `started_at`, `file_path`.
4. Keep local JSONL write as fallback only if `brain_bridge_health.ok` is false — or remove entirely if epic says hard cutover.
5. Add/update tests that mock the brain bridge and assert round-trip against the contract in `docs/engineering/experience-events.md` (in tapps-brain repo — read only).

**Optional convenience (P2):** `brain_get_neighbors` now accepts `entity_refs_json` — array of `{entity_type, canonical_name}` or `{type, id}` — so per-file graph queries don't need a separate `brain_resolve_entity` call.

### Done when

- `tapps_stats` / metrics consumers work with brain reachable and **no local JSONL read on happy path**.
- TAP-1997 acceptance criteria met; local JSONL can be deleted or deprecated per TAP-1996 plan.

### tapps-mcp status (2026-06-09)

| Item | Status |
|------|--------|
| Phase 1 — `quality_metric` emit via `record_kg_event` + `entity_spec()` | **Done** |
| Phase 1.5 — dual-write + interim `memory_save` read fallback | **Done** (fallback still in `load_tool_call_metrics_from_brain`) |
| `brain_bridge.query_events()` consumer | **Done** |
| `tapps_dashboard` / `tapps_stats` brain hydrate | **Done** when `TAPPS_METRICS_STORAGE=brain` |
| Default read path (no JSONL on happy path) | **Done** — unset env → `brain` when bridge healthy, else `dual`; explicit `dual`/`brain`/`local` override |
| Per-file `entity_id` filter on reads | **Done** — `entity_id` param on `load_tool_call_metrics_from_brain` / `_load_from_disk` |
| Checklist / other JSONL consumers | **Not audited** |

---

## Task B — TAP-1998: Migrate domain weights YAML to brain profile KV

**Goal:** Stop persisting `.tapps-mcp/adaptive/domain_weights.yaml`; use brain profile-scoped learned data.

### Brain surfaces (already live)

- **MCP:** `brain_profile_set(profile, key, value_json)` / `brain_profile_get(profile, key)`
- **REST:**
  - `POST /v1/profile/data:set` — body: `{"profile": "repo-brain", "key": "domain_weights", "value_json": {...}}`
  - `POST /v1/profile/data:get` — body: `{"profile": "repo-brain", "key": "domain_weights"}`
  - Returns set: `{"ok": true}`; get: `{"ok": true, "value_json": {...}}` or `{"ok": false}`
- Scoped by `X-Project-Id` + negotiated `X-Brain-Profile` (profile gate applies).
- Tools registered in `full` and `operator` MCP profiles.

### tapps-mcp changes

1. In `DomainWeightStore` (or equivalent in tapps-core adaptive module), replace YAML read/write with `brain_profile_get`/`set` via existing HTTP bridge.
2. Use the negotiated profile name from brain profile negotiation — don't hardcode unless that's already the contract.
3. Key suggestion: `domain_weights` (matches brain integration test).
4. One-time migration: on first brain-backed read, if `brain_profile_get` returns `ok: false`, load existing YAML and `brain_profile_set` to seed, then stop touching the file.
5. Tests: round-trip set/get; graceful behavior when brain unreachable (fail closed or cached — match existing adaptive policy).

### Done when

- Domain weights survive across sessions without `.tapps-mcp/adaptive/domain_weights.yaml`.
- TAP-1998 closed.

### tapps-mcp status (2026-06-09)

| Item | Status |
|------|--------|
| `DomainWeightStore` YAML persistence | **Fallback only** — brain profile KV when bridge healthy; YAML seeds on first read |
| `brain_profile_get` / `brain_profile_set` bridge methods | **Done** — `HttpBrainBridge.profile_get` / `profile_set` |

---

## Out of scope for this handoff (track separately)

- **TAP-1996** — broader local-state file removal (metrics + adaptive + others).
- **TAP-2000** — checklist write via `brain_record_event`; read-back via
  `fetch_prior_checklist_outcome` → `brain_query_events` (done 2026-06-09).
- **TAP-2003** — quality gate failures as KG events.
- **TAP-2981 consumer** — optional: fetch skill via `GET /v1/skill` instead of vendored GitHub raw URL (AgentForge / HTTP-only clients).

## Constraints

- **Do not edit tapps-brain.** If an API gap is found, file a new tapps-brain Linear issue and stop.
- Use existing tapps-mcp brain HTTP bridge patterns (`TAPPS_BRAIN_BASE_URL`, auth token, `X-Project-Id`, profile negotiation).
- Run tapps-mcp quality pipeline on changed files before declaring done.

## Linear issues to close when done

- **TAP-1997**, **TAP-1998** (and **TAP-1996** when all local-state paths are migrated).

## References (tapps-mcp)

- `packages/tapps-core/src/tapps_core/metrics/brain_telemetry.py` — emit + `load_tool_call_metrics_from_brain`
- `packages/tapps-core/src/tapps_core/brain_bridge.py` — `query_events`, `record_kg_event`
- `packages/tapps-core/src/tapps_core/adaptive/persistence.py` — `DomainWeightStore` (YAML today)
- `packages/tapps-mcp/src/tapps_mcp/server_metrics_tools.py` — `tapps_stats` / `tapps_dashboard` hydrate
- `docs/handoff/BRAIN-wave2-capabilities.md` — brain capability request history
