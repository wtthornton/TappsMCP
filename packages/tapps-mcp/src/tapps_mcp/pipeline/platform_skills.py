"""Skill definition templates for Claude Code and Cursor.

Contains SKILL.md templates and the ``generate_skills`` function.
Extracted from ``platform_generators.py`` to reduce file size.

Epic 76: Claude skills use space-delimited ``allowed-tools`` per agentskills.io spec.
Cursor skills use ``mcp_tools`` (YAML list); Cursor applies tool restrictions via mcp_tools.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Skills templates (Story 12.8)
# ---------------------------------------------------------------------------

CLAUDE_SKILLS: dict[str, str] = {
    "tapps-score": """\
---
name: tapps-score
user-invocable: true
model: claude-haiku-4-5-20251001
description: Score a Python file across 7 quality categories and display a structured report.
allowed-tools: mcp__tapps-mcp__tapps_score_file mcp__tapps-mcp__tapps_quick_check
argument-hint: "[file-path]"
---

Score the specified Python file using TappsMCP:

1. Call `mcp__tapps-mcp__tapps_quick_check` with the file path to get an instant score
2. If the score is below 80, call `mcp__tapps-mcp__tapps_score_file` for the full breakdown
3. Present the results in a table: category, score (0-100), top issue per category
4. Highlight any category scoring below 70 as a priority fix
5. Suggest the single highest-impact change the developer can make
""",
    "tapps-gate": """\
---
name: tapps-gate
user-invocable: true
model: claude-haiku-4-5-20251001
description: Run a quality gate check and report pass/fail with blocking issues.
allowed-tools: mcp__tapps-mcp__tapps_quality_gate
argument-hint: "[file-path]"
disable-model-invocation: true
---

Run a quality gate check using TappsMCP:

1. Call `mcp__tapps-mcp__tapps_quality_gate` with the current project
2. Display the overall pass/fail result clearly
3. List each failing criterion with its actual vs. required value
4. If the gate fails, list the minimum changes required to pass
5. Do not declare work complete if the gate has not passed
""",
    "tapps-validate": """\
---
name: tapps-validate
user-invocable: true
model: claude-haiku-4-5-20251001
description: Validate all changed files meet quality thresholds before declaring work complete.
allowed-tools: mcp__tapps-mcp__tapps_validate_changed
disable-model-invocation: true
---

Validate changed files using TappsMCP:

1. Identify the Python files you changed in this session (from git status or your edit history)
2. Call `mcp__tapps-mcp__tapps_validate_changed` with explicit `file_paths` (comma-separated) scoped to only those files. **Never call without `file_paths`** - auto-detect scans all git-changed files and can be very slow in large repos. Default is quick mode; only use `quick=false` as a last resort (pre-release, security audit).
3. Display each file with its score and pass/fail status
4. If any file fails, list it with the top issue preventing it from passing
5. Confirm explicitly when all changed files pass before declaring work done
6. If any files fail, do NOT mark the task as complete
""",
    "tapps-finish-task": """\
---
name: tapps-finish-task
user-invocable: true
model: claude-haiku-4-5-20251001
description: Run the end-of-task TAPPS pipeline in one shot — validate_changed, then checklist, then an optional memory save for anything architectural or patterned learned this session. The recommended final step before declaring work complete.
allowed-tools: mcp__tapps-mcp__tapps_validate_changed mcp__tapps-mcp__tapps_checklist mcp__tapps-mcp__tapps_memory
argument-hint: "[task_type: feature|bugfix|refactor|security|review]"
---

Close out the current task end-to-end. Run each step; do NOT skip one that failed — surface the failure and stop.

1. **Validate changed files.** Identify the files you edited this session (git status, your edit history). Call `mcp__tapps-mcp__tapps_validate_changed` with explicit `file_paths` (comma-separated) scoped to those files. **Never call without `file_paths`.** Default is quick mode. If any file fails, list it with the top blocking issue and stop — the task is not complete. Do not proceed to step 2 until all changed files pass.

