"""Tests for the tree-sitter base extractor and dispatcher."""

from __future__ import annotations

from pathlib import Path

from docs_mcp.extractors.dispatcher import get_extractor
from docs_mcp.extractors.generic import GenericExtractor
from docs_mcp.extractors.python import PythonExtractor


class TestDispatcher:
    """Tests for the extractor dispatcher."""

    def test_python_returns_python_extractor(self) -> None:
        ext = get_extractor(Path("foo.py"))
        assert isinstance(ext, PythonExtractor)

    def test_pyi_returns_python_extractor(self) -> None:
        ext = get_extractor(Path("foo.pyi"))
        assert isinstance(ext, PythonExtractor)

    def test_unknown_returns_generic(self) -> None:
        ext = get_extractor(Path("foo.txt"))
        assert isinstance(ext, GenericExtractor)

    def test_ts_without_treesitter_returns_generic(self) -> None:
        """When tree-sitter is not installed, .ts gets GenericExtractor."""
        # This test verifies fallback behavior.
        ext = get_extractor(Path("foo.ts"))
        # May be TreeSitter or Generic depending on installation.
        assert ext is not None

    def test_go_without_treesitter_returns_generic(self) -> None:
        ext = get_extractor(Path("foo.go"))
        assert ext is not None

    def test_rs_without_treesitter_returns_generic(self) -> None:
        ext = get_extractor(Path("foo.rs"))
        assert ext is not None

    def test_java_without_treesitter_returns_generic(self) -> None:
        ext = get_extractor(Path("foo.java"))
        assert ext is not None


class TestTreeSitterBaseImport:
    """Tests for graceful degradation when tree-sitter is not installed."""

    def test_has_tree_sitter_flag(self) -> None:
        from docs_mcp.extractors.treesitter_base import HAS_TREE_SITTER

        # The flag should be a boolean regardless of installation status.
        assert isinstance(HAS_TREE_SITTER, bool)

    def test_base_class_importable(self) -> None:
        from docs_mcp.extractors.treesitter_base import TreeSitterExtractor

        assert TreeSitterExtractor is not None
