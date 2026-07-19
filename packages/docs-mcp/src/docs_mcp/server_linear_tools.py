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

import asyncio
import threading
import time
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from docs_mcp.linters.linear_issue import lint_issue
from docs_mcp.mcp_register import register_tool
from docs_mcp.server import _ANNOTATIONS_READ_ONLY, _META_DEFERRED, _record_call
from docs_mcp.server_helpers import success_response
from docs_mcp.triage.linear_issue import triage_issues
from docs_mcp.validators.linear_issue import validate_issue

_logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# TAP-2007: PR-shape procedural pattern write (once per session)
# ---------------------------------------------------------------------------

_pr_shape_lock = threading.Lock()
_pr_shape_written: bool = False


def _reset_pr_shape_written() -> None:
    """Reset the per-session flag (for tests and process hygiene)."""
    global _pr_shape_written
    with _pr_shape_lock:
        _pr_shape_written = False


async def _write_pr_shape_to_brain(common_rules: list[str]) -> None:
    """Write a procedural PR-shape memory via the tapps_core brain bridge.

    Best-effort — never raises.  Uses the supersede-then-save pattern so
    repeat invocations across multiple sessions update rather than orphan.
    """
    key = "procedural.pr-shape.session"
    rules_str = ", ".join(common_rules[:5]) if common_rules else "none"
    value = (
        f"Agent-ready Linear issue shape: score threshold 100, "
        f"requires ## What / ## Where (file:LINE anchor) / ## Why / ## Acceptance (checkboxes) / ## Refs. "
        f"Common lint rules seen: [{rules_str}]. "
        f"Use docs_lint_linear_issue to pre-validate before create."
    )[:1024]
    tags = ["procedural", "pr-shape", "auto-captured", "docs-mcp"]

    try:
        from tapps_core.brain_bridge import create_brain_bridge

        bridge = create_brain_bridge(settings=None)
        if bridge is None:
            return

        # Try supersede first (preserves history chain on regen)
        if hasattr(bridge, "supersede"):
            try:
                sup: dict[str, Any] | None = await bridge.supersede(key=key, new_value=value)
                if sup is not None and not (
                    isinstance(sup, dict) and sup.get("error") == "not_found"
                ):
                    _logger.debug("pr_shape_supersede_ok")
                    return
            except Exception:
                pass

        await bridge.save(
            key=key,
            value=value,
            tier="procedural",
            source="agent",
            source_agent="docs-mcp",
            scope="project",
            tags=tags,
            skip_consolidation=True,
        )
        _logger.debug("pr_shape_save_ok")
    except Exception:
        _logger.debug("pr_shape_write_failed", exc_info=True)