2. **Verify the checklist.** Call `mcp__tapps-mcp__tapps_checklist(task_type=<feature|bugfix|refactor|security|review>)`. If the response has `complete: false`, the `missing_steps` list names required tools you skipped — address each (or explain why it does not apply) and re-run the checklist. Only proceed when `complete: true`.

3. **Save learnings (conditional).** If this session produced a non-obvious architectural or pattern-level decision — a new convention, a subtle trade-off, a gotcha someone else would re-discover — call `mcp__tapps-mcp__tapps_memory(action="save", tier=<"architectural"|"pattern">, ...)` with a concise body. Skip this step for routine fixes, refactors where the code itself documents the decision, or trivial bugfixes.

4. **Report.** Emit a one-line summary: `Files validated: N pass. Checklist: <task_type> complete. Memory saved: yes|no.` If any step failed or was skipped, say so explicitly.
""",
    "tapps-report": """\
---
name: tapps-report
user-invocable: true
model: claude-haiku-4-5-20251001
description: >-
  Generate a quality report across Python files in the project.
  Scores multiple files and presents an aggregate summary.
allowed-tools: mcp__tapps-mcp__tapps_report
argument-hint: "[file-path or empty for project-wide]"
---

Generate a quality report using TappsMCP:

1. Call `mcp__tapps-mcp__tapps_report` with an optional file path
2. If no file path, a project-wide report scores up to 20 files
3. Present results in a table: file | score | pass/fail | top issue
4. Highlight any files scoring below the quality gate threshold
5. Suggest priority fixes for the lowest-scoring files
""",
    "tapps-review-pipeline": """\
---
name: tapps-review-pipeline
user-invocable: true
model: claude-sonnet-4-6
description: >-
  Orchestrate a parallel review-fix-validate pipeline across multiple changed files.
  Spawns tapps-review-fixer agents in worktrees for parallel processing.
allowed-tools: mcp__tapps-mcp__tapps_validate_changed mcp__tapps-mcp__tapps_checklist
context: fork
agent: general-purpose
---

Run a parallel review-fix-validate pipeline on changed Python files:

1. Call `mcp__tapps-mcp__tapps_session_start` if not already called
2. Determine scope: detect changed Python files via git diff or accept a file list
3. For each file (or batch of files), spawn a `tapps-review-fixer` agent in a worktree:
   - Use the Task tool with `subagent_type: "general-purpose"` and `isolation: "worktree"`
   - Pass the file path and instructions to score, fix, and gate the file
4. Wait for all agents to complete and collect their results
5. Merge any worktree changes back (review diffs before accepting)
6. Call `mcp__tapps-mcp__tapps_validate_changed` with explicit `file_paths` to verify all files pass
7. Call `mcp__tapps-mcp__tapps_checklist(task_type="review")` for final verification
8. Present a summary table: file | before score | after score | gate | fixes applied
""",
    "tapps-research": """\
---
name: tapps-research
user-invocable: true
description: >-
  Look up library documentation and research best practices
  for the technologies used in this project.
allowed-tools: mcp__tapps-mcp__tapps_lookup_docs
argument-hint: "[library] [topic]"
context: fork
model: claude-sonnet-4-6
---

Look up library documentation using TappsMCP:

1. Call `mcp__tapps-mcp__tapps_lookup_docs` with the library name and topic
2. If coverage is incomplete, call `mcp__tapps-mcp__tapps_lookup_docs` with a more specific topic
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
  and dependency CVE checks.
allowed-tools: >-
  mcp__tapps-mcp__tapps_security_scan
  mcp__tapps-mcp__tapps_dependency_scan
argument-hint: "[file-path]"
---

Run a comprehensive security audit using TappsMCP:

1. Call `mcp__tapps-mcp__tapps_security_scan` on the target file to detect vulnerabilities
2. Call `mcp__tapps-mcp__tapps_dependency_scan` to check for known CVEs in dependencies
3. Group all findings by severity (critical, high, medium, low)
4. Suggest a prioritized fix order starting with the highest-severity issues
""",
    "tapps-memory": """\
