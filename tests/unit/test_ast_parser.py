"""Unit tests for tapps_mcp.project.ast_parser."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.project.ast_parser import ASTParser


class TestASTParser:
    def test_parse_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("")
        info = ASTParser().parse_file(f)
        assert info.imports == []
        assert info.functions == []
        assert info.classes == []

    def test_parse_imports(self, tmp_path: Path) -> None:
        f = tmp_path / "imp.py"
        f.write_text("import os\nfrom pathlib import Path\n")
        info = ASTParser().parse_file(f)
        assert "os" in info.imports
        assert "pathlib.Path" in info.imports

    def test_parse_function(self, tmp_path: Path) -> None:
        f = tmp_path / "funcs.py"
        f.write_text('def hello(name: str) -> str:\n    """Greet."""\n    return f"hi {name}"\n')
        info = ASTParser().parse_file(f)
        assert len(info.functions) == 1
        assert info.functions[0].name == "hello"
        assert "name" in info.functions[0].args
        assert info.functions[0].returns == "str"
        assert info.functions[0].docstring == "Greet."

    def test_parse_class(self, tmp_path: Path) -> None:
        f = tmp_path / "cls.py"
        f.write_text("class Foo(Bar):\n    def method(self): ...\n")
        info = ASTParser().parse_file(f)
        assert len(info.classes) == 1
        assert info.classes[0].name == "Foo"
        assert "Bar" in info.classes[0].bases
        assert "method" in info.classes[0].methods

    def test_parse_constants(self, tmp_path: Path) -> None:
        f = tmp_path / "const.py"
        f.write_text('VERSION = "1.0"\nMAX = 100\n')
        info = ASTParser().parse_file(f)
        names = [c[0] for c in info.constants]
        assert "VERSION" in names
        assert "MAX" in names

    def test_parse_docstring(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.py"
        f.write_text('"""Module doc."""\n\nx = 1\n')
        info = ASTParser().parse_file(f)
        assert info.docstring == "Module doc."

    def test_syntax_error_returns_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("def broken(:\n")
        info = ASTParser().parse_file(f)
        assert info.imports == []

    def test_cache_reuse(self, tmp_path: Path) -> None:
        f = tmp_path / "cached.py"
        f.write_text("x = 1\n")
        parser = ASTParser()
        r1 = parser.parse_file(f)
        r2 = parser.parse_file(f)
        assert r1 is r2

    def test_cache_bypass(self, tmp_path: Path) -> None:
        f = tmp_path / "nocache.py"
        f.write_text("x = 1\n")
        parser = ASTParser()
        r1 = parser.parse_file(f)
        r2 = parser.parse_file(f, use_cache=False)
        assert r1 is not r2

    def test_clear_cache(self, tmp_path: Path) -> None:
        f = tmp_path / "clearcache.py"
        f.write_text("x = 1\n")
        parser = ASTParser()
        parser.parse_file(f)
        parser.clear_cache()
        assert len(parser._cache) == 0

    def test_get_file_structure(self, tmp_path: Path) -> None:
        f = tmp_path / "struct.py"
        f.write_text("import os\n\ndef foo(): ...\n\nclass Bar: ...\n")
        result = ASTParser().get_file_structure(f)
        assert "os" in result["imports"]
        assert any(fn["name"] == "foo" for fn in result["functions"])
        assert any(c["name"] == "Bar" for c in result["classes"])

    def test_async_function(self, tmp_path: Path) -> None:
        f = tmp_path / "async_fn.py"
        f.write_text("async def run() -> None: ...\n")
        info = ASTParser().parse_file(f)
        assert len(info.functions) == 1
        assert info.functions[0].name == "run"
