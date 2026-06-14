# pyproject.toml: reconcile tapps-brain git pin

## What

Reconcile tapps-brain floor >=3.24.0 and git rev d893fc1 against latest GitHub tag v3.22.4; document or retag as appropriate.

## Where

- `pyproject.toml:4-9`
- `packages/tapps-core/pyproject.toml:24-25`

## Acceptance

- [ ] Brain pin strategy documented in pyproject comment or ADR note
- [ ] Git rev or tag matches intended brain release with docs_lookup support
- [ ] tapps_memory health probe passes after uv sync
- [ ] ADR-0013 floor updated if tag v3.24.0+ ships

## Refs

TAP-3940, docs/epics/EPIC-111.md