---
name: tapps-memory
user-invocable: true
model: claude-sonnet-4-6
description: >-
  Manage shared project memory for cross-session knowledge persistence.
  33 actions: save, search, federation, profiles, Hive, and more.
allowed-tools: mcp__tapps-mcp__tapps_memory mcp__tapps-mcp__tapps_session_notes
argument-hint: "[action] [key]"
---

Manage shared project memory using TappsMCP (33 actions):

**Core CRUD:** save, save_bulk, get, list, delete
**Search:** search (ranked BM25 with composite scoring)
**Intelligence:** reinforce (reset decay), gc (archive stale), contradictions (detect stale claims), reseed
**Consolidation:** consolidate (merge related entries with provenance), unconsolidate (undo)
**Import/export:** import (JSON), export (JSON or Markdown)
**Federation:** federate_register, federate_publish, federate_subscribe, federate_sync, federate_search, federate_status
**Maintenance:** index_session (index session notes), validate (check store integrity), maintain (GC + consolidation + contradiction detection)
**Security:** safety_check, verify_integrity | **Profiles:** profile_info, profile_list, profile_switch | **Diagnostics:** health
**Hive / Agent Teams:** hive_status, hive_search, hive_propagate, agent_register

Steps:
1. Determine the action from the list above
2. For saves, classify tier (architectural/pattern/procedural/context) and scope (project/branch/session/shared)
3. Call `mcp__tapps-mcp__tapps_memory` with the action and parameters
4. Display results with confidence scores, tiers, and composite relevance scores
5. For consolidation, use `dry_run=True` first to preview merged entries
6. For federation, register the project first, then publish shared-scope entries
""",
    "tapps-tool-reference": """\
---
name: tapps-tool-reference
user-invocable: true
model: claude-haiku-4-5-20251001
description: >-
  Look up when to use each TappsMCP tool. Full tool reference with per-tool
  guidance for session start, scoring, validation, checklist, docs, experts, and more.
allowed-tools: mcp__tapps-mcp__tapps_server_info
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
| Tool | When to use it |
|------|----------------|
| **tapps_memory** | Session start: search past decisions. Session end: save learnings |
| **tapps_session_notes** | Key decisions during session - promote to memory for persistence |

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
| **tapps_init** | Pipeline bootstrap (once per project) - creates AGENTS.md, rules, hooks. **CLI fallback:** `tapps-mcp upgrade --force --host auto` then `tapps-mcp doctor` |
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
  platform rules, hooks, agents, skills, and MCP config.
allowed-tools: mcp__tapps-mcp__tapps_init mcp__tapps-mcp__tapps_doctor
argument-hint: "[project-root]"
---

Bootstrap TappsMCP in a new or existing project:

1. Call `mcp__tapps-mcp__tapps_init` to run the full bootstrap pipeline
2. Check the response for `content_return: true` — if present, the server could not
   write files directly (Docker / read-only mount).  Apply the files from
   `file_manifest.files[]` using the Write tool.  See `/tapps-apply-files` for details.
3. If files were written directly, review the created files (AGENTS.md, TECH_STACK.md, platform rules, hooks)
4. If any issues are reported, call `mcp__tapps-mcp__tapps_doctor` to diagnose
5. Verify that `.claude/settings.json` has MCP tool auto-approval rules
6. Confirm the project is ready for the TappsMCP quality workflow

**If `tapps_init` is not available** (server not in available MCP servers), use the CLI:
1. Run from the project root: `tapps-mcp upgrade --force --host auto`
2. Then verify: `tapps-mcp doctor`
3. Restart your MCP host to pick up the new config
""",
    "tapps-engagement": """\
---
name: tapps-engagement
user-invocable: true
model: claude-haiku-4-5-20251001
description: >-
  Change the TappsMCP enforcement intensity (high, medium, or low).
  Controls which quality tools are mandatory vs optional.
