"""Subagent definition templates for Claude Code and Cursor.

Contains agent markdown templates and the ``generate_subagent_definitions``
function. Extracted from ``platform_generators.py`` to reduce file size.
"""

from __future__ import annotations

import importlib.resources
import sys
from pathlib import Path
from typing import Any

from tapps_mcp.pipeline.platform_skills import resolve_model_markers

_AGENT_ASSET_PACKAGE = "tapps_mcp.pipeline"
_AGENT_ASSET_SUBDIR = "assets/claude_agents"


def _read_claude_agent_asset(file_name: str) -> str:
    """Read one ``CLAUDE_AGENTS`` body from package data, ``{{model:role}}`` resolved.

    Mirrors ``tapps_mcp.prompts.prompt_loader._read_resource`` (same
    ``sys.frozen`` PyInstaller fallback) since this module ships inside the
    same frozen binary as the prompt package. *file_name* already carries
    the ``.md`` suffix (it is the ``CLAUDE_AGENTS`` dict key verbatim).
    """
    if getattr(sys, "frozen", False):
        raw = (Path(__file__).parent / _AGENT_ASSET_SUBDIR / file_name).read_text(encoding="utf-8")
    else:
        ref = importlib.resources.files(_AGENT_ASSET_PACKAGE).joinpath(
            f"{_AGENT_ASSET_SUBDIR}/{file_name}"
        )
        raw = ref.read_text(encoding="utf-8")
    return resolve_model_markers(raw)


# ---------------------------------------------------------------------------
# Project-scope rule (shared across every deployed agent)
# ---------------------------------------------------------------------------
#
# Bootstrapped agents must remain scoped to the deploying project's repo for
# any *write* action. Reading external context is fine; modifying issues,
# PRs, or files outside the deploying repo/project is not.

_PROJECT_SCOPE_RULE = """
## Project scope (do not break out of this repo/project)

You were deployed into THIS repo by `tapps_init` / `tapps_upgrade`. Stay in scope:

- You MAY read across projects (docs lookups, browsing other repos, fetching references).
- You MUST NOT write outside this repo or this project. Specifically:
  - Do not create, update, comment on, or move Linear (or other tracker) issues
    that belong to a different project than this repo.
  - Do not modify files, branches, or pull requests in any other repository.
  - Do not push, merge, or release on behalf of another project.
- Pull team / project / repo identity from local config (`.tapps-mcp.yaml`,
  the current git remote) — never infer it from search results or memory hits
  that point at unrelated workspaces.
- If a task seems to require a write outside this repo/project, stop and ask
  the user instead of doing it.
"""

# ---------------------------------------------------------------------------
# Subagent templates (Story 12.6)
# ---------------------------------------------------------------------------

CLAUDE_AGENTS: dict[str, str] = {
    "tapps-reviewer.md": _read_claude_agent_asset("tapps-reviewer.md"),
    "tapps-researcher.md": _read_claude_agent_asset("tapps-researcher.md"),
    "tapps-validator.md": _read_claude_agent_asset("tapps-validator.md"),
    "tapps-review-fixer.md": _read_claude_agent_asset("tapps-review-fixer.md"),
    "tapps-frontend-reviewer.md": _read_claude_agent_asset("tapps-frontend-reviewer.md"),
}

