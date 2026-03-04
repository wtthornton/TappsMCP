"""Tests for the tree-sitter Rust extractor."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


ts = pytest.importorskip("tree_sitter", reason="tree-sitter not installed")
ts_rust = pytest.importorskip("tree_sitter_rust", reason="tree-sitter-rust not installed")

from docs_mcp.extractors.treesitter_rust import RustExtractor  # noqa: E402


@pytest.fixture
def extractor() -> RustExtractor:
    return RustExtractor()


class TestCanHandle:
    def test_rs_file(self, extractor: RustExtractor) -> None:
        assert extractor.can_handle(Path("foo.rs")) is True

    def test_py_file(self, extractor: RustExtractor) -> None:
        assert extractor.can_handle(Path("foo.py")) is False


class TestExtractRust:
    def test_extract_sample(self, extractor: RustExtractor) -> None:
        sample = FIXTURES / "sample.rs"
        result = extractor.extract(sample)
        assert result.path == str(sample)

    def test_imports(self, extractor: RustExtractor) -> None:
        sample = FIXTURES / "sample.rs"
        result = extractor.extract(sample)
        assert len(result.imports) >= 1

    def test_module_docstring(self, extractor: RustExtractor) -> None:
        sample = FIXTURES / "sample.rs"
        result = extractor.extract(sample)
        assert result.docstring is not None
        assert "sample" in result.docstring.lower()

    def test_functions(self, extractor: RustExtractor) -> None:
        sample = FIXTURES / "sample.rs"
        result = extractor.extract(sample)
        func_names = [f.name for f in result.functions]
        assert "read_all" in func_names

    def test_async_function(self, extractor: RustExtractor) -> None:
        sample = FIXTURES / "sample.rs"
        result = extractor.extract(sample)
        fetch = next(f for f in result.functions if f.name == "fetch_data")
        assert fetch.is_async is True

    def test_function_parameters(self, extractor: RustExtractor) -> None:
        sample = FIXTURES / "sample.rs"
        result = extractor.extract(sample)
        read_all = next(f for f in result.functions if f.name == "read_all")
        assert len(read_all.parameters) >= 1

    def test_function_return_type(self, extractor: RustExtractor) -> None:
        sample = FIXTURES / "sample.rs"
        result = extractor.extract(sample)
        read_all = next(f for f in result.functions if f.name == "read_all")
        assert read_all.return_annotation is not None
        assert "Vec" in read_all.return_annotation

    def test_structs(self, extractor: RustExtractor) -> None:
        sample = FIXTURES / "sample.rs"
        result = extractor.extract(sample)
        class_names = [c.name for c in result.classes]
        assert "User" in class_names

    def test_struct_fields(self, extractor: RustExtractor) -> None:
        sample = FIXTURES / "sample.rs"
        result = extractor.extract(sample)
        user = next(c for c in result.classes if c.name == "User")
        field_names = [f.name for f in user.class_variables]
        assert "name" in field_names
        assert "email" in field_names

    def test_enums(self, extractor: RustExtractor) -> None:
        sample = FIXTURES / "sample.rs"
        result = extractor.extract(sample)
        class_names = [c.name for c in result.classes]
        assert "Role" in class_names

    def test_enum_variants(self, extractor: RustExtractor) -> None:
        sample = FIXTURES / "sample.rs"
        result = extractor.extract(sample)
        role = next(c for c in result.classes if c.name == "Role")
        variant_names = [v.name for v in role.class_variables]
        assert "Admin" in variant_names
        assert "Editor" in variant_names

    def test_traits(self, extractor: RustExtractor) -> None:
        sample = FIXTURES / "sample.rs"
        result = extractor.extract(sample)
        class_names = [c.name for c in result.classes]
        assert "Greeter" in class_names

    def test_trait_methods(self, extractor: RustExtractor) -> None:
        sample = FIXTURES / "sample.rs"
        result = extractor.extract(sample)
        greeter = next(c for c in result.classes if c.name == "Greeter")
        method_names = [m.name for m in greeter.methods]
        assert "greet" in method_names

    def test_impl_methods(self, extractor: RustExtractor) -> None:
        sample = FIXTURES / "sample.rs"
        result = extractor.extract(sample)
        func_names = [f.name for f in result.functions]
        assert "new" in func_names
        assert "display_name" in func_names

    def test_constants(self, extractor: RustExtractor) -> None:
        sample = FIXTURES / "sample.rs"
        result = extractor.extract(sample)
        const_names = [c.name for c in result.constants]
        assert "MAX_RETRIES" in const_names

    def test_doc_comments(self, extractor: RustExtractor) -> None:
        sample = FIXTURES / "sample.rs"
        result = extractor.extract(sample)
        user = next(c for c in result.classes if c.name == "User")
        assert user.docstring is not None
        assert "user" in user.docstring.lower()

    def test_nonexistent_file(self, extractor: RustExtractor) -> None:
        p = Path("/nonexistent/file.rs")
        result = extractor.extract(p)
        assert result.path == str(p)
        assert result.functions == []
