# tapps-brain: Local and Multi-Project Setup

This guide explains how to connect tapps-mcp to tapps-brain for persistent memory.
Two transport modes are available — the choice depends on your topology.

---

## Transport modes

| Mode | Env vars required | When to use |
|------|-------------------|-------------|
| **In-process** (default for single-workstation use) | `TAPPS_BRAIN_DATABASE_URL` | Same-host setups where tapps-mcp and Postgres run together. See [ADR-0001](../adr/0001-in-process-agentbrain-via-brainbridge.md). |
| **HTTP** (recommended for multi-workstation / multi-tenant) | `TAPPS_MCP_MEMORY_BRAIN_HTTP_URL` + `TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN` | Shared brain server, server-side deployment, or any environment where per-project isolation is needed |

### When to pick which

**In-process is the tapps-mcp default per [ADR-0001](../adr/0001-in-process-agentbrain-via-brainbridge.md).** `BrainBridge` loads `AgentBrain` directly in the tapps-mcp process and routes reads/writes through it — no network round-trip, no HTTP lifespan race, no diagnostic ambiguity from a separate service being down.

**HTTP mode is the right choice when:**
- **Multi-tenant isolation** is required — the `X-Project-Id` header scopes reads/writes per request; in-process gives every process direct row access.
- **Secret surface** matters — one bearer token to rotate beats a Postgres password on every host.
- **Cross-host deployment** — when consumers other than tapps-mcp need the same memory store, the HTTP service is the canonical surface they reach.
- **Diagnostic clarity** — HTTP mode eliminates the "two-pipe ambiguity" where `tapps_session_start()` reports `memory_status.enabled: false` even though `mcp__tapps-brain__*` tools succeed over MCP (TAP-596).

---

## HTTP setup (recommended)

### 1. Start tapps-brain-http

Follow the tapps-brain-http README to start the server (typically on port 8080).

### 2. Create a project and obtain a bearer token

```bash
tapps-brain project register --name my-project --slug my-project
tapps-brain token create --project my-project
```

### 3. Set environment variables

```bash
# Point tapps-mcp at the running tapps-brain-http server
export TAPPS_MCP_MEMORY_BRAIN_HTTP_URL=http://localhost:8080

# Bearer token from step 2
export TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN=tb_your_token_here

# Optional: project slug for X-Project-Id header (recommended)
export TAPPS_MCP_MEMORY_BRAIN_PROJECT_ID=my-project
```

Or set them in `.tapps-mcp.yaml`:

```yaml
memory:
  brain_http_url: "http://localhost:8080"
  brain_auth_token: "${TAPPS_BRAIN_AUTH_TOKEN}"
  brain_project_id: "my-project"
```

### 4. Verify

```bash
uv run tapps-mcp doctor
```

`tapps_session_start()` should report `memory_status.enabled: true` and `brain_bridge_health.ok: true`.

---

## VSCode / GUI-launched IDE (the GUI-launch gotcha)

**Symptom:** `tapps_session_start()` reports `memory_status.enabled: false` even though the token is set in your shell and `tapps-brain-http` is running.

**Root cause:** VSCode launched from a desktop launcher (GNOME, macOS Dock, Windows Start Menu) inherits its environment from the **systemd user session** (Linux) or the **launchd/login session** (macOS/Windows) — not from `~/.bashrc` or `~/.profile`. Those files are only sourced by interactive or login shells. The `${TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN}` placeholder in `.mcp.json` expands to empty because the variable was never set in the GUI process tree.

Quick check — run this in the VSCode integrated terminal:

```bash
env | grep TAPPS_MCP_MEMORY
```

If the output is blank, the vars aren't in the GUI session environment.

### Fix (Linux — systemd user session)

Create (or update) `~/.config/environment.d/tapps-brain.conf`:

```ini
# ~/.config/environment.d/tapps-brain.conf
# Picked up by systemd --user at desktop login.
# Static KEY=VALUE only — no shell expansion, no $(…) substitution.
TAPPS_MCP_MEMORY_BRAIN_HTTP_URL=http://localhost:8080
TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN=tb_your_token_here
```

Then **log out of your desktop session and log back in**. A VSCode restart alone is not enough — `environment.d` is read by systemd at session start, not at process launch.

> **Static-only constraint:** `environment.d` does not support shell expansion or command substitution. If you currently generate the token dynamically (e.g. reading from a `.env` file at shell startup), you must write the literal token value here. The long-term solution — a single token source of truth — is tracked separately.

### Fix (macOS)

