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
- **Session checklist** — Track which tools were used so the AI doesn’t skip required steps.
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

| Tool | Purpose |
|------|--------|
| **tapps_server_info** | Server version, available tools, installed checkers (ruff, mypy, bandit, radon), and configuration. |
| **tapps_score_file** | Score a Python file 0–100 across 7 categories. Options: `quick` (ruff-only, &lt;500 ms), `fix` (apply ruff fixes then score). |
| **tapps_security_scan** | Bandit + secret detection; returns findings with redacted context. |
| **tapps_quality_gate** | Pass/fail vs thresholds. Presets: `standard` (70), `strict` (80), `framework` (75). |
| **tapps_lookup_docs** | Look up current docs for a library (Context7 + cache). Args: `library`, `topic`, `mode` (code/info). Optional: set `CONTEXT7_API_KEY` for live fetch. |
| **tapps_validate_config** | Validate Dockerfile, docker-compose, or WebSocket/MQTT/InfluxDB configs. `config_type`: `auto` or explicit type. |
| **tapps_consult_expert** | Ask a domain expert; auto-routes or use `domain` override. Returns answer, confidence, and sources. |
| **tapps_list_experts** | List all 16 domain experts and their knowledge-base status. |
| **tapps_checklist** | Show which tools were called this session and what’s missing. Task types: `feature`, `bugfix`, `refactor`, `security`, `review`. |

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
| **CONTEXT7_API_KEY** | Optional. Used by `tapps_lookup_docs` for live Context7 API fetches; cache still works without it. |

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
