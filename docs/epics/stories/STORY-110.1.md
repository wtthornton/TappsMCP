# cli.py: HTTP-safe memory search + continue-session ergonomics

## What

Route `tapps-mcp memory search` through BrainBridge when brain HTTP is configured; update handoff/continue skills for full markdown mirror and `memory recall --recall-key session-handoff`; add doctor HTTP-only memory CLI guidance.

## Where

- `packages/tapps-mcp/src/tapps_mcp/cli.py:1130-1200`
- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_skills.py:50-64`
- `packages/tapps-mcp/src/tapps_mcp/distribution/doctor.py` (`check_memory_cli_http_mode`)
- `packages/tapps-mcp/tests/unit/test_cli_memory.py:209-260`
- `packages/tapps-mcp/tests/unit/test_platform_skills.py:487-510`
- `docs/MEMORY_REFERENCE.md:219-227`

## Acceptance

- [ ] `memory search` calls `bridge.search` when `create_brain_bridge` returns non-None
- [ ] `memory search` falls back to local `MemoryStore` only when bridge is unavailable
- [ ] Handoff skill instructs `memory save --value "$(cat .tapps-mcp/session-handoff.md)"`
- [ ] Continue skill prefers `memory recall --recall-key session-handoff` with `memory search` as alternative
- [ ] Doctor row `Memory CLI (HTTP mode)` explains DSN-required subcommands when HTTP-only
- [ ] Unit tests cover bridge-first search and HTTP-mode doctor check
