"""TAP-2717: Deterministic audit-finding → Linear fix-story converter.

Converts an audit finding (``severity`` / ``category`` / ``files`` /
``evidence`` / ``recommendation``) into a 5-section Linear story body that
is guaranteed to pass ``docs_validate_linear_issue`` with
``agent_ready=true`` by construction.

Section mapping:

  recommendation  → ## What
  files           → ## Where   (numbered list; bare paths get ``:1`` appended)
  evidence        → ## Why
  severity-derived checks → ## Acceptance (always ≥1 ``- [ ]`` checkbox)
  severity + category + parent_id → ## Refs

The generated title uses the ``"{category}: {recommendation}"`` pattern,
truncated to ≤80 characters at a word boundary.

TAP-2720: ``FindingStory`` now carries ``priority`` and ``estimate`` fields.
Priority maps P0→1 (Urgent), P1→2 (High), P2/P3→3 (Normal). Estimate
scales with severity base, file count, and optional average radon complexity.

TAP-2721: ``find_duplicate_in_snapshot()`` checks a pre-fetched Linear
snapshot for an issue whose title already covers the same finding. The
caller (``tapps_finding_to_story`` handler) passes cached snapshot issues;
no unfiltered ``list_issues`` calls are made.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Valid severity levels (P-priority notation from the audit filing protocol)
VALID_SEVERITIES: frozenset[str] = frozenset({"P0", "P1", "P2", "P3"})

# Valid category labels from the audit finding schema
VALID_CATEGORIES: frozenset[str] = frozenset(
    {"security", "correctness", "performance", "style", "docs", "deadcode"}
)

_TITLE_MAX_LEN: int = 80

# Matches a trailing line-range reference ":N" or ":N-N" (N = digits)
_HAS_LINE_REF_RE = re.compile(r":\d+(?:-\d+)?$")

# TAP-2720: Linear priority values (1=Urgent … 4=Low, 0=None)
_SEVERITY_PRIORITY: dict[str, int] = {
    "P0": 1,  # Urgent
    "P1": 2,  # High
    "P2": 3,  # Normal
    "P3": 3,  # Normal
}

# TAP-2720: Base story-point estimates by severity (Fibonacci-aligned)
_SEVERITY_BASE_ESTIMATE: dict[str, int] = {
    "P0": 8,  # security/correctness hole — likely cross-cutting
    "P1": 5,  # high-severity correctness — non-trivial root cause
    "P2": 2,  # style/minor refactor — routine
    "P3": 1,  # informational — low effort
}


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FindingStory:
    """Rendered title + body for a single fix story derived from an audit finding.

    Attributes:
        title: Linear issue title (≤80 chars).
        body: 5-section Markdown body (``## What`` / ``## Where`` /
            ``## Why`` / ``## Acceptance`` / ``## Refs``).
        estimate: Story-point estimate for the fix (TAP-2720). Derived
            from severity base, file count, and optional radon CC.
            Fibonacci-aligned: 1, 2, 3, 5, 8, or 13.
        priority: Linear priority value (TAP-2720). Mapped from severity:
            P0→1 (Urgent), P1→2 (High), P2/P3→3 (Normal).
        labels: Linear labels to apply when filing the issue.
            Defaults to ``("audit-fix",)`` so Ralph selects it as an
            implementable fix story and skips ``audit-digest`` digests.
    """

    title: str
    body: str
    estimate: int
    priority: int
    labels: tuple[str, ...] = ("audit-fix",)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalise_file_anchor(file_path: str) -> str:
    """Ensure *file_path* ends with ``:LINE`` or ``:LINE-LINE`` for the linter.

    The docs-mcp linter requires at least one ``path/to/file.ext:N`` anchor
    in the issue description.  Bare paths that lack a line reference get
    ``:1`` appended so the anchor regex matches them.
    """
    stripped = file_path.strip()
    if _HAS_LINE_REF_RE.search(stripped):
        return stripped
    return f"{stripped}:1"


def _make_title(category: str, recommendation: str) -> str:
    """Build a ≤80-character title from the category and recommendation text.

    Title pattern: ``"{category}: {recommendation_text}"``.

    If the recommendation pushes the title over 80 chars, the text is
    truncated at the last word boundary before the limit and an ellipsis
    (``…``) is appended.
    """
    cat = category.lower().strip()
    prefix = f"{cat}: "
    max_rec_len = _TITLE_MAX_LEN - len(prefix)
    rec = recommendation.strip()
    if len(rec) > max_rec_len:
        truncated = rec[:max_rec_len].rsplit(" ", 1)[0]
        rec = truncated.rstrip(",. ") + "\u2026"
    return f"{prefix}{rec}"[:_TITLE_MAX_LEN]


def _render_where(files: list[str]) -> str:
    """Render a numbered list of file anchors for ``## Where``."""
    lines: list[str] = []
    for i, f in enumerate(files, start=1):
        anchor = _normalise_file_anchor(f)
        lines.append(f"{i}. `{anchor}`")
    return "\n".join(lines)


def _render_acceptance(severity: str) -> str:
    """Render severity-appropriate ``- [ ]`` checkboxes for ``## Acceptance``."""
    items: list[str] = [
        "- [ ] Root cause identified and addressed as described in `## What`",
        "- [ ] All tests pass after the fix (`uv run pytest -x`)",
        "- [ ] `tapps_quick_check` reports no new findings on changed files",
    ]
    if severity == "P0":
        items.insert(0, "- [ ] Security/correctness impact scoped and confirmed safe")
        items.append("- [ ] Fix reviewed by a second agent or human before merge")
    elif severity == "P1":
        items.append("- [ ] Regression test added covering the fixed code path")
    return "\n".join(items)


def _derive_estimate(severity: str, files: list[str], avg_complexity: float) -> int:
    """Compute a Fibonacci-aligned story-point estimate (TAP-2720).

    Formula (additive, capped at 13):

    - Base by severity: P0→8, P1→5, P2→2, P3→1
    - +1 per 3 additional files beyond the first (file-count bonus)
    - +1 if ``avg_complexity > 10``; +2 if ``avg_complexity > 20``
      (radon cyclomatic-complexity bonus — 0 when not supplied)

    The result is always a positive integer in the range ``[1, 13]``.
    """
    base = _SEVERITY_BASE_ESTIMATE.get(severity, 2)
    file_bonus = max(0, len(files) - 1) // 3
    if avg_complexity > 20:
        complexity_bonus = 2
    elif avg_complexity > 10:
        complexity_bonus = 1
    else:
        complexity_bonus = 0
    return min(base + file_bonus + complexity_bonus, 13)


def _render_refs(severity: str, category: str, parent_id: str) -> str:
    """Render ``## Refs`` with audit provenance metadata."""
    lines: list[str] = [
        f"- Severity: **{severity}**",
        f"- Category: **{category}**",
    ]
    if parent_id:
        lines.append(f"- Audit session: {parent_id}")
    lines.append("- Source: `tapps_finding_to_story` (deterministic converter)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# TAP-2721: Duplicate detection against cached Linear snapshots
# ---------------------------------------------------------------------------

# Regex for title normalisation — collapse any run of non-alphanumeric chars
# (punctuation, dashes, colons, ellipsis) to a single space for comparison.
_DEDUP_NORM_RE = re.compile(r"\W+")


def _normalise_for_dedup(title: str) -> str:
    """Lowercase and collapse punctuation for duplicate-title comparison.

    The generated title pattern is ``"{category}: {recommendation}"``.
    Normalising both sides removes cosmetic differences (trailing ellipsis,
    punctuation, extra whitespace) so an exact string match catches true
    semantic duplicates while ignoring formatting noise.
    """
    return _DEDUP_NORM_RE.sub(" ", title.lower()).strip()


def find_duplicate_in_snapshot(
    title: str,
    issues: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Search *issues* for an existing issue that duplicates *title*.

    Uses normalised title comparison (lowercase, punctuation collapsed)
    so minor formatting differences (trailing ``…``, colons, dashes) do
    not prevent a match.  Returns the first matching issue dict — which
    must contain at minimum ``"id"`` and ``"title"`` keys — or ``None``
    when no duplicate is found.

    The caller is responsible for supplying *issues* from a prior
    ``tapps_linear_snapshot_get`` call so no unfiltered ``list_issues``
    requests are made inside this function (TAP-2721).

    Args:
        title: Generated story title (from :func:`finding_to_story`).
        issues: List of issue dicts from a Linear snapshot.  Each dict
            must contain ``"id"`` (the issue identifier, e.g. ``"TAP-123"``)
            and ``"title"`` (the issue title string).

    Returns:
        The first matching issue dict, or ``None``.
    """
    needle = _normalise_for_dedup(title)
    if not needle:
        return None
    for issue in issues:
        existing = _normalise_for_dedup(str(issue.get("title") or ""))
        if existing and existing == needle:
            return issue
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def finding_to_story(
    severity: str,
    category: str,
    files: list[str],
    evidence: str,
    recommendation: str,
    parent_id: str = "",
    avg_complexity: float = 0.0,
) -> FindingStory:
    """Convert an audit finding into a Linear fix-story with 5 canonical sections.

    The returned body is guaranteed to pass ``docs_validate_linear_issue``
    with ``agent_ready=true`` by construction:

    - ``## Where`` always contains ≥1 file anchor (``path/to/file.ext:N``).
    - ``## Acceptance`` always contains ≥1 ``- [ ]`` checkbox.
    - Title is ≤80 chars and non-empty.

    The returned :class:`FindingStory` also carries ``priority`` (mapped from
    severity) and ``estimate`` (derived from severity, file count, and
    ``avg_complexity``) for direct use in ``save_issue`` (TAP-2720).

    Args:
        severity: ``"P0"`` | ``"P1"`` | ``"P2"`` | ``"P3"``.
        category: One of ``"security"``, ``"correctness"``, ``"performance"``,
            ``"style"``, ``"docs"``, or ``"deadcode"``.
        files: File paths with optional line ranges, e.g.
            ``["src/module.py:10-25"]``.  A bare path without a line ref
            is treated as ``:1`` for anchor purposes.
        evidence: One-line description of the symptom (with tool-output ref).
        recommendation: One-line fix direction (informational only).
        parent_id: Linear parent ticket identifier (e.g. ``"TAP-2040"``).
            Included in ``## Refs`` when provided.
        avg_complexity: Average radon cyclomatic complexity of the affected
            files (optional). Increases the estimate when above thresholds
            of 10 (+1 point) or 20 (+2 points). Default ``0.0`` (no bonus).

    Returns:
        :class:`FindingStory` with ``title``, ``body``, ``estimate``,
        ``priority``, and ``labels`` ready to pass to
        ``docs_validate_linear_issue`` and then ``save_issue``.

    Raises:
        ValueError: if *files* is empty, *evidence* is blank, or
            *recommendation* is blank.
    """
    if not files:
        msg = "`files` must contain at least one file path"
        raise ValueError(msg)
    if not evidence.strip():
        msg = "`evidence` must be non-empty"
        raise ValueError(msg)
    if not recommendation.strip():
        msg = "`recommendation` must be non-empty"
        raise ValueError(msg)

    title = _make_title(category, recommendation)

    sections: list[str] = [
        f"## What\n\n{recommendation.strip()}",
        f"## Where\n\n{_render_where(files)}",
        f"## Why\n\n{evidence.strip()}",
        f"## Acceptance\n\n{_render_acceptance(severity)}",
        f"## Refs\n\n{_render_refs(severity, category, parent_id)}",
    ]

    body = "\n\n".join(sections) + "\n"
    return FindingStory(
        title=title,
        body=body,
        estimate=_derive_estimate(severity, files, avg_complexity),
        priority=_SEVERITY_PRIORITY.get(severity, 3),
    )
