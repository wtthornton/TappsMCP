"""Extractor dispatcher -- selects the best extractor for a given file."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from docs_mcp.extractors.base import Extractor

logger: structlog.stdlib.BoundLogger = structlog.get_logger()  # type: ignore[assignment]


def get_extractor(file_path: Path) -> Extractor:
    """Return the best available extractor for *file_path*.

    Priority:
    1. ``PythonExtractor`` for .py/.pyi (AST-based, always available)
    2. Tree-sitter language-specific extractors (if tree-sitter installed)
    3. ``GenericExtractor`` as universal regex fallback
    """
    from docs_mcp.extractors.generic import GenericExtractor
    from docs_mcp.extractors.python import PythonExtractor

    suffix = file_path.suffix.lower()

    # Python files: prefer the AST extractor.
    if suffix in {".py", ".pyi"}:
        return PythonExtractor()

    # Try tree-sitter extractors for other languages.
    ts_extractor = _get_treesitter_extractor(suffix)
    if ts_extractor is not None:
        return ts_extractor

    # Fallback to regex.
    return GenericExtractor()


def _get_treesitter_extractor(suffix: str) -> Extractor | None:
    """Return a tree-sitter extractor for *suffix*, or None if unavailable."""
    if suffix in {".ts", ".tsx"}:
        try:
            from docs_mcp.extractors.treesitter_typescript import TypeScriptExtractor

            ext = TypeScriptExtractor()
            if ext.can_handle(Path(f"file{suffix}")):
                return ext  # type: ignore[return-value]
        except Exception:  # noqa: BLE001
            pass

    elif suffix == ".go":
        try:
            from docs_mcp.extractors.treesitter_go import GoExtractor

            ext = GoExtractor()
            if ext.can_handle(Path(f"file{suffix}")):
                return ext  # type: ignore[return-value]
        except Exception:  # noqa: BLE001
            pass

    elif suffix == ".rs":
        try:
            from docs_mcp.extractors.treesitter_rust import RustExtractor

            ext = RustExtractor()
            if ext.can_handle(Path(f"file{suffix}")):
                return ext  # type: ignore[return-value]
        except Exception:  # noqa: BLE001
            pass

    elif suffix == ".java":
        try:
            from docs_mcp.extractors.treesitter_java import JavaExtractor

            ext = JavaExtractor()
            if ext.can_handle(Path(f"file{suffix}")):
                return ext  # type: ignore[return-value]
        except Exception:  # noqa: BLE001
            pass

    return None
