# Docker MCP Distribution

Docker images for TappsMCP and DocsMCP, used for external distribution, CI/CD,
and sandboxed environments.

## Setup: Direct stdio with tapps-mcp and docs-mcp

TappsMCP and DocsMCP use direct stdio transport. Configure them as `tapps-mcp`
and `docs-mcp` server entries in your MCP client config.

### Claude Code (.mcp.json)

```json
{
  "mcpServers": {
    "tapps-mcp": {
      "type": "stdio",
      "command": "uv",
      "args": ["--directory", "C:\\cursor\\TappMCP", "run", "--no-sync", "tapps-mcp", "serve"],
      "env": { "TAPPS_MCP_PROJECT_ROOT": "." }
    },
    "docs-mcp": {
      "type": "stdio",
      "command": "uv",
      "args": ["--directory", "C:\\cursor\\TappMCP", "run", "--no-sync", "docsmcp", "serve"],
      "env": { "DOCS_MCP_PROJECT_ROOT": "." }
    }
  }
}
```

### Cursor (.cursor/mcp.json)

Same as above but use `${workspaceFolder}` instead of `"."` for env values.

## Building Docker Images

For external distribution or CI/CD:

```bash
# TappsMCP
docker build -t tapps-mcp:1.8.0 -t tapps-mcp:latest .

# DocsMCP
docker build -f packages/docs-mcp/Dockerfile -t docs-mcp:1.8.0 -t docs-mcp:latest .

# Verify
docker run --rm tapps-mcp:1.8.0 tapps-mcp --version
docker run --rm docs-mcp:1.8.0 docsmcp --version
```

## Structure

```
docker-mcp/
  tapps-mcp/
    server.yaml    # Registry entry for Docker MCP Catalog
  docs-mcp/
    server.yaml    # Registry entry for Docker MCP Catalog
  profiles/
    tapps-minimal.yaml      # TappsMCP only
    tapps-standard.yaml     # TappsMCP + DocsMCP + Context7
    tapps-full.yaml         # + GitHub + Filesystem
    tapps-core-tools.yaml   # TappsMCP + DocsMCP, use with examples for Tier 1/2 only
    tapps-reviewer.yaml     # Role: code review & security
    tapps-planning.yaml     # Role: epics, stories & planning (TappsMCP + DocsMCP)
    tapps-frontend.yaml     # Role: frontend / UX work
    tapps-developer.yaml    # Role: daily feature/bugfix development
    tapps-standard-170.yaml # Pinned to 1.7.0
    tapps-standard-180.yaml # Pinned to 1.8.0
  examples/
    tools-core-tier1.yaml       # Tier 1 only (~11 tools)
    tools-core-tier1-tier2.yaml # Tier 1+2 (~23 tools)
```

## Profiles

| Profile | Servers | Use Case |
|---------|---------|----------|
| `tapps-standard-170` | tapps-mcp, docs-mcp, context7 @ 1.7.0 | Pinned to 1.7.0 |
| `tapps-standard-180` | tapps-mcp, docs-mcp, context7 @ 1.8.0 | Pinned to 1.8.0 |
| `tapps-minimal` | tapps-mcp | Code quality only |
| `tapps-standard` | tapps-mcp, docs-mcp, context7 | Quality + docs + library lookup |
| `tapps-full` | tapps-mcp, docs-mcp, context7, github, filesystem | Full developer workflow |
| `tapps-core-tools` | tapps-mcp, docs-mcp | Curated Tier 1 (and optionally Tier 2) tools only |
| `tapps-reviewer` | tapps-mcp | Code review & security (~10 tools) |
| `tapps-planning` | tapps-mcp, docs-mcp | Epics, stories & planning |
| `tapps-frontend` | tapps-mcp | Frontend / UX (~7 tools) |
| `tapps-developer` | tapps-mcp | Daily feature/bugfix dev (~12 tools) |

## Content-return pattern (Epic 87)

When running inside Docker with a **read-only workspace mount**, TappsMCP tools
cannot write files directly to your project. Instead, tools return a **`FileManifest`**
with the file contents and instructions, so the AI client applies the writes
using its own native capabilities (Write/Edit tools).

### How it works

1. Tool detects read-only filesystem (or `TAPPS_WRITE_MODE=content` env var)
2. Instead of writing, the tool returns `content_return: true` with a `file_manifest`
3. The AI agent reads the manifest and writes each file using its native tools
4. The agent follows `agent_instructions` for verification and warnings

### Environment variables

| Variable | Values | Effect |
|----------|--------|--------|
| `TAPPS_WRITE_MODE` | `direct` | Force direct file writes (writable mount required) |
| `TAPPS_WRITE_MODE` | `content` | Force content-return mode |
| *(unset)* | | Auto-detect via filesystem probe |

### Tools that support content-return

- `tapps_init` / `tapps_upgrade` (pass `output_mode: "content_return"` to force)
- `tapps_set_engagement_level`
- `tapps_manage_experts` (add/scaffold)
- `tapps_memory` (export)
- `docs_config` (set action)
- All `docs_generate_*` generators

## Docker path mapping

When running TappsMCP inside a container, set `TAPPS_HOST_ROOT` for host-path
translation:

```bash
docker run --rm \
  -v "$(pwd):/workspace" \
  -e TAPPS_HOST_ROOT="$(pwd)" \
  -e TAPPS_DOCKER=1 \
  tapps-mcp tapps-mcp serve
```

## Images

| Server | Image (pinned 1.8.0) | Dockerfile |
|--------|----------------------|------------|
| tapps-mcp | `ghcr.io/wtthornton/tapps-mcp:1.8.0` | `Dockerfile` |
| docs-mcp | `ghcr.io/wtthornton/docs-mcp:1.8.0` | `packages/docs-mcp/Dockerfile` |
| combined | `ghcr.io/wtthornton/tapps-platform` | `Dockerfile.platform` |
