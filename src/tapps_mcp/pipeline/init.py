"""Bootstrap TAPPS pipeline files in a consuming project."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from pathlib import Path

from tapps_mcp.prompts.prompt_loader import (
    load_handoff_template,
    load_platform_rules,
    load_runlog_template,
)


class _SafeWriter(Protocol):
    def __call__(self, rel_path: str, content: str) -> None: ...


def bootstrap_pipeline(
    project_root: Path,
    *,
    create_handoff: bool = True,
    create_runlog: bool = True,
    platform: str = "",
) -> dict[str, Any]:
    """Create pipeline template files in the project.

    Returns a summary dict with ``created``, ``skipped``, and ``errors`` lists.

    All file writes are validated to stay within *project_root*.
    """
    created: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    project_root = project_root.resolve()

    def _safe_write(rel_path: str, content: str) -> None:
        """Write *content* to *rel_path* under project_root, safely."""
        target = (project_root / rel_path).resolve()
        # Security: ensure target is within project root
        try:
            target.relative_to(project_root)
        except ValueError:
            errors.append(f"{rel_path}: path escapes project root")
            return

        if target.exists():
            skipped.append(rel_path)
            return

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        created.append(rel_path)

    if create_handoff:
        _safe_write("docs/TAPPS_HANDOFF.md", load_handoff_template())

    if create_runlog:
        _safe_write("docs/TAPPS_RUNLOG.md", load_runlog_template())

    if platform:
        if platform == "claude":
            _bootstrap_claude(project_root, _safe_write)
        elif platform == "cursor":
            _bootstrap_cursor(_safe_write)
        else:
            errors.append(f"Unknown platform: {platform!r}. Use 'claude' or 'cursor'.")

    return {
        "created": created,
        "skipped": skipped,
        "errors": errors,
    }


def _bootstrap_claude(
    project_root: Path,
    safe_write: _SafeWriter,
) -> None:
    """Append pipeline reference to CLAUDE.md (or create it)."""
    claude_md = project_root / "CLAUDE.md"
    content = load_platform_rules("claude")

    if claude_md.exists():
        existing = claude_md.read_text(encoding="utf-8")
        if "TAPPS" in existing:
            # Already has TAPPS reference
            return
        # Append to existing file
        claude_md.write_text(
            existing.rstrip() + "\n\n" + content,
            encoding="utf-8",
        )
        return

    safe_write("CLAUDE.md", content)


def _bootstrap_cursor(safe_write: _SafeWriter) -> None:
    """Create Cursor pipeline rule file."""
    content = load_platform_rules("cursor")
    safe_write(".cursor/rules/tapps-pipeline.md", content)
