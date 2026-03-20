"""Verify tapps_core.knowledge.rag_safety re-exports from security.content_safety.

The content safety module was originally at ``knowledge.rag_safety`` and has
been moved to ``security.content_safety``.  The old import path is a re-export
shim kept for backward compatibility.  All behavioral tests live in
``test_content_safety.py``.
"""

from __future__ import annotations

from tapps_core.knowledge.rag_safety import SafetyCheckResult, check_content_safety
from tapps_core.security.content_safety import (
    SafetyCheckResult as CoreSafetyCheckResult,
)
from tapps_core.security.content_safety import (
    check_content_safety as core_check_content_safety,
)


class TestReexportIdentity:
    """The re-export shim must expose the exact same objects as the source."""

    def test_check_content_safety_is_same_object(self) -> None:
        assert check_content_safety is core_check_content_safety

    def test_safety_check_result_is_same_object(self) -> None:
        assert SafetyCheckResult is CoreSafetyCheckResult
