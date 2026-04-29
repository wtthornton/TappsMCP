# Remove or populate removed_stale drift_type

## What

Remove or populate removed_stale drift_type

## Where

- `packages/docs-mcp/src/docs_mcp/validators/drift.py:58-67`
- `411-413`

## Acceptance

- [ ] 1. Either implement stale doc detection (docs mentioning deleted symbols) OR
2. Remove "removed_stale" from drift_type enum value and docstring
3. Document rationale in comments if deferred
4. Update DriftItem model and tests accordingly
5. All existing tests pass
6. Code reviewed and merged to master