allowed-tools: mcp__tapps-mcp__tapps_set_engagement_level
argument-hint: "[high|medium|low]"
disable-model-invocation: true
---

Set the TappsMCP LLM engagement level:

1. Call `mcp__tapps-mcp__tapps_set_engagement_level` with the desired level
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
  Apply file operations from a TappsMCP content-return response.
  Used when the MCP server runs in Docker and cannot write files directly.
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
description: Create, lint, validate, or triage Linear issues and epics for agents. MANDATORY for all Linear writes — never call plugin save_issue directly. Routes to docs-mcp generator/validator/triage tools and the Linear plugin by user intent.
allowed-tools: mcp__docs-mcp__docs_generate_epic mcp__docs-mcp__docs_generate_story mcp__docs-mcp__docs_lint_linear_issue mcp__docs-mcp__docs_validate_linear_issue mcp__docs-mcp__docs_linear_triage mcp__plugin_linear_linear__save_issue mcp__plugin_linear_linear__get_issue mcp__plugin_linear_linear__list_issues mcp__tapps-mcp__tapps_linear_snapshot_get mcp__tapps-mcp__tapps_linear_snapshot_put mcp__tapps-mcp__tapps_linear_snapshot_invalidate
argument-hint: "[create-epic|create-story|lint TAP-###|validate|triage] [free-form detail]"
---

Work with Linear issues for AI-agent consumption. Infer intent from the user's prompt and act autonomously within scope — see `autonomy.md`. The user's original request is the authorization for the full generator → validator → save_issue chain; do NOT pause mid-flow to ask "should I create this?"

**When to invoke this skill:** ANY request that will create, update, or validate a Linear issue or epic. This includes "file a ticket", "create an issue", "open an epic", "track this as a story", or "add a bug report to Linear". Raw `save_issue` calls are a rule violation — route through this skill.

**Assignee — agent, not human (applies to every write below).** Resolve the agent user once per session via `mcp__plugin_linear_linear__list_users`, picking the user whose `name`/`displayName`/`email` matches `agent`, `bot`, `tapps`, `claude`, or `agent_user` in `.tapps-mcp.yaml`. Cache the id. Pass `assignee_id=<agent_user_id>` on every `save_issue`. If no agent user exists, leave `assignee_id` unset — never fall back to the OAuth user (the human running the session). Only override when the user explicitly names a person.

**Create an epic** (prompt names multiple stories, or "epic", or spans a cross-cutting initiative):
1. Call `mcp__docs-mcp__docs_generate_epic` with the user's ask. Required: `title`, `purpose_and_intent` ("We are doing this so that ..."), `goal`, `motivation`, `acceptance_criteria`, `stories` (JSON array). Optional: `priority`, `estimated_loe`, `references`, `non_goals`.
2. The tool writes `docs/epics/EPIC-<N>.md` to the project. Read it back.
3. Build the Linear-body markdown following the 5-to-7 section epic shape: `## Purpose & Intent`, `## Goal`, `## Motivation`, `## Acceptance Criteria`, `## Stories`, `## Out of Scope`, `## Refs`.
4. Validate via `mcp__docs-mcp__docs_validate_linear_issue(title, description, priority, is_epic=true)`. Target score 100 / `agent_ready=true`.
5. Call `mcp__plugin_linear_linear__save_issue(team, project, title, description, priority, assignee_id=<agent_user_id>, ...)` without `id`. Proceed without prompting the user.
6. Create each child story via the create-story flow below, passing `parent_id=<epic TAP-id>` (each child is also assigned to the agent).
7. After all writes, call `mcp__tapps-mcp__tapps_linear_snapshot_invalidate(team, project)`.

