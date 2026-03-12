# Story 75.2: Cross-File Type Error Detection in quick_check

**Epic:** [EPIC-75-DOCKER-PIPELINE-RELIABILITY](../EPIC-75-DOCKER-PIPELINE-RELIABILITY.md)
**Priority:** P1 | **LOE:** 4–6 days | **Recurrence:** 2

## Problem

`tapps_quick_check` does not catch cross-file type errors such as:
- Calling a method with wrong keyword arguments (e.g. `generate(user_id=...)` when signature expects `_user_id`)
- Method signature mismatches between caller and callee across modules
- Missing async context manager handling

These bugs require cross-package type resolution that mypy provides — but only when the full package graph is importable. In the Docker container environment, packages often aren't fully importable (missing deps, partial installs), so mypy's cross-file analysis silently produces no findings.

**Observed pattern:** Bugs are found by a separate bug-scanner agent; `tapps_quick_check` only confirms the fix is clean *after* the bug is resolved. It operates as a post-fix gate, not a pre-fix detector.

## Root Cause Analysis

1. `tapps_quick_check` runs mypy on a single file. Mypy needs the full dependency graph resolved to catch cross-file errors.
2. In Docker containers, `pip install -e .` may not have been run, so imports fail silently in mypy.
3. When mypy can't resolve imports, it skips cross-module checks entirely — no error, no warning, just silence.
4. The AST-based fallback analysis in `tapps_quick_check` only checks single-file patterns (complexity, naming, etc.), not cross-file relationships.

## Tasks

- [ ] **Detect mypy import resolution failures**: After running mypy, parse output for `import-not-found` or `no-any-return` patterns that indicate broken cross-file resolution. Add a `mypy_cross_file_coverage` field to quick_check output (`full`, `partial`, `none`).
- [ ] **AST-based cross-reference check**: Build a lightweight call-site analyzer that:
  - Extracts function/method calls with keyword arguments from the target file's AST
  - Resolves the callee's definition file (via import path resolution)
  - Compares caller kwargs against callee parameter names
  - Flags mismatches as `potential_type_error` (confidence: medium, since resolution is best-effort)
- [ ] **Signature drift detector**: When both caller and callee files are available, compare:
  - Parameter names (exact match)
  - Parameter count (caller provides more/fewer than callee accepts)
  - `*args`/`**kwargs` presence (suppresses false positives)
- [ ] **Report degraded coverage**: When cross-file analysis is unavailable (mypy import failures, callee file not found), include `"cross_file_analysis": "degraded"` in output so the consumer knows the gap exists.
- [ ] **Unit tests**: kwarg mismatch detection, signature drift, degraded mode, files with `**kwargs` (no false positive).
- [ ] **Integration test**: Feed known-bad file pair (caller with wrong kwargs → callee with different param names) and verify detection.

## Acceptance Criteria

- [ ] `tapps_quick_check` detects kwarg name mismatches across files when both files are accessible.
- [ ] Output includes `cross_file_analysis` status field (`full`, `partial`, `degraded`).
- [ ] When mypy cross-file resolution fails, AST-based fallback runs and results are marked `confidence: medium`.
- [ ] No false positives on functions accepting `**kwargs`.
- [ ] Existing single-file quick_check behavior unchanged.
- [ ] Tests cover: mismatch found, no mismatch, degraded mode, `**kwargs` suppression.

## Design Notes

- This is intentionally **best-effort** — the goal is to catch the 80% case (wrong kwarg names) not to replicate mypy's full type system.
- The AST cross-reference should be a separate module (e.g. `scoring/cross_ref.py`) so it can be reused by `tapps_score_file` later.
- Performance budget: cross-ref analysis adds ≤ 500ms per file on typical codebases.

## Files (likely)

- `packages/tapps-core/src/tapps_core/scoring/cross_ref.py` (new — AST cross-reference analyzer)
- `packages/tapps-mcp/src/tapps_mcp/server_scoring_tools.py` (quick_check integration)
- `packages/tapps-core/src/tapps_core/tools/mypy.py` (import failure detection)
- `packages/tapps-core/tests/unit/test_cross_ref.py` (new)
- `packages/tapps-mcp/tests/unit/test_server_scoring_tools.py`
