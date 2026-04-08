# Agent Build Instructions - TappsMCP

## Project Setup
```bash
# Install all packages (uv workspace monorepo)
uv sync --all-packages
```

## Running Tests

> **EPIC-BOUNDARY ONLY:** Do NOT run tests mid-epic. Only run at epic boundaries
> (last `- [ ]` in a `##` section of fix_plan.md) or before EXIT_SIGNAL: true.
> Mid-epic: set `TESTS_STATUS: DEFERRED` and move on.

```bash
# Run tests per package (recommended -- avoids conftest collisions)
uv run pytest packages/tapps-core/tests/ -v
uv run pytest packages/tapps-mcp/tests/ -v
uv run pytest packages/docs-mcp/tests/ -v

# Run tests excluding slow integration tests (fast local feedback)
uv run pytest packages/tapps-mcp/tests/ -m "not slow" -v

# Run a single test file
uv run pytest packages/tapps-mcp/tests/unit/test_scorer.py -v
```

## Type Checking
```bash
uv run mypy --strict packages/tapps-mcp/src/tapps_mcp/
uv run mypy --strict packages/tapps-core/src/tapps_core/
```

## Linting and Formatting
```bash
uv run ruff check packages/*/src/
uv run ruff format --check packages/*/src/
```

## Run the MCP Servers
```bash
uv run tapps-mcp serve           # TappsMCP (code quality)
uv run docsmcp serve             # DocsMCP (documentation)
```

## Project Structure
- **tapps-core** (`packages/tapps-core/`): Shared infrastructure library
- **tapps-mcp** (`packages/tapps-mcp/`): Code quality MCP server (26 tools)
- **docs-mcp** (`packages/docs-mcp/`): Documentation MCP server (32 tools)
- **tapps-brain** (external git dep): Standalone memory system

## Code Conventions
- Python 3.12+ with `from __future__ import annotations`
- `structlog` for logging (NEVER bare `logging` or `print()`)
- `pathlib.Path` for all file paths
- Pydantic v2 models for config/data
- `ruff` for linting (line length: 100)
- Async/await for tool handlers
- All file ops through `security/path_validator.py`

## Key Learnings
- FastMCP constructor: `FastMCP("TappsMCP")` -- no `version` kwarg
- Windows tests: Use `python -c "import time; time.sleep(N)"` for timeout tests
- Patch lazy imports at source modules, not re-exports
- mypy `ignore_missing_imports` covers optional deps -- don't add redundant `# type: ignore`

## Quality Standards

### Git Workflow
- Use conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`
- Commit with descriptive messages after each task
- Mark items complete in .ralph/fix_plan.md upon completion

### Feature Completion Checklist (EPIC BOUNDARY ONLY)

**Mid-epic task:**
- [ ] Implementation matches the acceptance criteria in fix_plan.md
- [ ] Changes committed with descriptive message
- [ ] fix_plan.md updated: `- [ ]` -> `- [x]`

**Epic boundary (last task in section):**
- [ ] All above, plus:
- [ ] `uv run pytest packages/tapps-mcp/tests/ -m "not slow" -v` passes
- [ ] `uv run ruff check packages/*/src/` passes
- [ ] .ralph/AGENT.md updated (if new patterns introduced)
