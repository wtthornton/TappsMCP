"""Domain and role-flow skill templates (ADR-0025)."""

from __future__ import annotations

_DOMAIN_FINISH = """\
6. **Close out.** Invoke `/tapps-finish-task` with the task_type from the playbook response. Do not declare done without validate + checklist.
"""

_DOMAIN_STEP_PLAYBOOK = """\
1. **Session bootstrap.** Call `tapps_session_start()` if not already called this session.
2. **Load playbook.** Call `tapps_domain_playbook(domain="{domain}")` (or read bundled checklist from the response). Follow its workflow and checklist.
3. **Library docs.** For each entry in `lookup_hints`, call `tapps_lookup_docs(library=..., topic=...)` before using those APIs.
4. **Domain tools.** Run the tools listed in `recommended_tools` on changed files in scope.
5. **Edit loop.** After each Python file change, call `tapps_quick_check(file_path=...)`.
"""

_CLAUDE_DOMAIN_TOOLS = (
    "mcp__nlt-build__tapps_session_start "
    "mcp__nlt-build__tapps_domain_playbook "
    "mcp__nlt-build__tapps_lookup_docs "
    "mcp__nlt-build__tapps_quick_check "
    "mcp__nlt-build__tapps_validate_changed "
    "mcp__nlt-build__tapps_checklist"
)

_CURSOR_DOMAIN_TOOLS = [
    "tapps_session_start",
    "tapps_domain_playbook",
    "tapps_lookup_docs",
    "tapps_quick_check",
    "tapps_validate_changed",
    "tapps_checklist",
]


def _claude_domain_skill(
    name: str,
    description: str,
    domain: str,
    extra_tools: str = "",
    extra_steps: str = "",
    task_type: str = "feature",
) -> str:
    tools = _CLAUDE_DOMAIN_TOOLS + (f" {extra_tools}" if extra_tools else "")
    body = _DOMAIN_STEP_PLAYBOOK.format(domain=domain) + extra_steps + _DOMAIN_FINISH
    body = body.replace(
        "task_type from the playbook response",
        f"task_type={task_type}",
    )
    return f"""\
---
name: {name}
user-invocable: true
model: claude-sonnet-4-6
description: >-
  {description}
allowed-tools: {tools}
argument-hint: "[file-path or scope]"
---

Domain playbook workflow — same quality gate as the standard TAPPS pipeline.

{body}
"""


def _cursor_domain_skill(
    name: str,
    description: str,
    domain: str,
    extra_tools: list[str] | None = None,
    extra_steps: str = "",
    task_type: str = "feature",
) -> str:
    tools = _CURSOR_DOMAIN_TOOLS + (extra_tools or [])
    tools_yaml = "\n".join(f"  - {t}" for t in tools)
    body = _DOMAIN_STEP_PLAYBOOK.format(domain=domain) + extra_steps + _DOMAIN_FINISH
    body = body.replace(
        "task_type from the playbook response",
        f"task_type={task_type}",
    )
    body = body.replace("`tapps_", "`").replace("mcp__nlt-build__", "")
    return f"""\
---
name: {name}
description: >-
  {description}
mcp_tools:
{tools_yaml}
---

Domain playbook workflow — same quality gate as the standard TAPPS pipeline.

{body}
"""


CLAUDE_DOMAIN_SKILLS: dict[str, str] = {
    "tapps-domain-security": _claude_domain_skill(
        "tapps-domain-security",
        "Security-focused TAPPS workflow: playbook, library docs, security scan, and CVE check. "
        "Use when implementing auth, secrets, input validation, or pre-release security passes.",
        "security",
        extra_tools="mcp__nlt-build__tapps_security_scan mcp__nlt-build__tapps_dependency_scan",
        extra_steps=(
            "4b. Run `tapps_security_scan` on sensitive changed files.\n"
            "4c. Run `tapps_dependency_scan` when lockfiles or dependencies changed.\n"
        ),
        task_type="security",
    ),
    "tapps-domain-testing": _claude_domain_skill(
        "tapps-domain-testing",
        "Testing-focused TAPPS workflow: playbook, pytest docs, diff impact, and validation. "
        "Use when adding tests, fixing test gaps, or validating affected tests after refactors.",
        "testing-strategies",
        extra_tools="mcp__nlt-build__tapps_diff_impact mcp__nlt-build__tapps_call_graph",
        extra_steps="4b. Call `tapps_diff_impact(file_paths=...)` to rank affected tests.\n",
        task_type="qa",
    ),
    "tapps-domain-frontend": _claude_domain_skill(
        "tapps-domain-frontend",
        "Frontend/UX TAPPS workflow: playbook, UI library docs, and quality gate on scored files. "
        "Use when building UI components, accessibility fixes, or client-side routing changes.",
        "user-experience",
        extra_tools="mcp__nlt-build__tapps_score_file",
        task_type="frontend",
    ),
    "tapps-flow-develop": """\
---
name: tapps-flow-develop
user-invocable: true
model: claude-haiku-4-5-20251001
description: >-
  Standard feature/bugfix development flow via the shared TAPPS pipeline.
  Use when starting daily implementation work and you want session start,
  lookup docs, quick_check loop, and finish-task without a domain specialist.
allowed-tools: mcp__nlt-build__tapps_session_start mcp__nlt-build__tapps_lookup_docs mcp__nlt-build__tapps_quick_check mcp__nlt-build__tapps_validate_changed mcp__nlt-build__tapps_checklist Bash
argument-hint: "[task_type: feature|bugfix]"
---

1. `tapps_session_start()`
2. `tapps_lookup_docs` before each external library API
3. Edit loop: `tapps_quick_check` after Python edits
4. `/tapps-finish-task` with `task_type=feature` or `bugfix`
""",
    "tapps-flow-review": """\
---
name: tapps-flow-review
user-invocable: true
model: claude-sonnet-4-6
description: >-
  QA/review flow: parallel review pipeline or single-file review ending in checklist.
  Use when reviewing PRs, audit findings, or validating another agent's changes.
allowed-tools: mcp__nlt-build__tapps_validate_changed mcp__nlt-build__tapps_checklist mcp__nlt-build__tapps_security_scan
argument-hint: "[file paths]"
---

Prefer `/tapps-review-pipeline` for multiple Python files. Otherwise:

1. `tapps_security_scan` + `tapps_quick_check` on targets
2. `/tapps-finish-task` with `task_type=review` or `qa`
""",
    "tapps-flow-frontend": """\
---
name: tapps-flow-frontend
user-invocable: true
model: claude-sonnet-4-6
description: >-
  Frontend work flow combining UX playbook and standard finish pipeline.
  Use when the task is primarily UI/UX implementation or accessibility.
allowed-tools: mcp__nlt-build__tapps_session_start mcp__nlt-build__tapps_domain_playbook mcp__nlt-build__tapps_lookup_docs mcp__nlt-build__tapps_quick_check mcp__nlt-build__tapps_validate_changed mcp__nlt-build__tapps_checklist
---

1. Invoke `/tapps-domain-frontend` steps 1–5, **or** run this shortcut:
   - `tapps_domain_playbook(domain="user-experience")`
   - `tapps_lookup_docs` for UI libraries in scope
2. `/tapps-finish-task` with `task_type=frontend`
3. Optional persona: agency-agents Frontend Developer (voice only; TappsMCP owns gates)
""",
}

