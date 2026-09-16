"""Skill definition templates for Claude Code and Cursor.

Contains SKILL.md templates and the ``generate_skills`` function.
Extracted from ``platform_generators.py`` to reduce file size.

Epic 76: Claude skills use space-delimited ``allowed-tools`` per agentskills.io spec.
Cursor skills use ``mcp_tools`` (YAML list); Cursor applies tool restrictions via mcp_tools.
"""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import re
import sys
from pathlib import Path
from typing import Any

from tapps_mcp.pipeline.agent_contract import (
    FINISH_TASK_VALIDATE_CALL_GRAPH_NOTE,
    TOOL_REFERENCE_CALL_GRAPH_ROWS,
    finish_task_checklist_and_doc_gaps,
)
from tapps_mcp.pipeline.platform_skill_continuous_learning import (
    CONTINUOUS_LEARNING_COMPANION_FILES,
    CONTINUOUS_LEARNING_CURSOR_SKILL_BODY,
)
from tapps_mcp.pipeline.platform_skill_orchestration import (
    ORCHESTRATION_PROMPT_COMPANION_FILES,
    ORCHESTRATION_PROMPT_CREATE_ONLY_FILES,
    ORCHESTRATION_PROMPT_SKILL_BODY,
)
from tapps_mcp.pipeline.platform_skill_validation_contract import (
    VALIDATION_CONTRACT_COMPANION_FILES,
    VALIDATION_CONTRACT_SKILL_BODY,
)
from tapps_mcp.pipeline.platform_skill_wayfind import (
    WAYFIND_COMPANION_FILES,
    WAYFIND_SKILL_BODY,
)
from tapps_mcp.pipeline.skill_asset_policy import (
    write_companions,
)
from tapps_mcp.pipeline.skill_managed_block import (
    extract_block,
    install_or_refresh_skill,
    normalize_block_version,
    prepend_below_frontmatter,
)

# ---------------------------------------------------------------------------
# Shared session-transfer bodies (TAP-3574/3575/3581)
# ---------------------------------------------------------------------------

_HANDOFF_MARKDOWN_SHAPE = """\
```markdown
# Session handoff
**Program:** <program or campaign name>
**Updated:** <ISO-8601 UTC from date -u>
**Git:** <short-sha or omit>
**Linear P0:** <TAP-#### or none>

## Done
- ...

## Open
- ...

## Next (P0)
- ... (plain prose; put TAP-#### in **Linear P0** above)

## Blockers
- none

## Changed files
- ... (optional; top paths from git status when multi-file)

## Verify
- ...

## Success criterion
- ...

## Cumulative (loop checkpoints — required for shift boundaries)
- Sub-goal: <k> · VAL IDs: <…>
- Attempt: <a> of <cap> (cumulative across shifts)
- Budget spent: <spent>/<ceiling>
- Refuted strategies: <bullets>
- Resume line: <exact cold-start launch line from prompt>
```"""

_HANDOFF_P0_GATE = """\
**P0 gate.** Before persisting: when **Open** has real items (not `none` / `- ...` placeholders), **Next (P0)** must name one concrete next action. Set **Linear P0:** to the TAP id when known. If P0 is missing, ask the user once — do not persist an incomplete handoff."""

_HANDOFF_PRE_GATE = """\
0. **Session bootstrap (if needed).** If `tapps_session_start()` was not called this session, call it now (cached is fine) so flywheel scope and checker context are correct. Skip when already called."""

_HANDOFF_PERSIST = """\
2. **Persist (one atomic call when MCP is available).** Do **not** write the file separately before MCP — `tapps_handoff_save` writes `.tapps-mcp/session-handoff.md`, lints, mirrors to brain, and can close the session lifecycle.

   Draft the full markdown in memory using the shape above:
   - **Program:** the program or campaign this session belongs to. It is the ownership key: the guard compares it against whoever wrote the file last, and only a *different* stated program is a conflict. Leave the placeholder in and the write is reported as unknown ownership — archived, never refused, but nobody can tell your handoff from anyone else's.
   - **Updated:** run `date -u +%Y-%m-%dT%H:%M:%SZ` — never a placeholder like `T00:00:00Z`
   - **Git:** `git rev-parse --short HEAD` when inside a git repo
   - **Linear P0:** TAP-#### when known (preferred retrieval key for brain session search)
   - **Blockers:** `- none` alone when clear — put user actions under **Verify** or **Next (P0)**, not Blockers
   - **Changed files:** optional bullets from `git status --short` when the session touched many files

   | Priority | When | How |
   |----------|------|-----|
   | 1 (MCP) | `nlt-memory` available | `tapps_handoff_save(markdown=..., session_end=true)` — single call; do **not** also call `tapps_session_end` |
   | 2 (CLI atomic) | Shell auth; no MCP write | `uv run tapps-mcp handoff write --file <draft.md> [--slot <your-program>] --session-end` — `--file` is the **input** to read, `--slot` picks the **destination** |
   | 3 (manual) | Brain HTTP only | `uv run tapps-mcp memory save --key session-handoff --tier context --tags handoff,cross-session --value "$(cat .tapps-mcp/session-handoff.md)"` — full markdown body |
   | 4 (skip) | Brain offline | File-only via Bash heredoc: `mkdir -p .tapps-mcp && cat > .tapps-mcp/session-handoff.md <<'EOF'` … `EOF` |

   **Slots — when another program shares this repo.** `slot="<your-program>"` writes `.tapps-mcp/handoffs/<slot>.md` and brain key `session-handoff.<slot>` instead of the shared default, so concurrent programs stop overwriting each other. Lowercase letters, digits and dashes, at most 48 characters. Omit it and you write the shared file, which is correct for a repo running one program at a time.

   **When the response carries `conflict`.** Print it. `foreign: true` means you replaced another program's handoff — name the program from `conflict.previous` and the recovery path from `conflict.archived_to`; the right fix is almost always to re-save under your own `slot=`. `foreign: "unknown"` means nobody could tell (no **Program:** header on one side) — say so rather than reporting a clean write. Under `handoff_conflict_mode: block` the save is **refused** with `handoff_owner_conflict`: retry with `slot=`, or pass `force=true` only when you genuinely mean to take over the shared file (the incumbent is archived first either way).

   Handoff **Updated** older than 7 days: pass `allow_lint_warnings=true` on `tapps_handoff_save` if lint warns on age."""

# Always refreshed on init/upgrade even when overwrite=False (other skills preserve customizations).
SESSION_TRANSFER_SKILL_NAMES: tuple[str, ...] = (
    "tapps-handoff-session",
    "tapps-continue-session",
)

# Legacy alias — older skill bodies referenced this name in comments only.
_HANDOFF_BRAIN_MIRROR = _HANDOFF_PERSIST

_CONTINUE_LOAD_AND_CONTEXT = """\
2. **Choose the handoff, then load it.** A repo can hold several: the shared `.tapps-mcp/session-handoff.md` plus one per slot under `.tapps-mcp/handoffs/`. Enumerate before reading — `uv run tapps-mcp handoff list` prints every one, newest first, with its slot, program, **Updated** and age.
   - **A slot argument was given** (`/tapps-continue-session <slot>`) → load that one: `.tapps-mcp/handoffs/<slot>.md`. Say so if it does not exist; do not silently fall back to the shared file.
   - **Exactly one fresh handoff** → load it and continue.
   - **More than one** → **list the slots and ask which to resume — never silently pick one.** Print slot, program, **Updated** and age for each, then stop and wait. Picking for the user is how one program resumes another program's state without either noticing. Recency is not consent: the newest handoff is frequently the *other* program's.
   - Then read the chosen file — primary source.
   - Else best-effort CLI (no `tapps_memory` MCP — removed v3.12.0): `uv run tapps-mcp memory get --key session-handoff` (slotted: `--key session-handoff.<slot>`; brain offline or auth missing → skip).
   - Optional supplements (only if present): `docs/NEXT_SESSION_PROMPT.md`, `docs/TAPPS_HANDOFF.md` (**Next:** section).
   - **P0 fallback:** If **Next (P0)** is empty but **Open** has bullets, promote the first Open item as provisional P0 and flag it in the continue block.
   - **Memory context (optional):** `uv run tapps-mcp memory recall --recall-key session-handoff --query "<P0 text or Linear id>"` pins the handoff mirror then adds semantic hits (HTTP-safe). Alternative: `uv run tapps-mcp memory search --query "..."`. Skip silently when brain auth is unavailable."""

