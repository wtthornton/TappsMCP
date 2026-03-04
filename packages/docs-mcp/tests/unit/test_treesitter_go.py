"""Tests for the tree-sitter Go extractor."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


ts = pytest.importorskip("tree_sitter", reason="tree-sitter not installed")
ts_go = pytest.importorskip("tree_sitter_go", reason="tree-sitter-go not installed")

from docs_mcp.extractors.treesitter_go import GoExtractor  # noqa: E402


@pytest.fixture
def extractor() -> GoExtractor:
    return GoExtractor()


class TestCanHandle:
    def test_go_file(self, extractor: GoExtractor) -> None:
        assert extractor.can_handle(Path("foo.go")) is True

    def test_py_file(self, extractor: GoExtractor) -> None:
        assert extractor.can_handle(Path("foo.py")) is False


class TestExtractGo:
    def test_extract_sample(self, extractor: GoExtractor) -> None:
        sample = FIXTURES / "sample.go"
        result = extractor.extract(sample)
        assert result.path == str(sample)

    def test_imports(self, extractor: GoExtractor) -> None:
        sample = FIXTURES / "sample.go"
        result = extractor.extract(sample)
        assert len(result.imports) >= 1

    def test_package_docstring(self, extractor: GoExtractor) -> None:
        sample = FIXTURES / "sample.go"
        result = extractor.extract(sample)
        assert result.docstring is not None
        assert "sample" in result.docstring.lower()

    def test_functions(self, extractor: GoExtractor) -> None:
        sample = FIXTURES / "sample.go"
        result = extractor.extract(sample)
        func_names = [f.name for f in result.functions]
        assert "NewUser" in func_names
        assert "ReadAll" in func_names

    def test_methods(self, extractor: GoExtractor) -> None:
        sample = FIXTURES / "sample.go"
        result = extractor.extract(sample)
        func_names = [f.name for f in result.functions]
        assert "String" in func_names

    def test_function_parameters(self, extractor: GoExtractor) -> None:
        sample = FIXTURES / "sample.go"
        result = extractor.extract(sample)
        new_user = next(f for f in result.functions if f.name == "NewUser")
        assert len(new_user.parameters) >= 2
        param_names = [p.name for p in new_user.parameters]
        assert "name" in param_names

    def test_function_return_type(self, extractor: GoExtractor) -> None:
        sample = FIXTURES / "sample.go"
        result = extractor.extract(sample)
        new_user = next(f for f in result.functions if f.name == "NewUser")
        assert new_user.return_annotation is not None
        assert "User" in new_user.return_annotation

    def test_structs(self, extractor: GoExtractor) -> None:
        sample = FIXTURES / "sample.go"
        result = extractor.extract(sample)
        class_names = [c.name for c in result.classes]
        assert "User" in class_names

    def test_struct_fields(self, extractor: GoExtractor) -> None:
        sample = FIXTURES / "sample.go"
        result = extractor.extract(sample)
        user = next(c for c in result.classes if c.name == "User")
        field_names = [f.name for f in user.class_variables]
        assert "Name" in field_names
        assert "Email" in field_names

    def test_interfaces(self, extractor: GoExtractor) -> None:
        sample = FIXTURES / "sample.go"
        result = extractor.extract(sample)
        class_names = [c.name for c in result.classes]
        assert "Greeter" in class_names

    def test_interface_methods(self, extractor: GoExtractor) -> None:
        sample = FIXTURES / "sample.go"
        result = extractor.extract(sample)
        greeter = next(c for c in result.classes if c.name == "Greeter")
        method_names = [m.name for m in greeter.methods]
        assert "Greet" in method_names

    def test_constants(self, extractor: GoExtractor) -> None:
        sample = FIXTURES / "sample.go"
        result = extractor.extract(sample)
        const_names = [c.name for c in result.constants]
        assert "MaxSize" in const_names

    def test_variables(self, extractor: GoExtractor) -> None:
        sample = FIXTURES / "sample.go"
        result = extractor.extract(sample)
        const_names = [c.name for c in result.constants]
        assert "DefaultName" in const_names

    def test_doc_comments(self, extractor: GoExtractor) -> None:
        sample = FIXTURES / "sample.go"
        result = extractor.extract(sample)
        new_user = next(f for f in result.functions if f.name == "NewUser")
        assert new_user.docstring is not None
        assert "new User" in new_user.docstring

    def test_nonexistent_file(self, extractor: GoExtractor) -> None:
        p = Path("/nonexistent/file.go")
        result = extractor.extract(p)
        assert result.path == str(p)
        assert result.functions == []
