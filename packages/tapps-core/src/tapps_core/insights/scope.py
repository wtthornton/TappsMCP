"""Scope and confidentiality enforcement for InsightEntry records (STORY-102.5).

Problem: Both tapps-mcp and docs-mcp write InsightEntry records that may
contain project-internal facts. If the scope is accidentally set to ``shared``
those facts can leak across projects via federation.

This module provides:
- :exc:`ScopeViolation` — raised when a scope rule is broken
- :func:`enforce_scope` — clamps or validates an InsightEntry's scope
- :func:`validate_origin_scope` — checks that origin/scope combinations are legal

Rules
-----
1. Only entries with ``server_origin=user`` may have ``scope=shared`` without
   ``allow_shared=True``.
2. ``scope=session`` is never permitted for InsightEntry records — insights must
   outlive the session to be useful.
3. ``scope=branch`` requires a non-empty ``branch`` field (inherited from MemoryEntry
   validator, re-checked here for clarity).

These rules are opt-in enforced: callers that want to allow ``shared`` scope
pass ``allow_shared=True``.
"""

from __future__ import annotations

from tapps_brain.models import MemoryScope

from tapps_core.insights.models import InsightEntry, InsightOrigin


class ScopeViolation(ValueError):
    """Raised when an InsightEntry has an illegal scope/origin combination."""


def enforce_scope(
    entry: InsightEntry,
    *,
    allow_shared: bool = False,
) -> InsightEntry:
    """Validate and, where possible, clamp an InsightEntry's scope.

    Rules applied in order:
    1. ``scope=session`` → downgraded to ``project`` (insights must persist).
    2. ``scope=shared`` without ``allow_shared=True`` and origin not ``user``
       → downgraded to ``project``.
    3. ``scope=branch`` without a ``branch`` name → raises :exc:`ScopeViolation`.

    Args:
        entry: The InsightEntry to validate/clamp.
        allow_shared: When ``True``, ``scope=shared`` is permitted regardless
            of origin. Set this only for explicitly cross-project insights.

    Returns:
        A (possibly modified) InsightEntry with scope enforced.

    Raises:
        :exc:`ScopeViolation`: When a rule violation cannot be auto-corrected.
    """
    scope = entry.scope

    # Rule 1: session scope is not allowed for insights
    if scope == MemoryScope.session:
        entry = entry.model_copy(update={"scope": MemoryScope.project})
        scope = MemoryScope.project

    # Rule 2: shared scope requires explicit opt-in or user origin
    if scope == MemoryScope.shared:
        if not allow_shared and entry.server_origin != InsightOrigin.user:
            entry = entry.model_copy(update={"scope": MemoryScope.project})
            scope = MemoryScope.project

    # Rule 3: branch scope requires branch name
    if scope == MemoryScope.branch:
        if not entry.branch:
            msg = (
                f"InsightEntry '{entry.key}' has scope=branch but no branch name. "
                "Set entry.branch or change scope to 'project'."
            )
            raise ScopeViolation(msg)

    return entry


def validate_origin_scope(entry: InsightEntry) -> list[str]:
    """Return a list of scope/origin policy warnings for an InsightEntry.

    Unlike :func:`enforce_scope`, this function is non-mutating and returns
    human-readable warnings rather than raising or clamping. Use it for
    logging or audit purposes.

    Returns:
        List of warning strings. Empty list means no issues found.
    """
    warnings: list[str] = []
    scope = str(entry.scope)
    origin = entry.server_origin

    if scope == "shared" and origin not in (InsightOrigin.user, InsightOrigin.unknown):
        warnings.append(
            f"scope=shared with server_origin={origin}: "
            "shared insights may propagate across projects via federation."
        )

    if scope == "session":
        warnings.append(
            "scope=session: insights will not survive beyond the current session."
        )

    if scope == "branch" and not entry.branch:
        warnings.append("scope=branch but no branch name set.")

    if entry.subject_path and scope == "session":
        warnings.append(
            f"Path-scoped insight (subject_path={entry.subject_path!r}) "
            "uses ephemeral scope=session — it will not be recalled in future sessions."
        )

    return warnings
