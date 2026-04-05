"""Structured YAML frontmatter injection and update for markdown files.

Adds or updates YAML frontmatter metadata in existing markdown documents,
preserving existing fields while merging auto-detected values.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import structlog
from pydantic import BaseModel

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

_FRONTMATTER_PATTERN = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)

# Keywords that hint at Diataxis quadrants (used as lightweight fallback
# when the full Diataxis classifier from Epic 82 is not available).
_DIATAXIS_HINTS: dict[str, list[str]] = {
    "tutorial": ["getting started", "step by step", "learn", "tutorial", "walkthrough"],
    "how-to": ["how to", "guide", "recipe", "configure", "set up", "install"],
    "reference": ["api", "reference", "specification", "parameters", "returns"],
    "explanation": ["why", "background", "architecture", "design", "concept"],
}


class FrontmatterResult(BaseModel):
    """Result of frontmatter generation or update."""

    content: str
    fields_added: list[str]
    fields_preserved: list[str]
    had_existing: bool


class FrontmatterGenerator:
    """Injects or updates YAML frontmatter in markdown files.

    Preserves existing fields, merges new auto-detected values, and
    supports manual override via existing frontmatter keys.
    """

    MANAGED_FIELDS: ClassVar[frozenset[str]] = frozenset({
        "title", "description", "category", "diataxis_type",
        "last_modified", "tags",
    })

    def generate(
        self,
        content: str,
        *,
        file_path: Path | None = None,
        extra_fields: dict[str, Any] | None = None,
    ) -> FrontmatterResult:
        """Add or update frontmatter in markdown content.

        Args:
            content: The markdown file content.
            file_path: Optional path for tag/category inference.
            extra_fields: Additional fields to include in frontmatter.

        Returns:
            FrontmatterResult with updated content and field tracking.
        """
        existing, body = self._parse_existing(content)
        had_existing = bool(existing)

        # Auto-detect fields
        auto: dict[str, Any] = {}
        auto["title"] = self._detect_title(body)
        auto["description"] = self._detect_description(body)
        if file_path is not None:
            auto["tags"] = self._detect_tags(body, file_path)
        auto["diataxis_type"] = self._detect_diataxis_type(body)
        auto["last_modified"] = datetime.now(tz=UTC).strftime("%Y-%m-%d")

        # Merge: existing fields take precedence over auto-detected
        merged: dict[str, Any] = {}
        fields_added: list[str] = []
        fields_preserved: list[str] = []

        # Start with auto-detected
        for key, value in auto.items():
            if value:
                merged[key] = value

        # Override with extra_fields
        if extra_fields:
            for key, value in extra_fields.items():
                if value is not None:
                    merged[key] = value

        # Preserve existing fields (they win)
        for key, value in existing.items():
            if key in merged:
                fields_preserved.append(key)
            merged[key] = value

        # Track what was newly added
        for key in merged:
            if key not in existing:
                fields_added.append(key)

        # Render frontmatter
        fm_lines = ["---"]
        for key, value in merged.items():
            if isinstance(value, list):
                if value:
                    fm_lines.append(f"{key}:")
                    for item in value:
                        fm_lines.append(f"  - {item}")
            elif isinstance(value, str) and "\n" in value:
                fm_lines.append(f"{key}: |")
                for line in value.split("\n"):
                    fm_lines.append(f"  {line}")
            else:
                # Quote strings that contain special YAML characters
                str_val = str(value)
                if any(c in str_val for c in ":#{}[]|>&*?!%@`"):
                    fm_lines.append(f'{key}: "{str_val}"')
                else:
                    fm_lines.append(f"{key}: {str_val}")
        fm_lines.append("---")
        fm_lines.append("")

        new_content = "\n".join(fm_lines) + body

        return FrontmatterResult(
            content=new_content,
            fields_added=fields_added,
            fields_preserved=fields_preserved,
            had_existing=had_existing,
        )

    def _parse_existing(self, content: str) -> tuple[dict[str, Any], str]:
        """Parse existing YAML frontmatter from content.

        Returns:
            Tuple of (parsed fields dict, remaining body content).
        """
        match = _FRONTMATTER_PATTERN.match(content)
        if not match:
            return {}, content

        fm_text = match.group(1)
        body = content[match.end():]

        # Simple YAML parser for flat key-value pairs
        fields: dict[str, Any] = {}
        current_key = ""
        current_list: list[str] = []

        for line in fm_text.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue

            # List item
            if stripped.startswith("- ") and current_key:
                current_list.append(stripped[2:].strip())
                continue

            # Flush any pending list
            if current_key and current_list:
                fields[current_key] = current_list
                current_list = []
                current_key = ""

            # Key-value pair
            if ":" in stripped:
                key, _, value = stripped.partition(":")
                key = key.strip()
                value = value.strip()
                if value:
                    # Remove surrounding quotes
                    if (value.startswith('"') and value.endswith('"')) or (
                        value.startswith("'") and value.endswith("'")
                    ):
                        value = value[1:-1]
                    fields[key] = value
                else:
                    # Might be a list or multiline
                    current_key = key

        # Flush final list
        if current_key and current_list:
            fields[current_key] = current_list

        return fields, body

    def _detect_title(self, body: str) -> str:
        """Detect title from first H1 heading."""
        for line in body.split("\n"):
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("##"):
                return stripped[2:].strip()
        return ""

    def _detect_description(self, body: str) -> str:
        """Detect description from first non-heading paragraph."""
        in_paragraph = False
        para_lines: list[str] = []

        for line in body.split("\n"):
            stripped = line.strip()

            # Skip headings, blank lines before first paragraph
            if stripped.startswith("#"):
                if in_paragraph:
                    break
                continue
            if not stripped:
                if in_paragraph:
                    break
                continue

            # Skip special lines
            if stripped.startswith(("- ", "* ", "1.", "|", "```", ">")):
                if in_paragraph:
                    break
                continue

            in_paragraph = True
            para_lines.append(stripped)

        desc = " ".join(para_lines)
        # Truncate long descriptions
        if len(desc) > 200:
            desc = desc[:197] + "..."
        return desc

    def _detect_tags(self, body: str, file_path: Path) -> list[str]:
        """Detect tags from content keywords and file path."""
        tags: set[str] = set()

        # Tags from file path components
        for part in file_path.parts:
            part_lower = part.lower()
            if part_lower in ("docs", "src", "tests", "packages"):
                continue
            if part_lower.endswith(".md"):
                # Use filename without extension as tag
                name = part_lower[:-3].replace("_", "-").replace(" ", "-")
                if len(name) > 2 and name not in ("readme", "index"):
                    tags.add(name)

        # Tags from content keywords
        body_lower = body.lower()
        keyword_tags = {
            "api": ["api", "endpoint", "rest", "graphql"],
            "testing": ["test", "pytest", "unittest", "coverage"],
            "security": ["security", "authentication", "authorization", "vulnerability"],
            "deployment": ["deploy", "docker", "kubernetes", "ci/cd"],
            "configuration": ["config", "configuration", "settings", "environment"],
        }
        for tag, keywords in keyword_tags.items():
            if any(kw in body_lower for kw in keywords):
                tags.add(tag)

        return sorted(tags)[:10]

    def _detect_diataxis_type(self, body: str) -> str:
        """Lightweight Diataxis classification from content hints."""
        body_lower = body.lower()
        scores: dict[str, int] = {}

        for quadrant, keywords in _DIATAXIS_HINTS.items():
            score = sum(1 for kw in keywords if kw in body_lower)
            if score > 0:
                scores[quadrant] = score

        if not scores:
            return ""

        return max(scores, key=scores.get)  # type: ignore[arg-type]
