# init.py: _bootstrap_claude skips CLAUDE.md obligation updates on upgrade

## What

On 2026-04-24 I shipped TAP-964 (tapps_linear_snapshot_get/put/invalidate) and TAP-967 (narrow list_issues triage) in tapps-mcp 3.3.0.

## Where

- `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py:1217-1247`
- `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py:1284-1350`

## Acceptance

- [ ] tapps_upgrade refreshes a BEGIN/END-marker-wrapped TAPPS obligations region in CLAUDE.md without touching content outside the markers
- [ ] First upgrade run on a consumer with an unmarked legacy TAPPS Quality Pipeline section auto-wraps the existing default obligations paragraph in markers (one-time migration) and leaves custom lines outside the wrap untouched
- [ ] User-customized lines outside the marked region survive a round-trip through tapps_upgrade (regression asserted in tests)
- [ ] Unit tests cover four cases: fresh project with no CLAUDE.md / legacy unmarked TAPPS section / marked block with stale obligations to refresh / customized lines both inside and outside the marker
- [ ] CHANGELOG entry documents the one-time auto-wrap migration behavior so maintainers review the first diff

## Refs

TAP-964, TAP-967
