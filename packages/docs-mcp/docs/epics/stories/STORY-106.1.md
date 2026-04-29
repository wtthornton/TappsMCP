# Spike: confirm Linear plugin project-update write path

## What

Research spike: determine which Linear API surface the tapps_release_update tool should use to post a project update.

## Where

- `packages/docs-mcp/docs/epics/EPIC-106.md:1-50`
- `packages/tapps-mcp/src/tapps_mcp/server_helpers.py:1-80`

## Acceptance

- [ ] Query the Linear plugin tool list and GraphQL schema to determine whether a projectUpdate create/update mutation is available
- [ ] Document the chosen write path (projectUpdate native / save_document / save_comment) as a one-paragraph ADR comment posted to TAP-1108
- [ ] Record any API limitations (field restrictions field types rate limits) that will constrain the template design in story 2

## Refs

TAP-1108
