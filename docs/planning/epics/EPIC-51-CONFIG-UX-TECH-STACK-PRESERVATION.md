# Epic 51: Configuration UX & TECH_STACK Preservation

**Priority:** P1 | **LOE:** ~1 week | **Source:** Consumer feedback v2 (BUG-2, ENH-1, ENH-4)

## Problem Statement

Three configuration-related issues degrade the consumer experience:

1. **TECH_STACK.md overwrite** (BUG-2): `tapps_init` unconditionally overwrites a manually curated TECH_STACK.md with auto-detected content that may be empty (e.g., non-Python projects with no detectable source). Unlike AGENTS.md which has smart-merge and an `overwrite_agents_md` parameter, TECH_STACK.md has no protection.

2. **No config schema reference** (ENH-1): `.tapps-mcp.yaml` has no published schema. Users discover valid fields by trial-and-error or reading Python source. While BUG-1 (crash on unknown fields) was fixed with `extra="ignore"`, users still can't discover what fields ARE valid.

3. **Silent cache warming skip** (ENH-4): When `CONTEXT7_API_KEY` is missing, cache warming silently skips with only a structured log entry. The init result includes `"skipped": "no_api_key"` but no user-visible warning or guidance.

## Stories

### Story 51.1: TECH_STACK.md overwrite protection

**Files:** `pipeline/init.py`, `server_pipeline_tools.py`

1. Add `overwrite_tech_stack_md: bool = False` to `BootstrapConfig` dataclass
2. Add matching parameter to `bootstrap_pipeline()` and `tapps_init()` MCP tool
3. When `overwrite_tech_stack_md=False` and TECH_STACK.md already exists:
   - Skip writing entirely (preserve user content)
   - Return `"action": "preserved"` in the result
4. When `overwrite_tech_stack_md=True`, overwrite as current behavior
5. Add CLI `--overwrite-tech-stack` flag to `tapps-mcp init`
6. Add test: existing TECH_STACK.md with custom content is preserved by default
7. Add test: `overwrite_tech_stack_md=True` overwrites as before

**Acceptance criteria:**
- Default `tapps_init` never overwrites existing TECH_STACK.md
- Explicit `overwrite_tech_stack_md=True` still works
- Result dict clearly indicates whether file was preserved, created, or updated

### Story 51.2: Config schema reference documentation

**Files:** `cli.py`, new `docs/CONFIG_REFERENCE.md`

1. Add `tapps-mcp show-config` CLI command that dumps the current effective config as YAML with comments
2. Generate `docs/CONFIG_REFERENCE.md` documenting all `.tapps-mcp.yaml` fields:
   - Field name, type, default value, description
   - Nested model fields (memory, adaptive, docker, scoring_weights, quality_gate)
   - Example `.tapps-mcp.yaml` for common scenarios (minimal, strict, non-Python project)
3. Optionally: add `tapps-mcp config-schema` that outputs JSON Schema from Pydantic model

**Acceptance criteria:**
- `tapps-mcp show-config` prints effective configuration
- `docs/CONFIG_REFERENCE.md` covers all settings fields
- At least 3 example configs for common use cases

### Story 51.3: Prominent cache warming skip warnings

**Files:** `pipeline/init.py`, `knowledge/warming.py`

1. In `pipeline/init.py` `_warm_caches()`, when warming returns `"skipped": "no_api_key"`:
   - Add a `"warning"` field to the result: `"Cache warming skipped: CONTEXT7_API_KEY not set. Add it to your MCP server env config."`
   - Emit `ctx.info()` with the warning message if ctx is available
2. In `warming.py`, upgrade `logger.info("cache_warming_skipped")` to `logger.warning()`
3. Collect all warnings from init sub-steps and surface them in a top-level `"warnings"` list in the init result

**Acceptance criteria:**
- Init result includes clear `"warnings"` list when cache warming is skipped
- Warning includes actionable guidance (how to set the API key)
- `ctx.info()` delivers real-time notification to MCP clients

## Dependencies

- None (all changes are self-contained)

## Testing

- Unit tests for TECH_STACK.md preservation (create, update, preserve scenarios)
- Unit test for `show-config` CLI command output
- Unit test for warning propagation in init result
- Integration test: full `tapps_init` with existing TECH_STACK.md
