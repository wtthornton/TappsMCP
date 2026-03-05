# Docker MCP Distribution

Docker MCP Catalog and profile artifacts for TappsMCP and DocsMCP.

## Structure

```
docker-mcp/
  tapps-mcp/
    server.yaml    # Registry metadata for Docker MCP Catalog
    tools.json     # Static tool definitions (auto-generated)
    readme.md      # Catalog listing documentation
  docs-mcp/
    server.yaml    # Registry metadata for Docker MCP Catalog
    tools.json     # Static tool definitions (auto-generated)
    readme.md      # Catalog listing documentation
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
# From repo root; you will be prompted for a catalog name (e.g. tappsmcp-local)
docker mcp catalog import docker-mcp/catalog.yaml
```

## Profiles

| Profile | Servers | Use Case |
|---------|---------|----------|
| `tapps-minimal` | tapps-mcp | Code quality only |
| `tapps-standard` | tapps-mcp, docs-mcp, context7 | Quality + docs + library lookup |
| `tapps-full` | tapps-mcp, docs-mcp, context7, github, filesystem | Full developer workflow |

## Regenerating tools.json

```bash
python scripts/generate-tools-json.py
```

## Submitting to Docker MCP Catalog

The `tapps-mcp/` and `docs-mcp/` directories are structured per
[docker/mcp-registry CONTRIBUTING.md](https://github.com/docker/mcp-registry/blob/main/CONTRIBUTING.md).
To submit:

1. Fork [docker/mcp-registry](https://github.com/docker/mcp-registry)
2. Copy `docker-mcp/tapps-mcp/` to `servers/tapps-mcp/`
3. Copy `docker-mcp/docs-mcp/` to `servers/docs-mcp/`
4. Submit PR

## Sharing Profiles via OCI Registry

```bash
docker mcp profile push ghcr.io/tapps-mcp/profiles/tapps-standard:v1
```
