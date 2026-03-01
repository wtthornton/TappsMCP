"""Module coupling analysis based on import graphs.

Calculates afferent coupling (Ca), efferent coupling (Ce), and
instability (I = Ce / (Ca + Ce)) for every module in the graph.
Identifies hub modules with high coupling in both directions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from tapps_mcp.project.import_graph import ImportGraph

logger = structlog.get_logger(__name__)

# A module is considered a "hub" when both afferent and efferent coupling
# meet or exceed this threshold.
HUB_THRESHOLD = 8


@dataclass
class ModuleCoupling:
    """Coupling metrics for a single module."""

    module: str
    afferent: int = 0  # Ca: modules that depend on this one
    efferent: int = 0  # Ce: modules this one depends on
    instability: float = 0.0  # I = Ce / (Ca + Ce), 0=stable, 1=unstable
    is_hub: bool = False  # high Ca AND high Ce


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def calculate_coupling(graph: ImportGraph) -> list[ModuleCoupling]:
    """Calculate coupling metrics for all modules in *graph*.

    Args:
        graph: An :class:`ImportGraph` built by :func:`build_import_graph`.

    Returns:
        A list of :class:`ModuleCoupling` sorted by total coupling
        (Ca + Ce) descending.
    """
    # Count unique afferent and efferent relationships per module.
    afferent_sets: dict[str, set[str]] = {mod: set() for mod in graph.modules}
    efferent_sets: dict[str, set[str]] = {mod: set() for mod in graph.modules}

    for edge in graph.edges:
        src = edge.source_module
        tgt = edge.target_module
        if src in efferent_sets:
            efferent_sets[src].add(tgt)
        if tgt in afferent_sets:
            afferent_sets[tgt].add(src)

    results: list[ModuleCoupling] = []
    for mod in graph.modules:
        ca = len(afferent_sets.get(mod, set()))
        ce = len(efferent_sets.get(mod, set()))
        total = ca + ce
        instability = ce / total if total > 0 else 0.0
        is_hub = ca >= HUB_THRESHOLD and ce >= HUB_THRESHOLD

        results.append(
            ModuleCoupling(
                module=mod,
                afferent=ca,
                efferent=ce,
                instability=round(instability, 4),
                is_hub=is_hub,
            )
        )

    # Sort by total coupling (Ca + Ce) descending, then alphabetically
    results.sort(key=lambda m: (-(m.afferent + m.efferent), m.module))

    logger.info(
        "coupling_metrics_calculated",
        modules=len(results),
        hubs=sum(1 for m in results if m.is_hub),
    )
    return results


def suggest_coupling_fixes(
    metrics: list[ModuleCoupling],
    limit: int = 5,
) -> list[str]:
    """Generate suggestions for over-coupled modules.

    Args:
        metrics: Coupling metrics from :func:`calculate_coupling`.
        limit: Maximum number of suggestions to return.

    Returns:
        Human-readable suggestions for reducing coupling.
    """
    if not metrics:
        return ["No modules analysed - no coupling suggestions."]

    suggestions: list[str] = []

    # Hub modules
    hubs = [m for m in metrics if m.is_hub]
    for hub in hubs[:limit]:
        suggestions.append(
            f"Module '{hub.module}' is a hub: imported by {hub.afferent} modules"
            f" and imports {hub.efferent} modules - consider splitting"
            " into smaller, focused modules."
        )

    # High efferent coupling (not already flagged as hub)
    high_efferent = [m for m in metrics if m.efferent >= HUB_THRESHOLD and not m.is_hub]
    remaining = limit - len(suggestions)
    for mod in high_efferent[:remaining]:
        suggestions.append(
            f"Module '{mod.module}' depends on {mod.efferent} modules"
            " - reduce by extracting shared logic into utility modules."
        )

    if not suggestions:
        suggestions.append("Coupling levels are within acceptable thresholds.")

    return suggestions
