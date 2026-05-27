# Brain Deployment — Async-Native Write Path

This document explains how the async-native write path activates in the tapps-brain
container and how operators can verify it is running.

## The DSN gate

Brain's `http_adapter.py` attaches the async backend **implicitly** when either of
these env vars is present in the **brain container** environment:

| Env var | Purpose |
|---|---|
| `TAPPS_BRAIN_DATABASE_URL` | Primary PostgreSQL DSN — activates async writes |
| `TAPPS_BRAIN_HIVE_DSN` | Hive namespace DSN — also activates async backend |

There is **no client-side flag** in tapps-mcp. The gate is DSN presence at the
brain HTTP adapter level. Setting either variable in the brain container is all
that is needed; tapps-mcp picks up the result automatically via the `/healthz`
probe.

## Why this matters

Without `TAPPS_BRAIN_DATABASE_URL`, the brain falls back to synchronous writes on
the slower SQLite-backed path. An upgraded deployment can silently remain on the
slower path if the DSN is not set in the container env. tapps-mcp's
`tapps_session_start` surfaces this via `brain_bridge_health.async_native` so the
operator can see the write-path status without checking container env directly.

## Verifying async-native status

Call `tapps_session_start` and inspect `brain_bridge_health.async_native`:

```json
{
  "brain_bridge_health": {
    "enabled": true,
    "ok": true,
    "async_native": true,
    "details": {
      "db_ok": true,
      "brain_version": "3.19.0"
    }
  }
}
```

| `async_native` value | Meaning |
|---|---|
| `true` | Brain has DB connected; async writes active |
| `false` | Brain has `TAPPS_BRAIN_DATABASE_URL` configured but DB unreachable |
| field absent | Legacy brain (pre-v3.19.0) or in-process mode; cannot determine |

> **Note:** `async_native` is only present when tapps-mcp connects to the brain
> via HTTP (`TAPPS_MCP_MEMORY_BRAIN_HTTP_URL` is set). In-process BrainBridge
> mode does not use an HTTP adapter, so the field is omitted.

## Docker Compose setup

A minimal `docker-compose.yml` for running tapps-brain with async writes enabled:

```yaml
services:
  tapps-brain:
    image: ghcr.io/wtthornton/tapps-brain:latest
    container_name: tapps-brain
    ports:
      - "8080:8080"
    environment:
      # Activates the async write backend in brain's http_adapter.py.
      # Both vars do the same job — set either (or both for Hive).
      TAPPS_BRAIN_DATABASE_URL: postgresql+asyncpg://brain:brain@postgres:5432/brain
      # TAPPS_BRAIN_HIVE_DSN: postgresql+asyncpg://brain:brain@postgres:5432/hive
      TAPPS_MCP_AUTH_TOKEN: "${TAPPS_BRAIN_AUTH_TOKEN}"
    depends_on:
      - postgres
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: brain
      POSTGRES_PASSWORD: brain
      POSTGRES_DB: brain
    volumes:
      - brain-pg:/var/lib/postgresql/data

volumes:
  brain-pg:
```

Configure tapps-mcp to connect to the brain:

```yaml
# .tapps-mcp.yaml
memory:
  brain_http_url: "http://localhost:8080"
  # or via env: TAPPS_MCP_MEMORY_BRAIN_HTTP_URL=http://localhost:8080
```

## Env vars reference

| Env var | Set on | Purpose |
|---|---|---|
| `TAPPS_BRAIN_DATABASE_URL` | brain container | PostgreSQL DSN; activates async writes |
| `TAPPS_BRAIN_HIVE_DSN` | brain container | Hive namespace DSN; also activates async backend |
| `TAPPS_MCP_MEMORY_BRAIN_HTTP_URL` | tapps-mcp process | URL tapps-mcp uses to reach the brain HTTP service |
| `TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN` | tapps-mcp process | Bearer token for authenticated brain calls |
| `TAPPS_BRAIN_AUTH_TOKEN` | tapps-mcp process | Alias for `TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN` |

## Changelog

- v3.16.0 — brain async-native write path graduated to stable (no explicit flag;
  DSN-gated)
- TAP-1982 — tapps-mcp surfaces `async_native` in `brain_bridge_health` at
  session start
