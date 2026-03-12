# Story 74.3: tapps_validate_changed base_ref zero-diff warning

**Epic:** [EPIC-74-CONSUMER-FEEDBACK-AUTOMATION-PIPELINE-UX](../EPIC-74-CONSUMER-FEEDBACK-AUTOMATION-PIPELINE-UX.md)
**Priority:** P1 | **LOE:** 1–2 days
**Status:** Complete

## Problem

When `tapps_validate_changed` is called with default `base_ref=HEAD`, it diffs against HEAD. If the caller has only staged (uncommitted) changes, the tool may see no diff and validate zero files — resulting in a silent pass. This is a misconfiguration risk in pre-commit or "validate before commit" flows. Consumers expect a warning when `base_ref=HEAD` and zero changed files are detected so that scripts can guard or document the behavior.

## Purpose & Intent

This story exists so that **callers are never silently wrong about what was validated**. When only staged (uncommitted) changes exist and base_ref is HEAD, zero files are validated—a common misconfiguration. Emitting a clear warning lets scripts and users fix the flow (e.g. commit first or pass a different base_ref) instead of believing everything passed when it did not.

## Tasks

- [x] In the validate_changed flow (e.g. in `batch_validator` or server handler), after computing changed files: when `base_ref.upper() == "HEAD"` (or equivalent) and the number of changed files is 0, add a warning to the response.
- [x] Warning message: e.g. "Zero changed files detected with base_ref=HEAD. If you have staged-but-uncommitted changes, diff is against HEAD so they are not included. Consider committing first or using a different base_ref."
- [x] Include this in `summary`, `next_steps`, or a dedicated `warnings` list in the response so both humans and scripts can detect it.
- [x] Do not change pass/fail semantics — still "pass" when zero files (no regression); only add the warning.
- [x] Add unit test: validate_changed with base_ref=HEAD and no unstaged/staged changes (or mocked empty diff) → response contains warning.
- [x] Optionally document in AGENTS.md or validate_changed docstring when to set base_ref in automated runs.

## Acceptance criteria

- [x] When base_ref=HEAD and files_validated==0, response includes a clear warning about staged-only scenario.
- [x] Pass/fail behavior unchanged; warning is additive.
- [x] Unit test verifies warning presence.
- [x] Doc update (AGENTS.md or tool) mentions base_ref for automation.

## Files

- `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py` — `_handle_no_changed_files` updated with `base_ref` param and `warnings` list
- `packages/tapps-mcp/tests/unit/test_composite_tools.py` — 2 new tests: `test_base_ref_head_zero_diff_warning`, `test_base_ref_non_head_no_warning`
