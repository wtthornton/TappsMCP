# Docker MCP Toolkit Submission Plan

Getting TappsMCP and DocsMCP listed in the [Docker MCP Toolkit](https://docs.docker.com/desktop/features/mcp-toolkit/) catalog so users can install with one click from Docker Desktop.

## Current State

| Asset | Status | Path |
|-------|--------|------|
| Dockerfile (tapps-mcp) | Ready | `Dockerfile` |
| Dockerfile (docs-mcp) | Ready | `packages/docs-mcp/Dockerfile` |
| Dockerfile (combined) | Ready | `Dockerfile.platform` |
| Registry artifacts | Needs update | `docker-mcp/` |
| CI publish workflow | Needs update | `.github/workflows/docker-publish.yml` |
| GHCR images published | Not yet | No release tags cut |

## Registry Format

The Docker MCP Registry ([docker/mcp-registry](https://github.com/docker/mcp-registry)) requires **one file per server**: `server.yaml`. That's it. No `tools.json`, no `readme.md` in the submission directory. Tools are discovered dynamically at runtime.

### Real examples from the registry

```yaml
# servers/playwright/server.yaml
name: playwright
image: mcp/playwright
type: server
longLived: true
meta:
  category: devops
  tags: [playwright, devops]
about:
  title: Playwright
  icon: https://avatars.githubusercontent.com/u/6154722?v=4
source:
  project: https://github.com/microsoft/playwright-mcp
  commit: a9d95f8d834733e2ef9f5ad3d3e7b042ff277b84
```

```yaml
# servers/github-official/server.yaml
name: github-official
image: ghcr.io/github/github-mcp-server
type: server
meta:
  category: devops
  tags: [github, devops]
about:
  title: "GitHub"
  description: "Official GitHub MCP Server..."
source:
  project: https://github.com/github/github-mcp-server
  commit: <pinned>
```

Key observations:
- `image` can be `mcp/<name>` (Docker Hub namespace, requires approval) or `ghcr.io/<org>/<name>`
- `source.commit` pins to a specific commit hash
- No `config.environment`, `config.secrets`, or `config.description` — those are optional
- `longLived: true` for servers that maintain persistent state (browsers, sessions)

## Gaps and Fixes

### 1. Image namespace

**Current:** `ghcr.io/tapps-mcp/tapps-mcp` (org doesn't exist)
**Fix:** Use `ghcr.io/wtthornton/tapps-mcp` and `ghcr.io/wtthornton/docs-mcp` matching the actual GitHub org. Update when/if a dedicated org is created.

### 2. server.yaml schema

**Current:** Custom fields (`config.environment[].mount`, `config.secrets`) not in real registry schema.
**Fix:** Rewrite to match actual registry format. Keep `config` section minimal or omit.

### 3. Extraneous files

**Current:** `tools.json` and `readme.md` per server.
**Fix:** Remove from registry submission. Keep locally for reference if desired.

### 4. Missing commit pin

**Current:** No `source.commit` or `source.branch`.
**Fix:** Pin to the release commit hash after cutting a tag.

### 5. Images not published

**Current:** CI workflow exists but no release tags have been cut.
**Fix:** Cut a release tag to trigger the publish pipeline.

## Execution Steps

### Phase 1 — Local Verification

```bash
# Build tapps-mcp image
docker build -t tapps-mcp:local .

# Build docs-mcp image
docker build -f packages/docs-mcp/Dockerfile -t docs-mcp:local .

# Smoke test tapps-mcp
docker run --rm tapps-mcp:local tapps-mcp --version
docker run --rm -v $(pwd):/workspace tapps-mcp:local tapps-mcp serve &
# verify it starts, then kill

# Smoke test docs-mcp
docker run --rm docs-mcp:local docsmcp --version
docker run --rm -v $(pwd):/workspace docs-mcp:local docsmcp serve &
```

### Phase 2 — Publish Images to GHCR

1. Ensure GitHub repo Settings > Packages > Package visibility = **Public**
2. Update `.github/workflows/docker-publish.yml` image refs:
   - `TAPPS_IMAGE: ghcr.io/wtthornton/tapps-mcp`
   - `DOCS_IMAGE: ghcr.io/wtthornton/docs-mcp`
3. Cut release tag: `git tag v0.9.0 && git push origin v0.9.0`
4. Verify images are pullable:
   ```bash
   docker pull ghcr.io/wtthornton/tapps-mcp:latest
   docker pull ghcr.io/wtthornton/docs-mcp:latest
   ```

### Phase 3 — Prepare Registry Submission

Update `docker-mcp/tapps-mcp/server.yaml`:
```yaml
name: tapps-mcp
image: ghcr.io/wtthornton/tapps-mcp
type: server
meta:
  category: devops
  tags:
    - code-quality
    - python
    - security
    - mcp
about:
  title: "TappsMCP"
  description: >
    Deterministic code quality MCP server. Scores Python files across 7
    categories, runs security scans, enforces quality gates, looks up library
    docs, and consults 17 domain experts. 30 tools, zero LLM calls.
  icon: https://raw.githubusercontent.com/wtthornton/TappsMCP/master/docs/icon.png
source:
  project: https://github.com/wtthornton/TappsMCP
  commit: <release-commit-sha>
config:
  description: "Mount your project directory to /workspace."
```

Update `docker-mcp/docs-mcp/server.yaml`:
```yaml
name: docs-mcp
image: ghcr.io/wtthornton/docs-mcp
type: server
meta:
  category: devops
  tags:
    - documentation
    - docs
    - python
    - mcp
about:
  title: "DocsMCP"
  description: >
    Documentation MCP server for automated generation, validation, and
    maintenance. Generates READMEs, API references, changelogs, ADRs,
    onboarding guides, and diagrams. 24 tools grounded in AST parsing
    and git history analysis.
  icon: https://raw.githubusercontent.com/wtthornton/TappsMCP/master/docs/icon.png
source:
  project: https://github.com/wtthornton/TappsMCP
  commit: <release-commit-sha>
config:
  description: "Mount your project directory to /workspace. Git required for history features."
```

### Phase 4 — Submit to Docker MCP Registry

```bash
# Fork and clone
gh repo fork docker/mcp-registry --clone
cd mcp-registry

# Create server entries
mkdir -p servers/tapps-mcp servers/docs-mcp
cp <path>/docker-mcp/tapps-mcp/server.yaml servers/tapps-mcp/
cp <path>/docker-mcp/docs-mcp/server.yaml servers/docs-mcp/

# Run validation
task build && task catalog

# Submit PR
gh pr create --title "Add tapps-mcp and docs-mcp servers" \
  --body "Adds TappsMCP (code quality, 30 tools) and DocsMCP (documentation, 24 tools)"
```

### Phase 5 — Post-Merge

- Update project README with `docker mcp catalog install tapps-mcp`
- Consider requesting `mcp/` Docker Hub namespace (gives Docker-signed provenance, SBOMs)
- Push companion profiles to OCI registry: `docker mcp profile push ghcr.io/wtthornton/profiles/tapps-standard:v1`

## Decision Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Submit as two servers | Yes | Separate install for quality vs docs, matches user needs |
| Image hosting | GHCR initially | Automatic with GitHub Actions, free for public repos |
| `mcp/` namespace | Pursue later | Requires Docker team approval, not blocking for initial listing |
| Combined platform image | Not submitted | Keep for power users, not needed in catalog |

## Tool count and core-tools profile (Epic 79.3)

To keep active tool count in the optimal range (~30 tools), the repo ships a **core-tools** profile and example `tools.yaml` for the Docker MCP Gateway:

- **Profile:** `docker-mcp/profiles/tapps-core-tools.yaml` (TappsMCP + DocsMCP).
- **Example allowlists:** `docker-mcp/examples/tools-core-tier1.yaml` (Tier 1 only, ~11 tools) and `docker-mcp/examples/tools-core-tier1-tier2.yaml` (Tier 1+2, ~23 tools). Copy to `~/.docker/mcp/tools.yaml` or use the profile Tools tab / `docker mcp profile tools` to enable only these tools.
- **Server-side preset:** Catalog entry `tapps-mcp-core` runs the same image with `TAPPS_MCP_TOOL_PRESET=core` so the server exposes only 7 Tier 1 tools without gateway filtering.

See `docker-mcp/README.md` § "Core tools profile and tool count" and [TOOL-TIER-RANKING.md](archive/planning/TOOL-TIER-RANKING.md).

## Timeline

| Phase | Estimated |
|-------|-----------|
| Phase 1: Local verification | Same day |
| Phase 2: Publish to GHCR | Same day (after tag) |
| Phase 3: Update artifacts | Same day |
| Phase 4: Submit PR | Same day |
| Phase 5: Docker review + merge | 1-7 days (external) |
| Available in catalog | ~24 hours post-merge |
