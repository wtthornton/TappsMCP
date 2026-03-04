# Docker MCP Toolkit Distribution

## Overview

The Docker MCP Toolkit (GA 2026) provides a managed distribution channel for MCP
servers via Docker Desktop. It combines a curated **MCP Catalog** (300+ verified
server images on Docker Hub), an **MCP Gateway** (stdio proxy managing container
lifecycle), and **profiles** (named server collections) into a zero-dependency
install experience for AI coding assistants.

For MCP server authors, the toolkit offers cross-platform distribution, automatic
security updates, image signing with SBOM provenance, and discoverability alongside
hundreds of other servers -- all without requiring users to install Python, Node.js,
or any other runtime.

## Architecture

```
AI Client (Claude Code, Cursor, VS Code Copilot)
    |
    v  stdio
Docker MCP Gateway (CLI plugin + proxy)
    |
    v  manages container lifecycle
MCP Server Containers (isolated Docker images)
    |
    v  volume mount
User's Project Directory (/workspace)
```

### Core Components

| Component | Purpose | Location |
|-----------|---------|----------|
| **MCP Catalog** | 300+ verified server images, browsable in Docker Desktop | hub.docker.com/mcp |
| **MCP Gateway** | Proxy routing client requests to containerized servers | `docker mcp gateway run` |
| **Profiles** | Named collections of servers with per-profile configuration | `~/.docker/mcp/` |
| **Dynamic MCP** | Mid-conversation server discovery and addition by agents | Built into gateway |
| **MCP Registry** | GitHub repo for catalog submissions | github.com/docker/mcp-registry |

### Configuration Files

The gateway stores configuration in `~/.docker/mcp/`:

```
~/.docker/mcp/
  docker-mcp.yaml    # Catalog of available servers
  registry.yaml      # Registry of enabled servers
  config.yaml        # Per-server runtime configuration
  tools.yaml         # Enabled tools per server
```

## Client Configuration

### Single Gateway Entry (Recommended)

Instead of configuring each MCP server individually, a single gateway entry
routes all requests through Docker:

```json
{
  "mcpServers": {
    "MCP_DOCKER": {
      "command": "docker",
      "args": ["mcp", "gateway", "run", "--profile", "my_profile"],
      "type": "stdio"
    }
  }
}
```

### VS Code / Cursor

```bash
# Connect VS Code to a profile
docker mcp client connect vscode --profile my_profile

# Connect Cursor to a profile
docker mcp client connect cursor --profile my_profile
```

### Claude Code

Add to `.claude/settings.json`:

```json
{
  "mcpServers": {
    "tapps-platform": {
      "command": "docker",
      "args": ["mcp", "gateway", "run", "--profile", "tapps-platform"]
    }
  }
}
```

## Supported Transports

| Transport | Use Case | Command |
|-----------|----------|---------|
| **stdio** | Default for gateway (single client) | `docker mcp gateway run` |
| **Streaming HTTP** | Multi-client, port-based | `docker mcp gateway run --port 8080 --transport streaming` |
| **SSE** | Legacy multi-client | `docker mcp gateway run --transport sse` |

For Docker MCP Toolkit, **stdio is the default and recommended transport**. The
gateway handles the translation between stdio (client side) and the container's
internal transport.

## Publishing to the Docker MCP Catalog

### Submission Process

