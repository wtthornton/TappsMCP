# Story 74.4: tapps_validate_changed optional traceability

**Epic:** [EPIC-74-CONSUMER-FEEDBACK-AUTOMATION-PIPELINE-UX](../EPIC-74-CONSUMER-FEEDBACK-AUTOMATION-PIPELINE-UX.md)  
**Priority:** P2 | **LOE:** 2–3 days

## Problem

In automated bugfix runs, the pipeline fixes multiple files then calls `tapps_validate_changed`. The output is a flat list of files with pass/fail per file. There is no way to correlate which quality finding (or fix) led to which validated file — e.g. for audit or "bug_id → files validated" traceability. Consumers requested a structured `bug_id` or `fix_ref` in the output (or per-file identifiers) so scripts can link validation to fix steps.

## Purpose & Intent

This story exists so that **automated runs can correlate validation results with fix steps or bug IDs** for auditing and reporting. Without a correlation id and structured per-file results, scripts cannot answer "which fixes did this validate run cover?" Adding optional traceability supports accountability and debugging in pipeline-heavy environments.

## Tasks

- [ ] Add optional parameter to `tapps_validate_changed`: e.g. `run_id: str | None = None` or `correlation_id: str | None = None` that, when provided, is included in the response so automated callers can tag this run and correlate with their own bug/fix IDs.
- [ ] Optionally include per-file result entries with stable keys (file_path, score, gate_passed, ...) so that scripts can map "fix for bug X" → list of file_paths validated in this run.
- [ ] Keep scope minimal: no server-side bug tracking; only echo correlation id and structured per-file list. Full "bug_id per finding" can be a follow-up if needed.
- [ ] Add unit test: validate_changed with run_id/correlation_id → response contains it and per-file structure is parseable.
- [ ] Document in tool docstring and AGENTS.md for automation use.

## Acceptance criteria

- [ ] Optional correlation/run_id parameter; when set, included in response.
- [ ] Per-file results are structured (e.g. list of { file_path, score, gate_passed, ... }) for script consumption.
- [ ] Backward compatible; existing callers unchanged.
- [ ] Tests and docs updated.

## Files

- `packages/tapps-mcp/src/tapps_mcp/tools/batch_validator.py`, `server_pipeline_tools.py`
- `packages/tapps-mcp/tests/unit/test_validate_changed_p0.py` or equivalent
- `AGENTS.md` (optional)
