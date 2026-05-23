#!/bin/bash
# .ralph/hooks/protect-ralph-files.sh
# PreToolUse hook for Edit/Write. Blocks edits to .ralph/ except fix_plan.md,
# and blocks edits to the Claude Code control plane under .claude/.
# Exit 0 = allow, Exit 2 = block.

set -euo pipefail

# Resolve the project's .ralph/ to an absolute prefix. TAP-2344 (AgentForge
# 2026-05-22 F3): the previous unanchored `*/.ralph/*` glob blocked the
# global `~/.ralph/` install too, which forced agents to bypass the hook
# whenever they needed to hotfix the global library. Match against the
# project prefix only; anything outside the project (e.g. `~/.ralph/`) is
# allowed to fall through.
_proj_dir="${CLAUDE_PROJECT_DIR:-$PWD}"
RALPH_DIR="$_proj_dir/.ralph"
[[ -d "$RALPH_DIR" ]] || exit 0

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')

# Normalize path (remove leading ./ if present)
FILE_PATH="${FILE_PATH#./}"

# Returns 0 if FILE_PATH points inside the project's .ralph/ directory.
# Accepts both absolute paths anchored at $RALPH_DIR and relative-shape
# paths the agent commonly emits (`.ralph/foo`).
_is_project_ralph() {
  local p="$1"
  case "$p" in
    "$RALPH_DIR"|"$RALPH_DIR"/*) return 0 ;;
    .ralph|.ralph/*) return 0 ;;
  esac
  return 1
}

if _is_project_ralph "$FILE_PATH"; then
  # Allow fix_plan.md edits (Ralph checks off tasks) and status.json updates
  # (the hooks write this).
  case "$FILE_PATH" in
    "$RALPH_DIR"/fix_plan.md|.ralph/fix_plan.md) exit 0 ;;
    "$RALPH_DIR"/status.json|.ralph/status.json) exit 0 ;;
  esac
  echo "BLOCKED: Cannot modify Ralph infrastructure file: $FILE_PATH" >&2
  echo "Only .ralph/fix_plan.md checkboxes may be updated by the agent." >&2
  exit 2
fi

# Block .ralphrc modifications. Two prior bugs fixed here:
#   1. The pattern `*".ralphrc"*` was substring-match, so it also matched
#      adjacent paths like `notmy.ralphrc.bak` or `vendor/foo.ralphrc-old`.
#      Anchor to a path boundary (`*/.ralphrc` or bare `.ralphrc`).
#   2. The `[[ -f "$FILE_PATH" ]]` guard let the Write tool *create* a new
#      `.ralphrc` (file did not yet exist → guard false → allow). The agent
#      could thus introduce a `.ralphrc` overriding model/auto-update/skill
#      settings even though existing `.ralphrc` edits were blocked.
# TAP-2344: anchor to the project root so a sibling project's .ralphrc
# isn't accidentally caught when the agent is editing across repos.
#
# .ralphrc.local is the operator-only override surface (gitignored, sourced
# by ralph_loop.sh after .ralphrc). It exists precisely so direct-to-main
# repos can persist RALPH_ALLOW_PUSH_MAIN=1 without the agent being able to
# self-unlock the R0 push-to-main block in validate-command.sh — so it must
# be blocked here too. Same anchoring rule: project-local only, never a
# sibling repo's file.
if [[ "$FILE_PATH" == "$_proj_dir/.ralphrc" ]]       || [[ "$FILE_PATH" == .ralphrc ]] || \
   [[ "$FILE_PATH" == "$_proj_dir/.ralphrc.local" ]] || [[ "$FILE_PATH" == .ralphrc.local ]]; then
  echo "BLOCKED: Cannot modify Ralph configuration: $FILE_PATH" >&2
  exit 2
fi

# Block the Claude Code control plane (TAP-623): settings, agents, hooks, commands.
# These files define Ralph's own guardrails; under bypassPermissions a single
# misread fix_plan.md line could otherwise disable every hook permanently.
if [[ "$FILE_PATH" == */.claude/settings*.json ]] || [[ "$FILE_PATH" == .claude/settings*.json ]] || \
   [[ "$FILE_PATH" == */.claude/agents/* ]]       || [[ "$FILE_PATH" == .claude/agents/* ]]       || \
   [[ "$FILE_PATH" == */.claude/hooks/* ]]        || [[ "$FILE_PATH" == .claude/hooks/* ]]        || \
   [[ "$FILE_PATH" == */.claude/commands/* ]]     || [[ "$FILE_PATH" == .claude/commands/* ]]; then
  echo "BLOCKED: Cannot modify Claude Code agent/hook config: $FILE_PATH" >&2
  exit 2
fi

exit 0
