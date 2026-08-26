"""Single source of truth for the per-file security verdict (TAP-6387).

``security_passed`` used to be derived independently in three places — the
scanner, the ``validate_changed`` orchestrator, and the ``validate_changed``
renderer — and the three disagreed. The renderer inferred failure from a raw
issue *count*, so a file whose findings were all low-severity rendered
``security=fail`` in ``summary_rows`` while the authoritative block in the same
response reported ``security_passed=true``.

The verdict answers exactly one question: **does this file carry a
critical/high finding, or did a scanner fail to read it?** A total issue count
cannot answer that, which is why counts of *all* findings are not an accepted
input here.

Producers call :func:`security_verdict`, counting blocking findings with
:func:`count_blocking`. Consumers that already hold a produced per-file result
call :func:`read_security_verdict` instead of deriving an answer of their own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

# Findings at these severities fail the file. Everything below is reported but
# does not change the verdict — that is precisely why a total issue count is
# the wrong input.
BLOCKING_SEVERITIES = frozenset({"critical", "high"})


def count_blocking(findings: Iterable[Any]) -> int:
    """Count findings whose severity blocks the file.

    Accepts any iterable of objects exposing a ``severity`` attribute — bandit
    issues, secret findings, or a scorer's attached issue list.
    """
    return sum(1 for f in findings if getattr(f, "severity", "") in BLOCKING_SEVERITIES)


def security_verdict(*, blocking_findings: int, scan_error: str | None = None) -> bool:
    """Return the security verdict for a single file.

    Args:
        blocking_findings: Number of critical/high findings across every
            scanner that ran, typically via :func:`count_blocking`.
        scan_error: Set when a scanner could not read the file (TAP-1794). An
            unreadable file must never be reported as clean.

    Returns:
        ``True`` when no finding is critical/high and every scanner read the
        file successfully.
    """
    return blocking_findings == 0 and scan_error is None


def read_security_verdict(file_result: Mapping[str, Any]) -> bool:
    """Read the verdict a producer already recorded on a per-file result.

    Consumers must not re-derive the verdict from ``security_issues`` or any
    other count — that divergence is the TAP-6387 defect. A missing key means
    no producer ran for this file, reported conservatively as a failure to
    match the ``structuredContent`` default.
    """
    return bool(file_result.get("security_passed", False))
