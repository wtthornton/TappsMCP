# validate_changed_output.py: top lint findings on gate fail

## What

validate_changed_output.py: top lint findings on gate fail

## Where

- `packages/tapps-mcp/src/tapps_mcp/tools/validate_changed_orchestrator.py:71-125`
- `packages/tapps-mcp/src/tapps_mcp/tools/validate_changed_output.py:127-172`
- `packages/tapps-mcp/tests/unit/test_per_file_results.py:1-150`

## Acceptance

- [ ] - When gate_passed is false
- [ ] per_file_results includes top_findings (max 3) with code
- [ ] message
- [ ] line
- Raw results array also carries lint_issues (serialized
- [ ] limit 3) matching quick_check shape
- summary_rows append first finding code e.g. F401 for grep-friendly scan
- Unit tests in test_per_file_results.py and test_validate_changed cover fail path with lint excerpts
- Backward compatible: passing files unchanged
