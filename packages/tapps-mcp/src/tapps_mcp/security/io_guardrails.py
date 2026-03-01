"""I/O guardrails - re-exported from tapps_core.security.io_guardrails.

This module re-exports all public symbols for backward compatibility.
The canonical implementation lives in ``tapps_core.security.io_guardrails``.
"""

from __future__ import annotations

from tapps_core.security.io_guardrails import (
    detect_likely_prompt_injection as detect_likely_prompt_injection,
)
from tapps_core.security.io_guardrails import sanitize_for_log as sanitize_for_log
