# Claude Code Hooks — Complete Reference

**Source:** Deep research conducted 2026-02-21
**Version:** Claude Code v2.1.49+ (February 2026)

## Overview

Claude Code supports **17 hook events** as of February 2026. Hooks are defined in
`.claude/settings.json` (project or user level) and fire at specific points in the
session lifecycle.

## Configuration Location

| Location | Scope | Shareable |
|----------|-------|-----------|
| `~/.claude/settings.json` | All projects | No (local) |
| `.claude/settings.json` | Single project | Yes (commit to repo) |
| `.claude/settings.local.json` | Single project | No (gitignored) |
| Managed policy settings | Organization-wide | Yes (admin) |
| Plugin `hooks/hooks.json` | When plugin enabled | Yes (bundled) |
| Subagent YAML frontmatter | While component active | Yes (in file) |

**Schema:** `https://json.schemastore.org/claude-code-settings.json`

## All 17 Hook Events

### Session Lifecycle

#### SessionStart
- **Fires:** New session, resume, `/clear`, or after compaction
- **Matchers:** `startup`, `resume`, `clear`, `compact`
- **Stdin:** common fields + `source`, `model`, `agent_type`
- **Exit 0:** stdout added to Claude's context (exception to normal rule)
- **Exit 2:** Shows stderr to user only (cannot block)
- **Special:** Can set env vars via `$CLAUDE_ENV_FILE`
- **TappsMCP use:** Auto-inject context on startup, re-inject after compaction

#### SessionEnd
- **Fires:** Session terminates
- **Matchers:** `clear`, `logout`, `prompt_input_exit`, `bypass_permissions_disabled`, `other`
- **Stdin:** common fields + `reason`
- **Exit 2:** Cannot block termination
- **TappsMCP use:** Final metrics/cleanup

#### Setup
- **Fires:** Only via `claude --init`, `--init-only`, or `--maintenance`
- **Matchers:** `init`, `maintenance`
- **Stdin:** common fields + `trigger`
- **Exit 0:** stdout shown to user
- **Exit 2:** Non-blocking
- **Added:** v2.1.10+ (January 2026)
- **TappsMCP use:** Bootstrap TappsMCP during `claude --init` team onboarding

### User Input

#### UserPromptSubmit
- **Fires:** When user submits prompt, before Claude processes it
- **Matchers:** None (fires on every prompt)
- **Stdin:** common fields + `prompt`
- **Exit 0:** stdout added to Claude's context
- **Exit 2:** **BLOCKS the prompt** and erases it from context
- **Decision:** `decision: "block"` with `reason`, `additionalContext`
- **TappsMCP use:** Inject current quality status with every prompt

### Tool Execution

#### PreToolUse
- **Fires:** After Claude creates tool params, before execution
- **Matchers:** Tool name — `Bash`, `Edit`, `Write`, `Read`, `Glob`, `Grep`, `Task`, `WebFetch`, `WebSearch`, `NotebookEdit`, and MCP tools (`mcp__<server>__<tool>`)
- **Stdin:** common fields + `tool_name`, `tool_input`, `tool_use_id`
- **Exit 0:** Proceed (optionally with JSON decision)
- **Exit 2:** **BLOCKS the tool call**
- **Decision (hookSpecificOutput):**
  - `permissionDecision`: `"allow"` | `"deny"` | `"ask"`
  - `permissionDecisionReason`: string
  - `updatedInput`: modifies tool input before execution
  - `additionalContext`: injected into Claude's context
- **TappsMCP use:** Log MCP calls, inject default params, enforce session-start-first

#### PermissionRequest
- **Fires:** When permission dialog about to show
- **Matchers:** Tool name (same as PreToolUse)
- **Stdin:** common fields + `tool_name`, `tool_input`, `permission_suggestions`
- **Exit 2:** Denies the permission
- **Decision (hookSpecificOutput):**
  - `behavior`: `"allow"` | `"deny"`
  - `updatedInput`: modify tool input (allow only)
  - `updatedPermissions`: apply "always allow" rules (allow only)
  - `message`: tell Claude why denied (deny only)
- **TappsMCP use:** Auto-allow all TappsMCP tools programmatically

#### PostToolUse
- **Fires:** After tool completes successfully
- **Matchers:** Tool name (same as PreToolUse)
- **Stdin:** common fields + `tool_name`, `tool_input`, `tool_response`, `tool_use_id`
- **Exit 2:** Shows stderr to Claude (cannot block — tool already ran)
- **Decision:** `decision: "block"` + `reason`, `additionalContext`, `updatedMCPToolOutput` (MCP only)
- **TappsMCP use:** Auto-trigger quality check after Edit/Write, post-process TappsMCP output

#### PostToolUseFailure
- **Fires:** After tool call fails
- **Matchers:** Tool name
- **Stdin:** common fields + `tool_name`, `tool_input`, `tool_use_id`, `error`, `is_interrupt`
- **Exit 2:** Shows stderr to Claude
- **TappsMCP use:** Error recovery guidance

### Agent Completion

#### Stop
- **Fires:** When main Claude agent finishes responding
- **Matchers:** None
- **Stdin:** common fields + `stop_hook_active` (boolean), `last_assistant_message`
- **Exit 2:** **PREVENTS Claude from stopping** (continues conversation)
- **Decision:** `decision: "block"` with required `reason`
- **CRITICAL:** Check `stop_hook_active` to prevent infinite loops
- **TappsMCP use:** Force `tapps_validate_changed` before session ends