_CONTINUE_GROUND_TRUTH_GATE = """\
3. **Ground-truth gate (run before emitting anything).** The handoff is a claim about the past, not evidence. Age is the weak signal — a handoff goes wrong the moment work lands after it was written, which is usually minutes, not days. Run all three checks and carry a verdict per claim:

   - **Commit drift.** `git log -1 --format=%h`, compared against the handoff **Git:** sha. On a mismatch, name what landed: `git log --oneline <handoff-sha>..HEAD`. A different sha means the file predates real work — treat **every Open item as unverified** until re-probed. *One benign case:* when the only commit in that range is the one that committed the handoff itself, the sha is stale by construction (the file records HEAD at write time, then becomes part of the next commit) — say so and move on. Any other commit in the range is real drift.
   - **P0 status.** Re-read the **Linear P0:** id from the tracker (`get_issue`), never from the handoff text. Flag it when the issue is already **Done** or **Canceled**. Treat a Done status as a **claim in both directions**: report it, and never conclude from it alone either that the work exists or that it does not — issues get auto-closed by a commit reference with no code behind them, and finished work sits under issues nobody moved.
   - **Named PR / branch.** For every PR the handoff names, `gh pr view <N> --json state,mergedAt` before offering it as a next action. A merged PR presented as "needs review" is the most common stale-handoff failure.

   **On any mismatch, correct `.tapps-mcp/session-handoff.md` before proceeding** — rewrite the wrong lines, then continue from the corrected file. Never leave a known-wrong artifact for the next session to inherit.

   **Why this outranks age.** The 7-day age warning never fires on the failure that actually happens — a handoff wrong within the hour. It matters more as orchestration loops recycle context at sub-goal boundaries: once a run clears its context the handoff is the only channel between runs, and no surviving context is left to contradict it."""

_CONTINUE_EMIT_AND_PROCEED = """\
5. **Emit continue block (~15 lines max).** Present:
   - **P0** — next action + Linear link if available (note if promoted from Open)
   - **Drift** — lead here whenever step 3 found a mismatch: the sha diff, the commits landed since, any already-Done P0 or already-merged PR. It outranks every other line in this block.
   - **Done / Open / Blockers** — compressed from handoff, each item tagged **verified**, **corrected**, or **unverified** from step 3. Never restate an Open item as fact when step 3 did not confirm it.
   - **Cumulative** (when present) — sub-goal, attempt vs cap, budget spent, refuted strategies, resume line
   - **Verify first** — commands from handoff
   - **Success criterion**
   - **Host reset** — Claude Code: operator may `/clear` then continue; Cursor: **new chat** then re-invoke this skill
   - **Stale warning** if handoff **Updated** is >7 days old or missing — the weaker signal; report it *below* the drift line, never in place of it

6. **Re-verify live state** when **Cumulative** is present — handoff is a pointer, not proof (orchestration §7 / cold-start companion). Step 3 covers sha, P0 status, and named PRs; also re-read any *metric* the handoff quotes (test count, score, coverage) from its newest artifact rather than inheriting the prose.

7. **Proceed on P0.** Ask only if P0 is ambiguous; otherwise start using normal TAPPS workflow (`tapps_quick_check` after Python edits). Do **not** ask the user to re-paste prior context when handoff files exist."""

# Skills removed in v3.12.0 (TAP-3930) — wrapper skills with no orchestration value.
DEPRECATED_TAPPS_SKILLS: frozenset[str] = frozenset(
    {"tapps-score", "tapps-gate", "tapps-validate", "tapps-report"}
)

# TAP-7386: one derived table mapping a role name to its model + effort, so a
# model migration is a one-place edit here instead of one edit per skill
# template below. Model ids and effort words come from the installed Claude
# Code CLI's accepted values (cc-expert doc 10-skills.md), never hardcoded
# independently of that source.
class RoleResolutionError(ValueError):
    """Raised when a skill template references an unknown model role."""


MODEL_ROLES: dict[str, dict[str, str]] = {
    "driver": {"model": "claude-sonnet-5", "effort": "medium"},
    "lane": {"model": "claude-sonnet-5", "effort": "medium"},
    "verifier-deterministic": {"model": "claude-haiku-4-5-20251001", "effort": "low"},
    "verifier-comparative": {"model": "claude-sonnet-5", "effort": "medium"},
    "verifier-semantic": {"model": "claude-sonnet-5", "effort": "medium"},
    "explorer": {"model": "claude-haiku-4-5-20251001", "effort": "low"},
    "prose": {"model": "claude-haiku-4-5-20251001", "effort": "low"},
}


def resolve_role_model(role: str) -> str:
    """Resolve a ``MODEL_ROLES`` role name to its literal ``model:`` value.

    Unknown roles refuse loudly (never fall back to a default model) so a
    typo'd role name fails at template-render time, not silently at runtime.
    """
    try:
        return MODEL_ROLES[role]["model"]
    except KeyError as exc:
        raise RoleResolutionError(f"unknown model role: {role!r}") from exc


# TAP-7385: the only skills whose frontmatter stays ambient (invocable by a
# plain-language request, no ``disable-model-invocation`` pin) across BOTH
# CLAUDE_SKILLS and CURSOR_SKILLS. Every other entry in either dict must carry
# the pin. This set is read by the frontmatter tests instead of being
# re-typed there, so the allowlist has exactly one place to drift from.
AMBIENT_FRONT_DOOR_SKILL_NAMES: frozenset[str] = frozenset(
    {
        # Universal task-completion gate — must trigger on "I'm done" style
        # requests without the user knowing its exact name.
        "tapps-finish-task",
        # Session bootstrap — must trigger on "continue" / "pick up where we
        # left off" without an explicit invocation.
        "tapps-continue-session",
        # Routing skill — has to be ambient to route *other* requests at all;
        # a non-ambient router can never be reached by the flow it routes.
        "tapps-wayfind",
    }
)

# Core skill tier for init/upgrade when ``skill_tier: core`` (context budget).
CORE_SKILL_NAMES: frozenset[str] = frozenset(
    {
        "tapps-finish-task",
        "tapps-handoff-session",
        "tapps-continue-session",
        "tapps-memory",
        "tapps-tool-reference",
        "tapps-research",
        "tapps-security",
        "tapps-init",
        "tapps-upgrade",
        "tapps-engagement",
        "tapps-apply-files",
        "linear-issue",
        "linear-read",
    }
)

_FINISH_TASK_CHECKLIST_AND_DOC_GAPS_CURSOR = finish_task_checklist_and_doc_gaps(
    claude_nlt_prefix=False
)

_FINISH_TASK_CHECKLIST_AND_DOC_GAPS_CLAUDE = finish_task_checklist_and_doc_gaps(
    claude_nlt_prefix=True
)

# ---------------------------------------------------------------------------
# Skills templates (Story 12.8)
# ---------------------------------------------------------------------------
#
# The 16 CLAUDE_SKILLS bodies below live as package-data ``.md`` files under
# ``assets/claude_skills/`` instead of inline string literals, so each is
# individually diffable/lintable/reviewable as the document it is. Every
# body still carries a ``model:`` line that is templated, never baked in:
# the file holds a ``{{model:<role>}}`` placeholder and ``_load_claude_skill``
# resolves it via ``resolve_role_model`` at load time, so ``MODEL_ROLES``
# stays the single place a model changes (TAP-7386). Baking a resolved
# model string into the file was explicitly rejected.

