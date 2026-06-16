# 23. Immutable MCP CLI releases — no in-place uv tool reinstall

Date: 2026-06-16

## Status

accepted (supersedes [0020](0020-global-uv-tool-default-blue-green-opt-in.md) inplace-default behavior)

## Context

MCP servers run as long-lived stdio child processes. Cursor (and other hosts)
keep a pipe open to a Python interpreter whose code lives under either:

- `~/.local/share/uv/tools/tapps-mcp/` (mutable `uv tool install` venv), or
- `~/.tapps-mcp/releases/<version>-<sha>/` (immutable blue/green release)

**Root cause of fleet-wide MCP death:** `uv tool install --reinstall` replaces
the mutable venv **in place** while live stdio servers still hold open handles
to the old tree. Python lazy-imports then read swapped files → import errors,
stdio drop, Cursor **error** state. Restarting Cursor does not help until the
corrupt process tree is cleared because the wrapper still targets the same
mutable path.

Generated Cursor wrappers made this worse by baking the absolute
`~/.local/share/uv/tools/.../bin/tapps-mcp` path into `exec` lines instead of
stable launchers.

ADR-0020 kept in-place reinstall as the default and made blue/green opt-in via
`TAPPS_MCP_USE_BLUE_GREEN=1`. That failed in practice: fleet rollout ran
in-place reinstall, deploy-local coexisted on the same machine, and consumer
repos (AgentForge, etc.) embedded mutable paths — dual-path drift and unrecoverable
Cursor errors without manual `pkill`.

## Decision

1. **Fleet / global CLI refresh uses blue/green only** — `upgrade-fleet
   --reinstall-clis` defaults to `deploy-local` (immutable release + flip
   `~/.tapps-mcp/current`). In-place reinstall requires explicit
   `--force-inplace-cli-reinstall` (operator accepts killing all MCP windows).

2. **Wrappers never embed `~/.local/share/uv/tools/*` paths** —
   `_resolve_global_cli()` returns `~/.local/bin/<tool>` shims or nothing.
   Every generated wrapper includes a runtime probe:
   `exec ~/.tapps-mcp/current/bin/<tool>` when executable, then fallback.

3. **After blue/green deploy, regenerate all fleet Cursor wrappers** so
   consumer repos pick up the runtime `current` probe without a manual init.

4. **`uv tool install --reinstall` remains for terminal CLI bootstrap** when no
   MCP `serve` processes are running — not for MCP server launch paths.

## Consequences

**Positive:** In-place venv mutation cannot kill MCP servers during normal fleet
upgrades; one immutable `current` symlink for all projects on a machine; Cursor
restart works because new spawns use a new release directory.

**Negative:** First deploy builds a release venv (~minutes); disk under
`~/.tapps-mcp/releases/`; operators reload MCP after deploy for new code in new
processes (running servers stay pinned until reload — by design).

## References

- [ADR-0019](0019-blue-green-dev-monorepo-mcp-deploy.md) — original blue/green model
- [ADR-0020](0020-global-uv-tool-default-blue-green-opt-in.md) — superseded inplace default
- [ADR-0005](0005-mcp-server-zombie-cleanup-hook-on-session-start.md) — orphan reap on deploy
