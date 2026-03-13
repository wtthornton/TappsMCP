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
  Research a technical question using domain experts and library docs.
  Combines expert consultation with docs lookup for comprehensive answers.
allowed-tools: >-
  mcp__tapps-mcp__tapps_research
  mcp__tapps-mcp__tapps_consult_expert
  mcp__tapps-mcp__tapps_lookup_docs
argument-hint: "[question]"
context: fork
model: claude-sonnet-4-6
---

Research a technical question using TappsMCP:

1. Call `mcp__tapps-mcp__tapps_research` with the question for expert + docs
2. If confidence < 0.7, call `mcp__tapps-mcp__tapps_lookup_docs` for the library
3. If multi-domain, call `mcp__tapps-mcp__tapps_consult_expert` per domain
4. Synthesize findings into a clear, actionable answer
5. Include confidence scores and suggest follow-up research if needed
""",
    "tapps-security": """\
---
name: tapps-security
user-invocable: true
model: claude-sonnet-4-6
description: >-
  Run a comprehensive security audit including vulnerability scanning,
  dependency CVE checks, and expert security consultation.
allowed-tools: >-
  mcp__tapps-mcp__tapps_security_scan
  mcp__tapps-mcp__tapps_dependency_scan
  mcp__tapps-mcp__tapps_consult_expert
argument-hint: "[file-path]"
---

Run a comprehensive security audit using TappsMCP:

1. Call `mcp__tapps-mcp__tapps_security_scan` on the target file to detect vulnerabilities
2. Call `mcp__tapps-mcp__tapps_dependency_scan` to check for known CVEs in dependencies
3. Call `mcp__tapps-mcp__tapps_consult_expert` with domain "security" for additional guidance
4. Group all findings by severity (critical, high, medium, low)
5. Suggest a prioritized fix order starting with the highest-severity issues
""",
    "tapps-memory": """\
---
name: tapps-memory
user-invocable: true
model: claude-sonnet-4-6
description: >-
  Manage shared project memory for cross-session knowledge persistence.
  20 actions: save, search, consolidate, federation, and more.
allowed-tools: mcp__tapps-mcp__tapps_memory mcp__tapps-mcp__tapps_session_notes
argument-hint: "[action] [key]"
---

Manage shared project memory using TappsMCP (20 actions):

**Core CRUD:** save, save_bulk, get, list, delete
**Search:** search (ranked BM25 with composite scoring)
**Intelligence:** reinforce (reset decay), gc (archive stale), contradictions (detect stale claims), reseed
**Consolidation:** consolidate (merge related entries with provenance), unconsolidate (undo)
**Import/export:** import (JSON), export (JSON or Markdown)
**Federation:** federate_register, federate_publish, federate_subscribe, federate_sync, federate_search, federate_status

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
| **tapps_consult_expert** | Domain-specific decisions (security, testing, APIs, etc.) |
| **tapps_research** | Combined expert + docs in one call |
| **tapps_list_experts** | See which expert domains exist |

## Project & memory
| Tool | When to use it |
|------|----------------|
| **tapps_project_profile** | When you need project context (tech stack, type) |
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
  Research a technical question using domain experts and library documentation.
  Combines expert consultation with docs lookup for comprehensive answers.
mcp_tools:
  - tapps_research
  - tapps_consult_expert
  - tapps_lookup_docs
---

Research a technical question using TappsMCP:

1. Call `tapps_research` with the question to get expert + docs in one call
2. If confidence is below 0.7, call `tapps_lookup_docs` directly for the relevant library
3. If the question spans multiple domains, call `tapps_consult_expert` per domain
4. Synthesize findings into a clear, actionable answer
5. Include confidence scores and suggest follow-up research if needed
""",
    "tapps-security": """\
---
name: tapps-security
description: >-
  Run a comprehensive security audit on a Python file including vulnerability scanning,
  dependency CVE checks, and expert security consultation.
mcp_tools:
  - tapps_security_scan
  - tapps_dependency_scan
  - tapps_consult_expert
---

Run a comprehensive security audit using TappsMCP:

1. Call `tapps_security_scan` on the target file to detect vulnerabilities
2. Call `tapps_dependency_scan` to check for known CVEs in dependencies
3. Call `tapps_consult_expert` with domain "security" for additional guidance
4. Group all findings by severity (critical, high, medium, low)
5. Suggest a prioritized fix order starting with the highest-severity issues
""",
    "tapps-memory": """\
---
name: tapps-memory
description: >-
  Manage shared project memory for cross-session knowledge persistence.
  20 actions: save, search, consolidate, federation, and more.
mcp_tools:
  - tapps_memory
  - tapps_session_notes
---

Manage shared project memory using TappsMCP (20 actions):

**Core CRUD:** save, save_bulk, get, list, delete
**Search:** search (ranked BM25 with composite scoring)
**Intelligence:** reinforce, gc, contradictions, reseed
**Consolidation:** consolidate (merge related entries), unconsolidate (undo)
**Import/export:** import (JSON), export (JSON or Markdown)
**Federation:** federate_register, federate_publish, federate_subscribe, federate_sync, federate_search, federate_status

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
