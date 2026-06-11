# settings.py: report_authoring preset path overrides

## What

Add report_authoring preset or path-based test_coverage overrides for narrative layout modules.

## Where

- `packages/tapps-core/src/tapps_core/config/settings.py:73-78`
- `packages/tapps-mcp/src/tapps_mcp/scoring/scorer.py:509-523`
- `packages/tapps-mcp/src/tapps_mcp/config/default.yaml:1-20`

## Acceptance

- [ ] - [ ] quality_preset report_authoring registered in PRESETS or scoring path overrides config
- [ ] Consumer can set narrative_path_globs (default reports/**) with test_coverage weight 0
- [ ] reports/foo/story.py passes gate when other categories pass and no unit test exists
- [ ] src/ modules still use standard test_coverage weight under report_authoring preset
- [ ] Unit tests cover preset selection and path glob matching

## Refs

docs/epics/EPIC-106.md
