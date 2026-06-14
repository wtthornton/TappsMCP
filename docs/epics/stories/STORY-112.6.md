# validate_changed_diagnostics.py: close EPIC-103 gaps

## What

validate_changed_diagnostics.py: close EPIC-103 gaps

## Where

- `packages/tapps-mcp/src/tapps_mcp/tools/validate_changed_diagnostics.py:1-200`
- `packages/tapps-mcp/src/tapps_mcp/tools/session_start_helpers.py:1-150`

## Why

validate_changed failures are actionable without per-file quick_check reruns

## Acceptance

- [ ] - [ ] Gate failures include top lint/type/security findings per file
- [ ] session_start cli_fallback hints match implemented CLI commands
- [ ] Archived EPIC-103 acceptance items marked done or deferred with rationale
