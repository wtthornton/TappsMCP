# pyproject.toml: bump quality checker pins

## What

Bump ruff to 0.15.17 and pip-audit to 2.10.1; align packages/tapps-mcp dev ruff floor with root pyproject.toml.

## Where

- `packages/tapps-mcp/pyproject.toml:57-65`
- `pyproject.toml:11-22`

## Acceptance

- [ ] ruff floor is >=0.15.17 in root and packages/tapps-mcp dev extras
- [ ] pip-audit floor is >=2.10.1
- [ ] uv lock resolves ruff 0.15.17 and pip-audit 2.10.1
- [ ] uv run ruff check packages/*/src/ passes

## Refs

TAP-3937, docs/epics/EPIC-111.md
