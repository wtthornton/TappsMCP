# TAPPS Quality Pipeline (optional)

This project can use the TAPPS MCP server for code quality. Tool responses include `next_steps` - consider them when useful.

## Tapps Rules

- Fix root causes — no workarounds.
- Query tapps-mcp (`tapps_lookup_docs`, `tapps_memory`) when uncertain.
- `tapps_lookup_docs` is a cached Context7 front — call it freely.
- Delegate noisy reads/searches to subagents to protect context.
- Write clean, efficient code; match existing style.
- Simplest correct solution wins.
- Linear writes via `linear-issue` skill; multi-issue reads via `linear-read` skill.

## Optional Tool Usage

Consider these steps when they fit your task.

### Session Start

Consider calling `tapps_session_start()` at session start for server info and project context.

### Before Using Any Library API

Consider calling `tapps_lookup_docs(library, topic)` before using an external library to avoid hallucinated APIs.

### After Editing Any Python File

Consider calling `tapps_quick_check(file_path)` after editing Python files.

### Before Declaring Work Complete

Consider calling `tapps_validate_changed(file_paths="file1.py,file2.py")` with explicit paths for multi-file changes and `tapps_checklist(task_type)` to verify steps. Default is quick mode; only use `quick=false` as a last resort.

### Domain Decisions

Consider calling `tapps_lookup_docs(library, topic)` for domain-specific guidance (security patterns, testing, API design, etc.).

### Refactoring or Deleting Files

Consider calling `tapps_impact_analysis(file_path)` before refactoring or deleting to see dependents.

### Infrastructure Config Changes

Consider calling `tapps_validate_config(file_path)` when changing Dockerfile, docker-compose, or infra config.

## Memory System

`tapps_memory` provides persistent cross-session knowledge with **33 actions** (save, search, consolidate, federation, profiles, hive, health, and more). Tiers: architectural/pattern/procedural/context. Scopes: project/branch/session/shared. Max 1500 entries. Memory is manual at low engagement: call `search` at session start and `save` before end. Auto-recall/capture hooks are disabled.

**Cross-session handoff:** when one session needs to pass a token, ID, or payload to a later session, call `tapps_memory(action="save", key="<slug>", value="<payload>")` instead of printing to stdout — the default `project` scope is already cross-session within the same repo. Read it back from the next session with `action="get"` or `action="search"`.

## 5-Stage Pipeline (optional)

When following a full workflow:

1. **Discover** - `tapps_session_start()`; optionally `tapps_memory(action="search")` for context
2. **Research** - `tapps_lookup_docs()` for libraries and domain decisions
3. **Develop** - `tapps_score_file(file_path, quick=True)` during edits
4. **Validate** - `tapps_quick_check()` or `tapps_validate_changed()`
5. **Verify** - `tapps_checklist(task_type)`; optionally `tapps_memory(action="save")` for findings

## Response Guidance

Tool responses include `next_steps` and `pipeline_progress`. Consider following them when appropriate.
Use `tapps_workflow(task_type="feature")` for recommended tool order.

## Quality Gate Notes

Gate failures are sorted by category weight. A security floor of 50/100 is enforced.

## Upgrade & Rollback

After upgrading TappsMCP, consider running `tapps_upgrade`. Use `tapps-mcp rollback` to restore previous configurations.

## CI Integration

TappsMCP can run in CI with `TAPPS_MCP_PROJECT_ROOT` and `tapps-mcp validate-changed`, or Claude Code headless with `tapps_validate_changed`.
