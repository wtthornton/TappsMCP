"""tapps-brain write path for docs-mcp architecture facts (STORY-102.2).

When ``brain_write_enabled`` is set in ``.docsmcp.yaml``, this module writes
structured architecture facts into tapps-brain after analysis tools run.
Facts are written as MemoryEntry records using the InsightEntry tagging
convention so that :func:`tapps_core.insights.migration.bulk_migrate` can
promote them later.

Key tagging convention
----------------------
Every entry written by this module carries:
  - ``"architecture"`` — marks the domain
  - ``"docs-mcp"`` — marks the producing server
  - ``"insight-type:{type}"`` — e.g. ``"insight-type:architecture"``
  - ``"schema-v1"`` — marks the INSIGHT_SCHEMA_VERSION

memory_group
  ``"insights"`` — separates insight entries from session/project memories.

Key scheme
----------
All keys are lowercase slugs matching ``^[a-z0-9][a-z0-9._-]{0,127}$``::

    arch.{project}.structure         ← overall project structure summary
    arch.{project}.pkg.{pkg_name}    ← per-package description + stats
    arch.{project}.entry_points      ← comma-separated entry point list

tapps-brain availability
------------------------
tapps-brain is an optional runtime dependency of docs-mcp. This module
imports it inside functions and catches ``ImportError`` so that docs-mcp
continues to work when tapps-brain is not installed.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from docs_mcp.analyzers.models import ModuleMap, ModuleNode
    from docs_mcp.generators.architecture import ArchitectureResult

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SOURCE_AGENT = "docs-mcp"
_MEMORY_TIER = "architectural"
_MEMORY_SCOPE = "project"
_MEMORY_GROUP = "insights"
_BASE_TAGS: list[str] = ["architecture", "docs-mcp", "insight-type:architecture", "schema-v1"]

# Key length ceiling (tapps-brain enforces 128 chars)
_MAX_KEY_LEN = 128
# Max packages to write per module_map call (avoid flooding the store)
_MAX_PACKAGES = 30
# Max value length (tapps-brain enforces 4096 chars)
_MAX_VALUE_LEN = 4096


# ---------------------------------------------------------------------------
# Key slug helpers
# ---------------------------------------------------------------------------

_SLUG_ALLOWED = re.compile(r"[^a-z0-9._-]")


def _slugify(text: str) -> str:
    """Convert an arbitrary string into a valid tapps-brain key segment.

    Lowercases, collapses invalid characters to ``.``, strips leading/trailing
    dots and hyphens, and truncates to avoid overflowing the key budget.
    """
    lowered = text.lower()
    slugged = _SLUG_ALLOWED.sub(".", lowered)
    # Collapse runs of separators
    slugged = re.sub(r"[._-]{2,}", ".", slugged)
    slugged = slugged.strip(".-")
    return slugged or "unknown"


def _build_key(*parts: str) -> str:
    """Join key segments and ensure max length."""
    key = ".".join(_slugify(p) for p in parts)
    # Ensure starts with alphanumeric
    key = re.sub(r"^[._-]+", "", key)
    return key[:_MAX_KEY_LEN]


def _truncate(value: str) -> str:
    """Truncate value to tapps-brain's max length."""
    return value[:_MAX_VALUE_LEN]


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class BrainWriteResult:
    """Result of a brain write operation."""

    written: int = 0
    skipped: int = 0
    failed: int = 0
    elapsed_ms: float = 0.0
    available: bool = True
    entries_written: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.written + self.skipped + self.failed

    def to_dict(self) -> dict[str, Any]:
        return {
            "brain_write": {
                "available": self.available,
                "written": self.written,
                "skipped": self.skipped,
                "failed": self.failed,
                "elapsed_ms": round(self.elapsed_ms, 1),
            }
        }


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


