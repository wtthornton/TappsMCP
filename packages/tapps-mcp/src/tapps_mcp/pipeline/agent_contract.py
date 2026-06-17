"""Shared agent-hint strings — single source for hooks, skills, rules, and usage gaps.

ADR-0021 / agent-contract audit: every surface that nudges agents about lookup,
validation, or finish-task should import from here so hints do not contradict.
See ADR-0022 for lookup timing and validation semantics.
"""

from __future__ import annotations

# Post-edit (Claude PostToolUse + Cursor afterFileEdit)
POST_EDIT_QUICK_CHECK_MSG = (
    "Edited: {file} — run tapps_quick_check after this edit."
)
POST_EDIT_IMPORT_LOOKUP_MSG = (
    "Imports detected ({libs}) — call tapps_lookup_docs(library=..., topic=...) "
    "before using those APIs in this session."
)
# Bash hook templates use $LIBS / $FILE instead of Python format fields.
POST_EDIT_IMPORT_LOOKUP_BASH = (
    "Imports detected ($LIBS) — call tapps_lookup_docs(library=..., topic=...) "
    "before using those APIs in this session (TAP-1330)."
)
POST_EDIT_QUICK_CHECK_BASH = (
    "Edited: $FILE — run tapps_quick_check after this edit."
)

# Stop / TaskCompleted reminders (warn-only telemetry; not hard blocks unless opt-in gates)
STOP_FINISH_REMINDER = (
    "Reminder: run /tapps-finish-task (or tapps_validate_changed + tapps_checklist "
    "manually) before declaring complete."
)
STOP_GAP_FOLLOWUP_DEFAULT = "Run /tapps-finish-task before declaring done."

# SessionStart / Stop gap hints (usage.py, hooks, CLI usage-gaps-hint)
SESSION_START_CHECKLIST_GAP_HINT = (
    "Last session ended without tapps_checklist after edits — run "
    "tapps_validate_changed + tapps_checklist before declaring done."
)
CHECKLIST_SKIPPED_REC = (
    "tapps_checklist was not called this session. Invoke "
    "/tapps-finish-task or tapps_checklist(task_type=<feature|bugfix|refactor|security>) "
    "before declaring done."
)

# Lookup gap remediation (ADR-0021 telemetry vs cache — ADR-0022 timing)
LOOKUP_GAP_RETRO_NOTE = (
    "retrospective MCP lookups clear telemetry gaps; cache hits are fine"
)
LOOKUP_TIMING_RULE = (
    "Call tapps_lookup_docs before first use of each external library in a session; "
    "retrospective lookups only clear telemetry gaps (ADR-0021), not missing knowledge."
)

# SubagentStart hook (Claude) — no stale direct tapps-mcp tapps_memory routing
SUBAGENT_START_INTRO = "[TappsMCP] This project uses TappsMCP for code quality."
SUBAGENT_START_TOOLS_LINE = (
    "Tools: tapps_quick_check, tapps_score_file, tapps_validate_changed. "
    "Memory: uv run tapps-mcp memory …; tapps_memory on nlt-memory when enabled (TAP-3895)."
)

# Validation semantics (finish-task vs stop-hook vs per-file edits)
VALIDATION_QUICK_VS_BATCH = (
    "`tapps_quick_check` = per-file during edits. `tapps_validate_changed` = batch "
    "before done. Stop-hook telemetry counts either as gate activity; "
    "/tapps-finish-task requires validate_changed for the edited set."
)

# Session start memory (bridge-only default; slim tapps_memory MCP on nlt-memory — TAP-3895)
MEMORY_RECALL_SESSION_START = (
    "Brain memory is bridge-only: use `uv run tapps-mcp memory search --query \"...\"` "
    "or pinned keys in `.tapps-mcp.yaml` → `memory_hooks.auto_recall.recall_keys`. "
    "When `nlt-memory` is enabled, `tapps_memory` MCP is a slim facade on that server."
)