1. Fork and clone [docker/mcp-registry](https://github.com/docker/mcp-registry)
2. Create a server directory: `servers/<server-name>/`
3. Add required files: `server.yaml`, `tools.json`, `readme.md`
4. Build and test locally with `task build -- --tools <server-name>`
5. Import to Docker Desktop: `docker mcp catalog import $PWD/catalogs/<name>/catalog.yaml`
6. Submit PR -- approved entries available within 24 hours

### Two Submission Paths

**Docker-Built (Recommended):**
- Docker builds, signs, and publishes your image to `mcp/<name>` on Docker Hub
- Includes cryptographic signatures, provenance tracking, SBOMs, automatic security updates
- Submit a `server.yaml` with `image: mcp/<name>` -- Docker handles the rest

**Self-Built:**
- You host your own image (GHCR, ACR, private registry)
- Still gets catalog entry but without Docker's enhanced security chain
- Specify your image: `image: ghcr.io/your-org/your-server:latest`

### Licensing Requirement

Submissions must use **permissive licenses** (MIT, Apache-2.0). GPL is not permitted.

### server.yaml Format

```yaml
name: tapps-mcp
image: mcp/tapps-mcp
type: server
meta:
  category: developer-tools
  tags:
    - code-quality
    - python
    - linting
    - security
about:
  title: TappsMCP - Code Quality Tools
  description: >
    Deterministic code quality MCP server with 28 tools.
  icon: https://example.com/icon.png
source:
  project: https://github.com/tapps-mcp/tapps-mcp
  commit: abc123
config:
  description: Mount your project directory to /workspace.
  secrets:
    - name: server.context7_api_key
      env: CONTEXT7_API_KEY
      example: <your-key>
      required: false
```

### tools.json Format

Static tool definitions for build-time validation. Generated by running the
server and capturing the `tools/list` MCP response:

```json
[
  {
    "name": "tapps_score_file",
    "description": "Score a Python file across 7 quality categories.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "file_path": {"type": "string"},
        "quick": {"type": "boolean", "default": false}
      },
      "required": ["file_path"]
    }
  }
]
```

If your server requires configuration before listing tools, provide the
`tools.json` file manually -- the build process will skip runtime tool discovery.

## Custom Catalogs (Enterprise / Self-Hosted)

Organizations can create private catalogs pointing to their own registries:

```yaml
# catalog.yaml
servers:
  tapps-mcp:
    name: tapps-mcp
    description: "Code quality MCP server (28 tools)"
    image: ghcr.io/your-org/tapps-mcp:latest
    transport: stdio
    environment:
      - name: TAPPS_MCP_PROJECT_ROOT
        value: /workspace
        mount: true
  docs-mcp:
    name: docs-mcp
    description: "Documentation MCP server (18 tools)"
    image: ghcr.io/your-org/docs-mcp:latest
    transport: stdio
```

Import with: `docker mcp catalog import ./catalog.yaml`

Benefits:
- Curate which servers are available to your org
- Host approved images in private registries
- Manage versions and updates centrally
- No dependency on Docker Hub availability

## Dockerfile Patterns for MCP Servers

### stdio-First Design

MCP Gateway expects servers to communicate via stdio by default:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .
# Default: stdio (for Docker MCP Gateway)
ENTRYPOINT ["my-server", "serve"]
# Override for direct HTTP: docker run ... my-server serve --transport http
```

### Volume Mount for Project Access

The gateway mounts the user's project directory into the container:

```dockerfile
ENV TAPPS_MCP_PROJECT_ROOT=/workspace
# Gateway mounts: -v /user/project:/workspace
```

### Health Checks

Include health checks for Docker Desktop monitoring:

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "print('ok')" || exit 1
```

### Multi-Stage Builds

Keep images small by separating build and runtime:

```dockerfile
# Build stage
FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml .
RUN pip wheel --no-deps --wheel-dir /wheels .

# Runtime stage
FROM python:3.12-slim
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
USER nonroot
ENTRYPOINT ["my-server", "serve"]
```

## Security Model

### Docker-Built Images

Images in the `mcp/` namespace on Docker Hub receive:

- **Digital signatures** verifying source and integrity
- **SBOM (Software Bill of Materials)** for full dependency transparency
- **Provenance tracking** linking image to source commit
- **Automatic security updates** when base images are patched

### Container Isolation

Each MCP server runs in its own container:

- Filesystem isolation (only mounted volumes are accessible)
- Network isolation (configurable per server)
- Resource limits (CPU, memory)
- Non-root user execution

### Secret Management

Docker Desktop manages secrets securely:

```yaml
# server.yaml
config:
  secrets:
    - name: server.api_key
      env: API_KEY
      required: true
```

Users configure secrets in Docker Desktop UI -- they are injected as environment
variables at runtime, never stored in catalog metadata.

## Best Practices

1. **Default to stdio transport** -- the MCP Gateway expects it
2. **Use multi-stage builds** -- keep images under 200 MB
3. **Run as non-root** -- required for security compliance
4. **Declare all env vars upfront** -- Docker Desktop UI auto-generates configuration forms
5. **Provide tools.json** -- speeds up catalog builds and avoids runtime discovery issues
6. **Use permissive licensing** -- MIT or Apache-2.0 for catalog acceptance
7. **Tag images with semver** -- `latest`, `0.8.1`, `0.8` for version pinning
8. **Sign images** -- use `cosign` with GitHub Actions OIDC for keyless signing
9. **Test with gateway locally** -- `docker mcp catalog import` before submitting
10. **Support volume mounts** -- users need to score/analyze their project files

## Anti-Patterns

- **HTTP-only servers** -- Gateway uses stdio; HTTP is for direct (non-gateway) use only
- **Hardcoded project paths** -- Use `TAPPS_MCP_PROJECT_ROOT` env var, not fixed paths
- **Root user in containers** -- Fails security review and catalog compliance
- **Missing tools.json** -- Build-time tool listing may fail if server needs runtime config
- **GPL licensing** -- Docker MCP Catalog explicitly rejects GPL
- **Large images** -- Images over 500 MB are slow to pull and waste disk; use slim bases
- **Ignoring .dockerignore** -- Build context includes tests, docs, .git without it

## Quick Reference

| Aspect | Recommendation |
|--------|---------------|
| Transport | stdio (for gateway), streamable-http (direct) |
| Base image | `python:3.12-slim` |
| Build pattern | Multi-stage (builder + runtime) |
| User | Non-root (`useradd` + `USER`) |
| Project mount | `/workspace` via `TAPPS_MCP_PROJECT_ROOT` |
| License | MIT or Apache-2.0 |
| Registry submission | PR to docker/mcp-registry |
| Image signing | cosign with OIDC (keyless) |
| Custom catalog | YAML index pointing to GHCR/private registry |
| Secret management | Docker Desktop UI, injected as env vars |
