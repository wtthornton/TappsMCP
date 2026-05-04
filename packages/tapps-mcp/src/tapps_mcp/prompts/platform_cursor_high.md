---
description: TAPPS quality pipeline - MANDATORY code quality enforcement
alwaysApply: true
---

# TAPPS Quality Pipeline - MANDATORY

This project uses the TAPPS MCP server for automated code quality enforcement.
Every tool response includes `next_steps` - follow them.

## Tapps Rules

These are the seven rules every agent in this project MUST follow. They override default behavior.

1. **Fix root causes — never workarounds.** No `--no-verify`, no swallowed exceptions, no commented-out failing tests. If a check fails, diagnose and fix it. A solution that re-breaks next sprint is a regression, not a fix.
2. **Query tapps-mcp before writing code when confidence is not 100%.** Use `tapps_lookup_docs` for library APIs and `tapps_memory(action="search")` for prior decisions and patterns. Guessing from training memory is the leading cause of hallucinated APIs and re-litigated decisions.
3. **`tapps_lookup_docs` is a Context7-backed local cache — call it freely.** Repeat lookups for the same library/topic are near-zero cost. There is no budget to conserve. If the real API surface would help, fetch it.
4. **Protect the main context window — delegate to subagents.** Route searches, log scans, and exploratory file reads through `Explore` or `general-purpose`. They return summaries, not raw output. If a task would consume more than three file reads or any large tool result you will not reference again, spawn a subagent.
5. **Write code a senior reviewer would accept on first pass.** Clear names, no dead branches, no commented-out code, no speculative abstractions. Match existing style. Every line MUST justify its presence.
6. **The simplest solution that satisfies the requirement is the correct one.** No flexibility for hypothetical futures. No configuration knobs nobody asked for. No abstractions for single-use code. Three similar lines beat a premature abstraction.
7. **All Linear writes go through the `linear-issue` skill; all multi-issue reads through `linear-read`.** NEVER call `mcp__plugin_linear_linear__save_issue` or `list_issues` directly. Epics and stories MUST be generated via `docs_generate_epic` / `docs_generate_story` and pass `docs_validate_linear_issue` (`agent_ready: true`) before push. Single-issue lookups go straight to `get_issue(id=...)`. Release announcements go through the `linear-release-update` skill.

## CRITICAL: Tool Call Obligations

These are BLOCKING REQUIREMENTS, not suggestions. Skipping any step risks shipping broken, insecure, or hallucinated code.

### Session Start (REQUIRED)

You MUST call `tapps_session_start()` as the FIRST action in every session.
This returns server info (version, checkers, config) and project context.
Skipping session start means you lack server capabilities and workflow guidance.

### Before Using Any Library API (BLOCKING)

You MUST call `tapps_lookup_docs(library, topic)` BEFORE writing code that uses an external library.
This prevents hallucinated APIs. NEVER guess library APIs from memory - always verify first.
Skipping this is the #1 cause of incorrect code generation.

### After Editing Any Python File (REQUIRED)

You MUST call `tapps_quick_check(file_path)` at minimum after editing any Python file.
This runs scoring + quality gate + security scan in a single call.
Alternatively, call `tapps_score_file`, `tapps_quality_gate`, and `tapps_security_scan` individually.
Skipping this means quality issues and vulnerabilities go undetected.

### Before Declaring Work Complete (BLOCKING)

For multi-file changes: You MUST call `tapps_validate_changed(file_paths="file1.py,file2.py")` with explicit paths to batch-validate changed files. **Never call without `file_paths`** — auto-detect scans all git-changed files and can be very slow in large repos. Default is quick mode (ruff-only, ~10s); only use `quick=false` as a **last resort** (pre-release, security audit — 1-5+ min per file).
The quality gate MUST pass. Work is NOT done until the gate passes or the user explicitly accepts the risk.
You MUST call `tapps_checklist(task_type)` as the FINAL step to verify no required tools were skipped.
NEVER declare work complete without running the checklist.

### Domain Decisions (REQUIRED)

