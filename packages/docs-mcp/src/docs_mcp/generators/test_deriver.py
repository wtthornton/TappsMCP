"""Derive test case names from acceptance criteria when none are provided."""

from __future__ import annotations

import re

import structlog

logger = structlog.get_logger(__name__)


def derive_test_names(acceptance_criteria: list[str]) -> list[str]:
    """Derive test function names from acceptance criteria.

    Strips leading prefixes (AC numbers, checkbox markers), converts to
    snake_case, prefixes with ``test_``, truncates to 60 characters, and
    deduplicates with numeric suffixes.

    Args:
        acceptance_criteria: List of acceptance criterion strings.

    Returns:
        List of derived test function names.
    """
    if not acceptance_criteria:
        return []

    names: list[str] = []
    seen: dict[str, int] = {}

    for criterion in acceptance_criteria:
        name = _criterion_to_test_name(criterion)
        if not name:
            continue

        # Deduplicate.
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1

        names.append(name)

    return names


def _criterion_to_test_name(criterion: str) -> str:
    """Convert a single acceptance criterion to a test function name.

    Processing steps:
    1. Strip leading AC/number prefixes (e.g., "AC1:", "AC 2:", "1.")
    2. Strip checkbox markers (e.g., "- [ ]", "- [x]")
    3. Convert to snake_case
    4. Prefix with "test_"
    5. Truncate to 60 characters
    """
    text = criterion.strip()
    if not text:
        return ""

    # Strip "AC1:", "AC 1:", "AC1 -", etc.
    text = re.sub(r"^AC\s*\d*\s*[:.-]\s*", "", text, flags=re.IGNORECASE)

    # Strip numbered prefixes: "1.", "1)", "1 -"
    text = re.sub(r"^\d+\s*[.):-]\s*", "", text)

    # Strip checkbox markers: "- [ ]", "- [x]", "* [ ]"
    text = re.sub(r"^[-*]\s*\[[ xX]?\]\s*", "", text)

    # Strip leading "- " or "* "
    text = re.sub(r"^[-*]\s+", "", text)

    text = text.strip()
    if not text:
        return ""

    # Convert to snake_case.
    # Replace non-alphanumeric with space, collapse, strip, join with _.
    slug = re.sub(r"[^a-zA-Z0-9\s]", "", text)
    slug = re.sub(r"\s+", "_", slug.strip()).lower()

    if not slug:
        return ""

    name = f"test_{slug}"

    # Truncate to 60 characters.
    if len(name) > 60:
        name = name[:60]
        # Don't end on an underscore.
        name = name.rstrip("_")

    return name
