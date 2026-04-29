# Replace single aggregate doc_mtime with per-file precision

## What

Replace single aggregate doc_mtime with per-file precision

## Where

- `packages/docs-mcp/src/docs_mcp/validators/drift.py:342-381`

## Acceptance

- [ ] 1. Track which documentation file mentions each public symbol
2. Use that doc file's mtime for severity/age assessment instead of max(doc_mtime)
3. Reduce false-positive error severity when one doc is touched but others are stale
4. Implement symbol-to-doc-file mapping during drift analysis
5. All existing tests pass; new tests cover mixed-age docs
6. Code reviewed and merged to master
