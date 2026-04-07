"""Import dependency graph builder for Python projects."""

from __future__ import annotations

import ast
from collections import defaultdict
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from pathlib import Path

import structlog
from pydantic import BaseModel

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class ImportEdge(BaseModel):
    """A single import relationship between two modules."""

    source: str
    target: str
    import_type: str = "runtime"
    line: int = 0
    names: list[str] = []


class ImportGraph(BaseModel):
    """Directed graph of import relationships in a project."""

    edges: list[ImportEdge] = []
    modules: list[str] = []
    external_imports: dict[str, list[str]] = {}
    entry_points: list[str] = []
    most_imported: list[str] = []
    total_internal_imports: int = 0
    total_external_imports: int = 0


class ImportGraphBuilder:
    """Builds a directed import dependency graph for a Python project."""

    SKIP_DIRS: ClassVar[frozenset[str]] = frozenset(
        {
            "__pycache__",
            ".git",
            ".venv",
            "venv",
            "node_modules",
            ".tox",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            "dist",
            "build",
            ".eggs",
            "site-packages",
        }
    )

    STDLIB_TOP_LEVEL: ClassVar[frozenset[str]] = frozenset(
        {
            "abc",
            "ast",
            "asyncio",
            "base64",
            "collections",
            "contextlib",
            "copy",
            "csv",
            "dataclasses",
            "datetime",
            "enum",
            "functools",
            "glob",
            "hashlib",
            "html",
            "http",
            "importlib",
            "inspect",
            "io",
            "itertools",
            "json",
            "logging",
            "math",
            "multiprocessing",
            "operator",
            "os",
            "pathlib",
            "pickle",
            "platform",
            "pprint",
            "queue",
            "random",
            "re",
            "secrets",
            "shlex",
            "shutil",
            "signal",
            "socket",
            "sqlite3",
            "string",
            "struct",
            "subprocess",
            "sys",
            "tempfile",
            "textwrap",
            "threading",
            "time",
            "timeit",
            "tomllib",
            "traceback",
            "types",
            "typing",
            "unittest",
            "urllib",
            "uuid",
            "warnings",
            "weakref",
            "xml",
            "zipfile",
            "__future__",
            "typing_extensions",
        }
    )

    def build(
        self,
        project_root: Path,
        *,
        source_dirs: list[str] | None = None,
    ) -> ImportGraph:
        """Build the import graph for a project."""
        src_paths = self._resolve_source_dirs(project_root, source_dirs)
        py_files = self._discover_python_files(src_paths)

        if not py_files:
            return ImportGraph()

        # Build mapping from module dotted name to relative path.
        # Register both the full path (e.g. src.helper) and the path
        # relative to the source root (e.g. helper) so that bare imports
        # like `import helper` resolve correctly for src/-layout projects.
        module_paths: dict[str, str] = {}
        path_to_module: dict[str, str] = {}
        for py_file in py_files:
            rel = py_file.relative_to(project_root)
            rel_str = str(rel).replace("\\", "/")
            dotted = self._path_to_module_name(rel)
            module_paths[dotted] = rel_str
            path_to_module[rel_str] = dotted

            # Also register the shortened form relative to the source root
            for src_path in src_paths:
                try:
                    rel_to_src = py_file.relative_to(src_path)
                except ValueError:
                    continue
                short_dotted = self._path_to_module_name(rel_to_src)
                if short_dotted != dotted:
                    if short_dotted not in module_paths:
                        module_paths[short_dotted] = rel_str
                    # Use the source-relative dotted name for resolution
                    # so that relative imports work correctly
                    path_to_module[rel_str] = short_dotted

        all_modules = sorted(set(module_paths.values()))

        edges: list[ImportEdge] = []
        external_imports: dict[str, list[str]] = defaultdict(list)
        total_external = 0

        for py_file in py_files:
            rel = py_file.relative_to(project_root)
            rel_str = str(rel).replace("\\", "/")
            source_module = path_to_module[rel_str]

            file_edges, file_externals = self._analyze_file(
                py_file,
                source_module,
                rel_str,
                module_paths,
                project_root,
            )
            edges.extend(file_edges)
            if file_externals:
                external_imports[rel_str] = file_externals
                total_external += len(file_externals)

        # Compute graph metrics
        incoming: dict[str, int] = defaultdict(int)
        has_incoming: set[str] = set()
        for edge in edges:
            incoming[edge.target] += 1
            has_incoming.add(edge.target)

        entry_points = sorted(m for m in all_modules if m not in has_incoming)

        most_imported = sorted(
            incoming.keys(),
            key=lambda m: incoming[m],
            reverse=True,
        )

        return ImportGraph(
            edges=edges,
            modules=all_modules,
            external_imports=dict(external_imports),
            entry_points=entry_points,
            most_imported=most_imported,
            total_internal_imports=len(edges),
            total_external_imports=total_external,
        )

    # ------------------------------------------------------------------
    # File discovery
    # ------------------------------------------------------------------

    def _resolve_source_dirs(
        self,
        project_root: Path,
        source_dirs: list[str] | None,
    ) -> list[Path]:
        """Resolve source directories, auto-detecting src/ or monorepo layout."""
        if source_dirs:
            resolved = [project_root / d for d in source_dirs if (project_root / d).is_dir()]
            if resolved:
                return resolved

        # Auto-detect: prefer src/ layout
        src = project_root / "src"
        if src.is_dir():
            return [src]

        # Monorepo: packages/*/src (for cross-package import resolution)
        pkgs_dir = project_root / "packages"
        if pkgs_dir.is_dir():
            result: list[Path] = []
            for pkg_dir in sorted(pkgs_dir.iterdir()):
                if not pkg_dir.is_dir() or pkg_dir.name.startswith("."):
                    continue
                pkg_src = pkg_dir / "src"
                if pkg_src.is_dir():
                    result.append(pkg_src)
            if result:
                return result

        return [project_root]

    def _discover_python_files(self, src_paths: list[Path]) -> list[Path]:
        """Walk source directories and collect .py files."""
        py_files: list[Path] = []
        for src_path in src_paths:
            if not src_path.is_dir():
                continue
            for item in src_path.rglob("*.py"):
                if self._should_skip(item):
                    continue
                py_files.append(item)
        return sorted(py_files)

    def _should_skip(self, path: Path) -> bool:
        """Check if a path is inside a directory that should be skipped."""
        for part in path.parts:
            if part in self.SKIP_DIRS or (part.startswith(".") and part != "."):
                return True
        return False

    # ------------------------------------------------------------------
    # Import analysis
    # ------------------------------------------------------------------

    def _analyze_file(
        self,
        py_file: Path,
        source_module: str,
        source_rel: str,
        module_paths: dict[str, str],
        project_root: Path,
    ) -> tuple[list[ImportEdge], list[str]]:
        """Parse a file and extract import edges."""
        try:
            source_text = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            logger.warning("read_error", path=str(py_file))
            return [], []

        try:
            tree = ast.parse(source_text, filename=str(py_file))
        except SyntaxError:
            logger.warning("syntax_error", path=str(py_file))
            return [], []

        # Detect TYPE_CHECKING blocks
        type_checking_ranges = self._find_type_checking_ranges(tree)
        # Detect try/except ImportError blocks
        conditional_ranges = self._find_conditional_import_ranges(tree)

        edges: list[ImportEdge] = []
        externals: list[str] = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue

            import_type = self._classify_import_type(
                node,
                type_checking_ranges,
                conditional_ranges,
                tree,
            )

            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_level = alias.name.split(".")[0]
                    target_path = self._resolve_import(
                        alias.name,
                        source_module,
                        module_paths,
                        project_root,
                    )
                    if target_path is not None:
                        edges.append(
                            ImportEdge(
                                source=source_rel,
                                target=target_path,
                                import_type=import_type,
                                line=node.lineno,
                                names=[],
                            )
                        )
                    elif top_level not in self.STDLIB_TOP_LEVEL:
                        externals.append(alias.name)

            elif isinstance(node, ast.ImportFrom):
                if node.module is None and node.level > 0:
                    # Relative import: from . import X
                    resolved_module = self._resolve_relative_import(
                        "",
                        node.level,
                        source_module,
                    )
                else:
                    module_name = node.module or ""
                    if node.level > 0:
                        resolved_module = self._resolve_relative_import(
                            module_name,
                            node.level,
                            source_module,
                        )
                    else:
                        resolved_module = module_name

                names = [alias.name for alias in (node.names or []) if alias.name != "*"]

                target_path = self._resolve_import(
                    resolved_module,
                    source_module,
                    module_paths,
                    project_root,
                )

                # If the target is a package (__init__.py), imported names
                # might be submodules. Try resolving each name as pkg.name.
                is_package = target_path is not None and target_path.endswith("__init__.py")
                if is_package and names:
                    for name in names:
                        sub_module = f"{resolved_module}.{name}" if resolved_module else name
                        sub_path = self._resolve_import(
                            sub_module,
                            source_module,
                            module_paths,
                            project_root,
                        )
                        if sub_path is not None:
                            edges.append(
                                ImportEdge(
                                    source=source_rel,
                                    target=sub_path,
                                    import_type=import_type,
                                    line=node.lineno,
                                    names=[name],
                                )
                            )
                        else:
                            # Name is an attribute of the package, not a submodule
                            # target_path is non-None here because is_package guards this block
                            edges.append(
                                ImportEdge(
                                    source=source_rel,
                                    target=str(target_path),
                                    import_type=import_type,
                                    line=node.lineno,
                                    names=[name],
                                )
                            )
                elif target_path is not None:
                    edges.append(
                        ImportEdge(
                            source=source_rel,
                            target=target_path,
                            import_type=import_type,
                            line=node.lineno,
                            names=names,
                        )
                    )
                else:
                    # Module didn't resolve at all. Try imported names as
                    # submodules (e.g. `from . import beta` resolving to
                    # a package that has no __init__.py).
                    resolved_any = False
                    for name in names:
                        sub_module = f"{resolved_module}.{name}" if resolved_module else name
                        sub_path = self._resolve_import(
                            sub_module,
                            source_module,
                            module_paths,
                            project_root,
                        )
                        if sub_path is not None:
                            edges.append(
                                ImportEdge(
                                    source=source_rel,
                                    target=sub_path,
                                    import_type=import_type,
                                    line=node.lineno,
                                    names=[name],
                                )
                            )
                            resolved_any = True

                    if not resolved_any:
                        top_level = resolved_module.split(".")[0] if resolved_module else ""
                        if top_level and top_level not in self.STDLIB_TOP_LEVEL:
                            externals.append(resolved_module)

        return edges, externals

    def _classify_import_type(
        self,
        node: ast.Import | ast.ImportFrom,
        type_checking_ranges: list[tuple[int, int]],
        conditional_ranges: list[tuple[int, int]],
        tree: ast.Module,
    ) -> str:
        """Classify an import as runtime, type_checking, conditional, or lazy."""
        line = node.lineno

        # Check TYPE_CHECKING guard
        for start, end in type_checking_ranges:
            if start <= line <= end:
                return "type_checking"

        # Check try/except ImportError
        for start, end in conditional_ranges:
            if start <= line <= end:
                return "conditional"

        # Check if inside a function body (lazy import)
        if self._is_inside_function(node, tree):
            return "lazy"

        return "runtime"

    def _find_type_checking_ranges(
        self,
        tree: ast.Module,
    ) -> list[tuple[int, int]]:
        """Find line ranges of `if TYPE_CHECKING:` blocks."""
        ranges: list[tuple[int, int]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            if self._is_type_checking_guard(node.test):
                start = node.lineno
                end = self._block_end_line(node)
                ranges.append((start, end))
        return ranges

    def _find_conditional_import_ranges(
        self,
        tree: ast.Module,
    ) -> list[tuple[int, int]]:
        """Find line ranges of try/except ImportError blocks."""
        ranges: list[tuple[int, int]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            has_import_error = any(
                self._handler_catches_import_error(handler) for handler in node.handlers
            )
            if has_import_error:
                start = node.lineno
                end = self._block_end_line(node)
                ranges.append((start, end))
        return ranges

    @staticmethod
    def _is_type_checking_guard(test: ast.expr) -> bool:
        """Check if the test expression is `TYPE_CHECKING`."""
        if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
            return True
        return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"

    @staticmethod
    def _handler_catches_import_error(handler: ast.ExceptHandler) -> bool:
        """Check if an except handler catches ImportError or ModuleNotFoundError."""
        if handler.type is None:
            return True
        if isinstance(handler.type, ast.Name):
            return handler.type.id in {"ImportError", "ModuleNotFoundError"}
        if isinstance(handler.type, ast.Tuple):
            return any(
                isinstance(elt, ast.Name) and elt.id in {"ImportError", "ModuleNotFoundError"}
                for elt in handler.type.elts
            )
        return False

    @staticmethod
    def _block_end_line(node: ast.AST) -> int:
        """Get the end line of an AST node, with fallback."""
        if hasattr(node, "end_lineno") and node.end_lineno is not None:
            return int(node.end_lineno)
        return int(getattr(node, "lineno", 0))

    @staticmethod
    def _is_inside_function(
        node: ast.AST,
        tree: ast.Module,
    ) -> bool:
        """Check if an AST node is inside a function body (not at module level)."""
        # Walk parents by iterating all function defs and checking line ranges
        for parent in ast.walk(tree):
            if not isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            parent_start = parent.lineno
            parent_end = getattr(parent, "end_lineno", None) or parent_start
            node_line = getattr(node, "lineno", 0)
            if parent_start < node_line <= parent_end:
                return True
        return False

    # ------------------------------------------------------------------
    # Module resolution
    # ------------------------------------------------------------------

    def _resolve_import(
        self,
        import_name: str,
        source_module: str,
        module_paths: dict[str, str],
        project_root: Path,
    ) -> str | None:
        """Resolve a dotted import name to a relative file path, or None."""
        if not import_name:
            return None

        # Direct match: import_name is a known module
        if import_name in module_paths:
            return module_paths[import_name]

        # Try as a package: import_name might resolve to __init__.py
        init_name = import_name + ".__init__"
        if init_name in module_paths:
            return module_paths[init_name]

        # Try parent: `from pkg.mod import name` where pkg.mod is a module
        parts = import_name.rsplit(".", 1)
        if len(parts) > 1:
            parent = parts[0]
            if parent in module_paths:
                return module_paths[parent]
            parent_init = parent + ".__init__"
            if parent_init in module_paths:
                return module_paths[parent_init]

        return None

    @staticmethod
    def _resolve_relative_import(
        module_name: str,
        level: int,
        source_module: str,
    ) -> str:
        """Resolve a relative import to an absolute dotted name."""
        parts = source_module.split(".")
        # Go up `level` levels from the source module's package
        # level=1 means current package, level=2 means parent package, etc.
        base_parts = parts[:-level] if len(parts) >= level else []

        if module_name:
            return ".".join([*base_parts, module_name]) if base_parts else module_name
        return ".".join(base_parts) if base_parts else ""

    @staticmethod
    def _path_to_module_name(rel_path: Path) -> str:
        """Convert a relative file path to a dotted module name."""
        parts = list(rel_path.parts)
        # Remove .py suffix from the last part
        if parts and parts[-1].endswith(".py"):
            parts[-1] = parts[-1][:-3]
        return ".".join(parts)
