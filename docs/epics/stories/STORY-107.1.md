# validators: pluggable consumer YAML manifest validation

## What

Extension point for consumer brand/template YAML validation without ReportLab-specific core schemas.

## Where

- `packages/tapps-mcp/src/tapps_mcp/validators/base.py:1-143`
- `packages/tapps-mcp/src/tapps_mcp/server.py:364-373`

## Acceptance

- [ ] - [ ] validate_config accepts consumer-registered YAML manifest validators via extension hook or config
- [ ] Core ships no ReportLab-specific field enums; consumer supplies pydantic model or JSON Schema path
- [ ] Auto-detect document manifest YAML under brands/ or templates/ when registered
- [ ] Unit test registers fixture schema and validates sample brand YAML
- [ ] Invalid manifest returns structured findings like other config types

## Refs

docs/epics/EPIC-107.md
