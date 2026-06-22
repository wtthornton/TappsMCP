"""Skill definition templates for Claude Code and Cursor.

Contains SKILL.md templates and the ``generate_skills`` function.
Extracted from ``platform_generators.py`` to reduce file size.

Epic 76: Claude skills use space-delimited ``allowed-tools`` per agentskills.io spec.
Cursor skills use ``mcp_tools`` (YAML list); Cursor applies tool restrictions via mcp_tools.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tapps_mcp.pipeline.agent_contract import finish_task_checklist_and_doc_gaps

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Shared session-transfer bodies (TAP-3574/3575/3581)
# ---------------------------------------------------------------------------

_HANDOFF_MARKDOWN_SHAPE = """\
```markdown
# Session handoff
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
```"""

_HANDOFF_P0_GATE = """\
**P0 gate.** Before persisting: when **Open** has real items (not `none` / `- ...` placeholders), **Next (P0)** must name one concrete next action. Set **Linear P0:** to the TAP id when known. If P0 is missing, ask the user once — do not persist an incomplete handoff."""

_HANDOFF_PRE_GATE = """\
0. **Session bootstrap (if needed).** If `tapps_session_start()` was not called this session, call it now (cached is fine) so flywheel scope and checker context are correct. Skip when already called."""

_HANDOFF_PERSIST = """\
2. **Persist (one atomic call when MCP is available).** Do **not** write the file separately before MCP — `tapps_handoff_save` writes `.tapps-mcp/session-handoff.md`, lints, mirrors to brain, and can close the session lifecycle.

   Draft the full markdown in memory using the shape above:
   - **Updated:** run `date -u +%Y-%m-%dT%H:%M:%SZ` — never a placeholder like `T00:00:00Z`
   - **Git:** `git rev-parse --short HEAD` when inside a git repo
   - **Linear P0:** TAP-#### when known (preferred retrieval key for brain session search)
   - **Blockers:** `- none` alone when clear — put user actions under **Verify** or **Next (P0)**, not Blockers
   - **Changed files:** optional bullets from `git status --short` when the session touched many files

   | Priority | When | How |
   |----------|------|-----|
   | 1 (MCP) | `nlt-memory` available | `tapps_handoff_save(markdown=..., session_end=true)` — single call; do **not** also call `tapps_session_end` |
   | 2 (CLI atomic) | Shell auth; no MCP write | `uv run tapps-mcp handoff write --file .tapps-mcp/session-handoff.md --session-end` after writing the file locally |
   | 3 (manual) | Brain HTTP only | `uv run tapps-mcp memory save --key session-handoff --tier context --tags handoff,cross-session --value "$(cat .tapps-mcp/session-handoff.md)"` — full markdown body |
   | 4 (skip) | Brain offline | File-only via Bash heredoc: `mkdir -p .tapps-mcp && cat > .tapps-mcp/session-handoff.md <<'EOF'` … `EOF` |

   Handoff **Updated** older than 7 days: pass `allow_lint_warnings=true` on `tapps_handoff_save` if lint warns on age."""

# Always refreshed on init/upgrade even when overwrite=False (other skills preserve customizations).
SESSION_TRANSFER_SKILL_NAMES: tuple[str, ...] = (
    "tapps-handoff-session",
    "tapps-continue-session",
)

# Legacy alias — older skill bodies referenced this name in comments only.
_HANDOFF_BRAIN_MIRROR = _HANDOFF_PERSIST

_CONTINUE_LOAD_AND_CONTEXT = """\
2. **Load handoff (priority order).**
   - Read `.tapps-mcp/session-handoff.md` if it exists — primary source.
   - Else best-effort CLI (no `tapps_memory` MCP — removed v3.12.0): `uv run tapps-mcp memory get --key session-handoff` (brain offline or auth missing → skip).
   - Optional supplements (only if present): `docs/NEXT_SESSION_PROMPT.md`, `docs/TAPPS_HANDOFF.md` (**Next:** section).
   - **P0 fallback:** If **Next (P0)** is empty but **Open** has bullets, promote the first Open item as provisional P0 and flag it in the continue block.
   - **Memory context (optional):** `uv run tapps-mcp memory recall --recall-key session-handoff --query "<P0 text or Linear id>"` pins the handoff mirror then adds semantic hits (HTTP-safe). Alternative: `uv run tapps-mcp memory search --query "..."`. Skip silently when brain auth is unavailable."""

_CONTINUE_EMIT_AND_PROCEED = """\
4. **Emit continue block (~15 lines max).** Present:
   - **P0** — next action + Linear link if available (note if promoted from Open)
   - **Done / Open / Blockers** — compressed from handoff
   - **Verify first** — commands from handoff
   - **Success criterion**
   - **Stale warning** if handoff **Updated** is >7 days old or missing

5. **Proceed on P0.** Ask only if P0 is ambiguous; otherwise start using normal TAPPS workflow (`tapps_quick_check` after Python edits). Do **not** ask the user to re-paste prior context when handoff files exist."""

# Skills removed in v3.12.0 (TAP-3930) — wrapper skills with no orchestration value.
DEPRECATED_TAPPS_SKILLS: frozenset[str] = frozenset(
    {"tapps-score", "tapps-gate", "tapps-validate", "tapps-report"}
)

_FINISH_TASK_CHECKLIST_AND_DOC_GAPS_CURSOR = finish_task_checklist_and_doc_gaps(claude_nlt_prefix=False)

_FINISH_TASK_CHECKLIST_AND_DOC_GAPS_CLAUDE = finish_task_checklist_and_doc_gaps(claude_nlt_prefix=True)

# ---------------------------------------------------------------------------
# Skills templates (Story 12.8)
# ---------------------------------------------------------------------------

CLAUDE_SKILLS: dict[str, str] = {
    "tapps-finish-task": """\
---
name: tapps-finish-task
user-invocable: true
model: claude-haiku-4-5-20251001
description: Run the end-of-task TAPPS pipeline in one shot — validate_changed, then checklist, then an optional memory save for anything architectural or patterned learned this session. The recommended final step before declaring work complete. Use when you have finished implementing a task and want to validate, run the checklist, and save learnings in one shot.
allowed-tools: mcp__nlt-build__tapps_validate_changed mcp__nlt-build__tapps_checklist mcp__nlt-build__tapps_lookup_docs Bash
argument-hint: "[task_type: feature|bugfix|refactor|security|review]"
---

Close out the current task end-to-end. Run each step; do NOT skip one that failed — surface the failure and stop.

1. **Validate changed files.** Identify the files you edited this session (git status, your edit history). Call `mcp__nlt-build__tapps_validate_changed` with explicit `file_paths` (comma-separated) scoped to those files. **Never call without `file_paths`.** Default is quick mode. If any file fails, list it with the top blocking issue and stop — the task is not complete. Do not proceed to step 2 until all changed files pass.

""" + _FINISH_TASK_CHECKLIST_AND_DOC_GAPS_CLAUDE + """

4. **Save learnings (conditional).** If this session produced a non-obvious architectural or pattern-level decision — a new convention, a subtle trade-off, a gotcha someone else would re-discover — run `uv run tapps-mcp memory save --key <slug> --tier <architectural|pattern> --value "<concise decision>"` (CLI via BrainBridge). Skip for routine fixes, refactors where the code documents the decision, or trivial bugfixes. Brain offline → skip silently.

5. **Report.** Emit a one-line summary: `Files validated: N pass. Checklist: <task_type> complete. Doc gaps: cleared|none. Memory saved: yes|no.` If any step failed or was skipped, say so explicitly.

6. **Transfer (optional).** If the user is ending the chat and wants the next session to pick up cleanly, invoke `/tapps-handoff-session` instead of pasting a long prompt.
""",
    "tapps-handoff-session": """\
---
name: tapps-handoff-session
user-invocable: true
model: claude-haiku-4-5-20251001
description: >-
  Write a structured cross-session handoff and close the TAPPS session
  lifecycle so the next chat can continue without a long paste. Use when
  ending a session, handing off to a fresh chat, or the user says hand
  off, save session state, or continue next time.
allowed-tools: mcp__nlt-memory__tapps_handoff_save mcp__nlt-build__tapps_session_start Bash
argument-hint: "[optional Linear issue id e.g. TAP-1234]"
disable-model-invocation: true
---

End the session with a durable handoff the next chat can load via `/tapps-continue-session`.

""" + _HANDOFF_PRE_GATE + """

