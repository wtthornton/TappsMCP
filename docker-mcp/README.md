# Docker MCP Distribution

Docker images and catalog artifacts for TappsMCP and DocsMCP.

## Recommended Setup: Direct stdio (no Docker MCP Gateway)

The **recommended** way to use TappsMCP is via direct stdio, using `uv run` from
the source directory. This avoids Docker MCP Gateway version-pinning issues,
catalog re-import steps, and container startup latency.

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

### Why not Docker MCP Gateway?

The Docker MCP Toolkit Gateway (`docker mcp gateway run`) adds friction:
- Image tags are pinned in the catalog -- every release requires `docker build` + `docker mcp catalog import`
- Stale versions persist silently if you forget to re-import
- Container startup adds latency to every tool call
- Extra indirection makes debugging harder

**Use Docker images for**: external distribution, CI/CD, sandboxed environments.
**Use direct stdio for**: local development, your own projects.

## Building Docker Images

For external distribution or CI/CD:

```bash
# TappsMCP
docker build -t tapps-mcp:1.7.0 -t tapps-mcp:latest .

# DocsMCP
docker build -f packages/docs-mcp/Dockerfile -t docs-mcp:1.7.0 -t docs-mcp:latest .

# Verify
docker run --rm tapps-mcp:1.7.0 tapps-mcp --version
docker run --rm docs-mcp:1.7.0 docsmcp --version
```

## Structure

```
docker-mcp/
  tapps-mcp/
    server.yaml    # Registry entry for Docker MCP Catalog (docker/mcp-registry format)
  docs-mcp/
    server.yaml    # Registry entry for Docker MCP Catalog (docker/mcp-registry format)
  profiles/
    tapps-minimal.yaml      # TappsMCP only
    tapps-standard.yaml     # TappsMCP + DocsMCP + Context7
    tapps-full.yaml         # + GitHub + Filesystem
    tapps-core-tools.yaml   # TappsMCP + DocsMCP, use with examples for Tier 1/2 only
    tapps-reviewer.yaml     # Role: code review & security (Epic 79.6)
    tapps-planning.yaml     # Role: epics, stories & planning (TappsMCP + DocsMCP)
    tapps-frontend.yaml     # Role: frontend / UX work
    tapps-developer.yaml    # Role: daily feature/bugfix development
    tapps-standard-170.yaml # Pinned to 1.7.0 (Toolkit profile)
  examples/
    tools-core-tier1.yaml       # Gateway tools.yaml: Tier 1 only (~11 tools)
    tools-core-tier1-tier2.yaml # Gateway tools.yaml: Tier 1+2 (~23 tools)
  catalog.yaml          # Gateway-format catalog (for docker mcp gateway run --catalog)
  toolkit-catalog.yaml  # Toolkit-native catalog (for docker mcp catalog import)
```

## Profiles

| Profile | Servers | Use Case |
|---------|---------|----------|
| `tapps-standard-170` | tapps-mcp, docs-mcp, context7 @ 1.7.0 | Same as tapps-standard but pinned to 1.7.0 |
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

## Docker MCP Toolkit (legacy/external distribution)

If you need to use the Docker MCP Toolkit for external distribution:

```bash
# 1. Build images
docker build -t tapps-mcp:1.7.0 -t tapps-mcp:latest .
docker build -f packages/docs-mcp/Dockerfile -t docs-mcp:1.7.0 -t docs-mcp:latest .

# 2. Import catalog
docker mcp catalog import docker-mcp/toolkit-catalog.yaml

# 3. Enable servers
docker mcp server enable tapps-mcp
docker mcp server enable docs-mcp

# 4. Connect clients
docker mcp client connect cursor
docker mcp client connect claude-code
```

**Important**: After every release, you must rebuild images AND re-import the
catalog. The toolkit pins exact image tags.

## Docker path mapping (Story 75.1)

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

| Server | Image (pinned 1.7.0) | Dockerfile |
|--------|----------------------|------------|
| tapps-mcp | `ghcr.io/wtthornton/tapps-mcp:1.7.0` | `Dockerfile` |
| docs-mcp | `ghcr.io/wtthornton/docs-mcp:1.7.0` | `packages/docs-mcp/Dockerfile` |
| combined | `ghcr.io/wtthornton/tapps-platform` | `Dockerfile.platform` |

## Submitting to Docker MCP Catalog

The `tapps-mcp/` and `docs-mcp/` directories each contain a single `server.yaml`
matching the [docker/mcp-registry](https://github.com/docker/mcp-registry) format.

```bash
gh repo fork docker/mcp-registry --clone
cd mcp-registry
cp -r <repo>/docker-mcp/tapps-mcp servers/tapps-mcp
cp -r <repo>/docker-mcp/docs-mcp servers/docs-mcp
task build && task catalog
gh pr create --title "Add tapps-mcp and docs-mcp servers"
```
