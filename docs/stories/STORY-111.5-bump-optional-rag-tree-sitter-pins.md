# pyproject.toml: bump optional RAG/tree-sitter pins

## What

Bump numpy, sentence-transformers, faiss-cpu, tree-sitter, tree-sitter-go, and tree-sitter-rust optional extras to latest stable.

## Where

- `packages/tapps-mcp/pyproject.toml:72-90`
- `packages/docs-mcp/pyproject.toml:43-50`
- `packages/tapps-core/pyproject.toml:35-40`

## Acceptance

- [ ] numpy >=2.4.6, sentence-transformers >=5.5.1, faiss-cpu >=1.14.3
- [ ] tree-sitter >=0.25.2, tree-sitter-go >=0.25.0, tree-sitter-rust >=0.24.2
- [ ] Optional extras install with uv sync --all-packages --extra treesitter (or vector)
- [ ] No import regressions in tree-sitter extraction tests

## Refs

TAP-3938, docs/epics/EPIC-111.md