_SKILL_ASSET_PACKAGE = "tapps_mcp.pipeline"
_SKILL_ASSET_SUBDIR = "assets/claude_skills"
_MODEL_MARKER_RE = re.compile(r"\{\{model:([a-z0-9_-]+)\}\}")


def _read_claude_skill_asset(skill_name: str) -> str:
    """Read one ``CLAUDE_SKILLS`` body from package data, marker un-resolved.

    Mirrors ``tapps_mcp.prompts.prompt_loader._read_resource`` (same
    ``sys.frozen`` PyInstaller fallback) since this module ships inside the
    same frozen binary as the prompt package.
    """
    file_name = f"{skill_name}.md"
    if getattr(sys, "frozen", False):
        return (Path(__file__).parent / _SKILL_ASSET_SUBDIR / file_name).read_text(
            encoding="utf-8"
        )
    ref = importlib.resources.files(_SKILL_ASSET_PACKAGE).joinpath(
        f"{_SKILL_ASSET_SUBDIR}/{file_name}"
    )
    return ref.read_text(encoding="utf-8")


def _load_claude_skill(skill_name: str) -> str:
    """Load one ``CLAUDE_SKILLS`` body and resolve its ``{{model:role}}`` marker.

    The marker is substituted via :func:`resolve_role_model` at import time --
    the same substitution point the prior inline-concatenated bodies used --
    so behavior is unchanged; only the body's storage location moved.
    """
    raw = _read_claude_skill_asset(skill_name)
    return _MODEL_MARKER_RE.sub(lambda m: resolve_role_model(m.group(1)), raw)


CLAUDE_SKILLS: dict[str, str] = {
    "tapps-finish-task": _load_claude_skill("tapps-finish-task"),
    "tapps-handoff-session": _load_claude_skill("tapps-handoff-session"),
    "tapps-continue-session": _load_claude_skill("tapps-continue-session"),
    "tapps-review-pipeline": _load_claude_skill("tapps-review-pipeline"),
    "tapps-refactor": _load_claude_skill("tapps-refactor"),
    "tapps-research": _load_claude_skill("tapps-research"),
    "tapps-security": _load_claude_skill("tapps-security"),
    "tapps-memory": _load_claude_skill("tapps-memory"),
    "tapps-tool-reference": _load_claude_skill("tapps-tool-reference"),
    "tapps-init": _load_claude_skill("tapps-init"),
    "tapps-upgrade": _load_claude_skill("tapps-upgrade"),
    "tapps-engagement": _load_claude_skill("tapps-engagement"),
    "tapps-apply-files": _load_claude_skill("tapps-apply-files"),
    "linear-issue": _load_claude_skill("linear-issue"),
    "linear-read": _load_claude_skill("linear-read"),
    "linear-release-update": _load_claude_skill("linear-release-update"),
}

