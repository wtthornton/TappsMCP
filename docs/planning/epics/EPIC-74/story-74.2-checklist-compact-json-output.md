# Story 74.2: tapps_checklist compact/JSON output

**Epic:** [EPIC-74-CONSUMER-FEEDBACK-AUTOMATION-PIPELINE-UX](../EPIC-74-CONSUMER-FEEDBACK-AUTOMATION-PIPELINE-UX.md)  
**Priority:** P2 | **LOE:** 2–3 days

## Problem

`tapps_checklist(task_type="bugfix")` returns a full markdown table (~30 lines). In automated script/CI contexts this is captured verbatim in logs and is unnecessarily verbose. Consumers want a `compact=True` flag or `format="json"` for a machine-readable summary to reduce log noise.

## Purpose & Intent

This story exists so that **CI and scripts get actionable checklist output without drowning logs in markdown tables**. Human users keep the default rich output; machines get a parseable summary (complete, missing, next_steps) for gates and reporting. It aligns checklist with the rest of the pipeline’s automation-friendly design.

## Tasks

- [ ] Add optional parameter(s) to `tapps_checklist`: e.g. `compact: bool = False` or `output_format: str = "markdown"` with allowed values `"markdown"` | `"json"` (and optionally `"compact"` as shorthand for one-line or short summary).
- [ ] When `compact=True` or `format="json"`: return a concise summary (e.g. task_type, complete, required_called, required_missing, optional_called, next_steps list) without the full markdown table in the main text; attach full data in `data` or structuredContent for consumers that need it.
- [ ] Ensure interactive use still defaults to human-readable markdown; no change to default behavior.
- [ ] Add unit tests for compact and JSON output; verify structure.
- [ ] Document in AGENTS.md (e.g. "For CI/automation use compact=True or format='json'").

## Acceptance criteria

- [ ] New parameter(s) backward-compatible; default behavior unchanged.
- [ ] Compact/JSON output provides machine-readable summary (task_type, complete, counts, next_steps).
- [ ] Tests added; existing checklist tests pass.
- [ ] AGENTS.md or tool description mentions CI/automation output options.

## Files

- `packages/tapps-mcp/src/tapps_mcp/tools/checklist.py`
- `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py` (if checklist handler is there)
- `packages/tapps-mcp/tests/unit/test_checklist.py`
- `AGENTS.md` (optional)
