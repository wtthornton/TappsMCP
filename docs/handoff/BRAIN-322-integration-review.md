# tapps-brain 3.22.0 — Integration Review for tapps-mcp + docs-mcp

> **Status (2026-06-03):** Findings 1, 2 implemented per [ADR-0012](../adr/0012-brain-capability-profile-per-consumer-role.md).
> Server bridge + generated `.mcp.json` now declare `full`; CLI auto-recall uses
> `reviewer`; docs-mcp stays on `agent_brain`; `tapps doctor` distinguishes a real
> gate from benign deferral. Finding 3 (payload_json) deferred until the brain
> version floor reaches ≥3.20.0. Finding 4 (feature adoption) is follow-up work.
>
> **Correction to the original Finding 1 below:** `diagnostics_report` IS in the
> `full` profile — `full` spans **100%** of `_BRIDGE_USED_TOOLS` (verified against
> `mcp_profiles.yaml`). `operator` only adds maintenance/admin tools the bridge
> degrades gracefully. So `full`, not `operator`, is the correct floor.

**Date:** 2026-06-03
**Reviewer:** Claude (Opus 4.8)
**Running brain:** 3.22.0 (HTTP service at `localhost:8080`)
**Installed in-process lib:** `tapps-brain` 3.18.0 (venv) — pin floor `>=3.18.0,<4`
**Scope:** Is tapps-mcp leveraging the newest brain (1) correctly and (2) using the features that help tapps-mcp / docs-mcp?

---

## Verdict

**docs-mcp: correct.** It declares the `agent_brain` profile, which exposes exactly the
`brain_*` facade (including `brain_get_neighbors` / `brain_explain_connection`) that its
`docs_kg_query` tool needs. No mismatch.

**tapps-mcp: one load-bearing correctness bug + several unused-feature gaps.** The runtime
`tapps_memory` facade runs on the `coder` profile, but its `BrainBridge` invokes ~30 brain
tools and `coder` exposes only ~12 of them. Against brain 3.22.0 (which **enforces** profile
gating on `tools/call`), the majority of `tapps_memory` actions are gated, not merely
deferred. This is already observable live in this session's `tapps_session_start`:

```
auth_probe: {ok:false, http_status:200, gated:true, tool:"memory_list",
             profile:"coder", suggested_profile:"reviewer"}
hive_status: degraded — "tapps-brain tool 'hive_status' is hidden by profile 'coder'"
memory_status: {enabled:false, degraded:true}
```

---

## Finding 1 — Profile mismatch: `coder` gates most of the `tapps_memory` surface  [HIGH]

The server singleton bridge that backs the `tapps_memory` tool (42 actions) is created with
`default_profile="coder"`:

