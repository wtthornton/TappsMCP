# Optimize doc corpus scanning from flat string to inverted index

## What

Optimize doc corpus scanning from flat string to inverted index

## Where

- `packages/docs-mcp/src/docs_mcp/validators/drift.py:149-157`
- `drift.py:193-207`

## Acceptance

- [ ] 1. Replace single concatenated doc string with inverted index (token → bool/set)
2. Build index once from all doc files at detector initialization
3. Lookup becomes O(1) set check instead of O(n) substring scan
4. Memory usage reduced by 70%+ for large doc corpora
5. Execution time for drift check improved by 40%+ on large projects
6. All existing tests pass
7. Code reviewed and merged to master