**Create a story** (default when prompt describes a single change/bug):
1. Call `mcp__docs-mcp__docs_generate_story` with the user's ask. Required: `title` (<=80 chars, pattern `file.py: symptom`), `files` (comma-separated, each with `:LINE-RANGE`), `acceptance_criteria` (verifiable items).
2. Default `audience="agent"` emits the 5-section Linear template (What/Where/Why/Acceptance/Refs) and round-trips through the validator.
3. If the call returns `INPUT_INVALID`, refine the inputs per the error message and retry. Do NOT pass `audience="human"` unless the user asks for a product-review doc.
4. Call the Linear plugin's `save_issue(..., assignee_id=<agent_user_id>, parent_id=<epic-id-if-any>)`. Proceed without prompting the user.
5. After `save_issue` returns, call `mcp__tapps-mcp__tapps_linear_snapshot_invalidate(team=<team>, project=<project>)` to evict stale cached snapshots for that slice.

**Lint** an existing issue (prompt like "lint TAP-686", "check TAP-###"):
1. Fetch via `mcp__plugin_linear_linear__get_issue`.
2. Pass title/description/labels/priority/estimate to `mcp__docs-mcp__docs_lint_linear_issue`.
3. Surface score, findings (with fix_hints), and reclaimable noise bytes. For each HIGH severity finding, quote the suggested fix.

**Validate** before creating or after editing (prompt like "is this agent-ready?"):
1. Call `mcp__docs-mcp__docs_validate_linear_issue` with the payload.
2. Report `{agent_ready, score, missing[]}`. Missing items are blockers; propose a concrete fix per item.

**Triage** a batch (prompt like "triage open issues", "find label gaps"):
1. If the user names a specific issue (e.g. "triage TAP-686"), use `mcp__plugin_linear_linear__get_issue(id="TAP-686")` — skip list/cache entirely.
2. **Cache-first read:** call `mcp__tapps-mcp__tapps_linear_snapshot_get(team=<team>, project=<project>, state="backlog" | "unstarted", label?)`. If `data.cached` is `true`, use `data.issues` directly — Linear was not called.
3. **On cache miss** (`data.cached` is `false`): call `mcp__plugin_linear_linear__list_issues` with narrow filters — `team`, `project`, `state`, `includeArchived=false` (never call without filters). Then populate the cache by calling `mcp__tapps-mcp__tapps_linear_snapshot_put(team, project, issues_json=json.dumps(response.issues), state, label?)` using the **same** team/project/state/label/limit as the get call so the keys align.
4. Pass the list to `mcp__docs-mcp__docs_linear_triage`.
5. Apply label_proposals, parent_groupings, and metadata_gaps via Linear plugin writes (each `save_issue` carries `assignee_id=<agent_user_id>` for any newly-owned items). No mid-flow user confirmation; the triage request is the authorization.
6. After any write, call `mcp__tapps-mcp__tapps_linear_snapshot_invalidate(team=<team>, project=<project>)` to refresh the cache on next read.

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
}

