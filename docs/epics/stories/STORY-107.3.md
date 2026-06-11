# init.py: document-builder memory profile preset

## What

Optional document-builder memory profile with auto-recall keys for document-shipping repos.

## Where

- `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py:940-965`
- `packages/tapps-mcp/src/tapps_mcp/server_memory_tools.py:1-80`

## Acceptance

- [ ] - [ ] Optional memory.profile document-builder offered on init when document tooling detected
- [ ] Profile seeds architectural keys: code gate vs document gate
- [ ] audit profiles
- [ ] env ROOT siblings pattern
- [ ] Consumer can override or disable via .tapps-mcp.yaml
- [ ] Unit test asserts profile suggestion in init result when reports/ present

## Refs

docs/epics/EPIC-107.md
