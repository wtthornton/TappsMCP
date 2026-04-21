<div align="center">

# Tapps Platform

**A quality and documentation toolset for AI coding assistants.**

Two MCP servers — **TappsMCP** (code quality) and **DocsMCP** (documentation) — that give LLMs and AI-powered IDEs **58 deterministic tools** for scoring, security scanning, quality gates, documentation lookup, doc generation, config validation, and shared memory.

[![CI](https://github.com/wtthornton/TappsMCP/actions/workflows/ci.yml/badge.svg)](https://github.com/wtthornton/TappsMCP/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP Protocol](https://img.shields.io/badge/MCP-2025--11--25-green.svg)](https://modelcontextprotocol.io/)
[![Tests](https://img.shields.io/badge/tests-6%2C900%2B_passing-brightgreen.svg)](#development)
[![Tools](https://img.shields.io/badge/MCP_tools-58-blue.svg)](#tools-reference)
[![Version](https://img.shields.io/badge/version-2.10.6-informational.svg)](#)

**Supported clients:** Claude Code · Cursor · VS Code (Copilot) · Claude Desktop · any MCP host

[Quick Start](#quick-start) · [Install](#install) · [Tools Reference](#tools-reference) · [Architecture](#architecture) · [Docs](#docs-and-roadmap)

</div>

---

## Overview

**Tapps Platform** ships two MCP servers for AI-assisted development: **TappsMCP** (code quality, security, shared memory) and **DocsMCP** (documentation generation and maintenance). Together they expose **58 tools** with structured, deterministic outputs suitable for Claude Code, Cursor, VS Code, and any MCP host.

### What's new in v2.10+

- **Resilient BrainBridge** (v2.10.0) — runtime tapps-brain version validation, stable agent identity persisted across restarts, offline write-queue drain on shutdown, graceful `BrainBridgeUnavailable` degraded payloads in every `tapps_memory` action.
- **DocsMCP quality fixes** (v2.10.2) — `docs_generate_changelog` refuses to overwrite hand-crafted files without `force=True`; `docs_check_style` auto-detects heading convention instead of defaulting to sentence-case; drift and completeness checkers no longer false-positive on test files.
- **Session reliability** (v2.10.3) — `_SessionFlags` dataclass eliminates magic-string race conditions in session state; atomic write for `AGENTS.md` upgrades; upgrade aborts on backup failure; workspace monorepo `pip-audit` scans now pass `--skip-editable`.
- **Karpathy behavioral guidelines** (v2.9.0) — vendored into the package and installed/refreshed by `tapps_init` / `tapps_upgrade` / verified by `tapps_doctor`.

See [CHANGELOG.md](CHANGELOG.md) for the full history.

**Memory & pipeline defaults** are POC-oriented: recurring `tapps_quick_check` memory, architectural **supersede**, impact-analysis enrichment, and **memory_hooks** (auto-recall / auto-capture) default **on** in shipped `default.yaml`. Override under `memory:` and `memory_hooks:` in `.tapps-mcp.yaml`, or inspect effective values with `tapps-mcp doctor`. See [docs/MEMORY_REFERENCE.md](docs/MEMORY_REFERENCE.md).

---

### Packages

| Package | PyPI Name | Purpose | Tools |
|---|---|---|---|
| **tapps-brain** | `tapps-brain` | Standalone memory system (SQLite persistence, BM25 retrieval, decay, federation) | 0 (library) |
| **tapps-core** | `tapps-core` | Shared infrastructure (config, security, logging, knowledge, metrics, adaptive) | 0 (library) |
| **tapps-mcp** | `tapps-mcp` | Code quality MCP server (scoring, gates, tools, validation) | 26 |
| **docs-mcp** | `docs-mcp` | Documentation generation and maintenance MCP server | 32 |

```
tapps-brain (standalone)  <──  tapps-core (shared infra)  <──  tapps-mcp (26 tools)
                                                          <──  docs-mcp  (32 tools)
                                                                      = 58 MCP tools
```

### Key highlights

- **58 deterministic MCP tools** (26 TappsMCP + 32 DocsMCP) — no LLM calls in the tool chain; same input always produces same output
- **Multi-language code scoring** - Python, TypeScript/JavaScript, Go, Rust across 7 categories (complexity, security, maintainability, test coverage, performance, structure, devex)
- **Documentation lookup** via Context7 and LlmsTxt providers with local caching
- **Persistent shared memory** via [tapps-brain](https://github.com/wtthornton/tapps-brain) - project decisions survive across sessions (SQLite + BM25 retrieval, time-based decay, federation)
- **Unified feature flags** - optional dependency detection (faiss, numpy, radon) with graceful degradation
- **Platform generation** - auto-generates hooks, agents, skills, and rules for Claude Code, Cursor, and VS Code
- **Self-bootstrapping** - `tapps_init` sets up quality infrastructure in any project with one call
- **Docker distribution** - Docker images for external distribution and CI/CD
- **6,900+ tests** across 3 packages with strict mypy and ruff enforcement, parallel execution (pytest-xdist), and randomized ordering (pytest-randomly)
- **Benchmark infrastructure** - AGENTBench evaluation, template optimization, tool effectiveness measurement

---

## Table of contents

- [What is TappsMCP?](#what-is-tappsmcp)
- [Features](#features)
- [Install](#install)
- [Quick start](#quick-start)
- [Connecting your AI client](#connecting-your-ai-client)
- [Bootstrapping TappsMCP in your project](#bootstrapping-tappsmcp-in-your-project)
- [Upgrading](#upgrading)
- [CLI utilities](#cli-utilities)
- [Tools reference](#tools-reference)
- [Configuration](#configuration)
- [Optional tool dependencies](#optional-tool-dependencies)
- [Docker](#docker)
- [Architecture](#architecture)
- [Development](#development)
- [Project layout](#project-layout)
- [DocsMCP (documentation server)](#docsmcp-documentation-server)
- [Docs and roadmap](#docs-and-roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## What is TappsMCP?

TappsMCP is a **quality toolset designed to help other projects and LLMs be the best they can**. LLMs writing code make repeatable mistakes: wrong APIs, missing tests, security issues, and inconsistent quality. TappsMCP moves **proven quality tooling** out of long system prompts and into a single MCP server that any project can install and use.

Any MCP-capable client (Claude Code, Cursor, VS Code Copilot, Claude Desktop, custom hosts) can call the same tools and get **structured, deterministic results** — scores, gates, security findings, doc lookups, and expert advice — without burning context on framework instructions. Install TappsMCP in your project, connect your AI client, and every coding session benefits from consistent quality enforcement.

---

## Features

The platform exposes **58 MCP tools** (26 TappsMCP + 32 DocsMCP) plus workflow prompts. All tools are **deterministic** (no LLM calls in the tool chain).

### Code quality & scoring

| Feature | Description |
|--------|-------------|
| **Code scoring** | 0–100 score across 7 categories: complexity, security, maintainability, test coverage, performance, structure, developer experience. Python uses ruff, mypy, bandit, radon, pylint+perflint (optional). TypeScript/JavaScript, Go, Rust use tree-sitter AST analysis (optional dependency, falls back to regex). See [Supported Languages](#supported-languages). |
| **Quality gates** | Pass/fail against configurable presets: **standard**, **strict**, **framework**. |
| **Structured outputs** | Machine-parseable JSON (`structuredContent`) for 6 tools: `tapps_score_file`, `tapps_quality_gate`, `tapps_quick_check`, `tapps_security_scan`, `tapps_validate_changed`, `tapps_validate_config`. |
| **Dead code detection** | Vulture-based unused functions, classes, imports, variables with confidence scoring; integrated into maintainability/structure. |
| **Circular dependency detection** | AST import graph, cycle detection, coupling metrics (Ca/Ce/instability). |
| **Session checklist** | Track which tools were called; required vs recommended by task type (feature, bugfix, refactor, security, review). **LLM engagement level** (high/medium/low) adjusts required tools and wording. |
| **Adaptive learning** | Scoring weights and expert voting adapt from usage. Adaptive domain detection routes queries based on learned feedback when enabled. Query expansion with ~120 synonym pairs improves domain detection recall. |

### Security & dependencies

| Feature | Description |
|--------|-------------|
| **Security scanning** | Bandit + secret detection with redacted context; severity counts and locations. |
| **Dependency vulnerability scanning** | pip-audit for known CVEs; severity filtering. |
| **Config validation** | Dockerfile, docker-compose, WebSocket/MQTT/InfluxDB best-practice checks. |
| **Path safety** | All file I/O restricted to configurable project root. |

### Knowledge & context

| Feature | Description |
|--------|-------------|
| **Documentation lookup** | Up-to-date library docs via Context7 (when `TAPPS_MCP_CONTEXT7_API_KEY` is set) and LlmsTxt (always available as fallback). Fuzzy matching, local cache. |
| **Project context** | Detect project type, tech stack, structure for context-aware analysis. |
| **Shared memory** | Powered by [tapps-brain](https://github.com/wtthornton/tapps-brain) — BM25 retrieval, decay, contradiction detection, federation, Hive (Agent Teams). **33 actions** on `tapps_memory` (CRUD, search, federation, profiles, security, maintenance, Hive). Shipped defaults turn on pipeline integrations and hooks; see [docs/MEMORY_REFERENCE.md](docs/MEMORY_REFERENCE.md). For local wiring and the VSCode/GUI-launch env-var gotcha, see [Local setup guide](docs/operations/TAPPS-BRAIN-LOCAL-SETUP.md). |
| **Session notes** | In-memory decisions and constraints for a single session. Promotable to shared memory for persistence. |
| **Impact analysis** | File dependencies and blast radius before refactoring or API changes. |
| **Quality reports** | JSON, Markdown, or HTML summaries. |

### Pipeline & platform integration

| Feature | Description |
|--------|-------------|
| **LLM engagement level** | **high** / **medium** / **low** — controls how strongly the AI is prompted (MUST/REQUIRED vs optional). Set via `.tapps-mcp.yaml`, env, or `tapps_set_engagement_level`. |
| **Platform hooks** | Auto-generated hooks: Claude Code (8), Cursor (3); quality checks on edit, stop, task completion, optional memory capture on stop. |
| **Subagent definitions** | Pre-built reviewer, researcher, validator, review-fixer for Claude Code and Cursor with `mcpServers`, `maxTurns`, role-appropriate `permissionMode`. |
| **Skills generation** | SKILL.md templates (score, gate, validate, review, research, memory, security) with 2026 Claude Code `allowed-tools:` spec, `argument-hint`, `disable-model-invocation`. |
| **Cursor rule types** | Always-on pipeline, auto-attach for Python, agent-requested expert consultation. |
| **Plugin bundles** | Ready-to-install plugin dirs (hooks, agents, skills, rules, MCP config). |
| **Agent Teams** | Quality watchdog teammate for Claude Code (TeammateIdle, TaskCompleted; opt-in). |
| **VS Code / Copilot** | `.github/copilot-instructions.md` with tool guidance and workflow. |
| **Cursor BugBot** | `.cursor/BUGBOT.md` for automated PR review standards. |
| **CI integration** | GitHub Actions workflow template; headless mode docs. |
| **Cursor marketplace** | Publishable plugin with marketplace.json, deep link, skills, agents, hooks. |
| **Agent SDK examples** | Python and TypeScript examples (quality check, CI pipeline, subagent registration). |
| **MCP elicitation** | Interactive preset in `tapps_quality_gate`, init confirmation in `tapps_init` where supported. |

---

## Supported languages

TappsMCP scoring tools detect language from file extension and route to the appropriate scorer:

| Language | Extensions | Status | Tooling |
|----------|------------|--------|---------|
| **Python** | `.py`, `.pyi` | ✅ Full | ruff, mypy, bandit, radon, vulture, pylint+perflint (optional) |
| **TypeScript** | `.ts`, `.tsx` | ✅ Full | tree-sitter (optional), regex fallback |
| **JavaScript** | `.js`, `.jsx`, `.mjs`, `.cjs` | ✅ Full | Routes to TypeScript scorer |
| **Go** | `.go` | ✅ Full | tree-sitter (optional), regex fallback |
| **Rust** | `.rs` | ✅ Full | tree-sitter (optional), regex fallback |

**How it works:**
- Language is auto-detected from file extension (case-insensitive)
- `get_scorer(file_path)` returns the appropriate scorer instance
- Unsupported extensions return `None` with a clear message
- JavaScript files route to the TypeScript scorer (shared implementation)

**Tree-sitter dependencies (optional):** For best results with non-Python languages, install tree-sitter:

```bash
uv sync --extra treesitter
# or: pip install tree-sitter tree-sitter-typescript tree-sitter-go tree-sitter-rust
```

When tree-sitter is not installed, scorers fall back to regex-based analysis with `degraded: true`.

**Language-specific patterns detected:**
- **TypeScript/JS:** Nested callbacks, `any` usage, type assertions, test functions, JSDoc comments
- **Go:** `unsafe.Pointer`, defer-in-loop, exported naming (MixedCaps), error handling, doc comments
- **Rust:** `unsafe` blocks, `.unwrap()` abuse, `#[test]` attributes, `///` doc comments, `snake_case` naming

---

## Install

Choose one of the following. After installing, see [Quick start](#quick-start) to configure your AI client and start the server.

| Method | Requirements | Use when |
|--------|--------------|----------|
| **MCP Registry** | MCP-compatible client | One-click install from the official MCP server registry. |
| **PyPI** | Python 3.12+, pip | You want a global or venv install and will run from any project. |
| **npx** | Node.js 18+ | Optional; use only if an npm package matches your release. Prefer **PyPI** or **`uv run`** from source otherwise. |
| **From source** | Python 3.12+, [uv](https://docs.astral.sh/uv/) or pip | You are developing TappsMCP or want the latest code. |
| **Docker** | Docker, Docker Compose | You want HTTP transport or to run in a container. |

### Install from MCP Registry

The official [MCP Registry](https://registry.modelcontextprotocol.io) provides one-click installation for compatible clients:

- **tapps-mcp**: [`io.github.wtthornton/tapps-mcp`](https://registry.modelcontextprotocol.io/servers/io.github.wtthornton/tapps-mcp) — Code quality tools
- **docs-mcp**: [`io.github.wtthornton/docs-mcp`](https://registry.modelcontextprotocol.io/servers/io.github.wtthornton/docs-mcp) — Documentation tools

Search for "tapps" or "docs-mcp" in your MCP client's server browser.

### Install from PyPI

```bash
pip install tapps-mcp
```

Or in a virtual environment:

```bash
python -m venv .venv

# Activate:
source .venv/bin/activate       # Linux / macOS
.venv\Scripts\activate          # Windows (cmd)
.venv/Scripts/activate          # Windows (Git Bash / PowerShell)

pip install tapps-mcp
```

**Upgrade:** `pip install -U tapps-mcp` then run `tapps-mcp upgrade` to refresh all generated files (AGENTS.md, platform rules, hooks, permissions). A backup is created automatically before overwriting — use `tapps-mcp rollback` if needed. See [CHANGELOG.md](CHANGELOG.md) for changes and [docs/UPGRADE_FOR_CONSUMERS.md](docs/UPGRADE_FOR_CONSUMERS.md) for the full upgrade guide.

### Install with npx (optional)

If a matching npm package is published for your TappsMCP version, you can run without a prior `pip`/`uv` install:

```bash
npx tapps-mcp serve
```

If `npx` fails or the package is unavailable, use [PyPI](#install-from-pypi) or [from source](#install-from-source) (`uv run tapps-mcp serve`) instead.

### Install from source

Clone the repo and install in editable mode with [uv](https://docs.astral.sh/uv/) (recommended):

```bash
git clone https://github.com/wtthornton/TappsMCP.git
cd tapps-mcp
```

**With uv (monorepo workspace):**

```bash
uv sync --all-packages           # install all 3 packages
uv run tapps-mcp serve           # run TappsMCP
uv run docsmcp serve             # run DocsMCP
```

**With pip (single package):**

```bash
pip install -e packages/tapps-mcp
# Run with: tapps-mcp serve
```

### Install with Docker

From the repo root (or use the image from a registry):

```bash
git clone https://github.com/wtthornton/TappsMCP.git
cd tapps-mcp
docker compose up --build -d
```

The server listens at **http://localhost:8000** (MCP at `/mcp`). See [Docker](#docker) and [docs/DOCKER_DEPLOYMENT.md](docs/DOCKER_DEPLOYMENT.md) for options (e.g. mounting another project).

---

## What you need

TappsMCP requires an MCP config in your project, a connected MCP host, and (for scoring tools) Python. Run `tapps-mcp doctor` to verify your setup. See [docs/ONBOARDING.md](docs/ONBOARDING.md) for the full getting-started checklist.

---

## Quick start

After [installing](#install), set up TappsMCP in your project and connect your AI client.

**1. Configure your AI client (auto-detect):**

```bash
tapps-mcp init                    # detects Claude Code, Cursor, VS Code
# or: tapps-mcp init --host cursor   # target a specific client
```

**Windows / monorepo checkout:** run init against your **app** root, not the `packages/tapps-mcp` folder. Example:

```powershell
uv --directory C:\path\to\tapps-mcp run tapps-mcp init --project-root C:\path\to\your-app
```

**2. Start the server:**

```bash
tapps-mcp serve                           # stdio (local clients)
# or: uv run tapps-mcp serve             # if installed from source with uv
# or: npx tapps-mcp serve                # if using npx
# or: tapps-mcp serve --transport http    # HTTP (remote / container)
```

**3. Verify:**

```bash
tapps-mcp doctor                  # diagnose configuration and connectivity
```

Then reload your AI client. The AI can call tools like `tapps_score_file` and `tapps_quality_gate`. See [Connecting your AI client](#connecting-your-ai-client) for client-specific details.

---

## Connecting your AI client

Point your MCP client at the TappsMCP server so the AI can call the tools. TappsMCP works with any MCP-capable client.

### Auto-setup with `tapps-mcp init`

The fastest way to configure your client:

```bash
tapps-mcp init                        # auto-detect installed clients
tapps-mcp init --host claude-code     # configure Claude Code
tapps-mcp init --host cursor          # configure Cursor
tapps-mcp init --host vscode          # configure VS Code
```

This generates the correct MCP configuration file for your client. Use `tapps-mcp init --check` to verify an existing setup. See [CLI utilities](#cli-utilities) for more options.

### Claude Code

Run `tapps-mcp init --host claude-code` or manually add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "tapps-mcp": {
      "command": "tapps-mcp",
      "args": ["serve"]
    }
  }
}
```

For project-level config, use `tapps-mcp init --host claude-code --scope project` to create `.mcp.json` in the project root.

### Cursor

1. Run `tapps-mcp init --host cursor` or manually edit `.cursor/mcp.json` in your project:

```json
{
  "mcpServers": {
    "tapps-mcp": {
      "command": "uv",
      "args": ["--directory", "/path/to/tapps-mcp", "run", "--no-sync", "tapps-mcp", "serve"]
    }
  }
}
```

Use `--no-sync` to avoid "file in use" errors when Cursor starts the server.

2. Restart or reload Cursor. The AI can then use tools like `tapps_score_file` and `tapps_quality_gate`.

### VS Code (Copilot)

Run `tapps-mcp init --host vscode` or manually edit `.vscode/mcp.json` in your project:

```json
{
  "servers": {
    "tapps-mcp": {
      "command": "tapps-mcp",
      "args": ["serve"]
    }
  }
}
```

### Claude Desktop

Add to your Claude Desktop config (e.g. `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "tapps-mcp": {
      "command": "tapps-mcp",
      "args": ["serve"]
    }
  }
}
```

Restart Claude Desktop after changing the config.

### For AI assistants

When TappsMCP is connected, call **`tapps_session_start`** at session start (server info + memory status). Use **`tapps_memory`** to recall and save project decisions across sessions. Use **`tapps_quick_check`** after editing files; before declaring work complete, run **`tapps_validate_changed`** and **`tapps_checklist`**. Use **`tapps_lookup_docs`** before writing code that uses an external library. See **[AGENTS.md](AGENTS.md)** for when to use each tool and the full workflow.

### Suggested workflow for the AI

1. Call **`tapps_session_start`** at session start (server info + memory status).
2. Use **`tapps_memory search`** to recall relevant project context and past decisions.
3. Use **`tapps_quick_check`** (or `tapps_score_file` with `quick: true`) during edit-lint-fix loops.
4. Use **`tapps_lookup_docs`** before writing code that uses an external library API.
5. Use **`tapps_validate_changed`** before marking work complete (validates all changed files).
6. Use **`tapps_memory save`** to persist important decisions and learnings for future sessions.
7. Call **`tapps_checklist`** to ensure no required steps were skipped.

---

## CLI utilities

TappsMCP includes CLI commands to set up, diagnose, and run the server. All commands work on **Linux, macOS, and Windows**.

| Command | Purpose |
|---------|---------|
| `tapps-mcp serve` | Start the MCP server. Options: `--transport stdio\|http` (default: stdio), `--host` (default: 127.0.0.1), `--port` (default: 8000). |
| `tapps-mcp init` | Bootstrap TappsMCP in a project. Creates MCP config, AGENTS.md, TECH_STACK.md, hooks, agents, skills, and platform rules. See [init options](#tapps-mcp-init-options) below. |
| `tapps-mcp upgrade` | Refresh all generated files (AGENTS.md, rules, hooks, settings) after upgrading TappsMCP. Creates a backup first. |
| `tapps-mcp doctor` | Diagnose configuration and connectivity: MCP config, AGENTS.md, hooks, checkers, tapps-brain, dual-memory warning, **memory pipeline effective config** (resolved `memory.*` / `memory_hooks.*`). |
| `tapps-mcp validate-changed` | Run quality validation on changed files from the CLI (same as MCP tool). Options: `--quick` (default) or `--full`. |
| `tapps-mcp show-config` | Dump effective TappsMCP configuration as YAML (redacts secrets). |
| `tapps-mcp build-plugin` | Generate a Claude Code plugin directory with skills, agents, hooks, MCP config, and rules. |
| `tapps-mcp rollback` | Restore configuration files from a pre-upgrade backup. Use `--list` to see backups, `--backup-id` for a specific one. |
| `tapps-mcp validate-skills` | Validate SKILL.md frontmatter (name, description, allowed-tools). Options: `--path`, `--platform claude\|cursor\|both`. |
| `tapps-mcp auto-capture` | Extract durable facts from stdin (Stop hook JSON) and save to memory. Option: `--max-facts` (default: 5). |
| `tapps-mcp replace-exe` | Replace running exe with new version (Windows frozen exe only). |
| `tapps-mcp memory list` | List memories with optional `--tier`, `--scope`, `--json` filters. |
| `tapps-mcp memory save` | Save a memory entry (`--key`, `--value`, `--tier`, `--tags`). |
| `tapps-mcp memory get` | Retrieve a memory by `--key`. |
| `tapps-mcp memory search` | Full-text search (`--query`, `--limit`, `--json`). |
| `tapps-mcp memory delete` | Delete a memory by `--key`. |
| `tapps-mcp memory recall` | Search and output XML for auto-recall hook injection (`--query`, `--max-results`, `--min-score`). |
| `tapps-mcp memory import-file` | Import memories from JSON (`--file`, `--overwrite`). |
| `tapps-mcp memory export-file` | Export memories to JSON (`--file`). |
| `tapps-mcp lookup-docs` | Look up library docs from CLI (`--library`, `--topic`, `--mode code\|info`, `--raw`). |
| `tapps-mcp research` | **Deprecated (EPIC-94)** — prints deprecation notice. |
| `tapps-mcp consult-expert` | **Deprecated (EPIC-94)** — prints deprecation notice. |
| `tapps-mcp benchmark run` | Run AGENTBench evaluation (context modes: none/tapps/human/all). |
| `tapps-mcp benchmark analyze` | Analyze benchmark results with statistical comparison. |
| `tapps-mcp benchmark report` | Generate markdown/CSV benchmark reports. |
| `tapps-mcp benchmark tools report` | Generate tool effectiveness report. |
| `tapps-mcp benchmark tools rank` | Show tool impact rankings. |
| `tapps-mcp benchmark tools calibrate` | Data-driven checklist tier calibration. |
| `tapps-mcp template optimize` | Run template optimization pipeline (redundancy + ablation + promotion). |
| `tapps-mcp template ablate` | Section ablation analysis (identify harmful sections). |
| `tapps-mcp template compare` | Compare two template versions side-by-side. |
| `tapps-mcp template history` | Show template version history with scores. |

### `tapps-mcp init` options

| Option | Description |
|--------|-------------|
| `--host claude-code \| cursor \| vscode \| auto` | Target MCP client (default: auto-detect). |
| `--scope user \| project` | Config scope for Claude Code: `user` writes to `~/.claude.json`, `project` writes to `.mcp.json` (default: user). |
| `--engagement-level high \| medium \| low` | LLM engagement level for AGENTS.md and rules. **high** = MUST/REQUIRED language; **low** = optional (default: medium). |
| `--force` | Overwrite existing config without prompting. |
| `--check` | Verify only; no writes. Returns pass/fail for each generated file. |
| `--dry-run` | Preview what would be created without writing any files. |
| `--rules` / `--no-rules` | Generate platform rule files (default: yes). |
| `--project-root PATH` | Project root (default: current dir). |
| `--overwrite-tech-stack` | Overwrite existing TECH_STACK.md (default: skip if present). |
| `--with-docs-mcp` | Also register the docs-mcp server in the generated MCP config. |
| `--with-context7 KEY` | Write `TAPPS_MCP_CONTEXT7_API_KEY` to the env block (uses `${VAR}` interpolation). Pass `prompt` to be asked interactively. |
| `--uv` / `--no-uv` | Force or disable `uv run` style MCP config (default: auto-detect from `uv.lock` + `pyproject.toml`). |
| `--uv-extra NAME` | Optional-dependency group for `uv run --extra <name>` (default: auto-detect). |

**What `tapps-mcp init` creates:**

| File | Purpose |
|------|---------|
| **AGENTS.md** | AI assistant workflow guide — when to call each tool, recommended pipeline, troubleshooting. |
| **TECH_STACK.md** | Auto-detected project profile (type, frameworks, CI, tests, package managers). |
| **CLAUDE.md** or **.cursor/rules/** | Platform-specific pipeline rules for quality enforcement. |
| **.mcp.json** or **~/.claude.json** | MCP server configuration for your AI client. |
| **docs/TAPPS_HANDOFF.md** | Session handoff template for multi-session work. |
| **docs/TAPPS_RUNLOG.md** | Pipeline run log template. |
| **.claude/hooks/** or **.cursor/hooks/** | Hook scripts (quality gate on edit, memory capture on stop). |
| **.claude/agents/** or **.cursor/agents/** | Subagent definitions (reviewer, researcher, validator, review-fixer). |
| **.claude/skills/** or **.cursor/skills/** | Skill templates (score, gate, validate, review, research, memory, security). |
| **.claude/settings.json** | Claude Code permission wildcards + hooks config. |
| **.github/copilot-instructions.md** | VS Code Copilot tool guidance. |
| **.github/workflows/tapps-quality.yml** | CI quality gate workflow. |
| **.cursor/BUGBOT.md** | BugBot quality standards (Cursor only). |

**What `tapps_init` does (MCP tool):**

The MCP tool version has all CLI options plus additional parameters for fine-grained control:

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `platform` | str | `""` | Target platform: `"claude"`, `"cursor"`, `"vscode"`, or `""` for auto-detect. |
| `project_root` | str | `"."` | Project root directory. |
| `check` | bool | `false` | Verify only; no writes. |
| `force` | bool | `false` | Overwrite existing config without prompting. |
| `scope` | str | `"project"` | Config scope: `"user"` or `"project"`. |
| `rules` | bool | `true` | Generate platform rule files. |
| `dry_run` | bool | `false` | Preview without writing. |
| `engagement_level` | str | `null` | Override LLM engagement level. |
| `minimal` | bool | `false` | Minimal init: MCP config + AGENTS.md only (faster, ~5-15s vs 10-35s). |
| `create_handoff` | bool | `true` | Create docs/TAPPS_HANDOFF.md. |
| `create_runlog` | bool | `true` | Create docs/TAPPS_RUNLOG.md. |
| `create_agents_md` | bool | `true` | Create AGENTS.md. |
| `create_tech_stack_md` | bool | `true` | Create TECH_STACK.md. |
| `overwrite_platform_rules` | bool | `false` | Overwrite existing platform rules. |
| `overwrite_agents_md` | bool | `false` | Overwrite existing AGENTS.md. |
| `overwrite_tech_stack_md` | bool | `false` | Overwrite existing TECH_STACK.md. |
| `agent_teams` | bool | `false` | Generate Agent Teams hooks (Claude Code only). |
| `warm_cache_from_tech_stack` | bool | `true` | Pre-fetch docs for detected libraries. |
| `warm_expert_rag_from_tech_stack` | bool | `true` | Pre-build expert RAG indices for relevant domains. |
| `install_missing_checkers` | bool | `false` | Auto-install missing ruff/mypy/bandit/radon. |
| `scaffold_experts` | bool | `false` | Generate business expert scaffolding. |
| `include_karpathy` | bool | `true` | Append the vendored [Karpathy behavioral guidelines](https://github.com/forrestchang/andrej-karpathy-skills) (MIT) to AGENTS.md and CLAUDE.md between idempotent BEGIN/END markers — content outside the markers is preserved. Both files are append/update only, never replaced. Set to `false` to opt out. `tapps_upgrade` refreshes the block when the vendored SHA changes; `tapps_doctor` reports `ok`/`stale`/`missing` per file. |
| `mcp_config` | bool | `false` | Write MCP config file only (no other files). |
| `output_mode` | str | `"auto"` | `"auto"` (write or return), `"content_return"` (always return file content), `"direct_write"` (always write). |
| `verify_only` | bool | `false` | Check which external checkers are installed. |

**Settings notes:**
- `.claude/settings.json` (Claude Code): Auto-populated with denyList patterns (`Read(**/__pycache__/**)`, `Read(.venv/**)`, `Read(**/*.egg-info/**)`) to prevent reads of build artifacts, and `BASH_MAX_OUTPUT_LENGTH: 150000` to cap verbose output.
- Hook scripts (`.claude/hooks/tapps-session-start.sh`): Auto-generated to kill stale MCP processes (older than 2 hours) at session startup, preventing zombie process accumulation.

### `tapps-mcp upgrade`

After upgrading TappsMCP (`pip install -U tapps-mcp`), refresh generated files:

```bash
tapps-mcp upgrade                           # auto-detect host, update all files
tapps-mcp upgrade --host claude-code        # target a specific host
tapps-mcp upgrade --dry-run                 # preview changes without writing
tapps-mcp upgrade --force                   # overwrite even if up-to-date
tapps-mcp upgrade --scope user              # upgrade user-level config (~/.claude.json)
```

**What it updates:** AGENTS.md (via smart-merge), platform rules, hooks, agents, skills, and `.claude/settings.json` permissions. Custom command paths (e.g. PyInstaller exe) are never overwritten.

A **backup** is automatically created before overwriting files (stored in `.tapps-mcp/backups/`). Use `tapps-mcp rollback` to restore from the latest backup if an upgrade causes issues.

**From within an AI session (MCP tool):**

```
tapps_upgrade(dry_run=true)                 # Preview what would change
tapps_upgrade()                             # Apply updates
tapps_upgrade(platform="claude", force=true) # Force-update Claude Code files
```

### `tapps-mcp build-plugin`

Generate a Claude Code plugin directory for marketplace distribution:

```bash
tapps-mcp build-plugin                              # default output: ./tapps-mcp-plugin/
tapps-mcp build-plugin --output-dir ./my-plugin     # custom output directory
tapps-mcp build-plugin --engagement-level high       # high enforcement rules
```

Creates a complete plugin with `.claude-plugin/plugin.json` manifest, namespaced skills, agents, hooks, MCP config, rules, and settings.

### `tapps-mcp rollback`

Restore configuration files from a pre-upgrade backup:

```bash
tapps-mcp rollback                            # restore from latest backup
tapps-mcp rollback --list                     # list available backups
tapps-mcp rollback --backup-id 2026-03-02-153000  # restore specific backup
tapps-mcp rollback --dry-run                  # preview without restoring
```

Backups are stored in `.tapps-mcp/backups/` and auto-cleaned (keeping the 5 most recent).

### `tapps-mcp doctor`

Diagnoses common issues: missing dependencies, config problems, connectivity:

```bash
tapps-mcp doctor
tapps-mcp doctor --project-root /path/to/project
```

Checks: MCP config, AGENTS.md, Karpathy guidelines block freshness, `.claude/settings.json` permissions, hooks, installed checkers, tapps-brain, memory pipeline flags (informational), dual-memory-server warning.

---

## Tools reference

Quick index:

| Tool | One-line purpose |
|------|------------------|
| **tapps_session_start** | **FIRST call** — server info only (version, checkers, config). |
| **tapps_server_info** | Discover server version, tools, checkers, and recommended workflow. |
| **tapps_score_file** | Score a Python file 0–100 across 7 quality categories. |
| **tapps_quick_check** | Fast score + gate + basic security in one call after editing a file. |
| **tapps_security_scan** | Run Bandit + secret detection on a Python file. |
| **tapps_quality_gate** | Pass/fail a file against a quality preset (standard/strict/framework). |
| **tapps_validate_changed** | Score + gate + security scan all changed files (auto-detects via git diff). |
| **tapps_lookup_docs** | Fetch current documentation for a library (Context7 when key set, LlmsTxt fallback; cache). |
| **tapps_validate_config** | Validate Dockerfile, docker-compose, or infra configs. |
| **tapps_consult_expert** | **Deprecated (EPIC-94)** — returns structured deprecation error with alternatives. |
| **tapps_research** | **Deprecated (EPIC-94)** — returns structured deprecation error with alternatives. |
| **tapps_checklist** | See which tools were called this session and what is still missing. |
| **tapps_session_notes** | Save and retrieve key decisions and constraints across the session. Promotable to shared memory. |
| **tapps_memory** | Shared memory — **33 actions**: CRUD (`save`, `save_bulk`, `get`, `list`, `delete`), `search`, intelligence (`reinforce`, `gc`, `contradictions`, `reseed`), consolidation, import/export, federation (6), `index_session`, `validate`, `maintain`, security (`safety_check`, `verify_integrity`), profiles (3), `health`, Hive/Agent Teams (`hive_status`, `hive_search`, `hive_propagate`, `agent_register`). See [MEMORY_REFERENCE.md](docs/MEMORY_REFERENCE.md). |
| **tapps_impact_analysis** | Analyze the impact of changes on the codebase (imports, dependents). |
| **tapps_report** | Generate a quality report (JSON, Markdown, or HTML) for scored files. |
| **tapps_dashboard** | View metrics dashboard with execution stats, expert performance, and trends. |
| **tapps_stats** | Retrieve aggregated usage statistics and quality trends across sessions. |
| **tapps_feedback** | Submit feedback on tool results to improve adaptive scoring and expert answers. |
| **tapps_dead_code** | Scan Python files for dead code — supports file, project-wide, or changed-files-only scanning with confidence scoring. |
| **tapps_dependency_scan** | Scan project dependencies for known vulnerabilities (pip-audit). |
| **tapps_dependency_graph** | Build import graph, detect circular imports, and calculate coupling metrics. |
| **tapps_init** | Bootstrap TappsMCP in a project: create AGENTS.md, TECH_STACK.md, platform rules, hooks, agents, skills. See [init options](#tapps-mcp-init-options). |
| **tapps_set_engagement_level** | Set LLM engagement level (high/medium/low) in `.tapps-mcp.yaml`; then run init with overwrite to apply. |
| **tapps_upgrade** | Validate and refresh all generated files (AGENTS.md, rules, hooks) after upgrading TappsMCP. Creates backup first. |
| **tapps_doctor** | Diagnose configuration, rules, hooks, connectivity, tapps-brain, and **memory pipeline effective config**; reports `llm_engagement_level` when set. |
| **tapps_workflow** | *(MCP prompt, not a tool)* Recommended tool call order for a specific task type. |

---

### tapps_session_start

**What it does:** Returns server info only: version, configuration, installed checkers, diagnostics, quick_start, and pipeline. This is the **required first call** in every session.

**Why use it:** Initializes the session with server capabilities so you know which checkers are available and the recommended workflow. Kept lightweight (~1s).

---

### tapps_server_info

**What it does:** Returns server metadata: name, version, MCP protocol version, project root, quality preset, and log level. Lists all available tool names and the status of external checkers (ruff, mypy, bandit, radon)—installed or not, with version or install hint. Also returns a short **`recommended_workflow`** string describing when to call which tools.

**Why use it:** Call once at session start so the AI (and any host) knows what this server can do, which checkers are available (and whether scoring will be degraded), and the intended workflow. Avoids guessing and ensures the rest of the session uses TappsMCP effectively.

---

### tapps_score_file

**What it does:** Scores a single Python file from 0–100 using up to seven categories: complexity (cyclomatic complexity), security (Bandit + heuristics), maintainability (maintainability index), test coverage (heuristic from test file presence), performance (nesting, loop size), structure (project layout), and developer experience (docs, tooling). Can run in **quick** mode (ruff-only, under ~500 ms) or full mode (ruff, mypy, bandit, radon in parallel). Optional **fix** mode (with quick) runs ruff with auto-fix before scoring. Supports three execution **modes**: `"auto"` (default, subprocess with fallback), `"subprocess"` (async subprocess only), or `"direct"` (radon as library, sync subprocess in thread pool - avoids async subprocess reliability issues in MCP contexts). Returns per-category scores, weights, details, actionable suggestions, and up to 20 lint/type/security issues. Sets `degraded: true` when some checkers are missing and fallbacks are used.

**Why use it:** Gives an objective, repeatable quality signal instead of subjective "looks good." Use quick mode during edit-lint-fix loops for fast feedback; use full mode before considering work complete. Use `mode="direct"` if you encounter subprocess reliability issues in your MCP host. The structured output is easy for the AI to interpret and act on (e.g. fix specific line numbers, follow actionable suggestions). Ensures quality is measured the same way regardless of model or prompt.

---

### tapps_security_scan

**What it does:** Runs a security-focused scan on a Python file: Bandit for common vulnerability patterns (e.g. SQL injection, hardcoded passwords, unsafe deserialization) and optional secret detection for API keys, tokens, and credentials. Returns counts by severity (critical, high, medium, low), lists of findings with location and message, and redacted context so sensitive snippets are not echoed. Indicates whether Bandit was available; if not, the response is marked degraded.

**Why use it:** Security issues are easy to introduce and hard to catch by eye. A dedicated scan surfaces real findings with severity so the AI (or human) can fix critical/high items first. Use when touching auth, I/O, or third-party integrations, or before any security-sensitive review. Redaction keeps secrets out of logs and context.

---

### tapps_quality_gate

**What it does:** Evaluates a Python file against a configurable quality preset. Runs full scoring (same as `tapps_score_file` full mode) then compares the result to thresholds for that preset: **standard** (e.g. overall ≥ 70), **strict** (e.g. ≥ 80), **framework** (e.g. ≥ 75 with higher bar on security). Returns pass/fail, overall score, per-category scores, thresholds used, and lists of failures and warnings with clear messages.

**Why use it:** Defines "good enough" in one place so work is not declared done until the bar is met. Prevents the AI from saying "done" when the file would fail CI or team standards. Call before marking a task complete; if it fails, the response tells you what to improve. Presets let different projects or roles use different strictness without changing prompts.

---

### tapps_quick_check

**What it does:** Runs a quick score + quality gate + basic security check on a single Python file in one fast call. Combines what would otherwise be three separate tool calls into one. For thorough multi-file validation, use `tapps_validate_changed` instead.

**Why use it:** The fastest way to check a file after editing. Use after every edit to catch quality regressions immediately. Skipping means issues accumulate until the final validation step.

---

### tapps_validate_changed

**What it does:** Detects changed Python files (via `git diff` against a base ref) or accepts an explicit comma-separated list. Default is `quick=True` (ruff-only scoring, under ~10s). Pass `quick=False` for full validation (ruff, mypy, bandit, radon). Includes impact analysis by default (`include_impact=True`) showing blast radius of changes. The `security_depth` parameter controls security scanning: `"basic"` (default) runs basic checks, `"full"` runs bandit + secret detection even in quick mode. Returns per-file results with pass/fail status, impact summary, and aggregated summary.

**Why use it:** Required before declaring multi-file work complete. Auto-detects what changed so you don't have to specify each file. Ensures no changed file slips through without quality validation. Impact analysis helps understand downstream effects of changes.

---

### tapps_lookup_docs

**What it does:** Fetches current documentation for a given library (e.g. FastAPI, React, SQLAlchemy). Uses Context7 when `TAPPS_MCP_CONTEXT7_API_KEY` is set; otherwise falls back to LlmsTxt (always available). Resolves the library name via fuzzy matching, checks a local cache first, and on cache miss fetches from the active provider. Accepts an optional **topic** (e.g. "routing", "hooks") and **mode** ("code" for API-style docs, "info" for conceptual). All returned content is checked for prompt-injection patterns before being returned. Response includes source (cache vs API), cache hit flag, and optional token estimate.

**Why use it:** LLMs often hallucinate library APIs or use outdated signatures. Looking up real docs right before writing or fixing code reduces wrong method names, wrong parameters, and deprecated usage. Use it before implementing or refactoring code that depends on an external library. Cache keeps repeated lookups fast and allows offline use when the API key is not set.

---

### tapps_validate_config

**What it does:** Validates a configuration or infrastructure file against best-practice rules. Supports **Dockerfile** (e.g. non-root user, pinning versions, multi-stage usage), **docker-compose** (e.g. resource limits, env handling), and code/config containing **WebSocket**, **MQTT**, or **InfluxDB** patterns. You pass a file path and optionally a **config_type**; with `auto`, the type is inferred from path and content. Returns valid/invalid, a list of findings with severity (critical, warning), and optional suggestions.

**Why use it:** Misconfigured Docker or infra leads to security and reliability issues that are easy to miss. This tool gives deterministic, rule-based feedback so the AI (or human) can fix problems before merge or deploy. Use when adding or changing Dockerfiles, docker-compose files, or the supported config patterns so the result matches team and operational standards.

---

### tapps_consult_expert (deprecated)

**Status:** Deprecated since EPIC-94. Returns a structured `TOOL_DEPRECATED` error with `alternatives` pointing to `tapps_lookup_docs` (for documentation) and AgentForge (for expert consultation).

**Migration:** Use `tapps_lookup_docs` for library documentation lookup. The RAG-based expert system has been removed.

---

### tapps_research (deprecated)

**Status:** Deprecated since EPIC-94. Returns a structured `TOOL_DEPRECATED` error with `alternatives` pointing to `tapps_lookup_docs` and AgentForge.

**Migration:** Use `tapps_lookup_docs` for library documentation lookup.

---

### tapps_checklist

**What it does:** Tracks which TappsMCP tools have been called in the current server session and evaluates that against a **task type**: `feature`, `bugfix`, `refactor`, `security`, or `review`. For that task type, some tools are required, some recommended, some optional. The tool returns the list of called tools, missing required/recommended/optional tools, and for each missing tool a short **reason** (in `missing_required_hints`, `missing_recommended_hints`, `missing_optional_hints`) explaining why to call it. It also returns a **complete** flag (true when all required tools have been called) and total call count. When `auto_run=True`, the tool automatically runs any missing required validations (via `tapps_validate_changed`) and re-evaluates the checklist.

**Why use it:** Ensures the AI does not skip important steps (e.g. never running the quality gate or security scan) before declaring work complete. Call before saying "done"; if `complete` is false, the hints tell you exactly which tools to call and why. Use `auto_run=True` to let the checklist fill in missing steps automatically. Task types align expectations (e.g. security tasks require a security scan) so the checklist matches the kind of work being done.

---

### tapps_session_notes

**What it does:** Persists key decisions, constraints, and context across a session. Supports **save** (store a note with category and optional tags), **get** (retrieve notes, optionally filtered by category), **list**, **clear**, and **promote** (copy a note to persistent shared memory via `tapps_memory`). Notes survive within a server session and are stored in `.tapps-mcp/session/`. Responses include a `migration_hint` suggesting `tapps_memory` for cross-session persistence.

**Why use it:** In long sessions, the AI may forget decisions made earlier. Session notes let the AI save constraints ("user wants sync-only, no async") and retrieve them later so earlier context is not lost. Use `promote` to persist important notes to shared memory so they survive across sessions. For new projects, prefer `tapps_memory` directly for persistent storage.

---

### tapps_memory

**What it does:** Persistent, project-scoped shared memory (tapps-brain, SQLite WAL + FTS5 at `{project_root}/.tapps-mcp/memory/memory.db`). Tiers: **architectural**, **pattern**, **procedural**, **context** with configurable half-lives. **33 actions** (single tool, `action=` dispatch): CRUD (**save**, **save_bulk**, **get**, **list**, **delete**), **search**, **reinforce**, **gc**, **contradictions**, **reseed**, **consolidate** / **unconsolidate**, **import** / **export**, six **federate_***, **index_session**, **validate**, **maintain**, **safety_check**, **verify_integrity**, **profile_info** / **profile_list** / **profile_switch**, **health**, and Hive / Agent Teams (**hive_status**, **hive_search**, **hive_propagate**, **agent_register**). With default config, **architectural** **save** may **supersede** the active version chain (`store.supersede`) instead of overwriting in place. Shipped defaults also enable expert/research auto-save, recurring `tapps_quick_check` procedural memory, **tapps_impact_analysis** `memory_context`, and **memory_hooks** auto-recall/auto-capture — all overridable in `.tapps-mcp.yaml`. Cap: **1500** entries per project (auto-GC near capacity). Full list: [docs/MEMORY_REFERENCE.md](docs/MEMORY_REFERENCE.md).

**Why use it:** Agents start every session without project context unless you persist it. Shared memory holds decisions, patterns, and workflows across sessions, with decay and contradiction checks to reduce stale answers. Expert and research tools can pull in relevant memories automatically when enabled.

---

### tapps_impact_analysis

**What it does:** Analyzes a Python file to determine its blast radius. Builds an import graph, identifies direct dependents (files that import the changed file), transitive dependents (multi-hop), and affected test files. Returns severity assessment, total affected count, and recommendations. When `memory.enabled` and `memory.enrich_impact_analysis` are true, includes **`memory_context`** from a project-relative memory search. Accepts an optional `change_type` parameter (`"added"`, `"modified"`, or `"removed"`) to adjust severity assessment.

**Why use it:** Before modifying a file, understand what else could break. Use when refactoring, renaming, or changing public APIs so the AI knows which downstream files may need updates.

---

### tapps_report

**What it does:** Generates a quality report for one or more scored files. Supports **json**, **markdown**, and **html** output formats. Combines scoring results, gate results, and optional metadata into a single structured report.

**Why use it:** Produces a human-readable summary of quality analysis. Use after scoring and gating to give the user a clear, formatted overview of code quality status.

---

### tapps_upgrade

**What it does:** Validates and refreshes all TappsMCP-generated files in a project after upgrading the server. Detects the platform (Claude Code, Cursor, or both) from existing config files and upgrades AGENTS.md (via smart-merge), platform rules, hooks, agents, skills, and settings. Uses `upgrade_mode` internally so custom command paths (e.g. PyInstaller exe) are never overwritten. Accepts optional `platform`, `force`, and `dry_run` parameters.

**Why use it:** After upgrading TappsMCP (`pip install -U tapps-mcp`), generated files may be outdated — missing new tools, stale hook scripts, or old AGENTS.md sections. Call `tapps_upgrade(dry_run=true)` to preview what would change, then `tapps_upgrade()` to apply updates. A backup is automatically created before overwriting (stored in `.tapps-mcp/backups/`). This is the MCP-tool equivalent of the `tapps-mcp upgrade` CLI command, usable from within an AI session without dropping to a terminal.

---

### tapps_set_engagement_level

**What it does:** Writes `llm_engagement_level` (`high`, `medium`, or `low`) to the project `.tapps-mcp.yaml`, merging with existing keys. Validates the level and returns success or an error message. Does not regenerate AGENTS.md or platform rules; run `tapps_init(overwrite_agents_md=True)` (or `tapps-mcp init --engagement-level <level>`) afterward to apply the new level to generated content.

**Why use it:** When the user asks to make TappsMCP stricter or more relaxed (e.g. "set tappsmcp to high"), call this tool then re-run init so AGENTS.md, platform rules, hooks, and checklist requirements reflect the chosen engagement level.

---

### tapps_doctor

**What it does:** Runs diagnostic checks and returns structured results: MCP configs (Claude / Cursor / VS Code), AGENTS.md, rules, hooks, permissions, optional quality-tool versions, tapps-brain import, **Memory pipeline (effective config)** (resolved `memory.*` and `memory_hooks.*` flags), and dual-memory-server warning. When `llm_engagement_level` is set in `.tapps-mcp.yaml`, the result includes that key. Returns per-check pass/fail, remediation hints, `pass_count`, `fail_count`, `all_passed`.

**Why use it:** When tools misbehave (permissions, missing checkers, split-brain memory servers), run `tapps_doctor()` to see what to fix. The memory row confirms which automatic memory features are active for the project.

---

### tapps_dead_code

**What it does:** Scans Python code for unused functions, classes, imports, and variables using Vulture (with AST fallback when Vulture is not installed). The `scope` parameter controls what is scanned: `"file"` (default) scans a single file specified by `file_path`, `"project"` scans all Python files in the project, and `"changed"` scans only files with uncommitted changes (via git diff). The `min_confidence` parameter (0-100, default 80) filters findings by confidence threshold. Returns a findings list with location, type, name, and confidence for each item, plus `files_scanned` count and `degraded` flag when Vulture is missing.

**Why use it:** Dead code accumulates silently and increases maintenance burden. Use during refactoring to identify safe removal candidates, or with `scope="changed"` before committing to ensure new changes do not introduce unused code. The confidence scoring helps prioritize which findings to act on.

---

### tapps_dashboard

**What it does:** Generates a comprehensive metrics dashboard covering scoring accuracy, gate pass rates, expert effectiveness, cache performance, quality trends, and alerts. The `time_range` parameter (`"1d"`, `"7d"`, `"30d"`, `"90d"`) filters the underlying data to the specified window. Supports `output_format` of `"json"` (default), `"markdown"`, `"html"`, or `"otel"`. The optional `sections` parameter lets you request specific dashboard sections (e.g. `["summary", "alerts", "recommendations"]`).

**Why use it:** Provides visibility into how TappsMCP is performing across sessions. Use to identify patterns (e.g. consistently failing quality gates, low cache hit rates) and act on recommendations to improve the development workflow.

---

### tapps_stats

**What it does:** Returns aggregated usage statistics for TappsMCP tools: call counts, success rates, average durations, cache hit rates, and gate pass rates. Filterable by `tool_name` (optional) and `period` (`"session"`, `"1d"`, `"7d"`, `"30d"`, `"all"`). The response includes a `recommendations` list with actionable suggestions based on usage patterns (e.g. "consider using tapps_quick_check more frequently during edits").

**Why use it:** Helps understand tool adoption and identify workflow gaps. The recommendations surface specific improvements based on actual usage data rather than generic advice.

---

### tapps_feedback

**What it does:** Submits feedback on whether a tool's output was helpful. Requires `tool_name` and `helpful` (boolean), with optional `context` for details. Validates `tool_name` against known tools and returns an error with the valid tool list for invalid names. Deduplicates identical feedback within 5 minutes to prevent noise. For scoring tools, feedback adjusts adaptive weights in real-time so subsequent scoring reflects what the user finds useful.

**Why use it:** Closes the feedback loop so TappsMCP improves over time. When a tool gives unhelpful results, reporting it adjusts internal weights. When results are helpful, it reinforces the current behavior. Use after any tool call where the output was notably good or bad.

---

### Scoring categories (tapps_score_file)

| Category | Weight | Description |
|----------|--------|-------------|
| complexity | 0.18 | Cyclomatic complexity (radon cc / AST fallback) |
| security | 0.27 | Bandit + pattern heuristics |
| maintainability | 0.24 | Maintainability index (radon mi / AST fallback) |
| test_coverage | 0.13 | Heuristic from matching test file existence |
| performance | 0.08 | AST: nested loops, large functions, deep nesting |
| structure | 0.05 | Project layout (pyproject.toml, tests/, README, .git) |
| devex | 0.05 | Developer experience (docs, AGENTS.md, tooling config) |

When ruff/mypy/bandit/radon are missing, the server uses AST-based fallbacks and reports `degraded: true` in the response.

---

## Configuration

### Project config (optional)

Create **`.tapps-mcp.yaml`** in the **project root** you want the AI to analyze:

```yaml
quality_preset: standard   # standard | strict | framework
log_level: INFO            # DEBUG | INFO | WARNING | ERROR
log_json: false            # JSON-structured logs
tool_timeout: 30           # Subprocess timeout in seconds
cache_max_mb: 100          # Knowledge cache max size in MB (LRU eviction)
llm_engagement_level: medium  # high | medium | low
dead_code_min_confidence: 80           # Minimum vulture confidence (0-100)
dead_code_whitelist_patterns: ["test_*", "conftest.py"]  # File patterns to exclude
```

Custom scoring weights (these are the defaults — adjust to your project's priorities):

```yaml
scoring_weights:
  complexity: 0.18
  security: 0.27
  maintainability: 0.24
  test_coverage: 0.13
  performance: 0.08
  structure: 0.05
  devex: 0.05
```

### Shared memory

Configure the persistent memory system. Shipped defaults are **POC-oriented** (integrations on); set any flag to `false` to quiet behavior.

```yaml
memory:
  enabled: true
  gc_enabled: true
  contradiction_check_on_start: true
  max_memories: 1500
  inject_into_experts: true
  auto_save_quality: true              # Expert / research → pattern-tier memory
  track_recurring_quick_check: true    # Repeated gate failures → procedural memory
  recurring_quick_check_threshold: 3
  enrich_impact_analysis: true         # tapps_impact_analysis memory_context
  auto_supersede_architectural: true   # Architectural save uses supersede / history
  decay:
    architectural_half_life_days: 180
    pattern_half_life_days: 60
    context_half_life_days: 14
    confidence_floor: 0.1

memory_hooks:
  auto_recall:
    enabled: true
    max_results: 5
    min_score: 0.3
  auto_capture:
    enabled: true
    max_facts: 5
```

Memory data lives under `{project_root}/.tapps-mcp/memory/`. Add `.tapps-mcp/` to `.gitignore` if you do not want local state in git. Run `tapps-mcp doctor` to see **Memory pipeline (effective config)** for your project.

### LLM Engagement Level

Control how strongly the AI is prompted to use TappsMCP tools: **high** (mandatory), **medium** (balanced), or **low** (optional). Set in `.tapps-mcp.yaml` or via `TAPPS_MCP_LLM_ENGAGEMENT_LEVEL`:

```yaml
llm_engagement_level: medium   # high | medium | low
```

- **high** — AGENTS.md and platform rules use MUST/REQUIRED language; checklist requires more tools; hooks use strong reminders.
- **medium** — Balanced (default). Recommended workflow and standard required tools.
- **low** — Softer “consider” language; fewer required tools; optional reminders.

To change the level at runtime, use the **`tapps_set_engagement_level(level)`** MCP tool (e.g. when the user says “set tappsmcp to high”). Then run `tapps_init` with `overwrite_agents_md=True` to regenerate AGENTS.md and platform rules with the new level. From the CLI: `tapps-mcp init --engagement-level high` (or `medium` / `low`).

### Environment variables

| Variable | Description |
|----------|-------------|
| **TAPPS_MCP_PROJECT_ROOT** | Restrict file operations to this directory (recommended for security). If unset, current working directory is used. |
| **TAPPS_MCP_HOST_PROJECT_ROOT** | Optional. Host path mapping for Docker/remote setups. When set, absolute paths from the IDE are mapped to the project root. |
| **TAPPS_MCP_CONTEXT7_API_KEY** | Optional. Used by `tapps_lookup_docs` for live Context7 API fetches; cache still works without it. |
| **TAPPS_MCP_QUALITY_PRESET** | Override quality preset (`standard`, `strict`, `framework`). Default: `standard`. |
| **TAPPS_MCP_LOG_LEVEL** | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). Default: `INFO`. |
| **TAPPS_MCP_DEAD_CODE_MIN_CONFIDENCE** | Minimum confidence for dead code findings (0–100). Default: `80`. |
| **TAPPS_MCP_DEAD_CODE_WHITELIST_PATTERNS** | Comma-separated file patterns to exclude (fnmatch). Default: `test_*,conftest.py`. |
| **TAPPS_MCP_LLM_ENGAGEMENT_LEVEL** | Override engagement level (`high`, `medium`, `low`) for template language and checklist. Default: `medium`. |

---

## Optional tool dependencies

Best results come with these tools installed; the server degrades gracefully without them.

| Tool | Purpose | Install |
|------|---------|--------|
| ruff | Linting + formatting | `pip install ruff` or `uv add ruff` |
| mypy | Type checking | `pip install mypy` or `uv add mypy` |
| bandit | Security scanning | `pip install bandit` or `uv add bandit` |
| radon | Complexity + maintainability | `pip install radon` or `uv add radon` |
| vulture | Dead code detection | `pip install vulture` or `uv add vulture` |
| pip-audit | Dependency vulnerability scanning | `pip install pip-audit` or `uv add pip-audit` |

**Vector RAG (optional):** For semantic search over memory entries, install the `rag` extras:

```bash
pip install tapps-mcp[rag]   # or: uv add tapps-mcp[rag]
```

This adds `faiss-cpu`, `sentence-transformers`, and `numpy`. When not installed, the memory system uses keyword-based search (no configuration needed).

---

## Docker

### Docker Compose (HTTP transport)

Run TappsMCP as a local HTTP MCP server:

```bash
docker compose up --build -d
```

- **Endpoint:** http://localhost:8000 (MCP at `/mcp`)
- **Env:** `TAPPS_MCP_PROJECT_ROOT`, `TAPPS_MCP_QUALITY_PRESET`, etc. (see [docs/DOCKER_DEPLOYMENT.md](docs/DOCKER_DEPLOYMENT.md))

Verification:

```bash
docker compose ps
docker compose logs --tail 20
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/
```

### Docker images (GHCR)

Pre-built multi-arch images are published on every release:

```bash
docker pull ghcr.io/wtthornton/tapps-mcp:latest
docker pull ghcr.io/wtthornton/docs-mcp:latest

# Run TappsMCP (stdio, mount current dir)
docker run -v $(pwd):/workspace ghcr.io/wtthornton/tapps-mcp:latest           # Linux / macOS
docker run -v %cd%:/workspace ghcr.io/wtthornton/tapps-mcp:latest             # Windows (cmd)
docker run -v ${PWD}:/workspace ghcr.io/wtthornton/tapps-mcp:latest           # Windows (PowerShell)

# Run with HTTP transport
docker run -p 8000:8000 -v $(pwd):/workspace ghcr.io/wtthornton/tapps-mcp:latest tapps-mcp serve --transport http --host 0.0.0.0 --port 8000
```

See [docs/DOCKER_MCP_TOOLKIT.md](docs/DOCKER_MCP_TOOLKIT.md) for Docker image distribution details.

---

## Bootstrapping TappsMCP in your project

Once TappsMCP is installed and your AI client is connected, use the `tapps_init` MCP tool to bootstrap quality infrastructure in your project:

```
tapps_init(platform="claude")      # or platform="cursor"
```

This creates:

| File | Purpose |
|------|---------|
| **AGENTS.md** | AI assistant workflow guide (when to call each tool) |
| **TECH_STACK.md** | Auto-detected project profile (type, frameworks, CI, tests) |
| **CLAUDE.md** or **.cursor/rules/** | Platform-specific pipeline rules |
| **docs/TAPPS_HANDOFF.md** | Session handoff template |
| **docs/TAPPS_RUNLOG.md** | Pipeline run log template |
| **.claude/hooks/** or **.cursor/hooks/** | Platform hook scripts (quality gate enforcement) |
| **.claude/agents/** or **.cursor/agents/** | Subagent definitions (reviewer, researcher, validator) |
| **.claude/skills/** or **.cursor/skills/** | Skill templates (score, gate, validate) |
| **.claude/settings.json** | Claude Code permission wildcard + hooks config |
| **.cursor/rules/*.mdc** | Cursor rules (always, auto-attach, agent-requested) |
| **.github/copilot-instructions.md** | VS Code Copilot tool guidance |
| **.github/workflows/tapps-quality.yml** | CI quality gate workflow |
| **.cursor/BUGBOT.md** | BugBot quality standards (Cursor only) |

Key optional flags (see [init options](#tapps-mcp-init-options) for the full list):

- `warm_cache_from_tech_stack=True` — pre-fetch docs for detected libraries (default: on)
- `warm_expert_rag_from_tech_stack=True` — pre-build domain indices for relevant tech stack (default: on)
- `install_missing_checkers=True` — auto-install missing ruff/mypy/bandit/radon
- `agent_teams=True` — generate Agent Teams hooks for quality watchdog teammate (Claude Code only)
- `minimal=True` — minimal init: MCP config + AGENTS.md only (faster, ~5-15s vs 10-35s)
- `scaffold_experts=True` — generate business expert scaffolding (knowledge dir + registry template)
- `output_mode="content_return"` — return file content instead of writing (for Docker environments)

After upgrading TappsMCP, run `tapps-mcp upgrade` to refresh all generated files, or re-run `tapps_init` with `overwrite_agents_md=True` and `overwrite_platform_rules=True`. See [Upgrading](#upgrading) and [docs/UPGRADE_FOR_CONSUMERS.md](docs/UPGRADE_FOR_CONSUMERS.md).

---

## Upgrading

When you upgrade TappsMCP, generated files (AGENTS.md, hooks, rules, skills) may need refreshing.

### Quick upgrade (recommended)

```bash
pip install -U tapps-mcp                    # 1. Upgrade the package
tapps-mcp upgrade --dry-run                 # 2. Preview what would change
tapps-mcp upgrade                           # 3. Apply updates
```

A **backup** is automatically created before overwriting files. Use `tapps-mcp rollback` to restore if needed:

```bash
tapps-mcp rollback --list                   # List available backups
tapps-mcp rollback                          # Restore from latest backup
tapps-mcp rollback --backup-id <timestamp>  # Restore specific backup
```

### Fine-grained control

| What to refresh | How |
|-----------------|-----|
| AGENTS.md (workflow, tool hints) | `tapps_init(overwrite_agents_md=True)` |
| Platform rules (CLAUDE.md, .cursor/rules) | `tapps_init(overwrite_platform_rules=True, platform="claude")` |
| TECH_STACK.md, caches, RAG indices | `tapps_init()` (default run refreshes these) |
| MCP host config | `tapps-mcp init --force` |
| Engagement level | `tapps_set_engagement_level("high")` then `tapps_init(overwrite_agents_md=True)` |

See [docs/UPGRADE_FOR_CONSUMERS.md](docs/UPGRADE_FOR_CONSUMERS.md) for the full upgrade guide.

---

## Architecture

### Package dependency graph

```
tapps-brain (standalone library)
    ^
    |
tapps-core (shared infrastructure)
    ^              ^
    |              |
tapps-mcp      docs-mcp
(26 tools)     (32 tools)
```

**[tapps-brain](https://github.com/wtthornton/tapps-brain)** is a standalone memory system extracted from tapps-core. It provides SQLite-backed persistence, BM25 retrieval, time-based decay, contradiction detection, consolidation, federation, and garbage collection. It has its own release cycle and test suite (521+ tests).

**tapps-core** provides shared infrastructure (config, security, logging, knowledge, metrics, adaptive). Its `memory/` package contains thin re-export shims that delegate to tapps-brain for backward compatibility (`from tapps_core.memory.store import MemoryStore` still works). The one exception is `injection.py`, which is a bridge adapter that translates TappsMCP settings into tapps-brain's `InjectionConfig`.

**tapps-mcp** and **docs-mcp** are MCP servers that depend on tapps-core. tapps-mcp also re-exports from tapps-core for backward compat with consuming projects.

### Memory subsystem

The memory system is implemented by tapps-brain and exposed via **33 actions** on the `tapps_memory` MCP tool (see [docs/MEMORY_REFERENCE.md](docs/MEMORY_REFERENCE.md)):

| Tier | Half-life | Use for |
|------|-----------|---------|
| `architectural` | 180 days | Design decisions, API contracts, system boundaries |
| `pattern` | 60 days | Recurring code patterns, domain conventions |
| `procedural` | 30 days | Build commands, deployment steps, workflow |
| `context` | 14 days | Sprint goals, current focus, temporary state |

Features: BM25 ranked retrieval (stemming + stop words), time-based confidence decay, contradiction detection, auto-consolidation, federation across projects, garbage collection, import/export (JSON + Markdown).

> **Deprecation notice:** `tapps_core.memory.*` imports still work but emit a `DeprecationWarning`. Prefer importing from `tapps_brain.*` directly in new code.

For the full architecture reference, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Development

This is a **uv workspace monorepo** with four packages. All commands run from the **repository root**.

```bash
# Install all packages (tapps-core, tapps-mcp, docs-mcp)
uv sync --all-packages

# Run tests per package (recommended - avoids conftest collisions)
uv run pytest packages/tapps-core/tests/ -v      # tapps-core (960+ tests)
uv run pytest packages/tapps-mcp/tests/ -v        # tapps-mcp (3,790+ tests)
uv run pytest packages/docs-mcp/tests/ -v         # docs-mcp  (2,170+ tests)

# Run a single test file
uv run pytest packages/tapps-mcp/tests/unit/test_scorer.py -v

# Coverage
uv run pytest packages/tapps-mcp/tests/ --cov=tapps_mcp --cov-report=term-missing

# Type checking
uv run mypy --strict packages/tapps-mcp/src/tapps_mcp/
uv run mypy --strict packages/tapps-core/src/tapps_core/

# Linting
uv run ruff check packages/*/src/
uv run ruff format --check packages/*/src/
```

If you see `ModuleNotFoundError`, run `uv sync --all-packages` first.

Pre-commit hooks are configured (`.pre-commit-config.yaml`). CI runs on push/PR to `master`/`main` (lint + tests on Ubuntu, Windows, macOS x Python 3.12, 3.13).

### Cross-platform notes

TappsMCP runs on **Linux, macOS, and Windows**. Platform-specific behavior:

| Area | Linux / macOS | Windows |
|------|---------------|---------|
| **Path handling** | Forward slashes, `pathlib.Path` | Forward or backslashes, drive letter normalization (`c:` -> lowercase) |
| **Hook scripts** | `.sh` files run natively | `.sh` files require Git Bash; `tapps_doctor` warns if misconfigured |
| **Virtual env activation** | `source .venv/bin/activate` | `.venv\Scripts\activate` (cmd) or `.venv/Scripts/activate` (Git Bash) |
| **Docker volume mounts** | `$(pwd):/workspace` | `%cd%:/workspace` (cmd) or `${PWD}:/workspace` (PowerShell) |
| **Exe replacement** | Not applicable | `tapps-mcp replace-exe` for frozen exe updates |
| **Timeout tests** | Standard `sleep` / `timeout` | Use `python -c "import time; time.sleep(N)"` (Git Bash intercepts `timeout`) |

---

## Project layout

This is a **uv workspace monorepo** with three packages under `packages/` plus the standalone [tapps-brain](https://github.com/wtthornton/tapps-brain) library:

```
packages/
├── tapps-core/                        # Shared infrastructure library (no MCP tools)
│   └── src/tapps_core/
│       ├── common/                    # Exceptions, logging, shared models, utilities
│       ├── config/                    # Settings, default.yaml
│       ├── security/                  # Path validation, IO guardrails, secrets, governance
│       ├── prompts/                   # Workflow prompt templates
│       ├── knowledge/                 # Context7 client, cache, lookup, warming, RAG safety,
│       │                              #   Context7 + LlmsTxt providers (providers/)
│       ├── experts/                   # Domain detector, engine, RAG, 174 knowledge files
│       ├── memory/                    # Re-export shims delegating to tapps-brain
│       │                              #   (injection.py is a bridge adapter)
│       ├── metrics/                   # Collector, dashboard, alerts, trends, OTel export
│       └── adaptive/                  # Adaptive scoring, expert voting, weight distribution
│
├── tapps-mcp/                         # Code quality MCP server (26 tools)
│   └── src/tapps_mcp/
│       ├── server.py, cli.py          # Entry points and MCP server
│       ├── server_*.py                # Tool modules (scoring, pipeline, metrics, memory, analysis)
│       ├── scoring/                   # Score model, scorer, dead code, dependency security
│       ├── gates/                     # Gate presets, evaluator
│       ├── tools/                     # Ruff, mypy, bandit, radon, vulture, pip-audit, checklist
│       ├── validators/                # Dockerfile, docker-compose, WebSocket, MQTT, InfluxDB
│       ├── project/                   # Project profiling, session notes, impact analysis
│       ├── benchmark/                 # Benchmark infrastructure (AGENTBench, template optimization, tool effectiveness)
│       ├── distribution/              # Setup generator (init, upgrade, doctor)
│       ├── pipeline/                  # Pipeline orchestration, platform generators
│       └── (re-exports)              # Backward-compatible re-exports from tapps-core
│
└── docs-mcp/                          # Documentation MCP server (32 tools)
    └── src/docs_mcp/
        ├── server.py, cli.py          # Entry points and MCP server
        ├── server_*.py                # Tool modules (helpers, analysis, git, validation, generation)
        ├── config/                    # DocsMCP-specific settings, default.yaml
        ├── extractors/               # Python, generic, docstring, type annotation extractors
        ├── analyzers/                # Module map, API surface, dependency, git history, diataxis
        ├── validators/               # Drift, completeness, link checker, freshness, diataxis, cross-refs
        ├── generators/               # README, changelog, release notes, API docs, ADR, guides, specs,
        │                             #   diagrams, interactive HTML, llms.txt, frontmatter, purpose, doc index
        └── integrations/             # TappsMCP integration

plugin/
└── cursor/                            # Ready-to-publish Cursor marketplace plugin
examples/
└── agent-sdk/                         # Claude Agent SDK integration examples (Python + TypeScript)
```

**External dependency:** [tapps-brain](https://github.com/wtthornton/tapps-brain) (`pip install tapps-brain`) provides the standalone memory system. It is a required dependency of tapps-core and is installed automatically.

**Backward compatibility:** `from tapps_mcp.config import load_settings` and `from tapps_core.memory.store import MemoryStore` still work - tapps-mcp re-exports from tapps-core, and tapps-core re-exports from tapps-brain. Existing consuming projects need no changes.

---

## DocsMCP (documentation server)

DocsMCP is a companion MCP server for documentation generation, drift detection, and maintenance. It shares infrastructure with TappsMCP via `tapps-core`.

### Tools (32)

#### Session & Configuration

| Tool | Description |
|------|-------------|
| `docs_session_start` | **FIRST call** — initialize session, detect project context, scan for existing docs. |
| `docs_project_scan` | Documentation state audit with completeness scoring and categorization. |
| `docs_config` | View or update DocsMCP configuration (`.docsmcp.yaml`). Actions: `view`, `set`. |

#### Code Analysis

| Tool | Description |
|------|-------------|
| `docs_module_map` | Build hierarchical module map with public API counts, docstrings, entry points. Supports Python, TypeScript, Go, Rust, Java. |
| `docs_api_surface` | Extract public API surface from a source file. Calculates doc coverage and reports missing docstrings. |
| `docs_git_summary` | Analyze git history: commits (conventional format), version boundaries from tags, contributor stats. |

#### Documentation Generation

| Tool | Description |
|------|-------------|
| `docs_generate_readme` | Generate or update README.md. Smart merge preserves human-written sections. Styles: minimal, standard, comprehensive. |
| `docs_generate_api` | Generate API reference from Python source. Formats: markdown, mkdocs, sphinx_rst. Includes usage examples from tests. |
| `docs_generate_changelog` | Generate CHANGELOG.md from git history. Formats: keep-a-changelog, conventional. |
| `docs_generate_release_notes` | Generate release notes for a specific version (or latest) with highlights, breaking changes, contributors. |
| `docs_generate_diagram` | Generate Mermaid, PlantUML, or D2 diagrams. Types: dependency, class_hierarchy, module_map, er_diagram, c4_context, c4_container, c4_component, sequence. D2 supports themes: default, sketch, terminal. |
| `docs_generate_architecture` | Generate comprehensive self-contained HTML architecture report with embedded SVG diagrams. |
| `docs_generate_adr` | Create Architecture Decision Records. Templates: MADR, Nygard. Auto-numbers from existing records. |
| `docs_generate_onboarding` | Generate developer onboarding guide with prerequisites, installation, project structure. |
| `docs_generate_contributing` | Generate CONTRIBUTING.md with development setup, coding standards, PR workflow. |
| `docs_generate_prd` | Generate Product Requirements Document with phased requirements and Gherkin acceptance criteria. |
| `docs_generate_prompt` | Generate LLM-facing prompt artifacts with purpose, task, context files, success criteria. |
| `docs_generate_epic` | Generate epic planning documents with stories, acceptance criteria, task breakdown, risk assessment. |
| `docs_generate_story` | Generate user story documents with "As a / I want / So that", sizing, and definition of done. |
| `docs_generate_llms_txt` | Generate llms.txt file (machine-readable project summary for AI). Modes: compact, full. |
| `docs_generate_frontmatter` | Add or update YAML frontmatter in markdown files. Auto-detects title, description, tags, Diataxis type. |
| `docs_generate_interactive_diagrams` | Generate interactive HTML page with Mermaid.js diagrams, pan/zoom, and diagram toggling. |
| `docs_generate_purpose` | Generate purpose/intent architecture template with design principles and quality attributes. |
| `docs_generate_doc_index` | Generate documentation index/map with categorized files and freshness indicators. |

> **Three-tier output (v1.17.0):** All generators use a write-first strategy. On writable filesystems, content is written to disk and only metadata is returned (saving context window). On read-only/Docker filesystems, small content (<20K) is inlined; large content uses `FileManifest` for client-side apply. All generators auto-compute a default `output_path` when omitted.

#### Validation & Checking

| Tool | Description |
|------|-------------|
| `docs_check_drift` | Detect documentation drift — code changes not reflected in docs. Reports undocumented additions and stale references. |
| `docs_check_completeness` | Evaluate doc completeness across categories (essential docs, dev docs, API coverage, docstrings). |
| `docs_check_links` | Validate internal links in markdown files. Verifies referenced files and anchors exist (not external HTTP links). |
| `docs_check_freshness` | Score documentation freshness based on file mod times. Fresh (<30d), aging (30-90d), stale (90-365d), ancient (>365d). |
| `docs_check_diataxis` | Check Diataxis content balance (Tutorial/How-to/Reference/Explanation) across all markdown files. |
| `docs_check_cross_refs` | Validate cross-references between docs. Detects orphan documents, broken references, missing backlinks. |
| `docs_validate_epic` | Validate epic document structure: required sections, story completeness, dependency cycles, files coverage. |
| `docs_check_style` | Deterministic markdown style/tone checks (passive voice, jargon, sentence length, heading consistency). |

### CLI

All commands work on **Linux, macOS, and Windows**.

```bash
docsmcp serve                    # Start DocsMCP MCP server (default: stdio)
docsmcp serve --transport http   # Start with HTTP transport
docsmcp serve --port 8001        # Custom port
docsmcp doctor                   # Check config, dependencies (tapps-core, mcp SDK, jinja2, gitpython)
docsmcp scan                     # Scan project for doc files; show inventory by category & size
docsmcp version                  # Print DocsMCP version
```

### Configuration

DocsMCP reads from `.docsmcp.yaml` in the project root:

```yaml
output_dir: docs                       # Directory for generated documentation
default_style: standard               # minimal | standard | comprehensive
default_format: markdown              # markdown | rst | plain
include_toc: true                     # Include table of contents
include_badges: true                  # Include badges in README
changelog_format: keep-a-changelog    # keep-a-changelog | conventional
adr_format: madr                      # madr | nygard
diagram_format: mermaid               # mermaid | plantuml | d2
git_log_limit: 500                    # Max git commits to analyze

# Tool filtering (optional)
tool_preset: full                     # full (all 32 DocsMCP tools) | core (subset)
enabled_tools: []                     # Allow list — when non-empty, only these tools are exposed
disabled_tools: []                    # Deny list — excluded from the exposed set
```

### Roadmap

DocsMCP is feature-complete with 32 MCP tools covering README generation, API documentation, changelog/release notes, ADRs, onboarding/contributing guides, PRD/epic/story generation, LLM prompt artifacts, Mermaid/PlantUML/D2 diagrams (8 types, 3 formats, D2 themes), interactive HTML diagrams, llms.txt generation, frontmatter management, Diataxis classification, drift detection, completeness validation, link/cross-ref checking, freshness analysis, style checking, purpose/intent templates, and documentation indexing. All generators use three-tier output (write-first/inline/manifest) with auto-computed default paths. See [docs/archive/planning/DOCSMCP_PRD.md](docs/archive/planning/DOCSMCP_PRD.md) for the original specification.

---

## Docs and roadmap

### For consuming projects

| Doc | Description |
|-----|-------------|
| [AGENTS.md](AGENTS.md) | AI assistant workflow guide - when to use each tool, recommended workflow, troubleshooting. |
| [docs/UPGRADE_FOR_CONSUMERS.md](docs/UPGRADE_FOR_CONSUMERS.md) | Upgrade guide for projects that install TappsMCP. |
| [docs/INIT_AND_UPGRADE_FEATURE_LIST.md](docs/INIT_AND_UPGRADE_FEATURE_LIST.md) | Init and upgrade: `tapps_init` vs `tapps-mcp init`, overwrite flags, upgrade path. |
| [docs/ONBOARDING.md](docs/ONBOARDING.md) | Getting started guide for new developers. |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common issues and solutions. |
| [docs/CONFIG_REFERENCE.md](docs/CONFIG_REFERENCE.md) | Full configuration reference. |

### For TappsMCP developers

| Doc | Description |
|-----|-------------|
| [CLAUDE.md](CLAUDE.md) | Instructions for AI assistants working on the TappsMCP codebase itself. |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development setup, coding standards, and how to submit changes. |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Full architecture documentation. |
| [docs/DOCKER_DEPLOYMENT.md](docs/DOCKER_DEPLOYMENT.md) | Docker build, run, env vars, and client connection. |
| [docs/DOCKER_MCP_TOOLKIT.md](docs/DOCKER_MCP_TOOLKIT.md) | Docker image distribution. |
| [docs/MEMORY_REFERENCE.md](docs/MEMORY_REFERENCE.md) | Full memory system reference (33 actions, configuration, defaults). |
| [CHANGELOG.md](CHANGELOG.md) | Release history following Keep a Changelog format. |
| [SECURITY.md](SECURITY.md) | Security policy and vulnerability reporting. |

**Roadmap (epics):** Foundation & Security ✅ · Core Quality MVP ✅ · Knowledge & Docs ✅ · Expert System ✅ · Project Context ✅ · Adaptive Learning ✅ · Distribution ✅ · Metrics & Dashboard ✅ · Pipeline Orchestration ✅ · Scoring Reliability ✅ · Expert + Context7 Integration ✅ · Retrieval Optimization ✅ · Platform Integration ✅ · Structured Outputs ✅ · Dead Code Detection ✅ · Dependency Vulnerability Scanning ✅ · Doc Backend Resilience ✅ · Circular Dependency Detection ✅ · MCP Upgrade Tool & Exe Path Handling ✅ · LLM Engagement Level ✅ · GitHub Templates & CI ✅ · GitHub Copilot & Governance ✅ · Shared Memory Foundation ✅ · Memory Intelligence ✅ · Memory Retrieval & Integration ✅ · Monorepo Workspace ✅ · tapps-core Extraction ✅ · DocsMCP Server Skeleton ✅ · Doc Provider Simplification ✅ · Platform Artifact Correctness ✅ · Memory Retrieval Upgrade ✅ · Expert Adaptive Integration ✅ · Quality Review Remediation ✅ · Hook & Platform Expansion ✅ · Pipeline Onboarding & Distribution ✅ · **Benchmark Infrastructure** ✅ · **Template Self-Optimization** ✅ · **MCP Tool Effectiveness** ✅

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and how to submit changes.

---

## License

MIT - see [LICENSE](LICENSE).

