"""Shared insight schema for cross-server knowledge exchange.

InsightEntry extends tapps-brain's MemoryEntry with typed fields for:
- insight_type: the domain the insight belongs to (quality, architecture, etc.)
- server_origin: which MCP server produced this insight
- schema_version: integer version for forward-compatible migration
- subject_path: optional file/module path the insight is about
- subject_kind: granularity of the subject (file, module, class, function, system)

This module is the canonical home for EPIC-102 shared insight types. Both
tapps-mcp and docs-mcp write InsightEntry records into tapps-brain so that
learnings compound across the entire AgentForge platform.

Schema version history:
  v1 (2026-04-14): Initial InsightEntry schema. All fields optional except those
                   inherited from MemoryEntry. Migration from bare MemoryEntry
                   populates insight_type=quality and server_origin=tapps-mcp by
                   default (conservative upgrade).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field
from tapps_brain.models import MemoryEntry

# ---------------------------------------------------------------------------
# Schema version sentinel
# ---------------------------------------------------------------------------

INSIGHT_SCHEMA_VERSION: int = 1
"""Current schema version. Increment when adding mandatory fields."""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class InsightType(StrEnum):
    """Domain classification of an insight."""

    quality = "quality"
    """Code quality signal from tapps-mcp scoring or gate checks."""

    architecture = "architecture"
    """Structural / design fact produced by docs-mcp architecture analysis."""

    documentation = "documentation"
    """Documentation health or coverage observation."""

    security = "security"
    """Security scan finding or remediation note."""

    pattern = "pattern"
    """Recurring coding pattern or anti-pattern observed across files."""

    dependency = "dependency"
    """Dependency relationship or version constraint."""


class InsightOrigin(StrEnum):
    """Which MCP server produced this insight."""

    tapps_mcp = "tapps-mcp"
    """TappsMCP code quality server."""

    docs_mcp = "docs-mcp"
    """DocsMCP documentation server."""

    user = "user"
    """Manually authored by a developer."""

    unknown = "unknown"
    """Origin not recorded (e.g. migrated from a bare MemoryEntry)."""


class SubjectKind(StrEnum):
    """Granularity of the subject an insight is about."""

    file = "file"
    module = "module"
    klass = "class"
    function = "function"
    system = "system"
    """Whole-project or cross-cutting concern."""


# ---------------------------------------------------------------------------
# InsightEntry model
# ---------------------------------------------------------------------------


class InsightEntry(MemoryEntry):
    """A versioned, typed memory entry for cross-server knowledge exchange.

    Extends :class:`tapps_brain.models.MemoryEntry` with insight-specific
    metadata. All extra fields carry sensible defaults so that existing
    MemoryEntry payloads can be losslessly promoted via
    :func:`tapps_core.insights.migration.migrate_memory_entry_to_insight`.

    Example::

        entry = InsightEntry(
            key="arch.tapps-core.memory.shim-pattern",
            value="tapps_core.memory is a backwards-compat shim over tapps-brain.",
            insight_type=InsightType.architecture,
            server_origin=InsightOrigin.docs_mcp,
            subject_path="packages/tapps-core/src/tapps_core/memory/__init__.py",
            subject_kind=SubjectKind.module,
        )
    """

    # ------------------------------------------------------------------
    # Insight-specific fields
    # ------------------------------------------------------------------

    insight_type: InsightType = Field(
        default=InsightType.quality,
        description="Domain classification of this insight.",
    )
    server_origin: InsightOrigin = Field(
        default=InsightOrigin.unknown,
        description="Which MCP server produced this insight.",
    )
    schema_version: Literal[1] = Field(
        default=1,
        description="InsightEntry schema version (always 1 for this release).",
    )
    subject_path: str = Field(
        default="",
        description=(
            "File or module path this insight is about "
            "(relative to project root). Empty means project-wide."
        ),
    )
    subject_kind: SubjectKind = Field(
        default=SubjectKind.system,
        description="Granularity of the subject.",
    )
