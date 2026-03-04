"""Tests for the tree-sitter Java extractor."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


ts = pytest.importorskip("tree_sitter", reason="tree-sitter not installed")
ts_java = pytest.importorskip("tree_sitter_java", reason="tree-sitter-java not installed")

from docs_mcp.extractors.treesitter_java import JavaExtractor  # noqa: E402


@pytest.fixture
def extractor() -> JavaExtractor:
    return JavaExtractor()


class TestCanHandle:
    def test_java_file(self, extractor: JavaExtractor) -> None:
        assert extractor.can_handle(Path("foo.java")) is True

    def test_py_file(self, extractor: JavaExtractor) -> None:
        assert extractor.can_handle(Path("foo.py")) is False


class TestExtractJava:
    def test_extract_sample(self, extractor: JavaExtractor) -> None:
        sample = FIXTURES / "sample.java"
        result = extractor.extract(sample)
        assert result.path == str(sample)

    def test_imports(self, extractor: JavaExtractor) -> None:
        sample = FIXTURES / "sample.java"
        result = extractor.extract(sample)
        assert len(result.imports) >= 2  # package + imports

    def test_classes(self, extractor: JavaExtractor) -> None:
        sample = FIXTURES / "sample.java"
        result = extractor.extract(sample)
        class_names = [c.name for c in result.classes]
        assert "UserService" in class_names
        assert "User" in class_names

    def test_class_methods(self, extractor: JavaExtractor) -> None:
        sample = FIXTURES / "sample.java"
        result = extractor.extract(sample)
        service = next(c for c in result.classes if c.name == "UserService")
        method_names = [m.name for m in service.methods]
        assert "findById" in method_names
        assert "getAll" in method_names

    def test_constructor(self, extractor: JavaExtractor) -> None:
        sample = FIXTURES / "sample.java"
        result = extractor.extract(sample)
        service = next(c for c in result.classes if c.name == "UserService")
        method_names = [m.name for m in service.methods]
        assert "UserService" in method_names

    def test_method_parameters(self, extractor: JavaExtractor) -> None:
        sample = FIXTURES / "sample.java"
        result = extractor.extract(sample)
        service = next(c for c in result.classes if c.name == "UserService")
        find = next(m for m in service.methods if m.name == "findById")
        assert len(find.parameters) >= 1
        assert find.parameters[0].name == "id"

    def test_method_return_type(self, extractor: JavaExtractor) -> None:
        sample = FIXTURES / "sample.java"
        result = extractor.extract(sample)
        service = next(c for c in result.classes if c.name == "UserService")
        find = next(m for m in service.methods if m.name == "findById")
        assert find.return_annotation is not None

    def test_class_fields(self, extractor: JavaExtractor) -> None:
        sample = FIXTURES / "sample.java"
        result = extractor.extract(sample)
        service = next(c for c in result.classes if c.name == "UserService")
        field_names = [f.name for f in service.class_variables]
        assert "serviceName" in field_names

    def test_interfaces(self, extractor: JavaExtractor) -> None:
        sample = FIXTURES / "sample.java"
        result = extractor.extract(sample)
        class_names = [c.name for c in result.classes]
        assert "Repository" in class_names

    def test_interface_methods(self, extractor: JavaExtractor) -> None:
        sample = FIXTURES / "sample.java"
        result = extractor.extract(sample)
        repo = next(c for c in result.classes if c.name == "Repository")
        method_names = [m.name for m in repo.methods]
        assert "findById" in method_names
        assert "findAll" in method_names
        assert "save" in method_names

    def test_enums(self, extractor: JavaExtractor) -> None:
        sample = FIXTURES / "sample.java"
        result = extractor.extract(sample)
        class_names = [c.name for c in result.classes]
        assert "UserRole" in class_names

    def test_enum_constants(self, extractor: JavaExtractor) -> None:
        sample = FIXTURES / "sample.java"
        result = extractor.extract(sample)
        role = next(c for c in result.classes if c.name == "UserRole")
        variant_names = [v.name for v in role.class_variables]
        assert "ADMIN" in variant_names
        assert "EDITOR" in variant_names

    def test_javadoc(self, extractor: JavaExtractor) -> None:
        sample = FIXTURES / "sample.java"
        result = extractor.extract(sample)
        service = next(c for c in result.classes if c.name == "UserService")
        assert service.docstring is not None
        assert "sample" in service.docstring.lower()

    def test_nonexistent_file(self, extractor: JavaExtractor) -> None:
        p = Path("/nonexistent/file.java")
        result = extractor.extract(p)
        assert result.path == str(p)
        assert result.functions == []
