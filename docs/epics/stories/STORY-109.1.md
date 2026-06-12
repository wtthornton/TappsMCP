# server.py: nlt-code-quality and nlt-platform-admin profiles

## What

Add NLT plugin MCP profiles for daily coding and platform admin: `nlt-code-quality` (15 tools) and `nlt-platform-admin` (14 tools), wired via `tool_preset` / `--profile` CLI flag.

## Where

1. `packages/tapps-mcp/src/tapps_mcp/server.py:253-420` — frozensets + `_resolve_allowed_tools`
2. `packages/tapps-mcp/src/tapps_mcp/cli.py:43-60` — `serve --profile` option
3. `packages/tapps-mcp/tests/unit/test_enabled_tools_config.py` — profile resolution tests
4. `docs/architecture/nlt-mcp-plugin-spec.yaml:102-283` — canonical tool lists

## Why

Phase 1 of Epic 109. Enables `uv run tapps-mcp serve --profile nlt-code-quality` as the v1.0 developer coding server (~9 eager tools).

## Acceptance

- [ ] `tool_preset=nlt-code-quality` registers exactly 15 tools per spec (no dependency_scan — release-only)
- [ ] `tool_preset=nlt-platform-admin` registers exactly 14 tools including brain elevation tools
- [ ] Profiles are disjoint (no tool in both tapps-mcp NLT profiles)
- [ ] `tapps-mcp serve --profile nlt-code-quality` sets preset before server import
- [ ] Tests pass in `test_enabled_tools_config.py`
- [ ] `--profile full` and unset preset still register all 38 tapps tools

## Refs

- EPIC-109 story 109.1
- `docs/architecture/nlt-mcp-plugin-spec.yaml`
