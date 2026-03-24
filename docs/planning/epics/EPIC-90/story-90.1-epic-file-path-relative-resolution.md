# Story 90.1: Resolve epic_file_path relative to project_root

<!-- docsmcp:start:metadata -->
**Epic:** [90 - Epic Validation Enhancements](../EPIC-90-EPIC-VALIDATION-ENHANCEMENTS.md)
**Points:** 2
**Priority:** P2 - Medium
**Status:** Proposed

<!-- docsmcp:end:metadata -->

## User Story

As an agent running epic validation, I need `epic_file_path` to accept relative paths resolved against `project_root`, so that I don't have to construct absolute Windows paths manually.

## Description

`CallTracker.evaluate_epic()` (line 722 of `checklist.py`) calls `Path(file_path).read_text()` without resolving the path. When a relative path like `docs/specs/epic.md` is provided, Python resolves it against `os.getcwd()` -- which is the MCP server's working directory, not the target project's root. The result is `[Errno 2] No such file or directory`.

The fix: `project_root` is already available in `eval_kwargs` (passed from line 1244 of `server.py`). Thread it into `evaluate_epic()` and resolve relative paths against it.

## Tasks

- [ ] Update `evaluate_epic()` signature to accept `project_root` from `eval_kwargs`
- [ ] When `file_path` is relative, resolve against `project_root`
- [ ] When `file_path` is absolute, use as-is (existing behavior)
- [ ] Improve error message to include the resolved path: `"Epic file not found: {resolved_path} (resolved from {original_path})"`
- [ ] Add tests:
  - Relative path with project_root resolves correctly
  - Relative path without project_root falls back to cwd
  - Absolute path is unchanged
  - Non-existent file gives clear error with resolved path

## Acceptance Criteria

- [ ] `tapps_checklist(epic_file_path="docs/specs/epic.md")` works when project_root is set
- [ ] Absolute paths continue to work unchanged
- [ ] Error messages show both original and resolved paths

## Definition of Done

Relative `epic_file_path` values resolve against `project_root`, matching the behavior of all other file-path-accepting tools.
