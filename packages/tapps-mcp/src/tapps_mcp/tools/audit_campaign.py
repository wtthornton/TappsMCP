"""Orchestrate an audit campaign for a project scope.

This module composes :mod:`audit_chunker` (cluster files into sessions)
and :mod:`audit_session_template` (render the per-session ticket body)
into a single :class:`CampaignSpec` — the structured plan that the
``tapps_audit_campaign`` MCP tool returns at ``mode="plan"``. No Linear
writes, no brain memory writes happen here; the spec is pure data the
caller can inspect or hand to a dispatch step.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from tapps_mcp.tools.audit_chunker import AuditChunk, chunk_scope
from tapps_mcp.tools.audit_session_template import (
    VALID_CATEGORIES,
    render_campaign_epic,
    render_session_ticket,
)

_DEFAULT_CATEGORIES: list[str] = ["quality", "security", "dead_code"]
_EPIC_REF_PLACEHOLDER: str = "<campaign-epic>"


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
    scope = (scope or project_root).resolve()
    graph_root = (graph_root or project_root).resolve()
    cats = list(categories) if categories else list(_DEFAULT_CATEGORIES)
    unknown = sorted(set(cats) - VALID_CATEGORIES)
    if unknown:
        msg = f"Unknown categories: {unknown}. Valid: {sorted(VALID_CATEGORIES)}"
        raise ValueError(msg)

    plan = chunk_scope(
        project_root,
        scope,
        graph_root=graph_root,
        min_size=min_size,
        target_size=chunk_size,
        max_size=max_size,
    )

    campaign_id = campaign_id or _build_campaign_id(scope, commit_sha)

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
            )
        )

    epic_title, epic_body = render_campaign_epic(
        scope=_rel_or_str(scope, project_root),
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
        scope=str(scope),
        graph_root=str(graph_root),
        commit_sha=commit_sha,
        categories=cats,
        team=team,
        project=project,
        epic=CampaignEpic(title=epic_title, body=epic_body),
        sessions=sessions,
        skipped_trivial=list(plan.skipped_trivial),
        total_files=plan.total_files,
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