- [server_helpers.py:155](../../packages/tapps-mcp/src/tapps_mcp/server_helpers.py#L155) — `create_brain_bridge(settings, default_profile="coder")`

`coder` (18 tools) exposes only the `brain_*` facade + session hooks + KG reads:
`brain_recall, brain_remember, brain_forget, brain_learn_success/failure, brain_status,
memory_index_session, memory_capture, tapps_brain_session_end, memory_search_sessions,
memory_reinforce, feedback_rate, feedback_gap, hive_search, memory_find_related,
brain_get_neighbors, brain_explain_connection, brain_record_events_batch`.

But `HttpBrainBridge` calls the **low-level** surface (`_BRIDGE_USED_TOOLS`,
[brain_bridge.py:301](../../packages/tapps-core/src/tapps_core/brain_bridge.py#L301)). Tools the
bridge invokes that `coder` does **not** expose (→ `ToolNotInProfileError` / `-32601` on first
call against 3.22.0):

| Bridge method | Brain tool called | In `coder`? |
|---|---|---|
| `save()` | `memory_save` ([2533](../../packages/tapps-core/src/tapps_core/brain_bridge.py#L2533)) | ❌ |
| `get()` | `memory_get` | ❌ |
| `delete()` | `memory_delete` | ❌ |
| `search()` | `memory_search` | ❌ |
| `list_memories()` | `memory_list` | ❌ (this is the gated auth-probe tool) |
| `recall_for_prompt()` | `memory_recall` | ❌ (`coder` has `brain_recall`, not `memory_recall`) |
| `supersede()` | `memory_supersede` | ❌ |
| `hive_status()` | `hive_status` | ❌ (degraded live) |
| `hive_propagate()` | `hive_propagate` | ❌ — and it's elevation-guard-wired at [server_helpers.py:163](../../packages/tapps-mcp/src/tapps_mcp/server_helpers.py#L163) |
| `agent_register()` | `agent_register` | ❌ |
| `record_kg_event()` | `brain_record_event` (singular) ([2122](../../packages/tapps-core/src/tapps_core/brain_bridge.py#L2122)) | ❌ (`coder` has only `brain_record_events_batch`) |
| `save_many/recall_many/reinforce_many()` | `memory_*_many` | ❌ |
| `flywheel_report/process()` | `flywheel_*` | ❌ |
| `diagnostics_report()` | `diagnostics_report` | ❌ (operator-only) |

In `coder`, exposed: `brain_recall`, `brain_remember`, `memory_reinforce`,
`memory_find_related`, `brain_get_neighbors`, `brain_explain_connection`, `feedback_rate/gap`,
`memory_index_session`, `memory_search_sessions`, `tapps_brain_session_end`, `hive_search`,
`brain_record_events_batch`. Everything else the facade offers is gated.

**Why it was masked.** The hook-path bridges (auto-recall/capture) use only the coder subset,
so they work — [auto_capture.py:98](../../packages/tapps-mcp/src/tapps_mcp/memory/auto_capture.py#L98),
[compact_index.py:47](../../packages/tapps-mcp/src/tapps_mcp/memory/compact_index.py#L47). `coder`
is correct *for those*. The bug is that the **server** bridge backing the full `tapps_memory`
tool shares the same narrow profile. (This repo also has memory hooks disabled, so the breakage
isn't felt here — but every consuming project that enables `tapps_memory` writes/reads against a
gated brain hits it.)

**Confirms the prior finding** captured in memory `reference_brain_profile_tool_map`: *"no single
profile spans all"* the tools the bridge needs.

### Fix
Give the **runtime server bridge** a profile that matches `_BRIDGE_USED_TOOLS`:

- **Minimum correct floor: `full`** — exposes all 63 standard tools. Under 3.20+ deferred-loading,
  only 8 appear in `tools/list`, but all remain **callable via `tools/call`**, and TAP-2100 removed
  the bridge preflight-reject, so the bridge calls them directly with no gating.
- **`operator`** if `diagnostics_report`, `gc` (`maintenance_gc`), and `consolidate` must run live
  rather than degrade — those three are operator-only. The CLI admin path already uses `operator`
  ([cli.py:1036](../../packages/tapps-mcp/src/tapps_mcp/cli.py#L1036)); the server does not.
- **Do not** leave the server on `coder` — that profile is for embedded `brain_*`-facade consumers
  (like docs-mcp), not the full-fidelity `tapps_memory` gateway.

Change [server_helpers.py:155](../../packages/tapps-mcp/src/tapps_mcp/server_helpers.py#L155) (and the
non-admin CLI path [cli.py:795](../../packages/tapps-mcp/src/tapps_mcp/cli.py#L795)) from `"coder"` to
`"full"` (or `"operator"`). Keep `auto_capture` / `compact_index` on `coder` — they're correct.
Consumers can still override via `memory.brain_profile` in `.tapps-mcp.yaml`
([brain_auth.py:89](../../packages/tapps-core/src/tapps_core/brain_auth.py#L89)).

---

## Finding 2 — `doctor` remediation hint misattributes a real `coder` gate as benign  [MEDIUM]

[doctor.py:1718 `check_brain_profile`](../../packages/tapps-mcp/src/tapps_mcp/distribution/doctor.py#L1718)
correctly computes `gated_used = _BRIDGE_USED_TOOLS - exposed`, but its failure hint
([doctor.py:1808](../../packages/tapps-mcp/src/tapps_mcp/distribution/doctor.py#L1808)) says the
mismatch is *"expected for the 'full'/'operator' profiles — deferred tools remain callable."*
That is true for `full`/`operator` but **false for `coder`/`reviewer`/`agent_brain`/`seeder`**,
where the tools are genuinely absent from the profile and `tools/call` rejects them.

### Fix
Branch the hint on the declared profile. If `declared in {full, operator}` → "deferred, benign."
Otherwise → "genuine gate: these calls will raise `ToolNotInProfileError`; switch
`memory.brain_profile` to a profile that exposes them." The data to do this is already in scope
(`declared`, `gated_used`).

---

## Finding 3 — `record_kg_event` uses the singular tool + legacy `payload_json`  [LOW]

[brain_bridge.py:2122](../../packages/tapps-core/src/tapps_core/brain_bridge.py#L2122) calls
`brain_record_event` (singular) with `{"payload_json": json.dumps(...)}`.

- Singular `brain_record_event` is **not** in `coder` (only `brain_record_events_batch` is) —
  folds into Finding 1; resolved by the profile fix.
- `payload_json` is the **legacy alias**. Brain 3.20 moved to native list/dict shapes
  (`entities`, `edges`, `payload` passed directly). The alias still works
  ([`tools_kg.py`](https://github.com/wtthornton/tapps-brain/blob/main/src/tapps_brain/mcp_server/tools_kg.py#L94)
  — *"native `payload` wins; when only `payload_json` is provided, emit…"*), so this is
  deprecated-but-functional, not broken. Migrate to native shapes before the alias is dropped.

---

## Finding 4 — Newer 3.19–3.22 features tapps-mcp could adopt  [feature gaps]

All present in the running 3.22.0, none wired into tapps-mcp:

1. **`brain_resolve_entity`** (3.21) — deterministic 2-pass entity→UUID resolution (no LLM).
   tapps-mcp currently derives entity IDs locally for KG upserts (TAP-1949); routing through
   `resolve_entity` would dedupe entities across repos/sessions and align with brain's canonical
   resolution. In `full`/`operator` and `agent_brain`.
2. **`recall_quality_metrics(window_seconds, project_id)`** (3.20) — server-side p50/p95 top-score,
   oldest-age, empty-recall-rate. Natural feed for `tapps_dashboard` / `tapps_stats` to show memory
   health instead of inferring it client-side.
3. **`brain_audit_consumers(project_id, since)`** (3.20) — "declared but silent" agents. Useful in
   `tapps doctor` to flag a registered-but-unused brain consumer.
4. **`/v1/tools/list` ETag + `Cache-Control` + 304** (3.20) — the bridge's warm-cache probe
   ([doctor.py:1772](../../packages/tapps-mcp/src/tapps_mcp/distribution/doctor.py#L1772)) could send
   `If-None-Match` to short-circuit catalog refetches.
5. **`/v1/experience:batch`** (256 KB body, 100 events/txn, 3.19) + `brain_record_events_batch`
   (already in `coder`) — prefer batch KG ingestion over the per-event `record_kg_event` loop when
   recording multiple entities/edges from one analysis pass.
6. **Configurable explain ceilings** — `TAPPS_BRAIN_KG_EXPLAIN_MAX_HOPS` /
   `…_BRANCHING_FACTOR` (3.19). Surface as tunables for `explain_connection`-heavy callers.

(For docs-mcp specifically: it's correctly scoped today. The only adoption worth considering is
`brain_resolve_entity` if `docs_kg_query` ever needs name→entity resolution, which `agent_brain`
already exposes — no profile change required.)

---

## Finding 5 — In-process fallback lib is 3.18.0 while the service is 3.22.0  [INFO]

The venv's `tapps_brain` is 3.18.0; the HTTP service is 3.22.0. Since this repo runs in HTTP mode,
the 3.22.0 service is what's exercised — fine. But if `memory.brain_http_url` is ever unset, the
bridge falls back to in-process `AgentBrain` at 3.18.0, which lacks the 3.19–3.22 KG/`resolve_entity`
surface. Bumping the in-process lib to 3.22.0 keeps the two transports at feature parity. Low
priority while HTTP is the default.

---

## Prioritized recommendations

| # | Action | Severity | Effort |
|---|---|---|---|
| 1 | Switch the **server** bridge default profile `coder` → `full` (or `operator`). Keep hook bridges on `coder`. | HIGH | S |
| 2 | Profile-aware `doctor` hint: distinguish real gate (`coder`/`reviewer`/…) from benign deferral (`full`/`operator`). | MED | S |
| 3 | Migrate `record_kg_event` off `payload_json` to native `payload`/`entities`/`edges` shapes. | LOW | S |
| 4 | Adopt `recall_quality_metrics` in `tapps_dashboard`/`tapps_stats`; consider `brain_resolve_entity` for KG upserts; `If-None-Match` on the tools/list warm-cache probe. | LOW | M |
| 5 | Bump in-process `tapps-brain` lib 3.18.0 → 3.22.0 for transport parity (pin floor stays `>=3.18.0`). | INFO | S |

## Open decisions for you

- **#1 profile target — `full` vs `operator`?** `full` is the correct minimum and keeps the
  server's surface tight; `operator` additionally lets `gc` / `consolidate` / `diagnostics_report`
  run live instead of degrading. Pick `operator` only if those admin `tapps_memory` actions need to
  be functional from the running server (vs the CLI, which already uses `operator`).
- Should the profile fix ship as a template/scaffolding change too, so existing consumers pick it up
  via `tapps_upgrade` (version bump required per repo-workflow rules), or only as the in-repo default?
