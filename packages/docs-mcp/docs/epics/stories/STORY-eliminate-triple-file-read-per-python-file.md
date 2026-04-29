# Eliminate triple file read per Python file

## What

Eliminate triple file read per Python file

## Where

- `packages/docs-mcp/src/docs_mcp/validators/drift.py:357-391`

## Acceptance

- [ ] 1. Refactor to read each Python file once and reuse for empty-file check
- [ ] APISurfaceAnalyzer
- [ ] and docstring collection
2. Share single AST parse across drift detection and docstring analysis
3. Performance test shows 60%+ reduction in file I/O for medium-sized projects
4. All existing tests pass without modification
5. Code reviewed and merged to master