1. **Draft handoff (5–10 bullets).** From this session's work, write:
   - **Done** — what shipped or was verified
   - **Open** — in-progress or untested
   - **Next (P0)** — one concrete next action (plain prose)
   - **Blockers** — `- none` when clear
   - **Changed files** — optional; top paths from `git status --short`
   - **Verify** — commands to run first in the next session
   - **Success criterion** — one line

""" + _HANDOFF_P0_GATE + """

""" + _HANDOFF_MARKDOWN_SHAPE + """

""" + _HANDOFF_PERSIST + """

3. **Report.** One line: `Handoff written: .tapps-mcp/session-handoff.md. Linear P0: <id|none>. brain_mirror: ok|skipped. session_end: ok|skipped. Next session: invoke /tapps-continue-session`
""",
    "tapps-continue-session": """\
---
name: tapps-continue-session
user-invocable: true
model: claude-haiku-4-5-20251001
description: >-
  Bootstrap a fresh session from the last handoff by reading session-handoff.md,
  optional Linear context, and TAPPS session start — without pasting a long
  manifesto. Use when the user says continue, pick up where we left off, resume,
  or start a new session on an existing task (optional TAP-#### argument).
allowed-tools: mcp__nlt-build__tapps_session_start mcp__plugin_linear_linear__get_issue Bash Read
argument-hint: "[optional Linear issue id e.g. TAP-1234]"
---

Start work in a fresh context window by assembling structured state — not a user paste.

1. **Session bootstrap.**
   - **Preferred:** Call `mcp__nlt-build__tapps_session_start()`. If `data.compaction_rehydration` is present, summarize it in one sentence.
   - **CLI fallback** (MCP unavailable): Run `uv run tapps-mcp doctor --quick` and read `.tapps-mcp.yaml` for project context (quality preset, brain URL, engagement). Proceed without blocking.

""" + _CONTINUE_LOAD_AND_CONTEXT + """

3. **Linear context.**
   - If the user passed `TAP-####` (argument or in handoff **Linear P0**), call `mcp__plugin_linear_linear__get_issue(id=...)`.
   - For backlog/triage without a known id, invoke the `linear-read` skill instead of raw `list_issues` (do not call `list_issues` directly — cache gate).

""" + _CONTINUE_EMIT_AND_PROCEED + """
""",
    "tapps-review-pipeline": """\
---
name: tapps-review-pipeline
user-invocable: true
model: claude-sonnet-4-6
description: >-
  Orchestrate a parallel review-fix-validate pipeline across multiple changed files.
  Spawns tapps-review-fixer agents in worktrees for parallel processing. Use when
  you have multiple changed Python files that need parallel review, scoring, and
  quality gate fixing before declaring work complete.
allowed-tools: mcp__nlt-build__tapps_validate_changed mcp__nlt-build__tapps_checklist
context: fork
agent: general-purpose
---

Run a parallel review-fix-validate pipeline on changed Python files:

1. Call `mcp__nlt-build__tapps_session_start` if not already called
2. Determine scope: detect changed Python files via git diff or accept a file list
3. For each file (or batch of files), spawn a `tapps-review-fixer` agent in a worktree:
   - Use the Task tool with `subagent_type: "general-purpose"` and `isolation: "worktree"`
   - Pass the file path and instructions to score, fix, and gate the file
4. Wait for all agents to complete and collect their results
5. Merge any worktree changes back (review diffs before accepting)
6. Call `mcp__nlt-build__tapps_validate_changed` with explicit `file_paths` to verify all files pass
7. Call `mcp__nlt-build__tapps_checklist(task_type="review")` for final verification
8. Present a summary table: file | before score | after score | gate | fixes applied
""",
    "tapps-research": """\
---
name: tapps-research
user-invocable: true
description: >-
  Look up library documentation and research best practices
  for the technologies used in this project. Use when writing code that uses
  an external library or when you need API reference or version-specific guidance.
allowed-tools: mcp__nlt-build__tapps_lookup_docs
argument-hint: "[library] [topic]"
context: fork
model: claude-sonnet-4-6
---

Look up library documentation using TappsMCP:

1. Call `mcp__nlt-build__tapps_lookup_docs` with the library name and topic
2. If coverage is incomplete, call `mcp__nlt-build__tapps_lookup_docs` with a more specific topic
3. Synthesize findings into a clear, actionable answer with code examples
4. Include API signatures and usage patterns from the documentation
5. Suggest follow-up lookups if additional coverage is needed
""",
    "tapps-security": """\
---
name: tapps-security
user-invocable: true
model: claude-sonnet-4-6
description: >-
  Run a comprehensive security audit including vulnerability scanning
  and dependency CVE checks. Use when reviewing security-sensitive changes,
  before a security audit, or before a production release.
allowed-tools: >-
  mcp__nlt-build__tapps_security_scan
  mcp__nlt-build__tapps_dependency_scan
argument-hint: "[file-path]"
---

Run a comprehensive security audit using TappsMCP:

1. Call `mcp__nlt-build__tapps_security_scan` on the target file to detect vulnerabilities
2. Call `mcp__nlt-build__tapps_dependency_scan` to check for known CVEs in dependencies
3. Group all findings by severity (critical, high, medium, low)
4. Suggest a prioritized fix order starting with the highest-severity issues
""",
    "tapps-memory": """\
---
name: tapps-memory
user-invocable: true
model: claude-sonnet-4-6
description: >-
  Manage shared project memory via tapps-mcp CLI and session notes.
  Use when saving cross-session decisions, searching prior patterns, or
  checking brain bridge health. For chat handoffs use tapps-handoff-session.
allowed-tools: mcp__nlt-build__tapps_session_start mcp__nlt-memory__tapps_session_notes Bash
argument-hint: "[save|search|get] [key]"
---

`tapps_memory` on the **`nlt-memory`** MCP server is a slim facade (TAP-3895). Default consumer path is **`uv run tapps-mcp memory`** (bridge-only — never add direct `tapps-brain` to `.mcp.json`).

## Routing guide

| Need | Path |
|------|------|
| Cross-chat handoff | `/tapps-handoff-session` then `/tapps-continue-session` (`.tapps-mcp/session-handoff.md` is canonical) |
| Session-local notes | `mcp__nlt-memory__tapps_session_notes(action="save", ...)` |
| Save / recall / search brain | `uv run tapps-mcp memory <subcommand>` (CLI via BrainBridge) |
| Brain health before writes | `mcp__nlt-build__tapps_session_start()` → `data.brain_bridge_health` |
| Auto-recall at session start | Hooks run `tapps-mcp memory recall` — usually no manual step |

## Shell auth (CLI memory)

CLI reads brain auth from shell env (see `docs/operations/CONSUMER-REPO-BRAIN-WIRING.md`):
- `TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN` or `TAPPS_BRAIN_AUTH_TOKEN`
- `TAPPS_MCP_MEMORY_BRAIN_HTTP_URL` or `.tapps-mcp.yaml` → `memory.brain_http_url`

## Decide: should I write to memory?

```
Did the user teach a non-obvious rule?              → YES (save)
Was a decision made WITH RATIONALE that isn't       → YES (architectural / pattern)
  obvious from the code or the PR body?
Did a debug session reveal a subtle invariant?      → YES (pattern, tag: critical)
Is this a TODO / next-step / "remember to do X"?    → NO (use handoff skill or TodoWrite)
Is this re-derivable by reading the repo?           → NO
Does this duplicate a CHANGELOG / CLAUDE.md entry?  → NO
```

## Do NOT save

- Code patterns / file paths / module layout — derivable by reading the repo
- Git history, recent diffs, who-changed-what — `git log` / `git blame` are authoritative
- Ephemeral task state, debug fix recipes — use `tapps_session_notes` or the commit message
- Anything with secrets, tokens, or PII

## Pick a tier (when saving)

| Tier | Half-life | What it's for |
|---|---|---|
| `architectural` | 180d | System decisions, tech-stack choices, infra contracts |
| `pattern` | 60d | Coding conventions, API shapes, design patterns |
| `procedural` | 30d | Workflows, build/deploy commands, runbooks |
| `context` | 14d | Session-scope facts; use sparingly |

Tag important entries with `critical` or `security` via `--tags`.

## CLI commands (daily drivers)

```bash
uv run tapps-mcp memory save --key my-decision --tier architectural --value "..." --tags critical
uv run tapps-mcp memory get --key my-decision
uv run tapps-mcp memory search --query "auth pattern" --json
uv run tapps-mcp memory list --json
uv run tapps-mcp memory export --file memories.json
```

## Advanced surface

Federation, hive, knowledge graph, and batch ops: see `docs/MEMORY_REFERENCE.md`. **Consumer repo agents use CLI + docs**.

## See also

- `docs/MEMORY_REFERENCE.md` — full legacy action map and brain-health diagnostics
- `docs/operations/CONSUMER-REPO-BRAIN-WIRING.md` — bridge-only checklist and shell auth
""",
    "tapps-tool-reference": """\
---
name: tapps-tool-reference
user-invocable: true
model: claude-haiku-4-5-20251001
description: >-
  Look up when to use each TappsMCP tool. Full tool reference with per-tool
  guidance for session start, scoring, validation, checklist, docs, experts, and more.
  Use when you need guidance on which TappsMCP tool to call for a given situation.
allowed-tools: mcp__nlt-setup__tapps_server_info
argument-hint: "[tool-name or 'all']"
---

When the user asks about TappsMCP tools (e.g. "when do I use tapps_score_file?",
"what tools does TappsMCP have?", "tapps_quick_check vs tapps_quality_gate"),
provide the full tool reference from this skill.

## Essential tools (always-on workflow)
| Tool | When to use it |
|------|----------------|
| **tapps_session_start** | **FIRST call in every session** - returns server info only |
| **tapps_quick_check** | **After editing any Python file** - quick score + gate + basic security |
| **tapps_validate_changed** | **Before multi-file complete** - score + gate on changed files. Always pass explicit `file_paths`. Default is quick; `quick=false` is a last resort. |
| **tapps_checklist** | **Before declaring complete** - reports which tools were called |
| **tapps_quality_gate** | Before declaring work complete - ensures file passes preset |

## Scoring & quality
| Tool | When to use it |
|------|----------------|
| **tapps_score_file** | When editing/reviewing - use quick=True during edit loops |
| **tapps_server_info** | At session start - discover version, tools, recommended workflow |

## Documentation & experts
| Tool | When to use it |
|------|----------------|
| **tapps_lookup_docs** | Before writing code using an external library |

## Project & memory
| Tool / path | When to use it |
|------|----------------|
| **`tapps-mcp memory` CLI** | Save/search/get architectural or pattern decisions (`memory save`, `search`, `get`) |
| **tapps_session_notes** | Session-local notes during the chat |
| **tapps-handoff-session / tapps-continue-session** | Cross-chat transfer via `.tapps-mcp/session-handoff.md` |
| **tapps_session_start** | `brain_bridge_health` before memory writes; hooks auto-recall |

## Validation & analysis
| Tool | When to use it |
|------|----------------|
| **tapps_security_scan** | Security-sensitive changes or before security review |
| **tapps_validate_config** | When adding/changing Dockerfile, docker-compose, infra |
| **tapps_impact_analysis** | Before modifying a file's public API |
| **tapps_dead_code** | Find unused code during refactoring |
| **tapps_dependency_scan** | Check for CVEs before releases |
| **tapps_dependency_graph** | Understand module dependencies, circular imports |

## Pipeline & init
| Tool | When to use it |
|------|----------------|
| **tapps_init** | Pipeline bootstrap (once per project) - creates AGENTS.md, rules, hooks, MCP config (default). **CLI fallback:** `tapps-mcp upgrade --force --host auto` then `tapps-mcp doctor` |
| **tapps_upgrade** | After TappsMCP version update - refreshes generated files |
| **tapps_doctor** | Diagnose configuration issues |
| **tapps_set_engagement_level** | Change enforcement intensity (high/medium/low) |

Use `tapps_server_info` for the latest recommended workflow string.
""",
    "tapps-init": """\
---
name: tapps-init
user-invocable: true
model: claude-sonnet-4-6
description: >-
  Bootstrap TappsMCP in a project. Creates AGENTS.md, TECH_STACK.md,
  platform rules, hooks, agents, skills, and MCP config. Use when setting
  up TappsMCP in a new or existing project for the first time.
allowed-tools: mcp__nlt-setup__tapps_init mcp__nlt-setup__tapps_doctor
argument-hint: "[project-root]"
---

Bootstrap TappsMCP in a new or existing project:

1. Call `mcp__nlt-setup__tapps_init` to run the full bootstrap pipeline (`mcp_config` defaults true)
2. Check the response for `content_return: true` — if present, the server could not
   write files directly (Docker / read-only mount).  Apply the files from
   `file_manifest.files[]` using the Write tool.  See `/tapps-apply-files` for details.
3. If files were written directly, review the created files (AGENTS.md, TECH_STACK.md, platform rules, hooks, MCP config)
4. Confirm MCP config lists tapps-mcp only (no direct tapps-brain entry — bridge-only)
5. If any issues are reported, call `mcp__nlt-setup__tapps_doctor` to diagnose
6. Verify that `.claude/settings.json` has MCP tool auto-approval rules
7. For shared-brain HTTP wiring, see docs/operations/CONSUMER-REPO-BRAIN-WIRING.md
8. Confirm the project is ready for the TappsMCP quality workflow

**If `tapps_init` is not available** (server not in available MCP servers), use the CLI:
1. Run from the project root: `tapps-mcp upgrade --force --host auto`
2. Then verify: `tapps-mcp doctor`
3. Restart your MCP host to pick up the new config
""",
    "tapps-upgrade": """\
---
name: tapps-upgrade
user-invocable: true
model: claude-sonnet-4-6
description: >-
  Upgrade tapps-mcp / docs-mcp in this project to the latest version.
  Reinstalls global CLIs, restarts the MCP servers, refreshes scaffolding
  via `tapps-mcp upgrade` (dry-run preview + timestamped backup), and
  verifies via doctor + checklist. Use when a new tapps-mcp or docs-mcp
  version is available and the project scaffolding needs to be refreshed.
allowed-tools: Bash mcp__nlt-build__tapps_session_start mcp__nlt-setup__tapps_doctor mcp__nlt-build__tapps_checklist
argument-hint: "[--from-checkout <path> | --from-tag vX.Y.Z]"
---

Upgrade tapps-mcp / docs-mcp end-to-end. The user's request to upgrade is standing authorization for the full pipeline — do NOT pause mid-flow.

**Pick an install source from the prompt:**

- Local checkout (`--from-checkout <path>` or user mentions a local clone):
  `uv tool install --reinstall --from <path>/packages/tapps-mcp tapps-mcp`
  and the same for `docs-mcp`.
- Git tag (`--from-tag vX.Y.Z`):
  `uv tool install --reinstall "git+https://github.com/wtthornton/tapps-mcp.git@vX.Y.Z#subdirectory=packages/tapps-mcp" tapps-mcp`
  and the same for `docs-mcp`.
- If neither is specified, ASK once which to use.

**Steps:**

1. **Reinstall global CLIs.** Run both `uv tool install --reinstall ...` commands. Verify: `uv tool list | grep -E '(tapps-mcp|docs-mcp)'` — both must show the same version.
2. **Restart MCP servers.** The running processes still hold old code. Tell the user to exit/reopen (or `/mcp` reconnect), then re-invoke this skill. Stop here on the first invocation.
3. **Verify new version is live.** Call `mcp__nlt-build__tapps_session_start(force=true)`. Confirm `server.version` matches target and `diagnostics.install_drift.drift_detected == false`. If drift persists, the server wasn't restarted — go back to step 2.
4. **Dry-run the scaffolding refresh.** Run `tapps-mcp upgrade --dry-run`. Review the diff for AGENTS.md, CLAUDE.md, .claude/hooks/, .claude/rules/, .claude/agents/, .claude/skills/, .mcp.json. The smart-merge preserves customizations in non-canonical sections; canonical sections are replaced wholesale. Pause if a customized canonical section will be overwritten.
5. **Apply the upgrade.** Run `tapps-mcp upgrade` (writes timestamped backup to `.tapps-mcp/backups/<ts>/`).
6. **Verify.** Run `tapps-mcp doctor` AND `mcp__nlt-build__tapps_checklist(task_type="upgrade")`. Surface any problems — do not declare done on a failure.
7. **Report.** One-line summary: `Upgraded: tapps-mcp X.Y.Z, docs-mcp X.Y.Z. Scaffolding: N files. Doctor: OK. Checklist: complete. Backup: .tapps-mcp/backups/<ts>/`.

**Rollback (only if step 5/6 broke something):** `tapps-mcp rollback` restores from the most recent backup. Do NOT roll back "to be safe" after a clean run.

**Do NOT:**

- Publish to PyPI / npm — tapps-mcp is local-install only.
- Bump versions in the tapps-mcp dev repo itself — separate workflow.
- Touch tapps-brain — separate Docker service with its own release flow.
- Add `tapps-brain` as a top-level `.mcp.json` entry — it's bridge-only via tapps-mcp's BrainBridge.
""",
    "tapps-engagement": """\
---
name: tapps-engagement
user-invocable: true
model: claude-haiku-4-5-20251001
description: >-
  Change the TappsMCP enforcement intensity (high, medium, or low).
  Controls which quality tools are mandatory vs optional. Use when you want
  to switch between strict, balanced, or advisory enforcement modes.
allowed-tools: mcp__nlt-setup__tapps_set_engagement_level
argument-hint: "[high|medium|low]"
disable-model-invocation: true
---

Set the TappsMCP LLM engagement level:

1. Call `mcp__nlt-setup__tapps_set_engagement_level` with the desired level
2. **high** - All quality tools are mandatory; checklist enforces strict compliance
3. **medium** - Balanced enforcement; core tools required, advanced tools recommended
4. **low** - Optional guidance; quality tools are suggestions, not requirements
5. Confirm the level was saved to `.tapps-mcp.yaml`
6. If `content_return: true`, write `.tapps-mcp.yaml` from `file_manifest` using the Write tool
""",
    "tapps-apply-files": """\
---
name: tapps-apply-files
user-invocable: false
model: claude-haiku-4-5-20251001
description: >-
  Apply file operations from a TappsMCP content-return response. Use when
  a TappsMCP or DocsMCP tool returns content_return: true with a file_manifest
  because the server runs in Docker and cannot write files directly.
allowed-tools: ""
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

**Response structure:**
```
{
  "content_return": true,
  "file_manifest": {
    "mode": "content_return",
    "reason": "...",
    "summary": "...",
    "file_count": N,
    "files": [
      {"path": "relative/path", "content": "...", "mode": "create|overwrite|merge",
       "encoding": "utf-8", "description": "...", "priority": 5}
    ],
    "agent_instructions": {
      "persona": "...",
      "tool_preference": "...",
      "verification_steps": ["..."],
      "warnings": ["..."]
    }
  }
}
```
""",
    "linear-issue": """\
---
name: linear-issue
user-invocable: true
model: claude-haiku-4-5-20251001
description: Create, lint, validate, or triage Linear issues and epics for agents. MANDATORY for all Linear writes — never call plugin save_issue directly. Routes to docs-mcp generator/validator/triage tools and the Linear plugin by user intent. Use when creating, linting, validating, or triaging a Linear issue or epic.
allowed-tools: mcp__nlt-linear-issues__docs_generate_epic mcp__nlt-linear-issues__docs_generate_story mcp__nlt-linear-issues__docs_lint_linear_issue mcp__nlt-linear-issues__docs_validate_linear_issue mcp__nlt-linear-issues__docs_linear_triage mcp__nlt-linear-issues__docs_save_linear_issue mcp__plugin_linear_linear__save_issue mcp__plugin_linear_linear__get_issue mcp__plugin_linear_linear__list_issues mcp__nlt-linear-issues__tapps_linear_snapshot_get mcp__nlt-linear-issues__tapps_linear_snapshot_put mcp__nlt-linear-issues__tapps_linear_snapshot_invalidate
argument-hint: "[create-epic|create-story|lint TAP-###|validate|triage] [free-form detail]"
---

Work with Linear issues for AI-agent consumption. Infer intent from the user's prompt and act autonomously within scope — see `autonomy.md`. The user's original request is the authorization for the full generator → validator → save_issue chain; do NOT pause mid-flow to ask "should I create this?"

**When to invoke this skill:** ANY request that will create, update, or validate a Linear issue or epic. This includes "file a ticket", "create an issue", "open an epic", "track this as a story", or "add a bug report to Linear". Raw `save_issue` calls are a rule violation — route through this skill.

**Assignee — agent, not human (applies to every write below).** Resolve the agent user once per session via `mcp__plugin_linear_linear__list_users`, picking the user whose `name`/`displayName`/`email` matches `agent`, `bot`, `tapps`, `claude`, or `agent_user` in `.tapps-mcp.yaml`. Cache the id. Pass `assignee="<agent-user-id-or-name>"` on every `save_issue`. If no agent user exists, leave `assignee` unset — never fall back to the OAuth user (the human running the session). Only override when the user explicitly names a person.

**Create an epic** (prompt names multiple stories, or "epic", or spans a cross-cutting initiative):
1. Call `mcp__nlt-linear-issues__docs_generate_epic` with the user's ask. Required: `title`, `purpose_and_intent` ("We are doing this so that ..."), `goal`, `motivation`, `acceptance_criteria`, `stories` (JSON array). Optional: `priority`, `estimated_loe`, `references`, `non_goals`.
2. Use `data.content` from the generator response (default `write_to_disk=false` — no repo file). Do NOT read epic markdown from disk.
3. Build the Linear-body markdown following the 5-to-7 section epic shape: `## Purpose & Intent`, `## Goal`, `## Motivation`, `## Acceptance Criteria`, `## Stories`, `## Out of Scope`, `## Refs`.
4. Validate via `mcp__nlt-linear-issues__docs_validate_linear_issue(title, description, priority, is_epic=true)`. Target score 100 / `agent_ready=true`.
5. Call `mcp__nlt-linear-issues__docs_save_linear_issue(title=<title>, description=<description>)` as the server-side pre-save gate (TAP-2009). If `data.ok: true`, call `mcp__plugin_linear_linear__save_issue(team, project, title, description, priority, assignee="<agent-user-id-or-name>", ...)` without `id`. If `data.ok: false`, re-validate per the refusal envelope's `use`/`args` fields then retry this step.
6. Create each child story via the create-story flow below, passing `parent_id=<epic TAP-id>` (each child is also assigned to the agent).
7. After all writes, call `mcp__nlt-linear-issues__tapps_linear_snapshot_invalidate(team, project)`.

**Create a story** (default when prompt describes a single change/bug):
1. Call `mcp__nlt-linear-issues__docs_generate_story` with the user's ask. Required: `title` (<=80 chars, pattern `file.py: symptom`), `files` (comma-separated, each with `:LINE-RANGE`), `acceptance_criteria` (verifiable items).
2. Default `audience="agent"` emits the 5-section Linear template (What/Where/Why/Acceptance/Refs) and round-trips through the validator.
3. If the call returns `INPUT_INVALID`, refine the inputs per the error message and retry. Do NOT pass `audience="human"` unless the user asks for a product-review doc.
4. Call `mcp__nlt-linear-issues__docs_save_linear_issue(title=<title>, description=<description>)` as the server-side pre-save gate (TAP-2009). If `data.ok: true`, call `mcp__plugin_linear_linear__save_issue(..., assignee="<agent-user-id-or-name>", parent_id=<epic-id-if-any>)`. If `data.ok: false`, re-validate with `docs_validate_linear_issue` per the refusal envelope's `use`/`args` fields, then retry this step.
5. After `save_issue` returns, call `mcp__nlt-linear-issues__tapps_linear_snapshot_invalidate(team=<team>, project=<project>)` to evict stale cached snapshots for that slice.

**Lint** an existing issue (prompt like "lint TAP-686", "check TAP-###"):
1. Fetch via `mcp__plugin_linear_linear__get_issue`.
2. Pass title/description/labels/priority/estimate to `mcp__nlt-linear-issues__docs_lint_linear_issue`.
3. Surface score, findings (with fix_hints), and reclaimable noise bytes. For each HIGH severity finding, quote the suggested fix.

**Validate** before creating or after editing (prompt like "is this agent-ready?"):
1. Call `mcp__nlt-linear-issues__docs_validate_linear_issue` with the payload.
2. Report `{agent_ready, score, missing[]}`. Missing items are blockers; propose a concrete fix per item.

**Triage** a batch (prompt like "triage open issues", "find label gaps"):
1. If the user names a specific issue (e.g. "triage TAP-686"), use `mcp__plugin_linear_linear__get_issue(id="TAP-686")` — skip list/cache entirely.
2. **Cache-first read:** call `mcp__nlt-linear-issues__tapps_linear_snapshot_get(team=<team>, project=<project>, state="backlog" | "unstarted", label?)`. If `data.cached` is `true`, use `data.issues` directly — Linear was not called.
3. **On cache miss** (`data.cached` is `false`): call `mcp__plugin_linear_linear__list_issues` with narrow filters — `team`, `project`, `state`, `includeArchived=false` (never call without filters). Then populate the cache by calling `mcp__nlt-linear-issues__tapps_linear_snapshot_put(team, project, issues_json=json.dumps(response.issues), state, label?)` using the **same** team/project/state/label/limit as the get call so the keys align.
4. Pass the list to `mcp__nlt-linear-issues__docs_linear_triage`.
5. Apply label_proposals, parent_groupings, and metadata_gaps via Linear plugin writes (each `save_issue` carries `assignee="<agent-user-id-or-name>"` for any newly-owned items). No mid-flow user confirmation; the triage request is the authorization.
6. After any write, call `mcp__nlt-linear-issues__tapps_linear_snapshot_invalidate(team=<team>, project=<project>)` to refresh the cache on next read.

Rules (enforced by docs-mcp tools):
- Title <=80 chars; no em-dash preambles.
- Inline-code filenames (`AGENTS.md`), never `[AGENTS.md](AGENTS.md)` (Linear's autolinker mangles).
- Bare `TAP-###` refs, never `<issue id="UUID">TAP-###</issue>` wrappers.
- `## Acceptance` has at least one verifiable `- [ ]` item.
- `## Where` includes at least one `path/to/file.ext:LINE-RANGE` anchor.

Linear rendering workarounds (observed 2026-04-24):
- **Use numbered lists, not bulleted lists, in `## Where` and `## Acceptance` when items reference file paths.** Linear's markdown engine silently drops multiple bulleted `* path/...` entries (appears to dedupe on auto-linked filenames, especially `.md` files), keeping only the first. Numbered lists (`1.`, `2.`, ...) survive.
- **Wrap file paths in backticks** when they appear in list items: `` `path/to/file.py:1-100` `` rather than bare `path/to/file.py:1-100`. Prevents auto-linking that contributes to the dedupe bug.
- **Avoid raw `.md` filenames in bulleted prose.** Refer to "the agents-md template" or "the claude-md file" when the plain word would trigger auto-linking in a context that loses data. Inline-code with backticks is safe.
- **Tables with multiple columns** are fragile in Linear; prefer numbered lists with `—` separators for compact multi-field rows.
""",
    "linear-read": """\
---
name: linear-read
user-invocable: true
model: claude-haiku-4-5-20251001
description: Read multi-issue Linear data via cache-first dance. MANDATORY for any list-style Linear read. Routes through tapps_linear_snapshot_get/put before list_issues. Use when listing, filtering, or reviewing Linear issues (backlog review, "what's open", triage, "find issues assigned to X"). Single-issue lookups go straight to get_issue instead.
allowed-tools: mcp__nlt-linear-issues__tapps_linear_snapshot_get mcp__nlt-linear-issues__tapps_linear_snapshot_put mcp__nlt-linear-issues__tapps_linear_list_issues mcp__plugin_linear_linear__list_issues mcp__plugin_linear_linear__get_issue
argument-hint: "[free-form query, e.g. 'open issues in TAP', 'backlog assigned to me']"
---

Multi-issue Linear reads are cache-first by contract (TAP-967 audit found 5,368 `list_issues` calls with 0.26% cache adoption — soft rules failed; this skill is the routed path the agent reaches for instead). Invoke ANY time the user asks for a list, batch, or filtered view of Linear issues.

**When to invoke this skill:** "list Linear issues", "what's open in TAP", "find issues assigned to X", "review the backlog", "show me high-priority bugs", "what's in flight", "triage" (also routes through `linear-issue`). Do NOT invoke for single-issue lookups when the user has an issue id (e.g. "what's TAP-686 about?") — go straight to `mcp__plugin_linear_linear__get_issue(id="TAP-686")`.

**Core flow — every multi-issue read goes through these four steps in order:**

1. **`tapps_linear_snapshot_get(team, project, state, label?)` first.** Pass the same `state`, `label`, and `limit` you would pass to `list_issues`. State buckets the cache TTL (5 min for `open`/`unstarted`/`started`, 1 h for `completed`/`canceled`).
2. **On `cached=true`**, use `data.issues` and filter in-memory for the rest of the user's question — `list_issues` is NOT called. Project the fields you need with a list comprehension; do not re-query.
3. **On `cached=false`**, call `mcp__nlt-linear-issues__tapps_linear_list_issues(team, project, state, label?, limit?)` as a gate check (TAP-2010 server-side defence-in-depth).
   - On `ok=true`: proceed to call `mcp__plugin_linear_linear__list_issues` with NARROW filters: `team`, `project`, `state`, `includeArchived=false`. Never call without filters; never call with only `team` + `limit:250`.
   - On `ok=false` (gate miss): follow the `hint` — call `tapps_linear_snapshot_get` first, then re-check.
4. **Immediately after the miss-fetch**, populate the cache via `tapps_linear_snapshot_put(team, project, issues_json=json.dumps(issues), state, label?, limit?)` using the **same** key dimensions as the get call so the keys align.

**The 6-poll kickoff antipattern (the single biggest source of TAP-967's call volume):**

A common bad pattern is firing six sequential `list_issues` calls — `(state="Backlog", priority=1)`, `(Backlog, p2)`, `(Backlog, p3)`, `(Backlog, p4)`, `In Progress`, `Todo` — to assemble a session-start summary. Don't. Instead:

```
snap = tapps_linear_snapshot_get(team=<team>, project=<project>, state="open")
# on cache hit, use snap.data.issues directly; on miss, fetch once with state="open" then put.
issues = snap.data.issues
backlog_p1 = [i for i in issues if i["state"]["name"] == "Backlog" and i.get("priority", {}).get("value") == 1]
in_progress = [i for i in issues if i["state"]["type"] == "started"]
# ...etc, all from one snapshot.
```

One snapshot_get on `state="open"` covers Backlog + In Progress + Todo + Triage + Unstarted. The 5-minute TTL means the next session warms instantly — six API calls become zero.

**Status-bucket sweep (also a TAP-967 antipattern):**

Three sequential `list_issues({state: "backlog"})`, `({state: "unstarted"})`, `({state: "started"})` calls collapse to one `snapshot_get(state="open")` plus an in-memory filter on `state.type`.

**Other read shapes — same four-step flow:**

- **Filter by parent epic:** call `list_issues(parentId="TAP-1078")` directly on cache miss; pass the same parentId to `snapshot_put` as the `label` slot if you need a finer cache key. For most parent-epic reads, snapshot the broader `(team, project, state="open")` slice and filter in memory by `parent.id`.
- **Filter by assignee:** snapshot the team/state slice, filter `i["assignee"]["name"] == "X"` in memory.
- **Recent activity:** if you need `updatedAt=-P7D`, do the snapshot first; if the cache is < 5 min old, the `updatedAt` filter is a memory-side comprehension.

**After any Linear write** (from `linear-issue` or `linear-release-update` skills), call `mcp__nlt-linear-issues__tapps_linear_snapshot_invalidate(team, project)` so the next read returns fresh data. This skill itself does not write.

**Anti-patterns — do not do these:**

- Calling `list_issues` without a prior `snapshot_get` for the same key.
- Calling `list_issues({})` or `list_issues({team: "TAP", limit: 250})` (the unfiltered scroll — TAP-967's worst offender).
- Re-fetching the same narrow query 5-12 times in one assistant turn with no intervening writes (use the cache).
- Single-issue lookup via `list_issues` filtering — use `get_issue(id)` instead.

**Linear plugin parameter cheatsheet** (the flat parameters cover almost every real query — there is no need for raw GraphQL filter shapes):

- `team` — team name or ID, required for any narrow filter
- `project` — project name, ID, or slug
- `state` — state type (`triage`/`backlog`/`unstarted`/`started`/`completed`/`canceled`) or state name (`Backlog`/`Done`/...). The bucketed states (`open`, `closed`) are tapps-mcp cache keys, not Linear states.
- `assignee` — user ID, name, email, or `me`. `null` for unassigned.
- `parentId` — parent issue ID (e.g. `TAP-1078`)
- `label` — label name or ID
- `priority` — `0`=None, `1`=Urgent, `2`=High, `3`=Normal, `4`=Low
- `updatedAt` / `createdAt` — ISO-8601 date or duration (`-P7D`)
- `query` — full-text search across title and description
- `includeArchived` — default `true`; pass `false` to skip archived
- `limit` — max 250
""",
    "continuous-learning-v2": """\
---
name: continuous-learning-v2
user-invocable: true
description: Instinct-based learning system that observes sessions via hooks, creates atomic instincts with confidence scoring, and evolves them into skills/commands/agents. v2.1 adds project-scoped instincts to prevent cross-project contamination.
origin: ECC
version: 2.1.0
model: claude-sonnet-4-6
---

# Continuous Learning v2.1 - Instinct-Based Architecture

An advanced learning system that turns your Claude Code sessions into reusable knowledge through atomic "instincts" - small learned behaviors with confidence scoring.

**v2.1** adds **project-scoped instincts** — React patterns stay in your React project, Python conventions stay in your Python project, and universal patterns (like "always validate input") are shared globally.

## When to Activate

- Setting up automatic learning from Claude Code sessions
- Configuring instinct-based behavior extraction via hooks
- Tuning confidence thresholds for learned behaviors
- Reviewing, exporting, or importing instinct libraries
- Evolving instincts into full skills, commands, or agents
- Managing project-scoped vs global instincts
- Promoting instincts from project to global scope

## What's New in v2.1

| Feature | v2.0 | v2.1 |
|---------|------|------|
| Storage | Global (~/.claude/homunculus/) | Project-scoped (projects/<hash>/) |
| Scope | All instincts apply everywhere | Project-scoped + global |
| Detection | None | git remote URL / repo path |
| Promotion | N/A | Project → global when seen in 2+ projects |
| Commands | 4 (status/evolve/export/import) | 6 (+promote/projects) |
| Cross-project | Contamination risk | Isolated by default |

## What's New in v2 (vs v1)

| Feature | v1 | v2 |
|---------|----|----|
| Observation | Stop hook (session end) | PreToolUse/PostToolUse (100% reliable) |
| Analysis | Main context | Background agent (Haiku) |
| Granularity | Full skills | Atomic "instincts" |
| Confidence | None | 0.3-0.9 weighted |
| Evolution | Direct to skill | Instincts -> cluster -> skill/command/agent |
| Sharing | None | Export/import instincts |

## The Instinct Model

An instinct is a small learned behavior:

```yaml
---
id: prefer-functional-style
trigger: "when writing new functions"
confidence: 0.7
domain: "code-style"
source: "session-observation"
scope: project
project_id: "a1b2c3d4e5f6"
project_name: "my-react-app"
---

# Prefer Functional Style

## Action
Use functional patterns over classes when appropriate.

## Evidence
- Observed 5 instances of functional pattern preference
- User corrected class-based approach to functional on 2025-01-15
```

**Properties:**
- **Atomic** -- one trigger, one action
- **Confidence-weighted** -- 0.3 = tentative, 0.9 = near certain
- **Domain-tagged** -- code-style, testing, git, debugging, workflow, etc.
- **Evidence-backed** -- tracks what observations created it
- **Scope-aware** -- `project` (default) or `global`

## How It Works

```
Session Activity (in a git repo)
      |
      | Hooks capture prompts + tool use (100% reliable)
      | + detect project context (git remote / repo path)
      v
+---------------------------------------------+
|  projects/<project-hash>/observations.jsonl  |
|   (prompts, tool calls, outcomes, project)   |
+---------------------------------------------+
      |
      | Observer agent reads (background, Haiku)
      v
+---------------------------------------------+
|          PATTERN DETECTION                   |
|   * User corrections -> instinct             |
|   * Error resolutions -> instinct            |
|   * Repeated workflows -> instinct           |
|   * Scope decision: project or global?       |
+---------------------------------------------+
      |
      | Creates/updates
      v
+---------------------------------------------+
|  projects/<project-hash>/instincts/personal/ |
|   * prefer-functional.yaml (0.7) [project]   |
|   * use-react-hooks.yaml (0.9) [project]     |
+---------------------------------------------+
|  instincts/personal/  (GLOBAL)               |
|   * always-validate-input.yaml (0.85) [global]|
|   * grep-before-edit.yaml (0.6) [global]     |
+---------------------------------------------+
      |
      | /evolve clusters + /promote
      v
+---------------------------------------------+
|  projects/<hash>/evolved/ (project-scoped)   |
|  evolved/ (global)                           |
|   * commands/new-feature.md                  |
|   * skills/testing-workflow.md               |
|   * agents/refactor-specialist.md            |
+---------------------------------------------+
```

## Project Detection

The system automatically detects your current project:

1. **`CLAUDE_PROJECT_DIR` env var** (highest priority)
2. **`git remote get-url origin`** -- hashed to create a portable project ID (same repo on different machines gets the same ID)
3. **`git rev-parse --show-toplevel`** -- fallback using repo path (machine-specific)
4. **Global fallback** -- if no project is detected, instincts go to global scope

Each project gets a 12-character hash ID (e.g., `a1b2c3d4e5f6`). A registry file at `~/.claude/homunculus/projects.json` maps IDs to human-readable names.

## Quick Start

### 1. Enable Observation Hooks

Add to your `~/.claude/settings.json`.

**If installed as a plugin** (recommended):

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "${CLAUDE_PLUGIN_ROOT}/skills/continuous-learning-v2/hooks/observe.sh"
      }]
    }],
    "PostToolUse": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "${CLAUDE_PLUGIN_ROOT}/skills/continuous-learning-v2/hooks/observe.sh"
      }]
    }]
  }
}
```

**If installed manually** to `~/.claude/skills`:

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "~/.claude/skills/continuous-learning-v2/hooks/observe.sh"
      }]
    }],
    "PostToolUse": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "~/.claude/skills/continuous-learning-v2/hooks/observe.sh"
      }]
    }]
  }
}
```

