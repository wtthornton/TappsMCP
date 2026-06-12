# docs-mcp: nlt-project-docs profile

## What

Implement `docsmcp serve --profile nlt-project-docs` (27 tools, 6 eager).

## Where

1. `packages/docs-mcp/src/docs_mcp/server.py:136-200`
2. `packages/docs-mcp/src/docs_mcp/cli.py`
3. `docs/architecture/nlt-mcp-plugin-spec.yaml:177-218`

## Acceptance

- [ ] Profile registers 27 docs tools per spec
- [ ] Disjoint from tapps-platform NLT profiles
- [ ] Tests in `packages/docs-mcp/tests/unit/test_tool_meta.py` or new profile test file

## Refs

- EPIC-109 story 109.3
