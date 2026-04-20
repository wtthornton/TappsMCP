# tapps-brain: Local and Multi-Project Setup

This guide explains how to connect tapps-mcp to tapps-brain for persistent memory.
Two transport modes are available; **HTTP is recommended** for all deployments.

---

## Transport modes

| Mode | Env vars required | When to use |
|------|-------------------|-------------|
| **HTTP** (recommended) | `TAPPS_MCP_MEMORY_BRAIN_HTTP_URL` + `TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN` | Any workstation or server running tapps-brain-http |
| In-process / legacy | `TAPPS_BRAIN_DATABASE_URL` | Local development only; single-tenant, direct Postgres access |

### Why HTTP is preferred

- **Multi-tenant isolation** — `X-Project-Id` per request scopes reads/writes to one project. Direct-DB gives every process access to all rows.
- **Secret surface** — one bearer token to rotate. Direct-DB exposes a Postgres password on every host.
- **Deployment topology** — tapps-brain-http is the intended bridge between external consumers and Postgres. Duplicating the Postgres connection on every host defeats the isolation model.
- **Diagnostic clarity** — HTTP mode eliminates the "two-pipe ambiguity" where `tapps_session_start()` reports `memory_status.enabled: false` even though `mcp__tapps-brain__*` tools succeed over MCP (TAP-596 / tapps-mcp-two-pipes-to-tapps-brain).

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

## In-process / legacy setup (local dev only)

The in-process path is kept as a fallback for local development where running a
separate HTTP service is inconvenient.

```bash
export TAPPS_BRAIN_DATABASE_URL=postgresql://user:pass@localhost:5432/tapps_brain
```

### Limitations

- Requires every tapps-mcp process to have a direct Postgres connection.
- No per-project row isolation — all tenants share the same Postgres role.
- Multi-workstation setups are error-prone (connection pool contention, credential rotation).

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

### Version mismatch warning

tapps-mcp pins a minimum tapps-brain version in `packages/tapps-core/pyproject.toml`.
If the version probe fails, update tapps-brain-http to `>=3.7.2,<4`.
