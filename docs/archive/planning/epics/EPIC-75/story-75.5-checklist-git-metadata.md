# Story 75.5: Checklist Git Commit Metadata Linkage

**Epic:** [EPIC-75-DOCKER-PIPELINE-RELIABILITY](../EPIC-75-DOCKER-PIPELINE-RELIABILITY.md)
**Priority:** P2 | **LOE:** 1–2 days | **Recurrence:** 2

## Problem

`tapps_checklist` output does not include the git branch or HEAD SHA. In automated pipelines, the checklist serves as the final verification step, but its output cannot be correlated with a specific commit without manual lookup. Consumers must cross-reference `TAPPS_RUNLOG.md` entries with `git log` to establish the audit trail.

**Example from feedback:** Checklist confirmed all stages passed for commit `a80f38c7`, but the checklist response contained no reference to that SHA or the `master` branch.

## Tasks

- [ ] At checklist execution time, detect the current git context:
  - `branch`: result of `git rev-parse --abbrev-ref HEAD`
  - `head_sha`: result of `git rev-parse --short HEAD`
  - `head_sha_full`: result of `git rev-parse HEAD`
  - `dirty`: whether working tree has uncommitted changes (`git status --porcelain`)
- [ ] Add a `git_context` object to the checklist response: `{"branch": "master", "head_sha": "a80f38c7", "head_sha_full": "a80f38c7...", "dirty": false}`.
- [ ] If git is not available (not a repo, git not installed), set `git_context: null` with no error — graceful degradation.
- [ ] Use `subprocess_runner` (existing utility) for git commands to respect timeout and security constraints.
- [ ] Optionally accept a `commit_sha` parameter on `tapps_checklist` so callers can pass the SHA explicitly (useful when the checklist runs after a commit is made but HEAD may have advanced).
- [ ] Unit tests: git context populated, git not available (graceful null), explicit commit_sha override.

## Acceptance Criteria

- [ ] `tapps_checklist` response includes `git_context` with `branch`, `head_sha`, `dirty` fields.
- [ ] When git is unavailable, `git_context` is `null` — no error raised.
- [ ] Optional `commit_sha` parameter overrides auto-detected SHA.
- [ ] Existing checklist behavior and output format unchanged (git_context is additive).
- [ ] Tests cover: happy path, no-git graceful fallback, explicit SHA override.

## Files (likely)

- `packages/tapps-mcp/src/tapps_mcp/tools/checklist.py` (checklist logic)
- `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py` (checklist handler)
- `packages/tapps-mcp/tests/unit/test_checklist.py`
- `packages/tapps-mcp/tests/unit/test_server_pipeline_tools.py`
