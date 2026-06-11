# search_first warm reportlab/pypdf consumer deps

## What

search_first warm reportlab/pypdf consumer deps

## Where

- `packages/tapps-mcp/src/tapps_mcp/tools/session_start_helpers.py:873-935`
- `packages/tapps-mcp/tests/unit/test_server_pipeline_tools.py:1844-1915`

## Acceptance

- [ ] - search_first covered list includes reportlab and pypdf when pinned in pyproject optional-deps or dependency-groups
- Background cache_warm schedules lookup_docs for those libraries on session_start
- Unit test: pyproject with nlt-report-studio/reportlab adds entries to search_first.covered
