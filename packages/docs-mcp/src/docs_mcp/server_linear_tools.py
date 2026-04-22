"""DocsMCP Linear-issue tools.

Tools that operate on Linear issue payloads (title + description + metadata).
The agent fetches issues via the Linear MCP plugin and passes the payload in;
these tools do not call the Linear API themselves — they stay deterministic
and dependency-free.

Current tools:
    - ``docs_lint_linear_issue`` — rule-based lint against
      ``docs/linear/AGENT_ISSUES.md``.
    - ``docs_validate_linear_issue`` — pre-create gate returning
      ``{agent_ready, missing, score}``.

Policy reference: ``docs/linear/AGENT_ISSUES.md``.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from docs_mcp.linters.linear_issue import lint_issue
from docs_mcp.server import _ANNOTATIONS_READ_ONLY, _record_call
from docs_mcp.server_helpers import success_response
from docs_mcp.validators.linear_issue import validate_issue

_logger = structlog.get_logger(__name__)


async def docs_lint_linear_issue(
    title: str,
    description: str = "",
    labels: str = "",
    priority: int = -1,
    estimate: float = -1.0,
    parent_id: str = "",
    is_epic: bool = False,
) -> dict[str, Any]:
    """Lint one Linear issue against the TappsMCP agent-issue template.

    Evaluates title + description + metadata against the rules in
    ``docs/linear/AGENT_ISSUES.md`` and returns:

    - ``agent_ready``: bool — True iff no HIGH-severity violations.
    - ``score``: 0-100, starting at 100 with per-finding penalties.
    - ``findings``: list of ``{rule, severity, message, location, fix_hint}``.
    - ``suggested_label``: one of ``agent-ready`` / ``needs-clarification`` /
      ``agent-blocked``.
    - ``tokens``: ``{title_chars, description_chars, total_chars,
      estimated_tokens, noise_bytes_recoverable}``.

    The agent should call a Linear-MCP ``get_issue`` first and pass the fields
    in here. This tool never calls Linear directly — it stays deterministic
    so the same payload produces the same result.

    Args:
        title: Issue title. Required.
        description: Issue description (markdown). Default empty.
        labels: Comma-separated label names applied to the issue.
        priority: Linear priority (0=None, 1=Urgent, 2=High, 3=Normal,
            4=Low). Use ``-1`` to indicate "not provided" — that triggers a
            ``missing-priority`` finding.
        estimate: Story-point estimate. Use ``-1`` to indicate "not
            provided" — triggers a ``missing-estimate`` finding for
            non-epic issues.
        parent_id: Parent issue identifier (e.g. ``TAP-410``). Reserved
            for hierarchy-aware rules; currently informational.
        is_epic: When True, epic-specific rules apply (file anchor and
            estimate requirements relaxed).
    """
    _record_call("docs_lint_linear_issue")
    start = time.perf_counter_ns()

    labels_list = [lbl.strip() for lbl in labels.split(",") if lbl.strip()] if labels else []
    priority_val: int | None = priority if priority >= 0 else None
    estimate_val: float | None = estimate if estimate >= 0 else None

    result = lint_issue(
        title=title,
        description=description,
        labels=labels_list,
        priority=priority_val,
        estimate=estimate_val,
        parent_id=parent_id,
        is_epic=is_epic,
    )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    next_steps = _build_next_steps(result.to_dict())

    return success_response(
        "docs_lint_linear_issue",
        elapsed_ms,
        result.to_dict(),
        next_steps=next_steps,
    )


def _build_next_steps(result: dict[str, Any]) -> list[str]:
    """Up to 3 imperative next steps derived from findings."""
    steps: list[str] = []
    high = [f for f in result["findings"] if f["severity"] == "high"]
    if high:
        first = high[0]
        steps.append(f"Fix high-severity rule `{first['rule']}`: {first['fix_hint']}")
    if result["tokens"]["noise_bytes_recoverable"] > 0:
        steps.append(
            f"Reclaim ~{result['tokens']['noise_bytes_recoverable']} chars of noise "
            "(autolinker/UUID wrappers) — see findings."
        )
    if not result["agent_ready"]:
        steps.append(
            f"Apply label `{result['suggested_label']}` until HIGH findings are resolved."
        )
    elif result["score"] < 100:
        steps.append(
            f"Issue is agent-ready (score {result['score']}); clean up medium/low findings when touching."
        )
    return steps[:3]


async def docs_validate_linear_issue(
    title: str,
    description: str = "",
    labels: str = "",
    priority: int = -1,
    estimate: float = -1.0,
    parent_id: str = "",
    is_epic: bool = False,
) -> dict[str, Any]:
    """Pre-create gate for a Linear issue.

    Where ``docs_lint_linear_issue`` returns every rule violation with
    severity and fix hints, this tool answers one binary question: "Can an
    agent pick this up without human input?" The response is terser and
    designed for pre-creation gating or batch triage.

    Returns:
        - ``agent_ready``: True iff zero HIGH-severity findings.
        - ``score``: 0-100 (same scoring as the lint tool).
        - ``missing``: list of human-phrased items to add
          (e.g., "a file anchor", "a `## Acceptance` section").
        - ``issues``: per-field structured detail
          (``{severity, field, rule, message}``).
        - ``suggested_label``: one of ``agent-ready`` /
          ``needs-clarification`` / ``agent-blocked``.

    Agents should call this BEFORE creating a Linear issue. If
    ``agent_ready`` is False, fix the ``missing`` items first. For a deeper
    audit of an existing issue (token waste, style nits, fix hints), use
    ``docs_lint_linear_issue`` instead.

    Args:
        title: Issue title. Required.
        description: Issue description (markdown).
        labels: Comma-separated label names.
        priority: Linear priority (0=None, 1=Urgent, 2=High, 3=Normal,
            4=Low). ``-1`` means not provided.
        estimate: Story-point estimate. ``-1`` means not provided.
        parent_id: Parent issue identifier (reserved for hierarchy rules).
        is_epic: When True, relaxes file-anchor and estimate requirements.
    """
    _record_call("docs_validate_linear_issue")
    start = time.perf_counter_ns()

    labels_list = [lbl.strip() for lbl in labels.split(",") if lbl.strip()] if labels else []
    priority_val: int | None = priority if priority >= 0 else None
    estimate_val: float | None = estimate if estimate >= 0 else None

    report = validate_issue(
        title=title,
        description=description,
        labels=labels_list,
        priority=priority_val,
        estimate=estimate_val,
        parent_id=parent_id,
        is_epic=is_epic,
    )

    data = report.model_dump()
    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    next_steps = _validate_next_steps(data)

    return success_response(
        "docs_validate_linear_issue",
        elapsed_ms,
        data,
        next_steps=next_steps,
    )


def _validate_next_steps(data: dict[str, Any]) -> list[str]:
    """Up to 2 imperative next steps for the validator response."""
    steps: list[str] = []
    if data["missing"]:
        items = ", ".join(data["missing"][:2])
        steps.append(f"Add before creating: {items}.")
        steps.append(
            f"Once resolved, label `{data['suggested_label']}`. "
            "For deeper cleanup, call docs_lint_linear_issue."
        )
    else:
        steps.append(
            f"Issue is agent-ready (score {data['score']}). "
            f"Apply label `{data['suggested_label']}` and create."
        )
    return steps[:2]


def register(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register Linear-issue tools on the shared mcp instance."""
    if "docs_lint_linear_issue" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(docs_lint_linear_issue)
    if "docs_validate_linear_issue" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(docs_validate_linear_issue)
