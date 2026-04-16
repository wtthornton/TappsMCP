"""Tests for the regex-based generic/fallback extractor."""

from __future__ import annotations

from pathlib import Path

import pytest

from docs_mcp.extractors.generic import GenericExtractor


@pytest.fixture()
def extractor() -> GenericExtractor:
    return GenericExtractor()


# =========================================================================
# Python fallback tests
# =========================================================================


class TestPythonExtraction:
    """Python regex extraction (fallback when AST fails)."""

    def test_extracts_function_names(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "mod.py"
        src.write_text(
            "def hello(name: str) -> str:\n"
            '    """Greet someone."""\n'
            "    return f'hi {name}'\n"
            "\n"
            "def goodbye():\n"
            "    pass\n",
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        names = [f.name for f in info.functions]
        assert "hello" in names
        assert "goodbye" in names

    def test_extracts_async_function(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "async_mod.py"
        src.write_text(
            "async def fetch(url: str) -> bytes:\n    pass\n",
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        assert len(info.functions) == 1
        assert info.functions[0].name == "fetch"
        assert info.functions[0].is_async is True

    def test_extracts_class_names(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "cls.py"
        src.write_text(
            'class Animal(Base, Mixin):\n    """An animal."""\n    pass\n\nclass Dog:\n    pass\n',
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        names = [c.name for c in info.classes]
        assert "Animal" in names
        assert "Dog" in names
        animal = next(c for c in info.classes if c.name == "Animal")
        assert "Base" in animal.bases
        assert "Mixin" in animal.bases

    def test_extracts_class_docstring(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "doc.py"
        src.write_text(
            'class Foo:\n    """This is Foo."""\n    pass\n',
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        assert info.classes[0].docstring == "This is Foo."

    def test_handles_syntax_error_python(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "broken.py"
        src.write_text(
            "def still_found():\n"
            "    pass\n"
            "\n"
            "def oops((\n"  # syntax error
            "    broken\n"
            "\n"
            "class AlsoFound:\n"
            "    pass\n",
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        # Should still extract what it can.
        func_names = [f.name for f in info.functions]
        assert "still_found" in func_names
        class_names = [c.name for c in info.classes]
        assert "AlsoFound" in class_names

    def test_extracts_all_exports(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "exports.py"
        src.write_text(
            '__all__ = ["foo", "bar", "baz"]\n'
            "\n"
            "def foo(): pass\n"
            "def bar(): pass\n"
            "def baz(): pass\n",
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        assert info.all_exports == ["foo", "bar", "baz"]

    def test_detects_main_block(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "main.py"
        src.write_text(
            'def run():\n    pass\n\nif __name__ == "__main__":\n    run()\n',
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        assert info.has_main_block is True

    def test_no_main_block(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "lib.py"
        src.write_text("def helper(): pass\n", encoding="utf-8")
        info = extractor.extract(src, project_root=tmp_path)
        assert info.has_main_block is False

    def test_extracts_imports(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "imports.py"
        src.write_text(
            "import os\nfrom pathlib import Path\nimport sys, json\n\ndef work(): pass\n",
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        assert len(info.imports) >= 3
        assert any("os" in i for i in info.imports)
        assert any("pathlib" in i for i in info.imports)

    def test_extracts_constants(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "consts.py"
        src.write_text(
            'MAX_SIZE = 100\nDEFAULT_NAME = "hello"\nnot_a_constant = 42\n',
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        const_names = [c.name for c in info.constants]
        assert "MAX_SIZE" in const_names
        assert "DEFAULT_NAME" in const_names
        assert "not_a_constant" not in const_names

    def test_extracts_module_docstring(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "documented.py"
        src.write_text(
            '"""This is the module docstring."""\n\ndef foo(): pass\n',
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        assert info.docstring == "This is the module docstring."

    def test_extracts_function_parameters(
        self, extractor: GenericExtractor, tmp_path: Path
    ) -> None:
        src = tmp_path / "params.py"
        src.write_text(
            "def greet(name: str, count: int = 3) -> None:\n    pass\n",
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        assert len(info.functions) == 1
        params = info.functions[0].parameters
        assert len(params) == 2
        assert params[0].name == "name"
        assert params[0].annotation == "str"
        assert params[1].name == "count"
        assert params[1].default == "3"

    def test_extracts_return_annotation(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "ret.py"
        src.write_text("def get_value() -> int:\n    return 42\n", encoding="utf-8")
        info = extractor.extract(src, project_root=tmp_path)
        assert info.functions[0].return_annotation == "int"


# =========================================================================
# JavaScript / TypeScript tests
# =========================================================================


class TestJavaScriptExtraction:
    """JS/TS regex extraction."""

    def test_extracts_regular_functions(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "app.js"
        src.write_text(
            "function handleClick(event) {\n"
            "  console.log(event);\n"
            "}\n"
            "\n"
            "export async function fetchData(url) {\n"
            "  return await fetch(url);\n"
            "}\n",
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        names = [f.name for f in info.functions]
        assert "handleClick" in names
        assert "fetchData" in names
        fetch_fn = next(f for f in info.functions if f.name == "fetchData")
        assert fetch_fn.is_async is True

    def test_extracts_arrow_functions(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "utils.ts"
        src.write_text(
            "export const add = (a: number, b: number) => a + b;\n"
            "const multiply = async (x, y) => x * y;\n",
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        names = [f.name for f in info.functions]
        assert "add" in names
        assert "multiply" in names
        mul = next(f for f in info.functions if f.name == "multiply")
        assert mul.is_async is True

    def test_extracts_class_declarations(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "models.ts"
        src.write_text(
            "export class UserService extends BaseService {\n"
            "  constructor() { super(); }\n"
            "}\n"
            "\n"
            "class Logger {\n"
            "  log(msg) { console.log(msg); }\n"
            "}\n",
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        names = [c.name for c in info.classes]
        assert "UserService" in names
        assert "Logger" in names
        user_svc = next(c for c in info.classes if c.name == "UserService")
        assert "BaseService" in user_svc.bases

    def test_extracts_imports(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "index.js"
        src.write_text(
            "import React from 'react';\n"
            "import { useState, useEffect } from 'react';\n"
            "\n"
            "function App() { return null; }\n",
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        assert len(info.imports) == 2
        assert any("React" in i for i in info.imports)

    def test_extracts_jsdoc_as_docstring(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "jsdoc.js"
        src.write_text(
            "/**\n"
            " * Calculate the sum of two numbers.\n"
            " * @param {number} a\n"
            " * @param {number} b\n"
            " */\n"
            "function add(a, b) {\n"
            "  return a + b;\n"
            "}\n",
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        assert len(info.functions) == 1
        assert info.functions[0].docstring is not None
        assert "sum of two numbers" in info.functions[0].docstring

    def test_typescript_tsx_extension(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "component.tsx"
        src.write_text(
            "export function MyComponent() {\n  return <div/>;\n}\n",
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        assert len(info.functions) == 1
        assert info.functions[0].name == "MyComponent"


# =========================================================================
# Go tests
# =========================================================================


class TestGoExtraction:
    """Go regex extraction."""

    def test_extracts_func_declarations(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "main.go"
        src.write_text(
            "package main\n"
            "\n"
            'import "fmt"\n'
            "\n"
            "// Greet prints a greeting.\n"
            "func Greet(name string) {\n"
            '    fmt.Println("Hello", name)\n'
            "}\n"
            "\n"
            "func helper() {}\n",
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        names = [f.name for f in info.functions]
        assert "Greet" in names
        assert "helper" in names
        greet = next(f for f in info.functions if f.name == "Greet")
        assert greet.docstring is not None
        assert "greeting" in greet.docstring

    def test_extracts_type_declarations(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "types.go"
        src.write_text(
            "package models\n"
            "\n"
            "// User represents a user.\n"
            "type User struct {\n"
            "    Name string\n"
            "    Age  int\n"
            "}\n"
            "\n"
            "// Reader is a read interface.\n"
            "type Reader interface {\n"
            "    Read(p []byte) (n int, err error)\n"
            "}\n",
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        names = [c.name for c in info.classes]
        assert "User" in names
        assert "Reader" in names
        user = next(c for c in info.classes if c.name == "User")
        assert user.docstring is not None
        assert "user" in user.docstring.lower()

    def test_extracts_methods(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "methods.go"
        src.write_text(
            "package models\n"
            "\n"
            "// String returns the string representation.\n"
            "func (u *User) String() string {\n"
            "    return u.Name\n"
            "}\n",
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        assert len(info.functions) == 1
        assert info.functions[0].name == "String"

    def test_extracts_go_imports(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "imports.go"
        src.write_text(
            'package main\n\nimport "fmt"\nimport (\n    "os"\n    "strings"\n)\n',
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        assert len(info.imports) >= 1


# =========================================================================
# Rust tests
# =========================================================================


class TestRustExtraction:
    """Rust regex extraction."""

    def test_extracts_fn_declarations(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "lib.rs"
        src.write_text(
            "/// Add two numbers together.\n"
            "pub fn add(a: i32, b: i32) -> i32 {\n"
            "    a + b\n"
            "}\n"
            "\n"
            "fn helper() {}\n"
            "\n"
            "pub async fn fetch_data() {}\n",
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        names = [f.name for f in info.functions]
        assert "add" in names
        assert "helper" in names
        assert "fetch_data" in names
        add_fn = next(f for f in info.functions if f.name == "add")
        assert add_fn.docstring is not None
        assert "two numbers" in add_fn.docstring
        fetch_fn = next(f for f in info.functions if f.name == "fetch_data")
        assert fetch_fn.is_async is True

    def test_extracts_struct_declarations(
        self, extractor: GenericExtractor, tmp_path: Path
    ) -> None:
        src = tmp_path / "models.rs"
        src.write_text(
            "/// A configuration struct.\n"
            "pub struct Config {\n"
            "    pub name: String,\n"
            "    pub value: i32,\n"
            "}\n"
            "\n"
            "struct Internal {\n"
            "    data: Vec<u8>,\n"
            "}\n",
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        names = [c.name for c in info.classes]
        assert "Config" in names
        assert "Internal" in names
        config = next(c for c in info.classes if c.name == "Config")
        assert config.docstring is not None
        assert "configuration" in config.docstring.lower()

    def test_extracts_rust_doc_comments(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "docs.rs"
        src.write_text(
            "/// First line of documentation.\n"
            "/// Second line of documentation.\n"
            "pub fn documented() {}\n",
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        assert info.functions[0].docstring is not None
        assert "First line" in info.functions[0].docstring
        assert "Second line" in info.functions[0].docstring


# =========================================================================
# Edge case tests
# =========================================================================


class TestEdgeCases:
    """Edge cases and error handling."""

    def test_empty_file(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "empty.py"
        src.write_text("", encoding="utf-8")
        info = extractor.extract(src, project_root=tmp_path)
        assert info.path == "empty.py"
        assert info.functions == []
        assert info.classes == []

    def test_binary_file(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "binary.bin"
        src.write_bytes(bytes(range(256)) * 100)
        info = extractor.extract(src, project_root=tmp_path)
        # Should return empty, not crash.
        assert info.path == "binary.bin"
        assert info.functions == []

    def test_nonexistent_file(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "does_not_exist.py"
        info = extractor.extract(src, project_root=tmp_path)
        assert info.path == "does_not_exist.py"
        assert info.functions == []

    def test_unknown_extension(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "config.yaml"
        src.write_text("# YAML config file\nkey: value\n", encoding="utf-8")
        info = extractor.extract(src, project_root=tmp_path)
        assert info.path == "config.yaml"
        # Should extract leading comment as docstring.
        assert info.docstring is not None
        assert "YAML config" in info.docstring

    def test_large_file_skipped(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "huge.py"
        # Write just over 10MB of content.
        src.write_text("x = 1\n" * (2_000_000), encoding="utf-8")
        info = extractor.extract(src, project_root=tmp_path)
        # Should return empty rather than hang.
        assert info.path == "huge.py"
        assert info.functions == []

    def test_mixed_encoding_file(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "mixed.py"
        # Write valid UTF-8 with some Latin-1 bytes injected.
        content = b"def hello():\n    pass\n\xff\xfe\n"
        src.write_bytes(content)
        info = extractor.extract(src, project_root=tmp_path)
        # Should still extract the function.
        names = [f.name for f in info.functions]
        assert "hello" in names

    def test_can_handle_always_true(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        assert extractor.can_handle(tmp_path / "anything.xyz") is True
        assert extractor.can_handle(tmp_path / "code.py") is True
        assert extractor.can_handle(tmp_path / "data.csv") is True

    def test_relative_path_with_project_root(
        self, extractor: GenericExtractor, tmp_path: Path
    ) -> None:
        sub = tmp_path / "src" / "lib"
        sub.mkdir(parents=True)
        src = sub / "mod.py"
        src.write_text("def func(): pass\n", encoding="utf-8")
        info = extractor.extract(src, project_root=tmp_path)
        # Path should be relative.
        assert info.path == str(Path("src") / "lib" / "mod.py")

    def test_absolute_path_without_project_root(
        self, extractor: GenericExtractor, tmp_path: Path
    ) -> None:
        src = tmp_path / "mod.py"
        src.write_text("def func(): pass\n", encoding="utf-8")
        info = extractor.extract(src)
        # Path should be absolute since no project_root given.
        assert str(tmp_path) in info.path

    def test_file_with_only_comments(self, extractor: GenericExtractor, tmp_path: Path) -> None:
        src = tmp_path / "comments.py"
        src.write_text(
            "# This file has only comments\n# No actual code\n",
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        assert info.functions == []
        assert info.classes == []

    def test_multiline_docstring_extraction(
        self, extractor: GenericExtractor, tmp_path: Path
    ) -> None:
        src = tmp_path / "multiline.py"
        src.write_text(
            'def example():\n    """This is a\n    multi-line docstring.\n    """\n    pass\n',
            encoding="utf-8",
        )
        info = extractor.extract(src, project_root=tmp_path)
        assert info.functions[0].docstring is not None
        assert "multi-line" in info.functions[0].docstring
