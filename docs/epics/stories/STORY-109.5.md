# tapps_doctor: partial-enablement WARN thresholds

## What

Extend doctor to WARN when >3 nlt-* MCP servers enabled or combined eager tool count exceeds 20.

## Where

1. `packages/tapps-mcp/src/tapps_mcp/distribution/doctor.py:2758-2820`
2. `docs/architecture/nlt-mcp-plugin-spec.yaml:47-54`

## Acceptance

- [ ] Detects nlt-* server entries in `.cursor/mcp.json` / `.mcp.json`
- [ ] WARN line when count >3 or eager total >20
- [ ] Per-server tool count row for each enabled nlt-* profile
- [ ] Unit tests with fixture mcp.json files

## Refs

- EPIC-109 story 109.5
