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
    tapps-minimal.yaml      # TappsMCP only
    tapps-standard.yaml     # TappsMCP + DocsMCP + Context7
    tapps-full.yaml         # + GitHub + Filesystem
    tapps-core-tools.yaml   # TappsMCP + DocsMCP, use with examples for Tier 1/2 only
    tapps-reviewer.yaml     # Role: code review & security (Epic 79.6)
    tapps-planning.yaml     # Role: epics, stories & planning (TappsMCP + DocsMCP)
    tapps-frontend.yaml     # Role: frontend / UX work
    tapps-developer.yaml    # Role: daily feature/bugfix development
  examples/
    tools-core-tier1.yaml       # Gateway tools.yaml: Tier 1 only (~11 tools)
    tools-core-tier1-tier2.yaml # Gateway tools.yaml: Tier 1+2 (~23 tools)
  catalog.yaml    # Self-hosted catalog (GHCR images; includes tapps-mcp-core preset)
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

### Cursor: use TappsMCP 1.3.1 via MCP_DOCKER

1. **Build and tag local images** (if not already done):
   ```bash
   docker build -t tapps-mcp:1.3.1 .
   docker build -f packages/docs-mcp/Dockerfile -t docs-mcp:1.3.1 .
   ```

2. **Update Cursor's MCP config** (`~/.cursor/mcp.json`) so MCP_DOCKER uses the 1.3.1 catalog. Change the MCP_DOCKER server args from:
   ```json
   "args": ["mcp", "gateway", "run"]
   ```
   to:
   ```json
   "args": ["mcp", "gateway", "run", "--catalog", "<path>/docker-mcp/catalog.yaml", "--additional-catalog", "docker-mcp", "--servers", "tapps-mcp,docs-mcp,context7"]
   ```
   Use the **absolute path** to `docker-mcp/catalog.yaml` (e.g. `C:\\cursor\\TappMCP\\docker-mcp\\catalog.yaml` on Windows).

3. **Restart Cursor** (or reload MCP servers) so the gateway restarts with the new args.

4. **Verify** by calling `tapps_session_start` — the response should show `version: "1.3.1"`.

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
| `tapps-standard-131` | tapps-mcp, docs-mcp, context7 @ 1.3.1 | Same as tapps-standard but pinned to 1.3.1 (use after `docker mcp catalog import docker-mcp/catalog.yaml`) |
| `tapps-minimal` | tapps-mcp | Code quality only |
| `tapps-standard` | tapps-mcp, docs-mcp, context7 | Quality + docs + library lookup |
| `tapps-full` | tapps-mcp, docs-mcp, context7, github, filesystem | Full developer workflow |
| `tapps-core-tools` | tapps-mcp, docs-mcp | Curated Tier 1 (and optionally Tier 2) tools only — see below |
| `tapps-reviewer` | tapps-mcp | Code review & security (~10 tools) |
| `tapps-planning` | tapps-mcp, docs-mcp | Epics, stories & planning |
| `tapps-frontend` | tapps-mcp | Frontend / UX (~7 tools) |
| `tapps-developer` | tapps-mcp | Daily feature/bugfix dev (~12 tools) |

### Core tools profile and tool count

Research recommends keeping the **active tool count under ~30** for best LLM accuracy. TappsMCP has 29 tools and DocsMCP 22; together that exceeds the optimal range. Use the **core-tools** profile and example tool allowlists to expose only Tier 1 (or Tier 1 + Tier 2) tools.

**Option A — Gateway tool filtering (profile + example tools.yaml):**

1. Import the core-tools profile and run the gateway with it:
   ```bash
   docker mcp profile import docker-mcp/profiles/tapps-core-tools.yaml
   docker mcp gateway run --profile tapps-core-tools
   ```
2. Apply an example allowlist so the gateway exposes only Tier 1 (or Tier 1+2) tools:
   - **Tier 1 only (~11 tools):** Copy `docker-mcp/examples/tools-core-tier1.yaml` to `~/.docker/mcp/tools.yaml` (or use the Tools tab in Docker Desktop for the profile).
   - **Tier 1 + Tier 2 (~23 tools):** Copy `docker-mcp/examples/tools-core-tier1-tier2.yaml` to `~/.docker/mcp/tools.yaml`.

   Alternatively use the CLI to enable only the tools you want:
   ```bash
   docker mcp profile tools tapps-core-tools --enable tapps-mcp.tapps_session_start --enable tapps-mcp.tapps_quick_check ...
   ```

**Option B — Server-side core preset (TappsMCP only):**

Use the **tapps-mcp-core** catalog entry so the server exposes only 7 Tier 1 tools (no gateway tools.yaml needed). After importing the catalog, add **tapps-mcp-core** (not tapps-mcp) to your profile; you get `session_start`, `quick_check`, `validate_changed`, `quality_gate`, `checklist`, `lookup_docs`, `security_scan` only.

Tier lists are defined in [TOOL-TIER-RANKING.md](../docs/planning/TOOL-TIER-RANKING.md).

## Docker path mapping (Story 75.1)

When running TappsMCP inside a container, `tapps_session_start` resolves paths
relative to the container mount (e.g. `/workspace`). To enable host-path
translation in automated pipelines, set the `TAPPS_HOST_ROOT` environment
variable to the **host-side** project root:

```bash
docker run --rm \
  -v "$(pwd):/workspace" \
  -e TAPPS_HOST_ROOT="$(pwd)" \
  -e TAPPS_DOCKER=1 \
  tapps-mcp tapps-mcp serve
```

When `TAPPS_HOST_ROOT` is set, the `tapps_session_start` response includes a
`path_mapping` object:

```json
{
  "container_root": "/workspace",
  "host_root": "C:\\cursor\\HomeIQ",
  "mapping_available": true
}
```

If the variable is absent, `mapping_available` is `false` and a warning is
surfaced so callers can adapt.

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

| Server | Image (pinned 1.3.1) | Dockerfile |
|--------|----------------------|------------|
| tapps-mcp | `ghcr.io/wtthornton/tapps-mcp:1.3.1` | `Dockerfile` |
| docs-mcp | `ghcr.io/wtthornton/docs-mcp:1.3.1` | `packages/docs-mcp/Dockerfile` |
| combined | `ghcr.io/wtthornton/tapps-platform` | `Dockerfile.platform` |

The catalog and server.yaml entries pin to **1.3.1**. Use `tapps-standard-131` profile after importing the catalog to run the gateway with 1.3.1 images.
