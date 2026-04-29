# linear-standards.md rule update + release-update docs

## What

Documentation-only story.

## Where

- `.claude/rules/linear-standards.md:1-80`
- `AGENTS.md:1-60`
- `packages/tapps-mcp/src/tapps_mcp/config/settings.py:1-80`

## Acceptance

- [ ] linear-standards.md has a new Release Updates section documenting the tapps_release_update flow (trigger → generate → validate → post → invalidate)
- [ ] AGENTS.md and README.md tool lists include tapps_release_update with a one-line description
- [ ] .tapps-mcp.yaml schema documents the release_update_overrides block (extra_sections footer custom_links fields)

## Refs

TAP-1108
