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

**Supervision / systemd cgroup constraint (load-bearing):** `fleet start` launches the six servers as plain subprocesses (`setsid`, not a new systemd scope), so they remain in the **invoking unit's cgroup**. Under systemd the default `KillMode=control-group` reaps everything in a unit's cgroup the moment the unit's main process exits. Therefore:

- The canonical `tapps-mcp-fleet.service` is `Type=oneshot` **with `RemainAfterExit=yes`** — the unit stays "active (exited)", its cgroup is not torn down, and the servers survive.
- The watchdog (`tapps-mcp-fleet-watch.service` + `.timer`, polling every 60s) must **never call `fleet start` directly**. A `Type=oneshot` watchdog without `RemainAfterExit` would spawn the servers into its own cgroup and reap them on exit — a self-sustaining down→respawn→kill loop. Instead it runs `tapps-mcp fleet ensure`, which probes reachability and, only when unhealthy, runs `systemctl --user restart tapps-mcp-fleet.service` so the servers land in the canonical unit's surviving cgroup (falling back to a direct start only outside systemd).

`tapps-mcp fleet install-systemd` is the **single source of truth** for all three units; do not hand-author the watchdog. `tapps-mcp doctor` flags the crash-loop signature (PID files recorded but ports not listening) distinctly from "never started".

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
# optional (recommended) — install all units (service + health-aware watchdog):
#   tapps-mcp fleet install-systemd
#   systemctl --user daemon-reload
#   systemctl --user enable --now tapps-mcp-fleet.service
#   systemctl --user enable --now tapps-mcp-fleet-watch.timer

# 2. Per consumer repo
tapps-mcp init --host cursor --mcp-transport http --force --bundle full

# 3. Reload Cursor once — MCP connects to HTTP URLs (no stdio spawn)
```

Revert: set `mcp_transport: stdio` in yaml and re-run `tapps-mcp upgrade --host cursor`.