CURSOR_SKILLS: dict[str, str] = {
    "tapps-score": """\
---
name: tapps-score
description: Score a Python file across 7 quality categories and display a structured report.
mcp_tools:
  - tapps_score_file
  - tapps_quick_check
---

Score the specified Python file using TappsMCP:

1. Call `tapps_quick_check` with the file path to get an instant score
2. If the score is below 80, call `tapps_score_file` for the full 7-category breakdown
3. Present the results in a table: category, score (0-100), top issue per category
4. Highlight any category scoring below 70 as a priority fix
5. Suggest the single highest-impact change the developer can make
""",
    "tapps-gate": """\
---
name: tapps-gate
description: Run a quality gate check and report pass/fail with blocking issues.
mcp_tools:
  - tapps_quality_gate
---

Run a quality gate check using TappsMCP:

1. Call `tapps_quality_gate` with the current project
2. Display the overall pass/fail result clearly
3. List each failing criterion with its actual vs. required value
4. If the gate fails, list the minimum changes required to pass
5. Do not declare work complete if the gate has not passed
""",
    "tapps-validate": """\
---
name: tapps-validate
description: Validate all changed files meet quality thresholds before declaring work complete.
mcp_tools:
  - tapps_validate_changed
---

Validate changed files using TappsMCP:

1. Identify the Python files you changed in this session (from git status or your edit history)
2. Call `tapps_validate_changed` with explicit `file_paths` (comma-separated) scoped to only those files. **Never call without `file_paths`** - auto-detect scans all git-changed files and can be very slow in large repos. Default is quick mode; only use `quick=false` as a last resort (pre-release, security audit).
3. Display each file with its score and pass/fail status
4. If any file fails, list it with the top issue preventing it from passing
5. Confirm explicitly when all changed files pass before declaring work done
6. If any files fail, do NOT mark the task as complete
""",
    "tapps-finish-task": """\
---
name: tapps-finish-task
description: >-
  Run the end-of-task TAPPS pipeline in one shot: validate changed files,
  verify the checklist, and optionally save learnings to memory.
mcp_tools:
  - tapps_validate_changed
  - tapps_checklist
  - tapps_memory
---

Close out the current task end-to-end. Run each step; do NOT skip one that failed — surface the failure and stop.

1. **Validate changed files.** Identify files edited this session (git status, edit history). Call `tapps_validate_changed` with explicit `file_paths` (comma-separated). Never call without `file_paths`. If any file fails, list it with the top blocking issue and stop.
2. **Verify the checklist.** Call `tapps_checklist(task_type=<feature|bugfix|refactor|security|review>)`. If `complete: false`, address each entry in `missing_steps` and re-run.
3. **Save learnings (conditional).** If the session produced a non-obvious architectural or pattern-level decision, call `tapps_memory(action="save", tier=<"architectural"|"pattern">)`. Skip for routine fixes.
4. **Report.** Emit a one-line summary: `Files validated: N pass. Checklist: <task_type> complete. Memory saved: yes|no.`
""",
    "tapps-report": """\
---
name: tapps-report
description: >-
  Generate a quality report across Python files in the project.
  Scores multiple files and presents an aggregate summary.
mcp_tools:
  - tapps_report
---

Generate a quality report using TappsMCP:

1. Call `tapps_report` with an optional file path
2. If no file path, a project-wide report scores up to 20 files
3. Present results in a table: file | score | pass/fail | top issue
4. Highlight any files scoring below the quality gate threshold
5. Suggest priority fixes for the lowest-scoring files
""",
    "tapps-review-pipeline": """\
---
name: tapps-review-pipeline
description: >-
  Orchestrate a parallel review-fix-validate pipeline across multiple changed files.
  Spawns tapps-review-fixer agents for parallel processing.
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
  for the technologies used in this project.
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
  and dependency CVE checks.
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
  Manage shared project memory for cross-session knowledge persistence.
  33 actions: save, search, federation, profiles, Hive, and more.
mcp_tools:
  - tapps_memory
  - tapps_session_notes
---

Manage shared project memory using TappsMCP (33 actions):

**Core CRUD:** save, save_bulk, get, list, delete
**Search:** search (ranked BM25 with composite scoring)
**Intelligence:** reinforce, gc, contradictions, reseed
**Consolidation:** consolidate (merge related entries), unconsolidate (undo)
**Import/export:** import (JSON), export (JSON or Markdown)
**Federation:** federate_register, federate_publish, federate_subscribe, federate_sync, federate_search, federate_status
**Maintenance:** index_session (index session notes), validate (check store integrity), maintain (GC + consolidation + contradiction detection)
**Security:** safety_check, verify_integrity | **Profiles:** profile_info, profile_list, profile_switch | **Diagnostics:** health
**Hive / Agent Teams:** hive_status, hive_search, hive_propagate, agent_register

Steps:
1. Determine the action from the list above
2. For saves, classify tier (architectural/pattern/procedural/context) and scope (project/branch/session/shared)
3. Call `tapps_memory` with the action and parameters
4. Display results with confidence scores and composite relevance scores
""",
    "tapps-tool-reference": """\
---
name: tapps-tool-reference
description: >-
  Look up when to use each TappsMCP tool. Full tool reference with per-tool
  guidance for session start, scoring, validation, checklist, docs, experts.
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
  platform rules, hooks, agents, skills, and MCP config.
mcp_tools:
  - tapps_init
  - tapps_doctor
---

Bootstrap TappsMCP in a new or existing project:

1. Call `tapps_init` to run the full bootstrap pipeline
2. Check the response for `content_return: true` — if present, the server could not
   write files directly (Docker / read-only mount).  Apply the files from
   `file_manifest.files[]` using the Write tool.  See `/tapps-apply-files` for details.
3. If files were written directly, review the created files (AGENTS.md, TECH_STACK.md, platform rules, hooks)
4. If any issues are reported, call `tapps_doctor` to diagnose
5. Verify that MCP config has tool auto-approval rules
6. Confirm the project is ready for the TappsMCP quality workflow

**If `tapps_init` is not available** (server not in available MCP servers), use the CLI:
1. Run from the project root: `tapps-mcp upgrade --force --host auto`
2. Then verify: `tapps-mcp doctor`
3. Restart your MCP host to pick up the new config
""",
    "tapps-engagement": """\
---
name: tapps-engagement
description: >-
  Change the TappsMCP enforcement intensity (high, medium, or low).
  Controls which quality tools are mandatory vs optional.
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
  Apply file operations from a TappsMCP content-return response.
  Used when the MCP server runs in Docker and cannot write files directly.
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
description: Create, lint, validate, or triage Linear issues for agents. Routes to docs-mcp Linear tools and the Linear plugin by user intent.
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

**Assignee — agent, not human (applies to every write below).** Resolve the agent user once per session via `linear_list_users`, picking the user whose `name`/`displayName`/`email` matches `agent`, `bot`, `tapps`, `claude`, or `agent_user` in `.tapps-mcp.yaml`. Cache the id. Pass `assignee_id=<agent_user_id>` on every Linear write. If no agent user exists, leave `assignee_id` unset — never fall back to the OAuth user. Only override when the user explicitly names a person.

**Create** a new issue (default when prompt describes a change/bug):

1. Call `docs_generate_story` with the user's ask. Required args: `title` (<=80 chars, pattern `file.py: symptom`), `files` (comma-separated, each with `:LINE-RANGE`), `acceptance_criteria` (verifiable items).
2. Default `audience="agent"` emits the 5-section Linear template (What/Where/Why/Acceptance/Refs) and round-trips through the validator.
3. If the call returns `INPUT_INVALID`, refine the inputs per the error message and retry. Do NOT pass `audience="human"` unless the user asks for a product-review doc.
4. Call the Linear plugin's write tool with `assignee_id=<agent_user_id>`. Proceed without prompting the user.
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
5. Apply label_proposals, parent_groupings, and metadata_gaps via Linear writes (each carrying `assignee_id=<agent_user_id>` for any newly-owned items). No mid-flow user confirmation.
6. After any write, call `tapps_linear_snapshot_invalidate(team=<team>, project=<project>)` to refresh the cache on next read.

Rules (enforced by docs-mcp tools):

- Title <=80 chars; no em-dash preambles.
- Inline-code filenames (`AGENTS.md`), never `[AGENTS.md](AGENTS.md)` (Linear's autolinker mangles).
- Bare `TAP-###` refs, never `<issue id="UUID">TAP-###</issue>` wrappers.
- `## Acceptance` has at least one verifiable `- [ ]` item.
- `## Where` includes at least one `path/to/file.ext:LINE-RANGE` anchor.
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

    Creates 12 skill directories with ``SKILL.md`` in
    ``.claude/skills/`` or ``.cursor/skills/`` depending on the platform.
    Existing files are skipped to preserve user customizations unless
    *overwrite* is ``True`` (used by the upgrade path to refresh
    corrected frontmatter).
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
            if overwrite:
                target.write_text(full_content, encoding="utf-8")
                updated.append(skill_name)
            else:
                skipped.append(skill_name)
        else:
            target.write_text(full_content, encoding="utf-8")
            created.append(skill_name)

    return {"created": created, "updated": updated, "skipped": skipped}