Use `launchctl setenv` to inject the vars into the user session:

```bash
launchctl setenv TAPPS_MCP_MEMORY_BRAIN_HTTP_URL http://localhost:8080
launchctl setenv TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN tb_your_token_here
```

Then restart VSCode (a full logout/login is not required on macOS; `launchctl setenv` takes effect for new processes immediately after VSCode restarts).

For persistence across reboots, add a `launchd` plist under `~/Library/LaunchAgents/`.

### Verification after fix

In a VSCode integrated terminal:

```bash
# Confirm the vars are present
env | grep TAPPS_MCP_MEMORY

# Confirm the MCP server sees them
uv run tapps-mcp doctor
```

`tapps_session_start()` should now return `memory_status.enabled: true` and `brain_bridge_health.ok: true`.

---

## In-process setup (default)

The in-process path is the tapps-mcp default per [ADR-0001](../adr/0001-in-process-agentbrain-via-brainbridge.md). `BrainBridge` loads `AgentBrain` directly and connects to Postgres via the DSN below; no separate HTTP service is required.

```bash
export TAPPS_BRAIN_DATABASE_URL=postgresql://user:pass@localhost:5432/tapps_brain
```

### Tradeoffs vs HTTP mode

- Each tapps-mcp process opens its own Postgres connection pool. Cross-process consistency comes from Postgres, not from a shared in-memory cache.
- No per-project row isolation at the connection layer — all tenants share the same Postgres role. (For multi-tenant deployments, prefer HTTP mode.)
- Multi-workstation setups require Postgres credential distribution; rotation touches every host. (HTTP mode rotates one bearer token instead.)

---

## Troubleshooting

### `memory_status.enabled: false` despite tapps-brain running

Check which transport mode is active:

```
tapps_session_start() → brain_bridge_health → details → mode
```

If `mode` is absent or the bridge is `None`, neither transport is configured.
Verify your env vars: `TAPPS_MCP_MEMORY_BRAIN_HTTP_URL` (HTTP path) or
`TAPPS_BRAIN_DATABASE_URL` (in-process path).

### `brain_bridge_health.ok: false` in HTTP mode

The `/health` endpoint on tapps-brain-http is unreachable. Check:

1. The server is running and the URL is correct.
2. No firewall blocks the port.
3. The bearer token is valid (401 responses appear in bridge logs).

### Token expands to empty (bearer header is blank)

**Symptom:** `brain_bridge_health` shows a 401 or the bridge is disabled; `memory_status.enabled: false`.

**Cause:** The `${TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN}` placeholder in `.mcp.json` expanded to an empty string. This is the [GUI-launch gotcha](#vscode--gui-launched-ide-the-gui-launch-gotcha).

**Fix:** Follow the `environment.d` / `launchctl` steps above, then do a full desktop relogin (Linux) or VSCode restart (macOS).

### Container is down

**Symptom:** `brain_bridge_health.ok: false`; `dsn_reachable: false`.

**Check:**

```bash
docker ps | grep tapps-brain
curl -s http://localhost:8080/health
```

If the container isn't running, start it per the tapps-brain-http README. If it's running but the health check fails, check container logs with `docker logs <container-id>`.

### Stale VSCode process (env change not picked up)

**Symptom:** You set the env var and restarted the MCP servers inside VSCode, but the token is still not reaching Claude Code.

**Cause:** The MCP server process is a child of the VSCode process. Restarting MCP servers inside VSCode does not re-read `environment.d` — the parent VSCode process still has the old (empty) environment.

**Fix:** Close VSCode completely and reopen it (Linux: requires full desktop relogin; macOS: reopen the app after `launchctl setenv`).

### Missing desktop relogin (Linux)

`environment.d` files are sourced once by `systemd --user` at login. Changes to `~/.config/environment.d/*.conf` do not take effect until the next login. A VSCode reload, terminal restart, or `systemctl --user restart` for individual services is **not sufficient**. You must log out of the desktop session and log back in.

To inject the vars into the *current* session without relogging (for testing only — not persistent):

```bash
systemctl --user set-environment TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN=tb_your_token_here
systemctl --user set-environment TAPPS_MCP_MEMORY_BRAIN_HTTP_URL=http://localhost:8080
```

Then restart VSCode so it inherits the updated systemd user environment.

### Version mismatch warning

tapps-mcp pins a minimum tapps-brain version in `packages/tapps-core/pyproject.toml`.
If the version probe fails, update tapps-brain-http to `>=3.7.2,<4`.
