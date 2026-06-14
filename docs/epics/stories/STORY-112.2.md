# validate_changed.py: cross-repo explicit file_paths

## What

validate_changed.py: cross-repo explicit file_paths

## Where

- `packages/tapps-mcp/src/tapps_mcp/tools/validate_changed.py:1-200`
- `packages/tapps-mcp/src/tapps_mcp/tools/validate_changed_collection.py:1-150`

## Why

validate-changed works from Cursor sessions opened in consumer repos

## Acceptance

- [ ] - [ ] Explicit repo-relative file_paths validate when project_root differs from MCP host
- [ ] path_hint names TAPPS_MCP_HOST_PROJECT_ROOT when mapping fails
- [ ] Regression test covers validate-changed from sibling repo workspace
