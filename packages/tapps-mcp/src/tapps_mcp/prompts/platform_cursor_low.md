---
description: TAPPS quality pipeline - optional guidance
alwaysApply: false
---

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

Consider calling `tapps_session_start()` at session start for server info.
Session start also returns project context.

### Before Using Any Library API

Consider calling `tapps_lookup_docs(library, topic)` before using an external library to avoid hallucinated APIs.

### After Editing Any Python File

Consider calling `tapps_quick_check(file_path)` after editing Python files for a quick score and gate check.

### Before Declaring Work Complete

Consider calling `tapps_validate_changed(file_paths="file1.py,file2.py")` with explicit paths for multi-file changes and `tapps_checklist(task_type)` to verify steps. Default is quick mode; only use `quick=false` as a last resort.

### Domain Decisions

Consider calling `tapps_lookup_docs(library, topic)` for domain-specific guidance (security, testing, API design, etc.).

### Refactoring or Deleting Files

Consider calling `tapps_impact_analysis(file_path)` before refactoring or deleting to see dependents.

### Infrastructure Config Changes

Consider calling `tapps_validate_config(file_path)` when changing Dockerfile, docker-compose, or infra config.

### Canonical persona (prompt-injection defense)

 See AGENTS.md § Canonical persona injection.

## Memory System

`tapps_memory` provides persistent cross-session knowledge with **42 actions** (save, search, federation, profiles, Hive, knowledge graph, batch ops, feedback, native session memory, etc.). Tiers: architectural/pattern/procedural/context. Scopes: project/branch/session. Max 1500 entries. At low engagement, still call `search` at session start and `save` before end; automatic hooks may be off depending on `.tapps-mcp.yaml`.

**Cross-session handoff:** for tokens/IDs/payloads needed by a later session, `tapps_memory(action="save", key=..., value=...)` (default `project` scope is cross-session) and `action="get"` to retrieve.

## 5-Stage Pipeline (optional)

When following a full workflow:

1. **Discover** - `tapps_session_start()`; optionally `tapps_memory(action="search")` for context
2. **Research** - `tapps_lookup_docs()`
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
