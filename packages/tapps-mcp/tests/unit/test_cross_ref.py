"""Tests for cross-file reference analysis (Story 75.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.scoring.cross_ref import (
    CrossRefResult,
    _extract_call_kwargs,
    _extract_function_params,
    _extract_imports,
    analyze_cross_references,
)


# ---------------------------------------------------------------------------
# Helper: parse AST from string
# ---------------------------------------------------------------------------

def _parse(code: str):
    import ast
    return ast.parse(code)


# ---------------------------------------------------------------------------
# Tests for _extract_imports
# ---------------------------------------------------------------------------

class TestExtractImports:
    def test_import_module(self) -> None:
        tree = _parse("import os")
        imports = _extract_imports(tree)
        assert imports["os"] == "os"

    def test_from_import(self) -> None:
        tree = _parse("from pathlib import Path")
        imports = _extract_imports(tree)
        assert imports["Path"] == "pathlib.Path"

    def test_aliased_import(self) -> None:
        tree = _parse("import numpy as np")
        imports = _extract_imports(tree)
        assert imports["np"] == "numpy"
        assert "numpy" not in imports

    def test_from_import_aliased(self) -> None:
        tree = _parse("from collections import OrderedDict as OD")
        imports = _extract_imports(tree)
        assert imports["OD"] == "collections.OrderedDict"


# ---------------------------------------------------------------------------
# Tests for _extract_call_kwargs
# ---------------------------------------------------------------------------

class TestExtractCallKwargs:
    def test_call_with_kwargs(self) -> None:
        tree = _parse("foo(bar=1, baz=2)")
        calls = _extract_call_kwargs(tree)
        assert len(calls) == 1
        assert calls[0]["callee_name"] == "foo"
        assert calls[0]["kwargs"] == ["bar", "baz"]

    def test_call_without_kwargs(self) -> None:
        tree = _parse("foo(1, 2)")
        calls = _extract_call_kwargs(tree)
        assert len(calls) == 0

    def test_method_call(self) -> None:
        tree = _parse("obj.method(x=1)")
        calls = _extract_call_kwargs(tree)
        assert len(calls) == 1
        assert calls[0]["callee_name"] == "obj.method"

    def test_star_kwargs_excluded(self) -> None:
        tree = _parse("foo(**kwargs)")
        calls = _extract_call_kwargs(tree)
        # **kwargs has arg=None, so it's excluded
        assert len(calls) == 0


# ---------------------------------------------------------------------------
# Tests for _extract_function_params
# ---------------------------------------------------------------------------

class TestExtractFunctionParams:
    def test_simple_params(self) -> None:
        tree = _parse("def foo(a, b, c): pass")
        params = _extract_function_params(tree, "foo")
        assert params == ["a", "b", "c"]

    def test_excludes_self(self) -> None:
        tree = _parse("class C:\n  def method(self, x, y): pass")
        params = _extract_function_params(tree, "method")
        assert params == ["x", "y"]

    def test_returns_none_for_var_kwargs(self) -> None:
        """Functions with **kwargs accept any kwarg — return None."""
        tree = _parse("def foo(a, **kwargs): pass")
        params = _extract_function_params(tree, "foo")
        assert params is None

    def test_returns_none_when_not_found(self) -> None:
        tree = _parse("def bar(): pass")
        params = _extract_function_params(tree, "nonexistent")
        assert params is None


# ---------------------------------------------------------------------------
# Tests for analyze_cross_references
# ---------------------------------------------------------------------------

class TestAnalyzeCrossReferences:
    def test_no_calls_returns_full(self, tmp_path: Path) -> None:
        """File with no kwarg calls returns full status with no findings."""
        src = tmp_path / "simple.py"
        src.write_text("x = 1\n", encoding="utf-8")
        result = analyze_cross_references(src, tmp_path)
        assert result.status == "full"
        assert result.findings == []

    def test_non_python_returns_degraded(self, tmp_path: Path) -> None:
        src = tmp_path / "file.ts"
        src.write_text("const x = 1;", encoding="utf-8")
        result = analyze_cross_references(src, tmp_path)
        assert result.status == "degraded"

    def test_nonexistent_file_returns_degraded(self, tmp_path: Path) -> None:
        result = analyze_cross_references(tmp_path / "missing.py", tmp_path)
        assert result.status == "degraded"

    def test_detects_kwarg_mismatch(self, tmp_path: Path) -> None:
        """Caller uses wrong kwarg names for a function in another file."""
        # Create callee module
        pkg = tmp_path / "mymod"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "helper.py").write_text(
            "def generate(_user_id, _context, _query_id):\n    pass\n",
            encoding="utf-8",
        )

        # Create caller
        caller = tmp_path / "caller.py"
        caller.write_text(
            "from mymod.helper import generate\n"
            "generate(user_id=1, context='x', query_id=2)\n",
            encoding="utf-8",
        )

        result = analyze_cross_references(caller, tmp_path)
        assert len(result.findings) == 1
        f = result.findings[0]
        assert "user_id" in f.issue
        assert f.confidence == "medium"
        assert f.callee_name == "generate"

    def test_no_false_positive_with_var_kwargs(self, tmp_path: Path) -> None:
        """Functions accepting **kwargs should not trigger findings."""
        pkg = tmp_path / "mymod"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "flexible.py").write_text(
            "def do_stuff(**kwargs):\n    pass\n",
            encoding="utf-8",
        )

        caller = tmp_path / "caller.py"
        caller.write_text(
            "from mymod.flexible import do_stuff\n"
            "do_stuff(any_kwarg=1, another=2)\n",
            encoding="utf-8",
        )

        result = analyze_cross_references(caller, tmp_path)
        assert result.findings == []

    def test_correct_kwargs_no_findings(self, tmp_path: Path) -> None:
        """Matching kwargs should produce no findings."""
        pkg = tmp_path / "mymod"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "exact.py").write_text(
            "def process(name, value):\n    pass\n",
            encoding="utf-8",
        )

        caller = tmp_path / "caller.py"
        caller.write_text(
            "from mymod.exact import process\n"
            "process(name='test', value=42)\n",
            encoding="utf-8",
        )

        result = analyze_cross_references(caller, tmp_path)
        assert result.findings == []

    def test_unresolved_imports_degrade_status(self, tmp_path: Path) -> None:
        """Imports that can't be resolved set status to degraded/partial."""
        caller = tmp_path / "caller.py"
        caller.write_text(
            "from nonexistent_package import func\n"
            "func(bad_kwarg=1)\n",
            encoding="utf-8",
        )

        result = analyze_cross_references(caller, tmp_path)
        assert result.status in ("degraded", "partial")
        assert result.files_unresolved > 0

    def test_syntax_error_returns_degraded(self, tmp_path: Path) -> None:
        src = tmp_path / "bad.py"
        src.write_text("def foo(:\n", encoding="utf-8")
        result = analyze_cross_references(src, tmp_path)
        assert result.status == "degraded"

    def test_to_dict_serialization(self) -> None:
        result = CrossRefResult(status="partial", files_resolved=2, files_unresolved=1)
        d = result.to_dict()
        assert d["cross_file_analysis"] == "partial"
        assert d["files_resolved"] == 2
        assert d["findings_count"] == 0