CURSOR_SKILLS: dict[str, str] = {
    "tapps-finish-task": """\
---
name: tapps-finish-task
description: >-
  Run the end-of-task TAPPS pipeline in one shot: validate changed files,
  verify the checklist, and optionally save learnings to memory. Use when
  you have finished implementing a task and want to validate, checklist,
  and save learnings in one shot.
mcp_tools:
  - tapps_validate_changed
  - tapps_checklist
  - tapps_lookup_docs
---

Close out the current task end-to-end. Run each step; do NOT skip one that failed — surface the failure and stop.

1. **Validate changed files.** Identify files edited this session (git status, edit history). Call `tapps_validate_changed` with explicit `file_paths` (comma-separated). Never call without `file_paths`. If any file fails, list it with the top blocking issue and stop.

   """
    + FINISH_TASK_VALIDATE_CALL_GRAPH_NOTE
    + """

"""
    + _FINISH_TASK_CHECKLIST_AND_DOC_GAPS_CURSOR
    + """

4. **Save learnings (conditional).** If the session produced a non-obvious architectural or pattern-level decision, run `uv run tapps-mcp memory save --key <slug> --tier <architectural|pattern> --value "<decision>"` (CLI via BrainBridge). Skip for routine fixes. Brain offline → skip silently.
5. **Report.** Emit a one-line summary: `Files validated: N pass. Checklist: <task_type> complete. Doc gaps: cleared|none. Memory saved: yes|no.`

6. **Transfer (optional).** If the user is ending the chat, invoke the `tapps-handoff-session` skill so the next session can run `tapps-continue-session`.
""",
    "tapps-handoff-session": """\
---
name: tapps-handoff-session
description: >-
  Write a structured cross-session handoff and close the TAPPS session
  lifecycle so the next chat can continue without a long paste. Use when
  ending a session, handing off to a fresh chat, or the user says hand
  off, save session state, or continue next time.
mcp_tools:
  - tapps_handoff_save
  - tapps_session_start
disable-model-invocation: true
---

End the session with a durable handoff the next chat loads via `tapps-continue-session`.

"""
    + _HANDOFF_PRE_GATE
    + """

1. **Draft handoff (5-10 bullets):** Done, Open, Next (P0), Blockers (`- none` when clear), optional Changed files, Verify, Success criterion.**Checkpoint trigger:** when the user says "checkpoint", "context full", or an
   orchestration prompt prints a `CHECKPOINT` block — include the **Cumulative**
   section above (not optional). Cross-ref: orchestration-prompt method §7.

"""
    + _HANDOFF_P0_GATE
    + """

"""
    + _HANDOFF_MARKDOWN_SHAPE
    + """

"""
    + _HANDOFF_PERSIST
    + """

3. **Report.** `Handoff: .tapps-mcp/session-handoff.md. Linear P0: <id|none>. brain_mirror: ok|skipped. session_end: ok|skipped. Next: tapps-continue-session`
""",
    "tapps-continue-session": """\
---
name: tapps-continue-session
description: >-
  Bootstrap a fresh session from the last handoff by reading session-handoff.md,
  optional Linear context, and TAPPS session start — without pasting a long
  manifesto. Use when the user says continue, pick up where we left off, resume,
  or start a new session on an existing task (optional TAP-#### argument).
mcp_tools:
  - tapps_session_start
  - linear_get_issue
---

Start work in a fresh context by assembling structured state.

1. **Session bootstrap.**
   - **Preferred:** Call `tapps_session_start()`. Note `compaction_rehydration` if present.
   - **CLI fallback** (MCP unavailable): Run `uv run tapps-mcp doctor --quick` and read `.tapps-mcp.yaml` for project context. Proceed without blocking.
- **Usage gaps:** `usage_gaps.recurring_validation_skips` is 7-day rolling fleet telemetry — not proof this call failed. Still run validate + checklist at epic boundaries in execution repos.

"""
    + _CONTINUE_LOAD_AND_CONTEXT
    + """

"""
    + _CONTINUE_GROUND_TRUTH_GATE
    + """

4. **Linear context.**
   - If the user passed `TAP-####` (argument or handoff **Linear P0**), call `get_issue(id=...)`.
   - For backlog/triage without a known id, invoke the `linear-read` skill — do not call raw `list_issues` (cache gate).

"""
    + _CONTINUE_EMIT_AND_PROCEED
    + """
""",
    "tapps-review-pipeline": """\
---
name: tapps-review-pipeline
description: >-
  Orchestrate a parallel review-fix-validate pipeline across multiple changed files.
  Spawns tapps-review-fixer agents for parallel processing. Use when you have
  multiple changed Python files that need parallel review, scoring, and quality
  gate fixing before declaring work complete.
mcp_tools:
  - tapps_validate_changed
  - tapps_checklist
  - tapps_session_start
disable-model-invocation: true
---

Run a parallel review-fix-validate pipeline on changed Python files:

1. Call `tapps_session_start` if not already called
2. Determine scope: detect changed Python files via git diff or accept a file list
3. For each file (or batch of files), spawn a `tapps-review-fixer` agent:
   - Pass the file path and instructions to score, fix, and gate the file
4. Wait for all agents to complete and collect their results
5. Review and merge any changes
6. Call `tapps_validate_changed` with explicit `file_paths` to verify all files pass
7. **Creator ≠ verifier:** the agents that *implemented* fixes must not be the sole judges.
   Spawn a fresh review pass that did not write the fixes, then
   `uv run tapps-mcp pipeline-mark creator-verifier`.
8. Call `tapps_checklist(task_type="review")` for final verification — clear
   `creator_verifier_skipped` / `contract_assertions_unverified` if present
9. Present a summary table: file | before score | after score | gate | fixes applied
""",
    "tapps-refactor": """\
---
name: tapps-refactor
description: >-
  Function-level refactor workflow using call graph tools (Epic 114).
  Use before changing a symbol's signature, deleting a function, or
  refactoring callers — maps blast radius via tapps_call_graph and diff_impact.
mcp_tools:
  - tapps_session_start
  - tapps_call_graph
  - tapps_impact_analysis
  - tapps_diff_impact
  - tapps_quick_check
  - tapps_validate_changed
  - tapps_checklist
disable-model-invocation: true
---

Symbol-level refactor workflow (Epic 114 / ADR-0017):

1. **Session bootstrap.** Call `tapps_session_start()` — read `call_graph` (`ready`, `stale`, `degraded`). Stale is informational; graph tools auto-rebuild on first use.

2. **Before editing a function.** `tapps_call_graph(symbol='...', query='callers')` — who calls this symbol? Use `query='callees'` or `query='chain'` as needed.

3. **Optional module context.** `tapps_impact_analysis(file_path='...', symbol='...', granularity='both')`.

4. **Edit loop.** After each Python file change, `tapps_quick_check(file_path='...')`.

5. **After edits.** `tapps_diff_impact(file_paths='...')` or `/tapps-finish-task` (`include_impact` default true refreshes cache).

6. **Close out.** `/tapps-finish-task` with `task_type=refactor`.

See `docs/CALL_GRAPH.md` for gap_rate / degraded semantics.
""",
    "tapps-research": """\
---
name: tapps-research
description: >-
  Look up library documentation and run open-ended / latest web research
  for the technologies used in this project. Use when writing code that uses
  an external library, when you need API reference, or when the question is
  time-sensitive / not covered by Context7 docs.
mcp_tools:
  - tapps_research
  - tapps_lookup_docs
disable-model-invocation: true
---

Research using TappsMCP's unified front door (ADR-0030):

1. Prefer `tapps_research`:
   - Library/API: pass `library=` (and optional `topic=`) or `route="docs"`
   - Open-ended / latest: pass `query=` (auto-routes to brain `web_research`)
   - Single URL scrape: pass `url=` (brain `research_fetch`)
2. For a known library name only, `tapps_lookup_docs` is fine (doc-only).
3. If the brain path returns `degraded=true` / `success=false`, report the structured error — do not invent Exa/Firecrawl keys locally.
4. Synthesize findings into a clear, actionable answer with code examples when docs content is present.
5. Suggest follow-up lookups if additional coverage is needed
""",
    "tapps-security": """\
---
name: tapps-security
description: >-
  Run a comprehensive security audit on a Python file including vulnerability scanning
  and dependency CVE checks. Use when reviewing security-sensitive changes,
  before a security audit, or before a production release.
mcp_tools:
  - tapps_security_scan
  - tapps_dependency_scan
disable-model-invocation: true
---

Run a comprehensive security audit using TappsMCP:

1. Call `tapps_security_scan` on the target file to detect vulnerabilities
2. Call `tapps_dependency_scan` to check for known CVEs in dependencies
3. Group all findings by severity (critical, high, medium, low)
4. Suggest a prioritized fix order starting with the highest-severity issues
""",
    "tapps-memory": """\
---
name: tapps-memory
description: >-
  Manage shared project memory via tapps-mcp CLI and session notes.
  Use when saving cross-session decisions, searching prior patterns, or
  checking brain bridge health. For chat handoffs use tapps-handoff-session.
mcp_tools:
  - tapps_session_start
  - tapps_session_notes
disable-model-invocation: true
---

`tapps_memory` on the **`nlt-memory`** MCP server is a slim facade (TAP-3895). Default consumer path is **`uv run tapps-mcp memory`** (bridge-only — never add direct `tapps-brain` to `.mcp.json`).

## Routing guide

| Need | Path |
|------|------|
| Cross-chat handoff | `tapps-handoff-session` then `tapps-continue-session` |
| Session-local notes | `tapps_session_notes(action="save", ...)` |
| Save / recall / search brain | `uv run tapps-mcp memory <subcommand>` |
| Brain health | `tapps_session_start(quick=false)` → `brain_bridge_health` |

## CLI (daily drivers)

`memory save`, `get`, `search`, `list`, `export` — see skill body for examples. Shell auth: `TAPPS_BRAIN_AUTH_TOKEN` or `TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN`.

## Tiers

`architectural` (180d), `pattern` (60d), `procedural` (30d), `context` (14d). Tag with `--tags critical,security` when warranted.

## Advanced

Federation, hive, KG: `docs/MEMORY_REFERENCE.md`. Consumer agents use CLI; coordinator agents may use brain MCP directly.
""",
    "tapps-tool-reference": """\
---
name: tapps-tool-reference
description: >-
  Look up when to use each TappsMCP tool. Full tool reference with per-tool
  guidance for session start, scoring, validation, checklist, docs, experts.
  Use when you need guidance on which TappsMCP tool to call for a given situation.
mcp_tools:
  - tapps_server_info
disable-model-invocation: true
---

When the user asks about TappsMCP tools, provide the full tool reference.
Essential: tapps_session_start (first), tapps_quick_check (after edits),
tapps_validate_changed (before complete, always pass file_paths), tapps_checklist (before complete).

## Essential tools (always-on workflow)
| Tool | When to use it |
|------|----------------|
| **tapps_session_start** | **FIRST call in every session** — server info + call_graph cache status |
| **tapps_quick_check** | **After editing any Python file** — quick score + gate + basic security |
| **tapps_validate_changed** | **Before multi-file complete** — score + gate on changed files. Always pass explicit `file_paths`. `include_impact=true` (default) refreshes call-graph cache. |
| **tapps_checklist** | **Before declaring complete** — reports which tools were called |
| **tapps_quality_gate** | Before declaring work complete — ensures file passes preset |

## Validation & analysis
| Tool | When to use it |
|------|----------------|
| **tapps_security_scan** | Security-sensitive changes or before security review |
| **tapps_validate_config** | When adding/changing Dockerfile, docker-compose, infra |
| **tapps_impact_analysis** | Module-level import blast radius before API or layout changes |
"""
    + TOOL_REFERENCE_CALL_GRAPH_ROWS
    + """
| **tapps_dead_code** | Find unused code during refactoring |
| **tapps_dependency_scan** | Check for CVEs before releases |
| **tapps_dependency_graph** | Understand module dependencies, circular imports |

## Planning, metrics & audit
| Tool | When to use it |
|------|----------------|
| **tapps_decompose** | Break a vague task into ordered, verifiable TAPPS tool-call steps before starting |
| **tapps_pipeline** | Show TAPPS pipeline stage progress and the next recommended tool call |
| **tapps_audit_campaign** | Plan, dispatch, or convert a file-scope audit campaign to a fix plan |
| **tapps_usage** | Session gap report: tools called vs pipeline expectations (edits without validation, libraries used without lookup_docs) |
| **tapps_dashboard** | Metrics dashboard: usage, gate pass rate, and trends |
| **tapps_stats** | Per-tool usage statistics: call counts, success rates, latency percentiles |

For function-level refactors use `/tapps-refactor`. Call `tapps_server_info` for the latest recommended workflow string.
""",
    "tapps-init": """\
---
name: tapps-init
description: >-
  Bootstrap TappsMCP in a project. Creates AGENTS.md, TECH_STACK.md,
  platform rules, hooks, agents, skills, and MCP config. Use when setting
  up TappsMCP in a new or existing project for the first time.
mcp_tools:
  - tapps_init
  - tapps_doctor
disable-model-invocation: true
---

Bootstrap TappsMCP in a new or existing project:

1. Call `tapps_init` to run the full bootstrap pipeline (`mcp_config` defaults true; **ADR-0018 default bundle is `full`**)
2. Check the response for `content_return: true` — if present, the server could not
   write files directly (Docker / read-only mount).  Apply the files from
   `file_manifest.files[]` using the Write tool.  See `/tapps-apply-files` for details.
3. If files were written directly, review the created files (AGENTS.md, TECH_STACK.md, platform rules, hooks, MCP config)
4. Confirm MCP config lists NLT `nlt-*` servers only (no direct tapps-brain entry — bridge-only)
5. If any issues are reported, call `tapps_doctor` to diagnose
6. Verify that MCP config has tool auto-approval rules
7. For shared-brain HTTP wiring, see docs/operations/CONSUMER-REPO-BRAIN-WIRING.md
8. Confirm the project is ready for the TappsMCP quality workflow
9. **Token-tight opt-down (optional):** `tapps-mcp mcp-bundle set developer` (or `minimal`), then reload MCP.

**If `tapps_init` is not available** (server not in available MCP servers), use the CLI:
1. Run from the project root: `tapps-mcp upgrade --force --host auto`
2. Then verify: `tapps-mcp doctor`
3. Restart your MCP host to pick up the new config
""",
    "tapps-upgrade": """\
---
name: tapps-upgrade
description: >-
  Upgrade tapps-mcp / docs-mcp in this project to the latest version.
  Reinstalls global CLIs, restarts MCP servers, refreshes scaffolding via
  `tapps-mcp upgrade`, verifies via doctor + checklist. Use when a new
  tapps-mcp or docs-mcp version is available and the project scaffolding
  needs to be refreshed.
mcp_tools:
  - tapps_session_start
  - tapps_doctor
  - tapps_checklist
disable-model-invocation: true
---

Upgrade tapps-mcp / docs-mcp end-to-end. The user's request is standing authorization — do NOT pause mid-flow.

**Pick install source from prompt:**

- Local checkout: `uv tool install --reinstall --from <path>/packages/tapps-mcp tapps-mcp` (and same for `docs-mcp`).
- Git tag: `uv tool install --reinstall "git+https://github.com/wtthornton/tapps-mcp.git@vX.Y.Z#subdirectory=packages/tapps-mcp" tapps-mcp`.

If unspecified, ask once.

**Steps:**

1. Reinstall both CLIs. Verify with `uv tool list | grep -E '(tapps-mcp|docs-mcp)'`.
2. Restart MCP servers (exit + reopen Cursor, or reconnect). Stop on first invocation; resume after restart.
3. `tapps_session_start(quick=false, force=true)`. Confirm `server.version` matches and `install_drift.drift_detected == false`.
4. `tapps-mcp upgrade --dry-run`. Review diff + `mcp_bundle` / `mcp_bundle_note` (custom trimmed sets preserved). Pause if a customized canonical section will be overwritten.
5. `tapps-mcp upgrade` (writes timestamped backup to `.tapps-mcp/backups/<ts>/`).
6. `tapps-mcp doctor` AND `tapps_checklist(task_type="upgrade")`. Stop on failure. Doctor shows eager (Claude) vs listed (Cursor).
7. One-line summary: versions, files refreshed, bundle, doctor + checklist status, backup path.

**Bundle opt-down:** `tapps-mcp mcp-bundle set developer|minimal|…` then reload MCP.

**Rollback:** `tapps-mcp rollback` (only if step 5/6 reveals a regression).

**Do NOT:** publish to PyPI/npm; bump tapps-mcp repo versions; touch tapps-brain; add `tapps-brain` as a top-level `.mcp.json` entry.
""",
    "tapps-engagement": """\
---
name: tapps-engagement
description: >-
  Change the TappsMCP enforcement intensity (high, medium, or low).
  Controls which quality tools are mandatory vs optional. Use when you want
  to switch between strict, balanced, or advisory enforcement modes.
mcp_tools:
  - tapps_set_engagement_level
disable-model-invocation: true
---

Set the TappsMCP LLM engagement level:

1. Call `tapps_set_engagement_level` with the desired level
2. **high** - All quality tools are mandatory; checklist enforces strict compliance
3. **medium** - Balanced enforcement; core tools required, advanced tools recommended
4. **low** - Optional guidance; quality tools are suggestions, not requirements
5. Confirm the level was saved to `.tapps-mcp.yaml`
6. If `content_return: true`, write `.tapps-mcp.yaml` from `file_manifest` using the Write tool
""",
    "tapps-apply-files": """\
---
name: tapps-apply-files
description: >-
  Apply file operations from a TappsMCP content-return response. Use when
  a TappsMCP or DocsMCP tool returns content_return: true with a file_manifest
  because the server runs in Docker and cannot write files directly.
mcp_tools: []
disable-model-invocation: true
---

When a TappsMCP or DocsMCP tool returns `content_return: true` with a `file_manifest`,
the server could not write files (Docker / read-only filesystem).  Apply the files:

1. Read `file_manifest.agent_instructions.persona` — adopt that role
2. If `backup_recommended` is true, warn the user that existing files may be overwritten
3. Sort files by `priority` (lowest first) — config files before content files
4. For each file in `file_manifest.files[]`:
   - **mode "create"**: Use the Write tool.  Create parent directories as needed.
   - **mode "overwrite"**: Use the Write tool to replace the file entirely.
   - **mode "merge"**: Read the existing file first, then apply the `content` as a
     replacement for the managed section.  The content is the pre-computed merge result;
     write it with the Write tool (the merge was already done server-side).
5. Write the `content` field **verbatim** — do not modify, reformat, or add comments
6. Follow `agent_instructions.verification_steps` after all files are written
7. Communicate any `agent_instructions.warnings` to the user
""",
    "linear-issue": """\
---
name: linear-issue
description: Create, lint, validate, or triage Linear issues for agents. Routes to docs-mcp Linear tools and the Linear plugin by user intent. Use when creating, linting, validating, or triaging a Linear issue or epic.
mcp_tools:
  - docs_generate_story
  - docs_lint_linear_issue
  - docs_validate_linear_issue
  - docs_linear_triage
  - linear_get_issue
  - linear_list_issues
  - tapps_linear_snapshot_get
  - tapps_linear_snapshot_put
  - tapps_linear_snapshot_invalidate
disable-model-invocation: true
---

Work with Linear issues for AI-agent consumption. Infer intent from the user's prompt and act autonomously within scope. The user's original request is standing authorization for the full generator → validator → save chain — do NOT pause mid-flow to ask "should I create this?"

**Assignee — agent, not human (applies to every write below).** Resolve the agent user once per session via `linear_list_users`, picking the user whose `name`/`displayName`/`email` matches `agent`, `bot`, `tapps`, `claude`, or `agent_user` in `.tapps-mcp.yaml`. Cache the id. Pass `assignee="<agent-user-id-or-name>"` on every Linear write. If no agent user exists, leave `assignee` unset — never fall back to the OAuth user. Only override when the user explicitly names a person.

**Create** a new issue (default when prompt describes a change/bug):

1. Call `docs_generate_story` with the user's ask. Required args: `title` (<=80 chars, pattern `file.py: symptom`), `files` (comma-separated, each with `:LINE-RANGE`), `acceptance_criteria` (newline-separated verifiable items — commas inside a criterion are preserved; do not comma-delimit).
2. Default `audience="agent"` emits the 5-section Linear template (What/Where/Why/Acceptance/Refs) and round-trips through the validator.
3. If the call returns `INPUT_INVALID`, refine the inputs per the error message and retry. Do NOT pass `audience="human"` unless the user asks for a product-review doc.
4. Call the Linear plugin's write tool with `assignee="<agent-user-id-or-name>"`. Proceed without prompting the user.
5. After the write returns, call `tapps_linear_snapshot_invalidate(team=<team>, project=<project>)` to evict stale cached snapshots for that slice.

**Lint** an existing issue (prompt like "lint TAP-686"):

1. Fetch via `linear_get_issue`.
2. Pass title/description/labels/priority/estimate to `docs_lint_linear_issue`.
3. Surface score, findings (with fix_hints), and reclaimable noise bytes.

**Validate** before creating (prompt like "is this agent-ready?"):

1. Call `docs_validate_linear_issue` with the payload.
2. Report `{agent_ready, score, missing[]}`. Missing items are blockers; propose a concrete fix per item.

**Triage** a batch (prompt like "triage open issues"):

1. If the user names a specific issue (e.g. "triage TAP-686"), use `linear_get_issue(id="TAP-686")` — skip list/cache entirely.
2. **Cache-first read:** call `tapps_linear_snapshot_get(team=<team>, project=<project>, state="backlog" | "unstarted", label?)`. If `data.cached` is `true`, use `data.issues` directly — Linear was not called.
3. **On cache miss** (`data.cached` is `false`): call `linear_list_issues` with narrow filters — `team`, `project`, `state`, `includeArchived=false` (never call without filters). Then populate the cache by calling `tapps_linear_snapshot_put(team, project, issues_json=json.dumps(response.issues), state, label?)` using the **same** team/project/state/label/limit as the get call so the keys align.
4. Pass the list to `docs_linear_triage`.
5. Apply label_proposals, parent_groupings, and metadata_gaps via Linear writes (each carrying `assignee="<agent-user-id-or-name>"` for any newly-owned items). No mid-flow user confirmation.
6. After any write, call `tapps_linear_snapshot_invalidate(team=<team>, project=<project>)` to refresh the cache on next read.

Rules (enforced by docs-mcp tools):

- Title <=80 chars; no em-dash preambles.
- Inline-code filenames (`AGENTS.md`), never `[AGENTS.md](AGENTS.md)` (Linear's autolinker mangles).
- Bare `TAP-###` refs, never `<issue id="UUID">TAP-###</issue>` wrappers.
- `## Acceptance` has at least one verifiable `- [ ]` item.
- `## Where` includes at least one `path/to/file.ext:LINE-RANGE` anchor.
""",
    "linear-read": """\
---
name: linear-read
description: Read multi-issue Linear data via cache-first dance. MANDATORY for any list-style Linear read. Routes through tapps_linear_snapshot_get/put before list_issues. Use when listing, filtering, or reviewing Linear issues (backlog review, "what's open", triage, "find issues assigned to X"). Single-issue lookups go straight to get_issue instead.
mcp_tools:
  - tapps_linear_snapshot_get
  - tapps_linear_snapshot_put
  - tapps_linear_list_issues
  - linear_list_issues
  - linear_get_issue
disable-model-invocation: true
---

Multi-issue Linear reads are cache-first by contract (TAP-967 audit: 5,368 `list_issues` calls / 0.26% cache adoption). Invoke ANY time the user asks for a list, batch, or filtered view of Linear issues.

**When to invoke:** "list Linear issues", "what's open in TAP", "find issues assigned to X", "review the backlog". Skip for single-issue lookups (`get_issue(id="TAP-686")`).

**Core flow — every multi-issue read:**

1. `tapps_linear_snapshot_get(team, project, state, label?)` first. Use `state="open"`/`"closed"` as **cache buckets** only — Linear does not understand those aliases.
2. On `cached=true`, use `data.issues` and filter in-memory — `list_issues` is NOT called.
3. On `cached=false`, call `tapps_linear_list_issues(team, project, state, label?, limit?)` as a gate check (TAP-2010). On `ok=true` for a bucket alias, call `linear_list_issues` with team/project only (**omit state**), `includeArchived=false`, then filter by `statusType` in memory. On `ok=true` for a concrete Linear state, pass that state through. On `ok=false`, follow the `hint` (re-call `snapshot_get` first).
4. Immediately call `tapps_linear_snapshot_put(team, project, issues_json=json.dumps(issues), state, label?, limit?)` with the **same cache-bucket `state`** as the get call (e.g. still `state="open"`).

**The 6-poll kickoff antipattern:** firing six `list_issues` calls (one per state x priority bucket) collapses to one `snapshot_get(state="open")` plus an in-memory filter. The 5-min open-state TTL means the next session warms instantly.

**Status-bucket sweep antipattern:** three sequential `list_issues` calls for `backlog`/`unstarted`/`started` collapses to one `snapshot_get(state="open")` + memory filter on `state.type`.

**Anti-patterns — do not do these:**

- `list_issues` without a prior `snapshot_get` for the same key.
- `list_issues({})` or `list_issues({team, limit:250})` (the unfiltered scroll).
- Passing `state="open"` or `state="closed"` to the Linear plugin `list_issues` — those are cache buckets and return zero issues.
- Re-fetching the same narrow query 5-12 times in one turn with no intervening writes.
- Single-issue lookup via `list_issues` filtering — use `get_issue(id)` instead.
""",
    "linear-release-update": """\
---
name: linear-release-update
description: Post a structured Linear project update document on a version release. Orchestrates tapps_release_update → docs_validate_release_update → save_document → cache invalidation. Use when posting a release announcement to Linear after shipping a new version.
mcp_tools:
  - tapps_release_update
  - docs_generate_release_update
  - docs_validate_release_update
  - docs_release_gate
  - linear_save_document
  - tapps_linear_snapshot_invalidate
disable-model-invocation: true
---

Post a structured Linear project update document when a new version is released. The user's request to post a release update is standing authorization for the full pipeline — do NOT pause mid-flow to ask "should I post this?"

**Flow:**

1. Call `tapps_release_update(version, prev_version, team, project)`.
   - `version` and `prev_version` are required. Parse from the user's prompt or ask once if both are missing.
   - `team` and `project`: read from `.tapps-mcp.yaml` if present (`linear_team`, `linear_project` fields), otherwise pass empty strings.
   - If `dry_run=true` is requested, pass it through — the tool returns the body without requiring validation to pass.

1b. **Docs release gate (required unless dry_run):** Call `docs_release_gate`. Stop on fail.

2. Check the response:
   - If `success=false`: surface the `error.message` and `findings` to the user. Stop — do not post.
   - If `agent_ready=false` (and not dry_run): surface findings, stop.
   - If `agent_ready=true`: proceed.

3. Call `linear_save_document`:
   - `project`: use `data.project` from the tool response.
   - `title`: use `data.document_title` from the tool response (format: `Release vX.Y.Z — YYYY-MM-DD`).
   - `content`: use `data.body` from the tool response verbatim.

4. After `save_document` succeeds, call `tapps_linear_snapshot_invalidate`:
   - `team`: use `data.team` from tool response.
   - `project`: use `data.project` from tool response.

5. Report the document URL from `save_document` response and the version that was posted.

**Rules:**
- Never call `save_document` without a prior `agent_ready=true` from `tapps_release_update` (unless `dry_run=true`).
- `document_title` must use the em-dash format from `data.document_title` — do not construct it manually.
- Do not modify the body returned by the tool. Pass `data.body` verbatim.
""",
}