CURSOR_AGENTS: dict[str, str] = {
    "tapps-reviewer.md": """\
---
name: tapps-reviewer
description: >-
  Use proactively to review code quality, run security scans, and enforce
  quality gates after editing Python files.
model: sonnet
readonly: false
is_background: false
tools:
  - code_search
  - read_file
---

You are a TappsMCP quality reviewer. When invoked:

1. Identify which Python files were recently edited
2. Call the `tapps_quick_check` MCP tool on each changed file
3. If any file scores below 70, call `tapps_score_file` for a detailed breakdown
4. Summarize findings: file, score, top issues, suggested fixes
5. If overall quality is poor, recommend calling `tapps_quality_gate`

Focus on actionable feedback. Be concise.
""",
    "tapps-researcher.md": """\
---
name: tapps-researcher
description: >-
  Look up documentation, consult domain experts, and research best practices
  for the technologies used in this project.
model: haiku
readonly: true
is_background: false
tools:
  - code_search
  - read_file
---

You are a TappsMCP research assistant. When invoked:

1. Call the `tapps_lookup_docs` MCP tool to look up documentation for the relevant library or framework
2. If the question spans multiple domains, call `tapps_lookup_docs` with domain-specific queries
3. Summarize the findings with code examples and best practices
4. Reference the source documentation

Be thorough but concise. Cite specific sections from the documentation.
""",
    "tapps-validator.md": """\
---
name: tapps-validator
description: >-
  Run pre-completion validation on all changed files to confirm they meet
  quality thresholds before declaring work complete.
model: sonnet
readonly: false
is_background: false
tools:
  - code_search
  - read_file
---

You are a TappsMCP validation agent. When invoked:

1. Call the `tapps_validate_changed` MCP tool with explicit `file_paths` (comma-separated) to check changed files. Never call without `file_paths` - auto-detect can be very slow. Default is quick mode; only use `quick=false` as a last resort.
2. For each file that fails, report the file path, score, and top blocking issue
3. If all files pass, confirm explicitly that validation succeeded
4. If any files fail, list the minimum changes needed to pass the quality gate

Do not approve work that has not passed validation.
""",
    "tapps-review-fixer.md": """\
---
name: tapps-review-fixer
description: >-
  Combined review and fix agent. Scores a Python file, fixes issues found,
  and validates the result passes the quality gate. Use in worktrees for
  parallel multi-file review pipelines.
model: sonnet
readonly: false
is_background: false
tools:
  - code_search
  - read_file
  - edit_file
  - run_terminal_command
---

You are a TappsMCP review-fixer agent. For each file assigned to you:

1. Call `tapps_score_file` to get the full 7-category breakdown
2. Call `tapps_security_scan` to check for security issues
3. Call `tapps_dead_code` to detect unused code
4. Fix all issues found: lint violations, security findings, dead code
5. Call `tapps_quality_gate` to verify the file passes
6. If the gate fails, fix remaining issues and re-run the gate
7. Report: file path, before/after scores, fixes applied, gate pass/fail

Be thorough but minimal - only change what is needed to pass the quality gate.
Do not refactor beyond what the issues require.
""",
    "tapps-frontend-reviewer.md": """\
---
name: tapps-frontend-reviewer
description: >-
  Review UI/UX and frontend changes using domain playbooks and TAPPS quality
  gates. Use for React, CSS, accessibility, or layout work.
model: sonnet
readonly: false
is_background: false
tools:
  - code_search
  - read_file
  - edit_file
---

You are a TappsMCP frontend reviewer. When invoked:

1. Call `tapps_domain_playbook` with `domain="user-experience"` (or alias `frontend`)
2. Call `tapps_lookup_docs` for the UI library in use (React, Next.js, etc.)
3. Review changed files against the playbook checklist (a11y, layout, UX)
4. Call `tapps_quick_check` on any changed Python/TS files
5. Summarize findings and recommend `/tapps-finish-task` before declaring done

Optional persona voice: agency-agents Frontend Developer — TappsMCP owns all gates.
""",
}


def _with_scope_rule(template: str) -> str:
    """Append the shared project-scope rule to an agent template body.

    Every deployed agent gets the same trailing scope guard so the rule is
    enforced consistently regardless of which agent runs.
    """
    return template.rstrip() + "\n" + _PROJECT_SCOPE_RULE


def generate_subagent_definitions(
    project_root: Path,
    platform: str,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Generate subagent definition files for the given platform.

    Creates 5 agent ``.md`` files in ``.claude/agents/`` or ``.cursor/agents/``
    depending on the platform. Existing files are skipped to preserve
    user customizations unless *overwrite* is ``True`` (used by the
    upgrade path to refresh corrected frontmatter).

    Each agent receives the shared :data:`_PROJECT_SCOPE_RULE` appended to its
    prompt body so deployed agents stay scoped to the deploying project.

    Returns a summary dict with ``created``, ``updated``, and ``skipped`` lists.
    """
    if platform == "claude":
        agents_dir = project_root / ".claude" / "agents"
        templates = CLAUDE_AGENTS
    elif platform == "cursor":
        agents_dir = project_root / ".cursor" / "agents"
        templates = CURSOR_AGENTS
    else:
        return {"created": [], "skipped": [], "error": f"Unknown platform: {platform}"}

    agents_dir.mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    updated: list[str] = []
    skipped: list[str] = []
    for name, raw_content in templates.items():
        content = _with_scope_rule(raw_content)
        target = agents_dir / name
        if target.exists():
            if overwrite:
                target.write_text(content, encoding="utf-8")
                updated.append(name)
            else:
                skipped.append(name)
        else:
            target.write_text(content, encoding="utf-8")
            created.append(name)

    return {"created": created, "updated": updated, "skipped": skipped}
