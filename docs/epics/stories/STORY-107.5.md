# TROUBLESHOOTING.md: fix yaml config_type doc drift

## What

Align TROUBLESHOOTING validate_config yaml guidance with actual core config types.

## Where

- `docs/TROUBLESHOOTING.md:37-51`
- `packages/tapps-mcp/src/tapps_mcp/server.py:364-373`

## Acceptance

- [ ] - [ ] TROUBLESHOOTING documents only implemented validate_config types OR points to extension hook from 107.1
- [ ] Remove or qualify config_type yaml example until pluggable validator ships
- [ ] Cross-link checklist-policy.yaml pattern for brand YAML changes
- [ ] No misleading copy-paste example that returns invalid_config_type today

## Refs

docs/epics/EPIC-107.md