def _fire_pr_shape_pattern(lint_result_dict: dict[str, Any]) -> None:
    """Schedule the PR-shape procedural write once per session (fire-and-forget).

    Only fires when the linted issue is agent-ready.  Deduplicates via the
    module-level ``_pr_shape_written`` flag so only one write is emitted per
    MCP server process lifetime.
    """
    global _pr_shape_written
    if not lint_result_dict.get("agent_ready"):
        return
    with _pr_shape_lock:
        if _pr_shape_written:
            return
        _pr_shape_written = True

    common_rules = [f["rule"] for f in lint_result_dict.get("findings", [])[:5]]
    try:
        # Fire-and-forget best-effort write; no reference kept on purpose.
        asyncio.create_task(_write_pr_shape_to_brain(common_rules))  # noqa: RUF006
    except Exception:
        pass
    _logger.info("pr_shape_pattern_scheduled")


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
    - ``suggested_label``: ``"spec-ready"`` for agent-ready issues, ``""``
      otherwise.
    - ``suggested_status``: ``"Backlog"`` (agent-ready, queued for pickup)
      or ``"Triage"`` (needs spec/review or is blocked on a human decision).
      Agents using status-based gating should read this rather than
      ``suggested_label``.
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

    result_dict = result.to_dict()

    # TAP-2007: write PR-shape procedural memory once per session on agent-ready lint.
    _fire_pr_shape_pattern(result_dict)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    next_steps = _build_next_steps(result_dict)

    return success_response(
        "docs_lint_linear_issue",
        elapsed_ms,
        result_dict,
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
            f"Move issue to `{result['suggested_status']}` status until HIGH findings are resolved."
        )
    elif result["score"] < 100:
        steps.append(
            f"Issue is spec-ready (score {result['score']}); clean up medium/low findings when touching."
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
    project_root: str = "",
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
        - ``suggested_label``: ``"spec-ready"`` for agent-ready issues,
          ``""`` otherwise.
        - ``suggested_status``: ``"Backlog"`` (agent-ready) or ``"Triage"``
          (needs spec/review or human decision). Read this rather than
          ``suggested_label`` when using status-based workflow gating.

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
        project_root: Optional override for project root directory. Defaults
            to the DocsMCP project root detected from settings. The gate
            sentinel is written under ``{project_root}/.tapps-mcp/`` when
            ``agent_ready=true``.
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
    if data.get("agent_ready"):
        _persist_validate_sentinel(project_root)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    next_steps = _validate_next_steps(data)

    return success_response(
        "docs_validate_linear_issue",
        elapsed_ms,
        data,
        next_steps=next_steps,
    )


def _persist_validate_sentinel(project_root: str) -> None:
    """Write the linear-write gate sentinel after a passing validation."""
    from pathlib import Path

    from docs_mcp.config.settings import load_docs_settings
    from docs_mcp.integrations.linear_gateway import write_validate_sentinel

    try:
        root_override = Path(project_root) if project_root.strip() else None
        settings = load_docs_settings(root_override)
        if not write_validate_sentinel(settings.project_root):
            _logger.warning("validate_sentinel_write_failed", root=str(settings.project_root))
    except Exception:
        _logger.warning("validate_sentinel_write_failed", exc_info=True)


def _validate_next_steps(data: dict[str, Any]) -> list[str]:
    """Up to 2 imperative next steps for the validator response."""
    steps: list[str] = []
    if data["missing"]:
        items = ", ".join(data["missing"][:2])
        steps.extend(
            (
                f"Add before creating: {items}.",
                (
                    f"Until resolved, the issue belongs in `{data['suggested_status']}` status. "
                    "For deeper cleanup, call docs_lint_linear_issue."
                ),
            )
        )
    else:
        steps.extend(
            (
                (
                    f"Issue is spec-ready (score {data['score']}). "
                    "Call docs_save_linear_issue(title, description), then save_issue."
                ),
                (
                    f"Create in `{data['suggested_status']}` status "
                    f"(label `{data['suggested_label']}` when applicable)."
                ),
            )
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
        1. ``list_issues`` (Linear MCP) with explicit narrowing —
           always pass ``team``, ``project``, ``state`` (``"backlog"``
           or ``"unstarted"``), and ``includeArchived=False``. Broad
           queries waste Linear quota; narrow ones cache well.
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
            "labels": ["Bug", "spec-ready"],
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
            f"{non_ready}/{total} issues are not spec-ready — see per_issue.missing for each."
        )
    return steps[:3]


async def docs_save_linear_issue(
    title: str,
    description: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Pre-save gate for Linear issues (TAP-2009).

    Checks whether ``docs_validate_linear_issue`` has been called recently
    (within 30 minutes) before allowing a Linear ``save_issue`` to proceed.

    When the gate passes, returns ``{ok: true}`` — the agent should then call
    ``mcp__plugin_linear_linear__save_issue`` with the same title and
    description.  When the gate fires, returns the standard
    ``validate_missing`` refusal envelope (see
    ``docs/architecture/gateway-envelope.md``); call
    ``docs_validate_linear_issue`` first to satisfy the gate.

    This is the server-side counterpart to
    ``.claude/hooks/tapps-pre-linear-write.sh``, providing defence-in-depth
    when hooks are absent (other MCP clients, CI, read-only Claude Code
    configs).

    Args:
        title: Issue title — passed through to the refusal envelope so the
            agent knows which ``docs_validate_linear_issue`` call will satisfy
            the gate.
        description: Issue description (markdown) — same pass-through purpose.
        project_root: Optional override for project root directory. Defaults
            to the DocsMCP project root detected from settings.
    """
    _record_call("docs_save_linear_issue")
    start = time.perf_counter_ns()

    from pathlib import Path

    from docs_mcp.config.settings import load_docs_settings
    from docs_mcp.integrations.linear_gateway import gate_linear_save
    from docs_mcp.server_helpers import error_response

    try:
        root_override = Path(project_root) if project_root.strip() else None
        settings = load_docs_settings(root_override)
    except Exception as exc:
        return error_response("docs_save_linear_issue", "CONFIG_ERROR", str(exc))

    refusal = gate_linear_save(settings.project_root, title, description)
    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    if refusal is not None:
        return success_response(
            "docs_save_linear_issue",
            elapsed_ms,
            refusal,
            next_steps=[
                f"Call docs_validate_linear_issue(title={title!r}, description=...) first.",
                "Confirm agent_ready=true, then call docs_save_linear_issue again.",
            ],
        )

    return success_response(
        "docs_save_linear_issue",
        elapsed_ms,
        {
            "ok": True,
            "message": (
                "Gate passed — call mcp__plugin_linear_linear__save_issue "
                "with the same title and description params."
            ),
        },
        next_steps=[
            "Call mcp__plugin_linear_linear__save_issue(team, project, title, description, ...) now.",
        ],
    )


def register(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register Linear-issue tools on the shared mcp instance.

    TAP-1987: docs_lint_linear_issue and docs_validate_linear_issue are daily
    drivers (eager). docs_linear_triage is deferred.
    TAP-2009: docs_save_linear_issue is a daily-driver gate (eager).
    """
    if "docs_lint_linear_issue" in allowed_tools:
        register_tool(mcp_instance, docs_lint_linear_issue, annotations=_ANNOTATIONS_READ_ONLY)
    if "docs_validate_linear_issue" in allowed_tools:
        register_tool(mcp_instance, docs_validate_linear_issue, annotations=_ANNOTATIONS_READ_ONLY)
    if "docs_linear_triage" in allowed_tools:
        register_tool(
            mcp_instance,
            docs_linear_triage,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta=_META_DEFERRED,
        )
    if "docs_save_linear_issue" in allowed_tools:
        register_tool(mcp_instance, docs_save_linear_issue, annotations=_ANNOTATIONS_READ_ONLY)