### 2. Initialize Directory Structure

The system creates directories automatically on first use, but you can also create them manually:

```bash
# Global directories
mkdir -p ~/.claude/homunculus/{instincts/{personal,inherited},evolved/{agents,skills,commands},projects}

# Project directories are auto-created when the hook first runs in a git repo
```

### 3. Use the Instinct Commands

```bash
/instinct-status     # Show learned instincts (project + global)
/evolve              # Cluster related instincts into skills/commands
/instinct-export     # Export instincts to file
/instinct-import     # Import instincts from others
/promote             # Promote project instincts to global scope
/projects            # List all known projects and their instinct counts
```

## Commands

| Command | Description |
|---------|-------------|
| `/instinct-status` | Show all instincts (project-scoped + global) with confidence |
| `/evolve` | Cluster related instincts into skills/commands, suggest promotions |
| `/instinct-export` | Export instincts (filterable by scope/domain) |
| `/instinct-import <file>` | Import instincts with scope control |
| `/promote [id]` | Promote project instincts to global scope |
| `/projects` | List all known projects and their instinct counts |

## Configuration

Edit `config.json` to control the background observer:

```json
{
  "version": "2.1",
  "observer": {
    "enabled": false,
    "run_interval_minutes": 5,
    "min_observations_to_analyze": 20
  }
}
```

