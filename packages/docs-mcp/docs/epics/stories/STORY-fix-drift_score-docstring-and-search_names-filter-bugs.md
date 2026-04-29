# Fix drift_score docstring and search_names filter bugs

## What

Fix drift_score docstring and search_names filter bugs

## Where

- `packages/docs-mcp/src/docs_mcp/server_val_tools.py:32-166`
- `packages/docs-mcp/src/docs_mcp/validators/drift.py:70-81`

## Acceptance

- [ ] 1. drift_score docstring corrected to say "higher = more drift" (bug #1)
2. search_names filter refactored to search raw symbol list
- [ ] not truncated description (bug #2)
3. _qualify function detects src/ and lib/ prefixes and strips them for qualified names (bug #3)
4. All three changes are tested and pass existing test suite
5. Code is reviewed and merged to master
