"""Tests for the Python AST extractor."""

from __future__ import annotations

from pathlib import Path

import pytest

from docs_mcp.extractors.python import PythonExtractor


@pytest.fixture
def extractor() -> PythonExtractor:
    return PythonExtractor()


# ------------------------------------------------------------------
# can_handle
# ------------------------------------------------------------------


class TestCanHandle:
    def test_handles_py_files(self, extractor: PythonExtractor) -> None:
        assert extractor.can_handle(Path("module.py")) is True

    def test_handles_pyi_files(self, extractor: PythonExtractor) -> None:
        assert extractor.can_handle(Path("module.pyi")) is True

    def test_rejects_non_python(self, extractor: PythonExtractor) -> None:
        assert extractor.can_handle(Path("module.js")) is False
        assert extractor.can_handle(Path("module.txt")) is False
        assert extractor.can_handle(Path("Makefile")) is False


# ------------------------------------------------------------------
# Empty / error cases
# ------------------------------------------------------------------


class TestEmptyAndErrors:
    def test_empty_file(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "empty.py"
        f.write_text("", encoding="utf-8")
        result = extractor.extract(f, project_root=tmp_path)
        assert result.path == "empty.py"
        assert result.functions == []
        assert result.classes == []
        assert result.constants == []
        assert result.imports == []
        assert result.docstring is None

    def test_syntax_error_returns_degraded(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "bad.py"
        f.write_text("def foo(:\n", encoding="utf-8")
        result = extractor.extract(f, project_root=tmp_path)
        assert result.path == "bad.py"
        assert result.functions == []

    def test_nonexistent_file_returns_degraded(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "missing.py"
        result = extractor.extract(f, project_root=tmp_path)
        assert result.path == "missing.py"
        assert result.functions == []

    def test_encoding_error_returns_degraded(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "binary.py"
        # Write invalid UTF-8 that also isn't valid latin-1 Python
        f.write_bytes(b"\x80\x81\x82def foo():\n    pass\n")
        # Should not raise
        result = extractor.extract(f, project_root=tmp_path)
        assert result.path == "binary.py"


# ------------------------------------------------------------------
# Module-level docstring
# ------------------------------------------------------------------


class TestModuleDocstring:
    def test_module_docstring_extracted(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "mod.py"
        f.write_text('"""Module docstring."""\n\nx = 1\n', encoding="utf-8")
        result = extractor.extract(f, project_root=tmp_path)
        assert result.docstring == "Module docstring."

    def test_no_module_docstring(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "mod.py"
        f.write_text("x = 1\n", encoding="utf-8")
        result = extractor.extract(f, project_root=tmp_path)
        assert result.docstring is None


# ------------------------------------------------------------------
# Function extraction
# ------------------------------------------------------------------


class TestFunctionExtraction:
    def test_simple_function(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "funcs.py"
        f.write_text(
            'def greet(name: str) -> str:\n    """Say hello."""\n    return f"Hello {name}"\n',
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        assert len(result.functions) == 1
        func = result.functions[0]
        assert func.name == "greet"
        assert func.line == 1
        assert func.return_annotation == "str"
        assert func.docstring == "Say hello."
        assert func.is_async is False
        assert "def greet(name: str) -> str:" in func.signature

    def test_async_function(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "async_funcs.py"
        f.write_text(
            "async def fetch(url: str) -> bytes:\n    pass\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        func = result.functions[0]
        assert func.is_async is True
        assert func.signature.startswith("async def")

    def test_function_no_annotations(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "plain.py"
        f.write_text("def add(x, y):\n    return x + y\n", encoding="utf-8")
        result = extractor.extract(f, project_root=tmp_path)
        func = result.functions[0]
        assert func.return_annotation is None
        assert len(func.parameters) == 2
        assert func.parameters[0].name == "x"
        assert func.parameters[0].annotation is None

    def test_function_with_defaults(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "defaults.py"
        f.write_text(
            "def connect(host: str = 'localhost', port: int = 8080) -> None:\n    pass\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        func = result.functions[0]
        assert func.parameters[0].default == "'localhost'"
        assert func.parameters[1].default == "8080"

    def test_args_and_kwargs(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "varargs.py"
        f.write_text(
            "def log(*args: str, **kwargs: int) -> None:\n    pass\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        func = result.functions[0]
        params = {p.name: p for p in func.parameters}
        assert params["args"].kind == "VAR_POSITIONAL"
        assert params["args"].annotation == "str"
        assert params["kwargs"].kind == "VAR_KEYWORD"
        assert params["kwargs"].annotation == "int"

    def test_keyword_only_params(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "kwonly.py"
        f.write_text(
            "def foo(a: int, *, key: str = 'x') -> None:\n    pass\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        func = result.functions[0]
        key_param = next(p for p in func.parameters if p.name == "key")
        assert key_param.kind == "KEYWORD_ONLY"
        assert key_param.default == "'x'"

    def test_positional_only_params(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "posonly.py"
        f.write_text("def foo(x: int, /) -> None:\n    pass\n", encoding="utf-8")
        result = extractor.extract(f, project_root=tmp_path)
        func = result.functions[0]
        assert func.parameters[0].kind == "POSITIONAL_ONLY"


# ------------------------------------------------------------------
# Decorator extraction
# ------------------------------------------------------------------


class TestDecoratorExtraction:
    def test_simple_decorator(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "deco.py"
        f.write_text(
            "@staticmethod\ndef foo():\n    pass\n", encoding="utf-8"
        )
        result = extractor.extract(f, project_root=tmp_path)
        func = result.functions[0]
        assert len(func.decorators) == 1
        assert func.decorators[0].name == "staticmethod"
        assert func.decorators[0].arguments is None
        assert func.is_staticmethod is True

    def test_decorator_with_arguments(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "deco_args.py"
        f.write_text(
            "from functools import lru_cache\n\n"
            "@lru_cache(maxsize=128)\ndef compute(n: int) -> int:\n    return n\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        func = result.functions[0]
        deco = func.decorators[0]
        assert deco.name == "lru_cache"
        assert deco.arguments == "maxsize=128"

    def test_property_decorator(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "prop.py"
        f.write_text(
            "class C:\n    @property\n    def x(self) -> int:\n        return 1\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        method = result.classes[0].methods[0]
        assert method.is_property is True

    def test_classmethod_decorator(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "cm.py"
        f.write_text(
            "class C:\n    @classmethod\n    def create(cls) -> 'C':\n        return cls()\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        method = result.classes[0].methods[0]
        assert method.is_classmethod is True

    def test_abstractmethod_decorator(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "abc_m.py"
        f.write_text(
            "from abc import abstractmethod\n\n"
            "class Base:\n    @abstractmethod\n    def run(self) -> None:\n        pass\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        method = result.classes[0].methods[0]
        assert method.is_abstractmethod is True

    def test_multiple_decorators(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "multi_deco.py"
        f.write_text(
            "class C:\n"
            "    @classmethod\n"
            "    @abstractmethod\n"
            "    def run(cls) -> None:\n"
            "        pass\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        method = result.classes[0].methods[0]
        assert method.is_classmethod is True
        assert method.is_abstractmethod is True
        assert len(method.decorators) == 2


# ------------------------------------------------------------------
# Class extraction
# ------------------------------------------------------------------


class TestClassExtraction:
    def test_simple_class(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "cls.py"
        f.write_text(
            'class Animal:\n    """An animal."""\n\n'
            "    def speak(self) -> str:\n        return ''\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        assert len(result.classes) == 1
        cls = result.classes[0]
        assert cls.name == "Animal"
        assert cls.docstring == "An animal."
        assert len(cls.methods) == 1
        assert cls.methods[0].name == "speak"

    def test_class_with_bases(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "inherit.py"
        f.write_text(
            "class Dog(Animal, Serializable):\n    pass\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        cls = result.classes[0]
        assert cls.bases == ["Animal", "Serializable"]

    def test_class_with_decorator(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "dataclass.py"
        f.write_text(
            "from dataclasses import dataclass\n\n"
            "@dataclass\nclass Point:\n    x: float\n    y: float\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        cls = result.classes[0]
        assert len(cls.decorators) == 1
        assert cls.decorators[0].name == "dataclass"

    def test_class_variables(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "clsvar.py"
        f.write_text(
            "class Config:\n"
            "    debug: bool = True\n"
            "    name = 'app'\n"
            "    count: int\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        cls = result.classes[0]
        assert len(cls.class_variables) == 3
        names = {v.name for v in cls.class_variables}
        assert names == {"debug", "name", "count"}

        debug_var = next(v for v in cls.class_variables if v.name == "debug")
        assert debug_var.annotation == "bool"
        assert debug_var.value == "True"

        count_var = next(v for v in cls.class_variables if v.name == "count")
        assert count_var.annotation == "int"
        assert count_var.value is None

    def test_nested_class(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "nested.py"
        f.write_text(
            "class Outer:\n"
            "    class Inner:\n"
            "        def method(self) -> None:\n"
            "            pass\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        # Nested class is captured as a top-level body item of Outer,
        # but since our extractor only looks at direct children,
        # nested classes won't be separate — they are part of Outer.
        assert len(result.classes) == 1
        assert result.classes[0].name == "Outer"


# ------------------------------------------------------------------
# Import extraction
# ------------------------------------------------------------------


class TestImportExtraction:
    def test_import_statement(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "imp.py"
        f.write_text("import os\nimport sys\n", encoding="utf-8")
        result = extractor.extract(f, project_root=tmp_path)
        assert "import os" in result.imports
        assert "import sys" in result.imports

    def test_from_import(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "fromimp.py"
        f.write_text(
            "from pathlib import Path\nfrom typing import Optional, List\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        assert len(result.imports) == 2
        assert any("pathlib" in i for i in result.imports)
        assert any("typing" in i for i in result.imports)


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------


class TestConstants:
    def test_module_constant_plain(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "const.py"
        f.write_text("MAX_SIZE = 100\n", encoding="utf-8")
        result = extractor.extract(f, project_root=tmp_path)
        assert len(result.constants) == 1
        assert result.constants[0].name == "MAX_SIZE"
        assert result.constants[0].value == "100"
        assert result.constants[0].annotation is None

    def test_module_constant_annotated(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "ann_const.py"
        f.write_text("TIMEOUT: int = 30\n", encoding="utf-8")
        result = extractor.extract(f, project_root=tmp_path)
        assert len(result.constants) == 1
        assert result.constants[0].name == "TIMEOUT"
        assert result.constants[0].value == "30"
        assert result.constants[0].annotation == "int"

    def test_annotation_only_no_value(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "ann_only.py"
        f.write_text("name: str\n", encoding="utf-8")
        result = extractor.extract(f, project_root=tmp_path)
        assert len(result.constants) == 1
        assert result.constants[0].name == "name"
        assert result.constants[0].value is None
        assert result.constants[0].annotation == "str"


# ------------------------------------------------------------------
# __all__ and __main__
# ------------------------------------------------------------------


class TestAllAndMain:
    def test_all_exports_detected(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "exp.py"
        f.write_text(
            "__all__ = ['foo', 'bar']\n\ndef foo(): pass\ndef bar(): pass\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        assert result.all_exports == ["foo", "bar"]

    def test_no_all_is_none(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "noall.py"
        f.write_text("def foo(): pass\n", encoding="utf-8")
        result = extractor.extract(f, project_root=tmp_path)
        assert result.all_exports is None

    def test_main_block_detected(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "main.py"
        f.write_text(
            "def run(): pass\n\nif __name__ == '__main__':\n    run()\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        assert result.has_main_block is True

    def test_no_main_block(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "nomain.py"
        f.write_text("def run(): pass\n", encoding="utf-8")
        result = extractor.extract(f, project_root=tmp_path)
        assert result.has_main_block is False

    def test_main_block_reversed(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "main_rev.py"
        f.write_text(
            "if '__main__' == __name__:\n    pass\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        assert result.has_main_block is True


# ------------------------------------------------------------------
# Type annotations
# ------------------------------------------------------------------


class TestTypeAnnotations:
    def test_optional_annotation(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "opt.py"
        f.write_text(
            "def foo(x: int | None) -> str | None:\n    pass\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        func = result.functions[0]
        assert func.parameters[0].annotation == "int | None"
        assert func.return_annotation == "str | None"

    def test_generic_container_annotation(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "generic.py"
        f.write_text(
            "def foo(items: list[dict[str, int]]) -> tuple[int, ...]:\n    pass\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        func = result.functions[0]
        assert func.parameters[0].annotation == "list[dict[str, int]]"
        assert func.return_annotation == "tuple[int, ...]"

    def test_string_annotation(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "forward.py"
        f.write_text(
            "def foo() -> 'MyClass':\n    pass\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        func = result.functions[0]
        assert func.return_annotation == "'MyClass'"


# ------------------------------------------------------------------
# Path handling
# ------------------------------------------------------------------


class TestPathHandling:
    def test_relative_path_with_project_root(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        sub = tmp_path / "src" / "pkg"
        sub.mkdir(parents=True)
        f = sub / "mod.py"
        f.write_text("x = 1\n", encoding="utf-8")
        result = extractor.extract(f, project_root=tmp_path)
        # Should be relative
        assert result.path == str(Path("src") / "pkg" / "mod.py")

    def test_absolute_path_without_project_root(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "mod.py"
        f.write_text("x = 1\n", encoding="utf-8")
        result = extractor.extract(f)
        # Without project_root, path is absolute
        assert str(tmp_path) in result.path


# ------------------------------------------------------------------
# Protocol conformance
# ------------------------------------------------------------------


class TestProtocolConformance:
    def test_conforms_to_extractor_protocol(self) -> None:
        """PythonExtractor should be usable where Extractor is expected."""
        from docs_mcp.extractors.base import Extractor

        def use_extractor(e: Extractor) -> bool:
            return e.can_handle(Path("test.py"))

        ext = PythonExtractor()
        assert use_extractor(ext) is True


# ------------------------------------------------------------------
# Complex / integration-style cases
# ------------------------------------------------------------------


class TestComplexCases:
    def test_full_module(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        """Test extraction of a realistic module with mixed content."""
        f = tmp_path / "full.py"
        f.write_text(
            '"""A sample module."""\n'
            "\n"
            "from __future__ import annotations\n"
            "import os\n"
            "from pathlib import Path\n"
            "\n"
            "__all__ = ['MyClass', 'helper']\n"
            "\n"
            "VERSION: str = '1.0.0'\n"
            "MAX_RETRIES = 3\n"
            "\n"
            "\n"
            "class MyClass(object):\n"
            '    """My class docstring."""\n'
            "\n"
            "    default_name: str = 'unnamed'\n"
            "\n"
            "    def __init__(self, name: str) -> None:\n"
            '        """Initialize."""\n'
            "        self.name = name\n"
            "\n"
            "    @property\n"
            "    def display_name(self) -> str:\n"
            "        return self.name.upper()\n"
            "\n"
            "    @staticmethod\n"
            "    def create() -> MyClass:\n"
            "        return MyClass('default')\n"
            "\n"
            "\n"
            "async def helper(x: int, y: int = 0) -> int:\n"
            '    """Help with stuff."""\n'
            "    return x + y\n"
            "\n"
            "\n"
            "if __name__ == '__main__':\n"
            "    print('hello')\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)

        assert result.docstring == "A sample module."
        assert result.has_main_block is True
        assert result.all_exports == ["MyClass", "helper"]

        # Imports
        assert len(result.imports) == 3

        # Constants
        const_names = {c.name for c in result.constants}
        assert "VERSION" in const_names
        assert "MAX_RETRIES" in const_names
        # __all__ is also captured as a constant
        assert "__all__" in const_names

        # Class
        assert len(result.classes) == 1
        cls = result.classes[0]
        assert cls.name == "MyClass"
        assert cls.bases == ["object"]
        assert cls.docstring == "My class docstring."
        assert len(cls.methods) == 3
        method_names = {m.name for m in cls.methods}
        assert method_names == {"__init__", "display_name", "create"}
        assert len(cls.class_variables) == 1
        assert cls.class_variables[0].name == "default_name"

        # Properties and staticmethods
        display = next(m for m in cls.methods if m.name == "display_name")
        assert display.is_property is True
        create = next(m for m in cls.methods if m.name == "create")
        assert create.is_staticmethod is True

        # Async function
        assert len(result.functions) == 1
        func = result.functions[0]
        assert func.name == "helper"
        assert func.is_async is True
        assert func.docstring == "Help with stuff."
        assert func.return_annotation == "int"

    def test_end_line_tracking(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "lines.py"
        f.write_text(
            "def foo():\n"
            "    x = 1\n"
            "    return x\n"
            "\n"
            "class Bar:\n"
            "    def method(self):\n"
            "        pass\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        func = result.functions[0]
        assert func.line == 1
        assert func.end_line == 3

        cls = result.classes[0]
        assert cls.line == 5
        assert cls.end_line == 7

    def test_decorator_with_dotted_name(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "dotted.py"
        f.write_text(
            "@app.route('/hello', methods=['GET'])\n"
            "def hello():\n    pass\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        deco = result.functions[0].decorators[0]
        assert deco.name == "app.route"
        assert deco.arguments == "'/hello', methods=['GET']"

    def test_all_tuple_format(
        self, extractor: PythonExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "all_tuple.py"
        f.write_text(
            "__all__ = ('alpha', 'beta')\n",
            encoding="utf-8",
        )
        result = extractor.extract(f, project_root=tmp_path)
        assert result.all_exports == ["alpha", "beta"]
