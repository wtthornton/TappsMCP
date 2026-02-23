# TappsMCP

**A quality toolset for AI coding assistants.** TappsMCP is an MCP server that gives LLMs and AI-powered IDEs deterministic code quality tools — scoring, security scanning, quality gates, documentation lookup, config validation, and domain expert consultation — all through structured tool calls instead of prompt injection.

**Use TappsMCP in your projects** to help Claude Code, Cursor, VS Code Copilot, and other MCP-capable clients produce higher-quality code with consistent, repeatable standards.

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
- [Docs and roadmap](#docs-and-roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## What is TappsMCP?

TappsMCP is a **quality toolset designed to help other projects and LLMs be the best they can**. LLMs writing code make repeatable mistakes: wrong APIs, missing tests, security issues, and inconsistent quality. TappsMCP moves **proven quality tooling** out of long system prompts and into a single MCP server that any project can install and use.

Any MCP-capable client (Claude Code, Cursor, VS Code Copilot, Claude Desktop, custom hosts) can call the same tools and get **structured, deterministic results** — scores, gates, security findings, doc lookups, and expert advice — without burning context on framework instructions. Install TappsMCP in your project, connect your AI client, and every coding session benefits from consistent quality enforcement.

---

## Features

- **Code scoring** — 0–100 score across 7 categories (complexity, security, maintainability, test coverage, performance, structure, developer experience).
- **Security scanning** — Bandit + secret detection with redacted context.
- **Quality gates** — Pass/fail against configurable presets (standard, strict, framework).
- **Dead code detection** — Vulture-based detection of unused functions, classes, imports, and variables with confidence scoring, integrated into maintainability/structure scores.
- **Dependency vulnerability scanning** — pip-audit integration for known CVEs in third-party packages with severity filtering.
- **Circular dependency detection** — AST-based import graph, cycle detection, and coupling metrics (Ca/Ce/instability).
- **Structured outputs** — Machine-parseable JSON (`structuredContent`) alongside human-readable text for all scoring tools (MCP 2025-11-25).
- **Documentation lookup** — Up-to-date library docs via [Context7](https://context7.com) with multi-provider fallback (llms.txt), fuzzy matching, and local cache.
- **Config validation** — Dockerfile, docker-compose, WebSocket/MQTT/InfluxDB patterns against best practices.
- **Domain experts** — 16 built-in experts (security, testing, APIs, etc.) with RAG-backed answers and confidence scores.
- **Project context** — Detect project type, tech stack, and structure for context-aware analysis.
- **Session notes** — Persist key decisions and constraints across long AI sessions.
- **Impact analysis** — Understand file dependencies before refactoring or changing APIs.
- **Quality reports** — Generate JSON, Markdown, or HTML quality summaries.
- **Session checklist** — Track which tools were used so the AI doesn't skip required steps.
- **Adaptive learning** — Scoring weights and expert voting adapt based on usage patterns (internal).
- **Path safety** — All file operations restricted to a configurable project root.
- **Platform hooks** — Auto-generated hook scripts for Claude Code (7 hooks) and Cursor (3 hooks) that enforce quality checks on edit, stop, and task completion.
- **Subagent definitions** — Pre-built agent definitions (reviewer, researcher, validator) for Claude Code and Cursor with platform-specific formats.
- **Skills generation** — SKILL.md templates for scoring, gating, and validation workflows on both platforms.
- **Plugin bundles** — Ready-to-install plugin directories for Claude Code and Cursor with all hooks, agents, skills, rules, and MCP config bundled together.
- **Cursor rule types** — Three-tier Cursor rules: always-on pipeline, auto-attach for Python files, agent-requested expert consultation.
- **Agent Teams** — Quality watchdog teammate pattern for Claude Code Agent Teams with TeammateIdle and TaskCompleted hooks (opt-in).
- **VS Code / Copilot instructions** — `.github/copilot-instructions.md` for GitHub Copilot with tool guidance, workflow, and scoring reference.
- **Cursor BugBot rules** — `.cursor/BUGBOT.md` with quality standards, security rules, and scoring thresholds for automated PR review.
- **MCP elicitation** — Interactive preset selection in `tapps_quality_gate` and init confirmation in `tapps_init` on supporting clients (graceful fallback on others).
- **CI integration** — GitHub Actions workflow template and headless mode documentation for non-interactive quality gate enforcement.
- **Cursor marketplace** — Ready-to-publish plugin bundle with marketplace.json, deep link, skills, agents, and hooks.
- **Agent SDK examples** — Python and TypeScript examples for Claude Agent SDK integration (basic quality check, CI pipeline, subagent registration).

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

**Upgrade:** `pip install -U tapps-mcp` then run `tapps-mcp upgrade` to refresh all generated files (AGENTS.md, platform rules, hooks, permissions). See [CHANGELOG.md](CHANGELOG.md) for changes and [docs/UPGRADE_FOR_CONSUMERS.md](docs/UPGRADE_FOR_CONSUMERS.md) for the full upgrade guide.

### Install with npx (no Python install)

No need to install Python. From any directory:

```bash
npx tapps-mcp serve
```

The first run downloads the package; use `npx tapps-mcp@latest serve` to pin to latest.

### Install from source

Clone the repo and install in editable mode with [uv](https://docs.astral.sh/uv/) (recommended) or pip:

```bash
git clone https://github.com/tapps-mcp/tapps-mcp.git
cd tapps-mcp
```

**With uv:**

```bash
uv sync
# Run with: uv run tapps-mcp serve
```

**With pip:**

```bash
pip install -e .
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

When TappsMCP is connected, call **`tapps_session_start`** at session start (combines server info + project profile). Use **`tapps_quick_check`** after editing files; before declaring work complete, run **`tapps_validate_changed`** and **`tapps_checklist`**. Use **`tapps_lookup_docs`** before writing code that uses an external library. See **[AGENTS.md](AGENTS.md)** for when to use each tool and the full workflow.

### Suggested workflow for the AI

1. Call **`tapps_session_start`** at session start to initialize context.
2. Use **`tapps_quick_check`** (or `tapps_score_file` with `quick: true`) during edit-lint-fix loops.
3. Use **`tapps_lookup_docs`** before writing code that uses an external library API.
4. Use **`tapps_validate_changed`** before marking work complete (validates all changed files).
5. Call **`tapps_checklist`** to ensure no required steps were skipped.

---

## CLI utilities

TappsMCP includes CLI commands to set up, diagnose, and run the server:

| Command | Purpose |
|---------|---------|
| `tapps-mcp serve` | Start the MCP server (stdio or HTTP transport) |
| `tapps-mcp init` | Generate MCP configuration for Claude Code, Cursor, or VS Code |
| `tapps-mcp init --check` | Verify existing MCP configuration without writing |
| `tapps-mcp init --force` | Overwrite existing config without prompting (for CI/scripts) |
| `tapps-mcp upgrade` | Validate and update all generated files (AGENTS.md, platform rules, hooks, settings) after upgrading TappsMCP |
| `tapps-mcp doctor` | Diagnose TappsMCP configuration and connectivity issues |

### `tapps-mcp init` options

```bash
tapps-mcp init [OPTIONS]
  --host     claude-code | cursor | vscode | auto   # Target client (default: auto-detect)
  --scope    user | project                          # Config scope for Claude Code (default: user)
  --force                                            # Overwrite without prompting
  --check                                            # Verify only, no writes
  --rules / --no-rules                               # Generate platform rule files (default: yes)
  --project-root PATH                                # Project root (default: current dir)
```

### `tapps-mcp upgrade`

After upgrading TappsMCP (`pip install -U tapps-mcp`), refresh generated files:

```bash
tapps-mcp upgrade                           # auto-detect host, update all files
tapps-mcp upgrade --host claude-code        # target a specific host
tapps-mcp upgrade --dry-run                 # preview changes without writing
tapps-mcp upgrade --force                   # overwrite even if up-to-date
```

Updates AGENTS.md, platform rules, hooks, agents, skills, and `.claude/settings.json` permissions.

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
| **tapps_session_start** | **FIRST call** — combines server info + project profile in one call. |
| **tapps_server_info** | Discover server version, tools, checkers, and recommended workflow. |
| **tapps_score_file** | Score a Python file 0–100 across 7 quality categories. |
| **tapps_quick_check** | Fast score + gate + basic security in one call after editing a file. |
| **tapps_security_scan** | Run Bandit + secret detection on a Python file. |
| **tapps_quality_gate** | Pass/fail a file against a quality preset (standard/strict/framework). |
| **tapps_validate_changed** | Score + gate + security scan all changed files (auto-detects via git diff). |
| **tapps_lookup_docs** | Fetch current documentation for a library (Context7 + cache). |
| **tapps_validate_config** | Validate Dockerfile, docker-compose, or infra configs. |
| **tapps_consult_expert** | Ask a domain expert and get RAG-backed answer with confidence. |
| **tapps_research** | Combined expert + docs lookup in one call (auto-supplements with Context7). |
| **tapps_list_experts** | List the 16 built-in expert domains and their status. |
| **tapps_checklist** | See which tools were called this session and what is still missing. |
| **tapps_project_profile** | Detect project type, tech stack, and structure for context-aware analysis. |
| **tapps_session_notes** | Save and retrieve key decisions and constraints across the session. |
| **tapps_impact_analysis** | Analyze the impact of changes on the codebase (imports, dependents). |
| **tapps_report** | Generate a quality report (JSON, Markdown, or HTML) for scored files. |
| **tapps_dashboard** | View metrics dashboard with execution stats, expert performance, and trends. |
| **tapps_stats** | Retrieve aggregated usage statistics and quality trends across sessions. |
| **tapps_feedback** | Submit feedback on tool results to improve adaptive scoring and expert answers. |
| **tapps_dead_code** | Scan a Python file for unused functions, classes, imports, and variables (Vulture). |
| **tapps_dependency_scan** | Scan project dependencies for known vulnerabilities (pip-audit). |
| **tapps_dependency_graph** | Build import graph, detect circular imports, and calculate coupling metrics. |
| **tapps_init** | Initialize a pipeline run: profile the project, set context, and plan the workflow. |
| **tapps_upgrade** | Validate and refresh all generated files (AGENTS.md, rules, hooks) after upgrading TappsMCP. |
| **tapps_doctor** | Diagnose configuration, rules, hooks, and connectivity — returns per-check pass/fail with hints. |
| **tapps_workflow** | *(MCP prompt)* Generate tool call order and recommendations for a specific task type. |

---

### tapps_session_start

**What it does:** Combines `tapps_server_info` and `tapps_project_profile` in a single call. Returns server metadata, installed checker status, project type, tech stack, and structure. This is the **required first call** in every session.

**Why use it:** Initializes the session with full context so all subsequent tool calls can use project-aware recommendations. Skipping this means tools lack project context and suggestions are generic.

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

**What it does:** Detects changed Python files (via `git diff` against a base ref) or accepts an explicit comma-separated list. Runs full score + quality gate + security scan on each file. Returns per-file results with pass/fail status and aggregated summary.

**Why use it:** Required before declaring multi-file work complete. Auto-detects what changed so you don't have to specify each file. Ensures no changed file slips through without quality validation.

---

### tapps_lookup_docs

**What it does:** Fetches current documentation for a given library (e.g. FastAPI, React, SQLAlchemy). Resolves the library name via fuzzy matching, checks a local cache first, and on cache miss can call the Context7 API (when `TAPPS_MCP_CONTEXT7_API_KEY` is set). Accepts an optional **topic** (e.g. "routing", "hooks") and **mode** ("code" for API-style docs, "info" for conceptual). All returned content is checked for prompt-injection patterns before being returned. Response includes source (cache vs API), cache hit flag, and optional token estimate.

**Why use it:** LLMs often hallucinate library APIs or use outdated signatures. Looking up real docs right before writing or fixing code reduces wrong method names, wrong parameters, and deprecated usage. Use it before implementing or refactoring code that depends on an external library. Cache keeps repeated lookups fast and allows offline use when the API key is not set.

---

### tapps_validate_config

**What it does:** Validates a configuration or infrastructure file against best-practice rules. Supports **Dockerfile** (e.g. non-root user, pinning versions, multi-stage usage), **docker-compose** (e.g. resource limits, env handling), and code/config containing **WebSocket**, **MQTT**, or **InfluxDB** patterns. You pass a file path and optionally a **config_type**; with `auto`, the type is inferred from path and content. Returns valid/invalid, a list of findings with severity (critical, warning), and optional suggestions.

**Why use it:** Misconfigured Docker or infra leads to security and reliability issues that are easy to miss. This tool gives deterministic, rule-based feedback so the AI (or human) can fix problems before merge or deploy. Use when adding or changing Dockerfiles, docker-compose files, or the supported config patterns so the result matches team and operational standards.

---

### tapps_consult_expert

**What it does:** Sends a natural-language question to a domain expert. The server has 16 built-in domains (e.g. security, testing, API design, database, observability). You can leave **domain** empty for auto-routing from the question, or pass a domain id (e.g. `"security"`, `"testing-strategies"`). The expert uses RAG over curated knowledge files, returns an answer, a confidence score, contributing factors, and source chunks. Answers are filtered for PII/secrets before return.

**Why use it:** When the AI (or user) is unsure about patterns, trade-offs, or best practices in a specific area, a single call returns focused, sourced guidance instead of generic advice. Use for security decisions, test strategy, API design, DB schema, or observability so the response is grounded in the expert knowledge base and the confidence score signals how much to rely on it.

---

### tapps_research

**What it does:** Combined expert consultation + documentation lookup in one call. Consults the domain expert first, then automatically supplements with Context7 documentation when expert RAG has no results or confidence is low. Accepts optional `library` and `topic` parameters (auto-inferred when empty). Returns expert answer, confidence, sources, and any supplementary docs content.

**Why use it:** Saves a round-trip compared to calling `tapps_consult_expert` and `tapps_lookup_docs` separately. Use when you need both expert guidance and current library documentation for a domain-specific question. The auto-supplementation means you always get documentation backing when the expert knowledge base has gaps.

---

### tapps_list_experts

**What it does:** Returns the list of all 16 built-in expert domains. For each expert it provides an id, display name, short description, and knowledge-base status (e.g. how many knowledge files are loaded). No parameters required.

**Why use it:** Lets the AI (or host) discover which domains exist before calling `tapps_consult_expert`. Use at session start or when the user asks "what can the experts help with?" so the right domain can be chosen and the right expert consulted.

---

### tapps_checklist

**What it does:** Tracks which TappsMCP tools have been called in the current server session and evaluates that against a **task type**: `feature`, `bugfix`, `refactor`, `security`, or `review`. For that task type, some tools are required, some recommended, some optional. The tool returns the list of called tools, missing required/recommended/optional tools, and for each missing tool a short **reason** (in `missing_required_hints`, `missing_recommended_hints`, `missing_optional_hints`) explaining why to call it. It also returns a **complete** flag (true when all required tools have been called) and total call count.

**Why use it:** Ensures the AI does not skip important steps (e.g. never running the quality gate or security scan) before declaring work complete. Call before saying "done"; if `complete` is false, the hints tell you exactly which tools to call and why. Task types align expectations (e.g. security tasks require a security scan) so the checklist matches the kind of work being done.

---

### tapps_project_profile

**What it does:** Analyzes the project at `TAPPS_MCP_PROJECT_ROOT` to detect project type (web app, CLI tool, library, microservice, data pipeline), tech stack (languages, frameworks, databases), and structure (source layout, test framework, dependency management). Returns a profile with type, confidence score, detected technologies, and structural metadata.

**Why use it:** Gives the AI context about the project before making changes. Prevents applying wrong patterns (e.g. web patterns to a CLI tool). Use at session start alongside `tapps_server_info` for context-aware analysis.

---

### tapps_session_notes

**What it does:** Persists key decisions, constraints, and context across a session. Supports **save** (store a note with category and optional tags), **get** (retrieve notes, optionally filtered by category), and **clear** operations. Notes survive within a server session and are stored in `.tapps-mcp/session/`.

**Why use it:** In long sessions, the AI may forget decisions made earlier. Session notes let the AI save constraints ("user wants sync-only, no async") and retrieve them later so earlier context is not lost. Use throughout the session to record and recall important decisions.

---

### tapps_impact_analysis

**What it does:** Analyzes a Python file to determine its impact on the codebase. Returns the file's imports, what other files import it (dependents), exported symbols, and a dependency depth estimate. Accepts an optional `change_description` to scope the analysis.

**Why use it:** Before modifying a file, understand what else could break. Use when refactoring, renaming, or changing public APIs so the AI knows which downstream files may need updates.

---

### tapps_report

**What it does:** Generates a quality report for one or more scored files. Supports **json**, **markdown**, and **html** output formats. Combines scoring results, gate results, and optional metadata into a single structured report.

**Why use it:** Produces a human-readable summary of quality analysis. Use after scoring and gating to give the user a clear, formatted overview of code quality status.

---

### tapps_upgrade

**What it does:** Validates and refreshes all TappsMCP-generated files in a project after upgrading the server. Detects the platform (Claude Code, Cursor, or both) from existing config files and upgrades AGENTS.md (via smart-merge), platform rules, hooks, agents, skills, and settings. Uses `upgrade_mode` internally so custom command paths (e.g. PyInstaller exe) are never overwritten. Accepts optional `platform`, `force`, and `dry_run` parameters.

**Why use it:** After upgrading TappsMCP (`pip install -U tapps-mcp`), generated files may be outdated — missing new tools, stale hook scripts, or old AGENTS.md sections. Call `tapps_upgrade(dry_run=true)` to preview what would change, then `tapps_upgrade()` to apply updates. This is the MCP-tool equivalent of the `tapps-mcp upgrade` CLI command, usable from within an AI session without dropping to a terminal.

---

### tapps_doctor

**What it does:** Runs a suite of diagnostic checks and returns structured results. Checks include: binary availability on PATH, MCP config files for Claude Code (user and project), Cursor, and VS Code, CLAUDE.md and Cursor rules presence, AGENTS.md version and completeness, `.claude/settings.json` permission entries, hook files, and installed quality tools (ruff, mypy, bandit, radon, vulture, pip-audit). Returns per-check pass/fail with messages and remediation hints, plus aggregated `pass_count`, `fail_count`, and `all_passed`.

**Why use it:** When TappsMCP tools are not working as expected — permission prompts, missing tools, degraded results — run `tapps_doctor()` to identify configuration issues. The structured output pinpoints exactly what needs fixing and suggests the command to fix it.

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

### Environment variables

| Variable | Description |
|----------|-------------|
| **TAPPS_MCP_PROJECT_ROOT** | Restrict file operations to this directory (recommended for security). If unset, current working directory is used. |
| **TAPPS_MCP_HOST_PROJECT_ROOT** | Optional. Host path mapping for Docker/remote setups. When set, absolute paths from the IDE are mapped to the project root. |
| **TAPPS_MCP_CONTEXT7_API_KEY** | Optional. Used by `tapps_lookup_docs` for live Context7 API fetches; cache still works without it. |
| **TAPPS_MCP_QUALITY_PRESET** | Override quality preset (`standard`, `strict`, `framework`). Default: `standard`. |
| **TAPPS_MCP_LOG_LEVEL** | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). Default: `INFO`. |

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

```bash
# Install with dev dependencies
uv sync

# Tests (unit + integration)
uv run pytest tests/ -v

# Coverage
uv run pytest tests/ --cov=tapps_mcp --cov-report=term-missing

# Type checking
uv run mypy --strict src/tapps_mcp/

# Linting
uv run ruff check src/
uv run ruff format --check src/
```

Run all commands above from the **repository root** after `uv sync`. If you see `ModuleNotFoundError: No module named 'tapps_mcp'`, install the package first (`uv sync` or `pip install -e .`).

Pre-commit hooks are configured (`.pre-commit-config.yaml`). CI runs on push/PR to `master`/`main` (lint + tests on Ubuntu, Windows, macOS × Python 3.12, 3.13).

---

## Project layout

```
src/tapps_mcp/
├── __init__.py, cli.py, server.py      # Entry points and MCP server
├── server_helpers.py                   # Shared response builders
├── server_scoring_tools.py             # tapps_score_file, tapps_quality_gate, tapps_quick_check
├── server_pipeline_tools.py            # tapps_validate_changed, tapps_session_start, tapps_init,
│                                       #   tapps_upgrade, tapps_doctor
├── server_metrics_tools.py             # tapps_dashboard, tapps_stats, tapps_feedback, tapps_research
├── common/                             # Exceptions, logging, shared models, nudges
├── config/                             # Settings, default.yaml
├── security/                           # Path validation, IO guardrails, secrets, governance
├── scoring/                            # Score model, constants, scorer, dead code, dependency security
├── gates/                              # Gate presets, evaluator
├── tools/                              # Ruff, mypy, bandit, radon, vulture, pip-audit, parallel, checklist
├── knowledge/                          # Context7 client, cache, lookup, warming, RAG safety,
│                                       #   multi-provider support (providers/)
├── validators/                         # Dockerfile, docker-compose, WebSocket, MQTT, InfluxDB
├── experts/                            # Domain detector, engine, RAG, registry, confidence,
│                                       #   vector RAG, knowledge management, 119 knowledge files
├── project/                            # Project profiling, session notes, impact analysis, reports,
│                                       #   import graph, cycle detection, coupling metrics
├── adaptive/                           # Adaptive scoring, expert voting, weight distribution
├── metrics/                            # Collector, dashboard, alerts, trends, OTel export, feedback
├── prompts/                            # Workflow prompt templates and platform rule templates
├── distribution/                       # Setup generator (init, upgrade, doctor)
└── pipeline/                           # Pipeline orchestration, upgrade, handoff, initialization,
                                        #   AGENTS.md validation, platform generators
plugin/
└── cursor/                            # Ready-to-publish Cursor marketplace plugin
examples/
└── agent-sdk/                         # Claude Agent SDK integration examples (Python + TypeScript)
scripts/
└── validate-cursor-plugin.sh          # CI validation for plugin manifest
```

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
| [docs/planning/epics/README.md](docs/planning/epics/README.md) | Epic index, dependency graph, tool delivery timeline. |
| [CHANGELOG.md](CHANGELOG.md) | Release history following Keep a Changelog format. |
| [SECURITY.md](SECURITY.md) | Security policy and vulnerability reporting. |

**Roadmap (epics):** Foundation & Security ✅ · Core Quality MVP ✅ · Knowledge & Docs ✅ · Expert System ✅ · Project Context ✅ · Adaptive Learning ✅ · Distribution ✅ · Metrics & Dashboard ✅ · Pipeline Orchestration ✅ · Scoring Reliability ✅ · Expert + Context7 Integration ✅ · Retrieval Optimization ✅ · Platform Integration ✅ · Structured Outputs ✅ · Dead Code Detection ✅ · Dependency Vulnerability Scanning ✅ · Doc Backend Resilience ✅ · Circular Dependency Detection ✅ · MCP Upgrade Tool & Exe Path Handling ✅

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and how to submit changes.

---

## License

MIT - see [LICENSE](LICENSE).

