# Apply source_filter as pre-filter, not post-filter

## What

Apply source_filter as pre-filter, not post-filter

## Where

- `packages/docs-mcp/src/docs_mcp/server_val_tools.py:91-129`
- `validators/drift.py:292-301`

## Acceptance

- [ ] 1. Add source_files parameter to DriftDetector.check() method signature
2. Filter Python files before analysis instead of after
3. Large projects with selective source_files see 90%+ reduction in scan time
4. All existing tests pass; new tests verify filtering behavior
5. Documentation updated to clarify pre-filter behavior
6. Code reviewed and merged to master
