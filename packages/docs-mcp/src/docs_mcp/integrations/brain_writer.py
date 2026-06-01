"""tapps-brain write path for docs-mcp architecture facts (STORY-102.2).

When ``brain_write_enabled`` is set in ``.docsmcp.yaml``, this module writes
structured architecture facts into tapps-brain after analysis tools run.
Facts are written as MemoryEntry records using the InsightEntry tagging
convention so that :func:`tapps_core.insights.migration.bulk_migrate` can
promote them later.

Writes route through :class:`tapps_core.brain_bridge.BrainBridge` (TAP-1919,
ADR-0001) so every save participates in the bridge's circuit-breaker,
profile filter (TAP-1579), content-safety gate, Hive routing, and
async-native Postgres write path (TAP-1117). Bypassing the bridge — e.g.
importing :class:`tapps_brain.store.MemoryStore` directly — is a violation
of ``.claude/rules/integration-hygiene.md`` and produces silent data loss
into an embedded SQLite shadow.

Profile pinning (TAP-1925)
--------------------------
The bridge factory is called with ``default_profile="agent_brain"`` so
docs-mcp only sees the 10-tool ``brain_*`` facade on the wire
(``brain_remember``, ``brain_recall``, ``brain_record_event``,
``brain_get_neighbors``, ``brain_explain_connection``). Any attempt to call
``memory_*``, ``hive_*``, or ``maintenance_*`` tools surfaces a
:class:`tapps_core.brain_bridge.ToolNotInProfileError` — loud, never silent.
The ``agent_brain`` profile is the minimum surface docs-mcp needs and
reduces the ``/v1/tools/list`` payload from ~40 entries to 10.

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
tapps-brain is an optional runtime dependency of docs-mcp; the BrainBridge
factory in ``tapps_core.brain_bridge`` returns ``None`` when no transport is
configured (no ``TAPPS_MCP_MEMORY_BRAIN_HTTP_URL`` and no
``TAPPS_BRAIN_DATABASE_URL``). Callers receive ``BrainWriteResult(available=False)``.
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
    """Writes architecture facts into tapps-brain via :class:`BrainBridge`.

    Instantiated once per tool call. The bridge is opened lazily and the
    writer falls back to ``BrainWriteResult(available=False)`` when no
    bridge transport is configured (no HTTP URL, no in-process DSN). All
    writes go through the bridge's circuit-breaker, profile filter,
    content-safety gate, and async-native write path.

    Args:
        project_root: Project root path (passed to in-process bridge for
            ``project_dir`` resolution; ignored by the HTTP bridge).
    """

    def __init__(self, project_root: Path) -> None:
        self._root = project_root
        self._bridge: Any = None  # tapps_core.brain_bridge.BrainBridge | None
        self._bridge_resolved: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def write_from_architecture_result(
        self,
        result: ArchitectureResult,
        project_name: str,
    ) -> BrainWriteResult:
        """Write a top-level structure summary from an ArchitectureGenerator result.

        Produces a single ``arch.{project}.structure`` entry summarising package,
        module, edge and class counts.
        """
        t0 = time.perf_counter()
        bridge = self._get_bridge()
        if bridge is None:
            return BrainWriteResult(available=False)

        br = BrainWriteResult()
        key = _build_key("arch", project_name, "structure")
        value = _truncate(
            f"Architecture summary for {project_name}: "
            f"{result.package_count} packages, {result.module_count} modules, "
            f"{result.edge_count} import edges, {result.class_count} classes."
        )
        await self._save(bridge, br, key, value)
        br.elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "arch_brain_write_structure",
            project=project_name,
            written=br.written,
            failed=br.failed,
        )
        return br

    async def write_from_module_map(self, module_map: ModuleMap) -> BrainWriteResult:
        """Write per-package and entry-point facts from a ModuleMap result.

        Writes one ``arch.{project}.pkg.{name}`` entry per top-level package
        (capped at :data:`_MAX_PACKAGES`) and an ``arch.{project}.entry_points``
        entry when entry points are present.
        """
        t0 = time.perf_counter()
        bridge = self._get_bridge()
        if bridge is None:
            return BrainWriteResult(available=False)

        br = BrainWriteResult()
        project = module_map.project_name

        # Per-package entries
        for node in module_map.module_tree[:_MAX_PACKAGES]:
            key = _build_key("arch", project, "pkg", node.name)
            value = self._describe_node(project, node)
            await self._save(bridge, br, key, value)

        # Entry points
        if module_map.entry_points:
            ep_key = _build_key("arch", project, "entry_points")
            ep_value = _truncate(
                f"Entry points for {project}: " + ", ".join(module_map.entry_points[:20])
            )
            await self._save(bridge, br, ep_key, ep_value)

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

    def _get_bridge(self) -> Any:
        """Return a cached BrainBridge, or None if no transport is configured.

        Delegates to :func:`tapps_core.brain_bridge.create_brain_bridge`. The
        factory selects between HttpBrainBridge (when
        ``TAPPS_MCP_MEMORY_BRAIN_HTTP_URL`` is set) and the in-process
        BrainBridge (when ``TAPPS_BRAIN_DATABASE_URL`` is set), and returns
        None when neither is configured. Result is cached for the lifetime
        of this writer instance.
        """
        if self._bridge_resolved:
            return self._bridge
        self._bridge_resolved = True
        try:
            from tapps_core.brain_bridge import create_brain_bridge

            self._bridge = create_brain_bridge(settings=None, default_profile="agent_brain")
            if self._bridge is None:
                logger.debug("brain_bridge_unavailable", root=str(self._root))
            return self._bridge
        except ImportError:
            logger.debug("tapps_core_not_available", root=str(self._root))
            return None
        except Exception:
            logger.warning(
                "brain_bridge_open_failed",
                root=str(self._root),
                exc_info=True,
            )
            return None

    async def _save(
        self,
        bridge: Any,
        br: BrainWriteResult,
        key: str,
        value: str,
    ) -> None:
        """Write key/value to brain, preferring supersede over save on regen.

        Tries ``bridge.supersede(key, new_value)`` first so regeneration
        preserves the supersession chain in brain's history. Falls back to
        ``bridge.save()`` when the key is absent (first write) — indicated by
        either a ``{"error": "not_found"}`` response or an exception from the
        in-process bridge (which raises on missing keys rather than returning
        an error dict).
        """
        # --- supersede path (regen: key already exists) ---
        supersede_result: dict[str, Any] | None = None
        try:
            supersede_result = await bridge.supersede(key=key, new_value=value)
        except Exception:
            # In-process bridge raises BrainBridgeUnavailable (wrapping e.g.
            # KeyError) when the key is absent.  Any exception here means we
            # should fall through to the save path below.
            supersede_result = None

        if supersede_result is not None and not (
            isinstance(supersede_result, dict)
            and supersede_result.get("error") == "not_found"
        ):
            # Supersede was attempted and the key existed.
            if isinstance(supersede_result, dict) and (
                supersede_result.get("success") is False
                or supersede_result.get("degraded") is True
            ):
                logger.warning(
                    "brain_supersede_degraded",
                    key=key,
                    reason=supersede_result.get("reason", ""),
                )
                br.failed += 1
                return
            br.written += 1
            br.entries_written.append(key)
            return

        # --- save path (first write: key absent) ---
        try:
            result = await bridge.save(
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
        except Exception:
            logger.warning("brain_write_failed", key=key, exc_info=True)
            br.failed += 1
            return
        if isinstance(result, dict) and (
            result.get("success") is False or result.get("degraded") is True
        ):
            logger.warning(
                "brain_write_degraded",
                key=key,
                reason=result.get("reason", ""),
                queued=result.get("queued", False),
            )
            br.failed += 1
            return
        br.written += 1
        br.entries_written.append(key)

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
