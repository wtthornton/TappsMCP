# 18. Deploy all six NLT MCP servers by default (full bundle)

Date: 2026-06-16

## Status

Accepted (2026-06-16)

Supersedes [ADR-0016](0016-needs-based-nlt-mcp-taxonomy.md) on the **default bundle**
only. ADR-0016's needs-based taxonomy (Build / Memory / Setup profiles, server IDs,
zero-duplication rules, session bundle definitions) remains in force.

## Context

ADR-0016 made `tapps_init` / `tapps_upgrade` write the **`developer`** bundle by
default — `nlt-build`, `nlt-memory`, `nlt-linear-issues` active, with `nlt-setup`,
`nlt-project-docs`, and `nlt-release-ship` as commented opt-in blocks. The goal was to
stay inside the doctor partial-enablement budget (≤3 servers, ≤20 combined eager tools).

In practice the opt-in friction outweighed the eager-tool savings:

- Consumers regularly hit "tool not available" gaps mid-task (docs generation, release
  notes, bootstrap/diagnostics) because the owning server was commented out, then had to
  hand-edit `mcp.json` and reload the IDE.
- Maintainer repos (AgentForge, the tapps-mcp dev checkout) already set
  `mcp_bundle: full` explicitly, so the "default down" only affected the consumers least
  equipped to debug a missing server.
- The eager-tool count for all six servers is bounded and known (≈30 eager), and modern
  MCP hosts tolerate it. The cost is real but it is a single steady-state cost, not a
  per-task surprise.

The deployment process should make the full surface available by default, and let
token-tight users **opt down** — the inverse of ADR-0016's opt-up model.

## Decision

The deployment default bundle is **`full`** (all six `nlt-*` servers active).

- `normalize_mcp_bundle(None | invalid)` returns `full` (was `developer`).
- `_infer_mcp_bundle` falls back to `full` when no bundle is set in `.tapps-mcp.yaml`
  and no `nlt-*` servers are already enabled on disk. An explicit `mcp_bundle` in
  `.tapps-mcp.yaml`, or a set of enabled servers that matches a smaller bundle, is still
  honored — this change only moves the **unset/fresh** default.
- `tapps_init` / `tapps_upgrade` and the `--bundle` CLI flags default to `full`.
- The single source of truth is `DEFAULT_NLT_BUNDLE` in
  `packages/tapps-mcp/src/tapps_mcp/distribution/nlt_mcp_config.py`.

Opting down stays first-class: `--bundle developer|minimal|...` or
`mcp_bundle: developer` in `.tapps-mcp.yaml`.

### Doctor

`check_nlt_partial_enablement` already treats six enabled servers with a resolved
`mcp_bundle=full` as an **intentional PASS** (not a WARN). With `full` as the resolved
default, fresh deployments pass cleanly. The partial-enablement WARN now only fires for
genuine mismatches (e.g. servers enabled that don't match any bundle, or six servers
while the resolved bundle is smaller than `full`).

## Consequences

### Positive

- No mid-task "enable the other server and reload" friction — the full tool surface is
  present after a single `tapps_init` / `tapps_upgrade`.
- Maintainer and consumer repos converge on the same default; fewer config drift bugs.
- Opt-down is explicit and discoverable via `--bundle` / `mcp_bundle`.

### Negative

- Higher steady-state eager-tool count per session (≈30 vs ≈18 for `developer`). Token-
  tight sessions must opt down with `--bundle minimal|developer`.
- **Multi-window cost:** running multiple IDE windows against the same project now spawns
  six `serve` processes per window instead of three. On constrained machines this can
  surface as transient "errored" MCP status in the IDE during global CLI reinstalls; the
  mitigation is the session-start zombie cleanup (ADR-0005) and reloading the window.
- The doctor partial-enablement budget (≤3 servers) is no longer the deployment default;
  it remains the recommendation for explicitly token-constrained sessions.

## Alternatives considered

1. **Keep `developer` default (ADR-0016)** — Rejected: opt-up friction caused repeated
   mid-task tool gaps for the consumers least able to fix `mcp.json` by hand.
2. **Write all six but leave three commented (present-but-inactive)** — Rejected: still
   requires a manual uncomment + reload to use the docs/release/setup tools; does not
   remove the friction, only relocates it.
3. **Per-host heuristic (full on maintainer repos, developer elsewhere)** — Rejected:
   adds hidden, hard-to-debug branching; explicit `mcp_bundle` already covers the
   maintainer case.

## References

- [ADR-0016](0016-needs-based-nlt-mcp-taxonomy.md) — needs-based taxonomy (superseded on default only)
- [ADR-0005](0005-mcp-server-zombie-cleanup-hook-on-session-start.md) — zombie cleanup mitigates multi-window churn
- [nlt-mcp-plugin-spec.yaml](../architecture/nlt-mcp-plugin-spec.yaml)
- `packages/tapps-mcp/src/tapps_mcp/distribution/nlt_mcp_config.py` — `DEFAULT_NLT_BUNDLE`
