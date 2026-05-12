# 5. MCP server zombie-cleanup hook on session start

Date: 2026-05-02

## Status

accepted

## Context

Claude Code spawns a fresh MCP server subprocess (one tapps-mcp + one docs-mcp) per session. When a session ends — whether by user exit, terminal close, or crash — the parent process does not consistently reap its MCP children. Over weeks of use, dozens of stale tapps-mcp / docs-mcp processes accumulate, each holding a Postgres connection to tapps-brain and ~200MB of resident memory. Manual `pkill` works but is not discoverable to operators who haven't been told about the leak.

## Decision

`.claude/hooks/tapps-session-start.sh` runs a cleanup block on every Claude Code session start that kills any tapps-mcp / docsmcp process older than 2 hours before spawning the new one. The hook is shipped by `tapps_init` / `tapps_upgrade` into consumer projects. The 2-hour threshold is intentionally generous — long-running explicit sessions are preserved; only true abandon-and-respawn zombies get reaped.

## Consequences

**Positive:** Operators see bounded process and memory growth without manual intervention. Each new session starts against a clean slate; brain Postgres connection pool stays under control.

**Negative:** A user with a deliberately-long single session (>2 hours) who opens a second Claude Code window will have their original MCP server killed at the second window's startup. Acceptable in practice: MCP servers are stateless across sessions.

**Operational note:** The cleanup block is load-bearing — do not remove from the hook template.
