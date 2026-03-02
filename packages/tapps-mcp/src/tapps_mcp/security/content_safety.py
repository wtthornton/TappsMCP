"""Content safety - re-exported from tapps_core.security.content_safety.

This module re-exports all public symbols for backward compatibility.
The canonical implementation lives in ``tapps_core.security.content_safety``.
"""

from __future__ import annotations

from tapps_core.security.content_safety import (
    _INJECTION_PATTERNS,
    SafetyCheckResult,
    _sanitise_content,
    check_content_safety,
)

__all__ = [
    "_INJECTION_PATTERNS",
    "SafetyCheckResult",
    "_sanitise_content",
    "check_content_safety",
]
