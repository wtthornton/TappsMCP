# Epic 24: MCP Streamable HTTP Transport

**Status:** Proposed
**Priority:** P1 - High (enables remote/container deployment patterns)
**Estimated LOE:** ~3-4 weeks (1 developer)
**Dependencies:** Epic 6 (Distribution)
**Blocks:** Epic 25 (IDE Marketplace - HTTP transport helpful)

---

## Goal

Harden and productionize the Streamable HTTP transport for TappsMCP, adding authentication, health checks, Docker Compose support, and configuration for remote/container deployment scenarios.

## Why This Epic Exists

TappsMCP already has a **basic** Streamable HTTP transport (`cli.py` serve command with `--transport http`, using `mcp.streamable_http_app()` via uvicorn). However, the current implementation is minimal:

1. **No authentication** - The HTTP endpoint is open to anyone who can reach it. For remote/container deployment, this is a security gap.

2. **No health/readiness endpoints** - Container orchestrators (Docker, Kubernetes) need health check endpoints to manage the service lifecycle.

3. **No Docker Compose example** - Epic 6 covers distribution but the Docker setup uses stdio transport. HTTP transport enables true client-server separation.

4. **No configuration** - Transport selection, TLS, CORS, and rate limiting are not configurable beyond CLI flags.

5. **SSE is deprecated** - The MCP protocol (`2025-11-25`) deprecates SSE in favor of Streamable HTTP. TappsMCP should fully embrace the standard transport.

The existing `run_server()` in `server.py` already calls `mcp.streamable_http_app()` for HTTP mode, so the FastMCP foundation is in place. This epic hardens it for production use.

## LLM Error Sources Addressed

| Error Source | How This Epic Helps |
|---|---|
| Can't share quality server across team | HTTP transport enables centralized deployment |
| Container restarts lose MCP connection | Health checks + reconnection enable reliable container lifecycle |
| Security risk from open HTTP endpoint | Authentication prevents unauthorized tool access |
| Complex MCP setup per developer | Shared server means configure once, connect many |

## Architecture Notes

### Current state

The HTTP transport path in `server.py:run_server()` already:
- Calls `mcp.streamable_http_app()` to get an ASGI app
- Wraps it in a Starlette app with a root health page
- Runs via uvicorn with configurable host/port
- Serves MCP at `/mcp` endpoint

### What needs hardening

```
server.py (run_server)
  └── mcp.streamable_http_app()     <- FastMCP provides this
       └── Starlette ASGI app
            ├── /           <- basic HTML page (exists)
            ├── /mcp        <- MCP endpoint (exists)
            ├── /health     <- NEW: health check
            ├── /ready      <- NEW: readiness check
            └── middleware
                 ├── AuthMiddleware    <- NEW: token/API key auth
                 ├── CORSMiddleware   <- NEW: configurable CORS
                 └── RateLimitMiddleware <- NEW: basic rate limiting
```

### Configuration additions to settings.py

```yaml
# .tapps-mcp.yaml additions
http:
  host: "0.0.0.0"
  port: 8000
  auth_token: ""           # or via TAPPS_MCP_AUTH_TOKEN env var
  cors_origins: ["*"]
  rate_limit_rpm: 60       # requests per minute, 0 = unlimited
  tls_cert: ""             # path to TLS cert (optional)
  tls_key: ""              # path to TLS key (optional)
```

## Stories

### Story 24.1: Health Check and Readiness Endpoints

Add `/health` and `/ready` endpoints to the HTTP transport. `/health` returns 200 if the process is alive. `/ready` returns 200 only when the scorer and settings are initialized and all configured tools are detected.

- `/health` - always returns `{"status": "ok", "version": "X.Y.Z"}`
- `/ready` - returns 200 when scorer initialized, 503 during startup
- Both endpoints bypass authentication
- Compatible with Docker HEALTHCHECK and Kubernetes probes

### Story 24.2: Authentication Middleware

Add token-based authentication for the HTTP transport. Support API key via `Authorization: Bearer <token>` header or `X-API-Key` header. Token configured via environment variable or `.tapps-mcp.yaml`.

- Starlette middleware that validates token on all `/mcp` requests
- Skip auth for `/health`, `/ready`, and `/` endpoints
- Token from `TAPPS_MCP_AUTH_TOKEN` env var or config file
- Clear error messages for missing/invalid tokens
- No auth required when token is not configured (local dev mode)

### Story 24.3: Docker Compose with HTTP Transport

Create a production-ready Docker Compose configuration that runs TappsMCP with HTTP transport, with proper health checks, volume mounts for project files, and environment variable configuration.

- `docker-compose.http.yml` with HTTP transport configuration
- Volume mount for project root (read-only)
- Environment variable passthrough for auth token
- HEALTHCHECK using `/health` endpoint
- Example `.env` file for configuration
- Documentation for multi-client connection

### Story 24.4: CORS and Rate Limiting

Add configurable CORS middleware and basic rate limiting to prevent abuse of the HTTP endpoint.

- CORS middleware with configurable allowed origins
- Rate limiting middleware (requests per minute per client IP)
- Configuration via `.tapps-mcp.yaml` and environment variables
- Sensible defaults: CORS allow all origins, rate limit 60 rpm

### Story 24.5: Transport Configuration and TLS

Consolidate transport configuration into settings, support TLS termination, and add CLI options for all transport parameters.

- HTTP transport settings in `TappsMCPSettings` (Pydantic model)
- TLS support via cert/key file paths
- `tapps-mcp serve --transport http --tls-cert ... --tls-key ...`
- Configuration validation at startup
- Update `tapps_doctor` to check HTTP transport configuration

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Security vulnerability from exposed HTTP endpoint | High | Auth middleware required for non-localhost; default to localhost-only |
| FastMCP HTTP transport API may change | Medium | Minimal wrapper around `streamable_http_app()` |
| TLS complexity for self-signed certs | Low | Document reverse proxy (nginx/caddy) as recommended approach |
| Rate limiting too aggressive for batch operations | Low | Configurable limits; `tapps_validate_changed` uses single connection |
