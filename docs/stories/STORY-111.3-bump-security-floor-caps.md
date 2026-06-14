# pyproject.toml: bump security floor caps

## What

Raise TAP-608 security floors: cryptography <50, pyjwt >=2.13, python-multipart >=0.0.32, requests >=2.34.2, pip >=26.1.2.

## Where

- `packages/tapps-mcp/pyproject.toml:45-55`
- `packages/docs-mcp/pyproject.toml:36-41`

## Acceptance

- [ ] cryptography floor is >=49.0.0 with cap <50
- [ ] pyjwt >=2.13.0, python-multipart >=0.0.32, requests >=2.34.2, pip >=26.1.2
- [ ] Matching floors in docs-mcp where applicable
- [ ] uv sync succeeds without resolver conflicts

## Refs

TAP-608, TAP-3935, docs/epics/EPIC-111.md
