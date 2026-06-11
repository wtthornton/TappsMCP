# validate_changed_output.py: judge rows in summary_rows

## What

Surface judge_results in the visible summary table and CLI output so agents do not ignore buried JSON fields.

## Where

- `packages/tapps-mcp/src/tapps_mcp/tools/validate_changed_output.py:286-322`
- `packages/tapps-mcp/src/tapps_mcp/cli.py:512-577`

## Acceptance

- [ ] - [ ] Each judge result appends a PASS/FAIL row to summary_rows (grep-friendly)
- [ ] CLI validate-changed echoes judge rows and exits non-zero on blocking judge fail
- [ ] Human summary string mentions judge pass/fail counts
- [ ] Unit test asserts summary_rows contains judge rows when judges run

## Refs

docs/epics/EPIC-104.md