class ArchitectureBrainWriter:
    """Writes architecture facts into tapps-brain as InsightEntry-tagged records.

    This class is instantiated once per tool call. It opens the MemoryStore
    lazily and falls back to ``available=False`` when tapps-brain is absent.

    Args:
        project_root: Project root path (determines store location).
    """

    def __init__(self, project_root: Path) -> None:
        self._root = project_root
        self._store: Any = None  # tapps_brain.store.MemoryStore | None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write_from_architecture_result(
        self,
        result: ArchitectureResult,
        project_name: str,
    ) -> BrainWriteResult:
        """Write a top-level structure summary from an ArchitectureGenerator result.

        Produces a single ``arch.{project}.structure`` entry summarising package,
        module, edge and class counts.
        """
        t0 = time.perf_counter()
        store = self._get_store()
        if store is None:
            return BrainWriteResult(available=False)

        br = BrainWriteResult()
        key = _build_key("arch", project_name, "structure")
        value = _truncate(
            f"Architecture summary for {project_name}: "
            f"{result.package_count} packages, {result.module_count} modules, "
            f"{result.edge_count} import edges, {result.class_count} classes."
        )
        self._save(store, br, key, value)
        br.elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "arch_brain_write_structure",
            project=project_name,
            written=br.written,
            failed=br.failed,
        )
        return br

    def write_from_module_map(self, module_map: ModuleMap) -> BrainWriteResult:
        """Write per-package and entry-point facts from a ModuleMap result.

        Writes one ``arch.{project}.pkg.{name}`` entry per top-level package
        (capped at :data:`_MAX_PACKAGES`) and an ``arch.{project}.entry_points``
        entry when entry points are present.
        """
        t0 = time.perf_counter()
        store = self._get_store()
        if store is None:
            return BrainWriteResult(available=False)

        br = BrainWriteResult()
        project = module_map.project_name

        # Per-package entries
        for node in module_map.module_tree[:_MAX_PACKAGES]:
            key = _build_key("arch", project, "pkg", node.name)
            value = self._describe_node(project, node)
            self._save(store, br, key, value)

        # Entry points
        if module_map.entry_points:
            ep_key = _build_key("arch", project, "entry_points")
            ep_value = _truncate(
                f"Entry points for {project}: " + ", ".join(module_map.entry_points[:20])
            )
            self._save(store, br, ep_key, ep_value)

        br.elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "arch_brain_write_module_map",
            project=project,
            written=br.written,
            failed=br.failed,
        )
        return br

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_store(self) -> Any:
        """Return a cached MemoryStore, or None if tapps-brain is unavailable."""
        if self._store is not None:
            return self._store
        try:
            from tapps_brain.store import MemoryStore

            self._store = MemoryStore(self._root)
            return self._store
        except ImportError:
            logger.debug("tapps_brain_not_available", root=str(self._root))
            return None
        except Exception:
            logger.warning(
                "tapps_brain_store_open_failed",
                root=str(self._root),
                exc_info=True,
            )
            return None

    def _save(
        self,
        store: Any,
        br: BrainWriteResult,
        key: str,
        value: str,
    ) -> None:
        """Attempt a single store.save(); update BrainWriteResult in-place."""
        try:
            store.save(
                key=key,
                value=value,
                tier=_MEMORY_TIER,
                source="system",
                source_agent=_SOURCE_AGENT,
                scope=_MEMORY_SCOPE,
                tags=list(_BASE_TAGS),
                memory_group=_MEMORY_GROUP,
                skip_consolidation=True,
            )
            br.written += 1
            br.entries_written.append(key)
        except Exception:
            logger.warning("brain_write_failed", key=key, exc_info=True)
            br.failed += 1

    @staticmethod
    def _describe_node(project: str, node: ModuleNode) -> str:
        """Build a concise value string for a ModuleNode."""
        parts = [f"Package {node.name} in {project}:"]
        if node.module_docstring:
            # Take the first sentence / line of the docstring
            first_line = node.module_docstring.split("\n")[0].strip().rstrip(".")
            if first_line:
                parts.append(first_line + ".")
        stats: list[str] = []
        if node.public_api_count:
            stats.append(f"{node.public_api_count} public API symbols")
        if node.class_count:
            stats.append(f"{node.class_count} classes")
        if node.function_count:
            stats.append(f"{node.function_count} functions")
        if node.submodules:
            stats.append(f"{len(node.submodules)} submodules")
        if stats:
            parts.append("Contains " + ", ".join(stats) + ".")
        return _truncate(" ".join(parts))
