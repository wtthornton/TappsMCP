"""RAG safety - backward-compatible re-export from security.content_safety.

The implementation has moved to ``tapps_core.security.content_safety`` to
break the circular dependency between ``memory`` and ``knowledge``
packages. This module re-exports all public symbols for backward
compatibility.
"""

from __future__ import annotations

# Re-export all public symbols for backward compatibility
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
