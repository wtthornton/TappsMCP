# server_analysis_tools.py: impact rebuild-documents nudge

## What

Enrich impact analysis with rebuild-documents nudge when layout or template modules change.

## Where

- `packages/tapps-mcp/src/tapps_mcp/server_analysis_tools.py:300-400`
- `packages/tapps-mcp/src/tapps_mcp/server_helpers.py:268-290`

## Acceptance

- [ ] - [ ] tapps_impact_analysis adds recommendation when changed file is under reports/
- [ ] templates/
- [ ] or brands/
- [ ] Recommendation includes suggested shell judge command placeholder and rebuild hint
- [ ] Nudge suppressed for unrelated src/ changes outside document paths
- [ ] Unit test covers document path match and non-match

## Refs

docs/epics/EPIC-107.md
