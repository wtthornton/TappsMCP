# Epic 53: CLI Parity for MCP-Only Tools

**Status:** Complete
**Priority:** P1 | **LOE:** ~1 week | **Source:** Consumer feedback v2 (ENH-2, ENH-3)

## Problem Statement

When the MCP server connection is lost mid-session (host restart, Cursor reload), all TappsMCP tools become unavailable. Key tools like `tapps_lookup_docs`, `tapps_memory`, `tapps_consult_expert`, and `tapps_research` have no CLI equivalents, leaving users without fallback access.

Additionally, MCP tool reconnection after host restart is an MCP protocol limitation that cannot be solved in TappsMCP itself. The best mitigation is CLI fallback + clear documentation.

## Stories

### Story 53.1: `tapps-mcp memory` CLI command

**Files:** `cli.py`

1. Add `tapps-mcp memory` Click group with subcommands:
   - `tapps-mcp memory list [--tier TIER] [--scope SCOPE]`
   - `tapps-mcp memory save --key KEY --value VALUE [--tier TIER] [--tags TAGS]`
   - `tapps-mcp memory get --key KEY`
   - `tapps-mcp memory search --query QUERY [--limit N]`
   - `tapps-mcp memory delete --key KEY`
   - `tapps-mcp memory import --file PATH`
   - `tapps-mcp memory export [--file PATH]`
2. Reuse `MemoryStore` from `memory/store.py` directly (no MCP needed)
3. Output as formatted table (list/search) or JSON (get/save)
4. Respect `TAPPS_MCP_PROJECT_ROOT` for memory storage location

**Acceptance criteria:**
- All 7 memory subcommands work without MCP server
- Output is human-readable in terminal
- `--json` flag for machine-readable output

### Story 53.2: `tapps-mcp lookup-docs` CLI command

**Files:** `cli.py`

1. Add `tapps-mcp lookup-docs --library LIB [--topic TOPIC] [--mode code|info]`
2. Reuse `LookupEngine` from `knowledge/lookup.py`
3. Print documentation content to stdout, truncated to terminal width
4. Support `--raw` flag for full untruncated output
5. Requires `CONTEXT7_API_KEY` env var (same as MCP tool)

**Acceptance criteria:**
- `tapps-mcp lookup-docs --library fastapi --topic routing` returns docs
- Graceful error message when API key is missing
- Expert fallback works same as MCP tool

### Story 53.3: `tapps-mcp research` CLI command

**Files:** `cli.py`

1. Add `tapps-mcp research --question "..." [--domain DOMAIN] [--library LIB]`
2. Reuse `ExpertEngine` from `experts/engine.py` + `LookupEngine`
3. Print expert answer + sources to stdout
4. Support `--json` flag for structured output

**Acceptance criteria:**
- Research produces same output as MCP tool
- Domain auto-detection works
- Sources are listed with confidence scores

### Story 53.4: `tapps-mcp consult-expert` CLI command

**Files:** `cli.py`

1. Add `tapps-mcp consult-expert --question "..." [--domain DOMAIN]`
2. Reuse `ExpertEngine` directly
3. Print answer, confidence, sources, and domain
4. Support `--json` flag

**Acceptance criteria:**
- Expert consultation works without MCP server
- All 17 domains accessible

### Story 53.5: Document MCP reconnection limitation

**Files:** `docs/TROUBLESHOOTING.md` (new)

1. Create troubleshooting guide documenting:
   - MCP tools become unavailable after host restart (known MCP protocol limitation)
   - Recovery steps: restart Claude Code session, or re-enable MCP server in Cursor settings
   - CLI fallback commands for when MCP is unavailable
   - How to verify MCP server health: `tapps-mcp doctor`
2. Reference troubleshooting guide from AGENTS.md and README.md

**Acceptance criteria:**
- Clear, actionable troubleshooting steps
- CLI fallback commands documented per scenario

## Dependencies

- None (reuses existing engine classes directly)

## Testing

- Unit tests for each CLI command (mock engines, verify output format)
- Integration test: CLI memory round-trip (save → get → list → delete)
- Integration test: CLI lookup-docs with mock Context7 response
