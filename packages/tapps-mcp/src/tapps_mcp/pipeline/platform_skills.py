"""Skill definition templates for Claude Code and Cursor.

Contains SKILL.md templates and the ``generate_skills`` function.
Extracted from ``platform_generators.py`` to reduce file size.
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
description: Score a Python file across 7 quality categories and display a structured report.
tools: mcp__tapps-mcp__tapps_score_file, mcp__tapps-mcp__tapps_quick_check
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
description: Run a quality gate check and report pass/fail with blocking issues.
tools: mcp__tapps-mcp__tapps_quality_gate
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
description: Validate all changed files meet quality thresholds before declaring work complete.
tools: mcp__tapps-mcp__tapps_validate_changed
---

Validate all changed files using TappsMCP:

1. Call `mcp__tapps-mcp__tapps_validate_changed` to get the list of changed files and their scores
2. Display each file with its score and pass/fail status
3. If any file fails, list it with the top issue preventing it from passing
4. Confirm explicitly when all changed files pass before declaring work done
5. If any files fail, do NOT mark the task as complete
""",
    "tapps-review-pipeline": """\
---
name: tapps-review-pipeline
description: >-
  Orchestrate a parallel review-fix-validate pipeline across multiple changed files.
  Spawns tapps-review-fixer agents in worktrees for parallel processing.
tools: mcp__tapps-mcp__tapps_validate_changed, mcp__tapps-mcp__tapps_checklist
---

Run a parallel review-fix-validate pipeline on changed Python files:

1. Call `mcp__tapps-mcp__tapps_session_start` if not already called
2. Determine scope: detect changed Python files via git diff or accept a file list
3. For each file (or batch of files), spawn a `tapps-review-fixer` agent in a worktree:
   - Use the Task tool with `subagent_type: "general-purpose"` and `isolation: "worktree"`
   - Pass the file path and instructions to score, fix, and gate the file
4. Wait for all agents to complete and collect their results
5. Merge any worktree changes back (review diffs before accepting)
6. Call `mcp__tapps-mcp__tapps_validate_changed` to verify all files pass
7. Call `mcp__tapps-mcp__tapps_checklist(task_type="review")` for final verification
8. Present a summary table: file | before score | after score | gate | fixes applied
""",
    "tapps-research": """\
---
name: tapps-research
description: >-
  Research a technical question using domain experts and library docs.
  Combines expert consultation with docs lookup for comprehensive answers.
tools: >-
  mcp__tapps-mcp__tapps_research,
  mcp__tapps-mcp__tapps_consult_expert,
  mcp__tapps-mcp__tapps_lookup_docs
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
description: >-
  Run a comprehensive security audit including vulnerability scanning,
  dependency CVE checks, and expert security consultation.
tools: >-
  mcp__tapps-mcp__tapps_security_scan,
  mcp__tapps-mcp__tapps_dependency_scan,
  mcp__tapps-mcp__tapps_consult_expert
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
description: >-
  Manage shared project memory for cross-session knowledge persistence.
  Save, retrieve, search, and manage memory entries with tier classification.
tools: mcp__tapps-mcp__tapps_memory, mcp__tapps-mcp__tapps_session_notes
---

Manage shared project memory using TappsMCP:

1. Determine the action: save, get, list, search, or delete
2. For saves, classify the memory tier (team, project, or session)
3. Call `mcp__tapps-mcp__tapps_memory` with the appropriate action and parameters
4. Display results with confidence scores and metadata
5. Suggest tier promotions for frequently accessed session-level memories
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

Validate all changed files using TappsMCP:

1. Call `tapps_validate_changed` to get the list of changed files and their scores
2. Display each file with its score and pass/fail status
3. If any file fails, list it with the top issue preventing it from passing
4. Confirm explicitly when all changed files pass before declaring work done
5. If any files fail, do NOT mark the task as complete
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
6. Call `tapps_validate_changed` to verify all files pass
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
  Save, retrieve, search, and manage memory entries with tier classification.
mcp_tools:
  - tapps_memory
  - tapps_session_notes
---

Manage shared project memory using TappsMCP:

1. Determine the action: save, get, list, search, or delete
2. For saves, classify the memory tier (team, project, or session)
3. Call `tapps_memory` with the appropriate action and parameters
4. Display results with confidence scores and metadata
5. Suggest tier promotions for frequently accessed session-level memories
""",
}


def generate_skills(
    project_root: Path,
    platform: str,
    *,
    engagement_level: str = "medium",
) -> dict[str, Any]:
    """Generate SKILL.md files for the given platform.

    Creates 7 skill directories with ``SKILL.md`` in
    ``.claude/skills/`` or ``.cursor/skills/`` depending on the platform.
    Existing files are skipped to preserve user customizations.
    When *engagement_level* is set, prepends a note (MANDATORY vs optional).

    Returns a summary dict with ``created`` and ``skipped`` lists.
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
    skipped: list[str] = []
    for skill_name, content in templates.items():
        skill_dir = skills_base / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        target = skill_dir / "SKILL.md"
        if target.exists():
            skipped.append(skill_name)
        else:
            target.write_text(engagement_note + content, encoding="utf-8")
            created.append(skill_name)

    return {"created": created, "skipped": skipped}