# Doc-lookup usage gaps (ADR-0021)
DOC_GAP_TELEMETRY_NOTE = (
    "Warm `.tapps-mcp-cache/` or CLI `tapps-mcp lookup-docs` clears SessionStart hints "
    "via `.lookup-docs-events.jsonl`; one MCP `tapps_lookup_docs` call still clears "
    "in-session CallTracker gaps (cache hit is fine)."
)

# Consumer docs — memory narrative (ADR-0022 / TAP-3895)
MEMORY_SYSTEMS_BULLET = (
    "**TappsMCP shared memory** — **`uv run tapps-mcp memory`** CLI via BrainBridge "
    "(default; do not add direct `tapps-brain` to `.mcp.json`). When **`nlt-memory`** "
    "is enabled, `tapps_memory` MCP on that server is a slim facade (TAP-3895). "
    "Architecture decisions, quality patterns, cross-agent knowledge. "
    "See [docs/MEMORY_REFERENCE.md](docs/MEMORY_REFERENCE.md) and `/tapps-memory` skill."
)
MEMORY_ACTIONS_ACCESS_NOTE = (
    "**Access:** Prefer `uv run tapps-mcp memory <subcommand>` (CLI). With `nlt-memory` "
    "enabled, `tapps_memory(action=...)` on that server exposes the same actions (TAP-3895). "
    "Not on default `nlt-build` alone (TAP-1994)."
)

# Copilot / VS Code — bounded write scope (parity with agent-scope.md / tapps-agent-scope.mdc)
COPILOT_PROJECT_SCOPE_SECTION = """\
## Project Scope (do not break out of this repo/project)

This Copilot instance was configured for THIS repo by `tapps_init` /
`tapps_upgrade`. Reading docs across projects is fine; **writing** outside
this repo or the linked tracker project is not. Specifically:

- Do not create, update, comment on, or move issues that belong to a
  different project than this repo.
- Do not modify files, branches, or pull requests in any other repository.
- Read team / project identity from `.tapps-mcp.yaml` or the current git
  remote, not from arbitrary search results.
- If a task seems to require a write outside this repo/project, ask the
  user before proceeding."""

_FINISH_TASK_DOC_GAPS_STEP3_BODY = """\
3. **Clear doc-lookup gaps.** When `usage_gaps.gaps` includes `library_uses_without_lookup_docs` or `libraries_without_lookup` is non-empty:
   - Call `{lookup_tool}` for **each** listed library (retrospective MCP lookups clear telemetry gaps; cache hits are fine — ADR-0021).
   - CLI `tapps-mcp lookup-docs` also records `.lookup-docs-events.jsonl` for the next session.
   - Re-run `{checklist_tool}` until `usage_gaps.gaps` is empty **and** `complete: true`.
   Prefer lookup **before first use** of each external library in future sessions."""

AGENTS_TEMPLATE_TOOL_COUNT_PLACEHOLDER = "{{TAPPS_MCP_TOOL_COUNT}}"
AGENTS_TEMPLATE_MEMORY_SYSTEMS_PLACEHOLDER = "{{MEMORY_SYSTEMS_BULLET}}"
AGENTS_TEMPLATE_MEMORY_ACCESS_PLACEHOLDER = "{{MEMORY_ACTIONS_ACCESS_NOTE}}"


def tapps_mcp_tool_count() -> int:
    """Canonical MCP tool count for AGENTS.md and docs."""
    from tapps_mcp.server import ALL_TOOL_NAMES

    return len(ALL_TOOL_NAMES)


def render_agents_template(content: str) -> str:
    """Substitute dynamic placeholders in AGENTS.md templates."""
    rendered = content.replace(
        AGENTS_TEMPLATE_TOOL_COUNT_PLACEHOLDER,
        str(tapps_mcp_tool_count()),
    )
    rendered = rendered.replace(
        AGENTS_TEMPLATE_MEMORY_SYSTEMS_PLACEHOLDER,
        MEMORY_SYSTEMS_BULLET,
    )
    return rendered.replace(
        AGENTS_TEMPLATE_MEMORY_ACCESS_PLACEHOLDER,
        MEMORY_ACTIONS_ACCESS_NOTE,
    )


