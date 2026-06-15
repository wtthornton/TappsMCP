"""Unit tests for static call resolution helpers."""

from __future__ import annotations

from tapps_mcp.project.call_graph_analyze import FileIndex
from tapps_mcp.project.call_graph_resolve import qualify, resolve_attribute, resolve_name


def test_qualify_module_function() -> None:
    idx = FileIndex(module="demo.mod", rel_path="demo/mod.py")
    assert qualify(idx, "run", []) == "demo.mod.run"


def test_resolve_self_method_call() -> None:
    idx = FileIndex(module="demo.svc", rel_path="demo/svc.py")
    idx.classes["Service"] = "demo.svc.Service"
    class_stack = ["Service"]
    callee = resolve_attribute(
        idx,
        _attr("self", "handle"),
        class_stack,
        {},
    )
    assert callee == "demo.svc.Service.handle"


def test_resolve_imported_name() -> None:
    idx = FileIndex(module="demo.main", rel_path="demo/main.py")
    idx.imports["helper"] = "other.helper"
    assert resolve_name(idx, "helper", [], {}) == "other.helper"


def _attr(base: str, name: str):
    import ast

    return ast.Attribute(value=ast.Name(id=base), attr=name)
