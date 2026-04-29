"""Batch triage of Linear issues.

Given a list of issue payloads (title + description + metadata), runs each
through the validator, aggregates label proposals, clusters issues that
share file paths into parent-grouping candidates, and summarizes metadata
gaps (missing priorities / estimates).

Read-only analysis. Does not write to Linear — the agent applies changes
via the Linear MCP plugin after user confirmation.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any

from pydantic import BaseModel, Field

from docs_mcp.validators.linear_issue import validate_issue

# Match any file path with a known source extension. Wider than the linter's
# anchor regex (which requires ``:LINE``) — for grouping we want every file
# mention, not just anchored ones.
_FILE_PATH_RE = re.compile(
    r"(?<![\w/])"
    r"([\w./\\-]+\.(?:py|pyi|ts|tsx|js|jsx|md|yaml|yml|toml|json|rs|go|java|rb|cpp|c|h))"
    r"(?=[\s:`,;)]|$)",
    re.MULTILINE,
)

# Paths matching any of these patterns are dropped from grouping — they
# don't carry meaningful co-change signal.
_NOISE_PATH_PATTERNS: tuple[str, ...] = (
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "pyproject.toml",
    "package.json",
    ".gitignore",
)

MIN_CLUSTER_SIZE = 2  # Paths shared by fewer issues aren't worth grouping.


class IssueTriageResult(BaseModel):
    """Per-issue triage output.

    ``suggested_label`` is always ``""`` — the ``spec-ready`` label has been
    retired (TAP-1086). Readiness is expressed solely through
    ``suggested_status`` (``"Backlog"`` = agent-ready, ``"Triage"`` = blocked).
    """

    id: str
    title: str
    agent_ready: bool
    score: int
    current_labels: list[str] = Field(default_factory=list)
    current_agent_label: str = ""  # Extracted from current_labels.
    suggested_label: str
    suggested_status: str
    missing: list[str] = Field(default_factory=list)
    file_paths: list[str] = Field(default_factory=list)


class LabelProposal(BaseModel):
    """A proposed label change for one issue."""

    issue_id: str
    from_label: str  # "" when no agent-label present.
    to_label: str
    reason: str


class ParentGrouping(BaseModel):
    """A proposed parent issue based on shared file paths."""

    shared_path: str
    issue_ids: list[str]
    proposed_parent_title: str


class MetadataGaps(BaseModel):
    """IDs of issues missing structured metadata."""

    no_priority: list[str] = Field(default_factory=list)
    no_estimate: list[str] = Field(default_factory=list)


class TriageSummary(BaseModel):
    """Aggregate counts for a Linear issue triage batch.

    Returned as part of :class:`TriageReport.summary`. ``agent_ready`` counts
    issues whose suggested status is ``Backlog``; ``needs_clarification``
    counts issues whose suggested status is ``Triage`` (combines what the
    old workflow split into ``needs-spec`` and ``agent-blocked`` labels).
    ``agent_blocked`` is retained as a field for backward compatibility but
    always reports 0 — the dimension was folded into Triage.
    """

    total: int
    agent_ready: int
    needs_clarification: int
    agent_blocked: int
    avg_score: float


class TriageReport(BaseModel):
    """Full output of :func:`triage_issues` for a batch of Linear issue payloads.

    Combines per-issue lint results, label proposals, parent-grouping
    candidates, metadata gap rollups, and an aggregate :class:`TriageSummary`.
    Consumed by the ``docs_linear_triage`` MCP tool and by agent workflows
    that want a single pass over a backlog before saving via the Linear
    plugin. Read-only — the triage function never calls Linear directly.
    """

    per_issue: list[IssueTriageResult]
    label_proposals: list[LabelProposal]
    parent_groupings: list[ParentGrouping]
    metadata_gaps: MetadataGaps
    summary: TriageSummary


_AGENT_LABELS: frozenset[str] = frozenset()


def triage_issues(issues: list[dict[str, Any]]) -> TriageReport:
    """Triage N Linear issue payloads.

    Each dict is expected to have ``id``, ``title``, and ``description`` at
    minimum; ``labels``, ``priority``, ``estimate``, ``parent_id``, ``is_epic``
    are optional. Missing keys default safely.
    """
    per_issue: list[IssueTriageResult] = []

    for raw in issues:
        result = _triage_one(raw)
        per_issue.append(result)

    label_proposals = _build_label_proposals(per_issue)
    parent_groupings = _build_parent_groupings(per_issue)
    metadata_gaps = _collect_metadata_gaps(per_issue, issues)
    summary = _summarize(per_issue)

    return TriageReport(
        per_issue=per_issue,
        label_proposals=label_proposals,
        parent_groupings=parent_groupings,
        metadata_gaps=metadata_gaps,
        summary=summary,
    )


def _triage_one(raw: dict[str, Any]) -> IssueTriageResult:
    issue_id = str(raw.get("id", ""))
    title = str(raw.get("title", ""))
    description = str(raw.get("description", ""))
    labels: list[str] = list(raw.get("labels") or [])
    priority = raw.get("priority")
    estimate = raw.get("estimate")
    parent_id = str(raw.get("parent_id", ""))
    is_epic = bool(raw.get("is_epic", False))

    report = validate_issue(
        title=title,
        description=description,
        labels=labels,
        priority=priority if isinstance(priority, int) else None,
        estimate=float(estimate) if isinstance(estimate, (int, float)) else None,
        parent_id=parent_id,
        is_epic=is_epic,
    )

    file_paths = _extract_file_paths(description)
    current_agent_label = _current_agent_label(labels)

    return IssueTriageResult(
        id=issue_id,
        title=title,
        agent_ready=report.agent_ready,
        score=report.score,
        current_labels=labels,
        current_agent_label=current_agent_label,
        suggested_label=report.suggested_label,
        suggested_status=report.suggested_status,
        missing=report.missing,
        file_paths=file_paths,
    )


def _current_agent_label(labels: list[str]) -> str:
    """Return the first agent-readiness label found, or '' if none."""
    for lbl in labels:
        if lbl in _AGENT_LABELS:
            return lbl
    return ""


def _extract_file_paths(description: str) -> list[str]:
    """Extract unique, normalized file paths from an issue description."""
    seen: set[str] = set()
    out: list[str] = []
    for match in _FILE_PATH_RE.finditer(description):
        raw_path = match.group(1)
        normalized = _normalize_path(raw_path)
        if not normalized or normalized in seen:
            continue
        if _is_noise_path(normalized):
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _normalize_path(path: str) -> str:
    """Normalize a captured file path: strip leading ./, collapse backslashes."""
    stripped = path.replace("\\", "/").lstrip("./")
    return stripped.strip()


def _is_noise_path(path: str) -> bool:
    return PurePosixPath(path).name in _NOISE_PATH_PATTERNS


def _build_label_proposals(results: list[IssueTriageResult]) -> list[LabelProposal]:
    """Propose removal of stale readiness labels (TAP-1086: spec-ready retired).

    With ``spec-ready`` retired, ``suggested_label`` is always ``""``.
    Proposals are generated only when an issue still carries a stale
    readiness label (e.g. ``spec-ready`` left over from before the retirement)
    and is no longer agent-ready, so callers can strip it and move the issue
    to Triage status.
    """
    proposals: list[LabelProposal] = []
    for res in results:
        if not res.current_agent_label:
            continue
        reason = _label_reason(res)
        proposals.append(
            LabelProposal(
                issue_id=res.id,
                from_label=res.current_agent_label,
                to_label="",
                reason=reason,
            )
        )
    return proposals


def _label_reason(res: IssueTriageResult) -> str:
    if res.missing:
        first = res.missing[0]
        extra = f" (+{len(res.missing) - 1} more)" if len(res.missing) > 1 else ""
        return f"Missing: {first}{extra}. Remove stale label and move to Triage status."
    return f"Score {res.score} — remove stale label and move to Triage status."


def _build_parent_groupings(results: list[IssueTriageResult]) -> list[ParentGrouping]:
    """Cluster issues sharing a file path into parent-grouping candidates.

    Only considers issues without an existing parent — we don't suggest
    re-parenting work already under an epic.
    """
    path_to_issues: dict[str, list[str]] = defaultdict(list)
    for res in results:
        for path in res.file_paths:
            path_to_issues[path].append(res.id)

    groupings: list[ParentGrouping] = []
    for path, issue_ids in path_to_issues.items():
        unique_ids = list(dict.fromkeys(issue_ids))  # Preserve order, dedupe.
        if len(unique_ids) < MIN_CLUSTER_SIZE:
            continue
        groupings.append(
            ParentGrouping(
                shared_path=path,
                issue_ids=unique_ids,
                proposed_parent_title=f"Hardening for `{PurePosixPath(path).name}`",
            )
        )

    # Sort: largest cluster first, then alphabetical by path.
    groupings.sort(key=lambda g: (-len(g.issue_ids), g.shared_path))
    return groupings


def _collect_metadata_gaps(
    results: list[IssueTriageResult],
    raw_issues: list[dict[str, Any]],
) -> MetadataGaps:
    no_priority: list[str] = []
    no_estimate: list[str] = []
    # Walk raw_issues to get priority/estimate (validator mutates to None internally).
    for raw in raw_issues:
        issue_id = str(raw.get("id", ""))
        priority = raw.get("priority")
        estimate = raw.get("estimate")
        is_epic = bool(raw.get("is_epic", False))
        if not isinstance(priority, int) or priority == 0:
            no_priority.append(issue_id)
        if not is_epic and (
            not isinstance(estimate, (int, float)) or estimate <= 0
        ):
            no_estimate.append(issue_id)
    return MetadataGaps(no_priority=no_priority, no_estimate=no_estimate)


def _summarize(results: list[IssueTriageResult]) -> TriageSummary:
    total = len(results)
    agent_ready = sum(1 for r in results if r.suggested_status == "Backlog")
    needs_clar = sum(1 for r in results if r.suggested_status == "Triage")
    avg = sum(r.score for r in results) / total if total else 0.0
    return TriageSummary(
        total=total,
        agent_ready=agent_ready,
        needs_clarification=needs_clar,
        agent_blocked=0,
        avg_score=round(avg, 1),
    )
