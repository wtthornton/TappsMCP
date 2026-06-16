# 20. Global uv-tool default; blue/green deploy opt-in

Date: 2026-06-16

## Status

accepted (supersedes [0019](0019-blue-green-dev-monorepo-mcp-deploy.md) default behavior only)

## Context

ADR-0019 introduced blue/green deploy (`~/.tapps-mcp/current`) to stop in-place
`uv tool install --reinstall` from mutating files under live MCP stdio processes.
In practice on a single-operator machine with many Cursor windows and consumer
repos:

1. **Two global paths** coexisted (`~/.tapps-mcp/current` and
   `~/.local/share/uv/tools/tapps-mcp`), often at different effective versions.
2. **Generated Cursor wrappers** preferred `current` whenever the symlink existed,
   including consumer projects — not only the dev monorepo.
3. **`deploy-local` ran multiple times per session** while long-lived stdio
   children survived partial reloads → doctor PASS (fresh CLI probe) but Cursor
   ERROR (dead/stale processes).
4. **Orphan reap on deploy-local** does not replace a full fleet reload; sessionStart
   zombie cleanup was removed (ADR-0005 supersession) to protect multi-window
   workflows.

The operator preference: **one install story (global uv tool)**; blue/green only
when explicitly requested for zero-downtime dev deploy experiments.

## Decision

1. **Default MCP launch path:** global `uv tool install` shims at
   `~/.local/bin/{tapps-mcp,docsmcp}` (unchanged for consumers since ADR-0003).
2. **Blue/green is opt-in:** wrappers and drift probes use
   `~/.tapps-mcp/current` only when `TAPPS_MCP_USE_BLUE_GREEN=1` (or
   `true`/`yes`/`on`) is set in the environment **before** Cursor spawns MCP
   servers.
3. **`upgrade-fleet --reinstall-clis`** defaults to `uv tool install -e
   --reinstall`; pass **`--blue-green-deploy`** to run `deploy-local` instead.
4. **`deploy-local` remains available** for explicit zero-downtime flips when the
   operator sets `TAPPS_MCP_USE_BLUE_GREEN=1` and accepts reload discipline.

### Required operator workflow (global default)

After any global CLI reinstall:

```bash
pkill -f 'tapps-mcp serve' 2>/dev/null || true
pkill -f 'docsmcp serve' 2>/dev/null || true
uv tool install -e --reinstall packages/tapps-mcp   # from checkout
uv tool install -e --reinstall packages/docs-mcp
# Developer: Reload Window in every open Cursor project
```

Never mix `deploy-local` and `uv tool install --reinstall` in the same release
cycle without a full MCP restart.

## Consequences

**Positive:** Single source of truth for version; doctor, session_start, and CLI
align after reload; consumer and dev wrappers behave the same; fewer surprise
ERROR states from symlink flips under live processes.

**Negative:** In-place reinstall while MCP children are live can still cause
import errors (original ADR-0019 problem) — mitigated by mandatory
kill-and-reload workflow above, not by automatic blue/green.

**Neutral:** `~/.tapps-mcp/releases/` may remain on disk from prior deploys; inert
until `TAPPS_MCP_USE_BLUE_GREEN=1` is set.

## Implementation plan (phased)

| Phase | Scope | Status |
|-------|--------|--------|
| **0 — Recovery** | `pkill` + global reinstall + reload all Cursor windows | Operational |
| **1 — Opt-in gate** | `blue_green_enabled()`, wrapper template, drift probes, fleet CLI flag | Code (this release) |
| **2 — Docs** | CLAUDE.md, repo-workflow, TROUBLESHOOTING, supersede note on ADR-0019 index | Follow-up |
| **3 — Fleet refresh** | `upgrade-fleet --reinstall-clis` across consumer repos; regenerate wrappers | On demand |
| **4 — Optional** | `tapps doctor` reports active deploy mode (global vs blue/green env) | Nice-to-have |

## Alternatives

- **Keep blue/green as default (ADR-0019 as-is):** Rejected — dual-path drift
  recurred on single-operator multi-window setup.
- **Remove blue/green entirely:** Rejected — still useful for explicit
  zero-downtime experiments; keep `deploy-local` behind env flag.

## References

- [ADR-0019](0019-blue-green-dev-monorepo-mcp-deploy.md) — original blue/green decision
- [ADR-0005](0005-mcp-server-zombie-cleanup-hook-on-session-start.md) — sessionStart reap removal
- [ADR-0003](0003-no-pypi-or-npm-publish-global-install-from-local-checkout.md) — global install model
