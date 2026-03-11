# Story 78.1: Tool tapps_get_canonical_persona (resolve name → allowlisted path, return markdown)

**Epic:** [EPIC-78-CANONICAL-PERSONA-INJECTION-PROMPT-INJECTION-DEFENSE](../EPIC-78-CANONICAL-PERSONA-INJECTION-PROMPT-INJECTION-DEFENSE.md)  
**Priority:** P2 | **LOE:** 3–5 days

## Problem

There is no TappsMCP tool that returns the canonical (trusted) persona definition from project- or user-controlled agent/rule files. To support “inject trusted persona when user requests one,” we need a tool that accepts a persona name, resolves it to an allowlisted path, and returns the file content.

## Purpose & Intent

This story exists so that **the pipeline can retrieve the trusted persona definition from project- or user-controlled files** when the user requests a persona by name. Without this tool, there is no programmatic way to inject canonical content; the tool is the foundation for the rule/instruction in 78.2 and for the overall prompt-injection defense.

## Tasks

- [ ] Add a new MCP tool `tapps_get_canonical_persona` in TappsMCP server. Suggested signature: `persona_name: str`, `project_root: str | None` (optional; default from host or TAPPS_MCP_HOST_PROJECT_ROOT). Return: structured (e.g. `content: str`, `source_path: str`, `slug: str`) or simple `content` string (full file body including frontmatter).
- [ ] **Slug resolution:** Normalize `persona_name` to a slug: lowercase, replace spaces/special chars with single hyphen, strip leading/trailing hyphens (e.g. “Frontend Developer” → `frontend-developer`, “tapps-reviewer” → `tapps-reviewer`). Match both “name” and “name.md” / “name.mdc” as filename.
- [ ] **Lookup order:** (1) `project_root/.claude/agents/<slug>.md`, (2) `project_root/.cursor/agents/<slug>.md`, (3) `project_root/.cursor/rules/<slug>.mdc`, (4) `project_root/.cursor/rules/<slug>.md`, (5) optionally `Path.home()/.claude/agents/<slug>.md`. Use first existing file; do not read outside these allowlisted directories.
- [ ] **Path safety:** Use `PathValidator(project_root).validate_path(path, must_exist=True)` from `tapps_core.security.path_validator` for project paths. For user home `~/.claude/agents/`, resolve to absolute path and ensure the resolved path is strictly under `Path.home()/.claude/agents/` (no traversal). Reject any path outside project_root or the allowed user dir.
- [ ] **Not found:** If no file matches, return a clear error (tool result or raised MCP error) so the caller can handle gracefully (e.g. “Persona ‘X’ not found in .claude/agents, .cursor/agents, or .cursor/rules”).
- [ ] **Tests:** Unit tests for slug resolution (various inputs), lookup order (mock filesystem or temp dir), path validator rejection of traversal, not-found case. Add tests in `packages/tapps-mcp/tests/unit/` (e.g. `test_canonical_persona.py` or under existing server test module).
- [ ] Register the tool in the TappsMCP server (same pattern as other tools: `@mcp.tool()`, `_record_call("tapps_get_canonical_persona")`). Document in AGENTS.md under “When to use each tool.”

## Acceptance criteria

- [ ] `tapps_get_canonical_persona(persona_name, project_root?)` is callable via MCP and returns the full markdown content of the first matching file in allowlisted dirs.
- [ ] Slug resolution and lookup order are implemented as specified; path validator is used; no reads outside allowlisted dirs.
- [ ] Not-found returns a clear error; no crash.
- [ ] Unit tests cover slug, lookup order, path safety, and not-found.

## Files

- `packages/tapps-mcp/src/tapps_mcp/server.py` (or a dedicated `server_persona_tools.py` if preferred) — add tool handler
- New helper module (optional): `packages/tapps-mcp/src/tapps_mcp/pipeline/persona_resolver.py` — slug + lookup order + path allowlist logic (keeps server handler thin)
- `packages/tapps-core/src/tapps_core/security/path_validator.py` — use existing PathValidator; no changes unless allowlist needs to be configurable
- `packages/tapps-mcp/tests/unit/test_canonical_persona.py` or `test_server.py` (extend) — tests for tool and resolver
- `AGENTS.md` — add one line for when to use tapps_get_canonical_persona

## Dependencies

- Epic 12 (platform integration); path validator and init/upgrade persona paths are existing.

## References

- docs/planning/research/2026-AGENTS-RESEARCH-CLAUDE-CURSOR-AGENCY-AGENTS.md §7
- tapps_core.security.path_validator.PathValidator
- platform_subagents.py (where .claude/agents and .cursor/agents content is defined)
