# Epic 46: Docker MCP Toolkit Distribution

- **Status:** Complete
- **Priority:** P1
- **Estimated LOE:** ~3-4 weeks (1 developer)
- **Dependencies:** Epic 6 (Distribution), Epic 37 (Pipeline Onboarding), DocsMCP Epic 10 (Distribution)
- **Blocks:** None

## Goal

Package TappsMCP and DocsMCP as Docker MCP Toolkit-compatible container images, publish them to the Docker MCP Catalog (and GHCR), ship curated companion profiles (Context7, GitHub, Filesystem), and integrate Docker-aware lifecycle management into `tapps_init`, `tapps_upgrade`, and `tapps_doctor` -- giving users zero-dependency, cross-platform, one-click installation with a complete developer toolchain via Docker Desktop.

## Motivation

TappsMCP and DocsMCP currently distribute via three channels:

| Channel | Pros | Cons |
|---------|------|------|
| **PyPI** (`pip install`) | Standard Python | Requires Python 3.12+, venv management |
| **PyInstaller exe** | No Python needed | Windows-only, ~80 MB, no auto-update, manual rebuild |
| **Docker image** (existing) | Cross-platform, isolated | Not discoverable, manual `docker run` |

The **Docker MCP Toolkit** (released 2025, GA 2026) solves the discovery and configuration problems:

- **300+ servers** in the Docker MCP Catalog -- users browse and install in Docker Desktop
- **MCP Gateway** proxies all servers behind a single stdio connection -- one config entry per profile
- **Profiles** group servers into project-specific bundles (e.g., "tapps-mcp + docs-mcp + context7")
- **Dynamic MCP** lets agents discover and add servers mid-conversation
- **Signed images** with SBOM, provenance tracking, and automatic security updates (Docker-built path)
- **Custom catalogs** let organizations curate approved servers via YAML index
- **Profile sharing** via OCI registries for team-wide distribution

Publishing to the Docker MCP Catalog gives TappsMCP/DocsMCP:
1. **Cross-platform zero-dependency install** (Windows, macOS, Linux -- no Python needed)
2. **Discoverability** alongside 300+ other MCP servers
3. **Auto-updates** via image tag management
4. **Enterprise trust** via Docker's signing and SBOM chain
5. **Simplified client config** -- one gateway entry replaces per-server setup
6. **Companion ecosystem** -- bundle with Context7, GitHub, Filesystem MCPs in curated profiles

### Companion MCP Servers

TappsMCP is most effective when paired with complementary MCP servers:

| Server | Docker Catalog | Why It Complements TappsMCP |
|--------|---------------|----------------------------|
| **Context7** | `mcp/context7` | Library docs lookup -- TappsMCP uses Context7 API internally, but users also benefit from the standalone MCP for ad-hoc doc queries outside of `tapps_lookup_docs` |
| **GitHub** | `mcp/github` | PR/issue management -- TappsMCP generates GitHub templates, CI configs, and governance files; GitHub MCP lets agents create PRs, manage issues, run checks |
| **Filesystem** | `mcp/filesystem` | Secure file access -- provides sandboxed file operations that complement TappsMCP's path-validated file scoring |
| **Sequential Thinking** | `mcp/sequentialthinking` | Structured reasoning -- breaks complex architectural decisions into steps before calling `tapps_consult_expert` |

**Context7 dual role**: TappsMCP uses Context7 as a **library API** (via `CONTEXT7_API_KEY`) inside `tapps_lookup_docs` and `tapps_research`. The **Context7 MCP server** is a separate companion that gives the AI client direct access for ad-hoc doc queries. Both are valuable and complementary.

## Acceptance Criteria