from tapps_mcp.pipeline.platform_domain_skills import (
    CLAUDE_DOMAIN_SKILLS,
    CURSOR_DOMAIN_SKILLS,
)

CLAUDE_SKILLS.update(CLAUDE_DOMAIN_SKILLS)
CURSOR_SKILLS.update(CURSOR_DOMAIN_SKILLS)


def _pin_ambient(skill_name: str, body: str) -> str:
    """Insert ``disable-model-invocation: true`` into ``body``'s frontmatter.

    Used for bodies sourced from sibling template modules
    (``platform_domain_skills``, ``platform_skill_orchestration``,
    ``platform_skill_continuous_learning``) that this lane's file partition
    does not include — the pin is applied here, post-import, instead of
    editing those modules. A no-op if the body already carries the pin.
    """
    if "disable-model-invocation:" in body:
        return body
    assert body.startswith("---\n"), f"{skill_name}: body has no frontmatter"
    end = body.index("\n---\n", 4)
    return body[:end] + "\ndisable-model-invocation: true" + body[end:]


# TAP-7385: the 8 ambient CLAUDE_SKILLS beyond the 3 stated front doors
# (AMBIENT_FRONT_DOOR_SKILL_NAMES) were simply missed by the prior pass, not
# intentionally ambient — none of them is a fleet-wide entry point the way
# tapps-finish-task / tapps-continue-session / tapps-wayfind are. Pin all 8,
# on both hosts, without touching the sibling modules that define their
# bodies.
_MISSED_AMBIENT_SKILL_NAMES = (
    "tapps-domain-security",
    "tapps-domain-testing",
    "tapps-domain-frontend",
    "tapps-flow-develop",
    "tapps-flow-review",
    "tapps-flow-frontend",
)
for _name in _MISSED_AMBIENT_SKILL_NAMES:
    CLAUDE_SKILLS[_name] = _pin_ambient(_name, CLAUDE_SKILLS[_name])
    CURSOR_SKILLS[_name] = _pin_ambient(_name, CURSOR_SKILLS[_name])

