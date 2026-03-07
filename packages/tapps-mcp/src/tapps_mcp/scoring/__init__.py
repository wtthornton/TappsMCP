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
from tapps_mcp.scoring.scorer_base import STANDARD_CATEGORIES, ScorerBase

__all__ = [
    # Models
    "CategoryScore",
    "ScoreResult",
    # Base class
    "ScorerBase",
    "STANDARD_CATEGORIES",
    # Language scorers (lazy-loaded to avoid circular imports with tools/)
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

# Lazy-load scorer classes to break circular import:
# scoring/__init__ -> scorer.py -> tools/bandit.py -> scoring.models -> scoring/__init__
_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "CodeScorer": ("tapps_mcp.scoring.scorer", "CodeScorer"),
    "TypeScriptScorer": ("tapps_mcp.scoring.scorer_typescript", "TypeScriptScorer"),
    "GoScorer": ("tapps_mcp.scoring.scorer_go", "GoScorer"),
    "RustScorer": ("tapps_mcp.scoring.scorer_rust", "RustScorer"),
}


def __getattr__(name: str) -> object:
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        import importlib

        mod = importlib.import_module(module_path)
        val = getattr(mod, attr)
        globals()[name] = val  # cache for subsequent access
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
