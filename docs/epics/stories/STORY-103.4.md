# validate_changed: failure_reason for score 0.0

## What

validate_changed: failure_reason for score 0.0

## Where

- `packages/tapps-mcp/src/tapps_mcp/tools/validate_changed_orchestrator.py:71-125`
- `packages/tapps-mcp/src/tapps_mcp/tools/validate_changed_output.py:127-172`

## Acceptance

- [ ] - per_file_results includes failure_reason when score is 0.0 or gate_passed false
- Enum values: parse_error
- [ ] lint_blocker
- [ ] gate_threshold
- [ ] scoring_error
- [ ] unsupported_file
- Derived from gate_failures
- [ ] lint_issues
- [ ] errors list — same logic in _validate_single_file
- summary_rows show failure_reason for score=0.0 rows
- Tests cover syntax-error file and F821 undefined name scenarios
