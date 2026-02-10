# Epic 6: Distribution, Production Readiness & Future

**Status:** Complete
**Priority:** P3 — Important for adoption, not for functionality
**Estimated LOE:** ~2-3 weeks (1 developer)
**Dependencies:** Epic 1 (Core Quality MVP), ideally all epics complete
**Blocks:** None

---

## Goal

Make TappsMCP easy to install, easy to configure, and production-ready. This epic covers PyPI publishing, Docker packaging, one-command setup, CI/CD pipelines, and forward-looking features (MCP resources/prompts, shared `tapps-core` package, full workflow state).

## 2026 Best Practices Applied

- **PyPI with trusted publishing**: Use GitHub Actions OIDC trusted publisher for PyPI uploads — no API tokens stored in secrets. See [PyPI trusted publishers](https://docs.pypi.org/trusted-publishers/).
- **Multi-stage Docker builds**: Slim production image with pre-installed tools (ruff, mypy, bandit). Development image with test dependencies. Use `python:3.12-slim` base.
- **`uv` for fast installs**: Support `uv pip install tapps-mcp` alongside regular `pip install tapps-mcp`. Include `uv.lock` for reproducible environments.
- **MCP resources and prompts (protocol `2025-11-25` features)**: Expose knowledge files as MCP resources via `@mcp.resource("tapps://knowledge/{domain}/{topic}")` and the system prompt as an MCP prompt template via `@mcp.prompt()`. These features can eliminate manual system prompt configuration.
- **ASGI production deployment**: Use `mcp.http_app()` to get an ASGI app for uvicorn/gunicorn. Streamable HTTP serves at `/mcp` endpoint.
- **`fastmcp run --reload` for development**: Hot-reload during development with `fastmcp run server.py --reload`.
- **Semantic versioning with changelog**: `CHANGELOG.md` following Keep a Changelog format. Automated version bumping via `bump-my-version` or similar.
- **npm wrapper via `npx`**: For Cursor users who live in the Node ecosystem, provide `npx tapps-mcp` that auto-installs the Python package. Use `@anthropic/sdk`-style wrapper pattern.

## Acceptance Criteria

- [ ] `pip install tapps-mcp` works (base install)
- [ ] `pip install tapps-mcp[vector]` installs FAISS extras
- [ ] `tapps-mcp init` generates config for Claude Code / Cursor / VS Code
- [ ] `npx tapps-mcp` works for Node.js users
- [ ] Docker image published to GitHub Container Registry
- [ ] Docker image includes ruff, mypy, bandit pre-installed
- [ ] CI pipeline: test on Windows + Linux + macOS, Python 3.12 + 3.13
- [ ] CI pipeline: publish to PyPI on git tag (trusted publishing)
- [ ] Setup guide: Claude Code, Cursor, VS Code + Continue
- [ ] Setup time < 5 minutes from install to working MCP server
- [ ] MCP resources expose knowledge files via `@mcp.resource()` (e.g., `tapps://knowledge/security/owasp-top-10`)
- [ ] MCP prompt template provides system prompt via `@mcp.prompt()` — eliminates manual config

---

## Stories

### 6.1 — PyPI Publishing

**Points:** 3

Publish `tapps-mcp` to PyPI with proper metadata and extras.

**Tasks:**
- Finalize `pyproject.toml`:
  - Package name: `tapps-mcp`
  - Entry point: `tapps-mcp = tapps_mcp.cli:main`
  - Extras: `[vector]` for FAISS + sentence-transformers
  - Classifiers, license, URLs, Python version constraints
- Set up GitHub Actions trusted publisher workflow
- Build with `uv build` or `python -m build`
- Test install in clean virtualenv on all platforms
- Publish to TestPyPI first, then PyPI

**Definition of Done:** `pip install tapps-mcp` installs a working CLI. `tapps-mcp serve` starts the server.

---

### 6.2 — One-Command Setup

**Points:** 3

`tapps-mcp init` generates configuration for popular MCP hosts.

**Tasks:**
- Implement `tapps-mcp init` command:
  - Detect which MCP hosts are installed (Claude Code, Cursor)
  - Generate appropriate config file:
    - Claude Code: write to `~/.claude/settings.json` (merge with existing)
    - Cursor: write to `.cursor/mcp.json`
    - VS Code + Continue: write to `.continue/config.json`
  - Prompt for optional settings: Context7 API key, quality preset
  - Generate minimal system prompt and copy to clipboard
- `tapps-mcp init --check` verifies existing config is working

**Definition of Done:** `tapps-mcp init` generates working config in < 30 seconds. No manual JSON editing required.

---

### 6.3 — npm Wrapper

**Points:** 2

`npx tapps-mcp` for Node.js ecosystem users (Cursor users).

**Tasks:**
- Create npm package `tapps-mcp` (thin wrapper)
- Wrapper checks for Python installation, installs `tapps-mcp` via pip/uv if needed
- Delegates to `tapps-mcp serve` with all args forwarded
- Publish to npm registry
- Test on Windows + Linux + macOS

**Definition of Done:** `npx tapps-mcp serve` works for users with Python installed.

---

### 6.4 — Docker Image

**Points:** 3

Zero-dependency deployment via Docker.

**Tasks:**
- Create multi-stage Dockerfile:
  - Builder stage: install Python deps
  - Production stage: `python:3.12-slim` + ruff + mypy + bandit + radon pre-installed
- Create `docker-compose.yml` for easy local use
- Support both stdio and Streamable HTTP transports in container
- Pre-warm cache with common library docs (React, FastAPI, Express, etc.)
- Publish to GitHub Container Registry (ghcr.io)
- Test: `docker run ghcr.io/tapps/tapps-mcp serve` works

**Definition of Done:** Docker image starts MCP server with all tools pre-installed. Image size < 500MB.

---

### 6.5 — CI/CD Pipeline

**Points:** 3

Comprehensive CI/CD with multi-platform testing and automated publishing.

**Tasks:**
- GitHub Actions workflows:
  - `test.yml`: test matrix (Windows/Linux/macOS × Python 3.12/3.13)
  - `lint.yml`: ruff check + ruff format + mypy strict
  - `publish.yml`: build + publish to PyPI on tag (trusted publishing)
  - `docker.yml`: build + push Docker image on tag
- Test coverage reporting (codecov or similar)
- Dependency scanning (dependabot or renovate)
- Security scanning (CodeQL or similar)

**Definition of Done:** CI passes on all platforms. Tags auto-publish to PyPI and GHCR.

---

### 6.6 — Documentation

**Points:** 2

Comprehensive setup guides and API documentation.

**Tasks:**
- README.md: overview, features, quick start, architecture diagram
- Setup guides:
  - Claude Code setup (with screenshots)
  - Cursor setup (with screenshots)
  - VS Code + Continue setup
  - Docker setup
- Tool reference: all tools with input/output schemas and examples
- System prompt guide: recommended prompts for different workflows
- Troubleshooting: common issues and solutions
- Contributing guide: how to add knowledge files, new validators, new domains

**Definition of Done:** A developer can set up TappsMCP from documentation alone in < 5 minutes.

---

### 6.7 — Implement MCP Resources & Prompts

**Points:** 5

Implement MCP resources and prompts using FastMCP's `@mcp.resource()` and `@mcp.prompt()` decorators. These are supported features in protocol `2025-11-25`.

**Tasks:**
- **MCP Resources** — Expose knowledge files as browsable resources:
  ```python
  @mcp.resource("tapps://knowledge/{domain}/{topic}")
  def get_knowledge(domain: str, topic: str) -> str:
      """Retrieve expert knowledge for a domain and topic."""
      ...

  @mcp.resource("tapps://config/quality-presets")
  def get_presets() -> str:
      """Get available quality gate presets."""
      ...
  ```
  - Expose all 119 knowledge files across 16 domains
  - Expose quality gate presets and scoring configuration
  - Expose project profile data
- **MCP Prompts** — Provide system prompt as template:
  ```python
  @mcp.prompt()
  def tapps_workflow(task_type: str = "general") -> str:
      """Generate the TappsMCP workflow prompt for LLM integration."""
      ...
  ```
  - Eliminates manual system prompt configuration in Claude Code / Cursor
  - Task-type-specific prompts (feature, bugfix, refactor, config)
  - Include recommended tool call order
- Test with Claude Code and Cursor to verify client support

**Definition of Done:** Knowledge files browsable as MCP resources. System prompt auto-provided via MCP prompt template.

---

### 6.8 — (Future) Shared `tapps-core` Package

**Points:** 8 (placeholder — this is Phase 6 / post-launch)

Extract truly shared modules into a separate PyPI package.

**Tasks:**
- Identify modules shared between `tapps-agents` and `tapps-mcp`:
  - `scoring/` (scorer, constants, registry, validators)
  - `gates/` (base, quality gates, security gate, enforcement)
  - `security/` (path validator, io guardrails, rag safety, governance)
  - `knowledge/` (kb cache, fuzzy matcher, circuit breaker, context7 client)
  - `experts/` core (engine, registry, builtins, base expert, simple RAG)
- Create `tapps-core` package with stable API
- Refactor both `tapps-agents` and `tapps-mcp` to depend on `tapps-core`
- Publish to PyPI
- Set up version synchronization

**Definition of Done:** Bug fixes to shared logic go into `tapps-core`. Both consumers get them via version bumps.

**Note:** This is a future epic, not part of the initial launch. Track upstream changes in `SYNC_LOG.md` until then.

---

### 6.9 — (Future) Full Workflow State Tool

**Points:** 5 (placeholder — only if demand exists)

Optional advanced tool for power users who want full checkpoint/restore semantics.

**Tasks:**
- Extract from `workflow/`:
  - `state_manager.py` → `tapps_mcp/state/manager.py`
  - `durable_state.py` → `durable_state.py`
  - `checkpoint_manager.py` → `checkpoints.py`
  - `execution_metrics.py` → `metrics.py`
- Wire as `tapps_workflow_state` MCP tool
- Only implement if `tapps_session_notes` users request full state management

**Definition of Done:** Power users can save/restore full workflow checkpoints via MCP.

**Note:** Only build this if there's user demand from Epic 4's `tapps_session_notes`.

---

### 6.10 — (Future) Auto Expert Generator

**Points:** 3 (placeholder)

Evaluate extracting `experts/auto_generator.py` as a `tapps_generate_expert` tool.

**Tasks:**
- Evaluate feasibility: can an MCP tool generate new expert domains from user-provided knowledge?
- If viable: implement `tapps_generate_expert` tool
- If not: document why and close

---

## Key Dependencies
- `build` — Python build backend
- `twine` — PyPI upload (or GitHub Actions trusted publisher)
- Docker — for container image

## Success Metrics
- Setup time < 5 minutes from `pip install` to working server
- `npx tapps-mcp` works for Node.js users
- Docker image < 500MB
- CI passes on all 6 platform/version combinations