| Key | Default | Description |
|-----|---------|-------------|
| `observer.enabled` | `false` | Enable the background observer agent |
| `observer.run_interval_minutes` | `5` | How often the observer analyzes observations |
| `observer.min_observations_to_analyze` | `20` | Minimum observations before analysis runs |

Other behavior (observation capture, instinct thresholds, project scoping, promotion criteria) is configured via code defaults in `instinct-cli.py` and `observe.sh`.

## Scope Decision Guide

| Pattern Type | Scope | Examples |
|-------------|-------|---------|
| Language/framework conventions | **project** | "Use React hooks", "Follow Django REST patterns" |
| File structure preferences | **project** | "Tests in `__tests__`/", "Components in src/components/" |
| Code style | **project** | "Use functional style", "Prefer dataclasses" |
| Error handling strategies | **project** | "Use Result type for errors" |
| Security practices | **global** | "Validate user input", "Sanitize SQL" |
| General best practices | **global** | "Write tests first", "Always handle errors" |
| Tool workflow preferences | **global** | "Grep before Edit", "Read before Write" |
| Git practices | **global** | "Conventional commits", "Small focused commits" |

## Instinct Promotion (Project -> Global)

When the same instinct appears in multiple projects with high confidence, it's a candidate for promotion to global scope.

