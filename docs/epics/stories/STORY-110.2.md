# handoff_write.py: atomic handoff write CLI and MCP tool

## What

Add `tapps-mcp handoff write` (and optional MCP `tapps_handoff_save`) that atomically persists canonical markdown, mirrors full body to brain, validates TAP-3573 schema, and optionally triggers session-end flywheel.

## Where

- `packages/tapps-mcp/src/tapps_mcp/tools/handoff_write.py` (new)
- `packages/tapps-mcp/src/tapps_mcp/cli.py` (`handoff` command group)
- `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py` (optional MCP handler)
- `packages/tapps-mcp/tests/unit/test_handoff_write.py` (new)

## Acceptance

- [ ] CLI accepts structured args or stdin/file markdown and writes `.tapps-mcp/session-handoff.md`
- [ ] Brain mirror uses full markdown body with key `session-handoff`, tier `context`, tags `handoff,cross-session`
- [ ] Metadata includes `git_sha`, `git_branch`, `linear_p0`, `updated_at` when available
- [ ] P0/Open schema violations fail with actionable lint errors (reuse `handoff_schema`)
- [ ] `--session-end` flag optionally calls session-end flywheel; default off
- [ ] Unit tests cover happy path, lint failure, and brain-unavailable degrade
