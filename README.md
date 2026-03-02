# Tapps Platform

> **A quality and documentation toolset for AI coding assistants.** Two MCP servers — **TappsMCP** (code quality) and **DocsMCP** (documentation) — that give LLMs and AI-powered IDEs deterministic tools for scoring, security scanning, quality gates, documentation lookup, doc generation, config validation, and domain expert consultation — through structured tool calls instead of prompt injection.

Use TappsMCP and DocsMCP in your projects so **Claude Code**, **Cursor**, **VS Code Copilot**, and other MCP-capable clients produce higher-quality code with consistent, repeatable standards.

**Supported clients:** Claude Code · Cursor · VS Code (Copilot) · Claude Desktop · any MCP host

### Packages

| Package | PyPI Name | Purpose | Tools |
|---|---|---|---|
| **tapps-core** | `tapps-core` | Shared infrastructure (config, security, logging, knowledge, memory, experts, metrics) | 0 (library) |
| **tapps-mcp** | `tapps-mcp` | Code quality MCP server (scoring, gates, tools, validation) | 28 |
| **docs-mcp** | `docs-mcp` | Documentation generation and maintenance MCP server | 3 (MVP) |

[![CI](https://github.com/tapps-mcp/tapps-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/tapps-mcp/tapps-mcp/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Table of contents

- [What is TappsMCP?](#what-is-tappsmcp)
- [Features](#features)
- [Install](#install)
- [Quick start](#quick-start)
- [Connecting your AI client](#connecting-your-ai-client)
- [CLI utilities](#cli-utilities)
- [Tools reference](#tools-reference)
- [Configuration](#configuration)
- [Optional tool dependencies](#optional-tool-dependencies)
- [Docker](#docker)
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

TappsMCP exposes **28 MCP tools** plus workflow prompts. All tools are **deterministic** (no LLM calls in the tool chain).

### Code quality & scoring

| Feature | Description |
|--------|-------------|
| **Code scoring** | 0–100 score across 7 categories: complexity, security, maintainability, test coverage, performance, structure, developer experience. Quick mode (ruff-only) or full (ruff, mypy, bandit, radon). |
| **Quality gates** | Pass/fail against configurable presets: **standard**, **strict**, **framework**. |
| **Structured outputs** | Machine-parseable JSON (`structuredContent`) for 6 tools: `tapps_score_file`, `tapps_quality_gate`, `tapps_quick_check`, `tapps_security_scan`, `tapps_validate_changed`, `tapps_validate_config`. |
| **Dead code detection** | Vulture-based unused functions, classes, imports, variables with confidence scoring; integrated into maintainability/structure. |
| **Circular dependency detection** | AST import graph, cycle detection, coupling metrics (Ca/Ce/instability). |
| **Session checklist** | Track which tools were called; required vs recommended by task type (feature, bugfix, refactor, security, review). **LLM engagement level** (high/medium/low) adjusts required tools and wording. |
| **Adaptive learning** | Scoring weights and expert voting adapt from usage. Adaptive domain detection routes queries based on learned feedback when enabled. Query expansion with ~60 synonym pairs improves domain detection recall. |

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
| **Documentation lookup** | Up-to-date library docs via Context7 (when `TAPPS_MCP_CONTEXT7_API_KEY` is set) and LlmsTxt (always, as fallback). Fuzzy matching, local cache. |
| **Domain experts** | 17 built-in experts (security, testing, APIs, GitHub, etc.) with RAG-backed answers, confidence scores, and knowledge freshness warnings. |
| **Project context** | Detect project type, tech stack, structure for context-aware analysis. |
| **Shared memory** | Persistent, project-scoped memory with BM25-scored retrieval (stemming + stop-word filtering), time-based decay, contradiction detection, and expert injection. Memories survive across sessions in SQLite (WAL + FTS5). Three tiers (architectural/pattern/context) with configurable half-lives. Auto-seeds from project profile. Auto-GC in `tapps_session_start` when memory exceeds 80% capacity. `reinforce` and `gc` actions exposed via MCP tool. |
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

## Install

Choose one of the following. After installing, see [Quick start](#quick-start) to configure your AI client and start the server.

| Method | Requirements | Use when |
|--------|--------------|----------|
| **PyPI** | Python 3.12+, pip | You want a global or venv install and will run from any project. |
| **npx** | Node.js 18+ | You prefer not to touch Python; runs on demand. |
| **From source** | Python 3.12+, [uv](https://docs.astral.sh/uv/) or pip | You are developing TappsMCP or want the latest code. |
| **Docker** | Docker, Docker Compose | You want HTTP transport or to run in a container. |

### Install from PyPI

```bash
pip install tapps-mcp
```

Or in a virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux
pip install tapps-mcp
```

**Upgrade:** `pip install -U tapps-mcp` then run `tapps-mcp upgrade` to refresh all generated files (AGENTS.md, platform rules, hooks, permissions). A backup is created automatically before overwriting — use `tapps-mcp rollback` if needed. See [CHANGELOG.md](CHANGELOG.md) for changes and [docs/UPGRADE_FOR_CONSUMERS.md](docs/UPGRADE_FOR_CONSUMERS.md) for the full upgrade guide.

### Install with npx (no Python install)

No need to install Python. From any directory:

```bash
npx tapps-mcp serve
```

The first run downloads the package; use `npx tapps-mcp@latest serve` to pin to latest.

### Install from source

Clone the repo and install in editable mode with [uv](https://docs.astral.sh/uv/) (recommended):

```bash
git clone https://github.com/tapps-mcp/tapps-mcp.git
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
git clone https://github.com/tapps-mcp/tapps-mcp.git
cd tapps-mcp
docker compose up --build -d
```

The server listens at **http://localhost:8000** (MCP at `/mcp`). See [Docker](#docker) and [docs/DOCKER_DEPLOYMENT.md](docs/DOCKER_DEPLOYMENT.md) for options (e.g. mounting another project).

---

## Quick start

After [installing](#install), set up TappsMCP in your project and connect your AI client.

**1. Configure your AI client (auto-detect):**

```bash
tapps-mcp init                    # detects Claude Code, Cursor, VS Code
# or: tapps-mcp init --host cursor   # target a specific client
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

For project-level config, use `tapps-mcp init --host claude-code --scope project` to create `.mcp.json` in the project root. For full access without permission prompts, see [docs/CLAUDE_FULL_ACCESS_SETUP.md](docs/CLAUDE_FULL_ACCESS_SETUP.md).

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

When TappsMCP is connected, call **`tapps_session_start`** at session start (server info + memory status); call **`tapps_project_profile`** when you need project context. Use **`tapps_memory`** to recall and save project decisions across sessions. Use **`tapps_quick_check`** after editing files; before declaring work complete, run **`tapps_validate_changed`** and **`tapps_checklist`**. Use **`tapps_lookup_docs`** before writing code that uses an external library. See **[AGENTS.md](AGENTS.md)** for when to use each tool and the full workflow.

### Suggested workflow for the AI

1. Call **`tapps_session_start`** at session start (server info + memory status). Call **`tapps_project_profile`** when you need tech stack, project type, or recommendations.
2. Use **`tapps_memory search`** to recall relevant project context and past decisions.
3. Use **`tapps_quick_check`** (or `tapps_score_file` with `quick: true`) during edit-lint-fix loops.
4. Use **`tapps_lookup_docs`** before writing code that uses an external library API.
5. Use **`tapps_validate_changed`** before marking work complete (validates all changed files).
6. Use **`tapps_memory save`** to persist important decisions and learnings for future sessions.
7. Call **`tapps_checklist`** to ensure no required steps were skipped.

---

## CLI utilities

TappsMCP includes CLI commands to set up, diagnose, and run the server:

| Command | Purpose |
|---------|---------|
| `tapps-mcp serve` | Start the MCP server (stdio or HTTP transport). |
| `tapps-mcp init` | Generate MCP configuration for Claude Code, Cursor, or VS Code. Use `--engagement-level high\|medium\|low` to set LLM engagement. |
| `tapps-mcp init --check` | Verify existing MCP configuration without writing. |
| `tapps-mcp init --force` | Overwrite existing config without prompting (CI/scripts). |
| `tapps-mcp upgrade` | Refresh all generated files (AGENTS.md, rules, hooks, settings) after upgrading TappsMCP. |
| `tapps-mcp doctor` | Diagnose configuration and connectivity; reports `llm_engagement_level` when set. |
| `tapps-mcp validate-changed` | Run quality validation on changed files from the CLI (same as MCP tool). |
| `tapps-mcp build-plugin` | Generate a Claude Code plugin directory with skills, agents, hooks, MCP config, and rules. |
| `tapps-mcp rollback` | Restore configuration files from a pre-upgrade backup. Use `--list` to see backups. |

### `tapps-mcp init` options

| Option | Description |
|--------|-------------|
| `--host claude-code \| cursor \| vscode \| auto` | Target MCP client (default: auto-detect). |
| `--scope user \| project` | Config scope for Claude Code (default: user). |
| `--engagement-level high \| medium \| low` | LLM engagement level for generated AGENTS.md and rules (default: medium). |
| `--force` | Overwrite existing config without prompting. |
| `--check` | Verify only; no writes. |
| `--rules` / `--no-rules` | Generate platform rule files (default: yes). |
| `--project-root PATH` | Project root (default: current dir). |

### `tapps-mcp upgrade`

After upgrading TappsMCP (`pip install -U tapps-mcp`), refresh generated files:

```bash
tapps-mcp upgrade                           # auto-detect host, update all files
tapps-mcp upgrade --host claude-code        # target a specific host
tapps-mcp upgrade --dry-run                 # preview changes without writing
tapps-mcp upgrade --force                   # overwrite even if up-to-date
```

Updates AGENTS.md, platform rules, hooks, agents, skills, and `.claude/settings.json` permissions. A **backup** is automatically created before overwriting files. Use `tapps-mcp rollback` to restore from the latest backup if an upgrade causes issues.

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

Checks: MCP config, AGENTS.md version and completeness, `.claude/settings.json` permissions, hook files, installed checkers.

---

## Tools reference

Quick index:

| Tool | One-line purpose |
|------|------------------|
| **tapps_session_start** | **FIRST call** — server info only (version, checkers, config); call tapps_project_profile for project context. |
| **tapps_server_info** | Discover server version, tools, checkers, and recommended workflow. |
| **tapps_score_file** | Score a Python file 0–100 across 7 quality categories. |
| **tapps_quick_check** | Fast score + gate + basic security in one call after editing a file. |
| **tapps_security_scan** | Run Bandit + secret detection on a Python file. |
| **tapps_quality_gate** | Pass/fail a file against a quality preset (standard/strict/framework). |
| **tapps_validate_changed** | Score + gate + security scan all changed files (auto-detects via git diff). |
| **tapps_lookup_docs** | Fetch current documentation for a library (Context7 when key set, LlmsTxt fallback; cache). |
| **tapps_validate_config** | Validate Dockerfile, docker-compose, or infra configs. |
| **tapps_consult_expert** | Ask a domain expert and get RAG-backed answer with confidence. |
| **tapps_research** | Combined expert + docs lookup in one call (Context7 when key set, LlmsTxt fallback). |
| **tapps_list_experts** | List the 17 built-in expert domains and their status. |
| **tapps_checklist** | See which tools were called this session and what is still missing. |
| **tapps_project_profile** | Detect project type, tech stack, and structure for context-aware analysis. |
| **tapps_session_notes** | Save and retrieve key decisions and constraints across the session. Promotable to shared memory. |
| **tapps_memory** | Persistent shared memory: save, get, list, delete, search, reinforce, contradictions, gc, reseed, import, export. |
| **tapps_impact_analysis** | Analyze the impact of changes on the codebase (imports, dependents). |
| **tapps_report** | Generate a quality report (JSON, Markdown, or HTML) for scored files. |
| **tapps_dashboard** | View metrics dashboard with execution stats, expert performance, and trends. |
| **tapps_stats** | Retrieve aggregated usage statistics and quality trends across sessions. |
| **tapps_feedback** | Submit feedback on tool results to improve adaptive scoring and expert answers. |
| **tapps_dead_code** | Scan Python files for dead code — supports file, project-wide, or changed-files-only scanning with confidence scoring. |
| **tapps_dependency_scan** | Scan project dependencies for known vulnerabilities (pip-audit). |
| **tapps_dependency_graph** | Build import graph, detect circular imports, and calculate coupling metrics. |
| **tapps_init** | Bootstrap TappsMCP in a project: create AGENTS.md, TECH_STACK.md, platform rules, warm caches. |
| **tapps_set_engagement_level** | Set LLM engagement level (high/medium/low) in `.tapps-mcp.yaml`; then run init with overwrite to apply. |
| **tapps_upgrade** | Validate and refresh all generated files (AGENTS.md, rules, hooks) after upgrading TappsMCP. |
| **tapps_doctor** | Diagnose configuration, rules, hooks, and connectivity; reports `llm_engagement_level` when set. |
| **tapps_workflow** | *(MCP prompt, not a tool)* Recommended tool call order for a specific task type. |

---

### tapps_session_start

**What it does:** Returns server info only: version, configuration, installed checkers, diagnostics, quick_start, and pipeline. This is the **required first call** in every session. It does not run project profile; call **tapps_project_profile** when you need project type, tech stack, or recommendations.

**Why use it:** Initializes the session with server capabilities so you know which checkers are available and the recommended workflow. Kept lightweight (~1s). Call tapps_project_profile on demand for project context.

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

### tapps_consult_expert

**What it does:** Sends a natural-language question to a domain expert. The server has 17 built-in domains (e.g. security, testing, API design, database, observability, GitHub). You can leave **domain** empty for auto-routing from the question, or pass a domain id (e.g. `"security"`, `"testing-strategies"`). The expert uses RAG over curated knowledge files, returns an answer, a confidence score, contributing factors, and source chunks. Answers are filtered for PII/secrets before return.

**Why use it:** When the AI (or user) is unsure about patterns, trade-offs, or best practices in a specific area, a single call returns focused, sourced guidance instead of generic advice. Use for security decisions, test strategy, API design, DB schema, or observability so the response is grounded in the expert knowledge base and the confidence score signals how much to rely on it.

---

### tapps_research

**What it does:** Combined expert consultation + documentation lookup in one call. Consults the domain expert first, then supplements with docs from Context7 (when key set) or LlmsTxt (fallback). Accepts optional `library` and `topic` parameters (auto-inferred when empty). The `file_context` parameter accepts a path to the file being edited, allowing the tool to infer the relevant library from imports. Returns expert answer, confidence, sources, and supplementary docs content.

**Why use it:** Saves a round-trip compared to calling `tapps_consult_expert` and `tapps_lookup_docs` separately. Use when you need both expert guidance and current library documentation for a domain-specific question. Docs are always fetched to provide the most complete answer. Pass `file_context` when editing a specific file so the tool can auto-detect which library to look up from imports.

---

### tapps_list_experts

**What it does:** Returns the list of all 17 built-in expert domains. For each expert it provides an id, display name, short description, and knowledge-base status (e.g. how many knowledge files are loaded). No parameters required.

**Why use it:** Lets the AI (or host) discover which domains exist before calling `tapps_consult_expert`. Use at session start or when the user asks "what can the experts help with?" so the right domain can be chosen and the right expert consulted.

---

### tapps_checklist

**What it does:** Tracks which TappsMCP tools have been called in the current server session and evaluates that against a **task type**: `feature`, `bugfix`, `refactor`, `security`, or `review`. For that task type, some tools are required, some recommended, some optional. The tool returns the list of called tools, missing required/recommended/optional tools, and for each missing tool a short **reason** (in `missing_required_hints`, `missing_recommended_hints`, `missing_optional_hints`) explaining why to call it. It also returns a **complete** flag (true when all required tools have been called) and total call count. When `auto_run=True`, the tool automatically runs any missing required validations (via `tapps_validate_changed`) and re-evaluates the checklist.

**Why use it:** Ensures the AI does not skip important steps (e.g. never running the quality gate or security scan) before declaring work complete. Call before saying "done"; if `complete` is false, the hints tell you exactly which tools to call and why. Use `auto_run=True` to let the checklist fill in missing steps automatically. Task types align expectations (e.g. security tasks require a security scan) so the checklist matches the kind of work being done.

---

### tapps_project_profile

**What it does:** Analyzes the project at `TAPPS_MCP_PROJECT_ROOT` to detect project type (web app, CLI tool, library, microservice, data pipeline), tech stack (languages, frameworks, databases), and structure (source layout, test framework, dependency management). Returns a profile with type, confidence score, detected technologies, and structural metadata.

**Why use it:** Gives the AI context about the project before making changes. Prevents applying wrong patterns (e.g. web patterns to a CLI tool). Use at session start alongside `tapps_server_info` for context-aware analysis.

---

### tapps_session_notes

**What it does:** Persists key decisions, constraints, and context across a session. Supports **save** (store a note with category and optional tags), **get** (retrieve notes, optionally filtered by category), **list**, **clear**, and **promote** (copy a note to persistent shared memory via `tapps_memory`). Notes survive within a server session and are stored in `.tapps-mcp/session/`. Responses include a `migration_hint` suggesting `tapps_memory` for cross-session persistence.

**Why use it:** In long sessions, the AI may forget decisions made earlier. Session notes let the AI save constraints ("user wants sync-only, no async") and retrieve them later so earlier context is not lost. Use `promote` to persist important notes to shared memory so they survive across sessions. For new projects, prefer `tapps_memory` directly for persistent storage.

---

### tapps_memory

**What it does:** Persistent, project-scoped shared memory accessible to all MCP-connected agents. Memories are typed by tier (`architectural`, `pattern`, `context`), carry confidence scores (0.0-1.0 with source-based defaults), and persist across sessions in SQLite with WAL mode and FTS5 full-text search at `{project_root}/.tapps-mcp/memory/memory.db`. Supports 11 actions: **save** (with RAG safety filtering), **get** (with scope resolution: session > branch > project), **list** (filtered by tier/scope/tags), **delete**, **search** (FTS5 ranked retrieval with composite scoring), **reinforce** (reset decay clock, optional confidence boost), **contradictions** (detect memories that contradict current project state), **gc** (archive decayed memories), **reseed** (re-populate from project profile), **import** and **export** (JSON format with path validation). Time-based exponential decay with tier-specific half-lives (architectural: 180 days, pattern: 60 days, context: 14 days). Contradiction detection compares memories against `tapps_project_profile` for tech stack drift, missing files, and deleted branches. Relevant memories are auto-injected into `tapps_consult_expert` and `tapps_research` responses (configurable by engagement level). Max 500 memories per project with lowest-confidence eviction.

**Why use it:** Agents start every session amnesiac about the project. Shared memory means the project remembers things, not the developer's tool. Save architectural decisions ("we use JWT with RS256"), patterns ("always mock the DB in unit tests"), and context ("current sprint focuses on auth"). Memories decay naturally so stale information loses trust. Contradiction detection catches drift (e.g., memory says "we use SQLAlchemy" after migrating to Prisma). Expert injection means `tapps_consult_expert` automatically includes relevant project memory in its response.

---

### tapps_impact_analysis

**What it does:** Analyzes a Python file to determine its blast radius. Builds an import graph, identifies direct dependents (files that import the changed file), transitive dependents (multi-hop), and affected test files. Returns severity assessment, total affected count, and recommendations. Accepts an optional `change_type` parameter (`"added"`, `"modified"`, or `"removed"`) to adjust severity assessment.

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

**What it does:** Runs a suite of diagnostic checks and returns structured results. Checks include: binary availability on PATH, MCP config files for Claude Code (user and project), Cursor, and VS Code, CLAUDE.md and Cursor rules presence, AGENTS.md version and completeness, `.claude/settings.json` permission entries, hook files, and installed quality tools (ruff, mypy, bandit, radon, vulture, pip-audit). When `llm_engagement_level` is set in `.tapps-mcp.yaml`, the result includes an `llm_engagement_level` key. Returns per-check pass/fail with messages and remediation hints, plus aggregated `pass_count`, `fail_count`, and `all_passed`.

**Why use it:** When TappsMCP tools are not working as expected — permission prompts, missing tools, degraded results — run `tapps_doctor()` to identify configuration issues. The structured output pinpoints exactly what needs fixing and suggests the command to fix it.

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

Configure the persistent memory system (all values shown are defaults):

```yaml
memory:
  enabled: true                       # Enable/disable memory system
  gc_enabled: true                    # Auto-archive decayed memories at session start
  contradiction_check_on_start: true  # Check for stale memories at session start
  max_memories: 500                   # Max entries per project
  inject_into_experts: true           # Auto-inject memories into expert/research responses
  decay:
    architectural_half_life_days: 180 # Slow decay for architectural decisions
    pattern_half_life_days: 60        # Medium decay for coding patterns
    context_half_life_days: 14        # Fast decay for session context
    confidence_floor: 0.1             # Memories never decay below this
```

Memory data is stored at `{project_root}/.tapps-mcp/memory/` (SQLite database + JSONL audit log). Add `.tapps-mcp/memory/` to `.gitignore` — memory is project-local, not shared via version control.

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

**Vector RAG (optional):** For semantic search over expert knowledge files, install the `rag` extras:

```bash
pip install tapps-mcp[rag]   # or: uv add tapps-mcp[rag]
```

This adds `faiss-cpu`, `sentence-transformers`, and `numpy`. When not installed, the expert system uses keyword-based RAG (no configuration needed).

---

## Docker

Run TappsMCP as a local MCP server in a container (Streamable HTTP on port 8000):

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

Optional flags:

- `warm_cache_from_tech_stack=True` — pre-fetch Context7 docs for detected libraries
- `warm_expert_rag_from_tech_stack=True` — pre-build expert RAG indices for relevant domains
- `verify_server=True` — check which external checkers are installed
- `install_missing_checkers=True` — auto-install missing ruff/mypy/bandit/radon
- `agent_teams=True` — generate Agent Teams hooks for quality watchdog teammate (Claude Code only)

After upgrading TappsMCP, run `tapps-mcp upgrade` to refresh all generated files, or re-run `tapps_init` with `overwrite_agents_md=True` and `overwrite_platform_rules=True`. See [docs/UPGRADE_FOR_CONSUMERS.md](docs/UPGRADE_FOR_CONSUMERS.md).

---

## Development

This is a **uv workspace monorepo** with three packages. All commands run from the **repository root**.

```bash
# Install all packages (tapps-core, tapps-mcp, docs-mcp)
uv sync --all-packages

# Run all tests across the entire workspace (4300+ tests)
uv run pytest packages/tapps-core/tests/ packages/tapps-mcp/tests/ packages/docs-mcp/tests/ -v

# Run tests for a single package
uv run pytest packages/tapps-core/tests/ -v      # tapps-core (1087 tests)
uv run pytest packages/tapps-mcp/tests/ -v        # tapps-mcp (3123 tests)
uv run pytest packages/docs-mcp/tests/ -v         # docs-mcp  (107 tests)

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

---

## Project layout

This is a **uv workspace monorepo** with three packages under `packages/`:

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
│       ├── experts/                   # Domain detector, engine, RAG, 139 knowledge files
│       ├── memory/                    # Shared memory: SQLite persistence, decay, retrieval
│       ├── metrics/                   # Collector, dashboard, alerts, trends, OTel export
│       └── adaptive/                  # Adaptive scoring, expert voting, weight distribution
│
├── tapps-mcp/                         # Code quality MCP server (28 tools)
│   └── src/tapps_mcp/
│       ├── server.py, cli.py          # Entry points and MCP server
│       ├── server_*.py                # Tool modules (scoring, pipeline, metrics, memory, analysis)
│       ├── scoring/                   # Score model, scorer, dead code, dependency security
│       ├── gates/                     # Gate presets, evaluator
│       ├── tools/                     # Ruff, mypy, bandit, radon, vulture, pip-audit, checklist
│       ├── validators/                # Dockerfile, docker-compose, WebSocket, MQTT, InfluxDB
│       ├── project/                   # Project profiling, session notes, impact analysis
│       ├── distribution/              # Setup generator (init, upgrade, doctor)
│       ├── pipeline/                  # Pipeline orchestration, platform generators
│       └── (re-exports)              # Backward-compatible re-exports from tapps-core
│
└── docs-mcp/                          # Documentation MCP server (3 tools, MVP)
    └── src/docs_mcp/
        ├── server.py, cli.py          # Entry points and MCP server
        ├── server_helpers.py          # Response builders, singletons
        └── config/                    # DocsMCP-specific settings, default.yaml

plugin/
└── cursor/                            # Ready-to-publish Cursor marketplace plugin
examples/
└── agent-sdk/                         # Claude Agent SDK integration examples (Python + TypeScript)
```

**Backward compatibility:** `from tapps_mcp.config import load_settings` still works — tapps-mcp re-exports everything from tapps-core. Existing consuming projects need no changes.

---

## DocsMCP (documentation server)

DocsMCP is a companion MCP server for documentation generation, drift detection, and maintenance. It shares infrastructure with TappsMCP via `tapps-core`.

### Current tools (MVP)

| Tool | Description |
|------|-------------|
| `docs_session_start` | Initialize session, detect project context, scan existing documentation |
| `docs_project_scan` | Comprehensive documentation state audit with completeness scoring |
| `docs_config` | View/update DocsMCP configuration (`.docsmcp.yaml`) |

### CLI

```bash
docsmcp serve          # Start the DocsMCP MCP server
docsmcp doctor         # Check configuration and dependencies
docsmcp scan           # Run documentation inventory
docsmcp generate       # Generate documentation (coming soon)
docsmcp version        # Print version
```

### Configuration

DocsMCP reads from `.docsmcp.yaml` in the project root:

```yaml
output_dir: docs
default_style: standard        # minimal | standard | comprehensive
default_format: markdown       # markdown | rst | plain
include_toc: true
include_badges: true
changelog_format: keep-a-changelog
adr_format: madr
diagram_format: mermaid
git_log_limit: 500
```

### Roadmap

DocsMCP is in early development. Planned features include README generation, API documentation, changelog generation, Mermaid diagrams, drift detection, completeness validation, and multi-language support. See [docs/planning/DOCSMCP_PRD.md](docs/planning/DOCSMCP_PRD.md) for the full specification.

---

## Docs and roadmap

### For consuming projects

| Doc | Description |
|-----|-------------|
| [AGENTS.md](AGENTS.md) | AI assistant workflow guide - when to use each tool, recommended workflow, troubleshooting. |
| [addenda.md](addenda.md) | Best practices for Claude Code, Cursor, consuming projects, troubleshooting. |
| [docs/TAPPS_MCP_SETUP_AND_USE.md](docs/TAPPS_MCP_SETUP_AND_USE.md) | Detailed setup and use guide (Cursor, Claude, tools workflow). |
| [docs/UPGRADE_FOR_CONSUMERS.md](docs/UPGRADE_FOR_CONSUMERS.md) | Upgrade guide for projects that install TappsMCP. |
| [docs/INIT_AND_UPGRADE_FEATURE_LIST.md](docs/INIT_AND_UPGRADE_FEATURE_LIST.md) | Init and upgrade: `tapps_init` vs `tapps-mcp init`, overwrite flags, upgrade path. |
| [docs/CLAUDE_FULL_ACCESS_SETUP.md](docs/CLAUDE_FULL_ACCESS_SETUP.md) | Grant Claude Code full access (no permission prompts). |
| [docs/MIGRATION_FROM_TAPPS_AGENTS.md](docs/MIGRATION_FROM_TAPPS_AGENTS.md) | Migrating from tapps-agents: what to remove, keep, configure. |
| [docs/ci-integration.md](docs/ci-integration.md) | CI/CD integration: GitHub Actions, headless mode, direct CLI invocation. |
| [docs/MCP_CLIENT_TIMEOUTS.md](docs/MCP_CLIENT_TIMEOUTS.md) | Handling long-running tool timeouts in MCP clients. |

### For TappsMCP developers

| Doc | Description |
|-----|-------------|
| [CLAUDE.md](CLAUDE.md) | Instructions for AI assistants working on the TappsMCP codebase itself. |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development setup, coding standards, and how to submit changes. |
| [docs/ARCHITECTURE_CACHE_AND_RAG.md](docs/ARCHITECTURE_CACHE_AND_RAG.md) | Context7 cache SWR behavior and expert RAG index architecture. |
| [docs/DOCKER_DEPLOYMENT.md](docs/DOCKER_DEPLOYMENT.md) | Docker build, run, env vars, and client connection. |
| [docs/planning/TAPPS_MCP_PLAN.md](docs/planning/TAPPS_MCP_PLAN.md) | Architecture and design rationale. |
| [docs/planning/TAPPS_PLATFORM_PRD.md](docs/planning/TAPPS_PLATFORM_PRD.md) | Platform restructure PRD (monorepo, extraction, composition). |
| [docs/planning/DOCSMCP_PRD.md](docs/planning/DOCSMCP_PRD.md) | DocsMCP feature specification (18 tools, 12 epics). |
| [docs/planning/epics/README.md](docs/planning/epics/README.md) | Epic index, dependency graph, tool delivery timeline. |
| [CHANGELOG.md](CHANGELOG.md) | Release history following Keep a Changelog format. |
| [SECURITY.md](SECURITY.md) | Security policy and vulnerability reporting. |

**Roadmap (epics):** Foundation & Security ✅ · Core Quality MVP ✅ · Knowledge & Docs ✅ · Expert System ✅ · Project Context ✅ · Adaptive Learning ✅ · Distribution ✅ · Metrics & Dashboard ✅ · Pipeline Orchestration ✅ · Scoring Reliability ✅ · Expert + Context7 Integration ✅ · Retrieval Optimization ✅ · Platform Integration ✅ · Structured Outputs ✅ · Dead Code Detection ✅ · Dependency Vulnerability Scanning ✅ · Doc Backend Resilience ✅ · Circular Dependency Detection ✅ · MCP Upgrade Tool & Exe Path Handling ✅ · LLM Engagement Level ✅ · GitHub Templates & CI ✅ · GitHub Copilot & Governance ✅ · Shared Memory Foundation ✅ · Memory Intelligence ✅ · Memory Retrieval & Integration ✅ · **Monorepo Workspace** ✅ · **tapps-core Extraction** ✅ · **DocsMCP Server Skeleton** ✅

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and how to submit changes.

---

## License

MIT - see [LICENSE](LICENSE).

