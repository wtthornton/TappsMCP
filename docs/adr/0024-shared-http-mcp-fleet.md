# ADR-0024: Shared HTTP MCP fleet for multi-window Cursor

## Status

Accepted (2026-06-16)

## Context

Cursor spawns one stdio MCP child process **per window per server**. With the default **full** NLT bundle (six servers) and 2–5 Cursor windows, a machine runs 12–30+ long-lived `serve --profile nlt-*` processes.

Cursor also rotates stdio MCP connections every ~9–10 minutes (`transport_closed`). When many connections drop together, Cursor’s reconnect path can fail for several minutes — reload window does not always respawn servers. CLI smoke tests of `.cursor/bin/nlt-*-serve.sh` still pass; the failure is host lifecycle + process count, not broken TappsMCP binaries.

Blue/green CLI deploy (ADR-0019, ADR-0023) fixed **in-place reinstall killing live stdio children** but not the multi-window stdio architecture.

## Decision

Run **six long-lived HTTP MCP servers** on fixed localhost ports (8760–8765), started once per machine via:

- `tapps-mcp fleet start` (or `scripts/nlt-http-fleet.sh start`)
- Optional systemd user unit: `tapps-mcp fleet install-systemd`

Consumer projects opt in with `mcp_transport: http` in `.tapps-mcp.yaml` or `tapps-mcp init --mcp-transport http`. Host MCP configs use `streamableHttp` URLs instead of stdio wrapper scripts.

| Server | Port | Endpoint |
|--------|------|----------|
| nlt-build | 8760 | http://127.0.0.1:8760/mcp |
| nlt-memory | 8761 | http://127.0.0.1:8761/mcp |
| nlt-setup | 8762 | http://127.0.0.1:8762/mcp |
| nlt-linear-issues | 8763 | http://127.0.0.1:8763/mcp |
| nlt-project-docs | 8764 | http://127.0.0.1:8764/mcp |
| nlt-release-ship | 8765 | http://127.0.0.1:8765/mcp |

**Per-project identity:** each `.cursor/mcp.json` entry sends `X-Tapps-Project-Root: <absolute consumer path>`. HTTP middleware binds that header to a contextvar; `load_settings()` / `load_docs_settings()` honor it per request so one fleet serves every repo/window.

**Fleet process env:** `~/.tapps-mcp/fleet.env` sets `TAPPS_FLEET_CODE_ROOT` (default `~/code` when present) for path mapping via `TAPPS_MCP_HOST_PROJECT_ROOT`. Operator secrets load from `~/.tapps-operator.env` (same as stdio wrappers).

## Consequences

### Positive

- **Six processes total** regardless of Cursor window count — eliminates rotation/reconnect storms from per-window stdio spawns.
- Reload / multi-window no longer multiplies MCP children.
- Fleet survives Cursor restarts; windows reconnect to existing HTTP endpoints.
- Same blue/green `~/.tapps-mcp/current/bin/*` binaries as stdio wrappers.

### Negative / limits

- Requires one-time fleet start (systemd recommended for login persistence).
- All consumer repos must regenerate MCP config (`init --mcp-transport http` or yaml).
- Fleet code root must cover all repos (default `~/code`; override in `fleet.env`).
- Claude Code / remote hosts: HTTP fleet is localhost-first; remote dev needs port forwarding or stays on stdio.

## Alternatives considered

1. **Developer bundle (3 servers)** — reduces load but does not fix stuck reconnect.
2. **Reload / toggle MCP** — operational workaround, not structural.
3. **Per-window stdio + orphan-only cleanup** — necessary but insufficient (ADR-0005, v3.12.36+ hooks).

## Rollout

```bash
# 1. Start fleet (once per machine)
tapps-mcp fleet start
# optional: tapps-mcp fleet install-systemd && systemctl --user enable --now tapps-mcp-fleet

# 2. Per consumer repo
tapps-mcp init --host cursor --mcp-transport http --force --bundle full

# 3. Reload Cursor once — MCP connects to HTTP URLs (no stdio spawn)
```

Revert: set `mcp_transport: stdio` in yaml and re-run `tapps-mcp upgrade --host cursor`.
