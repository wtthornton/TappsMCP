# Docker MCP Distribution

Docker MCP Catalog and profile artifacts for TappsMCP and DocsMCP.
See [docs/DOCKER_MCP_TOOLKIT.md](../docs/DOCKER_MCP_TOOLKIT.md) for the full submission plan.

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
    tapps-standard-150.yaml # Pinned to 1.5.0 (Toolkit profile)
  examples/
    tools-core-tier1.yaml       # Gateway tools.yaml: Tier 1 only (~11 tools)
    tools-core-tier1-tier2.yaml # Gateway tools.yaml: Tier 1+2 (~23 tools)
  catalog.yaml          # Gateway-format catalog (for docker mcp gateway run --catalog)
  toolkit-catalog.yaml  # Toolkit-native catalog (for docker mcp catalog import)
```

## Quick Start (Docker MCP Toolkit)

The Docker MCP Toolkit (v0.40+) is the recommended way to run TappsMCP via Docker.
It manages catalogs, server lifecycle, and client connections natively.

### 1. Build local images

```bash
docker build -t tapps-mcp:1.5.0 -t tapps-mcp:latest .
docker build -f packages/docs-mcp/Dockerfile -t docs-mcp:1.5.0 -t docs-mcp:latest .
```

### 2. Import the Toolkit catalog

```bash
docker mcp catalog import docker-mcp/toolkit-catalog.yaml
```

### 3. Enable servers

```bash
docker mcp server enable tapps-mcp
docker mcp server enable docs-mcp
```

### 4. Connect clients

```bash
docker mcp client connect cursor
docker mcp client connect claude-code
```

This adds an `MCP_DOCKER` gateway entry to each client's MCP config automatically.
The gateway exposes all enabled servers (tapps-mcp, docs-mcp, plus any others like
context7, fetch, playwright).

### 5. Verify

```bash
docker mcp tools ls          # should list 54+ tools (30 tapps + 24 docs)
docker mcp server ls          # should show tapps-mcp, docs-mcp enabled
docker mcp client ls          # should show cursor, claude-code connected
```

Call `tapps_session_start` from your client -- response should show `version: "1.5.0"`.

### Alternative: Gateway with custom catalog (legacy)

If you prefer manual gateway configuration instead of the Toolkit:

```bash
# In ~/.cursor/mcp.json or .mcp.json:
"MCP_DOCKER": {
  "command": "docker",
  "args": ["mcp", "gateway", "run", "--catalog", "<path>/docker-mcp/catalog.yaml",
           "--additional-catalog", "docker-mcp", "--servers", "tapps-mcp,docs-mcp,context7"]
}
```

### Build locally (without Toolkit)

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
| `tapps-standard-150` | tapps-mcp, docs-mcp, context7 @ 1.5.0 | Same as tapps-standard but pinned to 1.5.0 |
| `tapps-minimal` | tapps-mcp | Code quality only |
| `tapps-standard` | tapps-mcp, docs-mcp, context7 | Quality + docs + library lookup |
| `tapps-full` | tapps-mcp, docs-mcp, context7, github, filesystem | Full developer workflow |
| `tapps-core-tools` | tapps-mcp, docs-mcp | Curated Tier 1 (and optionally Tier 2) tools only — see below |
| `tapps-reviewer` | tapps-mcp | Code review & security (~10 tools) |
| `tapps-planning` | tapps-mcp, docs-mcp | Epics, stories & planning |
| `tapps-frontend` | tapps-mcp | Frontend / UX (~7 tools) |
| `tapps-developer` | tapps-mcp | Daily feature/bugfix dev (~12 tools) |

### Core tools profile and tool count

Research recommends keeping the **active tool count under ~30** for best LLM accuracy. TappsMCP has 30 tools and DocsMCP 24; together that exceeds the optimal range. Use the **core-tools** profile and example tool allowlists to expose only Tier 1 (or Tier 1 + Tier 2) tools.

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

Tier lists are defined in [TOOL-TIER-RANKING.md](../docs/archive/planning/TOOL-TIER-RANKING.md).

## Content-return pattern (Epic 87)

When running inside Docker with a **read-only workspace mount** (the default for
Docker MCP Toolkit), TappsMCP tools cannot write files directly to your project.
Instead, tools that would normally create or modify files return a **`FileManifest`**
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

### Forcing content-return for testing

```bash
# Via env var
docker run --rm -v "$(pwd):/workspace:ro" -e TAPPS_WRITE_MODE=content tapps-mcp serve

# Via tool parameter
tapps_init(output_mode="content_return")
tapps_upgrade(output_mode="content_return")
```

### Verifying write mode with doctor

```bash
tapps-mcp doctor  # includes "Write mode" check in Docker section
```

---

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

| Server | Image (pinned 1.5.0) | Dockerfile |
|--------|----------------------|------------|
| tapps-mcp | `ghcr.io/wtthornton/tapps-mcp:1.5.0` | `Dockerfile` |
| docs-mcp | `ghcr.io/wtthornton/docs-mcp:1.5.0` | `packages/docs-mcp/Dockerfile` |
| combined | `ghcr.io/wtthornton/tapps-platform` | `Dockerfile.platform` |

The catalog and server.yaml entries pin to **1.5.0**. Use `tapps-standard-150` profile or the Toolkit-native approach (`docker mcp catalog import` + `docker mcp server enable`).
