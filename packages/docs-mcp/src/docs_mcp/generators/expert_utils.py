"""Shared helpers for expert guidance extraction and filtering in epic/story generators.

Used by EpicGenerator and StoryGenerator to:
- Extract the first substantive paragraph from consultation answers (skipping
  boilerplate like "Based on domain knowledge...").
- Filter guidance by confidence and content quality (Epic 18.3).
"""

from __future__ import annotations

import re
from typing import Any

# Boilerplate that appears at the start of consultation answers; skip when extracting advice.
_NO_KNOWLEDGE_PATTERN: re.Pattern[str] = re.compile(
    r"no specific knowledge found", re.IGNORECASE,
)
_BOILERPLATE_PATTERN: re.Pattern[str] = re.compile(
    r"^Based on domain knowledge\s*\([^)]+\)\s*:?\s*$",
    re.IGNORECASE,
)
_MIN_SUBSTANTIVE_LEN = 60  # Paragraphs shorter than this are likely boilerplate.


def extract_expert_advice(answer: str, max_length: int = 300) -> str:
    """Extract the first substantive paragraph from an expert consultation answer.

    Skips markdown headers and boilerplate lines (e.g. "Based on domain knowledge
    (N source(s), confidence X%):") so that the returned text is actual advice.

    Args:
        answer: Full consultation answer text (may start with ## header and boilerplate).
        max_length: Maximum length of the returned advice string (default 300).

    Returns:
        First non-header, non-boilerplate paragraph, trimmed to max_length; empty if none.
    """
    if not answer or not answer.strip():
        return ""
    for para in answer.strip().split("\n\n"):
        cleaned = para.strip()
        if not cleaned:
            continue
        if cleaned.startswith("#"):
            continue
        if _NO_KNOWLEDGE_PATTERN.search(cleaned):
            continue
        if _BOILERPLATE_PATTERN.match(cleaned):
            continue
        if len(cleaned) < _MIN_SUBSTANTIVE_LEN and ":" in cleaned and "confidence" in cleaned.lower():
            continue
        if len(cleaned) > max_length:
            cleaned = cleaned[: max_length - 3].rsplit(" ", 1)[0] + "..."
        return cleaned
    return ""


def parse_confidence(confidence_str: str) -> float:
    """Parse a confidence string like '85%' to 0.85."""
    try:
        return float(str(confidence_str).rstrip("%")) / 100
    except (ValueError, AttributeError, TypeError):
        return 0.0


def filter_expert_guidance(guidance: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter expert guidance by confidence and content quality (Epic 18.3).

    - Confidence < 30%: suppressed entirely.
    - Confidence 30-50%: replaced with review-recommended message.
    - Confidence >= 50% with real content: kept as-is.
    - Empty or "No specific knowledge" advice: suppressed.
    """
    filtered: list[dict[str, Any]] = []
    for item in guidance:
        advice = (item.get("advice") or "").strip()
        confidence = parse_confidence(item.get("confidence", "0%"))

        if not advice or _NO_KNOWLEDGE_PATTERN.search(advice):
            continue
        if confidence < 0.3:
            continue
        if confidence < 0.5:
            domain = item.get("domain", "unknown")
            filtered.append({
                **item,
                "advice": (
                    f"Expert review recommended for {domain} "
                    "- automated analysis inconclusive"
                ),
            })
        else:
            filtered.append(item)
    return filtered