CURSOR_DOMAIN_SKILLS: dict[str, str] = {
    "tapps-domain-security": _cursor_domain_skill(
        "tapps-domain-security",
        "Security-focused TAPPS workflow: playbook, library docs, security scan, and CVE check. "
        "Use when implementing auth, secrets, input validation, or pre-release security passes.",
        "security",
        extra_tools=["tapps_security_scan", "tapps_dependency_scan"],
        extra_steps=(
            "4b. Run `tapps_security_scan` on sensitive changed files.\n"
            "4c. Run `tapps_dependency_scan` when lockfiles or dependencies changed.\n"
        ),
        task_type="security",
    ),
    "tapps-domain-testing": _cursor_domain_skill(
        "tapps-domain-testing",
        "Testing-focused TAPPS workflow: playbook, pytest docs, diff impact, and validation. "
        "Use when adding tests, fixing test gaps, or validating affected tests after refactors.",
        "testing-strategies",
        extra_tools=["tapps_diff_impact", "tapps_call_graph"],
        extra_steps="4b. Call `tapps_diff_impact(file_paths=...)` to rank affected tests.\n",
        task_type="qa",
    ),
    "tapps-domain-frontend": _cursor_domain_skill(
        "tapps-domain-frontend",
        "Frontend/UX TAPPS workflow: playbook, UI library docs, and quality gate on scored files. "
        "Use when building UI components, accessibility fixes, or client-side routing changes.",
        "user-experience",
        extra_tools=["tapps_score_file"],
        task_type="frontend",
    ),
    "tapps-flow-develop": """\
---
name: tapps-flow-develop
description: >-
  Standard feature/bugfix development flow via the shared TAPPS pipeline.
  Use when starting daily implementation work and you want session start,
  lookup docs, quick_check loop, and finish-task without a domain specialist.
mcp_tools:
  - tapps_session_start
  - tapps_lookup_docs
  - tapps_quick_check
  - tapps_validate_changed
  - tapps_checklist
---

1. `tapps_session_start()`
2. `tapps_lookup_docs` before each external library API
3. Edit loop: `tapps_quick_check` after Python edits
4. `/tapps-finish-task` with `task_type=feature` or `bugfix`
""",
    "tapps-flow-review": """\
---
name: tapps-flow-review
description: >-
  QA/review flow: parallel review pipeline or single-file review ending in checklist.
  Use when reviewing PRs, audit findings, or validating another agent's changes.
mcp_tools:
  - tapps_validate_changed
  - tapps_checklist
  - tapps_security_scan
---

Prefer `/tapps-review-pipeline` for multiple Python files. Otherwise:

1. `tapps_security_scan` + `tapps_quick_check` on targets
2. `/tapps-finish-task` with `task_type=review` or `qa`
""",
    "tapps-flow-frontend": """\
---
name: tapps-flow-frontend
description: >-
  Frontend work flow combining UX playbook and standard finish pipeline.
  Use when the task is primarily UI/UX implementation or accessibility.
mcp_tools:
  - tapps_session_start
  - tapps_domain_playbook
  - tapps_lookup_docs
  - tapps_quick_check
  - tapps_validate_changed
  - tapps_checklist
---

1. Invoke `/tapps-domain-frontend` steps 1–5, **or** run this shortcut:
   - `tapps_domain_playbook(domain="user-experience")`
   - `tapps_lookup_docs` for UI libraries in scope
2. `/tapps-finish-task` with `task_type=frontend`
3. Optional persona: agency-agents Frontend Developer (voice only; TappsMCP owns gates)
""",
}
