# tapps-mcp: tapps_release_update MCP tool + CLI wrapper

## What

New MCP tool in tapps-mcp.

## Where

- `packages/tapps-mcp/src/tapps_mcp/tools/release_update.py:1-250`
- `packages/tapps-mcp/src/tapps_mcp/server.py:1-80`
- `packages/tapps-mcp/tests/unit/test_release_update_tool.py:1-150`

## Acceptance

- [ ] tapps_release_update(version
- [ ] prev_version
- [ ] bump_type
- [ ] dry_run) MCP tool is registered and callable
- [ ] Tool orchestrates: infer bump_type from semver delta if omitted → call docs_generate_release_update → call docs_validate_release_update → post via confirmed Linear write path → call tapps_linear_snapshot_invalidate
- [ ] dry_run=True returns the rendered body without posting to Linear
- [ ] Project identity (team/project) is read from .tapps-mcp.yaml; tool errors clearly if not configured
- [ ] CLI wrapper uv run tapps-mcp release-update --version vX.Y.Z calls the same orchestration
- [ ] mypy strict + ruff pass; pytest coverage >= 80% for new module

## Refs

TAP-1108