**Auto-promotion criteria:**
- Same instinct ID in 2+ projects
- Average confidence >= 0.8

**How to promote:**

```bash
# Promote a specific instinct
python3 instinct-cli.py promote prefer-explicit-errors

# Auto-promote all qualifying instincts
python3 instinct-cli.py promote

# Preview without changes
python3 instinct-cli.py promote --dry-run
```

The `/evolve` command also suggests promotion candidates.

## Confidence Scoring

| Score | Meaning | Behavior |
|-------|---------|----------|
| 0.3 | Tentative | Suggested but not enforced |
| 0.5 | Moderate | Applied when relevant |
| 0.7 | Strong | Auto-approved for application |
| 0.9 | Near-certain | Core behavior |

**Confidence increases** when:
- Pattern is repeatedly observed
- User doesn't correct the suggested behavior
- Similar instincts from other sources agree

**Confidence decreases** when:
- User explicitly corrects the behavior
- Pattern isn't observed for extended periods
- Contradicting evidence appears

## Why Hooks vs Skills for Observation?

> "v1 relied on skills to observe. Skills are probabilistic -- they fire ~50-80% of the time based on Claude's judgment."

Hooks fire **100% of the time**, deterministically. This means:
- Every tool call is observed
- No patterns are missed
- Learning is comprehensive

