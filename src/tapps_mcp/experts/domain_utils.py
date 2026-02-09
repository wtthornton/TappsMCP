"""Utility functions for domain name handling."""

from __future__ import annotations

import re
from urllib.parse import urlparse

# Known domain-to-directory mappings for built-in experts.
# Maps expert domain names to their actual knowledge-base directory names.
_MAX_DIRECTORY_NAME_LENGTH = 200

DOMAIN_TO_DIRECTORY_MAP: dict[str, str] = {
    "performance-optimization": "performance",
    "ai-agent-framework": "ai-frameworks",
    "testing-strategies": "testing",
}


def sanitize_domain_for_path(domain: str) -> str:
    """Sanitise a domain name or URL for use as a directory path.

    Handles URLs by extracting the hostname and path, then sanitising
    invalid filename characters.  Also applies known domain-to-directory
    name mappings for built-in experts.

    Args:
        domain: Domain name or URL
            (e.g. ``"home-automation"`` or ``"https://www.home-assistant.io/docs/"``).

    Returns:
        Sanitised string safe for use as a directory name.
    """
    if not domain:
        return "unknown"

    # Check for known mappings first.
    if domain in DOMAIN_TO_DIRECTORY_MAP:
        return DOMAIN_TO_DIRECTORY_MAP[domain]

    # Try to parse as URL.
    try:
        parsed = urlparse(domain)
        if parsed.netloc:
            parts = [parsed.netloc.replace("www.", "")]
            if parsed.path and parsed.path != "/":
                path_parts = [p for p in parsed.path.strip("/").split("/") if p]
                parts.extend(path_parts)
            domain = "-".join(parts)
    except Exception:  # noqa: S110
        pass  # Not a valid URL — use as-is.

    # Replace invalid filename characters with hyphens.
    sanitized = re.sub(r'[<>:"/\\|?*\s&]+', "-", domain)

    # Remove leading/trailing dots and hyphens.
    sanitized = sanitized.strip(".-")

    # Collapse consecutive hyphens.
    sanitized = re.sub(r"-+", "-", sanitized)

    if not sanitized:
        sanitized = "unknown"
    elif len(sanitized) > _MAX_DIRECTORY_NAME_LENGTH:
        sanitized = sanitized[:_MAX_DIRECTORY_NAME_LENGTH].rstrip("-")

    return sanitized.lower()
