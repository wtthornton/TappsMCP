"""Orchestrate an audit campaign for a project scope.

This module composes :mod:`audit_chunker` (cluster files into sessions)
and :mod:`audit_session_template` (render the per-session ticket body)
into a single :class:`CampaignSpec` — the structured plan that the
``tapps_audit_campaign`` MCP tool returns at ``mode="plan"``. No Linear
writes, no brain memory writes happen here; the spec is pure data the
caller can inspect or hand to a dispatch step.

``mode="fix_plan"`` builds a companion :class:`FixPlanSpec` from a
persisted campaign spec: one implementable fix story per session cluster,
plus a parent fix epic. Stories are generated via
:func:`~tapps_mcp.tools.finding_to_story.finding_to_story` and are
guaranteed ``agent_ready=True`` by construction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tapps_mcp.tools.audit_chunker import AuditChunk, chunk_scope
from tapps_mcp.tools.audit_session_template import (
    VALID_CATEGORIES,
    render_campaign_epic,
    render_session_ticket,
)
from tapps_mcp.tools.finding_to_story import finding_to_story
from tapps_mcp.tools.project_paths import infer_monorepo_graph_root, resolve_path_under_root

_DEFAULT_CATEGORIES: list[str] = ["quality", "security", "dead_code"]
_EPIC_REF_PLACEHOLDER: str = "<campaign-epic>"

# Map audit category names to finding_to_story category names.
_AUDIT_TO_FIX_CATEGORY: dict[str, str] = {
    "quality": "correctness",
    "security": "security",
    "dead_code": "deadcode",
    "docs": "docs",
}


def finalize_session_bodies(
    spec_dict: dict[str, Any], epic_ref: str
) -> dict[str, Any]:
    """Substitute the real epic ref into every session body.

    Returns a new spec dict with the placeholder replaced. Idempotent:
    running twice with the same epic_ref is a no-op on already-substituted
    bodies.
    """
    if not epic_ref:
        msg = "epic_ref is required to finalize session bodies"
        raise ValueError(msg)
    sessions = spec_dict.get("sessions") or []
    new_sessions = []
    for session in sessions:
        body = session.get("body", "")
        new_body = body.replace(_EPIC_REF_PLACEHOLDER, epic_ref)
        new_sessions.append({**session, "body": new_body})
    return {**spec_dict, "sessions": new_sessions, "epic_ref": epic_ref}


@dataclass
class CampaignEpic:
    """Rendered title + body for the campaign parent Linear epic."""

    title: str
    body: str


@dataclass
class CampaignSession:
    """One session ticket rendered for the campaign."""

    session_index: int
    title: str
    body: str
    files: list[str]
    modules: list[str]
    intra_edges: int
    boundary_edges: int
    rationale: str
    labels: list[str] = field(default_factory=lambda: ["audit-readonly"])


@dataclass
class CampaignSpec:
    """Structured plan for an audit campaign run."""

    campaign_id: str
    project_root: str
    scope: str
    graph_root: str
    commit_sha: str
    categories: list[str]
    team: str
    project: str
    epic: CampaignEpic
    sessions: list[CampaignSession] = field(default_factory=list)
    skipped_trivial: list[str] = field(default_factory=list)
    total_files: int = 0

    @property
    def total_chunks(self) -> int:
        return len(self.sessions)


def build_campaign_spec(
    project_root: Path,
    scope: Path | None = None,
    *,
    graph_root: Path | None = None,
    commit_sha: str = "",
    categories: list[str] | None = None,
    chunk_size: int = 6,
    min_size: int = 4,
    max_size: int = 9,
    team: str = "",
    project: str = "",
    campaign_id: str = "",
) -> CampaignSpec:
    """Build a structured audit campaign for ``scope`` under ``project_root``.

    Args:
        project_root: Repo root, used for relative-path display.
        scope: Subdirectory to audit (None = whole project).
        graph_root: Import-graph root (None = project_root). Set to a package
            source root for monorepos so module names resolve correctly —
            see TAP-2035.
        commit_sha: Repo commit SHA at plan time. Empty if unknown.
        categories: Audit categories from
            ``{"quality", "security", "dead_code", "docs"}``. Defaults to
            ``["quality", "security", "dead_code"]``.
        chunk_size: Soft target files per session.
        min_size: Sessions smaller than this get bin-packed by package.
        max_size: Sessions larger than this get split.
        team: Linear team for the eventual epic (carried through to spec).
        project: Linear project for the eventual epic (carried through).
        campaign_id: Explicit campaign id. Empty = auto-generate.
    """
    project_root = project_root.resolve()
    if scope is None:
        scope_path = project_root
    elif scope.is_absolute():
        scope_path = scope.resolve()
    else:
        scope_path = resolve_path_under_root(str(scope), project_root)

    if graph_root is None:
        graph_root_path = infer_monorepo_graph_root(project_root, scope_path) or project_root
    elif graph_root.is_absolute():
        graph_root_path = graph_root.resolve()
    else:
        graph_root_path = resolve_path_under_root(str(graph_root), project_root)
    cats = list(categories) if categories else list(_DEFAULT_CATEGORIES)
    unknown = sorted(set(cats) - VALID_CATEGORIES)
    if unknown:
        msg = f"Unknown categories: {unknown}. Valid: {sorted(VALID_CATEGORIES)}"
        raise ValueError(msg)

    plan = chunk_scope(
        project_root,
        scope_path,
        graph_root=graph_root_path,
        min_size=min_size,
        target_size=chunk_size,
        max_size=max_size,
    )

    campaign_id = campaign_id or _build_campaign_id(scope_path, commit_sha)

    file_line_counts = _count_lines_for_files(plan.chunks, project_root)

    sessions: list[CampaignSession] = []
    for chunk in plan.chunks:
        ticket = render_session_ticket(
            chunk,
            campaign_id=campaign_id,
            epic_ref=_EPIC_REF_PLACEHOLDER,
            commit_sha=commit_sha or "uncommitted",
            categories=cats,
            file_line_counts=file_line_counts,
        )
        sessions.append(
            CampaignSession(
                session_index=chunk.session_index,
                title=ticket.title,
                body=ticket.body,
                files=list(chunk.files),
                modules=list(chunk.modules),
                intra_edges=chunk.intra_edges,
                boundary_edges=chunk.boundary_edges,
                rationale=chunk.rationale,
                labels=list(ticket.labels),
            )
        )

    epic_title, epic_body = render_campaign_epic(
        scope=_rel_or_str(scope_path, project_root),
        campaign_id=campaign_id,
        commit_sha=commit_sha or "uncommitted",
        categories=cats,
        sessions=sessions,
        total_files=plan.total_files,
        skipped_trivial=plan.skipped_trivial,
    )

    return CampaignSpec(
        campaign_id=campaign_id,
        project_root=str(project_root),
        scope=_rel_or_str(scope_path, project_root),
        graph_root=_rel_or_str(graph_root_path, project_root),
        commit_sha=commit_sha,
        categories=cats,
        team=team,
        project=project,
        epic=CampaignEpic(title=epic_title, body=epic_body),
        sessions=sessions,
        skipped_trivial=list(plan.skipped_trivial),
        total_files=plan.total_files,
    )


@dataclass
class FixStory:
    """Rendered fix story derived from one campaign session cluster.

    Generated by :func:`build_fix_plan_spec` via
    :func:`~tapps_mcp.tools.finding_to_story.finding_to_story`. The
    ``agent_ready`` flag is always ``True`` because ``finding_to_story``
    guarantees the body passes ``docs_validate_linear_issue`` by
    construction.
    """

    session_index: int
    title: str
    body: str
    files: list[str]
    labels: list[str] = field(default_factory=lambda: ["audit-fix"])
    agent_ready: bool = True
    estimate: int = 2  # TAP-2720: story-point estimate from finding_to_story
    priority: int = 3  # TAP-2720: Linear priority (3=Normal for P2 default)


@dataclass
class FixPlanSpec:
    """Structured fix plan derived from a persisted audit campaign spec."""

    campaign_id: str
    fix_epic_title: str
    fix_epic_body: str
    fix_stories: list[FixStory] = field(default_factory=list)

    @property
    def total_stories(self) -> int:
        return len(self.fix_stories)


def _audit_category_to_fix_category(audit_cat: str) -> str:
    """Map an audit category name to a ``finding_to_story`` category name."""
    return _AUDIT_TO_FIX_CATEGORY.get(audit_cat.lower(), "correctness")


def render_fix_epic(
    campaign_id: str,
    scope: str,
    categories: list[str],
    commit_sha: str,
    total_files: int,
    stories: list[FixStory],
) -> tuple[str, str]:
    """Render the fix-epic title + body for a campaign fix plan.

    The returned body follows the same epic template as
    :func:`~tapps_mcp.tools.audit_session_template.render_campaign_epic`
    (Purpose & Intent / Goal / Motivation / Acceptance Criteria /
    Technical Notes / Refs) and is intended to pass
    ``docs_validate_linear_issue(is_epic=true)`` with ``agent_ready=true``.

    Args:
        campaign_id: The source audit campaign id.
        scope: Human-readable scope label (e.g. ``"tapps_mcp"``).
        categories: Audit categories from which findings were sourced.
        commit_sha: Repo commit SHA at audit-plan time.
        total_files: Total number of files audited in the campaign.
        stories: :class:`FixStory` list to include in acceptance criteria.

    Returns:
        ``(title, body)`` tuple ready for Linear submission.
    """
    title = f"fix campaign: {scope} ({campaign_id.rsplit('-', 1)[-1]})"
    if len(title) > 80:
        title = title[:77] + "..."

    cats_display = ", ".join(sorted(categories))
    story_count = len(stories)
    accept_lines = "\n".join(
        f"- [ ] Fix story #{s.session_index}: `{s.title}` — {len(s.files)} file(s)"
        for s in stories
    )

    body = (
        "## Purpose & Intent\n\n"
        f"Implement fixes for the issues identified by audit campaign "
        f"`{campaign_id}` across {total_files} file(s) under `{scope}`. "
        "Each child fix story corresponds to one audit-session cluster; "
        "the `audit-fix` label marks tickets as implementable fixes — "
        "distinct from the read-only `audit-readonly` audit sessions.\n\n"
        "## Goal\n\n"
        f"Complete all {story_count} fix story ticket(s) listed in "
        "`## Acceptance Criteria`. Each fix story should be implemented, "
        "validated with `tapps_quick_check`, and closed before this epic closes.\n\n"
        "## Motivation\n\n"
        "The companion audit campaign identified quality issues across this scope. "
        "This fix epic converts those sessions into implementable work items "
        "with clean file anchors, acceptance criteria, and `audit-fix` labels "
        "for agents to select.\n\n"
        "## Acceptance Criteria\n\n"
        f"{accept_lines}\n"
        "- [ ] All fix stories have `tapps_quick_check` reporting no new findings\n"
        "- [ ] All fix stories merged to master\n\n"
        "## Technical Notes\n\n"
        f"1. Source audit campaign id: `{campaign_id}`\n"
        f"2. Audit commit: `{commit_sha}`\n"
        f"3. Audit categories: **{cats_display}**\n"
        f"4. Scope: `{scope}`\n"
        "5. Fix coverage tracked in brain under `fix.campaign.<id>` "
        "(distinct from audit coverage at `audit.campaign.<id>`)\n\n"
        "## Refs\n\n"
        "1. `TAP-2718` — tapps_audit_campaign fix_plan mode (this epic's generator)\n"
        "2. `TAP-2716` — audit-campaign bridge: findings to fix stories\n"
        "3. `packages/tapps-mcp/src/tapps_mcp/tools/finding_to_story.py:1` "
        "— fix story renderer\n"
    )
    return title, body


def build_fix_plan_spec(spec_dict: dict[str, Any]) -> FixPlanSpec:
    """Build a :class:`FixPlanSpec` from a persisted campaign spec dict.

    Converts each session in *spec_dict* into one implementable fix story
    using :func:`~tapps_mcp.tools.finding_to_story.finding_to_story`.
    The generated stories have ``agent_ready=True`` by construction.

    Args:
        spec_dict: A campaign spec dict as persisted by
            :func:`~tapps_mcp.tools.audit_manifest.save_campaign_spec`.
            Must include ``campaign_id`` and ``sessions``.

    Returns:
        :class:`FixPlanSpec` with the rendered fix epic and child fix stories.

    Raises:
        ValueError: if *spec_dict* has no ``campaign_id``.
    """
    campaign_id = str(spec_dict.get("campaign_id") or "")
    if not campaign_id:
        msg = "spec_dict must contain a non-empty campaign_id"
        raise ValueError(msg)

    categories: list[str] = list(spec_dict.get("categories") or ["quality"])
    scope = str(spec_dict.get("scope") or "")
    commit_sha = str(spec_dict.get("commit_sha") or "uncommitted")
    total_files = int(spec_dict.get("total_files") or 0)
    sessions: list[dict[str, Any]] = list(spec_dict.get("sessions") or [])

    # Use the first audit category to drive fix story categorisation.
    fix_category = _audit_category_to_fix_category(categories[0] if categories else "quality")

    # Use the directory name as the short scope label for the fix epic title.
    scope_label = Path(scope).name if scope else campaign_id

    fix_stories: list[FixStory] = []
    for session in sessions:
        idx = int(session.get("session_index") or 0)
        files: list[str] = list(session.get("files") or [])
        if not files:
            continue
        rationale = str(session.get("rationale") or f"Session {idx}: review quality issues")
        rec = f"Fix quality findings from audit session {idx}"

        story = finding_to_story(
            severity="P2",
            category=fix_category,
            files=files,
            evidence=rationale,
            recommendation=rec,
            parent_id="",  # parent epic ref is not yet known at build time
        )
        fix_stories.append(
            FixStory(
                session_index=idx,
                title=story.title,
                body=story.body,
                files=files,
                labels=list(story.labels),
                agent_ready=True,
                estimate=story.estimate,
                priority=story.priority,
            )
        )

    fix_epic_title, fix_epic_body = render_fix_epic(
        campaign_id=campaign_id,
        scope=scope_label,
        categories=categories,
        commit_sha=commit_sha,
        total_files=total_files,
        stories=fix_stories,
    )

    return FixPlanSpec(
        campaign_id=campaign_id,
        fix_epic_title=fix_epic_title,
        fix_epic_body=fix_epic_body,
        fix_stories=fix_stories,
    )


def _build_campaign_id(scope: Path, commit_sha: str) -> str:
    """Deterministic campaign id from scope + date + SHA prefix."""
    date = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    slug = _slug(scope.name) or "scope"
    sha_part = (commit_sha[:7] or "nosha") if commit_sha else "nosha"
    return f"audit-{date}-{slug}-{sha_part}"


def _slug(text: str) -> str:
    """Tight kebab-case slug — lowercase, [a-z0-9-] only, max 30 chars."""
    lowered = text.lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return cleaned[:30]


def _count_lines_for_files(
    chunks: list[AuditChunk],
    project_root: Path,
) -> dict[str, int]:
    """Read line counts once for every file across all chunks."""
    counts: dict[str, int] = {}
    for chunk in chunks:
        for rel in chunk.files:
            if rel in counts:
                continue
            try:
                with (project_root / rel).open(encoding="utf-8") as fh:
                    counts[rel] = sum(1 for _ in fh)
            except (OSError, UnicodeDecodeError):
                counts[rel] = 0
    return counts


def _rel_or_str(path: Path, project_root: Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)
