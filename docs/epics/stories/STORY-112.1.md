# server_analysis_tools.py: honor project_root in MCP handlers

## What

server_analysis_tools.py: honor project_root in MCP handlers

## Where

- `packages/tapps-mcp/src/tapps_mcp/server_analysis_tools.py:1-400`
- `packages/tapps-mcp/src/tapps_mcp/tools/audit_campaign.py:120-160`

## Why

agents in consumer repos can run audit/report/deps tools against tapps-mcp without path mapping failures

## Acceptance

- [ ] - [ ] tapps_audit_campaign resolves scope/graph_root against explicit project_root
- [ ] tapps_report scores files under project_root not MCP host root
- [ ] tapps_dependency_scan and tapps_dead_code honor project_root
- [ ] Unit test reproduces cross-repo call from host tapps-brain targeting tapps-mcp
