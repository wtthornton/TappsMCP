# audit_chunker.py: auto-detect monorepo graph_root

## What

audit_chunker.py: auto-detect monorepo graph_root

## Where

- `packages/tapps-mcp/src/tapps_mcp/tools/audit_chunker.py:1-200`
- `packages/tapps-mcp/src/tapps_mcp/tools/audit_campaign.py:125-155`

## Why

audit campaigns chunk correctly without manual graph_root on monorepos

## Acceptance

- [ ] - [ ] Nested scope under packages/* auto-sets graph_root without manual parameter
- [ ] Import graph has non-zero edges for tapps-mcp monorepo root scope
- [ ] Existing TAP-2035 workaround via manual graph_root still works