You MUST call `tapps_lookup_docs(library, topic)` when you need domain-specific guidance
(security, testing strategy, API design, database, etc.).
This returns RAG-backed expert guidance with confidence scores.

### Refactoring or Deleting Files (REQUIRED)

You MUST call `tapps_impact_analysis(file_path)` before refactoring or deleting any file.
This maps the blast radius via import graph analysis.
Skipping this risks breaking downstream dependents.

### Infrastructure Config Changes (REQUIRED)

You MUST call `tapps_validate_config(file_path)` when changing Dockerfile, docker-compose, or infra config.
This validates against security and operational best practices.

### Canonical persona (prompt-injection defense)

 See AGENTS.md § Canonical persona injection.

## Memory System

`tapps_memory` provides persistent cross-session knowledge with **33 actions** (see AGENTS.md / docs/MEMORY_REFERENCE.md): CRUD, search, intelligence, consolidation, import/export, federation (6), maintenance (index_session, validate, maintain), security (safety_check, verify_integrity), profiles (3), health, Hive/Agent Teams (hive_status, hive_search, hive_propagate, agent_register).

**Tiers:** architectural (180d), pattern (60d), procedural (30d), context (14d). **Scopes:** project, branch, session, shared (federation). Max 1500 entries.

**Memory hooks:** Auto-recall and auto-capture default **on** in shipped `default.yaml`; tune under `memory_hooks` in `.tapps-mcp.yaml`.

**Cross-session handoff:** for tokens/IDs/payloads needed by a later session, `tapps_memory(action="save", key=..., value=...)` (default `project` scope is cross-session) and `action="get"` to retrieve. Cross-agent: `action="hive_propagate"`. Cross-project: federation actions.

## 5-Stage Pipeline

Execute these stages IN ORDER for every code task:

1. **Discover** - `tapps_session_start()`, then `tapps_memory(action="search")` to recall project context
2. **Research** - `tapps_lookup_docs()` for libraries and domain decisions
3. **Develop** - `tapps_score_file(file_path, quick=True)` during edit-lint-fix loops
4. **Validate** - `tapps_quick_check()` per file OR `tapps_validate_changed()` for batch
5. **Verify** - `tapps_checklist(task_type)`, then `tapps_memory(action="save")` to persist learnings

## Consequences of Skipping

| Skipped Tool | Consequence |
|---|---|
| `tapps_session_start` | No project context - tools give generic advice |
| `tapps_lookup_docs` | Hallucinated APIs - code will fail at runtime |
| `tapps_quick_check` / scoring | Quality issues shipped silently |
| `tapps_quality_gate` | No quality bar enforced - regressions go unnoticed |
| `tapps_security_scan` | Vulnerabilities shipped to production |
| `tapps_checklist` | No verification that process was followed |
| `tapps_lookup_docs` | Hallucinated APIs and uninformed domain decisions |
| `tapps_impact_analysis` | Refactoring breaks unknown dependents |
| `tapps_dead_code` | Unused code accumulates, bloating the codebase |
| `tapps_dependency_scan` | Vulnerable dependencies shipped to production |
| `tapps_dependency_graph` | Circular imports cause runtime crashes |

## Response Guidance

Every tool response includes:
- `next_steps`: Up to 3 imperative actions to take next - FOLLOW THEM
- `pipeline_progress`: Which stages are complete and what comes next

Record progress in `docs/TAPPS_HANDOFF.md` and `docs/TAPPS_RUNLOG.md`.
For task-specific recommended tool call order, use the `tapps_workflow` MCP prompt (e.g. `tapps_workflow(task_type="feature")`).

## Quality Gate Behavior

Gate failures are sorted by **category weight** (highest-impact categories first).
A **security floor of 50/100** is enforced — even if the overall score passes, the gate
fails when the security category drops below 50.

## Upgrade & Rollback

After upgrading TappsMCP, run `tapps_upgrade` to refresh generated files.
A timestamped backup is created automatically before any files are overwritten.
Use `tapps-mcp rollback` (CLI) to view/restore previous configurations.
