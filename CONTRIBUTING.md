# Contributing to TappsMCP

Thank you for your interest in contributing to TappsMCP! This guide covers everything you need to get started.

## Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** package manager (recommended)
- **Git**

## Development Setup

```bash
# Clone the repository
git clone https://github.com/tapps-mcp/tapps-mcp.git
cd TappMCP

# Install all packages (uv workspace)
uv sync --all-packages

# Verify setup
uv run tapps-mcp doctor
```

## Repository Structure

This is a **uv workspace monorepo** with three packages:

| Package | Path | Purpose |
|---|---|---|
| **tapps-core** | `packages/tapps-core/` | Shared infrastructure library |
| **tapps-mcp** | `packages/tapps-mcp/` | Code quality MCP server (30 tools) |
| **docs-mcp** | `packages/docs-mcp/` | Documentation MCP server (32 tools) |

Together, **tapps-mcp** + **docs-mcp** expose **62** deterministic MCP tools. `tapps-mcp doctor` reports resolved memory pipeline flags for the project under test.

## Running Tests

Run tests per-package to avoid conftest collisions:

```bash
# All tests per package
uv run pytest packages/tapps-core/tests/ -v      # ~2,000+ tests
uv run pytest packages/tapps-mcp/tests/ -v        # ~4,700+ tests
uv run pytest packages/docs-mcp/tests/ -v         # ~1,500+ tests

# Single test file
uv run pytest packages/tapps-mcp/tests/unit/test_scorer.py -v

# Single test by name
uv run pytest packages/tapps-mcp/tests/unit/test_scorer.py -k "test_score_empty_file" -v

# Skip slow subprocess-heavy tests
uv run pytest packages/tapps-mcp/tests/ -m "not slow" -v
```

## Code Quality

### Linting & Formatting

```bash
uv run ruff check packages/*/src/
uv run ruff format --check packages/*/src/
```

### Type Checking

```bash
uv run mypy --strict packages/tapps-mcp/src/tapps_mcp/
uv run mypy --strict packages/tapps-core/src/tapps_core/
```

### Self-Hosted Quality Pipeline

When TappsMCP's own MCP server is available, use it on this codebase:

1. Call `tapps_session_start` first
2. Use `tapps_quick_check` after editing Python files
3. Use `tapps_validate_changed` before declaring work complete
4. Call `tapps_checklist(task_type="feature")` as the final step

## Code Conventions

- **Python 3.12+** with `from __future__ import annotations` at the top of every file
- **Type annotations everywhere** -- `mypy --strict` must pass
- **`structlog`** for logging -- never `print()` or `logging` directly
- **`pathlib.Path`** for all file paths
- **Pydantic v2** models for configuration and data structures
- **`ruff`** for linting and formatting (line length: 100)
- **Async/await** for all tool handlers and external I/O
- All file operations through the path validator (`security/path_validator.py`)

## Adding a New MCP Tool

1. Add the handler in the appropriate `server_*.py` file using `@mcp.tool()`
2. Call `_record_call("tool_name")` at the top of the handler (for checklist tracking)
3. Register the tool in the checklist task map (`tools/checklist.py`)
4. Add to `AGENTS.md` and `README.md` tools reference
5. Add tests in `packages/tapps-mcp/tests/unit/` and optionally `tests/integration/`

## Submitting Changes

1. Create a feature branch from `master`:

   ```bash
   git checkout -b feature/my-feature
   ```

2. Make your changes and ensure tests pass:

   ```bash
   uv run pytest packages/<affected-package>/tests/ -v
   uv run ruff check packages/<affected-package>/src/
   uv run mypy --strict packages/<affected-package>/src/<package_name>/
   ```

3. Commit with a descriptive message (conventional commits preferred):

   ```bash
   git commit -m "feat: add my new feature"
   ```

4. Push and open a Pull Request against `master`

## Known Gotchas

- **mypy + `@mcp.tool()`**: The mcp SDK decorator is untyped. `pyproject.toml` has `disallow_untyped_decorators = false` for `tapps_mcp.server`.
- **Pydantic + `TYPE_CHECKING`**: Models using forward refs must import at runtime, not under `TYPE_CHECKING`. Use `# noqa: TC001`.
- **Windows testing**: Use `python -c "import time; time.sleep(N)"` for timeout tests.
- **Patching lazy imports**: Some imports happen inside tool handlers from `tapps_core`. Patch at source modules, not re-export wrappers.

## Reporting Issues

When reporting issues, please include:

- A clear and descriptive title
- Steps to reproduce the problem
- Expected behavior vs actual behavior
- Your environment (OS, Python version, MCP client)
- Relevant tool output or error messages
