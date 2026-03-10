# Epic 66.2: Checklist Validation Note for 0 Files (Tool UX)

**Status:** Complete
**Priority:** P3 | **LOE:** 1-2 days | **Source:** [TAPPS_MCP_TOOL_UX_REVIEW](../TAPPS_MCP_TOOL_UX_REVIEW.md)
**Dependencies:** Epic 8 (pipeline), checklist

## Problem Statement

When `tapps_checklist(auto_run=True)` runs `tapps_validate_changed` and validate_changed returns `files_validated: 0`, the checklist still reports `complete: true` (if no required tools missing). The agent doesn't know that validation ran but checked no files—possible path mapping issue.

## Stories

### Story 66.2.1: validation_note in auto_run_results

**Files:** `packages/tapps-mcp/src/tapps_mcp/tools/checklist.py`

1. When auto_run runs validate_changed and `files_validated == 0`:
   - Add `validation_note` to `auto_run_results.validate_changed`: "Validation ran but 0 files validated. Consider tapps_quick_check on changed files."
   - Include in `next_steps` when applicable
2. Only when files_validated=0; omit otherwise

**Acceptance criteria:**
- auto_run_results.validate_changed includes validation_note when files_validated=0
- next_steps suggests tapps_quick_check
- No note when files_validated > 0

### Story 66.2.2: Unit test

**Files:** `packages/tapps-mcp/tests/unit/test_checklist.py`

1. Add test: auto_run with mock validate_changed returning 0 files → checklist includes validation_note

**Acceptance criteria:**
- Unit test passes

## Testing

- Unit: checklist validation_note when auto_run validate_changed returns 0 files
- Unit: no validation_note when files_validated > 0