# ---------------------------------------------------------------------------
# Multi-file / smart-merge skills (orchestration-prompt + tapps-wayfind)
# ---------------------------------------------------------------------------
# The body is host-agnostic prose (no tool grants), so the same text serves the
# Claude and Cursor hosts. orchestration-prompt is one of the 8 missed-ambient
# skills above; tapps-wayfind is a stated front door and stays ambient.
#
# The CLAUDE_SKILLS side of each pair now loads its body from the same
# package-data asset used by every other CLAUDE_SKILLS entry, extracted
# byte-for-byte from ORCHESTRATION_PROMPT_SKILL_BODY / WAYFIND_SKILL_BODY /
# VALIDATION_CONTRACT_SKILL_BODY / CONTINUOUS_LEARNING_CLAUDE_SKILL_BODY at
# the time of extraction (none of those four constants concatenate
# resolve_role_model — each hardcodes its model or omits the field — so no
# {{model:role}} marker applies here). The CURSOR_SKILLS side is untouched:
# it keeps importing the constant directly from the sibling module.
CLAUDE_SKILLS["orchestration-prompt"] = _pin_ambient(
    "orchestration-prompt", _load_claude_skill("orchestration-prompt")
)
CURSOR_SKILLS["orchestration-prompt"] = _pin_ambient(
    "orchestration-prompt", ORCHESTRATION_PROMPT_SKILL_BODY
)
CLAUDE_SKILLS["tapps-wayfind"] = _load_claude_skill("tapps-wayfind")
CURSOR_SKILLS["tapps-wayfind"] = WAYFIND_SKILL_BODY
CLAUDE_SKILLS["tapps-validation-contract"] = _load_claude_skill("tapps-validation-contract")
CURSOR_SKILLS["tapps-validation-contract"] = VALIDATION_CONTRACT_SKILL_BODY
CLAUDE_SKILLS["continuous-learning-v2"] = _pin_ambient(
    "continuous-learning-v2", _load_claude_skill("continuous-learning-v2")
)
CURSOR_SKILLS["continuous-learning-v2"] = _pin_ambient(
    "continuous-learning-v2", CONTINUOUS_LEARNING_CURSOR_SKILL_BODY
)