def lookup_gap_recommendation(libraries: list[str], *, generic: bool) -> str:
    """One-line remediation for ``library_uses_without_lookup_docs`` gaps."""
    if libraries:
        sample = ", ".join(libraries[:8])
        suffix = (
            f' Call tapps_lookup_docs(library="{libraries[0]}", topic="<api>") '
            f"for each ({LOOKUP_GAP_RETRO_NOTE})."
        )
        return (
            f"No tapps_lookup_docs this session; edited files reference: {sample}.{suffix}"
        )
    if generic:
        return (
            "No tapps_lookup_docs calls this session despite recent edits. "
            "Call it before using any external library API "
            f"({LOOKUP_GAP_RETRO_NOTE}; CLI lookup-docs also counts — ADR-0021)."
        )
    return ""


def finish_task_doc_gaps_step(*, claude_nlt_prefix: bool) -> str:
    """Step 3 block for tapps-finish-task (Cursor vs Claude tool names)."""
    if claude_nlt_prefix:
        lookup = "mcp__nlt-build__tapps_lookup_docs"
        checklist = "mcp__nlt-build__tapps_checklist"
    else:
        lookup = "tapps_lookup_docs"
        checklist = "tapps_checklist"
    return _FINISH_TASK_DOC_GAPS_STEP3_BODY.format(
        lookup_tool=f"{lookup}(library=<name>, topic=<relevant-api>)",
        checklist_tool=checklist,
    )


def finish_task_checklist_and_doc_gaps(*, claude_nlt_prefix: bool) -> str:
    """Steps 2–3 for finish-task skills."""
    if claude_nlt_prefix:
        checklist_line = (
            "2. **Verify the checklist.** Call "
            "`mcp__nlt-build__tapps_checklist(task_type=<feature|bugfix|refactor|security|review>)`. "
            "Read the inline **`usage_gaps`** block — not only `complete` / `missing_steps`. "
            "If `complete: false`, address each entry in `missing_steps` and re-run."
        )
    else:
        checklist_line = (
            "2. **Verify the checklist.** Call "
            "`tapps_checklist(task_type=<feature|bugfix|refactor|security|review>)`. "
            "Read the inline **`usage_gaps`** block — not only `complete` / `missing_steps`. "
            "If `complete: false`, address each entry in `missing_steps` and re-run."
        )
    return f"{checklist_line}\n\n{finish_task_doc_gaps_step(claude_nlt_prefix=claude_nlt_prefix)}"


__all__ = [
    "AGENTS_TEMPLATE_TOOL_COUNT_PLACEHOLDER",
    "CHECKLIST_SKIPPED_REC",
    "COPILOT_PROJECT_SCOPE_SECTION",
    "DOC_GAP_TELEMETRY_NOTE",
    "LOOKUP_GAP_RETRO_NOTE",
    "LOOKUP_TIMING_RULE",
    "MEMORY_ACTIONS_ACCESS_NOTE",
    "MEMORY_RECALL_SESSION_START",
    "MEMORY_SYSTEMS_BULLET",
    "POST_EDIT_IMPORT_LOOKUP_BASH",
    "POST_EDIT_IMPORT_LOOKUP_MSG",
    "POST_EDIT_QUICK_CHECK_BASH",
    "POST_EDIT_QUICK_CHECK_MSG",
    "SESSION_START_CHECKLIST_GAP_HINT",
    "STOP_FINISH_REMINDER",
    "STOP_GAP_FOLLOWUP_DEFAULT",
    "SUBAGENT_START_INTRO",
    "SUBAGENT_START_TOOLS_LINE",
    "VALIDATION_QUICK_VS_BATCH",
    "finish_task_checklist_and_doc_gaps",
    "finish_task_doc_gaps_step",
    "lookup_gap_recommendation",
    "render_agents_template",
    "tapps_mcp_tool_count",
]
