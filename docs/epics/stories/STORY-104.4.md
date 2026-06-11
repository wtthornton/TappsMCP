# judge.py: add when_changed glob filter for judges

## What

Optional glob list so slow document rebuild/audit judges run only when relevant paths change.

## Where

- `packages/tapps-core/src/tapps_core/metrics/judge.py:1-226`
- `packages/tapps-mcp/src/tapps_mcp/tools/validate_changed.py:560-621`

## Acceptance

- [ ] - [ ] JudgeDefinition accepts optional when_changed list of glob patterns
- [ ] Judge skipped (result pass
- [ ] message skipped) when git diff vs base_ref touches no matching paths
- [ ] Judge runs when any changed path matches a when_changed glob
- [ ] Empty when_changed means always run (backward compatible)
- [ ] Unit tests cover match
- [ ] no-match skip
- [ ] and empty when_changed

## Refs

docs/epics/EPIC-104.md
