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
"""

from __future__ import annotations

import re
from dataclasses import dataclass

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
        labels: Linear labels to apply when filing the issue.
            Defaults to ``("audit-fix",)`` so Ralph selects it as an
            implementable fix story and skips ``audit-digest`` digests.
    """

    title: str
    body: str
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
# Public API
# ---------------------------------------------------------------------------


def finding_to_story(
    severity: str,
    category: str,
    files: list[str],
    evidence: str,
    recommendation: str,
    parent_id: str = "",
) -> FindingStory:
    """Convert an audit finding into a Linear fix-story with 5 canonical sections.

    The returned body is guaranteed to pass ``docs_validate_linear_issue``
    with ``agent_ready=true`` by construction:

    - ``## Where`` always contains ≥1 file anchor (``path/to/file.ext:N``).
    - ``## Acceptance`` always contains ≥1 ``- [ ]`` checkbox.
    - Title is ≤80 chars and non-empty.

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

    Returns:
        :class:`FindingStory` with ``title`` and ``body`` ready to pass to
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
    return FindingStory(title=title, body=body)
