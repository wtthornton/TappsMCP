# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is TappsMCP?

TappsMCP is an **MCP server** providing deterministic code quality tools to LLMs and AI coding assistants. It scores Python files, runs security scans, enforces quality gates, looks up library docs, validates configs, and consults domain experts — all via structured MCP tool calls. Any MCP-capable client (Claude Code, Cursor, VS Code Copilot) can use it. If you are a consuming project, see [AGENTS.md](AGENTS.md) instead.

## Development commands

```bash
# Install dependencies
uv sync

# Run all tests (2282+ tests)
uv run pytest tests/ -v

# Run a single test file
uv run pytest tests/unit/test_scorer.py -v

# Run a single test by name
uv run pytest tests/unit/test_scorer.py -k "test_score_empty_file" -v

# Run with coverage (80% minimum, fail_under enforced)
uv run pytest tests/ --cov=tapps_mcp --cov-report=term-missing

# Skip slow subprocess-heavy tests
uv run pytest tests/ -m "not slow" -v

# Type checking (strict mode)
uv run mypy --strict src/tapps_mcp/

# Linting and formatting
uv run ruff check src/
uv run ruff format --check src/

# Run the MCP server (stdio)
uv run tapps-mcp serve

# CLI utilities
uv run tapps-mcp doctor           # diagnose config issues
uv run tapps-mcp upgrade --dry-run  # preview generated file updates
```

## Architecture

### Server module split

The MCP server is split across four files to stay under complexity limits. All share the same `mcp` FastMCP instance created in `server.py`:

- **`server.py`** — Creates the `FastMCP("TappsMCP")` instance, registers MCP resources/prompts, and imports the other three modules which register their tools on the shared `mcp` object.
- **`server_scoring_tools.py`** — `tapps_score_file`, `tapps_quality_gate`, `tapps_quick_check`
- **`server_pipeline_tools.py`** — `tapps_validate_changed`, `tapps_session_start`, `tapps_init`, `tapps_upgrade`, `tapps_doctor`
- **`server_metrics_tools.py`** — `tapps_dashboard`, `tapps_stats`, `tapps_feedback`, `tapps_research`
- **`server_helpers.py`** — Shared utilities: response builders, singleton caches (`_get_scorer()`, `_get_settings()`)

### Tool registration flow

To add a new MCP tool:
1. Add the handler in the appropriate `server_*.py` file using `@mcp.tool()`
2. Call `_record_call("tool_name")` at the top of the handler (for checklist tracking)
3. Register the tool in the checklist task map (`tools/checklist.py`)
4. Add to AGENTS.md and README.md tools reference
5. Add tests in `tests/unit/` and optionally `tests/integration/`

### Dual CLI / MCP tool pattern

Several features exist as both a CLI command (`cli.py` via Click) and an MCP tool. The CLI entry points delegate to shared logic:
- `tapps-mcp init` (CLI) → `pipeline/init.py` ← `tapps_init` (MCP tool in `server_pipeline_tools.py`)
- `tapps-mcp upgrade` (CLI) → `distribution/setup_generator.py` / `pipeline/upgrade.py` ← `tapps_upgrade` (MCP tool)
- `tapps-mcp doctor` (CLI) → `distribution/doctor.py` ← `tapps_doctor` (MCP tool)

### Caching and singletons

Three module-level caches require reset in tests (done by autouse fixture in `tests/conftest.py`):
- **Settings**: `load_settings()` in `config/settings.py` — cached singleton, reset via `_reset_settings_cache()`
- **CodeScorer**: `_get_scorer()` in `server_helpers.py` — cached singleton, reset via `_reset_scorer_cache()`
- **Tool detection**: `detect_installed_tools()` in `tools/tool_detection.py` — reset via `_reset_tools_cache()`

### Scoring pipeline

`scoring/scorer.py` orchestrates the 7-category scoring engine. In full mode, `tools/parallel.py` runs ruff, mypy, bandit, and radon concurrently via `asyncio.gather`. Quick mode runs ruff only. When external tools are missing, AST-based fallbacks in `scoring/scorer.py` produce degraded results. The `tools/` directory has one module per external checker (ruff, mypy, bandit, radon, vulture, pip-audit) plus `ruff_direct.py` and `radon_direct.py` for library-mode execution.

### Security model

All file I/O goes through `security/path_validator.py`, which sandboxes operations to `TAPPS_MCP_PROJECT_ROOT`. The `security/` package also handles secret scanning, IO guardrails, and governance checks.

### Expert system

17 domain experts in `experts/` with 135+ curated knowledge markdown files under `experts/knowledge/`. The `experts/engine.py` uses keyword-based RAG (or optional vector RAG with faiss). All retrieved content passes through `knowledge/rag_safety.py` for prompt injection filtering.

### Platform generation

`pipeline/platform_generators.py` generates hooks, agents, skills, rules, and CI workflows for Claude Code and Cursor. `pipeline/agents_md.py` handles AGENTS.md smart-merge (preserving custom sections while updating tool definitions).

## Code conventions

- **Python 3.12+** — `from __future__ import annotations` at the top of every file
- **Type annotations everywhere** — `mypy --strict` must pass
- **`structlog`** for logging — never `print()` or `logging` directly
- **`pathlib.Path`** for all file paths
- **Pydantic v2** models for configuration and data structures
- **`ruff`** for linting and formatting (line length: 100)
- **Async/await** for all tool handlers and external I/O
- All file operations through the path validator (`security/path_validator.py`)

## Known gotchas

- **mypy + `@mcp.tool()`**: The mcp SDK decorator is untyped. `pyproject.toml` has `disallow_untyped_decorators = false` for `tapps_mcp.server` specifically.
- **mypy + optional deps**: `ignore_missing_imports = true` covers mcp, faiss, numpy, sentence_transformers, radon. Don't add redundant `# type: ignore[import-untyped]` — mypy won't flag those, and the comments become "unused-ignore" errors.
- **Pydantic + `TYPE_CHECKING`**: Models using forward refs in field types must import at runtime, not under `TYPE_CHECKING`. Use `# noqa: TC001` to suppress ruff.
- **`structlog.get_logger()`**: Returns `Any` — use `# type: ignore[no-any-return]` in the wrapper.
- **Ruff RUF012**: Mutable class-level attributes need `ClassVar` annotation.
- **Windows testing**: Use `python -c "import time; time.sleep(N)"` for timeout tests — Git Bash intercepts `cmd /c timeout`.
- **Patching lazy imports in server.py**: Some imports (e.g., `KBCache`, `LookupEngine`) happen inside tool handlers. Patch them at their source modules, not at `tapps_mcp.server`.

## Self-hosted quality pipeline

When TappsMCP's own MCP server is available in your session, use it on this codebase:

1. Call `tapps_session_start` first
2. Use `tapps_quick_check` after editing Python files
3. Use `tapps_validate_changed` before declaring work complete
4. Call `tapps_checklist(task_type="feature")` or appropriate type before finishing

## Important context

- TappsMCP is a **tool for other projects** — changes should consider how consuming projects will be affected
- The `tapps_init` MCP tool bootstraps TappsMCP in consuming projects (creates AGENTS.md, TECH_STACK.md, platform rules, hooks, agents, skills)
- All tools are **deterministic** — no LLM calls in the tool chain; same input produces same output
- When external checkers are missing, tools fall back to AST-based analysis and mark results as `degraded: true`
