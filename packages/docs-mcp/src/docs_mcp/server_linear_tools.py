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
    - ``docs_linear_triage`` — batch triage of N issues; proposes labels
      and parent groupings.

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
from docs_mcp.triage.linear_issue import triage_issues
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


async def docs_linear_triage(
    issues: list[dict[str, Any]],
    enable_parent_grouping: bool = True,
) -> dict[str, Any]:
    """Batch-triage N Linear issues. Read-only proposals; no Linear writes.

    The agent fetches issues via the Linear MCP plugin and passes the
    payload list here. The tool runs each issue through the validator,
    aggregates label proposals, clusters issues that share file paths
    into parent-grouping candidates, and summarizes metadata gaps.

    Typical workflow:
        1. ``list_issues`` (Linear MCP) → collect open issues.
        2. Reshape into this tool's input schema.
        3. Call ``docs_linear_triage(issues=[...])``.
        4. Review ``label_proposals`` / ``parent_groupings`` with the user.
        5. Apply approved changes via Linear MCP ``save_issue``.

    Input schema — each dict supports these keys (``id``, ``title``,
    ``description`` are the only load-bearing ones):

        {
            "id": "TAP-686",
            "title": "upgrade.py: rglob traverses node_modules",
            "description": "## What\\n...",
            "labels": ["Bug", "agent-ready"],
            "priority": 2,
            "estimate": 2.0,
            "parent_id": "TAP-400",
            "is_epic": false
        }

    Returns a ``TriageReport`` with:
        - ``per_issue``: validator results per issue + extracted file paths.
        - ``label_proposals``: ``{issue_id, from_label, to_label, reason}``
          only for issues whose current agent-label differs from the
          suggested one.
        - ``parent_groupings``: ``{shared_path, issue_ids,
          proposed_parent_title}`` for paths shared by ≥2 issues.
        - ``metadata_gaps``: ``{no_priority, no_estimate}`` issue-id lists.
        - ``summary``: aggregate counts + average score.

    Args:
        issues: List of issue payloads. Each dict needs at minimum
            ``id``, ``title``, ``description``.
        enable_parent_grouping: When False, skips file-path clustering
            (cheaper for very large batches). Default True.
    """
    _record_call("docs_linear_triage")
    start = time.perf_counter_ns()

    report = triage_issues(issues)
    data = report.model_dump()

    if not enable_parent_grouping:
        data["parent_groupings"] = []

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    next_steps = _triage_next_steps(data)

    return success_response(
        "docs_linear_triage",
        elapsed_ms,
        data,
        next_steps=next_steps,
    )


def _triage_next_steps(data: dict[str, Any]) -> list[str]:
    """Up to 3 imperative next steps summarizing the triage output."""
    steps: list[str] = []
    summary = data["summary"]
    total = summary["total"]
    ready = summary["agent_ready"]

    if data["label_proposals"]:
        steps.append(
            f"Review {len(data['label_proposals'])} label change(s) and apply via Linear MCP."
        )
    if data["parent_groupings"]:
        top = data["parent_groupings"][0]
        steps.append(
            f"Consider grouping {len(top['issue_ids'])} issues under a parent for "
            f"`{top['shared_path']}` (+{len(data['parent_groupings']) - 1} more clusters)."
        )
    if summary["needs_clarification"] > 0 or summary["agent_blocked"] > 0:
        non_ready = total - ready
        steps.append(
            f"{non_ready}/{total} issues are not agent-ready — see per_issue.missing for each."
        )
    return steps[:3]


def register(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register Linear-issue tools on the shared mcp instance."""
    if "docs_lint_linear_issue" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(docs_lint_linear_issue)
    if "docs_validate_linear_issue" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(docs_validate_linear_issue)
    if "docs_linear_triage" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(docs_linear_triage)
