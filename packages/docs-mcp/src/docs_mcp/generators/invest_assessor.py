"""INVEST checklist auto-assessment from story configuration signals."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from docs_mcp.generators.stories import StoryConfig

logger = structlog.get_logger(__name__)


def assess_invest(config: StoryConfig) -> dict[str, bool]:
    """Auto-assess INVEST checklist items from story configuration.

    Returns a dict with keys matching the INVEST acronym. Values are True
    when the signal is strong enough to auto-check, False otherwise.

    Assessment rules:
    - Independent: True when dependencies list is empty.
    - Negotiable: Always False (requires human judgment).
    - Valuable: True when so_that is non-empty.
    - Estimable: True when points > 0 or size is set.
    - Small: True when points <= 5 or size in ("S", "M").
    - Testable: True when test_cases or acceptance_criteria are non-empty.
    """
    return {
        "Independent": len(config.dependencies) == 0,
        "Negotiable": False,  # Always requires human judgment
        "Valuable": bool(config.so_that),
        "Estimable": config.points > 0 or bool(config.size),
        "Small": _is_small(config),
        "Testable": bool(config.test_cases) or bool(config.acceptance_criteria),
    }


def _is_small(config: StoryConfig) -> bool:
    """Determine if a story is small enough for one sprint."""
    if config.size in ("S", "M"):
        return True
    if config.size in ("L", "XL"):
        return False
    # No size set — check points.
    if config.points > 0:
        return config.points <= 5
    return False  # Unknown size, don't auto-check
