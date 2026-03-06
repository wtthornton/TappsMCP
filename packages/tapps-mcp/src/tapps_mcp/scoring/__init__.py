"""Scoring engine: file scoring, metrics, pattern detection.

This package provides the code quality scoring infrastructure for TappsMCP.
The main entry point is ``CodeScorer`` for Python files, which inherits from
the abstract ``ScorerBase`` class.

Epic 56 introduces multi-language support via additional scorer implementations
(TypeScriptScorer, GoScorer, RustScorer) that also inherit from ScorerBase.
Use ``get_scorer()`` from ``language_detector`` to automatically route files
to the appropriate scorer based on file extension.
"""

from tapps_mcp.scoring.language_detector import (
    EXTENSION_TO_LANGUAGE,
    SUPPORTED_LANGUAGES,
    detect_language,
    get_scorer,
    get_scorer_for_language,
    get_supported_extensions,
    is_language_supported,
)
from tapps_mcp.scoring.models import CategoryScore, ScoreResult
from tapps_mcp.scoring.scorer import CodeScorer
from tapps_mcp.scoring.scorer_base import STANDARD_CATEGORIES, ScorerBase
from tapps_mcp.scoring.scorer_go import GoScorer
from tapps_mcp.scoring.scorer_rust import RustScorer
from tapps_mcp.scoring.scorer_typescript import TypeScriptScorer

__all__ = [
    # Models
    "CategoryScore",
    "ScoreResult",
    # Base class
    "ScorerBase",
    "STANDARD_CATEGORIES",
    # Language scorers
    "CodeScorer",
    "TypeScriptScorer",
    "GoScorer",
    "RustScorer",
    # Language detection
    "detect_language",
    "get_scorer",
    "get_scorer_for_language",
    "is_language_supported",
    "get_supported_extensions",
    "EXTENSION_TO_LANGUAGE",
    "SUPPORTED_LANGUAGES",
]
