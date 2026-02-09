"""I/O guardrails: sanitisation and prompt-injection heuristics.

Use ``sanitize_for_log`` when logging user-provided strings.
Use ``detect_likely_prompt_injection`` as an optional heuristic layer.
"""

from __future__ import annotations

import re


def sanitize_for_log(s: str, max_len: int = 500) -> str:
    """Sanitise a string for safe logging.

    Strips ASCII control characters (except tab/newline) and C1 controls,
    then truncates to *max_len*.

    Args:
        s: Raw string (user input, error message, etc.).
        max_len: Maximum output length.

    Returns:
        Sanitised string safe for structured logs.
    """
    if not isinstance(s, str):
        s = str(s)
    # Strip control characters (0x00-0x08, 0x0b, 0x0c, 0x0e-0x1f, 0x7f-0x9f)
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", s)
    s = s.strip()
    if len(s) > max_len:
        s = s[: max_len - 3] + "..."
    return s


def detect_likely_prompt_injection(user_input: str) -> bool:
    """Heuristic check for likely prompt-injection patterns.

    This is a *warn-only* layer — callers should log a warning but should
    **not** block execution solely based on this result.

    Args:
        user_input: User-supplied string.

    Returns:
        ``True`` if the input looks like a potential prompt injection.
    """
    if not user_input or not isinstance(user_input, str):
        return False

    u = user_input.strip().lower()
    patterns = [
        r"ignore\s+(all\s+)?(previous|above|prior)\s+instructions",
        r"disregard\s+(all\s+)?(previous|above)",
        r"you\s+are\s+now\s+",
        r"new\s+instructions?\s*:",
        r"system\s*:\s*",
        r"\[INST\]",
        r"<\|im_start\|>",
        r"human\s*:\s*.*\s*assistant\s*:",
        r"pretend\s+you\s+are",
        r"act\s+as\s+if\s+you",
        r"output\s+(only|just)\s+",
        r"respond\s+only\s+with\s+",
    ]
    return any(re.search(p, u, re.IGNORECASE | re.DOTALL) for p in patterns)
