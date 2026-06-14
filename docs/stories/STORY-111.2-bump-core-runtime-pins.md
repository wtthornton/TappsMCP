# pyproject.toml: bump core runtime pins

## What

Bump mcp, pydantic, pydantic-settings, structlog (raise <26 cap), click, anyio, and filelock to latest stable targets.

## Where

- `packages/tapps-mcp/pyproject.toml:26-37`
- `packages/tapps-core/pyproject.toml:24-33`
- `packages/docs-mcp/pyproject.toml:27-35`

## Acceptance

- [ ] mcp floor is >=1.27.2
- [ ] pydantic floor is >=2.13.4 and pydantic-settings >=2.14.1
- [ ] structlog floor is >=26.1.0 with upper cap <27
- [ ] click >=8.4.1, anyio >=4.13.0, filelock >=3.29.4
- [ ] uv sync --all-packages succeeds

## Refs

TAP-3934, docs/epics/EPIC-111.md
