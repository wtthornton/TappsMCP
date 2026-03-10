# Story 75.4: validate_changed Per-File Pass/Fail Rows

**Epic:** [EPIC-75-DOCKER-PIPELINE-RELIABILITY](../EPIC-75-DOCKER-PIPELINE-RELIABILITY.md)
**Priority:** P2 | **LOE:** 2–3 days | **Recurrence:** 2

## Problem

`tapps_validate_changed` returns a consolidated narrative report when validating multiple files. While accurate and comprehensive, the output cannot be easily parsed by CI log tools or automated pipelines without regex. Consumers want machine-readable per-file pass/fail rows like:

```
PASS  sandbox.py        score=7.2  gate=pass  security=pass
FAIL  processor.py      score=4.1  gate=fail  security=pass  issues=3
PASS  generator.py      score=6.8  gate=pass  security=pass
```

This format enables `grep FAIL` in CI logs, structured reporting in GitHub Actions step summaries, and programmatic correlation with fix commits.

## Tasks

- [ ] Add a `per_file_results` list to the `tapps_validate_changed` response structure, each entry containing: `file`, `status` (PASS/FAIL), `score`, `gate_passed`, `security_passed`, `issue_count`.
- [ ] Add a `summary_rows` field containing pre-formatted text lines (one per file) in the grep-friendly format shown above.
- [ ] Preserve the existing narrative `report` field unchanged for backward compatibility.
- [ ] Add optional `format` parameter: `"full"` (default, narrative + rows), `"compact"` (rows only), `"json"` (structured per-file JSON).
- [ ] Update the structured output schema (`output_schemas.py`) if validate_changed has one.
- [ ] Unit tests: multiple files with mixed pass/fail, compact format, JSON format, single file (no regression).
- [ ] Verify `summary_rows` is grep-friendly: consistent column alignment, PASS/FAIL prefix.

## Acceptance Criteria

- [ ] `tapps_validate_changed` response includes `per_file_results` list and `summary_rows` text.
- [ ] Each `per_file_results` entry has: `file`, `status`, `score`, `gate_passed`, `security_passed`, `issue_count`.
- [ ] `format="compact"` returns only the per-file rows (no narrative).
- [ ] `format="json"` returns structured JSON per-file results.
- [ ] Default behavior (`format="full"`) returns both narrative and rows — no breaking change.
- [ ] Tests cover: mixed results, all-pass, all-fail, single file, each format option.

## Files (likely)

- `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py` (validate_changed handler)
- `packages/tapps-mcp/src/tapps_mcp/tools/batch_validator.py` (batch validation logic)
- `packages/tapps-mcp/src/tapps_mcp/common/output_schemas.py` (structured output update)
- `packages/tapps-mcp/tests/unit/test_server_pipeline_tools.py`
- `packages/tapps-mcp/tests/unit/test_batch_validator.py`
