# Epic 47: Workspace-Scoped Init

**Status:** Complete
**Priority:** P1
**Estimated LOE:** ~1-1.5 weeks
**Dependencies:** None (builds on existing init infrastructure)
**Blocks:** None
**Source:** Consuming project feedback — `OpenClawAgents/docs/tapps-mcp-init.md`

---

## Goal

Ensure `tapps-mcp init` defaults to **workspace-scoped** configuration so consuming projects get project-local setup without accidentally writing to user-global config files (e.g. `~/.claude.json`). The current default scope is `"user"`, which writes Claude Code config to `~/.claude.json` — a global location that affects all projects. Consuming projects expect init to be workspace-only by default.

## Problem Statement

A consuming project (OpenClawAgents) documented that `tapps-mcp init` should:

1. **Default to workspace/project scope** — not write to `~/.claude.json` unless explicitly requested
2. **Keep all generated config under the project directory** — so tapps-mcp is enabled only for that repo
3. **Respect `--scope project`** as the recommended default workflow

### Current Behavior (problematic)

| Host | Default Scope | Config Written |
|---|---|---|
| `claude-code` | `user` (default) | `~/.claude.json` (global!) |
| `cursor` | n/a (always project) | `.cursor/mcp.json` |
| `vscode` | n/a (always project) | `.vscode/mcp.json` |

