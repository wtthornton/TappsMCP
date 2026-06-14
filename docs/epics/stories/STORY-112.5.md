# doctor.py: NLT tool-budget default bundle

## What

doctor.py: NLT tool-budget default bundle

## Where

- `packages/tapps-mcp/src/tapps_mcp/distribution/doctor.py:1-400`
- `docs/architecture/nlt-mcp-plugin-spec.yaml:1-100`

## Why

fresh installs stay within MCP tool budget without manual server pruning

## Acceptance

- [ ] - [ ] Default NLT plugin bundle enables ≤3 servers (code-quality + platform-admin)
- [ ] doctor NLT partial-enablement check passes on fresh tapps_init
- [ ] docs/architecture/nlt-mcp-plugin-spec.yaml documents recommended bundles
