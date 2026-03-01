"""AST parser - extracts code structure from Python files.

Used by impact analysis (import graph) and project profiling (structure).
Pure stdlib - no external dependencies.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from pathlib import Path

from tapps_mcp.project.models import ClassInfo, FunctionInfo, ModuleInfo

logger = structlog.get_logger(__name__)


class ASTParser:
    """Parse Python source files and extract structural metadata."""

    def __init__(self) -> None:
        self._cache: dict[str, ModuleInfo] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_file(self, file_path: Path, *, use_cache: bool = True) -> ModuleInfo:
        """Parse *file_path* and return a :class:`ModuleInfo`.

        Args:
            file_path: Path to a ``.py`` file.
            use_cache: Re-use a previous parse result when available.
        """
        key = str(file_path)
        if use_cache and key in self._cache:
            return self._cache[key]

        try:
            code = file_path.read_text(encoding="utf-8")
            tree = ast.parse(code, filename=key)
        except (SyntaxError, UnicodeDecodeError):
            empty = ModuleInfo()
            if use_cache:
                self._cache[key] = empty
            return empty

        info = self._extract_module(tree)
        if use_cache:
            self._cache[key] = info
        return info

    def get_file_structure(self, file_path: Path) -> dict[str, Any]:
        """Return a plain-dict summary of *file_path*."""
        info = self.parse_file(file_path)
        return {
            "file": str(file_path),
            "imports": info.imports,
            "classes": [c.model_dump(exclude={"docstring"}) for c in info.classes],
            "functions": [f.model_dump(exclude={"docstring"}) for f in info.functions],
            "docstring": info.docstring,
        }

    def clear_cache(self) -> None:
        self._cache.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_module(self, tree: ast.Module) -> ModuleInfo:
        imports: list[str] = []
        functions: list[FunctionInfo] = []
        classes: list[ClassInfo] = []
        constants: list[tuple[str, Any]] = []
        docstring: str | None = None

        if tree.body and isinstance(tree.body[0], ast.Expr):
            val = tree.body[0].value
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                docstring = val.value

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for alias in node.names:
                    imports.append(f"{mod}.{alias.name}" if mod else alias.name)
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                functions.append(self._extract_func(node))
            elif isinstance(node, ast.ClassDef):
                classes.append(self._extract_class(node))
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        try:
                            value = ast.literal_eval(node.value)
                            constants.append((target.id, value))
                        except (ValueError, SyntaxError):
                            pass

        return ModuleInfo(
            imports=imports,
            functions=functions,
            classes=classes,
            constants=constants,
            docstring=docstring,
        )

    @staticmethod
    def _extract_func(node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionInfo:
        args = [a.arg for a in node.args.args]
        sig = f"def {node.name}({', '.join(args)})"
        returns: str | None = None
        if node.returns:
            returns = ast.unparse(node.returns)
        return FunctionInfo(
            name=node.name,
            line=node.lineno,
            signature=sig,
            args=args,
            returns=returns,
            docstring=ast.get_docstring(node),
        )

    @staticmethod
    def _extract_class(node: ast.ClassDef) -> ClassInfo:
        bases: list[str] = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            else:
                bases.append(ast.unparse(base))
        methods = [
            item.name
            for item in node.body
            if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
        ]
        return ClassInfo(
            name=node.name,
            line=node.lineno,
            bases=bases,
            methods=methods,
            docstring=ast.get_docstring(node),
        )