# Skills whose SKILL.md is refreshed via the managed-block smart-merge instead of
# the all-or-nothing skip/overwrite: the platform body is replaced surgically and
# each project's customizations (outside the markers) are preserved.
SMART_MERGE_SKILL_NAMES: frozenset[str] = frozenset(
    {"orchestration-prompt", "tapps-wayfind", "tapps-validation-contract"}
)

# Prose/meta skills whose frontmatter carries no tool grant (`allowed-tools:` on
# Claude, `mcp_tools:` on Cursor). Their bodies are host-agnostic guidance rather
# than tool-invoking workflows, so the same text serves both hosts.
#
# Exported so the frontmatter tests read the exemption from here instead of
# re-declaring a literal set. Two such tests each held their own copy, and
# neither was updated when tapps-wayfind and tapps-validation-contract were
# added — so both shipped unexempted and the suite went red.
NO_TOOL_GRANT_SKILL_NAMES: frozenset[str] = SMART_MERGE_SKILL_NAMES | {"continuous-learning-v2"}

# Companion files shipped alongside a skill's SKILL.md. Their upgrade policy —
# and every other scaffolded file's — is defined in ``skill_asset_policy``.
SKILL_COMPANION_FILES: dict[str, dict[str, str]] = {
    "orchestration-prompt": ORCHESTRATION_PROMPT_COMPANION_FILES,
    "tapps-wayfind": WAYFIND_COMPANION_FILES,
    "tapps-validation-contract": VALIDATION_CONTRACT_COMPANION_FILES,
    "continuous-learning-v2": CONTINUOUS_LEARNING_COMPANION_FILES,
}

# Companion files created once and NEVER overwritten (project-owned state).
SKILL_CREATE_ONLY_FILES: dict[str, dict[str, str]] = {
    "orchestration-prompt": ORCHESTRATION_PROMPT_CREATE_ONLY_FILES,
}


def _write_skill_companions(
    skill_dir: Path,
    skill_name: str,
    asset_actions: dict[str, dict[str, str]],
    overwrite_warnings: list[str],
) -> None:
    """Write *skill_name*'s companions and fold the outcome into the accumulators.

    The policy logic lives in :mod:`tapps_mcp.pipeline.skill_asset_policy`; this
    resolves the registries, hands them over, and records what happened so
    ``generate_skills`` reports it in one place.
    """
    result = write_companions(
        skill_dir,
        skill_name,
        SKILL_COMPANION_FILES.get(skill_name, {}),
        SKILL_CREATE_ONLY_FILES.get(skill_name, {}),
    )
    asset_actions[skill_name] = result["assets"]
    overwrite_warnings.extend(result["overwrite_warnings"])


SKILLS_MANIFEST_REL_PATH = (".tapps-mcp", "skills-manifest.json")


def _skill_manifest_hash(target: Path) -> str | None:
    """Hash *target*'s managed block, version-normalized, or ``None`` if absent.

    ``None`` covers both a missing file and one that exists but carries no
    ``BEGIN``/``END`` marker yet (a not-yet-force-refreshed skill from before
    TAP-6948 s3) — either way there is nothing on disk for the manifest to
    track until the next refresh gives the file a managed block.
    """
    if not target.exists():
        return None
    block = extract_block(target.read_text(encoding="utf-8"))
    if block is None:
        return None
    return hashlib.sha256(normalize_block_version(block).encode("utf-8")).hexdigest()


