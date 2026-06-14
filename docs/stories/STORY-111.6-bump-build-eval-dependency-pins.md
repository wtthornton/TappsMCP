# pyproject.toml: bump build/eval dependency pins

## What

Bump hatchling build backend, anthropic eval harness dep, and evaluate cohere reranker floor.

## Where

- `pyproject.toml:1-4`
- `pyproject.toml:30-33`
- `packages/tapps-core/pyproject.toml:41-43`

## Acceptance

- [ ] hatchling build requires >=1.30.1 in all package build-system sections
- [ ] anthropic dev-dep floor is >=0.109.1
- [ ] cohere reranker extra floor evaluated and set to >=7.0.4 if compatible
- [ ] uv sync succeeds

## Refs

TAP-3939, docs/epics/EPIC-111.md
