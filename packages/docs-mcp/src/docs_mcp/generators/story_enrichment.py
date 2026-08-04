"""Auto-population and enrichment for story generation.

Pulls project metadata, module maps, and expert guidance into the
generated story when ``auto_populate`` is on. Split out of
``stories.py`` under TAP-5609.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, ClassVar

import structlog

from docs_mcp.generators.story_base import StoryGeneratorBase
from docs_mcp.generators.story_models import StoryConfig

logger = structlog.get_logger(__name__)


class EnrichmentMixin(StoryGeneratorBase):
    """Auto-population and enrichment for story generation."""

    _AUTO_POPULATE_TIMEOUT_S: ClassVar[float] = 15.0

    def _auto_populate(
        self,
        project_root: Path,
        config: StoryConfig | None = None,
    ) -> dict[str, Any]:
        """Gather enrichment data from project analyzers and domain experts.

        Returns a dict with optional keys: tech_stack, module_summary,
        expert_guidance. Each key is only present when the corresponding
        analyzer/expert succeeds.

        A wall-clock budget of 15 s is enforced.  If a step exhausts the
        budget the remaining steps are skipped and partial results returned.
        """
        enrichment: dict[str, Any] = {}
        t_wall = time.perf_counter()
        budget = self._AUTO_POPULATE_TIMEOUT_S

        def _remaining() -> float:
            return budget - (time.perf_counter() - t_wall)

        steps: list[tuple[str, Any, list[Any]]] = [
            ("metadata", self._enrich_metadata, [project_root, enrichment]),
            ("module_map", self._enrich_module_map, [project_root, enrichment]),
        ]

        for key, fn, args in steps:
            if _remaining() <= 0:
                logger.warning("story_auto_populate_budget_exceeded", skipped=key)
                continue
            fn(*args)

        if config and _remaining() > 0:
            self._enrich_experts(config, enrichment)
        elif config:
            logger.warning("story_auto_populate_budget_exceeded", skipped="experts")

        return enrichment

    @staticmethod
    def _enrich_metadata(project_root: Path, enrichment: dict[str, Any]) -> None:
        """Enrich with tech stack from MetadataExtractor."""
        try:
            from docs_mcp.generators.metadata import MetadataExtractor

            extractor = MetadataExtractor()
            metadata = extractor.extract(project_root)
            parts: list[str] = []
            if metadata.name:
                parts.append(metadata.name)
            if metadata.python_requires:
                parts.append(f"Python {metadata.python_requires}")
            if parts:
                enrichment["tech_stack"] = ", ".join(parts)
        except Exception:
            logger.debug("story_auto_populate_metadata_failed", exc_info=True)

    @staticmethod
    def _enrich_module_map(project_root: Path, enrichment: dict[str, Any]) -> None:
        """Enrich with module structure from ModuleMapAnalyzer.

        Uses a shallow depth (3) to avoid hanging on large projects.
        """
        try:
            from docs_mcp.analyzers.module_map import ModuleMapAnalyzer

            analyzer = ModuleMapAnalyzer()
            module_map = analyzer.analyze(project_root, depth=3)
            enrichment["module_summary"] = (
                f"{module_map.total_packages} packages, "
                f"{module_map.total_modules} modules, "
                f"{module_map.public_api_count} public APIs"
            )
        except Exception:
            logger.debug("story_auto_populate_module_map_failed", exc_info=True)

    @staticmethod
    def _enrich_experts(config: StoryConfig, enrichment: dict[str, Any]) -> None:
        """Enrich stories with bundled domain playbook excerpts (ADR-0025)."""
        from docs_mcp.generators.domain_enrichment import enrich_expert_guidance

        context_parts = [
            config.title or "",
            config.purpose_and_intent or "",
            " ".join(config.acceptance_criteria) if config.acceptance_criteria else "",
        ]
        enrich_expert_guidance("\n".join(context_parts), enrichment, limit=2)
