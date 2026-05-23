# Contributing to TappsMCP

Thank you for your interest in contributing to TappsMCP! This guide covers everything you need to get started.

## Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** package manager (recommended)
- **Git**

## Development Setup

```bash
# Clone the repository
git clone https://github.com/wtthornton/TappsMCP.git
cd tapps-mcp

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
| **tapps-mcp** | `packages/tapps-mcp/` | Code quality MCP server (32 tools) |
| **docs-mcp** | `packages/docs-mcp/` | Documentation MCP server (38 tools) |

Together, **tapps-mcp** + **docs-mcp** expose **70** deterministic MCP tools. `tapps-mcp doctor` reports resolved memory pipeline flags for the project under test.

## Running Tests

Run tests per-package to avoid conftest collisions:

```bash
# All tests per package
uv run pytest packages/tapps-core/tests/ -v      # ~960+ tests
uv run pytest packages/tapps-mcp/tests/ -v        # ~3,790+ tests
uv run pytest packages/docs-mcp/tests/ -v         # ~2,170+ tests

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

## Tool Versioning

The MCP specification does not include tool-level versioning — it only date-stamps protocol revisions (most recent as of 2025-11-25). When a change would break existing callers (parameter rename, return-type change, removed field), use an additive rename instead:

1. Ship the new behavior under `<tool_name>_v2` (or `_v3`, etc.).
2. Keep the old name live and mark it deprecated (see [Deprecation Playbook](#deprecation-playbook) below).
3. Remove the old name only after the minimum deprecation window has elapsed.

**Example**: `tapps_memory_recall` gained a `tier` filter in v3.12.0. Because the filter changed default semantics, the new tool shipped as `tapps_memory_recall_v2`; the old tool logs a deprecation warning on every call and will be removed at the next minor release.

This rule applies to both `tapps-mcp` and `docs-mcp` tools.

## Deprecation Playbook

Removing or breaking a tool affects every downstream project that has installed TappsMCP. Follow this three-phase pattern:

### Phase 1 — Soft deprecation (ship alongside the replacement)

1. Add a `DEPRECATED: use <replacement> instead` note to the tool's docstring and `AGENTS.md` entry.
2. Emit a structured deprecation notice in the tool response:
   ```json
   { "deprecated": true, "message": "Use <replacement> instead.", "result": <original_result> }
   ```
3. Announce in `CHANGELOG.md` with the earliest planned removal version (90 days / next minor at earliest).

### Phase 2 — Surface reduction (optional, if usage is high)

1. Update `tapps_checklist` to flag the old tool name as a soft violation so agents are nudged away.
2. Add a `brain_record_event(event_type="tool_deprecated", tool=<name>)` call inside the handler so the feedback flywheel tracks declining usage.

### Phase 3 — Hard removal

1. Remove the handler, `@mcp.tool()` registration, checklist entry, and `AGENTS.md` reference.
2. Create a migration doc at `docs/migrations/<tool_name>.md` using the [template](docs/migrations/template.md).
3. Bump the **minor** version (breaking rename ships as `_v2`; hard removal is a minor bump per semver).

**Minimum window**: 90 days **or** one minor version release after the Phase 1 announcement, whichever is later.

## Hive Writes Require a Linked Approval

Calling `tapps_memory` with `agent_scope="hive"`, `action="hive_push"`, or `action="hive_propagate"` propagates memory entries to every agent and project that shares the Hive. Accidental hive writes cause cross-project context pollution.

**Rule**: every code path that performs a hive write must reference a Linear issue or PR comment that explicitly approves it.

1. Open a Linear issue (or add a PR comment) describing what will be written to the Hive and why it needs to be cross-project.
2. Get a maintainer thumbs-up.
3. Add a `# hive-approved: TAP-XXXX` comment on the same line (or the immediately preceding line) as the write call.

A CI lint job (`.github/workflows/hive-write-lint.yml`) greps for `agent_scope.*hive`, `hive_push`, and `hive_propagate` and fails the build if any occurrence lacks a `# hive-approved:` annotation within two lines.

## Submitting Changes

This repository follows a **commit-direct-to-master** workflow — no feature branches, no pull requests. See [`.claude/rules/repo-workflow.md`](.claude/rules/repo-workflow.md).

1. Make your changes and ensure tests pass:

   ```bash
   uv run pytest packages/<affected-package>/tests/ -v
   uv run ruff check packages/<affected-package>/src/
   uv run mypy --strict packages/<affected-package>/src/<package_name>/
   ```

2. Commit with a descriptive message (conventional commits preferred):

   ```bash
   git commit -m "feat: add my new feature"
   ```

3. Push to `master`. The pre-push hook (`.githooks/pre-push`, activated by `scripts/install-git-hooks.sh`) enforces a green non-slow unit suite before allowing the push.

## Known Gotchas

- **mypy + `@mcp.tool()`**: The mcp SDK decorator is untyped. `pyproject.toml` has `disallow_untyped_decorators = false` for `tapps_mcp.server`.
- **Pydantic + `TYPE_CHECKING`**: Models using forward refs must import at runtime, not under `TYPE_CHECKING`. Use `# noqa: TC001`.
- **Windows testing**: Use `python -c "import time; time.sleep(N)"` for timeout tests.
- **Patching lazy imports**: Some imports happen inside tool handlers from `tapps_core`. Patch at source modules, not re-export wrappers.

## Releasing

Every version bump in `packages/tapps-mcp/pyproject.toml` (and the workspace) must be followed by a self-stamp resync so `tapps_doctor` and `tapps_upgrade` introspection stay accurate. Drift between the shipped `__version__` and the `<!-- tapps-agents-version: X.Y.Z -->` marker in `AGENTS.md` makes consumers see false drift or skip real upgrades.

Release checklist:

1. Bump `version` in `packages/tapps-mcp/pyproject.toml` (and workspace if applicable).
2. Run `uv run tapps-mcp upgrade --apply` against this repo to resync `AGENTS.md`'s `tapps-agents-version` marker. Alternatively, edit the marker by hand to match.
3. Verify: `grep '^<!-- tapps-agents-version' AGENTS.md` matches the new `pyproject.toml` version.
4. Update `CHANGELOG.md` with the version, date, and notable changes.
5. Commit, tag, and push.

A future CI gate (tracked in TAP-982) will fail releases when the marker and `pyproject.toml` disagree.

## Reporting Issues

When reporting issues, please include:

- A clear and descriptive title
- Steps to reproduce the problem
- Expected behavior vs actual behavior
- Your environment (OS, Python version, MCP client)
- Relevant tool output or error messages
