"""Data models for code extraction results."""

from __future__ import annotations

from pydantic import BaseModel


class DecoratorInfo(BaseModel):
    """Information about a decorator applied to a function or class."""

    name: str
    arguments: str | None = None
    line: int


class ParameterInfo(BaseModel):
    """Information about a function parameter."""

    name: str
    annotation: str | None = None
    default: str | None = None
    kind: str = "POSITIONAL_OR_KEYWORD"


class FunctionInfo(BaseModel):
    """Information about a function or method."""

    name: str
    line: int
    end_line: int | None = None
    signature: str
    parameters: list[ParameterInfo] = []
    return_annotation: str | None = None
    decorators: list[DecoratorInfo] = []
    docstring: str | None = None
    is_async: bool = False
    is_property: bool = False
    is_staticmethod: bool = False
    is_classmethod: bool = False
    is_abstractmethod: bool = False


class ConstantInfo(BaseModel):
    """Information about a module-level or class-level constant/variable."""

    name: str
    line: int
    value: str | None = None
    annotation: str | None = None


class ClassInfo(BaseModel):
    """Information about a class definition."""

    name: str
    line: int
    end_line: int | None = None
    bases: list[str] = []
    decorators: list[DecoratorInfo] = []
    docstring: str | None = None
    methods: list[FunctionInfo] = []
    class_variables: list[ConstantInfo] = []


class ModuleInfo(BaseModel):
    """Information about a Python module extracted from its AST."""

    path: str
    docstring: str | None = None
    imports: list[str] = []
    functions: list[FunctionInfo] = []
    classes: list[ClassInfo] = []
    constants: list[ConstantInfo] = []
    has_main_block: bool = False
    all_exports: list[str] | None = None
