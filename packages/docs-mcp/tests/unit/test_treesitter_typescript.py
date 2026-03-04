"""Tests for the tree-sitter TypeScript extractor."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


ts = pytest.importorskip("tree_sitter", reason="tree-sitter not installed")
ts_typescript = pytest.importorskip(
    "tree_sitter_typescript", reason="tree-sitter-typescript not installed",
)

from docs_mcp.extractors.treesitter_typescript import TypeScriptExtractor  # noqa: E402


@pytest.fixture
def extractor() -> TypeScriptExtractor:
    return TypeScriptExtractor()


class TestCanHandle:
    def test_ts_file(self, extractor: TypeScriptExtractor) -> None:
        assert extractor.can_handle(Path("foo.ts")) is True

    def test_tsx_file(self, extractor: TypeScriptExtractor) -> None:
        assert extractor.can_handle(Path("foo.tsx")) is True

    def test_js_file(self, extractor: TypeScriptExtractor) -> None:
        assert extractor.can_handle(Path("foo.js")) is False

    def test_py_file(self, extractor: TypeScriptExtractor) -> None:
        assert extractor.can_handle(Path("foo.py")) is False


class TestExtractTS:
    def test_extract_sample_ts(self, extractor: TypeScriptExtractor) -> None:
        sample = FIXTURES / "sample.ts"
        result = extractor.extract(sample)
        assert result.path == str(sample)

    def test_imports(self, extractor: TypeScriptExtractor) -> None:
        sample = FIXTURES / "sample.ts"
        result = extractor.extract(sample)
        assert len(result.imports) >= 1

    def test_functions(self, extractor: TypeScriptExtractor) -> None:
        sample = FIXTURES / "sample.ts"
        result = extractor.extract(sample)
        func_names = [f.name for f in result.functions]
        assert "greet" in func_names
        assert "fetchData" in func_names

    def test_arrow_functions(self, extractor: TypeScriptExtractor) -> None:
        sample = FIXTURES / "sample.ts"
        result = extractor.extract(sample)
        func_names = [f.name for f in result.functions]
        assert "add" in func_names
        assert "processItems" in func_names

    def test_async_function(self, extractor: TypeScriptExtractor) -> None:
        sample = FIXTURES / "sample.ts"
        result = extractor.extract(sample)
        fetch = next(f for f in result.functions if f.name == "fetchData")
        assert fetch.is_async is True

    def test_async_arrow(self, extractor: TypeScriptExtractor) -> None:
        sample = FIXTURES / "sample.ts"
        result = extractor.extract(sample)
        proc = next(f for f in result.functions if f.name == "processItems")
        assert proc.is_async is True

    def test_function_parameters(self, extractor: TypeScriptExtractor) -> None:
        sample = FIXTURES / "sample.ts"
        result = extractor.extract(sample)
        greet = next(f for f in result.functions if f.name == "greet")
        assert len(greet.parameters) == 1
        assert greet.parameters[0].name == "name"
        assert greet.parameters[0].annotation == "string"

    def test_function_return_type(self, extractor: TypeScriptExtractor) -> None:
        sample = FIXTURES / "sample.ts"
        result = extractor.extract(sample)
        greet = next(f for f in result.functions if f.name == "greet")
        assert greet.return_annotation == "string"

    def test_classes(self, extractor: TypeScriptExtractor) -> None:
        sample = FIXTURES / "sample.ts"
        result = extractor.extract(sample)
        class_names = [c.name for c in result.classes]
        assert "User" in class_names

    def test_class_bases(self, extractor: TypeScriptExtractor) -> None:
        sample = FIXTURES / "sample.ts"
        result = extractor.extract(sample)
        user = next(c for c in result.classes if c.name == "User")
        assert "EventEmitter" in user.bases

    def test_class_methods(self, extractor: TypeScriptExtractor) -> None:
        sample = FIXTURES / "sample.ts"
        result = extractor.extract(sample)
        user = next(c for c in result.classes if c.name == "User")
        method_names = [m.name for m in user.methods]
        assert "getDisplayName" in method_names

    def test_interfaces(self, extractor: TypeScriptExtractor) -> None:
        sample = FIXTURES / "sample.ts"
        result = extractor.extract(sample)
        class_names = [c.name for c in result.classes]
        assert "AppConfig" in class_names

    def test_type_aliases(self, extractor: TypeScriptExtractor) -> None:
        sample = FIXTURES / "sample.ts"
        result = extractor.extract(sample)
        class_names = [c.name for c in result.classes]
        assert "LogLevel" in class_names

    def test_constants(self, extractor: TypeScriptExtractor) -> None:
        sample = FIXTURES / "sample.ts"
        result = extractor.extract(sample)
        const_names = [c.name for c in result.constants]
        assert "MAX_RETRIES" in const_names
        assert "API_URL" in const_names

    def test_jsdoc_on_function(self, extractor: TypeScriptExtractor) -> None:
        sample = FIXTURES / "sample.ts"
        result = extractor.extract(sample)
        greet = next(f for f in result.functions if f.name == "greet")
        assert greet.docstring is not None
        assert "Greet" in greet.docstring

    def test_nonexistent_file(self, extractor: TypeScriptExtractor) -> None:
        p = Path("/nonexistent/file.ts")
        result = extractor.extract(p)
        assert result.path == str(p)
        assert result.functions == []


class TestExtractTSX:
    def test_extract_tsx(self, extractor: TypeScriptExtractor) -> None:
        sample = FIXTURES / "sample.tsx"
        result = extractor.extract(sample)
        func_names = [f.name for f in result.functions]
        assert "Button" in func_names

    def test_tsx_interface(self, extractor: TypeScriptExtractor) -> None:
        sample = FIXTURES / "sample.tsx"
        result = extractor.extract(sample)
        class_names = [c.name for c in result.classes]
        assert "ButtonProps" in class_names
