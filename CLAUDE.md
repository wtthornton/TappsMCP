# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## What is TappsMCP?

TappsMCP is an **MCP server** providing deterministic code quality tools to LLMs and AI coding assistants. It scores Python files, runs security scans, enforces quality gates, looks up library docs, validates configs, and consults domain experts -- all via structured MCP tool calls. Any MCP-capable client (Claude Code, Cursor, VS Code Copilot) can use it. If you are a consuming project, see [AGENTS.md](AGENTS.md) instead.

## Repository structure

This is a **uv workspace monorepo** with three packages:

| Package | Path | Purpose |
|---|---|---|
| **tapps-core** | `packages/tapps-core/` | Shared infrastructure library (config, security, logging, knowledge, memory, experts, metrics, adaptive) |
| **tapps-mcp** | `packages/tapps-mcp/` | Code quality MCP server (29 tools, 31 actions) |
| **docs-mcp** | `packages/docs-mcp/` | Documentation MCP server (22 tools) |

tapps-mcp re-exports from tapps-core for backward compatibility (`from tapps_mcp.config import load_settings` still works).

For detailed module maps and internal architecture, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Development commands

```bash
# Install all packages
uv sync --all-packages

# Run tests per package (recommended -- avoids conftest collisions)
uv run pytest packages/tapps-core/tests/ -v      # 1,700+ tests
uv run pytest packages/tapps-mcp/tests/ -v        # 4,200+ tests
uv run pytest packages/docs-mcp/tests/ -v         # 1,300+ tests

# Run a single test file or by name
uv run pytest packages/tapps-mcp/tests/unit/test_scorer.py -v
uv run pytest packages/tapps-mcp/tests/unit/test_scorer.py -k "test_score_empty_file" -v

# Coverage (80% minimum, fail_under enforced)
uv run pytest packages/tapps-mcp/tests/ --cov=tapps_mcp --cov-report=term-missing

# Type checking (strict mode)
uv run mypy --strict packages/tapps-mcp/src/tapps_mcp/
uv run mypy --strict packages/tapps-core/src/tapps_core/

# Linting and formatting
uv run ruff check packages/*/src/
uv run ruff format --check packages/*/src/

# Run the MCP servers (stdio)
uv run tapps-mcp serve           # TappsMCP (code quality)
uv run docsmcp serve             # DocsMCP (documentation)

# CLI utilities
uv run tapps-mcp doctor           # diagnose config issues
uv run tapps-mcp upgrade --dry-run  # preview generated file updates
uv run tapps-mcp build-plugin      # generate Claude Code plugin directory
uv run docsmcp doctor             # DocsMCP diagnostics

# Benchmark subsystem
uv run tapps-mcp benchmark run|analyze|report
uv run tapps-mcp template optimize|ablate|compare|history
uv run tapps-mcp benchmark tools report|rank|calibrate
```

## Common workflows

### Adding a new MCP tool
1. Add handler in appropriate `server_*.py` using `@mcp.tool()`
2. Call `_record_call("tool_name")` at top of handler
3. Register in checklist task map (`tools/checklist.py`)
4. Add to AGENTS.md and README.md
5. Add tests in `packages/tapps-mcp/tests/unit/`

### Adding an expert domain
1. Create knowledge files in `experts/knowledge/<domain>/`
2. Register in `experts/registry.py`
3. Add domain hints to AGENTS.md

### Running the quality pipeline on this codebase
1. Call `tapps_session_start` first
2. Use `tapps_quick_check` after editing Python files
3. Use `tapps_validate_changed` before declaring work complete
4. Call `tapps_checklist(task_type="feature")` before finishing

## Code conventions

- **Python 3.12+** -- `from __future__ import annotations` at top of every file
- **Type annotations everywhere** -- `mypy --strict` must pass
- **`structlog`** for logging -- never `print()` or `logging` directly
- **`pathlib.Path`** for all file paths
- **Pydantic v2** models for configuration and data structures
- **`ruff`** for linting and formatting (line length: 100)
- **Async/await** for all tool handlers and external I/O
- All file operations through the path validator (`security/path_validator.py`)

## Known gotchas

- **mypy + `@mcp.tool()`**: The mcp SDK decorator is untyped. `pyproject.toml` has `disallow_untyped_decorators = false` for `tapps_mcp.server`.
- **mypy + optional deps**: `ignore_missing_imports = true` covers mcp, faiss, numpy, sentence_transformers, radon. Don't add redundant `# type: ignore[import-untyped]`.
- **Pydantic + `TYPE_CHECKING`**: Models using forward refs in field types must import at runtime, not under `TYPE_CHECKING`. Use `# noqa: TC001`.
- **`structlog.get_logger()`**: Returns `Any` -- use `# type: ignore[no-any-return]` in wrapper.
- **Ruff RUF012**: Mutable class-level attributes need `ClassVar` annotation.
- **Windows testing**: Use `python -c "import time; time.sleep(N)"` for timeout tests -- Git Bash intercepts `cmd /c timeout`.
- **Patching lazy imports**: Some imports happen inside tool handlers from `tapps_core`. Patch at source modules, not `tapps_mcp.server`.

## Important context

- TappsMCP is a **tool for other projects** -- changes should consider how consuming projects will be affected
- The `tapps_init` MCP tool bootstraps TappsMCP in consuming projects (creates AGENTS.md, TECH_STACK.md, platform rules, hooks, agents, skills)
- All tools are **deterministic** -- no LLM calls in the tool chain; same input produces same output
- When external checkers are missing, tools fall back to AST-based analysis and mark results as `degraded: true`