- [ ] TappsMCP Dockerfile produces a working image that passes `docker mcp` tool listing
- [ ] DocsMCP Dockerfile produces a working image that passes `docker mcp` tool listing
- [ ] `server.yaml` registry metadata created for both servers per docker/mcp-registry spec
- [ ] `tools.json` generated for both servers (static tool listing for build validation)
- [ ] Both images pass local `docker mcp catalog import` and tool invocation via gateway
- [ ] PR submitted to [docker/mcp-registry](https://github.com/docker/mcp-registry) for catalog inclusion
- [ ] Curated companion profiles (minimal, standard, full) created and tested
- [ ] `tapps_init` detects Docker MCP Toolkit and generates gateway-based MCP config
- [ ] `tapps_init` recommends missing companion servers when Docker is detected
- [ ] `tapps_upgrade` preserves Docker gateway entries and companion profile references
- [ ] `tapps_doctor` validates Docker daemon, images, gateway connectivity, and companion health
- [ ] `setup_generator.py` generates Docker MCP entries in `.mcp.json`, `.claude.json`, `.cursor/mcp.json`
- [ ] Elicitation wizard includes Docker transport and companion profile questions
- [ ] Settings model includes `DockerSettings` configuration
- [ ] GitHub Actions workflow builds and pushes images to GHCR on release
- [ ] Expert knowledge updated with Docker MCP Toolkit and companion patterns
- [ ] All new code has tests; existing tests still pass

---

## Stories

### 46.1 -- Dockerfile Hardening for MCP Catalog Compliance

**Points:** 5

The existing Dockerfiles (`Dockerfile` for TappsMCP, `packages/docs-mcp/Dockerfile` for DocsMCP) work but need adjustments for Docker MCP Catalog requirements:

1. **stdio as default transport** -- The MCP Gateway communicates via stdio, not HTTP. The TappsMCP Dockerfile currently defaults to `--transport http`. Must switch to stdio default with HTTP as override.
2. **Consistent base images** -- TappsMCP uses `python:3.14-slim`, DocsMCP uses `python:3.12-slim`. Align on `python:3.12-slim` (our minimum supported version) for stability.
3. **Monorepo-aware builds** -- Both servers depend on `tapps-core`. Dockerfiles must build `tapps-core` wheel first, then the server wheel.
4. **Volume mounts** -- Docker MCP Gateway mounts the user's project directory. Ensure `TAPPS_MCP_PROJECT_ROOT` is configurable via env var and defaults to `/workspace`.
5. **OCI labels** -- Verify all required OCI labels are present (`org.opencontainers.image.*`).

**Tasks:**
- Update TappsMCP `Dockerfile` to default to stdio transport (`CMD ["tapps-mcp", "serve"]`)
- Align both Dockerfiles on `python:3.12-slim` base
- Add monorepo build context: copy `packages/tapps-core/` and build its wheel in the builder stage
- Verify `TAPPS_MCP_PROJECT_ROOT=/workspace` env var is set and respected
- Add `.dockerignore` at repo root (exclude `.venv*`, `.git`, `dist/`, `*.egg-info`, `__pycache__`)
- Test both images locally: `docker build`, `docker run`, verify tool listing works via stdio
- Test with volume mount: `docker run -v $(pwd):/workspace tapps-mcp serve` should score files in `/workspace`

**Definition of Done:** Both Dockerfiles build clean images that respond correctly to MCP `tools/list` requests over stdio, and can score/analyze files mounted at `/workspace`.

---

### 46.2 -- Docker MCP Registry Metadata

**Points:** 5

Create the registry submission files per [docker/mcp-registry CONTRIBUTING.md](https://github.com/docker/mcp-registry/blob/main/CONTRIBUTING.md) guidelines.

Each server needs a directory under `servers/` with:
- `server.yaml` -- Server metadata, image reference, configuration, secrets
- `tools.json` -- Static tool definitions for build-time validation
- `readme.md` -- Documentation link

**Tasks:**
- Create `docker-mcp/tapps-mcp/server.yaml`:
  ```yaml
  name: tapps-mcp
  image: mcp/tapps-mcp
  type: server
  meta:
    category: developer-tools
    tags:
      - code-quality
      - python
      - linting
      - security
      - mcp
  about:
    title: TappsMCP - Code Quality Tools
    description: >
      Deterministic code quality MCP server. Scores Python files across 7
      categories, runs security scans, enforces quality gates, looks up
      library docs, validates configs, and consults 17 domain experts.
      28 tools, zero LLM calls in the tool chain.
    icon: https://raw.githubusercontent.com/tapps-mcp/tapps-mcp/master/docs/icon.png
  source:
    project: https://github.com/tapps-mcp/tapps-mcp
    commit: <HEAD>
  config:
    description: >
      Mount your project directory to /workspace. Optionally set
      CONTEXT7_API_KEY for documentation lookup.
    secrets:
      - name: server.context7_api_key
        env: CONTEXT7_API_KEY
        example: <your-context7-key>
        required: false
  ```
- Create `docker-mcp/tapps-mcp/tools.json` by running `tapps-mcp serve` in a subprocess, capturing the `tools/list` response, and saving the tool definitions
- Create `docker-mcp/docs-mcp/server.yaml` with similar structure (category: documentation, 18 tools)
- Create `docker-mcp/docs-mcp/tools.json` from DocsMCP tool listing
- Create `docker-mcp/tapps-mcp/readme.md` and `docker-mcp/docs-mcp/readme.md` pointing to repo docs
- Add a `scripts/generate-tools-json.py` utility to auto-generate `tools.json` from a running server

**Definition of Done:** Both `server.yaml` files validate per registry schema. `tools.json` accurately lists all tools. Files are ready for PR submission.

---

### 46.3 -- Curated Companion Profiles

**Points:** 5

Create tiered Docker MCP profiles that bundle TappsMCP/DocsMCP with complementary servers. Profiles are shareable via OCI registries and importable via `docker mcp catalog import`.

**Profiles:**

| Profile | Servers | Use Case |
|---------|---------|----------|
| `tapps-minimal` | tapps-mcp | Code quality only |
| `tapps-standard` | tapps-mcp, docs-mcp, context7 | Quality + docs + library lookup |
| `tapps-full` | tapps-mcp, docs-mcp, context7, github, filesystem | Full developer workflow |

**Tasks:**
- Create `docker-mcp/profiles/tapps-minimal.yaml`:
  ```yaml
  name: tapps-minimal
  description: "TappsMCP code quality tools"
  servers:
    - catalog://tapps-mcp
  ```
- Create `docker-mcp/profiles/tapps-standard.yaml`:
  ```yaml
  name: tapps-standard
  description: "TappsMCP + DocsMCP + Context7 library docs"
  servers:
    - catalog://tapps-mcp
    - catalog://docs-mcp
    - catalog://context7
  ```
- Create `docker-mcp/profiles/tapps-full.yaml`:
  ```yaml
  name: tapps-full
  description: "Full developer workflow: quality, docs, library lookup, GitHub, filesystem"
  servers:
    - catalog://tapps-mcp
    - catalog://docs-mcp
    - catalog://context7
    - catalog://github
    - catalog://filesystem
  ```
- Create `docker-mcp/catalog.yaml` self-hosted catalog pointing to GHCR images (for pre-catalog-approval or enterprise use):
  ```yaml
  servers:
    tapps-mcp:
      name: tapps-mcp
      description: "Code quality MCP server (28 tools)"
      image: ghcr.io/tapps-mcp/tapps-mcp:latest
      transport: stdio
      environment:
        - name: TAPPS_MCP_PROJECT_ROOT
          value: /workspace
          mount: true
    docs-mcp:
      name: docs-mcp
      description: "Documentation MCP server (18 tools)"
      image: ghcr.io/tapps-mcp/docs-mcp:latest
      transport: stdio
      environment:
        - name: TAPPS_MCP_PROJECT_ROOT
          value: /workspace
          mount: true
  ```
- Test full flow per profile: catalog import, profile creation, gateway run, tool invocation from each server
- Document companion server value in `docker-mcp/README.md`
- Push profiles to GHCR: `docker mcp profile push ghcr.io/tapps-mcp/profiles/tapps-standard:v1`

**Definition of Done:** All three profiles import cleanly, gateway routes to all servers, and tool calls succeed end-to-end. Profiles are pushable to OCI registries.

---

### 46.4 -- GitHub Actions: Build and Push Docker Images

**Points:** 5

Automate image builds on every release tag. Push to GHCR (immediately) and optionally Docker Hub `mcp/` namespace (after catalog approval).

**Tasks:**
- Create `.github/workflows/docker-publish.yml`:
  - Trigger on `v*` tags (e.g., `v0.8.1`)
  - Build TappsMCP image from root `Dockerfile`
  - Build DocsMCP image from `packages/docs-mcp/Dockerfile`
  - Tag images with: `latest`, semver (`0.8.1`), major-minor (`0.8`)
  - Push to `ghcr.io/tapps-mcp/tapps-mcp` and `ghcr.io/tapps-mcp/docs-mcp`
  - Generate SBOM with `docker sbom` or `syft`
  - Sign images with `cosign` (keyless, OIDC via GitHub Actions)
- Add build matrix for `linux/amd64` and `linux/arm64` (multi-arch)
- Cache Docker layers via `actions/cache` or buildx cache
- Add smoke test step: build image, run `docker run --rm <image> --version`, verify exit code 0
- Add integration test step: run tool listing via stdio and verify expected tool count (28 for tapps-mcp, 18 for docs-mcp)

**Definition of Done:** Pushing a `v*` tag triggers image builds, pushes signed multi-arch images to GHCR, and smoke tests pass.

---

### 46.5 -- `tapps_init` Docker Detection, Config Generation & Companion Recommendations

**Points:** 8

Extend `tapps_init` (pipeline tool + CLI), `setup_generator.py`, and the elicitation wizard to detect Docker MCP Toolkit, generate gateway-based MCP client configurations, and recommend companion servers.

#### 46.5a -- Settings Model: `DockerSettings`

Add Docker configuration to `TappsMCPSettings` in `tapps_core/config/settings.py`:

```python
class DockerSettings(BaseModel):
    """Docker MCP distribution settings."""
    enabled: bool = False
    transport: Literal["auto", "docker", "exe", "uv"] = "auto"
    profile: str = "tapps-standard"
    image: str = "ghcr.io/tapps-mcp/tapps-mcp:latest"
    docs_image: str = "ghcr.io/tapps-mcp/docs-mcp:latest"
    companions: list[str] = ["context7"]  # recommended companion servers

class TappsMCPSettings(BaseSettings):
    # ... existing fields ...
    docker: DockerSettings = DockerSettings()
```

Persist via `.tapps-mcp.yaml`:
```yaml
docker:
  enabled: true
  transport: docker
  profile: tapps-standard
  companions: [context7, github]
```

#### 46.5b -- Docker Detection in `pipeline/init.py`

Add a new `_detect_docker()` phase in `bootstrap_pipeline()`:

```python
async def _detect_docker(state: _BootstrapState) -> dict:
    """Detect Docker Desktop and MCP Toolkit availability."""
    result = {
        "docker_available": False,
        "docker_mcp_available": False,
        "docker_version": None,
        "installed_servers": [],
    }
    # 1. Check docker CLI on PATH
    # 2. Check `docker mcp` subcommand exists (MCP Toolkit)
    # 3. Query installed servers: `docker mcp server list`
    # 4. Compare against recommended companions
    return result
```

Store result in `_BootstrapState` for downstream use.

#### 46.5c -- MCP Config Generation in `setup_generator.py`

Extend the existing config generation to support Docker gateway entries:

- Extend `_detect_command_path()` to check `docker.transport` setting:
  ```python
  if settings.docker.enabled and settings.docker.transport in ("docker", "auto"):
      return "docker"  # command is "docker", args come from profile
  ```
- Add `_build_docker_server_entry(host: str, settings: TappsMCPSettings) -> dict`:
  ```python
  def _build_docker_server_entry(host, settings):
      return {
          "command": "docker",
          "args": ["mcp", "gateway", "run", "--profile", settings.docker.profile],
      }
  ```
- Extend `_merge_config()` to recognize Docker entries in `upgrade_mode`:
  ```python
  if upgrade_mode and old_entry.get("command") == "docker":
      # Preserve Docker profile reference
      new_entry["args"] = old_entry["args"]
  ```
- Extend `_is_valid_tapps_command()` in `doctor.py` (see 46.7) to accept `"docker"` as valid command
- Generate configs for all detected hosts: `.mcp.json` (Claude project), `~/.claude.json` (Claude user), `.cursor/mcp.json`, `.vscode/mcp.json`

#### 46.5d -- Companion Recommendation

After Docker detection, compare installed servers against recommended companions:

```python
async def _recommend_companions(state: _BootstrapState, settings: TappsMCPSettings) -> dict:
    """Recommend missing companion MCP servers."""
    installed = set(state.docker_result["installed_servers"])
    recommended = set(settings.docker.companions)
    missing = recommended - installed
    return {
        "installed": sorted(installed & recommended),
        "missing": sorted(missing),
        "install_commands": [
            f"docker mcp profile server add {settings.docker.profile} --server catalog://{s}"
            for s in sorted(missing)
        ],
    }
```

Include recommendations in the `tapps_init` response under `docker.companions`.

#### 46.5e -- Elicitation Wizard Update

Extend `common/elicitation.py` to add Docker-related questions (only when Docker is detected):

```python
# Question 7 (conditional: only if Docker MCP Toolkit detected)
{
    "id": "docker_transport",
    "title": "MCP Server Transport",
    "description": "How should TappsMCP run?",
    "options": [
        {"value": "docker", "label": "Docker MCP Gateway (recommended)"},
        {"value": "exe", "label": "Local executable (tapps-mcp.exe)"},
        {"value": "uv", "label": "uv run (development)"},
    ],
}
# Question 8 (conditional: only if docker transport selected)
{
    "id": "docker_profile",
    "title": "Companion Profile",
    "description": "Which companion servers to include?",
    "options": [
        {"value": "tapps-minimal", "label": "Minimal (TappsMCP only)"},
        {"value": "tapps-standard", "label": "Standard (+ DocsMCP + Context7)"},
        {"value": "tapps-full", "label": "Full (+ GitHub + Filesystem)"},
    ],
}
```

Persist choices to `.tapps-mcp.yaml` `docker:` section.

**Tasks:**
- Add `DockerSettings` to settings model
- Add `_detect_docker()` to `pipeline/init.py`
- Extend `_build_server_entry()` / add `_build_docker_server_entry()` in `setup_generator.py`
- Extend `_merge_config()` with Docker-aware upgrade_mode preservation
- Add `_recommend_companions()` logic
- Add 2 conditional wizard questions to `elicitation.py`
- Add `--transport` flag to `tapps-mcp init` CLI command in `cli.py`
- Add unit tests for detection, config generation, companion recommendations, and wizard flow

**Definition of Done:** `tapps_init` on a machine with Docker MCP Toolkit generates working gateway-based client configs, recommends missing companions, and persists Docker settings. Existing exe/uv paths remain unchanged when Docker is not detected.

---

### 46.6 -- `tapps_upgrade` Docker-Aware Preservation

**Points:** 5

Extend `tapps_upgrade` to correctly handle Docker MCP configurations during upgrades, including gateway entries, companion profiles, and Docker-specific settings.

**Tasks:**
- Extend `upgrade_pipeline()` in `pipeline/upgrade.py`:
  1. **Detect Docker mode**: Read `docker.transport` from `.tapps-mcp.yaml` settings
  2. **Backup Docker configs**: Include Docker-related entries (profile references, catalog.yaml) in pre-upgrade backup via `BackupManager`
  3. **Preserve Docker gateway entries**: When `upgrade_mode=True` in `_merge_config()`:
     - If existing command is `"docker"`, preserve `args` (profile reference)
     - Only update `env` and `instructions` fields
     - Never overwrite a Docker entry with an exe/uv entry
  4. **Regenerate companion recommendations**: After upgrade, re-run companion detection and include updated recommendations in upgrade result
  5. **Profile version check**: If using self-hosted catalog (`docker-mcp/catalog.yaml`), check if catalog image tags are outdated relative to current release

- Extend `_validate_config_file()` in `setup_generator.py`:
  - Recognize `"docker"` as a valid command (currently only accepts `"tapps-mcp"` or exe path)
  - Validate that gateway args reference an existing profile

- Update upgrade result dict:
  ```python
  {
      "docker": {
          "transport": "docker",
          "profile_preserved": True,
          "companions_status": {
              "installed": ["context7"],
              "missing": ["github"],
          },
          "image_update_available": True,  # if GHCR has newer tag
      }
  }
  ```

**Definition of Done:** `tapps_upgrade` on a Docker-configured project preserves the gateway config, doesn't downgrade to exe/uv, reports companion status, and includes Docker entries in the backup. Round-trip test: init with Docker → upgrade → verify Docker config intact.

---

### 46.7 -- `tapps_doctor` Docker Health Checks

**Points:** 5

Extend `tapps_doctor` with Docker-specific diagnostic checks that validate the full Docker MCP stack: daemon, images, gateway, companions, and connectivity.

**New check functions** (each returns `CheckResult`):

```python
def check_docker_daemon() -> CheckResult:
    """Verify Docker daemon is running and accessible."""
    # Run: docker info --format '{{.ServerVersion}}'
    # Pass: version returned
    # Fail: connection refused / not installed

def check_docker_mcp_toolkit() -> CheckResult:
    """Verify Docker MCP Toolkit plugin is installed."""
    # Run: docker mcp --version
    # Pass: version returned
    # Fail: 'mcp' not a docker command

def check_docker_images() -> CheckResult:
    """Verify tapps-mcp and docs-mcp images exist locally or are pullable."""
    # Run: docker image inspect <image>
    # Pass: image exists with expected labels
    # Fail: image not found (suggest: docker pull)

def check_docker_gateway() -> CheckResult:
    """Verify gateway can start and route to tapps-mcp."""
    # Run: docker mcp gateway run --profile <profile> (with timeout)
    # Send tools/list request
    # Pass: expected tool count returned
    # Fail: gateway error or wrong tool count

def check_docker_companions() -> CheckResult:
    """Verify recommended companion servers are in the active profile."""
    # Run: docker mcp server list (or parse profile config)
    # Compare against settings.docker.companions
    # Pass: all companions present
    # Warn: some missing (with install commands)

def check_docker_mcp_config() -> CheckResult:
    """Verify MCP client config references Docker gateway (not stale exe/uv)."""
    # Read .mcp.json / .claude.json / .cursor/mcp.json
    # Check command == "docker" and args reference valid profile
    # Pass: Docker config present
    # Fail: config references exe/uv when docker.enabled == True
```

**Tasks:**
- Add 6 new check functions to `distribution/doctor.py`
- Integrate into `run_doctor_structured()`:
  - Docker checks only run when `docker.enabled == True` in settings OR Docker is detected on PATH
  - Group Docker checks under a `"docker"` section in structured output
- Extend `_is_valid_tapps_command()` to accept `"docker"` as valid
- Add CLI output formatting for Docker checks (green/red with remediation hints)
- Structured output format:
  ```python
  {
      "checks": [...existing checks...],
      "docker_checks": [
          {"name": "Docker daemon", "ok": True, "message": "Docker 27.4.1 running"},
          {"name": "MCP Toolkit", "ok": True, "message": "docker-mcp v0.3.2"},
          {"name": "tapps-mcp image", "ok": True, "message": "ghcr.io/tapps-mcp/tapps-mcp:0.8.0"},
          {"name": "docs-mcp image", "ok": False, "message": "Not found", "detail": "Run: docker pull ghcr.io/tapps-mcp/docs-mcp:latest"},
          {"name": "Gateway connectivity", "ok": True, "message": "28 tools via tapps-standard profile"},
          {"name": "Companions", "ok": False, "message": "Missing: github", "detail": "Run: docker mcp profile server add tapps-standard --server catalog://github"},
      ],
      "docker_pass_count": 4,
      "docker_fail_count": 2,
  }
  ```
- Add unit tests for each check function (mock subprocess calls)

**Definition of Done:** `tapps_doctor` on a Docker-configured project validates the full stack (daemon → toolkit → images → gateway → companions → client config) and provides actionable remediation hints for failures.

---

### 46.8 -- Expert Knowledge & Documentation Updates

**Points:** 3

Update the expert knowledge base with Docker MCP Toolkit patterns, companion ecosystem, and lifecycle integration. Update project documentation.

**Tasks:**
- Create `experts/knowledge/cloud-infrastructure/docker-mcp-toolkit.md` *(already done in prior session)*:
  - Docker MCP Catalog architecture (gateway, profiles, dynamic discovery)
  - `server.yaml` format and required fields
  - `tools.json` generation for build-time validation
  - Custom catalog creation and import
  - Security model (signed images, SBOM, provenance)
  - Client configuration patterns (Claude, Cursor, VS Code)
  - Transport selection (stdio for gateway, streamable-http for direct)
- Create `experts/knowledge/cloud-infrastructure/mcp-companion-ecosystem.md`:
  - Companion server selection criteria
  - Profile composition patterns (minimal, standard, full)
  - Context7 dual role (API vs MCP server)
  - GitHub MCP for PR/issue workflow
  - Filesystem MCP for sandboxed file access
  - Profile sharing via OCI registries
  - Enterprise catalog curation
- Update `experts/knowledge/development-workflow/deployment-patterns.md` *(already done)*:
  - Docker MCP Toolkit as distribution channel
  - Gateway-based client configuration
- Update `experts/knowledge/software-architecture/mcp-server-architecture.md` *(already done)*:
  - Docker MCP Gateway transport
  - Docker MCP Catalog publishing
- Update `README.md` distribution section with Docker MCP install option
- Update `AGENTS.md` with Docker distribution notes

**Definition of Done:** Expert system returns Docker MCP Toolkit and companion guidance when asked about MCP distribution, containerization, deployment, or companion servers. README includes Docker MCP install instructions.

---

## Summary

| Story | Points | New Files | Modified Files | Est. Tests |
|-------|--------|-----------|----------------|------------|
| 46.1  | 5      | 1 (.dockerignore) | 2 (Dockerfiles) | ~8 |
| 46.2  | 5      | 7 (server.yaml x2, tools.json x2, readme.md x2, generate script) | 0 | ~6 |
| 46.3  | 5      | 5 (3 profiles, catalog.yaml, README) | 0 | ~8 |
| 46.4  | 5      | 1 (workflow YAML) | 0 | ~6 (CI smoke tests) |
| 46.5  | 8      | 0 | 6 (settings.py, init.py, setup_generator.py, elicitation.py, cli.py, models.py) | ~18 |
| 46.6  | 5      | 0 | 2 (upgrade.py, setup_generator.py) | ~10 |
| 46.7  | 5      | 0 | 1 (doctor.py) | ~12 |
| 46.8  | 3      | 1 (mcp-companion-ecosystem.md) | 3 (README.md, AGENTS.md, docker-mcp-toolkit.md) | 0 |
| **Total** | **41** | **15** | **14** | **~68** |

---

## Implementation Order

```
46.1 (Dockerfiles)
  └── 46.2 (Registry metadata)  ← needs working images
        └── 46.4 (CI/GHCR push) ← needs metadata for tagging
              └── 46.3 (Companion profiles) ← needs images in GHCR

46.5 (tapps_init + settings + setup_generator)
  ├── 46.6 (tapps_upgrade) ← depends on settings model and config generation
  └── 46.7 (tapps_doctor)  ← depends on settings model and Docker detection

46.8 (Knowledge) ← can start anytime, partially done
```

Two parallel tracks:
- **Track A (Images):** 46.1 → 46.2 → 46.4 → 46.3
- **Track B (Lifecycle):** 46.5 → 46.6 + 46.7 (parallel)
- **Track C (Knowledge):** 46.8 (independent)

---

## Cross-References

- [Epic 6 — Distribution & Production Readiness](EPIC-6-DISTRIBUTION.md) — Original Docker/PyPI/npm distribution
- [Epic 37 — Pipeline Onboarding & Distribution](EPIC-37-PIPELINE-ONBOARDING-DISTRIBUTION.md) — Plugin builder, upgrade rollback, elicitation wizard
- [Epic 33 — Platform Artifact Correctness](EPIC-33-PLATFORM-ARTIFACT-CORRECTNESS.md) — Skills, subagents, permission generation
- [DocsMCP Epic 10 — Distribution & CLI](../DOCSMCP_PRD.md) — DocsMCP PyPI publish (complementary)
- [Docker MCP Registry](https://github.com/docker/mcp-registry) — Submission target
- [Docker MCP Gateway](https://github.com/docker/mcp-gateway) — Open-source gateway/proxy
- [Docker MCP Toolkit Docs](https://docs.docker.com/ai/mcp-catalog-and-toolkit/toolkit/) — Official documentation
- [Docker MCP Profiles Docs](https://docs.docker.com/ai/mcp-catalog-and-toolkit/profiles/) — Profile management

## Cross-Epic Architecture Summary

```
Distribution Channels (after Epic 46):

  ┌──────────────────────────────────────────────────────────────┐
  │                    User Install Options                       │
  ├──────────────────────────────────────────────────────────────┤
  │                                                              │
  │  1. Docker MCP Toolkit (NEW - Epic 46)                       │
  │     docker mcp catalog → browse → install                    │
  │     Zero dependencies, cross-platform, signed                │
  │                                                              │
  │     Curated Profiles:                                        │
  │     ┌─────────────────────────────────────────────────┐     │
  │     │ tapps-minimal:  tapps-mcp                       │     │
  │     │ tapps-standard: tapps-mcp + docs-mcp + context7 │     │
  │     │ tapps-full:     + github + filesystem           │     │
  │     └─────────────────────────────────────────────────┘     │
  │              │                                               │
  │              v                                               │
  │     ┌─────────────┐     ┌──────────────┐                   │
  │     │  MCP Gateway │────▶│ tapps-mcp    │                   │
  │     │  (stdio)     │────▶│ docs-mcp     │                   │
  │     │              │────▶│ context7     │ (companion)       │
  │     │              │────▶│ github       │ (companion)       │
  │     │              │────▶│ filesystem   │ (companion)       │
  │     └─────────────┘     └──────────────┘                   │
  │                                                              │
  │  2. PyPI (Epic 6 / DocsMCP Epic 10)                          │
  │     pip install tapps-mcp / docs-mcp                         │
  │     Requires Python 3.12+                                    │
  │                                                              │
  │  3. PyInstaller exe (Epic 6)                                 │
  │     tapps-mcp.exe / docsmcp.exe                              │
  │     Windows-only, offline-capable                            │
  │                                                              │
  │  4. uv run (development)                                     │
  │     uv run tapps-mcp serve                                   │
  │     Source checkout required                                 │
  │                                                              │
  ├──────────────────────────────────────────────────────────────┤
  │  Lifecycle Tools (Docker-aware):                              │
  │                                                              │
  │  tapps_init   → detects Docker, generates gateway config,    │
  │                 recommends missing companions                 │
  │  tapps_upgrade→ preserves Docker entries, checks image tags  │
  │  tapps_doctor → validates daemon, toolkit, images, gateway,  │
  │                 companions, and client config                 │
  └──────────────────────────────────────────────────────────────┘

Docker MCP Registry Submission:

  ┌─────────────────┐    PR    ┌──────────────────────┐
  │ docker-mcp/     │────────▶│ docker/mcp-registry   │
  │  tapps-mcp/     │         │                      │
  │   server.yaml   │  review │  Docker builds,      │
  │   tools.json    │◀────────│  signs, publishes    │
  │   readme.md     │  24hrs  │  to mcp/tapps-mcp    │
  │  docs-mcp/      │         │  on Docker Hub       │
  │   server.yaml   │         └──────────────────────┘
  │   tools.json    │
  │   readme.md     │
  │  profiles/      │  ← shareable via OCI push
  │   tapps-*.yaml  │
  │  catalog.yaml   │  ← self-hosted alternative
  └─────────────────┘

Lifecycle Integration (init / upgrade / doctor):

  ┌─────────────┐         ┌──────────────┐         ┌─────────────┐
  │ tapps_init  │         │tapps_upgrade │         │tapps_doctor │
  ├─────────────┤         ├──────────────┤         ├─────────────┤
  │ _detect_    │         │ Preserve     │         │ check_docker│
  │  docker()   │         │  Docker      │         │  _daemon()  │
  │ _build_     │         │  gateway     │         │ check_docker│
  │  docker_    │         │  entries     │         │  _mcp_      │
  │  server_    │         │ Backup       │         │  toolkit()  │
  │  entry()    │         │  Docker      │         │ check_docker│
  │ _recommend_ │         │  configs     │         │  _images()  │
  │  companions │         │ Report       │         │ check_docker│
  │ Wizard Q7-8 │         │  companion   │         │  _gateway() │
  │ Settings    │         │  status      │         │ check_docker│
  │  persist    │         │ Image tag    │         │  _companions│
  └─────────────┘         │  freshness   │         │ check_docker│
                          └──────────────┘         │  _mcp_      │
                                                   │  config()   │
                                                   └─────────────┘
```

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Docker MCP Catalog rejects submission | Low | Medium | Self-hosted catalog as fallback; MIT license meets requirements |
| MCP Gateway stdio incompatibility | Low | High | Test extensively; servers already support stdio transport |
| Docker Desktop not installed on user machines | Medium | Low | `tapps_init` auto-detects; falls back to exe/uv path |
| Companion servers change API/catalog name | Medium | Low | Pin to catalog:// references; companion list is configurable in settings |
| Monorepo build context too large | Low | Low | `.dockerignore` excludes tests, docs, .venv; multi-stage build |
| Image size too large | Medium | Medium | Multi-stage build, slim base, no dev dependencies |
| Registry format changes | Low | Medium | Pin to current spec; monitor docker/mcp-registry for updates |
| Profile sharing format unstable | Medium | Low | OCI push is GA; fall back to catalog.yaml if format changes |
| Docker subprocess calls in init/doctor slow on cold start | Medium | Low | Cache detection results in `_BootstrapState`; timeout guards |
