# judge.py: wire blocking judges into all_gates_passed

## What

Fold blocking judge failures into the primary validate_changed pass/fail signal.

## Where

- `packages/tapps-core/src/tapps_core/metrics/judge.py:1-226`
- `packages/tapps-mcp/src/tapps_mcp/tools/validate_changed.py:383-424`
- `packages/tapps-mcp/src/tapps_mcp/common/output_schemas.py:125-136`

## Acceptance

- [ ] - [ ] When any blocking judge returns fail or error
- [ ] all_gates_passed is false
- [ ] ValidateChangedOutput.overall_passed reflects blocking judge failures
- [ ] Non-blocking judge failures leave all_gates_passed unchanged
- [ ] Unit tests in test_judge.py and validate_changed tests cover the integration

## Refs

docs/epics/EPIC-104.md
