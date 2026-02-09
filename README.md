# TappsMCP

**A Model Context Protocol (MCP) server that gives LLMs—Claude, Cursor, and others—deterministic code quality tools.** Score files, run security scans, enforce quality gates, look up docs, validate configs, and consult domain experts—all through structured tool calls instead of prompt injection.

[![CI](https://github.com/tapps-mcp/tapps-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/tapps-mcp/tapps-mcp/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Table of contents

- [What is TappsMCP?](#what-is-tappsmcp)
- [Features](#features)
- [Quick start](#quick-start)
- [Connecting your AI client](#connecting-your-ai-client)
- [Tools reference](#tools-reference)
- [Configuration](#configuration)
- [Optional tool dependencies](#optional-tool-dependencies)
- [Docker](#docker)
- [Development](#development)
- [Project layout](#project-layout)
- [Docs and roadmap](#docs-and-roadmap)
- [License](#license)

---

## What is TappsMCP?

LLMs writing code make repeatable mistakes: wrong APIs, missing tests, security issues, and inconsistent quality. TappsMCP moves **proven quality tooling** out of long system prompts and into a single MCP server. Any MCP-capable client (Cursor, Claude Desktop, custom hosts) can call the same tools and get **structured, deterministic results**—scores, gates, security findings, doc lookups, and expert advice—without burning context on framework instructions.

---

## Features

- **Code scoring** — 0–100 score across 7 categories (complexity, security, maintainability, test coverage, performance, structure, developer experience).
- **Security scanning** — Bandit + secret detection with redacted context.
- **Quality gates** — Pass/fail against configurable presets (standard, strict, framework).
- **Documentation lookup** — Up-to-date library docs via [Context7](https://context7.com) with fuzzy matching and local cache.
- **Config validation** — Dockerfile, docker-compose, WebSocket/MQTT/InfluxDB patterns against best practices.
- **Domain experts** — 16 built-in experts (security, testing, APIs, etc.) with RAG-backed answers and confidence scores.
- **Session checklist** — Track which tools were used so the AI doesn't skip required steps.
- **Path safety** — All file operations restricted to a configurable project root.

---

## Quick start

**Requirements:** Python 3.12+ and [uv](https://docs.astral.sh/uv/) (or pip).

```bash
# Clone and enter the repo
git clone https://github.com/tapps-mcp/tapps-mcp.git
cd tapps-mcp

# Install dependencies
uv sync

# Run via stdio (for Cursor, Claude Desktop, etc.)
uv run tapps-mcp serve

# Or run via HTTP (e.g. remote or container)
uv run tapps-mcp serve --transport http --port 8000
```

With **pip**: from the repo root run `pip install -e .`, then `tapps-mcp serve` (or `tapps-mcp serve --transport http --port 8000` for HTTP).

**One-liner with Docker:**

```bash
docker compose up --build -d
```

Server is available at **http://localhost:8000** (Streamable HTTP at `/mcp`). See [Docker](#docker) and [docs/DOCKER_DEPLOYMENT.md](docs/DOCKER_DEPLOYMENT.md) for details.

---

## Connecting your AI client

Point your MCP client at the TappsMCP server so the AI can call the tools.

### Cursor

1. Open **Settings → MCP** (or edit `.cursor/mcp.json` in your project).
2. Add the server (replace the path with your actual TappMCP repo path):

```json
{
  "mcpServers": {
    "tapps-mcp": {
      "command": "uv",
      "args": ["--directory", "C:\\cursor\\TappMCP", "run", "tapps-mcp", "serve"]
    }
  }
}
```

3. Restart or reload Cursor. The AI can then use tools like `tapps_score_file` and `tapps_quality_gate`.

### For AI assistants

When TappsMCP is connected, call **`tapps_server_info`** at session start (the response includes a short `recommended_workflow`). Use **`tapps_score_file`** (with `quick: true`) during edits; before declaring work complete, run **`tapps_score_file`** (full), **`tapps_quality_gate`**, and **`tapps_checklist`**. Use **`tapps_lookup_docs`** before writing code that uses an external library. See **[AGENTS.md](AGENTS.md)** for when to use each tool and the full workflow.

### Claude Desktop

Add to your Claude Desktop config (e.g. `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "tapps-mcp": {
      "command": "uv",
      "args": ["--directory", "/path/to/tapps-mcp", "run", "tapps-mcp", "serve"]
    }
  }
}
```

Restart Claude Desktop after changing the config.

### Suggested workflow for the AI

1. Call **`tapps_server_info`** at session start to see version and installed checkers.
2. Use **`tapps_score_file`** (with `quick: true`) during edit–lint–fix loops.
3. Use **`tapps_score_file`** (full) and **`tapps_quality_gate`** before marking work complete.
4. Call **`tapps_checklist`** to ensure no required steps were skipped.

---

## Tools reference

Quick index:

| Tool | One-line purpose |
|------|------------------|
| **tapps_server_info** | Discover server version, tools, checkers, and recommended workflow. |
| **tapps_score_file** | Score a Python file 0–100 across 7 quality categories. |
| **tapps_security_scan** | Run Bandit + secret detection on a Python file. |
| **tapps_quality_gate** | Pass/fail a file against a quality preset (standard/strict/framework). |
| **tapps_lookup_docs** | Fetch current documentation for a library (Context7 + cache). |
| **tapps_validate_config** | Validate Dockerfile, docker-compose, or infra configs. |
| **tapps_consult_expert** | Ask a domain expert and get RAG-backed answer with confidence. |
| **tapps_list_experts** | List the 16 built-in expert domains and their status. |
| **tapps_checklist** | See which tools were called this session and what is still missing. |

---

### tapps_server_info

**What it does:** Returns server metadata: name, version, MCP protocol version, project root, quality preset, and log level. Lists all available tool names and the status of external checkers (ruff, mypy, bandit, radon)—installed or not, with version or install hint. Also returns a short **`recommended_workflow`** string describing when to call which tools.

**Why use it:** Call once at session start so the AI (and any host) knows what this server can do, which checkers are available (and whether scoring will be degraded), and the intended workflow. Avoids guessing and ensures the rest of the session uses TappsMCP effectively.

---

### tapps_score_file

**What it does:** Scores a single Python file from 0–100 using up to seven categories: complexity (cyclomatic complexity), security (Bandit + heuristics), maintainability (maintainability index), test coverage (heuristic from test file presence), performance (nesting, loop size), structure (project layout), and developer experience (docs, tooling). Can run in **quick** mode (ruff-only, under ~500 ms) or full mode (ruff, mypy, bandit, radon in parallel). Optional **fix** mode (with quick) runs ruff with auto-fix before scoring. Returns per-category scores, weights, details, and up to 20 lint/type/security issues. Sets `degraded: true` when some checkers are missing and fallbacks are used.

**Why use it:** Gives an objective, repeatable quality signal instead of subjective "looks good." Use quick mode during edit–lint–fix loops for fast feedback; use full mode before considering work complete. The structured output is easy for the AI to interpret and act on (e.g. fix specific line numbers). Ensures quality is measured the same way regardless of model or prompt.

---

### tapps_security_scan

**What it does:** Runs a security-focused scan on a Python file: Bandit for common vulnerability patterns (e.g. SQL injection, hardcoded passwords, unsafe deserialization) and optional secret detection for API keys, tokens, and credentials. Returns counts by severity (critical, high, medium, low), lists of findings with location and message, and redacted context so sensitive snippets are not echoed. Indicates whether Bandit was available; if not, the response is marked degraded.

**Why use it:** Security issues are easy to introduce and hard to catch by eye. A dedicated scan surfaces real findings with severity so the AI (or human) can fix critical/high items first. Use when touching auth, I/O, or third-party integrations, or before any security-sensitive review. Redaction keeps secrets out of logs and context.

---

### tapps_quality_gate

**What it does:** Evaluates a Python file against a configurable quality preset. Runs full scoring (same as `tapps_score_file` full mode) then compares the result to thresholds for that preset: **standard** (e.g. overall ≥ 70), **strict** (e.g. ≥ 80), **framework** (e.g. ≥ 75 with higher bar on security). Returns pass/fail, overall score, per-category scores, thresholds used, and lists of failures and warnings with clear messages.

**Why use it:** Defines "good enough" in one place so work is not declared done until the bar is met. Prevents the AI from saying "done" when the file would fail CI or team standards. Call before marking a task complete; if it fails, the response tells you what to improve. Presets let different projects or roles use different strictness without changing prompts.

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

### tapps_list_experts

**What it does:** Returns the list of all 16 built-in expert domains. For each expert it provides an id, display name, short description, and knowledge-base status (e.g. how many knowledge files are loaded). No parameters required.

**Why use it:** Lets the AI (or host) discover which domains exist before calling `tapps_consult_expert`. Use at session start or when the user asks "what can the experts help with?" so the right domain can be chosen and the right expert consulted.

---

### tapps_checklist

**What it does:** Tracks which TappsMCP tools have been called in the current server session and evaluates that against a **task type**: `feature`, `bugfix`, `refactor`, `security`, or `review`. For that task type, some tools are required, some recommended, some optional. The tool returns the list of called tools, missing required/recommended/optional tools, and for each missing tool a short **reason** (in `missing_required_hints`, `missing_recommended_hints`, `missing_optional_hints`) explaining why to call it. It also returns a **complete** flag (true when all required tools have been called) and total call count.

**Why use it:** Ensures the AI does not skip important steps (e.g. never running the quality gate or security scan) before declaring work complete. Call before saying "done"; if `complete` is false, the hints tell you exactly which tools to call and why. Task types align expectations (e.g. security tasks require a security scan) so the checklist matches the kind of work being done.

---

### Scoring categories (tapps_score_file)

| Category | Weight | Description |
|----------|--------|-------------|
| complexity | 0.20 | Cyclomatic complexity (radon cc / AST fallback) |
| security | 0.20 | Bandit + pattern heuristics |
| maintainability | 0.15 | Maintainability index (radon mi / AST fallback) |
| test_coverage | 0.10 | Heuristic from matching test file existence |
| performance | 0.15 | AST: nested loops, large functions, deep nesting |
| structure | 0.10 | Project layout (pyproject.toml, tests/, README, .git) |
| devex | 0.10 | Developer experience (docs, AGENTS.md, tooling config) |

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

Custom scoring weights:

```yaml
scoring_weights:
  complexity: 0.20
  security: 0.20
  maintainability: 0.15
  test_coverage: 0.10
  performance: 0.15
  structure: 0.10
  devex: 0.10
```

### Environment variables

| Variable | Description |
|----------|-------------|
| **TAPPS_MCP_PROJECT_ROOT** | Restrict file operations to this directory (recommended for security). If unset, current working directory is used. |
| **TAPPS_MCP_CONTEXT7_API_KEY** | Optional. Used by `tapps_lookup_docs` for live Context7 API fetches; cache still works without it. |

---

## Optional tool dependencies

Best results come with these tools installed; the server degrades gracefully without them.

| Tool | Purpose | Install |
|------|---------|--------|
| ruff | Linting + formatting | `pip install ruff` or `uv add ruff` |
| mypy | Type checking | `pip install mypy` or `uv add mypy` |
| bandit | Security scanning | `pip install bandit` or `uv add bandit` |
| radon | Complexity + maintainability | `pip install radon` or `uv add radon` |

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
├── common/                             # Exceptions, logging, shared models
├── config/                             # Settings, default.yaml
├── security/                           # Path validation, IO guardrails, secrets, governance
├── scoring/                            # Score model, constants, scorer
├── gates/                              # Gate presets, evaluator
├── tools/                              # Ruff, mypy, bandit, radon, parallel, checklist
├── knowledge/                          # Context7 client, cache, lookup, warming, RAG safety
├── validators/                         # Dockerfile, docker-compose, WebSocket, MQTT, InfluxDB
└── experts/                            # Domain detector, engine, RAG, registry, confidence
```

---

## Docs and roadmap

| Doc | Description |
|-----|-------------|
| [docs/TAPPS_MCP_SETUP_AND_USE.md](docs/TAPPS_MCP_SETUP_AND_USE.md) | Setup and use summary (Cursor, Claude, tools workflow). |
| [docs/DOCKER_DEPLOYMENT.md](docs/DOCKER_DEPLOYMENT.md) | Docker build, run, env vars, and client connection. |
| [docs/CLAUDE_FULL_ACCESS_SETUP.md](docs/CLAUDE_FULL_ACCESS_SETUP.md) | Grant Claude Code full access (no permission prompts). |
| [docs/planning/TAPPS_MCP_PLAN.md](docs/planning/TAPPS_MCP_PLAN.md) | Architecture and design rationale. |
| [docs/planning/epics/README.md](docs/planning/epics/README.md) | Epic index, dependency graph, tool delivery timeline. |

**Roadmap (epics):** Foundation & Security ✅ · Core Quality MVP ✅ · Knowledge & Docs ✅ · Expert System ✅ · Project Context · Adaptive Learning · Distribution · Metrics & Dashboard

---

## License

MIT (see `pyproject.toml`).