## Backward Compatibility

v2.1 is fully compatible with v2.0 and v1:
- Existing global instincts in `~/.claude/homunculus/instincts/` still work as global instincts
- Existing `~/.claude/skills/learned/` skills from v1 still work
- Stop hook still runs (but now also feeds into v2)
- Gradual migration: run both in parallel

## Privacy

- Observations stay **local** on your machine
- Project-scoped instincts are isolated per project
- Only **instincts** (patterns) can be exported — not raw observations
- No actual code or conversation content is shared
- You control what gets exported and promoted
""",
    "linear-release-update": """\
---
name: linear-release-update
user-invocable: true
model: claude-haiku-4-5-20251001
description: Post a structured Linear project update document on a version release. Orchestrates tapps_release_update → docs_validate_release_update → save_document → cache invalidation. Use when posting a release announcement to Linear after shipping a new version.
allowed-tools: mcp__nlt-release-ship__tapps_release_update mcp__nlt-release-ship__docs_generate_release_update mcp__nlt-release-ship__docs_validate_release_update mcp__nlt-release-ship__docs_release_gate mcp__plugin_linear_linear__save_document mcp__nlt-linear-issues__tapps_linear_snapshot_invalidate
argument-hint: "--version vX.Y.Z --prev-version vX.Y.W [--team <team>] [--project <project>] [--dry-run]"
---

