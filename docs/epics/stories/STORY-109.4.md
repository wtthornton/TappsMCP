# tapps_init: multi-server mcp.json developer bundle

## What

Update init/upgrade to write `nlt-code-quality` + `nlt-platform-admin` MCP entries by default; comment opt-in servers.

## Where

1. `packages/tapps-mcp/src/tapps_mcp/distribution/setup_generator.py`
2. `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py`
3. `docs/architecture/nlt-mcp-plugin-spec.yaml:76-96,334-350`

## Acceptance

- [ ] `tapps_init` writes 2 enabled servers, 3 commented opt-in blocks
- [ ] `--bundle planning|docs|release` enables appropriate subset
- [ ] Never defaults to `full` bundle
- [ ] Doctor documents enabled nlt-* count

## Refs

- EPIC-109 story 109.4
