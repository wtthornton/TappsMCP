"""Documentation validation engine for DocsMCP.

Provides drift detection, completeness checking, link validation,
freshness scoring, epic structure validation, and style/tone checking
for project documentation.
"""

from __future__ import annotations

from docs_mcp.validators.completeness import CompletenessChecker, CompletenessReport
from docs_mcp.validators.drift import DriftDetector, DriftReport
from docs_mcp.validators.epic_validator import EpicValidationReport, EpicValidator
from docs_mcp.validators.freshness import FreshnessChecker, FreshnessReport
from docs_mcp.validators.link_checker import LinkChecker, LinkReport
from docs_mcp.validators.style import StyleChecker, StyleConfig, StyleReport

__all__ = [
    "CompletenessChecker",
    "CompletenessReport",
    "DriftDetector",
    "DriftReport",
    "EpicValidationReport",
    "EpicValidator",
    "FreshnessChecker",
    "FreshnessReport",
    "LinkChecker",
    "LinkReport",
    "StyleChecker",
    "StyleConfig",
    "StyleReport",
]
