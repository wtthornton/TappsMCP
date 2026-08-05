# TAPPS Quality Pipeline - MANDATORY

This project uses the TAPPS MCP server for automated code quality enforcement.
Every tool response includes `next_steps` - follow them.

## CRITICAL: Tool Call Obligations

These are BLOCKING REQUIREMENTS, not suggestions. Skipping any step risks shipping broken, insecure, or hallucinated code.

### Session Start (REQUIRED)

You MUST call `tapps_session_start()` as the FIRST action in every session.
This discovers server capabilities and detects the project's tech stack.
Skipping this means all subsequent tools lack project context.

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

For multi-file changes: You MUST call `tapps_validate_changed()` to batch-validate all changed files.
The quality gate MUST pass. Work is NOT done until the gate passes or the user explicitly accepts the risk.
You MUST call `tapps_checklist(task_type)` as the FINAL step to verify no required tools were skipped.
NEVER declare work complete without running the checklist. The `tapps_checklist` response carries an inline `usage_gaps` payload (same data as the standalone `tapps_usage` tool) — read it before declaring done. The Stop hook (`tapps-stop.sh`) also writes to `.tapps-mcp/.completion-gate-violations.jsonl` in warn mode when code edits ship without validation; no block, but the telemetry feeds `tapps_usage`.

### Domain Decisions (REQUIRED)

You MUST call `tapps_lookup_docs(library, topic)` when you need domain-specific guidance
(security patterns, testing strategy, API design, database best practices, etc.).
Use the returned documentation to inform your decisions.

### Refactoring or Deleting Files (REQUIRED)

For **module/file** blast radius: `tapps_impact_analysis(file_path)` (import graph).
For **function/method** refactors: `tapps_call_graph(symbol, query=callers|callees|chain|all)` or
`tapps_impact_analysis` with `symbol` and `granularity="symbol"|"both"` (Epic 114 / ADR-0017).
For **git-changed** batches: `tapps_diff_impact`; `tapps_validate_changed(include_impact=true)` adds `affected_tests`.
Skipping this risks breaking downstream dependents and missing test coverage.

### Infrastructure Config Changes (REQUIRED)

You MUST call `tapps_validate_config(file_path)` when changing Dockerfile, docker-compose, or infra config.
This validates against security and operational best practices.

## 5-Stage Pipeline

Execute these stages IN ORDER for every code task:

1. **Discover** - `tapps_session_start()`, then `uv run tapps-mcp memory search --query "..."` to recall project context
2. **Research** - `tapps_lookup_docs()` for libraries and domain decisions
3. **Develop** - `tapps_score_file(file_path, quick=True)` during edit-lint-fix loops
4. **Validate** - `tapps_quick_check()` per file OR `tapps_validate_changed()` for batch
5. **Verify** - `tapps_checklist(task_type)`, then `uv run tapps-mcp memory save --key ... --tier ... --value "..."` to persist learnings

## Consequences of Skipping

Critical gaps: skipping `session_start` removes project context; skipping `lookup_docs` causes hallucinated APIs; skipping validation ships bugs; skipping `checklist` loses verification. No workarounds—tools are mandatory.

## Response Guidance

Every tool response includes `next_steps` — follow them. Record progress in `docs/TAPPS_HANDOFF.md`.
For high-traffic tools, `next_steps` are templated with the active `file_path` — paste verbatim.

> **Skill deprecations (v3.12.0):** `tapps-score`, `tapps-gate`, `tapps-validate` are deprecated. Prefer direct MCP tool calls or `/tapps-finish-task`.

## CI Integration

Run `tapps-mcp validate-changed --preset staging` with `TAPPS_MCP_PROJECT_ROOT=/workspace` in CI environments.
