# CLAUDE.md — Instructions for AI assistants working on TappsMCP

This file provides context and best practices for AI assistants (Claude Code, Cursor, etc.) working on the **TappsMCP** codebase itself. If you are a consuming project that has TappsMCP installed as a tool, see [AGENTS.md](AGENTS.md) instead.

---

## What is TappsMCP?

TappsMCP is a **Model Context Protocol (MCP) server** that provides deterministic code quality tools to LLMs and AI coding assistants. It is a **toolset designed to help other projects and LLMs produce higher-quality code** by providing structured, repeatable quality analysis instead of relying on prompt injection.

TappsMCP gives any MCP-capable client (Claude Code, Cursor, VS Code Copilot, custom hosts) access to:

- Code scoring (0-100 across 7 categories)
- Security scanning (Bandit + secret detection)
- Quality gates (pass/fail against configurable presets)
- Dead code detection (Vulture with confidence scoring)
- Dependency vulnerability scanning (pip-audit)
- Circular dependency detection (import graph + coupling metrics)
- Documentation lookup (Context7 + multi-provider fallback + cache)
- Config validation (Dockerfile, docker-compose, infra)
- Domain expert consultation (16 built-in experts with RAG)
- Project profiling, impact analysis, session management
- Metrics, dashboards, and adaptive learning
- Structured outputs (machine-parseable JSON for all scoring tools)

---

## Project structure

```
src/tapps_mcp/
  __init__.py, cli.py, server.py              # Entry points and MCP server
  server_helpers.py                            # Shared response builders
  server_scoring_tools.py                      # Score file, quality gate, quick check
  server_pipeline_tools.py                     # Pipeline tools (validate_changed, session_start, init)
  server_metrics_tools.py                      # Dashboard, stats, feedback, research
  common/                                      # Exceptions, logging, shared models, nudges
  config/                                      # Settings (Pydantic), default.yaml
  security/                                    # Path validation, IO guardrails, secrets, governance
  scoring/                                     # Score model, constants, scorer, dead code, dependency security
  gates/                                       # Gate presets, evaluator
  tools/                                       # Ruff, mypy, bandit, radon, vulture, pip-audit, parallel, checklist
  knowledge/                                   # Context7 client, cache, lookup, fuzzy matcher, warming,
                                               #   multi-provider support (providers/)
  validators/                                  # Dockerfile, docker-compose, WebSocket, MQTT, InfluxDB
  experts/                                     # Domain experts, RAG engine, knowledge files (119 .md)
  project/                                     # Profiler, session notes, impact analysis, reports,
                                               #   import graph, cycle detection, coupling metrics
  adaptive/                                    # Adaptive scoring, expert voting, weight distribution
  metrics/                                     # Collector, dashboard, alerts, trends, OTel, feedback
  prompts/                                     # Workflow prompt templates and platform rule templates
  distribution/                                # Setup generator (init, upgrade, doctor)
  pipeline/                                    # Pipeline orchestration, AGENTS.md validation, platform generators
```

---

## Development commands

```bash
# Install dependencies
uv sync

# Run the MCP server (stdio)
uv run tapps-mcp serve

# Run all tests (2230+ tests)
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ --cov=tapps_mcp --cov-report=term-missing

# Type checking (strict mode)
uv run mypy --strict src/tapps_mcp/

# Linting and formatting
uv run ruff check src/
uv run ruff format --check src/

# Upgrade generated files after version bump
uv run tapps-mcp upgrade --dry-run   # preview changes
uv run tapps-mcp upgrade             # apply updates

# Diagnose configuration issues
uv run tapps-mcp doctor
```

---

## Code conventions

- **Python 3.12+** required
- `from __future__ import annotations` at the top of every file
- Type annotations everywhere — `mypy --strict` must pass
- Use `structlog` for logging (never `print()` or `logging` directly)
- Use `pathlib.Path` for all file paths
- Pydantic v2 models for configuration and data structures
- `ruff` for both linting and formatting (line length: 100)
- Async/await for all tool handlers and external I/O
- All file operations must go through the path validator (`security/path_validator.py`)

---

## Architecture principles

- **MCP-first**: All tools are exposed via MCP `@mcp.tool()` decorators in `server.py`
- **Deterministic**: Tools produce the same output for the same input — no LLM calls in the tool chain
- **Graceful degradation**: When external checkers (ruff, mypy, bandit, radon) are missing, fall back to AST-based analysis and mark results as `degraded: true`
- **Path safety**: All file operations are sandboxed to `TAPPS_MCP_PROJECT_ROOT`
- **Cache-first**: Context7 lookups use stale-while-revalidate caching
- **RAG safety**: All retrieved content is checked for prompt injection patterns

---

## Key files to know

| File | Purpose |
|------|---------|
| `server.py` | Main MCP server — registers all tools, resources, prompts |
| `server_scoring_tools.py` | `tapps_score_file`, `tapps_quality_gate`, `tapps_quick_check` |
| `server_pipeline_tools.py` | `tapps_validate_changed`, `tapps_session_start`, `tapps_init` |
| `server_metrics_tools.py` | `tapps_dashboard`, `tapps_stats`, `tapps_feedback`, `tapps_research` |
| `scoring/scorer.py` | Core 7-category scoring engine |
| `tools/parallel.py` | Parallel execution of ruff, mypy, bandit, radon, vulture |
| `config/settings.py` | All settings with env var overrides (`TAPPS_MCP_*`) |
| `knowledge/lookup.py` | Context7 documentation lookup with SWR cache |
| `experts/engine.py` | Expert consultation RAG engine |
| `pipeline/init.py` | `tapps_init` bootstrap logic |
| `pipeline/agents_md.py` | AGENTS.md validation and smart-merge logic |
| `pipeline/platform_generators.py` | Hooks, agents, skills, CI workflow generation |
| `distribution/setup_generator.py` | `tapps-mcp init` and `tapps-mcp upgrade` CLI |
| `distribution/doctor.py` | `tapps-mcp doctor` diagnostic checks |

---

## Testing

- Tests are in `tests/` with `tests/unit/` and `tests/integration/` subdirectories
- Use `pytest-asyncio` with `asyncio_mode = "auto"`
- Coverage target: 80% minimum (`fail_under = 80` in pyproject.toml)
- When adding a new tool or feature, add corresponding tests
- Run the full suite before committing: `uv run pytest tests/ -v`

---

## TappsMCP TAPPS pipeline integration

When TappsMCP's own MCP server is available in your session, use it on this codebase:

1. Call `tapps_session_start` first
2. Use `tapps_quick_check` after editing Python files
3. Use `tapps_validate_changed` before declaring work complete
4. Call `tapps_checklist(task_type="feature")` or appropriate type before finishing

---

## Important notes

- TappsMCP is a **tool for other projects** — changes should consider how consuming projects will be affected
- The `tapps_init` MCP tool bootstraps TappsMCP in consuming projects (creates AGENTS.md, TECH_STACK.md, platform rules)
- The `tapps-mcp init` CLI generates MCP host configuration for Claude Code, Cursor, or VS Code
- The `tapps-mcp upgrade` CLI validates and updates all generated files after a TappsMCP version upgrade
- The `tapps-mcp doctor` CLI diagnoses configuration and connectivity issues
- All 18 epics are complete (0-17) — see `docs/planning/epics/README.md` for the full history
