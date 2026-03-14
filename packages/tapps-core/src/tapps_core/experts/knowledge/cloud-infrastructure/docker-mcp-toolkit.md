# Docker MCP Distribution

## Overview

TappsMCP and DocsMCP are distributed as Docker images for external users, CI/CD
pipelines, and sandboxed environments. The MCP servers use direct stdio transport
and are registered as `tapps-mcp` and `docs-mcp` in MCP client configurations.

## Architecture

```
AI Client (Claude Code, Cursor, VS Code Copilot)
    |
    v  stdio
MCP Server (tapps-mcp or docs-mcp)
    |
    v  file system access
User's Project Directory
```

## Client Configuration

### Direct stdio (Recommended)

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

## Docker Images

| Server | Image | Purpose |
|--------|-------|---------|
| tapps-mcp | `ghcr.io/wtthornton/tapps-mcp` | Code quality scoring, security scanning, quality gates |
| docs-mcp | `ghcr.io/wtthornton/docs-mcp` | Documentation generation and validation |
| combined | `ghcr.io/wtthornton/tapps-platform` | Both servers in one image |

## Content-Return Pattern

When running inside Docker with a read-only workspace mount, tools cannot write
files directly. Instead, tools return a `FileManifest` with file contents and
instructions for the AI client to apply using its native Write/Edit tools.

| Variable | Values | Effect |
|----------|--------|--------|
| `TAPPS_WRITE_MODE` | `direct` | Force direct file writes |
| `TAPPS_WRITE_MODE` | `content` | Force content-return mode |
| *(unset)* | | Auto-detect via filesystem probe |

## Docker MCP Registry

The Docker MCP Registry ([docker/mcp-registry](https://github.com/docker/mcp-registry))
is the catalog for Docker-distributed MCP servers. Each server needs a single
`server.yaml` file in the `servers/<name>/` directory.

### server.yaml Format

```yaml
name: tapps-mcp
image: ghcr.io/wtthornton/tapps-mcp
type: server
meta:
  category: developer-tools
  tags: [code-quality, python, security]
about:
  title: TappsMCP
  description: Deterministic code quality MCP server with 30 tools.
source:
  project: https://github.com/wtthornton/TappsMCP
  commit: <release-commit-sha>
```

## Dockerfile Best Practices

1. Default to stdio transport
2. Use multi-stage builds to keep images small
3. Run as non-root user
4. Declare env vars upfront (TAPPS_MCP_PROJECT_ROOT)
5. Use permissive licensing (MIT or Apache-2.0)
6. Tag images with semver
7. Support volume mounts for project access

## Security Model

- Filesystem isolation (only mounted volumes accessible)
- Network isolation (configurable per container)
- Resource limits (CPU, memory)
- Non-root user execution
