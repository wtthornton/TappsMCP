"""TappsMCP integration for optional quality enrichment in DocsMCP.

Reads shared file artifacts produced by TappsMCP to enrich documentation
with quality scores, project profiles, and dependency data. All methods
return safe defaults when TappsMCP data is unavailable - DocsMCP never
fails due to missing TappsMCP data.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import structlog
from pydantic import BaseModel

log: structlog.stdlib.BoundLogger = structlog.get_logger()

_EXPORT_FILENAME = "docsmcp-export.json"
_SUPPORTED_VERSION = "1.0"

_SCORE_THRESHOLD_HIGH = 80
_SCORE_THRESHOLD_MEDIUM = 60


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TappsQualityScore(BaseModel):
    """Quality score data from TappsMCP."""

    file_path: str
    overall_score: float
    category_scores: dict[str, float] = {}


class TappsProjectProfile(BaseModel):
    """Project profile data from TappsMCP."""

    project_type: str = ""
    tech_stack: dict[str, Any] = {}
    has_ci: bool = False
    ci_systems: list[str] = []
    has_docker: bool = False
    has_tests: bool = False
    test_frameworks: list[str] = []
    package_managers: list[str] = []


class TappsDependencyData(BaseModel):
    """Dependency graph data from TappsMCP."""

    total_modules: int = 0
    total_edges: int = 0
    cycles: list[list[str]] = []
    coupling: list[dict[str, Any]] = []


class TappsEnrichment(BaseModel):
    """Combined TappsMCP enrichment data for DocsMCP."""

    available: bool = False
    quality_scores: list[TappsQualityScore] = []
    project_profile: TappsProjectProfile | None = None
    dependency_data: TappsDependencyData | None = None
    overall_project_score: float | None = None


# ---------------------------------------------------------------------------
# Integration class
# ---------------------------------------------------------------------------


class TappsIntegration:
    """Reads TappsMCP data from shared file artifacts for optional enrichment.

    All methods return ``None`` or empty defaults when TappsMCP data is
    unavailable.  DocsMCP never fails due to missing TappsMCP data.
    """

    def __init__(self, project_root: Path) -> None:
        self._root = project_root
        self._tapps_dir = project_root / ".tapps-mcp"

    # -- availability -------------------------------------------------------

    @property
    def is_available(self) -> bool:
        """Return True when the .tapps-mcp directory exists."""
        return self._tapps_dir.is_dir()

    # -- full enrichment ----------------------------------------------------

    def load_enrichment(self) -> TappsEnrichment:
        """Load combined enrichment data from the TappsMCP export file.

        Returns a ``TappsEnrichment`` with ``available=False`` when the
        export file is missing, malformed, or has an unsupported version.
        """
        if not self.is_available:
            return TappsEnrichment(available=False)

        try:
            data = self._read_export()
            if data is None:
                return TappsEnrichment(available=False)

            version = data.get("version", "")
            if version != _SUPPORTED_VERSION:
                log.debug(
                    "tapps_export_version_mismatch",
                    expected=_SUPPORTED_VERSION,
                    got=version,
                )
                return TappsEnrichment(available=False)

            quality_scores = [TappsQualityScore(**qs) for qs in data.get("quality_scores", [])]

            profile_raw = data.get("project_profile")
            profile = TappsProjectProfile(**profile_raw) if profile_raw else None

            dep_raw = data.get("dependency_data")
            dep_data = TappsDependencyData(**dep_raw) if dep_raw else None

            return TappsEnrichment(
                available=True,
                quality_scores=quality_scores,
                project_profile=profile,
                dependency_data=dep_data,
                overall_project_score=data.get("overall_project_score"),
            )
        except Exception:
            log.debug(
                "tapps_enrichment_load_failed",
                tapps_dir=str(self._tapps_dir),
                exc_info=True,
            )
            return TappsEnrichment(available=False)

    # -- individual loaders -------------------------------------------------

    def load_project_profile(self) -> TappsProjectProfile | None:
        """Load project profile from the TappsMCP export file.

        Returns ``None`` when the data is unavailable or cannot be parsed.
        """
        try:
            data = self._read_export()
            if data is None:
                return None

            profile_raw = data.get("project_profile")
            if not profile_raw:
                return None

            return TappsProjectProfile(**profile_raw)
        except Exception:
            log.debug(
                "tapps_profile_load_failed",
                tapps_dir=str(self._tapps_dir),
                exc_info=True,
            )
            return None

    def load_quality_scores(self) -> list[TappsQualityScore]:
        """Load quality scores from the TappsMCP export file.

        Returns an empty list when the data is unavailable or cannot be
        parsed.
        """
        try:
            data = self._read_export()
            if data is None:
                return []

            return [TappsQualityScore(**qs) for qs in data.get("quality_scores", [])]
        except Exception:
            log.debug(
                "tapps_quality_scores_load_failed",
                tapps_dir=str(self._tapps_dir),
                exc_info=True,
            )
            return []

    # -- badge generators ---------------------------------------------------

    @staticmethod
    def generate_quality_badge(score: float) -> str:
        """Generate a shields.io quality score badge in Markdown.

        Args:
            score: The overall quality score (0-100).

        Returns:
            Markdown image string for the quality badge.
        """
        if score >= _SCORE_THRESHOLD_HIGH:
            color = "brightgreen"
        elif score >= _SCORE_THRESHOLD_MEDIUM:
            color = "yellow"
        else:
            color = "red"

        encoded_score = urllib.parse.quote(f"{score:.0f}%")
        return f"![Quality](https://img.shields.io/badge/quality-{encoded_score}-{color})"

    @staticmethod
    def generate_gate_badge(passed: bool) -> str:
        """Generate a shields.io quality gate badge in Markdown.

        Args:
            passed: Whether the quality gate passed.

        Returns:
            Markdown image string for the gate badge.
        """
        if passed:
            label = "passing"
            color = "green"
        else:
            label = "failing"
            color = "red"

        return f"![Quality Gate](https://img.shields.io/badge/quality_gate-{label}-{color})"

    # -- internal helpers ---------------------------------------------------

    def _read_export(self) -> dict[str, Any] | None:
        """Read and parse the TappsMCP export JSON file.

        Returns ``None`` when the file does not exist or cannot be parsed.
        """
        export_path = self._tapps_dir / _EXPORT_FILENAME
        if not export_path.is_file():
            log.debug(
                "tapps_export_not_found",
                path=str(export_path),
            )
            return None

        text = export_path.read_text(encoding="utf-8")
        result: dict[str, Any] = json.loads(text)
        return result
