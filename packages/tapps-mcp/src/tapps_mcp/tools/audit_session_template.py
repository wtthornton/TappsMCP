"""Render the per-session audit ticket body.

The body is the executor's playbook for a single audit session: it lists
the files in scope, the exact tool sequence to run, the finding output
schema, and the protocol for filing findings as new Linear issues. The
rendered body is validated against ``docs_validate_linear_issue`` before
it is saved, so it must conform to the AGENT 5-section template
(``## What`` / ``## Where`` / ``## Why`` / ``## Acceptance`` / ``## Refs``).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from tapps_mcp.tools.audit_chunker import AuditChunk


class _SessionLike(Protocol):
    """Structural type for ``CampaignSession``-shaped objects.

    Defined here to avoid importing :mod:`audit_campaign` (which itself
    imports this module) at render time.
    """

    session_index: int
    title: str
    files: list[str]


VALID_CATEGORIES: frozenset[str] = frozenset(
    {"quality", "security", "dead_code", "docs"}
)

# Matches a trailing line-range reference ":N" or ":N-N" (N = digits).
# Used to ensure digest-ticket file anchors satisfy the docs-mcp linter.
_HAS_LINE_REF_RE = re.compile(r":\d+(?:-\d+)?$")


@dataclass
class SessionTicket:
    """Rendered title + body for a single audit session."""

    title: str
    body: str
    labels: list[str] = field(default_factory=lambda: ["audit-readonly"])


@dataclass
class DigestFinding:
    """A single P2 or P3 finding for bundling into a digest ticket.

    Each field mirrors the audit finding output schema emitted by the
    audit-session executor.
    """

    severity: str
    category: str
    files: list[str]
    evidence: str
    recommendation: str


@dataclass
class DigestTicket:
    """Rendered title + body for a P2/P3 finding-bundle (audit-digest) issue.

    The ``not-implementable`` label signals to Ralph and other consumers that
    this ticket is a read-only digest of low-severity observations, not an
    individually actionable fix story.
    """

    title: str
    body: str
    labels: list[str] = field(
        default_factory=lambda: ["not-implementable", "audit-readonly"]
    )


def render_session_ticket(
    chunk: AuditChunk,
    *,
    campaign_id: str,
    epic_ref: str,
    commit_sha: str,
    categories: list[str],
    file_line_counts: dict[str, int],
) -> SessionTicket:
    """Render the title + body for one audit session ticket.

    Args:
        chunk: The chunk this session covers.
        campaign_id: Stable id for the campaign run (used in brain memory keys).
        epic_ref: Linear identifier of the campaign parent epic (e.g. ``TAP-2040``).
        commit_sha: Repo commit SHA at the time of planning, for reproducibility.
        categories: Subset of ``{"quality", "security", "dead_code", "docs"}``
            scoped for this campaign.
        file_line_counts: Map of relative file path to line count (used in
            ``## Where`` anchors).
    """
    bad = sorted(set(categories) - VALID_CATEGORIES)
    if bad:
        msg = f"Unknown categories: {bad}. Valid: {sorted(VALID_CATEGORIES)}"
        raise ValueError(msg)

    cats_set = set(categories)
    title = _render_title(chunk)
    body = _render_body(
        chunk,
        campaign_id=campaign_id,
        epic_ref=epic_ref,
        commit_sha=commit_sha,
        categories=categories,
        cats_set=cats_set,
        file_line_counts=file_line_counts,
    )
    return SessionTicket(title=title, body=body)


def _render_title(chunk: AuditChunk) -> str:
    prefix = _common_prefix(chunk.modules)
    if prefix:
        title = f"audit: {prefix} cluster #{chunk.session_index} ({chunk.size} files)"
    else:
        title = f"audit: cluster #{chunk.session_index} ({chunk.size} files)"
    if len(title) > 80:
        title = title[:77] + "..."
    return title


def _render_body(
    chunk: AuditChunk,
    *,
    campaign_id: str,
    epic_ref: str,
    commit_sha: str,
    categories: list[str],
    cats_set: set[str],
    file_line_counts: dict[str, int],
) -> str:
    cats_display = ", ".join(sorted(cats_set))
    where_anchors = _render_where_anchors(chunk.files, file_line_counts)
    tool_per_file = _render_per_file_tools(cats_set)
    acceptance_extra = _render_acceptance_category_lines(cats_set)
    sections: list[str] = []

    sections.append(
        "<!-- ralph: audit-readonly -->\n\n"
        "## What\n\n"
        f"Read-only quality audit of the {chunk.size} files listed in `## Where`. "
        "Score every file, then file any findings as **new** Linear issues "
        "under this ticket per the protocol in `## Refs`. "
        "**Do not edit or fix anything in this scope.**"
    )

    sections.append(
        "## Where\n\n"
        f"Audited at commit `{commit_sha}`:\n\n"
        f"{where_anchors}"
    )

    sections.append(
        "## Why\n\n"
        f"These {chunk.size} files form an import cluster "
        f"({chunk.intra_edges} internal imports, {chunk.boundary_edges} boundary "
        "imports out of scope) — they are coupled tightly enough that bugs in "
        "one often involve the others, so they are reviewed as one session "
        "rather than in isolation.\n\n"
        f"Categories in scope for this session: **{cats_display}**."
    )

    sections.append(
        "## Acceptance\n\n"
        "- [ ] `tapps_session_start()` called at session start\n"
        "- [ ] `tapps_quick_check(file)` run on every file in `## Where`\n"
        f"{acceptance_extra}"
        "- [ ] `tapps_impact_analysis` run on any file scoring under 60\n"
        "- [ ] Findings filed per the protocol in `## Refs` "
        "(P0/P1 each = one issue with `parent_id` = this ticket; "
        "P2/P3 = one digest issue per session, parent = this ticket)\n"
        '- [ ] If zero findings: comment "no findings, session clean" '
        "on this ticket — do not file empty issues\n"
        "- [ ] Session note saved via `tapps_session_notes`\n"
        "- [ ] No source file in `## Where` modified by this session\n"
        "- [ ] After findings filed, set this ticket to **Done** in Linear "
        "(`save_issue(id=<this-ticket-id>, state=\"Done\")`) with a summary comment — "
        "**do NOT leave it In Progress** (causes re-selection and duplicate digests)"
    )

    sections.append(
        "## Refs\n\n"
        "### Tool sequence (exact)\n\n"
        "1. `tapps_session_start()`\n"
        "2. For each file in `## Where`:\n"
        f"{tool_per_file}"
        "3. `tapps_impact_analysis(file)` for any file with `overall_score < 60`\n"
        "4. Compile findings per the schema below\n\n"
        "### Finding output schema (per issue body)\n\n"
        "```json\n"
        "{\n"
        '  "severity": "P0|P1|P2|P3",\n'
        '  "category": "security|correctness|performance|style|docs|deadcode",\n'
        '  "files": ["path/file.py:LINE-RANGE", ...],\n'
        '  "evidence": "one-line description with tool-output reference",\n'
        '  "recommendation": "one-line fix direction (informational only — '
        'DO NOT apply)"\n'
        "}\n"
        "```\n\n"
        "### Finding-filing protocol\n\n"
        "1. **P0** (security holes, broken correctness): one Linear issue per "
        "finding via the `linear-issue` skill, `parent_id` = this ticket, "
        "priority = Urgent (1)\n"
        "2. **P1** (likely correctness, missing types in hot paths): same as "
        "P0, priority = High (2)\n"
        "3. **P2** (style, minor refactor, low-impact dead code): bundle all "
        "P2 findings in ONE digest issue per session, parent = this ticket, "
        f'priority = Normal (3), title `audit-digest session #{chunk.session_index}: '
        "K P2 findings`\n"
        "4. **P3** (informational, suggestions): bundle in the same digest "
        "issue as P2\n"
        "5. **Zero findings**: comment on this ticket — do not file any "
        "issues\n\n"
        "### Constraints\n\n"
        "- **Do not** edit any file in `## Where`\n"
        "- **Do not** run formatters, `ruff --fix`, or any auto-fixer\n"
        "- After findings are filed, set this ticket to **Done** in Linear "
        "(`save_issue(id=<this-ticket-id>, state=\"Done\")`) with a summary "
        "comment. **Do NOT leave it In Progress** — that causes Ralph to "
        "re-select and re-run the session on the next campaign loop, filing "
        "duplicate digest issues. The `audit-readonly` label on this ticket "
        "signals the contract to compatible runners.\n"
        "- If understanding a finding requires reading files outside "
        "`## Where`, note that in the digest body and stop — escalate rather "
        "than scope-creep\n\n"
        "### Campaign context\n\n"
        f"- Parent epic: {epic_ref}\n"
        f"- Campaign id: `{campaign_id}`\n"
        f"- Cohesion rationale: {chunk.rationale}\n"
        "- Coverage manifest: brain memory keys `audit:coverage:<file>`"
    )

    return "\n\n".join(sections) + "\n"


def _render_where_anchors(
    files: list[str],
    file_line_counts: dict[str, int],
) -> str:
    lines: list[str] = []
    for i, path in enumerate(files, start=1):
        loc = file_line_counts.get(path, 0)
        if loc > 0:
            lines.append(f"{i}. `{path}:1-{loc}`")
        else:
            lines.append(f"{i}. `{path}`")
    return "\n".join(lines)


def _render_per_file_tools(cats_set: set[str]) -> str:
    lines = [
        "   a. `tapps_score_file(file)` — record `overall_score`\n",
        "   b. `tapps_quick_check(file)` — record gate result\n",
    ]
    letter = ord("c")
    if "security" in cats_set:
        lines.append(
            f"   {chr(letter)}. `tapps_security_scan(file)` "
            "— bandit + pip-audit findings\n"
        )
        letter += 1
    if "dead_code" in cats_set:
        lines.append(
            f"   {chr(letter)}. `tapps_dead_code(file)` "
            "— vulture-confirmed dead code\n"
        )
        letter += 1
    if "docs" in cats_set:
        lines.append(
            f"   {chr(letter)}. `docs_check_drift(file)` "
            "— code-vs-docs drift\n"
        )
        letter += 1
    return "".join(lines)


def _render_acceptance_category_lines(cats_set: set[str]) -> str:
    extra: list[str] = []
    if "security" in cats_set:
        extra.append(
            "- [ ] `tapps_security_scan(file)` run on every file\n"
        )
    if "dead_code" in cats_set:
        extra.append(
            "- [ ] `tapps_dead_code(file)` run on every file\n"
        )
    if "docs" in cats_set:
        extra.append(
            "- [ ] `docs_check_drift` run on the cluster\n"
        )
    return "".join(extra)


def _common_prefix(modules: list[str]) -> str:
    if not modules:
        return ""
    parts = [m.split(".") for m in modules]
    common: list[str] = []
    for grouped in zip(*parts, strict=False):
        if len(set(grouped)) == 1:
            common.append(grouped[0])
        else:
            break
    return ".".join(common)


def _normalise_anchor(path: str) -> str:
    """Return *path* with a ``:LINE`` suffix if no line reference is present.

    The docs-mcp linter requires at least one ``path/to/file.ext:N`` anchor
    in the issue description. Bare paths that lack a line reference get
    ``:1`` appended.
    """
    stripped = path.strip()
    return stripped if _HAS_LINE_REF_RE.search(stripped) else f"{stripped}:1"


def render_digest_ticket(
    *,
    session_index: int,
    parent_ref: str,
    findings: Sequence[DigestFinding],
) -> DigestTicket:
    """Render the title + body for a P2/P3 findings digest (bundle) issue.

    The returned body is a valid 5-section issue body that will pass
    ``docs_validate_linear_issue`` by construction:

    - ``## Where`` contains ≥1 numbered file anchor (``path/file.ext:N``).
    - ``## Acceptance`` contains ≥1 ``- [ ]`` checkbox.
    - Title is ≤80 chars.

    The returned :class:`DigestTicket` carries
    ``labels=["not-implementable", "audit-readonly"]`` so consumers can
    identify it as a low-priority digest rather than an implementable fix
    story.

    Args:
        session_index: Audit session number — used in the title and refs.
        parent_ref: Linear identifier of the parent session ticket
            (e.g. ``"TAP-2040"``). Included in ``## Refs``.
        findings: Non-empty sequence of :class:`DigestFinding` objects
            representing the P2/P3 findings to bundle.

    Raises:
        ValueError: if *findings* is empty.
    """
    if not findings:
        msg = "`findings` must contain at least one finding"
        raise ValueError(msg)

    count = len(findings)
    title = f"audit-digest session #{session_index}: {count} P2/P3 findings"
    if len(title) > 80:
        title = title[:77] + "..."

    # Collect de-duplicated file paths in order of first appearance.
    seen: dict[str, None] = {}
    for f in findings:
        for fp in f.files:
            seen[fp] = None
    all_files = list(seen.keys())

    where_lines = [
        f"{i}. `{_normalise_anchor(p)}`" for i, p in enumerate(all_files, start=1)
    ]
    where_block = "\n".join(where_lines)

    # Build per-finding summary for ## Why.
    why_lines = [
        f"{i}. [{f.severity}/{f.category}] {f.evidence} — {f.recommendation}"
        for i, f in enumerate(findings, start=1)
    ]
    why_block = "\n".join(why_lines)

    categories = ", ".join(sorted({f.category for f in findings}))

    sections: list[str] = [
        (
            f"## What\n\n"
            f"P2/P3 findings bundle for audit session #{session_index}: "
            f"{count} finding(s) across {len(all_files)} file(s). "
            "These are informational observations (style, minor refactor, "
            "dead code, docs) that may or may not merit individual fix stories."
        ),
        f"## Where\n\n{where_block}",
        (
            f"## Why\n\n"
            f"Bundled from {count} P2/P3 finding(s) in session #{session_index}:\n\n"
            f"{why_block}"
        ),
        (
            "## Acceptance\n\n"
            "- [ ] Findings reviewed; any worth promoting to fix stories "
            "filed individually via `tapps_finding_to_story`"
        ),
        (
            f"## Refs\n\n"
            f"- Severity range: P2-P3\n"
            f"- Categories: {categories}\n"
            f"- Audit session: {parent_ref}\n"
            "- Source: `render_digest_ticket` (deterministic digest renderer)"
        ),
    ]

    body = "\n\n".join(sections) + "\n"
    return DigestTicket(title=title, body=body)


def render_campaign_epic(
    *,
    scope: str,
    campaign_id: str,
    commit_sha: str,
    categories: list[str],
    sessions: Sequence[_SessionLike],
    total_files: int,
    skipped_trivial: list[str],
) -> tuple[str, str]:
    """Render the parent epic title + body for a campaign.

    Returns a (title, body) tuple. Body conforms to the epic template
    (Purpose & Intent / Goal / Motivation / Acceptance Criteria /
    Technical Notes / Refs) and is intended to pass
    ``docs_validate_linear_issue(is_epic=true)`` with ``agent_ready=true``.
    """
    title = f"audit campaign: {scope} ({campaign_id.rsplit('-', 1)[-1]})"
    if len(title) > 80:
        title = title[:77] + "..."

    cats_display = ", ".join(sorted(categories))
    session_count = len(sessions)
    accept_lines = "\n".join(
        f"- [ ] Session #{s.session_index}: `{s.title}` — "
        f"{len(s.files)} files filed and reviewed"
        for s in sessions
    )
    skipped_count = len(skipped_trivial)

    body = (
        "## Purpose & Intent\n\n"
        f"We are doing this so that the {total_files} reviewable Python "
        f"files under `{scope}` are audited as {session_count} cohesive "
        "session(s) — each session gets a prescriptive playbook (which "
        "tapps-mcp tools to run, what counts as a finding, how to file it) "
        "and any findings land as new Linear issues parented to the session "
        "ticket. Coverage is tracked in brain memory under "
        f"`audit:coverage:<file>` keys so re-runs are idempotent.\n\n"
        "## Goal\n\n"
        f"Complete all {session_count} child session ticket(s) listed in "
        "`## Acceptance Criteria` and update the coverage manifest. "
        "The audit executor files findings; the orchestrator "
        "(`tapps_audit_campaign`) closes session tickets and writes the "
        "coverage entries.\n\n"
        "## Motivation\n\n"
        "Without an explicit campaign structure, code review on this scope "
        "would be ad-hoc, inconsistent across sessions, and impossible to "
        "track. This campaign produces a deterministic record of what was "
        "audited, at which commit, by which session, and what was found.\n\n"
        "## Acceptance Criteria\n\n"
        f"{accept_lines}\n"
        "- [ ] Coverage manifest entries written for every file in scope\n"
        "- [ ] All P0 / P1 findings filed as individual child issues "
        "parented to their session ticket\n"
        "- [ ] All P2 / P3 findings bundled into per-session digest issues "
        "parented to their session ticket\n\n"
        "## Technical Notes\n\n"
        f"1. Campaign id: `{campaign_id}`\n"
        f"2. Audited at commit `{commit_sha}`\n"
        f"3. Categories in scope: **{cats_display}**\n"
        f"4. Scope: `{scope}`\n"
        f"5. Files skipped as trivial (empty / re-export shim): "
        f"{skipped_count}\n"
        "6. Cluster strategy: undirected connected components, "
        "size-aware split + package-affinity bin-pack (see "
        "`packages/tapps-mcp/src/tapps_mcp/tools/audit_chunker.py:1-280`)\n\n"
        "## Refs\n\n"
        "1. `TAP-2036` — parent feature epic (`tapps_audit_campaign` tool)\n"
        "2. `TAP-2035` — `build_import_graph` 0-edge bug on monorepo roots "
        "(workaround via `graph_root` param)\n"
        f"3. `packages/tapps-mcp/src/tapps_mcp/tools/audit_session_template.py`"
        " — per-session ticket renderer\n"
    )
    return title, body
