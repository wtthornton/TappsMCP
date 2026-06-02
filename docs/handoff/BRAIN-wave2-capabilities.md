# Handoff → tapps-brain: capabilities needed to unblock the "migrate local state into brain" epic (TAP-1996)

**Status:** requested by tapps-mcp 2026-06-01. These are **tapps-brain** changes — they
cannot be made from the tapps-mcp repo (see `.claude/rules/agent-scope.md` /
`.claude/rules/integration-hygiene.md`). File as issues in the tapps-brain tracker.

## Why

Epic TAP-1996 (TappsMCP Platform) migrates three per-project local-state files into brain so
state is visible across sessions/agents:

- TAP-1997 — `metrics/` quality scores → brain events
- TAP-2000 — `.checklist-state.json` → brain events
- TAP-1998 — `adaptive/domain_weights.yaml` → brain profile data

All three have a clean **write** path today (`BrainBridge.record_kg_event` /
`record_event`). They are blocked on the **read** path: the data written cannot be read
back in the shape the consumers need. Two distinct brain capabilities are missing.

## Capability 1 — event reads must return the event payload

**Problem.** `brain_record_event` accepts a rich payload (`payload` dict with scalars like
`score`, `duration_ms`, `timestamp`). But the only event read-back,
`brain_get_neighbors`, returns *graph structure only*:
`{edge_id, predicate, edge_confidence, neighbor_id, entity_type, canonical_name, hop}`.
The scalar payload is not returned. tapps-mcp's dashboard / `tapps_stats` / `tapps_usage`
rolling aggregations (counts, averages, gate-skip-rate over a rolling window) need those
scalars, so the local JSON write cannot be removed without losing live telemetry.

**Request.** Provide a read that returns recorded event payloads, filterable by
`event_type` and time window. Suggested shapes (either works for tapps-mcp):

- Extend `brain_get_neighbors` to include each edge's stored `payload` dict, **or**
- Add a `brain_query_events(event_type, since, until, entity_id?, limit)` returning
  `[{event_type, entities, edges, payload, ts}]`.

Unblocks: TAP-1997 (dashboard reads from brain), TAP-2000 (`tapps_checklist` queries prior
outcomes).

## Capability 2 — entities addressable by deterministic key (not opaque UUID)

**Problem.** `brain_get_neighbors` takes a JSON array of entity **UUID** strings. tapps-mcp
wants to address an entity by a stable, derivable key (e.g. a file path), per TAP-1997's
acceptance `brain_get_neighbors(entity_ids=[<file_id>])`. There is no path→UUID lookup, and
keys are not deterministic today.

**Request.** This is already scoped as **TAP-1949** (deterministic UUIDv5 entity keys) in the
KG-migration epic TAP-1916. Capability 1 should land alongside or after TAP-1949 so reads can
be addressed by derived keys.

Unblocks: TAP-1997 per-file score-history criterion.

## Capability 3 — profile-data read/write surface (for TAP-1998)

**Problem.** The brain/`BrainBridge` profile surface is **negotiation-only**
(`X-Brain-Profile` header, `profile_status()`, `out_of_profile` envelope). There is no
`get_profile_data` / `set_profile_data` endpoint to store agent-scoped, per-profile learned
data (TAP-1998 wants to move `domain_weights.yaml` here so weights transfer across projects
via the profile/federation system).

**Request.** Add a profile-keyed key/value read/write to the brain, e.g.
`brain_profile_set(profile, key, value_json)` / `brain_profile_get(profile, key)`, scoped to
the negotiated agent profile and federation-capable (so `hive_propagate` can share weights).
If a memory-scope/tag mechanism is the intended substitute, document that as the supported
path instead.

Unblocks: TAP-1998 (domain-weights migration).

## Note for the non-Python consumers (tapps-mcp side, after the above land)

Two readers of the local files are **bash hooks**, which cannot call the async brain:

- TAP-2000: `tapps-user-prompt-submit.sh` reads `.checklist-state.json` to surface the
  per-turn "open checklist" reminder.
- TAP-1997: dashboard/report sidecars are read by `tapps-report` summary hooks.

When the local writes are removed, those hook features must either be dropped or backed by a
tapps-mcp-written local cache derived from a brain read (a tapps-mcp-side decision, tracked on
the respective stories — not a brain requirement).
