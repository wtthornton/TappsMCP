# tapps-platform: nlt-linear-issues and nlt-release-ship profiles

## What

Add cross-package MCP profiles on `tapps-platform serve --profile` for Linear issue workflow and release/shipping.

## Where

1. `packages/tapps-mcp/src/tapps_mcp/platform/combined_server.py:1-200`
2. `packages/tapps-mcp/src/tapps_mcp/platform/cli.py`
3. `docs/architecture/nlt-mcp-plugin-spec.yaml:141-245`

## Acceptance

- [ ] `nlt-linear-issues` exposes 15 tools (7 docs + 8 tapps), zero overlap with other profiles
- [ ] `nlt-release-ship` exposes 7 tools
- [ ] Unit tests verify tool lists match YAML spec

## Refs

- EPIC-109 story 109.2
