# Implement `since` parameter for incremental drift checking

## What

Implement `since` parameter for incremental drift checking

## Where

- `packages/docs-mcp/src/docs_mcp/validators/drift.py:292-324`
- `packages/docs-mcp/src/docs_mcp/server_val_tools.py:32-112`

## Acceptance

- [ ] 1. Implement git log filtering via `git diff` to scope changed files since a given ref/date
2. DriftDetector.check() accepts `since` as git ref (e.g.
- [ ] HEAD~1
- [ ] v1.0.0) or ISO date
3. Only Python files changed since `since` are analyzed for drift
4. Large projects with incremental changes see 80%+ reduction in scan time
5. CI workflows can use `since=origin/main` to check only PR changes
6. All existing tests pass; new tests cover incremental scenarios
7. Code reviewed and merged to master
