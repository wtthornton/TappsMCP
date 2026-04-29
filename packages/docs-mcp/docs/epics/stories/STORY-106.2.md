# docs-mcp: docs_generate_release_update + docs_validate_release_update

## What

New generator and validator in docs-mcp.

## Where

- `packages/docs-mcp/src/docs_mcp/generators/release_update.py:1-200`
- `packages/docs-mcp/src/docs_mcp/server_gen_tools.py:1-50`
- `packages/docs-mcp/tests/unit/test_release_update_generator.py:1-150`

## Acceptance

- [ ] docs_generate_release_update(version
- [ ] prev_version
- [ ] bump_type
- [ ] highlights
- [ ] issues_closed
- [ ] links) returns a markdown body matching the standard template
- [ ] Template sections: version header + health field + highlights bullets + issues-closed list + breaking-changes section (minor/major only) + links block
- [ ] docs_validate_release_update(body) returns agent_ready=true for a compliant body and agent_ready=false with structured findings for a non-compliant one
- [ ] Body sources from CHANGELOG.md section when present; falls back to git log conventional-commit groups; TAP-### refs scraped from commit messages
- [ ] mypy strict + ruff pass; pytest coverage >= 80% for new modules

## Refs

TAP-1108
