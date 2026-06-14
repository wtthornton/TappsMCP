# pyproject.toml: align test/dev toolchain pins

## What

Bump pytest 9.1, pytest-asyncio 1.4, pytest-cov 7.1, pytest-xdist 3.8, pytest-randomly 4.1, pre-commit 4.6, playwright 1.60; sync tapps-mcp dev floors with root.

## Where

- `pyproject.toml:11-23`
- `packages/tapps-mcp/pyproject.toml:57-68`

## Acceptance

- [ ] Root and tapps-mcp dev pytest floors match at >=9.1.0
- [ ] pytest-asyncio >=1.4.0 and pytest-cov >=7.1.0 in both manifests
- [ ] pytest-xdist >=3.8.0 and pytest-randomly >=4.1.0 in root dev-deps
- [ ] pre-commit >=4.6.0 and playwright >=1.60.0
- [ ] uv run pytest packages/tapps-mcp/tests/ -m "not slow" --maxfail=3 passes

## Refs

TAP-3936, docs/epics/EPIC-111.md