Post a structured Linear project update document when a new version is released. The user's request to post a release update is standing authorization for the full pipeline — do NOT pause mid-flow to ask "should I post this?"

**Flow:**

1. Call `mcp__nlt-release-ship__tapps_release_update(version, prev_version, team, project)`.
   - `version` and `prev_version` are required. Parse from the user's prompt or ask once if both are missing.
   - `team` and `project`: read from `.tapps-mcp.yaml` if present (`linear_team`, `linear_project` fields), otherwise pass empty strings.
   - If `dry_run=true` is requested, pass it through — the tool returns the body without requiring validation to pass.

1b. **Docs release gate (required unless dry_run):** Call `mcp__nlt-release-ship__docs_release_gate`. If `success=false` or aggregate verdict is fail, surface findings and stop — do not post.

2. Check the response:
   - If `success=false`: surface the `error.message` and `findings` to the user. Stop — do not post.
   - If `agent_ready=false` (and not dry_run): surface findings, stop.
   - If `agent_ready=true`: proceed.

3. Call `mcp__plugin_linear_linear__save_document`:
   - `project`: use `data.project` from the tool response.
   - `title`: use `data.document_title` from the tool response (format: `Release vX.Y.Z — YYYY-MM-DD`).
   - `content`: use `data.body` from the tool response verbatim.

4. After `save_document` succeeds, call `mcp__nlt-linear-issues__tapps_linear_snapshot_invalidate`:
   - `team`: use `data.team` from tool response.
   - `project`: use `data.project` from tool response.

5. Report the document URL from `save_document` response and the version that was posted.

**Rules:**
- Never call `save_document` without a prior `agent_ready=true` from `tapps_release_update` (unless `dry_run=true`).
- `document_title` must use the em-dash format from `data.document_title` — do not construct it manually.
- Do not modify the body returned by the tool. Pass `data.body` verbatim.
""",
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

""" + _FINISH_TASK_CHECKLIST_AND_DOC_GAPS_CURSOR + """

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
---

End the session with a durable handoff the next chat loads via `tapps-continue-session`.

""" + _HANDOFF_PRE_GATE + """

1. **Draft handoff (5–10 bullets):** Done, Open, Next (P0), Blockers (`- none` when clear), optional Changed files, Verify, Success criterion.

""" + _HANDOFF_P0_GATE + """

""" + _HANDOFF_MARKDOWN_SHAPE + """

""" + _HANDOFF_PERSIST + """

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

""" + _CONTINUE_LOAD_AND_CONTEXT + """

3. **Linear context.**
   - If the user passed `TAP-####` (argument or handoff **Linear P0**), call `get_issue(id=...)`.
   - For backlog/triage without a known id, invoke the `linear-read` skill — do not call raw `list_issues` (cache gate).

""" + _CONTINUE_EMIT_AND_PROCEED + """
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
---

Run a parallel review-fix-validate pipeline on changed Python files:

1. Call `tapps_session_start` if not already called
2. Determine scope: detect changed Python files via git diff or accept a file list
3. For each file (or batch of files), spawn a `tapps-review-fixer` agent:
   - Pass the file path and instructions to score, fix, and gate the file
4. Wait for all agents to complete and collect their results
5. Review and merge any changes
6. Call `tapps_validate_changed` with explicit `file_paths` to verify all files pass
7. Call `tapps_checklist(task_type="review")` for final verification
8. Present a summary table: file | before score | after score | gate | fixes applied
""",
    "tapps-research": """\
---
name: tapps-research
description: >-
  Look up library documentation and research best practices
  for the technologies used in this project. Use when writing code that uses
  an external library or when you need API reference or version-specific guidance.
mcp_tools:
  - tapps_lookup_docs
---

Look up library documentation using TappsMCP:

1. Call `tapps_lookup_docs` with the library name and topic
2. If coverage is incomplete, call `tapps_lookup_docs` with a more specific topic
3. Synthesize findings into a clear, actionable answer with code examples
4. Include API signatures and usage patterns from the documentation
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
---

`tapps_memory` on the **`nlt-memory`** MCP server is a slim facade (TAP-3895). Default consumer path is **`uv run tapps-mcp memory`** (bridge-only — never add direct `tapps-brain` to `.mcp.json`).

## Routing guide

| Need | Path |
|------|------|
| Cross-chat handoff | `tapps-handoff-session` then `tapps-continue-session` |
| Session-local notes | `tapps_session_notes(action="save", ...)` |
| Save / recall / search brain | `uv run tapps-mcp memory <subcommand>` |
| Brain health | `tapps_session_start()` → `brain_bridge_health` |

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
---

When the user asks about TappsMCP tools, provide the full tool reference.
Essential: tapps_session_start (first), tapps_quick_check (after edits),
tapps_validate_changed (before complete, always pass file_paths), tapps_checklist (before complete).
For the full table, see the skill content. Call tapps_server_info for workflow.
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
---

Bootstrap TappsMCP in a new or existing project:

1. Call `tapps_init` to run the full bootstrap pipeline (`mcp_config` defaults true)
2. Check the response for `content_return: true` — if present, the server could not
   write files directly (Docker / read-only mount).  Apply the files from
   `file_manifest.files[]` using the Write tool.  See `/tapps-apply-files` for details.
3. If files were written directly, review the created files (AGENTS.md, TECH_STACK.md, platform rules, hooks, MCP config)
4. Confirm MCP config lists tapps-mcp only (no direct tapps-brain entry — bridge-only)
5. If any issues are reported, call `tapps_doctor` to diagnose
6. Verify that MCP config has tool auto-approval rules
7. For shared-brain HTTP wiring, see docs/operations/CONSUMER-REPO-BRAIN-WIRING.md
8. Confirm the project is ready for the TappsMCP quality workflow

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
---

Upgrade tapps-mcp / docs-mcp end-to-end. The user's request is standing authorization — do NOT pause mid-flow.

**Pick install source from prompt:**

- Local checkout: `uv tool install --reinstall --from <path>/packages/tapps-mcp tapps-mcp` (and same for `docs-mcp`).
- Git tag: `uv tool install --reinstall "git+https://github.com/wtthornton/tapps-mcp.git@vX.Y.Z#subdirectory=packages/tapps-mcp" tapps-mcp`.

If unspecified, ask once.

**Steps:**

1. Reinstall both CLIs. Verify with `uv tool list | grep -E '(tapps-mcp|docs-mcp)'`.
2. Restart MCP servers (exit + reopen Cursor, or reconnect). Stop on first invocation; resume after restart.
3. `tapps_session_start(force=true)`. Confirm `server.version` matches and `install_drift.drift_detected == false`.
4. `tapps-mcp upgrade --dry-run`. Review diff for AGENTS.md, hooks, rules, skills, .mcp.json. Pause if a customized canonical section will be overwritten.
5. `tapps-mcp upgrade` (writes timestamped backup to `.tapps-mcp/backups/<ts>/`).
6. `tapps-mcp doctor` AND `tapps_checklist(task_type="upgrade")`. Stop on failure.
7. One-line summary: versions, files refreshed, doctor + checklist status, backup path.

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
---

Work with Linear issues for AI-agent consumption. Infer intent from the user's prompt and act autonomously within scope. The user's original request is standing authorization for the full generator → validator → save chain — do NOT pause mid-flow to ask "should I create this?"

**Assignee — agent, not human (applies to every write below).** Resolve the agent user once per session via `linear_list_users`, picking the user whose `name`/`displayName`/`email` matches `agent`, `bot`, `tapps`, `claude`, or `agent_user` in `.tapps-mcp.yaml`. Cache the id. Pass `assignee="<agent-user-id-or-name>"` on every Linear write. If no agent user exists, leave `assignee` unset — never fall back to the OAuth user. Only override when the user explicitly names a person.

**Create** a new issue (default when prompt describes a change/bug):

1. Call `docs_generate_story` with the user's ask. Required args: `title` (<=80 chars, pattern `file.py: symptom`), `files` (comma-separated, each with `:LINE-RANGE`), `acceptance_criteria` (verifiable items).
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
    "continuous-learning-v2": """\
