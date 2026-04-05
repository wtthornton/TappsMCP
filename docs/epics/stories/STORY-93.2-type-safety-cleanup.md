# Story 93.2 -- Type Safety Cleanup

<!-- docsmcp:start:user-story -->

> **As a** contributor touching TappsMCP internals, **I want** every surviving `type: ignore` to have a clear justification, **so that** I can distinguish "known library gap" from "someone gave up" when I edit the surrounding code.

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 3 | **Size:** S

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

Unjustified `type: ignore` comments accumulate over time and mask real bugs. This story establishes a rule: every `type: ignore` must either be removed or annotated with a one-line comment explaining the underlying library or SDK gap.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Inventory every `type: ignore` across `packages/*/src/`. For each, attempt removal and re-run `uv run mypy --strict`. If the ignore is still needed, add an adjacent comment explaining why (e.g., `# mcp SDK decorator is untyped`, `# structlog.get_logger returns Any`). Remove any that are no longer needed because upstream packages have added types.

Also audit public function signatures for `Any` leakage; replace with concrete types or `TypeVar` where it improves caller ergonomics.

See [Epic 93](../EPIC-93-full-code-review-and-fixes.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `packages/tapps-core/src/**/*.py`
- `packages/tapps-mcp/src/**/*.py`
- `packages/docs-mcp/src/**/*.py`
- `packages/*/pyproject.toml` (if any mypy overrides are no longer needed)

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Inventory all `type: ignore` comments (grep + file list)
- [ ] For each, attempt removal and verify `mypy --strict` passes
- [ ] For each surviving ignore, add a one-line justification comment
- [ ] Audit public function signatures for `Any` leakage
- [ ] Replace public-API `Any` with concrete types or `TypeVar`
- [ ] Remove stale `ignore_missing_imports` overrides from pyproject.toml

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Every `type: ignore` in `src/` has an adjacent justification comment
- [ ] `uv run mypy --strict` passes on all three packages
- [ ] Public function signatures have no unjustified `Any`
- [ ] `pyproject.toml` mypy overrides contain only still-needed entries

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Code reviewed and approved
- [ ] `mypy --strict` passes on all packages
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->