#### SubagentStart
- **Fires:** When subagent spawned via Task tool
- **Matchers:** Agent type — `Bash`, `Explore`, `Plan`, custom names
- **Stdin:** common fields + `agent_id`, `agent_type`
- **Exit 2:** Cannot block
- **Decision:** `additionalContext` (injected into subagent's context)
- **TappsMCP use:** Inject TappsMCP awareness into every subagent

#### SubagentStop
- **Fires:** When subagent finishes
- **Matchers:** Agent type
- **Stdin:** common fields + `stop_hook_active`, `agent_id`, `agent_type`, `agent_transcript_path`, `last_assistant_message`
- **Exit 2:** **Prevents subagent from stopping**
- **TappsMCP use:** Enforce quality on subagent output

### Agent Teams

#### TeammateIdle
- **Fires:** When teammate about to go idle
- **Stdin:** common fields + `teammate_name`, `team_name`
- **Exit 0:** Teammate goes idle
- **Exit 2:** **Keeps teammate working** (stderr = feedback)
- **Hook types:** `command` only
- **TappsMCP use:** Keep quality teammate active until gates pass

#### TaskCompleted
- **Fires:** When task being marked completed
- **Stdin:** common fields + `task_id`, `task_subject`, `task_description`, `teammate_name`, `team_name`
- **Exit 2:** **Prevents task from being marked complete** (stderr = feedback)
- **Hook types:** `command`, `prompt`, `agent`
- **TappsMCP use:** Verify quality gates before task completion

### Configuration & Infrastructure

#### ConfigChange
- **Fires:** When config file changes during session
- **Matchers:** `user_settings`, `project_settings`, `local_settings`, `policy_settings`, `skills`
- **Exit 2:** Blocks config change (except `policy_settings`)

#### WorktreeCreate
- **Fires:** When worktree being created
- **Output:** Hook prints absolute path to created worktree
- **Hook types:** `command` only

#### WorktreeRemove
- **Fires:** When worktree removed
- **Cannot block**
- **Hook types:** `command` only

#### PreCompact
- **Fires:** Before context compaction
- **Matchers:** `manual` (from `/compact`), `auto` (automatic)
- **Stdin:** common fields + `trigger`, `custom_instructions`
- **Exit 2:** Cannot block compaction
- **TappsMCP use:** Back up scoring context before compaction

#### Notification
- **Fires:** When Claude Code sends notification
- **Matchers:** `permission_prompt`, `idle_prompt`, `auth_success`, `elicitation_dialog`
- **Stdin:** common fields + `message`, `title`, `notification_type`
- **TappsMCP use:** Desktop alerts on quality gate failures

## Common Stdin Fields (All Events)

```json
{
  "session_id": "abc123",
  "transcript_path": "/path/to/session.jsonl",
  "cwd": "/path/to/project",
  "permission_mode": "default",
  "hook_event_name": "PreToolUse"
}
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `$CLAUDE_PROJECT_DIR` | Project root directory |
| `$CLAUDE_CODE_REMOTE` | `"true"` in remote/web environments |
| `$CLAUDE_ENV_FILE` | (SessionStart only) Write `export` statements to persist env vars |
| `$CLAUDE_PLUGIN_ROOT` | Plugin root (for plugin hooks) |

## Exit Code Reference

| Exit Code | Meaning |
|-----------|---------|
| 0 | Success — stdout parsed for JSON or shown in verbose mode |
| 2 | Blocking error — behavior varies by event (see each event above) |
| 1, 3+ | Non-blocking error — shown in verbose mode only |

## Hook Types

| Type | Speed | Capability |
|------|-------|------------|
| `command` | Fast (ms) | Shell script, receives stdin JSON |
| `prompt` | Slow (LLM call, 30s default) | LLM evaluates with `$ARGUMENTS` |
| `agent` | Slowest (multi-turn, 60s default) | Spawns subagent with tools |

## Hook Type Support Matrix

| Event | command | prompt | agent |
|-------|:-------:|:------:|:-----:|
| SessionStart | Yes | No | No |
| SessionEnd | Yes | No | No |
| Setup | Yes | No | No |
| UserPromptSubmit | Yes | Yes | Yes |
| PreToolUse | Yes | Yes | Yes |
| PermissionRequest | Yes | Yes | Yes |
| PostToolUse | Yes | Yes | Yes |
| PostToolUseFailure | Yes | Yes | Yes |
| Notification | Yes | No | No |
| SubagentStart | Yes | No | No |
| SubagentStop | Yes | Yes | Yes |
| Stop | Yes | Yes | Yes |
| TeammateIdle | Yes | No | No |
| TaskCompleted | Yes | Yes | Yes |
| ConfigChange | Yes | No | No |
| WorktreeCreate | Yes | No | No |
| WorktreeRemove | Yes | No | No |
| PreCompact | Yes | No | No |

## MCP Tool Matching

MCP tools follow the naming pattern `mcp__<server-name>__<tool-name>`.

| Pattern | Matches |
|---------|---------|
| `mcp__tapps-mcp__.*` | All TappsMCP tools |
| `^mcp__` | All MCP tools from any server |
| `mcp__tapps-mcp__tapps_score_file` | Exact match |

## Best Practices

1. **Infinite loop prevention:** Always check `stop_hook_active` in Stop/SubagentStop
2. **Performance:** Use `"async": true` for long-running tasks; set explicit `timeout`
3. **Shell profiles:** stdout must be clean JSON — no shell profile noise
4. **Case sensitivity:** Matchers are case-sensitive (`Bash` not `bash`)
5. **Hook snapshot:** Hooks captured at session startup; mid-session edits need `/hooks` review
6. **Async hooks cannot block:** `decision` fields have no effect in async hooks
