# init.py: auto-merge discovered judge preset

## What

Auto-merge discovered judge preset on init/upgrade for document-shipping consumers.

## Where

- `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py:940-965`
- `packages/tapps-mcp/src/tapps_mcp/pipeline/report_studio/installer.py:172-186`
- `packages/tapps-core/src/tapps_core/config/settings.py:748-758`

## Acceptance

- [ ] - [ ] tapps_init and tapps_upgrade merge validate_changed.judges when document tooling detected
- [ ] Preset uses path discovery (reports/
- [ ] build script glob
- [ ] audit test glob) not hard-coded ReportLab paths
- [ ] Merged judges default blocking true for document audit gates
- [ ] Existing consumer-defined judges are preserved (merge not overwrite)
- [ ] Unit test uses fixture project_root with nlt-report-studio pin

## Refs

docs/epics/EPIC-105.md
