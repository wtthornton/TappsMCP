"""Language detection and scorer routing for multi-language support.

This module provides automatic language detection based on file extensions
and routes files to the appropriate language-specific scorer.

Epic 56: Non-Python Language Scoring
Story 56.2: Language Detection & Routing
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from tapps_mcp.scoring.scorer_base import ScorerBase

logger = structlog.get_logger(__name__)

# Extension to language mapping.
# Keys are lowercase extensions with leading dot.
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    # Python
    ".py": "python",
    ".pyi": "python",
    # TypeScript / JavaScript
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    # Go
    ".go": "go",
    # Rust
    ".rs": "rust",
}

# Languages that share a scorer (JavaScript uses TypeScript scorer)
LANGUAGE_ALIASES: dict[str, str] = {
    "javascript": "typescript",
}

# Supported languages for scoring (languages with implemented scorers)
SUPPORTED_LANGUAGES: frozenset[str] = frozenset(
    {
        "python",
        "typescript",
        "go",
        "rust",
    }
)


def detect_language(file_path: Path | str) -> str | None:
    """Detect the programming language of a file based on its extension.

    Args:
        file_path: Path to the file to detect.

    Returns:
        The language identifier (e.g., "python", "typescript", "go", "rust"),
        or None if the language is not recognized.

    Examples:
        >>> detect_language(Path("main.py"))
        'python'
        >>> detect_language(Path("app.tsx"))
        'typescript'
        >>> detect_language(Path("server.go"))
        'go'
        >>> detect_language(Path("lib.rs"))
        'rust'
        >>> detect_language(Path("data.json"))
        None
    """
    path = Path(file_path) if isinstance(file_path, str) else file_path
    ext = path.suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(ext)


def get_canonical_language(language: str) -> str:
    """Get the canonical language name, resolving aliases.

    Args:
        language: The language identifier.

    Returns:
        The canonical language name (e.g., "javascript" -> "typescript").
    """
    return LANGUAGE_ALIASES.get(language, language)


def is_language_supported(language: str) -> bool:
    """Check if a language has a scorer implementation.

    Args:
        language: The language identifier.

    Returns:
        True if the language is supported for scoring.
    """
    canonical = get_canonical_language(language)
    return canonical in SUPPORTED_LANGUAGES


def get_scorer(file_path: Path | str) -> ScorerBase | None:
    """Get the appropriate scorer for a file based on its extension.

    This function detects the language of the file and returns an instance
    of the corresponding scorer. Returns None if the language is not
    supported for scoring.

    Args:
        file_path: Path to the file to score.

    Returns:
        A ScorerBase instance for the file's language, or None if unsupported.

    Examples:
        >>> scorer = get_scorer(Path("main.py"))
        >>> scorer.language
        'python'
        >>> get_scorer(Path("data.json"))
        None
    """
    language = detect_language(file_path)
    if language is None:
        return None
    return get_scorer_for_language(language)


def get_scorer_for_language(language: str) -> ScorerBase | None:
    """Get a scorer instance for a specific language.

    Args:
        language: The language identifier (e.g., "python", "typescript").

    Returns:
        A ScorerBase instance for the language, or None if unsupported.
    """
    canonical = get_canonical_language(language)

    if canonical == "python":
        from tapps_mcp.scoring.scorer import CodeScorer

        return CodeScorer()

    if canonical == "typescript":
        from tapps_mcp.scoring.scorer_typescript import TypeScriptScorer

        return TypeScriptScorer()

    if canonical == "go":
        from tapps_mcp.scoring.scorer_go import GoScorer

        return GoScorer()

    if canonical == "rust":
        from tapps_mcp.scoring.scorer_rust import RustScorer

        return RustScorer()

    logger.debug("unsupported_language", language=language)
    return None


def get_supported_extensions() -> frozenset[str]:
    """Get the set of all file extensions that can be scored.

    Returns:
        A frozenset of file extensions (with leading dot).
    """
    return frozenset(EXTENSION_TO_LANGUAGE.keys())


def get_languages_for_extensions(extensions: list[str]) -> set[str]:
    """Get the unique languages for a list of file extensions.

    Args:
        extensions: List of file extensions (with or without leading dot).

    Returns:
        Set of language identifiers.
    """
    languages: set[str] = set()
    for ext in extensions:
        normalized = ext if ext.startswith(".") else f".{ext}"
        lang = EXTENSION_TO_LANGUAGE.get(normalized.lower())
        if lang:
            languages.add(get_canonical_language(lang))
    return languages
