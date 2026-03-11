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

### Cursor: show tapps-mcp and docs-mcp with new versions (1.3.1)

1. **Import the catalog** (so the Toolkit uses the pinned 1.3.1 images):
   ```bash
   docker mcp catalog import docker-mcp/catalog.yaml
   ```
2. **Add servers to "My servers"** in MCP Toolkit: open **Catalog**, search for **tapps-mcp** and **docs-mcp**, and install/add each so they appear under My servers.
3. **Use the tapps-standard profile** (includes tapps-mcp + docs-mcp + Context7):
   ```bash
   docker mcp profile import tapps-standard
   docker mcp gateway run --profile tapps-standard
   ```
4. In **Cursor → Settings → Tools → Installed MCP Servers**, ensure **MCP_DOCKER** (or the Docker MCP gateway) is **enabled**. Enable **docs-mcp** there too if you want it as a separate server.
5. To use **1.3.1** you need the images: pull from GHCR after publish (`docker pull ghcr.io/wtthornton/tapps-mcp:1.3.1` and `docs-mcp:1.3.1`) or use your locally built images (tag as `tapps-mcp:1.3.1` and `docs-mcp:1.3.1` and run `docker mcp catalog import docker-mcp/catalog.yaml`).

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

| Server | Image (pinned 1.3.0) | Dockerfile |
|--------|----------------------|------------|
| tapps-mcp | `ghcr.io/wtthornton/tapps-mcp:1.3.0` | `Dockerfile` |
| docs-mcp | `ghcr.io/wtthornton/docs-mcp:1.3.0` | `packages/docs-mcp/Dockerfile` |
| combined | `ghcr.io/wtthornton/tapps-platform` | `Dockerfile.platform` |

The catalog and server.yaml entries pin to **1.3.0** so the MCP Toolkit and Cursor use the new versions.
