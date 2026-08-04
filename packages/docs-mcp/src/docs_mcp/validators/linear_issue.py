"""Validator for Linear issue payloads.

Thin wrapper over ``docs_mcp.linters.linear_issue.lint_issue`` that exposes a
pre-create gate shape: ``{agent_ready, score, missing[], issues[],
suggested_label}``. Callers use this *before* creating an issue in Linear to
ensure an agent can actually pick it up without human clarification.

The linter is the source of truth for *which* rules exist and their severity;
this module only translates HIGH-severity findings into a human-phrased
``missing[]`` list of things to add (not things to remove — that's lint's job).
"""

from __future__ import annotations

from pydantic import BaseModel

from docs_mcp.linters.linear_issue import (
    ISSUE_KIND_IMPLEMENTABLE,
    RULE_ACCEPTANCE_EMPTY,
    RULE_ACCEPTANCE_PROSE,
    RULE_MISSING_ACCEPTANCE,
    RULE_MISSING_FILE_ANCHOR,
    RULE_MISSING_MAP_SECTIONS,
    RULE_MISSING_QUESTION,
    RULE_TITLE_TOO_LONG,
    SEVERITY_HIGH,
    Finding,
    lint_issue,
)

# Maps HIGH-severity rule IDs to a canonical "what to add" phrasing. Only HIGH
# rules are surfaced as ``missing`` — medium/low lint findings are improvements,
# not blockers.
_MISSING_PHRASING: dict[str, str] = {
    RULE_MISSING_FILE_ANCHOR: "a file anchor (e.g., `path/to/file.py:LINE-RANGE`)",
    RULE_MISSING_ACCEPTANCE: "a `## Acceptance` section",
    RULE_ACCEPTANCE_EMPTY: "at least one `- [ ]` checkbox under `## Acceptance`",
    RULE_ACCEPTANCE_PROSE: ("only `- [ ]` checkbox lines under `## Acceptance` (no bare prose)"),
    RULE_TITLE_TOO_LONG: "a non-empty title (pattern: `file.py: symptom`)",
    RULE_MISSING_QUESTION: "a `## Question` section",
    RULE_MISSING_MAP_SECTIONS: (
        "a map section (`## Destination`, `## Decisions so far`, "
        "`## Not yet specified`, or `## Out of scope`)"
    ),
}


class ValidationIssue(BaseModel):
    """One blocking structural issue on a Linear issue payload."""

    severity: str  # "error" for HIGH-severity lint findings
    field: str  # "title" | "description" | "metadata"
    rule: str
    message: str


class ValidationReport(BaseModel):
    """Pre-create gate result for one Linear issue.

    ``suggested_label`` is always ``""`` — the ``spec-ready`` label has been
    retired (TAP-1086). Readiness is expressed solely through
    ``suggested_status``: ``"Backlog"`` (agent-ready) or ``"Triage"``
    (needs spec/human decision).
    """

    agent_ready: bool
    score: int
    missing: list[str]
    issues: list[ValidationIssue]
    suggested_label: str
    suggested_status: str


def validate_issue(
    title: str,
    description: str = "",
    labels: list[str] | None = None,
    priority: int | None = None,
    estimate: float | None = None,
    parent_id: str = "",
    *,
    is_epic: bool = False,
    issue_kind: str = ISSUE_KIND_IMPLEMENTABLE,
) -> ValidationReport:
    """Validate an issue payload as a pre-create gate.

    Returns ``agent_ready=True`` iff there are zero HIGH-severity findings.
    ``missing`` is the human-phrased list of what to add; ``issues`` is the
    structured per-field detail.

    Args:
        issue_kind: One of ``"implementable"`` (default), ``"decision"``, or
            ``"map-parent"`` — see ``lint_issue`` for the per-kind rule
            differences (TAP-5497).
    """
    lint_result = lint_issue(
        title=title,
        description=description,
        labels=labels,
        priority=priority,
        estimate=estimate,
        parent_id=parent_id,
        is_epic=is_epic,
        issue_kind=issue_kind,
    )

    blocking: list[Finding] = [f for f in lint_result.findings if f.severity == SEVERITY_HIGH]

    missing: list[str] = []
    issues: list[ValidationIssue] = []
    seen_rules: set[str] = set()

    for finding in blocking:
        if finding.rule not in seen_rules:
            phrasing = _MISSING_PHRASING.get(finding.rule, finding.message)
            missing.append(phrasing)
            seen_rules.add(finding.rule)
        issues.append(
            ValidationIssue(
                severity="error",
                field=_field_from_location(finding.location),
                rule=finding.rule,
                message=finding.message,
            )
        )

    return ValidationReport(
        agent_ready=lint_result.agent_ready,
        score=lint_result.score,
        missing=missing,
        issues=issues,
        suggested_label=lint_result.suggested_label,
        suggested_status=lint_result.suggested_status,
    )


def _field_from_location(location: str) -> str:
    """Collapse linter locations ('title', 'description:L5', 'metadata') into
    the three-bucket field taxonomy used by the validator."""
    if location.startswith("description"):
        return "description"
    if location == "metadata":
        return "metadata"
    return "title"
