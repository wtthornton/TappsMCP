# Code quality improvements (conditions, next_steps, getattr)

## What

Code quality improvements (conditions, next_steps, getattr)

## Where

- `packages/docs-mcp/src/docs_mcp/validators/drift.py:407-413`
- `server_val_tools.py:137`
- `360-361`

## Acceptance

- [ ] 1. Deduplicate severity/drift_type condition check — compute once
- [ ] reuse
2. Add next_steps guidance to docs_check_drift success_response
3. Remove getattr fallback on known Pydantic drift_fraction field
4. Narrow hardcoded "test" path skip to match on directory/filename boundaries only
5. All existing tests pass; new tests verify improvements
6. Code reviewed and merged to master
