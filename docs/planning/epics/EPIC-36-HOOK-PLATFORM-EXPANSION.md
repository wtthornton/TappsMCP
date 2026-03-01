# Epic 36: Hook & Platform Generation Expansion

**Status:** Proposed
**Priority:** P1 — High (expands hook coverage from 7 to 10 events, adds prompt-type hooks, engagement-level blocking)
**Estimated LOE:** ~2-2.5 weeks (1 developer)
**Dependencies:** Epic 33 (Platform Artifact Correctness), Epic 8 (Pipeline Orchestration), Epic 18 (LLM Engagement Level)
**Blocks:** None

---

## Goal

Expand TappsMCP's generated hook coverage from 6 event types / 7 config entries (SessionStart with 2 matchers: startup|resume + compact, PostToolUse, Stop, TaskCompleted, PreCompact, SubagentStart) to 9 event types by adding SubagentStop, SessionEnd, and PostToolUseFailure hooks. Introduce `type: "prompt"` hooks that use Haiku for judgment-based quality decisions. Add engagement-level-aware blocking behavior where `high` engagement generates exit-code-2 hooks that enforce quality gates, while `medium` and `low` remain advisory.

This epic is informed by AI OS Recommendation 1 (prompt-based guardrail hooks) and Recommendation 4 (expanded hook coverage from 3 to 8 events), adapted to TappsMCP's quality enforcement use case. TappsMCP already exceeds AI OS's hook coverage (7 vs 3), but the 2026 platform offers 17 events and 4 hook types — this epic captures the highest-value remaining gaps.

## Motivation

**Current gaps:**
1. When a subagent finishes editing files, no hook advises on quality validation (`SubagentStop` gap — note: this event is advisory only, does not support blocking)
2. When a session ends, there is no final quality summary or memory capture (`SessionEnd` gap — advisory only)
3. When a TappsMCP MCP tool fails, the failure is silent — no logging or retry guidance (`PostToolUseFailure` gap — advisory only)
4. All hooks use `type: "command"` (shell scripts). The `type: "prompt"` hook type uses Haiku for ~$0.001/evaluation, enabling intelligent quality judgment without external tools
5. At `engagement_level: high`, hooks on blockable events (Stop, TaskCompleted) should enforce (exit 2 = block), not just advise (exit 0)

## 2026 Best Practices Applied (verified against Claude Code docs 2026-02-28)

