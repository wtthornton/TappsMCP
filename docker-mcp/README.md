# Docker MCP Distribution

Docker MCP Catalog and profile artifacts for TappsMCP and DocsMCP.
See [docs/DOCKER_MCP_TOOLKIT.md](../docs/DOCKER_MCP_TOOLKIT.md) for the full submission plan.

## Structure

```
docker-mcp/
  tapps-mcp/
    server.yaml    # Registry entry for Docker MCP Catalog
  docs-mcp/
    server.yaml    # Registry entry for Docker MCP Catalog
  profiles/
    tapps-minimal.yaml   # TappsMCP only
    tapps-standard.yaml  # TappsMCP + DocsMCP + Context7
    tapps-full.yaml      # + GitHub + Filesystem
  catalog.yaml    # Self-hosted catalog (GHCR images)
```

## Quick Start

### Install from Docker MCP Catalog

```bash
# Single server
docker mcp catalog install tapps-mcp

# Curated profile (recommended)
docker mcp profile import tapps-standard
docker mcp gateway run --profile tapps-standard
```

### Install from self-hosted catalog (pre-approval or enterprise)

```bash
# From repo root
docker mcp catalog import docker-mcp/catalog.yaml
```

### Build locally

```bash
# TappsMCP
docker build -t tapps-mcp .
docker run --rm -v $(pwd):/workspace tapps-mcp tapps-mcp --version

# DocsMCP
docker build -f packages/docs-mcp/Dockerfile -t docs-mcp .
docker run --rm -v $(pwd):/workspace docs-mcp docsmcp --version
```

## Profiles

| Profile | Servers | Use Case |
|---------|---------|----------|
| `tapps-minimal` | tapps-mcp | Code quality only |
| `tapps-standard` | tapps-mcp, docs-mcp, context7 | Quality + docs + library lookup |
| `tapps-full` | tapps-mcp, docs-mcp, context7, github, filesystem | Full developer workflow |

## Submitting to Docker MCP Catalog

The `tapps-mcp/` and `docs-mcp/` directories each contain a single `server.yaml`
matching the [docker/mcp-registry](https://github.com/docker/mcp-registry) format.

```bash
# Fork and clone
gh repo fork docker/mcp-registry --clone
cd mcp-registry

# Copy server entries
cp -r <repo>/docker-mcp/tapps-mcp servers/tapps-mcp
cp -r <repo>/docker-mcp/docs-mcp servers/docs-mcp

# Validate and submit
task build && task catalog
gh pr create --title "Add tapps-mcp and docs-mcp servers"
```

## Images

| Server | Image | Dockerfile |
|--------|-------|------------|
| tapps-mcp | `ghcr.io/wtthornton/tapps-mcp` | `Dockerfile` |
| docs-mcp | `ghcr.io/wtthornton/docs-mcp` | `packages/docs-mcp/Dockerfile` |
| combined | `ghcr.io/wtthornton/tapps-platform` | `Dockerfile.platform` |
