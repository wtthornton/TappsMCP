# pip_audit.py: scope scan to target project

## What

pip_audit.py: scope scan to target project

## Where

- `packages/tapps-mcp/src/tapps_mcp/tools/pip_audit.py:1-200`
- `packages/tapps-mcp/src/tapps_mcp/server_analysis_tools.py:1-300`

## Why

dependency_scan reports only dependencies relevant to the target repo

## Acceptance

- [ ] - [ ] dependency_scan uses project venv or uv.lock when project_root set
- [ ] Global site-packages CVEs (e.g. torch) excluded from project scan
- [ ] scan_source reports project-scoped origin in response