- **4 hook types** — 2026 Claude Code supports `command`, `http`, `prompt`, and `agent` hooks. TappsMCP currently generates only `command`. This epic adds `prompt` type for intelligent quality judgment.
- **Prompt hooks** — Send tool input to Haiku for single-turn yes/no evaluation. Cost: ~$0.001/call. The 2026 docs confirm: `type: "prompt"`, `prompt: "..."`.
- **17 hook events** — SubagentStop, SessionEnd, and PostToolUseFailure are all documented events. Source: [code.claude.com/docs/en/hooks.md](https://code.claude.com/docs/en/hooks.md)
- **Exit code 2 blocking** — Supported on: PreToolUse, UserPromptSubmit, PermissionRequest, SessionStart, SubagentStart, PreCompact, Stop, TaskCompleted, ConfigChange. **NOT supported on: SubagentStop, SessionEnd, PostToolUseFailure** — these are advisory-only (exit 0).
- **Engagement levels** — TappsMCP's engagement level system (Epic 18) should control hook enforcement severity, not just tool description text.

## Acceptance Criteria

- [ ] SubagentStop hook: advises on Python files modified by subagent (advisory only — exit 2 not supported on this event)
- [ ] SessionEnd hook: triggers final quality summary and optional memory capture (advisory only — exit 2 not supported)
- [ ] PostToolUseFailure hook: logs TappsMCP MCP tool failures for diagnostics (advisory only — exit 2 not supported)
- [ ] Prompt-type hook: uses Haiku to evaluate whether quality checks should be run after file edits
- [ ] At `engagement_level: high`: TaskCompleted hook blocks (exit 2) if validation not run
- [ ] At `engagement_level: high`: Stop hook blocks on first invocation if no quality tools called
- [ ] At `engagement_level: medium`: all hooks advisory (exit 0) — current behavior preserved
- [ ] At `engagement_level: low`: minimal hooks generated (session start + compact only)
- [ ] Marker-file mechanism for tracking whether validation was run in current session
- [ ] All hook scripts tested; engagement-level variants tested
- [ ] `tapps_init` and `tapps_upgrade` generate the correct hook set for each engagement level

---

## Stories

### 36.1 — SubagentStop Quality Hook

**Points:** 3

Generate a SubagentStop hook that checks whether the subagent modified Python files and reminds about quality validation.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_hook_templates.py` (modify)
- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_generators.py` (modify)

**Tasks:**
- Create `tapps-subagent-stop.sh` hook script template:
  - Reads stdin JSON (SubagentStop event data includes subagent info)
  - Checks if the subagent made file changes (inspect worktree or diff)
  - If Python files were modified, prints reminder to stderr:
    "Subagent modified Python files. Run tapps_quick_check or tapps_validate_changed before accepting changes."
  - **IMPORTANT: SubagentStop does NOT support exit code 2 blocking** (verified 2026-02-28). All engagement levels exit 0 (advisory only).
  - At `engagement_level: high` and `medium`: generate hook with detailed reminder
  - At `engagement_level: low`: not generated
- Add to settings.json hook config:
  ```json
  {
    "hooks": {
      "SubagentStop": [
        {
          "type": "command",
          "command": ".claude/hooks/tapps-subagent-stop.sh"
        }
      ]
    }
  }
  ```
- Write ~4 tests: hook content correctness, engagement-level variants, settings.json integration

**Definition of Done:** SubagentStop hook advises on subagent file changes. Advisory at all levels (no blocking support).

---

### 36.2 — SessionEnd Summary Hook

**Points:** 3

Generate a SessionEnd hook that creates a quality summary and optionally saves it to memory.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_hook_templates.py` (modify)
- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_generators.py` (modify)

**Tasks:**
- Create `tapps-session-end.sh` hook script template:
  - Reads stdin JSON (SessionEnd event data)
  - Checks for a validation marker file (`.tapps-mcp/.last-validation-timestamp`)
  - If validation was run this session: prints summary "Session quality validated."
  - If validation was NOT run: prints warning "Session ended without running quality validation."
  - Non-blocking (SessionEnd does not support exit 2)
  - Optional: if `memory_capture` is enabled, call `tapps_memory save` with session summary
- Add to settings.json hook config
- Write ~4 tests: hook content, marker file check, memory capture conditional

**Definition of Done:** SessionEnd hook generates quality summary. Detects whether validation was run. Non-blocking.

---

### 36.3 — PostToolUseFailure Diagnostics Hook

**Points:** 2

Generate a PostToolUseFailure hook that logs TappsMCP MCP tool failures for debugging connectivity and configuration issues.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_hook_templates.py` (modify)
- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_generators.py` (modify)

**Tasks:**
- Create `tapps-tool-failure.sh` hook script template:
  - Reads stdin JSON (includes `tool_name`, `tool_input`, `error`)
  - Filters to only TappsMCP tools (match `mcp__tapps-mcp__*` in tool_name)
  - Logs failure details to stderr: "TappsMCP tool {name} failed: {error}. Check MCP server connectivity."
  - Non-blocking (PostToolUseFailure does not support exit 2)
  - At `engagement_level: low`: not generated (reduce noise)
- Add matcher regex: `"mcp__tapps-mcp__.*"` to scope hook to TappsMCP tools only
- Add to settings.json hook config
- Write ~3 tests: hook content, tool name filtering, engagement-level conditional

**Definition of Done:** PostToolUseFailure hook logs TappsMCP tool failures. Filtered to TappsMCP tools only. Non-blocking.

---

### 36.4 — Prompt-Type Quality Hook

**Points:** 5

Generate an optional `type: "prompt"` hook that uses Haiku to intelligently determine whether quality checks should be run after file edits.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_hook_templates.py` (modify)
- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_generators.py` (modify)
- `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py` (modify)

**Tasks:**
- Create a prompt-type hook configuration (not a shell script — prompt hooks are JSON config):
  ```json
  {
    "hooks": {
      "PostToolUse": [
        {
          "matcher": "Edit|Write",
          "type": "prompt",
          "prompt": "A file was just modified. Based on this tool output: $ARGUMENTS\n\nWas a Python file (.py) changed in a way that could affect code quality? If Python code was added, modified, or deleted, answer 'yes'. If only comments, whitespace, or non-Python files were changed, answer 'no'.",
          "model": "haiku",
          "timeout": 15
        }
      ]
    }
  }
  ```
- When the prompt hook answers "yes", it triggers a reminder to Claude to run `tapps_quick_check`
- When it answers "no", the hook passes silently
- Make prompt hooks opt-in via `prompt_hooks: true` parameter in `tapps_init`:
  - Default: `false` (prompt hooks cost ~$0.001/call and require API access)
  - When enabled, replaces the command-type `tapps-post-edit.sh` hook with the prompt-type version
- Document the cost implications in generated AGENTS.md: "Prompt hooks use Haiku (~$0.001/evaluation) for intelligent quality judgment."
- Generate alongside (not instead of) the command-type fallback — users can choose which to enable
- Write ~5 tests: prompt hook JSON structure, init parameter, replacement logic, cost documentation

**Definition of Done:** Prompt-type hook available as opt-in. Uses Haiku for intelligent file change detection. Falls back to command-type when disabled.

---

### 36.5 — Engagement-Level Blocking Hooks

**Points:** 5

At `engagement_level: high`, generate blocking (exit 2) variants of TaskCompleted and Stop hooks that enforce quality gate completion.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_hook_templates.py` (modify)
- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_generators.py` (modify)

**Tasks:**
- Implement a marker-file mechanism for tracking quality validation:
  - When `tapps_validate_changed` runs successfully, it creates/updates `.tapps-mcp/.validation-marker` with timestamp
  - Hooks check this marker to determine if validation was run in the current session
  - Marker is cleared at session start (by SessionStart hook)
- At `engagement_level: high`, generate blocking `tapps-task-completed.sh`:
  - Check for `.tapps-mcp/.validation-marker`
  - If missing or stale (> 1 hour old): exit 2 with message "BLOCKED: tapps_validate_changed has not been run. Run it before completing this task."
  - If present and recent: exit 0
- At `engagement_level: high`, generate blocking `tapps-stop.sh`:
  - On first Stop invocation (check `stop_hook_active`):
    - If no quality tools were called (no marker file): exit 2 with "BLOCKED: No quality validation was run this session. Run tapps_validate_changed before ending."
    - If quality tools were called: exit 0
  - On subsequent Stop invocations (stop_hook_active=True): exit 0 (prevent infinite loop)
- At `engagement_level: medium`: keep current advisory (exit 0) behavior
- At `engagement_level: low`: generate minimal hooks (session start + compact only, no stop/task hooks)
- Create engagement-level hook templates as separate dicts:
  - `CLAUDE_HOOK_SCRIPTS_HIGH`, `CLAUDE_HOOK_SCRIPTS_MEDIUM`, `CLAUDE_HOOK_SCRIPTS_LOW`
  - Or use a parameterized template function that takes engagement level
- Update `tapps_validate_changed` tool handler to create the validation marker file after successful runs
- Update `tapps_session_start` to clear the marker file (new session = fresh validation state)
- Write ~10 tests:
  - High engagement: TaskCompleted blocks without marker
  - High engagement: TaskCompleted passes with marker
  - High engagement: Stop blocks without quality tools
  - High engagement: Stop passes with marker
  - Medium engagement: all hooks exit 0
  - Low engagement: minimal hook set generated
  - Marker file creation by validate_changed
  - Marker file cleared by session_start
  - Stale marker detection (> 1 hour)
  - Stop hook infinite loop prevention

**Definition of Done:** High engagement generates blocking hooks. Marker file tracks validation state. Medium/low preserve current behavior.

---

### 36.6 — Engagement-Level Hook Set Selection

**Points:** 2

Wire engagement-level hook selection into `tapps_init` and `tapps_upgrade` so the correct hook set is generated for each level.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py` (modify)
- `packages/tapps-mcp/src/tapps_mcp/pipeline/upgrade.py` (modify)
- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_generators.py` (modify)

**Tasks:**
- Modify `generate_claude_hooks()` to accept `engagement_level` parameter:
  - `high`: Generate all hooks (10 events) with blocking behavior
  - `medium`: Generate standard hooks (7 events, current set + SubagentStop) with advisory behavior
  - `low`: Generate minimal hooks (SessionStart + SessionStart:compact only)
- Update `tapps_init` to pass `engagement_level` to hook generation
- Update `tapps_upgrade` to regenerate hooks at the project's configured engagement level
- Ensure `tapps_upgrade --dry-run` reports which hooks would change
- Write ~5 tests: hook count per engagement level, init passes level correctly, upgrade regenerates

**Definition of Done:** Hook generation is engagement-level-aware. Init and upgrade generate the correct set. Tests verify.

---

## Performance Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| Command hook execution | < 200ms | Shell script + Python JSON parsing |
| Prompt hook evaluation | < 3s | Haiku API call (network-dependent) |
| Marker file check | < 1ms | File stat() |
| Hook generation (all events) | < 100ms | Template formatting |

## File Layout

New hook scripts added to `CLAUDE_HOOK_SCRIPTS` dict in `platform_hook_templates.py`:
```
tapps-subagent-stop.sh     # SubagentStop quality validation
tapps-session-end.sh       # SessionEnd quality summary
tapps-tool-failure.sh      # PostToolUseFailure diagnostics
```

Prompt hook configuration added to settings.json generation (no script file — inline JSON).

Engagement-level variants either as separate template dicts or parameterized function.

## Key Dependencies

- Epic 33 (Platform Artifact Correctness — corrected settings.json generation)
- Epic 8 (Pipeline Orchestration — `tapps_init` and `tapps_upgrade` infrastructure)
- Epic 18 (LLM Engagement Level — engagement level config and template system)

## Key Design Decisions

1. **Prompt hooks are opt-in** — They cost ~$0.001/call and require API access (Haiku). Not all users want or can afford this. Default is command-type hooks.
2. **Blocking only at high engagement** — Blocking hooks (exit 2) are powerful but disruptive. Only `high` engagement should enforce. `medium` advises. `low` is minimal.
3. **Marker-file approach** — Simple, filesystem-based mechanism to track whether validation was run. No database or IPC needed. Cleared at session start for clean state.
4. **1-hour marker staleness** — A marker older than 1 hour likely reflects a previous work session, not the current one. Requiring fresh validation prevents stale approvals.
5. **PostToolUseFailure filtered to TappsMCP** — Only log failures from `mcp__tapps-mcp__*` tools, not every tool failure. Reduces noise.
6. **Three new events are all non-blocking** — The 2026 docs confirm SubagentStop, SessionEnd, and PostToolUseFailure do NOT support exit 2. They can only log/advise, not block operations. Only blockable events (Stop, TaskCompleted, etc.) can enforce at high engagement.
