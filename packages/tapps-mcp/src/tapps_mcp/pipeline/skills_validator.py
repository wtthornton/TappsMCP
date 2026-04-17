"""Skills spec validator (Epic 76). Validates SKILL.md frontmatter against agentskills.io."""

from __future__ import annotations

import re
from typing import Any

# Agent Skills spec: name 1-64 chars, lowercase alphanumeric + hyphens; description 1-1024.
NAME_MAX_LEN = 64
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DESCRIPTION_MIN_LEN = 1
DESCRIPTION_MAX_LEN = 1024


def validate_skill_frontmatter(
    skill_name: str,
    frontmatter: dict[str, Any],
    *,
    check_allowed_tools_format: bool = True,
) -> list[str]:
    """Validate skill frontmatter against Agent Skills spec (agentskills.io).

    Args:
        skill_name: Skill key (e.g. 'tapps-score') for error messages.
        frontmatter: Parsed YAML frontmatter (e.g. from first --- block).
        check_allowed_tools_format: If True, allow-tools must be space-delimited
            or YAML list; no comma-separated string.

    Returns:
        List of error strings; empty if valid.
    """
    errors: list[str] = []

    name = frontmatter.get("name")
    if name is None:
        errors.append(f"{skill_name}: frontmatter missing 'name'")
    elif not isinstance(name, str):
        errors.append(f"{skill_name}: 'name' must be a string")
    else:
        if len(name) > NAME_MAX_LEN:
            errors.append(f"{skill_name}: 'name' exceeds {NAME_MAX_LEN} chars (got {len(name)})")
        if not NAME_PATTERN.match(name):
            errors.append(f"{skill_name}: 'name' must be lowercase alphanumeric and hyphens only")

    desc = frontmatter.get("description")
    if desc is None:
        errors.append(f"{skill_name}: frontmatter missing 'description'")
    elif not isinstance(desc, str):
        errors.append(f"{skill_name}: 'description' must be a string")
    else:
        n = len(desc)
        if n < DESCRIPTION_MIN_LEN or n > DESCRIPTION_MAX_LEN:
            errors.append(
                f"{skill_name}: 'description' must be {DESCRIPTION_MIN_LEN}-{DESCRIPTION_MAX_LEN} chars (got {n})"
            )

    if check_allowed_tools_format and "allowed-tools" in frontmatter:
        at = frontmatter["allowed-tools"]
        if isinstance(at, str) and "," in at:
            errors.append(
                f"{skill_name}: 'allowed-tools' should be space-delimited per agentskills.io (found comma)"
            )

    return errors


def get_description_from_frontmatter_raw(raw_fm: str) -> str:
    """Parse raw YAML frontmatter and return normalized description string."""
    import yaml

    data = yaml.safe_load(raw_fm)
    if not data or not isinstance(data, dict):
        return ""
    desc = data.get("description")
    if desc is None:
        return ""
    return str(desc).strip()
