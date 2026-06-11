# session_start: MCP recovery + cli_fallback hints

## What

session_start: MCP recovery + cli_fallback hints

## Where

- `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py:646-660`
- `packages/tapps-mcp/src/tapps_mcp/tools/session_start_helpers.py:1-100`

## Acceptance

- [ ] - session_start data includes cli_fallback object mapping core MCP tools to CLI commands
- next_steps includes one-line hint when validation tools may be unavailable after host reload
- References docs/TROUBLESHOOTING.md MCP recovery section
- Unit test asserts cli_fallback keys include tapps_validate_changed and tapps_quick_check
