"""Canonical developer workflow content: Setup, Update, Daily, and when-to-use.

Single source of truth for tapps_session_start quick_start, tapps_init
developer_workflow response, and docs/TAPPS_WORKFLOW.md.
"""

from __future__ import annotations

DAILY_STEPS = [
    "1. FIRST: Call tapps_session_start() to initialize the session",
    "2. BEFORE using any library API: Call tapps_lookup_docs(library='<name>')",
    "3. DURING edits: Call tapps_quick_check(file_path='<path>') after each change",
    "4. BEFORE declaring done: Call tapps_validate_changed() - all gates MUST pass",
    "5. FINAL step: Call tapps_checklist(task_type='<type>') to verify completeness",
]

RECOMMENDED_WORKFLOW_TEXT = (
    "FIRST: Call tapps_session_start() to initialize. "
    "BEFORE using any library: Call tapps_lookup_docs(). "
    "AFTER editing Python files: "
    "Call tapps_score_file(quick=True) or tapps_quick_check(). "
    "BEFORE declaring done: Call tapps_validate_changed() or tapps_quality_gate(). "
    "FINAL step: Call tapps_checklist()."
)

SETUP_STEPS = [
    "Run tapps_doctor (optional) to verify MCP and checkers.",
    "Run tapps_init to bootstrap AGENTS.md, rules, hooks, skills.",
]

UPDATE_STEP = (
    "After upgrading TappsMCP (or pulling a new version), run tapps_upgrade. "
    "Optionally run tapps_doctor to verify."
)

WHEN_TO_USE = [
    ("tapps_lookup_docs", "Before using any external library API."),
    ("tapps_impact_analysis", "Before changing or removing a file's public API."),
    ("tapps_security_scan", "For auth, API routes, secrets, input validation."),
    ("tapps_validate_config", "When editing Dockerfile, docker-compose, or infra config."),
]


def get_developer_workflow_dict(*, setup_done: bool = True) -> dict[str, object]:
    """Return the developer_workflow object for tapps_init (and similar) responses."""
    return {
        "setup_done": setup_done,
        "daily_steps": list(DAILY_STEPS),
        "update_step": UPDATE_STEP,
        "when_to_use": [{"tool": t, "when": w} for t, w in WHEN_TO_USE],
    }


def render_workflow_md() -> str:
    """Render docs/TAPPS_WORKFLOW.md content."""
    lines = [
        "# TappsMCP developer workflow",
        "",
        "Short reference for Setup, Update, and Daily use. For full tool reference see AGENTS.md.",
        "",
        "## Setup (once per project)",
        "",
    ]
    for step in SETUP_STEPS:
        lines.append(f"- {step}")
    lines.extend(
        [
            "",
            "## Update (after upgrading TappsMCP)",
            "",
            f"- {UPDATE_STEP}",
            "",
            "## Daily workflow",
            "",
            "Every session:",
            "",
        ]
    )
    for step in DAILY_STEPS:
        lines.append(f"- {step}")
    lines.extend(
        [
            "",
            "Use `task_type` in tapps_checklist: feature, bugfix, refactor, security, review, or epic.",
            "",
            "## When to use other tools",
            "",
        ]
    )
    for tool, when in WHEN_TO_USE:
        lines.append(f"- **{tool}** — {when}")
    lines.append("")
    return "\n".join(lines)
