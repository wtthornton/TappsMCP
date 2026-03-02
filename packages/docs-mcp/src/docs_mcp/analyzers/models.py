"""Data models for code analysis results."""

from __future__ import annotations

from pydantic import BaseModel


class ModuleNode(BaseModel):
    """Hierarchical representation of a Python module/package."""

    name: str
    path: str
    is_package: bool = False
    submodules: list[ModuleNode] = []
    public_api_count: int = 0
    module_docstring: str | None = None
    has_main: bool = False
    all_exports: list[str] | None = None
    size_bytes: int = 0
    function_count: int = 0
    class_count: int = 0


class ModuleMap(BaseModel):
    """Complete module map of a project."""

    project_root: str
    project_name: str
    module_tree: list[ModuleNode] = []
    entry_points: list[str] = []
    total_modules: int = 0
    total_packages: int = 0
    public_api_count: int = 0