---
name: continuous-learning-v2
description: Instinct-based learning system that observes sessions via hooks, creates atomic instincts with confidence scoring, and evolves them into skills/commands/agents. v2.1 adds project-scoped instincts to prevent cross-project contamination.
origin: ECC
version: 2.1.0
---

# Continuous Learning v2.1 - Instinct-Based Architecture

An advanced learning system that turns your Claude Code sessions into reusable knowledge through atomic "instincts" - small learned behaviors with confidence scoring.

**v2.1** adds **project-scoped instincts** — React patterns stay in your React project, Python conventions stay in your Python project, and universal patterns (like "always validate input") are shared globally.

## When to Activate

- Setting up automatic learning from Claude Code sessions
- Configuring instinct-based behavior extraction via hooks
- Tuning confidence thresholds for learned behaviors
- Reviewing, exporting, or importing instinct libraries
- Evolving instincts into full skills, commands, or agents
- Managing project-scoped vs global instincts
- Promoting instincts from project to global scope

## What's New in v2.1

| Feature | v2.0 | v2.1 |
|---------|------|------|
| Storage | Global (~/.claude/homunculus/) | Project-scoped (projects/<hash>/) |
| Scope | All instincts apply everywhere | Project-scoped + global |
| Detection | None | git remote URL / repo path |
| Promotion | N/A | Project → global when seen in 2+ projects |
| Commands | 4 (status/evolve/export/import) | 6 (+promote/projects) |
| Cross-project | Contamination risk | Isolated by default |

## Commands

| Command | Description |
|---------|-------------|
| `/instinct-status` | Show all instincts (project-scoped + global) with confidence |
| `/evolve` | Cluster related instincts into skills/commands, suggest promotions |
| `/instinct-export` | Export instincts (filterable by scope/domain) |
| `/instinct-import <file>` | Import instincts with scope control |
| `/promote [id]` | Promote project instincts to global scope |
| `/projects` | List all known projects and their instinct counts |

## Quick Start

### 1. Enable Observation Hooks (add to `~/.claude/settings.json`)

```json
{
  "hooks": {
    "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "~/.claude/skills/continuous-learning-v2/hooks/observe.sh"}]}],
    "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "~/.claude/skills/continuous-learning-v2/hooks/observe.sh"}]}]
  }
}
```

### 2. Initialize Directory Structure

```bash
mkdir -p ~/.claude/homunculus/{instincts/{personal,inherited},evolved/{agents,skills,commands},projects}
```

## Scope Decision Guide

| Pattern Type | Scope | Examples |
|-------------|-------|---------|
| Language/framework conventions | **project** | "Use React hooks", "Follow Django patterns" |
| Code style | **project** | "Use functional style", "Prefer dataclasses" |
| Security practices | **global** | "Validate user input", "Sanitize SQL" |
| Tool workflow preferences | **global** | "Grep before Edit", "Read before Write" |

## Configuration

Edit `config.json` to control the background observer:

```json
{
  "version": "2.1",
  "observer": {
    "enabled": false,
    "run_interval_minutes": 5,
    "min_observations_to_analyze": 20
  }
}
```
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
---

Multi-issue Linear reads are cache-first by contract (TAP-967 audit: 5,368 `list_issues` calls / 0.26% cache adoption). Invoke ANY time the user asks for a list, batch, or filtered view of Linear issues.

**When to invoke:** "list Linear issues", "what's open in TAP", "find issues assigned to X", "review the backlog". Skip for single-issue lookups (`get_issue(id="TAP-686")`).

**Core flow — every multi-issue read:**

1. `tapps_linear_snapshot_get(team, project, state, label?)` first.
2. On `cached=true`, use `data.issues` and filter in-memory — `list_issues` is NOT called.
3. On `cached=false`, call `tapps_linear_list_issues(team, project, state, label?, limit?)` as a gate check (TAP-2010). On `ok=true`, call `linear_list_issues` with NARROW filters. On `ok=false`, follow the `hint` (re-call `snapshot_get` first).
4. Immediately call `tapps_linear_snapshot_put(team, project, issues_json=json.dumps(issues), state, label?, limit?)` with the **same** key dimensions as the get call.

**The 6-poll kickoff antipattern:** firing six `list_issues` calls (one per state x priority bucket) collapses to one `snapshot_get(state="open")` plus an in-memory filter. The 5-min open-state TTL means the next session warms instantly.

**Status-bucket sweep antipattern:** three sequential `list_issues` calls for `backlog`/`unstarted`/`started` collapses to one `snapshot_get(state="open")` + memory filter on `state.type`.

**Anti-patterns — do not do these:**

- `list_issues` without a prior `snapshot_get` for the same key.
- `list_issues({})` or `list_issues({team, limit:250})` (the unfiltered scroll).
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


def generate_skills(
    project_root: Path,
    platform: str,
    *,
    engagement_level: str = "medium",
    overwrite: bool = False,
) -> dict[str, Any]:
    """Generate SKILL.md files for the given platform.

    Creates skill directories with ``SKILL.md`` in
    ``.claude/skills/`` or ``.cursor/skills/`` depending on the platform.
    Existing files are skipped to preserve user customizations unless
    *overwrite* is ``True`` (used by the upgrade path to refresh
    corrected frontmatter) or the skill is in
    :data:`SESSION_TRANSFER_SKILL_NAMES` (always refreshed so handoff
    workflows stay aligned with doctor checks).
    When *engagement_level* is set, prepends a note (MANDATORY vs optional).

    Returns a summary dict with ``created``, ``updated``, and ``skipped`` lists.
    """
    if platform == "claude":
        skills_base = project_root / ".claude" / "skills"
        templates = CLAUDE_SKILLS
    elif platform == "cursor":
        skills_base = project_root / ".cursor" / "skills"
        templates = CURSOR_SKILLS
    else:
        return {"created": [], "skipped": [], "error": f"Unknown platform: {platform}"}

    engagement_note = ""
    if engagement_level == "high":
        engagement_note = "*Engagement: MANDATORY for high-enforcement projects.*\n\n"
    elif engagement_level == "low":
        engagement_note = "*Engagement: Optional for low-enforcement projects.*\n\n"

    created: list[str] = []
    updated: list[str] = []
    skipped: list[str] = []
    for skill_name, content in templates.items():
        skill_dir = skills_base / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        target = skill_dir / "SKILL.md"
        full_content = engagement_note + content
        if target.exists():
            refresh = overwrite or skill_name in SESSION_TRANSFER_SKILL_NAMES
            if refresh:
                target.write_text(full_content, encoding="utf-8")
                updated.append(skill_name)
            else:
                skipped.append(skill_name)
        else:
            target.write_text(full_content, encoding="utf-8")
            created.append(skill_name)

    return {"created": created, "updated": updated, "skipped": skipped}
