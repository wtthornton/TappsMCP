# doctor.py: report judge configuration status

## What

Extend doctor report-studio row to surface validate_changed.judges configuration status.

## Where

- `packages/tapps-mcp/src/tapps_mcp/distribution/doctor.py:3290-3410`
- `packages/tapps-core/src/tapps_core/config/settings.py:748-758`

## Acceptance

- [ ] - [ ] doctor check_report_studio row includes judges configured or missing detail
- [ ] When installed but judges empty
- [ ] detail recommends validate_changed.judges preset
- [ ] When judges present
- [ ] lists count and blocking vs advisory split
- [ ] Unit test covers installed+judges
- [ ] installed+no-judges
- [ ] not-installed

## Refs

docs/epics/EPIC-105.md
