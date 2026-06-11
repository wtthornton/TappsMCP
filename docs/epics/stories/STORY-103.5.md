# report-studio domain gate via judges preset

## What

report-studio domain gate via judges preset

## Where

- `packages/tapps-mcp/src/tapps_mcp/tools/validate_changed.py:535-543`
- `packages/tapps-mcp/src/tapps_mcp/pipeline/report_studio/installer.py:1-186`
- `packages/tapps-core/src/tapps_core/config/settings.py`

## Acceptance

- [ ] - .tapps-mcp.yaml supports validate_changed.judges preset list (pytest target for report-studio verify)
- When nlt-report-studio pinned in pyproject
- [ ] session_start or checklist recommends judges preset
- AGENTS.md documents judges param for domain audit after PDF rebuild
- Example judges config for thin-page/hyperlink audit via existing run_judges path
- Unit test: load_settings merges judges preset from yaml
