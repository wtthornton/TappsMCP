# Story 74.5: MCP config file validation

**Epic:** [EPIC-74-CONSUMER-FEEDBACK-AUTOMATION-PIPELINE-UX](../EPIC-74-CONSUMER-FEEDBACK-AUTOMATION-PIPELINE-UX.md)  
**Priority:** P2 | **LOE:** 2–4 days

## Problem

HomeIQ runs that change `.cursor/mcp.json` or `.mcp.json` (MCP server configuration) do not run any TappsMCP tool over those files. `tapps_validate_changed` only considers Python (and other scorable) files; `tapps_validate_config` targets Dockerfile and docker-compose. MCP JSON configs are thus shipped without validation. Consumers expect either (a) validate_changed to flag non-Python infra files and suggest validation, or (b) validate_config extended to support MCP server config so that config edits can be validated.

## Purpose & Intent

This story exists so that **MCP server config files are not a validation blind spot**. Today we validate code and Docker/infra but not the JSON that configures MCP itself; broken or incomplete MCP config can break the pipeline. Extending validation to MCP config (or at least flagging it in validate_changed) closes that gap and keeps quality coverage consistent across code and config.

## Tasks

- [ ] **Option A:** Extend `tapps_validate_config` to support MCP config type: add `config_type="mcp"` (or auto-detect from path patterns such as `mcp.json`, `.cursor/mcp.json`, `.mcp.json`). Implement a validator that checks JSON structure (e.g. `mcpServers` or top-level keys expected by MCP clients), required server fields, and basic sanity (command/args present). Reuse existing path and size checks.
- [ ] **Option B:** In `tapps_validate_changed`, when changed files include known MCP config paths, add a `next_steps` or `infra_hint`: "MCP config changed; consider running tapps_validate_config(file_path='...') if support is added" — and implement Option A so the hint is actionable.
- [ ] Prefer Option A for direct value; Option B as complementary so validate_changed can mention MCP configs.
- [ ] Document supported MCP config paths and validation rules (e.g. in validators or AGENTS.md).
- [ ] Add unit tests: validate_config with mcp.json (valid/invalid); optionally validate_changed with MCP config in changed list.
- [ ] Update AGENTS.md: when to use validate_config for MCP config files.

## Acceptance criteria

- [ ] At least one of: (A) tapps_validate_config accepts and validates MCP server config files; (B) tapps_validate_changed flags MCP config changes and suggests validation.
- [ ] MCP validator checks JSON structure and key server fields; no false positives on valid Cursor/Claude MCP configs.
- [ ] Backward compatible; existing validate_config behavior unchanged for Dockerfile/docker-compose.
- [ ] Tests and docs updated.

## Files

- `packages/tapps-mcp/src/tapps_mcp/validators/base.py` (detect_config_type, validate_config dispatch)
- New: `packages/tapps-mcp/src/tapps_mcp/validators/mcp_config.py` (or inline in base) — MCP JSON schema/checks
- `packages/tapps-mcp/src/tapps_mcp/server.py` (_VALID_CONFIG_TYPES, tapps_validate_config)
- `packages/tapps-mcp/tests/unit/test_validate_config.py` or new test file
- Optionally `batch_validator.py` / `server_pipeline_tools.py` for Option B
- `AGENTS.md`
