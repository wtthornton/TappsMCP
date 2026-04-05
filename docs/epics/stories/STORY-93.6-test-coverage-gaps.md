# Story 93.6 -- Test Coverage Gap Closure

<!-- docsmcp:start:user-story -->

> **As a** maintainer, **I want** every package at >= 85% line coverage with MCP handlers and security modules prioritized, **so that** the fixes from the other stories in this epic are exercised by the test suite and regressions are caught automatically.

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 5 | **Size:** M

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

Refactors from 93.2 through 93.5 are only safe if the tests cover the paths being modified. This story closes coverage gaps, prioritizing MCP tool handlers and `security/` code.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Run `uv run pytest --cov=<package>` per package and export line-coverage reports. List every file below 85%. Add unit tests for the uncovered branches, prioritizing:

1. `@mcp.tool()` handler functions (`server*.py`)
2. `security/` modules (path validator, command runner, secret scrubber)
3. Generator modules in docs-mcp

Raise each package's `fail_under` threshold in `pyproject.toml` to match the new baseline (minimum 85%).

See [Epic 93](../EPIC-93-full-code-review-and-fixes.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `packages/*/tests/unit/**/*.py` (new/expanded tests)
- `packages/*/pyproject.toml` (fail_under threshold)

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Run `uv run pytest --cov` per package; export reports
- [ ] List every file below 85% line coverage
- [ ] Add tests for MCP handlers first, then security/, then generators
- [ ] Add tests for remaining uncovered files
- [ ] Raise `fail_under` in pyproject.toml to match new baseline (>= 85%)
- [ ] Re-run full test suite and confirm CI passes

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] tapps-core line coverage >= 85%
- [ ] tapps-mcp line coverage >= 85%
- [ ] docs-mcp line coverage >= 85%
- [ ] Every MCP handler has at least one happy-path test
- [ ] Every security/ module has branch-level tests
- [ ] `fail_under` enforced in pyproject.toml

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Code reviewed and approved
- [ ] All tests passing
- [ ] Coverage thresholds enforced in CI
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->
