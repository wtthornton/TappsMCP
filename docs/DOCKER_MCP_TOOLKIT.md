# Docker Image Distribution

## Overview

TappsMCP and DocsMCP are distributed as Docker images for external distribution,
CI/CD, and sandboxed environments. The MCP servers are registered as `tapps-mcp`
and `docs-mcp` using direct stdio transport.

## Server Configuration

### Claude Code (.mcp.json)

```json
{
  "mcpServers": {
    "tapps-mcp": {
      "type": "stdio",
      "command": "tapps-mcp",
      "args": ["serve"],
      "env": { "TAPPS_MCP_PROJECT_ROOT": "." }
    },
    "docs-mcp": {
      "type": "stdio",
      "command": "docsmcp",
      "args": ["serve"],
      "env": { "DOCS_MCP_PROJECT_ROOT": "." }
    }
  }
}
```

### Cursor (.cursor/mcp.json)

Same structure but use `${workspaceFolder}` instead of `"."` for env values.

## Docker Images

| Server | Image | Dockerfile |
|--------|-------|------------|
| tapps-mcp | `ghcr.io/wtthornton/tapps-mcp` | `Dockerfile` |
| docs-mcp | `ghcr.io/wtthornton/docs-mcp` | `packages/docs-mcp/Dockerfile` |
| combined | `ghcr.io/wtthornton/tapps-platform` | `Dockerfile.platform` |

## Building Images

```bash
# TappsMCP
docker build -t tapps-mcp:1.7.0 -t tapps-mcp:latest .

# DocsMCP
docker build -f packages/docs-mcp/Dockerfile -t docs-mcp:1.7.0 -t docs-mcp:latest .

# Verify
docker run --rm tapps-mcp:1.7.0 tapps-mcp --version
docker run --rm docs-mcp:1.7.0 docsmcp --version
```

## Running in Docker

When running TappsMCP inside a container, set `TAPPS_HOST_ROOT` for host-path
translation:

```bash
docker run --rm \
  -v "$(pwd):/workspace" \
  -e TAPPS_HOST_ROOT="$(pwd)" \
  -e TAPPS_DOCKER=1 \
  tapps-mcp tapps-mcp serve
```

## Content-Return Pattern

When running inside Docker with a read-only workspace mount, tools return a
`FileManifest` with file contents instead of writing directly. The AI client
applies the writes using its native tools. Controlled via `TAPPS_WRITE_MODE`
env var (`direct` or `content`).

## Docker MCP Registry Submission

The `docker-mcp/tapps-mcp/` and `docker-mcp/docs-mcp/` directories contain
`server.yaml` files matching the [docker/mcp-registry](https://github.com/docker/mcp-registry) format.

```bash
gh repo fork docker/mcp-registry --clone
cd mcp-registry
cp -r <repo>/docker-mcp/tapps-mcp servers/tapps-mcp
cp -r <repo>/docker-mcp/docs-mcp servers/docs-mcp
task build && task catalog
gh pr create --title "Add tapps-mcp and docs-mcp servers"
```

## Dockerfile Best Practices

1. Default to stdio transport
2. Use multi-stage builds to keep images small
3. Run as non-root user
4. Declare env vars upfront
5. Use permissive licensing (MIT or Apache-2.0)
6. Tag images with semver
7. Support volume mounts for project access
