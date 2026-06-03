# 12. Select the tapps-brain capability profile per consumer role

Date: 2026-06-03

## Status

accepted

## Context

tapps-brain gates its MCP tool surface by the `X-Brain-Profile` request header.
Each profile exposes a curated subset of the ~76 brain tools
(`packages`/`mcp_server/mcp_profiles.yaml` in the tapps-brain repo):

| Profile | Tools | Intended consumer |
|---|---|---|
| `full` | 63 | full-fidelity clients (all standard read+write+hive+KG+feedback) |
| `operator` | 76 | operator scripts (full + maintenance/admin) |
| `coder` | 18 | repo-embedded coding agent (`brain_*` facade + capture/reinforce + KG reads) |
| `reviewer` | 8 | read-only PR/review agents (recall + search + graph) |
| `agent_brain` | 12 | canonical `AgentBrain` consumer (`brain_*` facade only) |
| `seeder` | 6 | bulk ingestion scripts (write-only) |

Two facts make profile choice load-bearing:

1. **From tapps-brain v3.20.0, the gate is enforced on every `tools/call`**
   (TAP-1929). A tool absent from the negotiated profile fails with
   `ToolNotInProfileError` (`-32602`), not a silent no-op.
2. **There is no single profile that fits every consumer.** The `coder`
   profile — which the tapps-mcp server bridge declared — is deliberately
   narrow: it exposes the `brain_*` facade plus a few hook tools, but **not**
   the low-level `memory_save`/`memory_get`/`memory_search`/`memory_list`/
   `memory_supersede`, `hive_status`/`hive_propagate`, `agent_register`, the
   `*_many` batch ops, `flywheel_*`, or `diagnostics_report`.

The tapps-mcp server singleton bridge backs the `tapps_memory` tool — a
42-action facade that exercises the **whole** low-level surface
(`_BRIDGE_USED_TOOLS`, 27 tools in `brain_bridge.py`). Running that facade on
`coder` gated ~18 of those tools. The breakage was masked in the tapps-mcp dev
repo (memory hooks disabled there) but every consuming project that enables
`tapps_memory` writes/reads against a v3.20.0+ brain hit it. The live
`tapps_session_start` probe showed it directly: `auth_probe.gated=true,
tool=memory_list, profile=coder, suggested_profile=reviewer`, and
`hive_status` "hidden by profile 'coder'".

Separately, `tapps doctor`'s `check_brain_profile` computed the gated set
correctly but its remediation hint claimed the gap was "expected for the
'full'/'operator' profiles — deferred tools remain callable" — which is only
true for `full`/`operator` (TAP-1985 deferred-loading) and actively misleading
for `coder`, where the tools are genuinely gated.

## Decision

**Choose the least-privilege profile that spans the tools each consumer role
actually calls, and name those choices as constants** in
`tapps_core.brain_bridge` so call sites stop hard-coding magic strings:

```python
BRAIN_PROFILE_SERVER   = "full"         # tapps_memory facade (read+write+hive+KG+feedback)
BRAIN_PROFILE_OPERATOR = "operator"     # CLI maintenance (gc/consolidate/config/export)
BRAIN_PROFILE_READONLY = "reviewer"     # read-only recall/search (CLI auto-recall)
BRAIN_PROFILE_HOOKS    = "coder"        # auto-recall/capture/reinforce + KG reads
BRAIN_PROFILE_FACADE   = "agent_brain"  # brain_* facade only (docs-mcp KG queries)
```

Role → call site:

- **Server runtime** (`server_helpers._get_brain_bridge`) → `full`. `full` is
  the *smallest* profile that exposes all of `_BRIDGE_USED_TOOLS`. The
  maintenance ops the facade can also call (`maintenance_gc`,
  `maintenance_consolidate`) are operator-only, are **not** in
  `_BRIDGE_USED_TOOLS`, and already degrade gracefully — so `full`, not
  `operator`, is the correct floor.
- **CLI auto-recall** (`cli._auto_recall`) → `reviewer`. It calls only
  `memory_search`; `reviewer` is the least-privilege profile exposing it.
  (It previously used `coder`, which hides `memory_search`, so auto-recall
  silently returned no hits on v3.20.0+.)
- **CLI maintenance** (`cli`, admin path) → `operator` (unchanged).
- **Memory hooks** (`memory/auto_capture`, `memory/compact_index`) → `coder`
  (unchanged — they only call the coder subset; `coder` is correct for them).
- **docs-mcp** (`docs_kg_query`) → `agent_brain` (unchanged — it calls only
  `brain_get_neighbors`/`brain_explain_connection`, both in `agent_brain`).

A consumer still overrides any of these via `memory.brain_profile` in
`.tapps-mcp.yaml` (or `TAPPS_BRAIN_PROFILE`); that value wins over the
`default_profile` passed to `create_brain_bridge`.

`tapps doctor` is made profile-aware: a gap under `full`/`operator`
(`BRAIN_PROFILES_DEFERRED_OK`) is reported as benign deferred-loading; a gap
under any narrow profile is reported as a genuine gate with a fix hint
pointing at `full`. Doctor also now probes with the server default profile
when none is configured, so its diagnosis matches what the runtime uses.

## Consequences

**Positive:**

- The `tapps_memory` facade works end-to-end against v3.20.0+ brains in
  consuming projects. Writes, reads, hive status, batch ops, and KG events are
  no longer gated.
- Profile choices are centralized, named, and documented — a reviewer sees the
  role and rationale instead of a bare `"coder"` string. Adding a tool to
  `_BRIDGE_USED_TOOLS` that `full` doesn't expose is now a visible decision.
- `tapps doctor` gives correct, actionable guidance instead of waving away a
  real gate as benign.
- Least-privilege is preserved where it's cheap: hooks stay on `coder`,
  read-only recall on `reviewer`, docs-mcp on `agent_brain`. Only the
  full-facade server uses `full`.

**Negative:**

- The server bridge surface widens from 18 tools (`coder`) to 63 (`full`).
  This is the surface the facade already needed; the previous narrow value was
  simply wrong for it. The token/attack-surface concern that motivated `coder`
  applies to embedded single-purpose agents, not to the tapps_memory gateway.

**Neutral:**

- Transport, version floor (`>=3.18.0`, ADR-0010/0011), circuit breaker, and
  offline-queue behavior are unchanged.
- No consumer config migration required; the change ships in package source and
  is picked up on the next `tapps_upgrade` / global reinstall.

## Alternatives considered

**Use `operator` for the server bridge.** Rejected as the default: `operator`
adds maintenance/admin tools (`maintenance_*`, `memory_*_config`,
`memory_export/import`) that are not in `_BRIDGE_USED_TOOLS`; the bridge already
degrades the two maintenance ops it can invoke. `operator` remains available via
`memory.brain_profile` for deployments that want `gc`/`consolidate` to run live.

**Refactor the bridge to route writes through the `brain_*` facade so `coder`
suffices.** Rejected: `coder` has no facade equivalent for `memory_list`,
`memory_supersede`, the `*_many` batch ops, `flywheel_*`, or
`diagnostics_report`. The facade is a strict subset; the wide profile is the
honest fit for a wide tool.

**Migrate `record_kg_event` off the deprecated `payload_json` alias to native
`payload`/`entities`/`edges` shapes (review Finding 3).** Deferred: native
shapes are a v3.20.0 feature, but the version floor is 3.18.0 (ADR-0010), so
native-only writes would break consumers on 3.18/3.19 brains. Revisit when the
floor moves to `>=3.20.0`.