- CLI `--scope` flag exists but **defaults to `"user"`** — the unsafe choice
- `tapps_init` MCP tool has **no scope parameter** (it doesn't write MCP config, but this is confusing to users)
- Auto-detection (`--host auto`) writes to `~/.claude.json` by default when Claude Code is detected
- The elicitation wizard has no scope question
- Doctor checks both paths but doesn't warn about user-scope being set
- `tapps-mcp upgrade` has no scope awareness

### Desired Behavior

| Host | Default Scope | Config Written |
|---|---|---|
| `claude-code` | `project` (new default) | `.mcp.json` (project root) |
| `cursor` | project (unchanged) | `.cursor/mcp.json` |
| `vscode` | project (unchanged) | `.vscode/mcp.json` |

---

## Stories

### Story 47.1: Change CLI default scope to "project"

**LOE:** S (~2-3 hours)
**Files:** `packages/tapps-mcp/src/tapps_mcp/cli.py`

Change the `--scope` flag default from `"user"` to `"project"` so that `tapps-mcp init` writes to `.mcp.json` (project root) instead of `~/.claude.json` by default.

**Acceptance Criteria:**
- `--scope` default is `"project"`
- `tapps-mcp init` (no flags) writes `.mcp.json` in project root for Claude Code
- `tapps-mcp init --scope user` still writes to `~/.claude.json` (opt-in)
- Help text updated to explain the change
- Existing `--scope project` behavior unchanged

**Tests:**
- Unit test: verify default scope is "project"
- Integration test: CLI invocation without `--scope` produces `.mcp.json`
- Integration test: CLI with `--scope user` produces `~/.claude.json` path

---

### Story 47.2: Add scope parameter to `tapps_init` MCP tool

**LOE:** M (~4-6 hours)
**Files:** `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py`, `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py`

The `tapps_init` MCP tool currently does not write MCP config files at all — it only writes pipeline artifacts (AGENTS.md, hooks, skills, etc.). Add an optional `mcp_config` parameter that, when enabled, also writes the MCP server config entry to the appropriate project-scoped config file.

**Acceptance Criteria:**
- New optional `mcp_config: bool = False` parameter on `tapps_init`
- When `mcp_config=True`, writes project-scoped MCP config (`.mcp.json`, `.cursor/mcp.json`, `.vscode/mcp.json`) based on `platform` parameter
- Never writes to `~/.claude.json` from the MCP tool (always project scope)
- Default `False` preserves backward compatibility
- Clear documentation in tool description about what it does vs CLI init

**Tests:**
- Unit test: `mcp_config=False` (default) does not write any MCP config
- Unit test: `mcp_config=True` with `platform="claude"` writes `.mcp.json`
- Unit test: `mcp_config=True` with `platform="cursor"` writes `.cursor/mcp.json`
- Unit test: verify no path resolves to `~/.claude.json`

---

### Story 47.3: Add scope to elicitation wizard

**LOE:** S (~2-3 hours)
**Files:** `packages/tapps-mcp/src/tapps_mcp/common/elicitation.py`

Add a scope question to the interactive init wizard when Claude Code is detected, so users are explicitly asked whether they want project-scoped or user-scoped config.

**Acceptance Criteria:**
- New wizard question: "Config scope: project (recommended) or user?"
- Default/recommended option is "project"
- Question only shown when Claude Code is a detected host
- Selected scope flows through to `_generate_config()`
- Wizard confirmation message accurately reflects chosen scope

**Tests:**
- Unit test: wizard includes scope question when Claude Code detected
- Unit test: wizard skips scope question for Cursor-only / VS Code-only
- Unit test: selected scope propagates correctly

---

### Story 47.4: Doctor warnings for user-scoped config

**LOE:** S (~2-3 hours)
**Files:** `packages/tapps-mcp/src/tapps_mcp/distribution/doctor.py`

Add a diagnostic check that warns when tapps-mcp is configured in `~/.claude.json` (user scope) and a project-scoped `.mcp.json` also exists or could be used instead.

**Acceptance Criteria:**
- New check: `check_scope_recommendation()` that warns about user-scoped Claude Code config
- Warning message recommends migrating to project scope with instructions
- Check passes (no warning) when only project-scoped config exists
- Check passes when no Claude Code config exists at all
- Severity: `warning` (not `error`) — user scope still works, just not recommended

**Tests:**
- Unit test: warning emitted when `~/.claude.json` has tapps-mcp entry
- Unit test: no warning when only `.mcp.json` exists
- Unit test: no warning when neither exists

---

### Story 47.5: Add `--scope` to `tapps-mcp upgrade`

**LOE:** S (~2-3 hours)
**Files:** `packages/tapps-mcp/src/tapps_mcp/cli.py`, `packages/tapps-mcp/src/tapps_mcp/pipeline/upgrade.py`, `packages/tapps-mcp/src/tapps_mcp/distribution/setup_generator.py`

Currently `tapps-mcp upgrade` refreshes platform artifacts but has no scope awareness. If a user initially set up with `--scope user` and later wants to migrate to project scope, upgrade should support this.

**Acceptance Criteria:**
- New `--scope` flag on `tapps-mcp upgrade` CLI command, default `"project"`
- When upgrading, if MCP config exists at the old scope location, offer to migrate it
- `--dry-run` shows what would be migrated
- Does not delete the old config automatically (just adds new, warns about old)

**Tests:**
- Unit test: upgrade with `--scope project` writes to `.mcp.json`
- Unit test: dry-run shows migration plan without writing
- Unit test: upgrade detects existing user-scope config and warns

---

### Story 47.6: Documentation and AGENTS.md updates

**LOE:** S (~1-2 hours)
**Files:** `AGENTS.md`, `README.md`, `packages/tapps-mcp/src/tapps_mcp/prompts/agents_template_*.md`

Update all documentation to reflect the new default scope and recommend project-scoped init.

**Acceptance Criteria:**
- AGENTS.md quickstart shows `tapps-mcp init` (which now defaults to project scope)
- README.md installation section updated
- Agent template prompts reference project scope
- Migration note for users who previously used user scope

**Tests:**
- No code tests (documentation only)
- Review: verify no documentation references assume user scope as default

---

## Implementation Order

```
47.1 (default scope) → 47.3 (wizard) → 47.4 (doctor) → 47.2 (MCP tool) → 47.5 (upgrade) → 47.6 (docs)
```

Story 47.1 is the critical fix — changing the default. Stories 47.2-47.5 are supporting improvements. Story 47.6 is documentation cleanup.

## Risk Assessment

- **Breaking change risk: LOW** — the `--scope` flag already exists; we're only changing the default. Users who explicitly pass `--scope user` are unaffected.
- **Backward compat:** Users who previously ran `tapps-mcp init` (with default `--scope user`) already have config in `~/.claude.json`. The doctor warning (47.4) will guide them to migrate.
- **MCP tool scope (47.2):** Adding `mcp_config` as opt-in (`False` default) means no change for existing MCP tool users.

## Files Affected (Summary)

| File | Stories |
|---|---|
| `cli.py` | 47.1, 47.5 |
| `setup_generator.py` | 47.1, 47.5 |
| `server_pipeline_tools.py` | 47.2 |
| `pipeline/init.py` | 47.2 |
| `common/elicitation.py` | 47.3 |
| `distribution/doctor.py` | 47.4 |
| `pipeline/upgrade.py` | 47.5 |
| `AGENTS.md`, `README.md`, prompts | 47.6 |
