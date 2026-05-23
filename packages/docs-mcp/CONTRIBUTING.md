# Contributing to docs-mcp

docs-mcp is part of the TappsMCP monorepo. See the [top-level CONTRIBUTING.md](../../CONTRIBUTING.md) for general setup, workflow, and code conventions. This file covers docs-mcp-specific rules.

## Running docs-mcp tests

```bash
uv run pytest packages/docs-mcp/tests/ -v         # ~2,170+ tests
uv run pytest packages/docs-mcp/tests/ -m "not slow" -v  # skip slow tests
```

## Adding a new docs-mcp tool

1. Add the handler in the appropriate `server_*.py` file using `@mcp.tool()`.
2. Register it in the tool registry / checklist map.
3. Add to `AGENTS.md` tools reference.
4. Add tests in `packages/docs-mcp/tests/unit/`.

## Tool Versioning

The MCP specification does not include tool-level versioning — it only date-stamps protocol revisions (most recent as of 2025-11-25). When a change would break existing callers (parameter rename, return-type change, removed field), use an additive rename instead:

1. Ship the new behavior under `<tool_name>_v2` (or `_v3`, etc.).
2. Keep the old name live and mark it deprecated (see [Deprecation Playbook](#deprecation-playbook) below).
3. Remove the old name only after the minimum deprecation window has elapsed.

This rule applies to both `docs-mcp` and `tapps-mcp` tools.

## Deprecation Playbook

Follow the same three-phase process documented in the [top-level CONTRIBUTING.md](../../CONTRIBUTING.md#deprecation-playbook):

1. **Phase 1 — Soft deprecation**: add `DEPRECATED` note to docstring + `AGENTS.md`, return structured deprecation envelope, announce in `CHANGELOG.md`.
2. **Phase 2 — Surface reduction** (optional): update checklist to flag old name; emit `brain_record_event` for usage tracking.
3. **Phase 3 — Hard removal**: remove handler + registrations, create migration doc at `docs/migrations/<tool_name>.md` using the [template](../../docs/migrations/template.md), bump minor version.

**Minimum window**: 90 days or one minor release after Phase 1, whichever is later.