def _write_skills_manifest(project_root: Path, platform: str, entries: dict[str, str]) -> None:
    """Merge *entries* into ``.tapps-mcp/skills-manifest.json`` under *platform*.

    Written at the end of every :func:`generate_skills` call — init and
    upgrade both route through here, so the manifest always reflects the
    emitter's most recent run. Records the hash actually written to disk
    (not re-derived from the templates at doctor-check time), so the
    directory-diff check (TAP-6948 s2,
    :func:`tapps_mcp.distribution.doctor_skills.check_skills_manifest_directory`)
    never has to reconstruct engagement-note-dependent content itself — it
    only ever compares two already-computed hashes. Merges rather than
    overwrites so a Claude-only run does not erase a previously written
    Cursor section, and vice versa.
    """
    manifest_path = project_root.joinpath(*SKILLS_MANIFEST_REL_PATH)
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        manifest = {}
    manifest[platform] = entries
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _install_unmanaged_skill(
    target: Path,
    skill_dir: Path,
    skill_name: str,
    content: str,
    engagement_note: str,
    *,
    overwrite: bool,
    asset_actions: dict[str, dict[str, str]],
    overwrite_warnings: list[str],
) -> str:
    """Install/refresh one non-smart-merge skill; return its result bucket.

    TAP-6948 s3: every registry skill outside :data:`SMART_MERGE_SKILL_NAMES`
    now carries the same BEGIN/END managed-block marker as the smart-merge
    trio, so a force-refresh preserves whatever a project wrote in the
    ``tapps-skill-project-customizations`` region below the block instead of
    replacing the file wholesale (TAP-6497's old ``overwrite`` policy for
    non-smart-merge SKILL.md is retired). Split out of :func:`generate_skills`
    to keep that function's branching flat.
    """
    body_with_note = prepend_below_frontmatter(content, engagement_note)
    if target.exists():
        refresh = overwrite or skill_name in SESSION_TRANSFER_SKILL_NAMES
        if refresh:
            action = install_or_refresh_skill(target, body_with_note, skill_name)
            bucket = "skipped" if action == "unchanged" else "updated"
        else:
            bucket = "skipped"
    else:
        install_or_refresh_skill(target, body_with_note, skill_name)
        bucket = "created"

    # Refresh registered companions under their declared policy, regardless of
    # whether SKILL.md itself was skipped — a project customizing SKILL.md
    # still wants its companion docs kept current (matches pre-TAP-6948 s3
    # behavior, where this ran unconditionally after the skip/refresh branch).
    if skill_name in SKILL_COMPANION_FILES or skill_name in SKILL_CREATE_ONLY_FILES:
        _write_skill_companions(skill_dir, skill_name, asset_actions, overwrite_warnings)
    return bucket


def generate_skills(
    project_root: Path,
    platform: str,
    *,
    engagement_level: str = "medium",
    overwrite: bool = False,
    skill_tier: str = "full",
) -> dict[str, Any]:
    """Generate SKILL.md files for the given platform.

    Creates skill directories with ``SKILL.md`` in
    ``.claude/skills/`` or ``.cursor/skills/`` depending on the platform.
    Existing files are skipped to preserve user customizations unless
    *overwrite* is ``True`` (used by the upgrade path to refresh
    corrected frontmatter) or the skill is in
    :data:`SESSION_TRANSFER_SKILL_NAMES` (always refreshed so handoff
    workflows stay aligned with doctor checks). When a refresh does happen,
    every non-smart-merge skill now goes through the same BEGIN/END
    managed-block marker as :data:`SMART_MERGE_SKILL_NAMES`
    (:func:`tapps_mcp.pipeline.skill_managed_block.install_or_refresh_skill`,
    TAP-6948 s3) instead of a wholesale overwrite, so anything a project wrote
    below the block survives.
    When *engagement_level* is set, prepends a note (MANDATORY vs optional).
    When *skill_tier* is ``"core"``, only :data:`CORE_SKILL_NAMES` are written;
    other registry skills are listed under ``skipped_tier``.

    Returns a summary dict with ``created``, ``updated``, ``skipped``, and
    ``skipped_tier`` lists, plus ``assets`` (per-skill companion actions) and
    ``asset_overwrite_warnings`` (customized companions upgrade will replace
    wholesale because their format carries no marker — TAP-6497). Also writes
    ``.tapps-mcp/skills-manifest.json`` (TAP-6948 s2) — see
    :func:`_write_skills_manifest`.
    """
    if platform == "claude":
        skills_base = project_root / ".claude" / "skills"
        templates = CLAUDE_SKILLS
    elif platform == "cursor":
        skills_base = project_root / ".cursor" / "skills"
        templates = CURSOR_SKILLS
    else:
        return {
            "created": [],
            "skipped": [],
            "skipped_tier": [],
            "error": f"Unknown platform: {platform}",
        }

    engagement_note = ""
    if engagement_level == "high":
        engagement_note = "*Engagement: MANDATORY for high-enforcement projects.*\n\n"
    elif engagement_level == "low":
        engagement_note = "*Engagement: Optional for low-enforcement projects.*\n\n"

    tier = skill_tier if skill_tier in {"core", "full"} else "full"
    created: list[str] = []
    updated: list[str] = []
    skipped: list[str] = []
    skipped_tier: list[str] = []
    asset_actions: dict[str, dict[str, str]] = {}
    overwrite_warnings: list[str] = []
    manifest_entries: dict[str, str] = {}
    for skill_name, content in templates.items():
        if tier == "core" and skill_name not in CORE_SKILL_NAMES:
            skipped_tier.append(skill_name)
            continue
        skill_dir = skills_base / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        target = skill_dir / "SKILL.md"

        if skill_name in SMART_MERGE_SKILL_NAMES:
            # wrap_with_markers (TAP-6598) emits the managed-block policy
            # header itself, directly after BEGIN — no prepend needed here.
            action = install_or_refresh_skill(target, content, skill_name)
            _write_skill_companions(skill_dir, skill_name, asset_actions, overwrite_warnings)
            if action == "created":
                created.append(skill_name)
            elif action == "unchanged":
                skipped.append(skill_name)
            else:  # refreshed | migrated
                updated.append(skill_name)
        else:
            bucket = _install_unmanaged_skill(
                target,
                skill_dir,
                skill_name,
                content,
                engagement_note,
                overwrite=overwrite,
                asset_actions=asset_actions,
                overwrite_warnings=overwrite_warnings,
            )
            {"created": created, "updated": updated, "skipped": skipped}[bucket].append(skill_name)

        block_hash = _skill_manifest_hash(target)
        if block_hash is not None:
            manifest_entries[skill_name] = block_hash

    _write_skills_manifest(project_root, platform, manifest_entries)

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "skipped_tier": skipped_tier,
        "skill_tier": tier,
        "assets": asset_actions,
        "asset_overwrite_warnings": overwrite_warnings,
    }


def prune_skills_for_tier(
    project_root: Path,
    platform: str,
    *,
    skill_tier: str = "full",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Remove managed non-core registry skills when ``skill_tier == "core"``.

    Only deletes skill directories whose names appear in the platform registry
    (or :data:`DEPRECATED_TAPPS_SKILLS`) and are outside :data:`CORE_SKILL_NAMES`.
    Unknown user skills are never removed.
    """
    import shutil

    if platform == "claude":
        skills_base = project_root / ".claude" / "skills"
        registry = set(CLAUDE_SKILLS) | set(DEPRECATED_TAPPS_SKILLS)
    elif platform == "cursor":
        skills_base = project_root / ".cursor" / "skills"
        registry = set(CURSOR_SKILLS) | set(DEPRECATED_TAPPS_SKILLS)
    else:
        return {"pruned": [], "would_prune": [], "error": f"Unknown platform: {platform}"}

    tier = skill_tier if skill_tier in {"core", "full"} else "full"
    if tier != "core" or not skills_base.is_dir():
        return {"pruned": [], "would_prune": [], "skill_tier": tier, "bytes_freed": 0}

    would_prune: list[str] = []
    pruned: list[str] = []
    bytes_freed = 0
    for child in sorted(skills_base.iterdir()):
        if not child.is_dir() or not (child / "SKILL.md").is_file():
            continue
        if child.name not in registry:
            continue
        if child.name in CORE_SKILL_NAMES:
            continue
        size = sum(p.stat().st_size for p in child.rglob("*") if p.is_file())
        bytes_freed += size
        would_prune.append(child.name)
        if not dry_run:
            shutil.rmtree(child)
            pruned.append(child.name)

    return {
        "pruned": pruned,
        "would_prune": would_prune,
        "skill_tier": tier,
        "bytes_freed": bytes_freed,
        "dry_run": dry_run,
    }
