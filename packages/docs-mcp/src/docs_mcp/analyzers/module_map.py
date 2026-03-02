"""Module structure analyzer that builds a hierarchical map of a Python project."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import structlog

from docs_mcp.analyzers.models import ModuleMap, ModuleNode
from docs_mcp.extractors.models import ModuleInfo
from docs_mcp.extractors.python import PythonExtractor

logger: structlog.stdlib.BoundLogger = structlog.get_logger()  # type: ignore[assignment]


class ModuleMapAnalyzer:
    """Walks a project directory and builds a hierarchical module map."""

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
        }
    )

    SKIP_SUFFIXES: ClassVar[frozenset[str]] = frozenset({".egg-info"})

    def __init__(self, extractor: PythonExtractor | None = None) -> None:
        self._extractor = extractor or PythonExtractor()

    def analyze(
        self,
        project_root: Path,
        *,
        depth: int = 10,
        include_private: bool = False,
        source_dirs: list[str] | None = None,
    ) -> ModuleMap:
        """Build a complete module map of the project.

        Args:
            project_root: Root directory of the project.
            depth: Maximum directory depth to traverse (0 = root only).
            include_private: Whether to include modules starting with ``_``
                (``__init__.py`` is always included regardless).
            source_dirs: Explicit source directories relative to project_root.
                When ``None``, auto-detects by looking for ``src/`` layout or
                directories containing Python files.
        """
        project_root = project_root.resolve()
        roots = self._resolve_source_dirs(project_root, source_dirs)

        module_tree: list[ModuleNode] = []
        for src_dir in sorted(roots):
            nodes = self._walk_directory(
                src_dir,
                project_root=project_root,
                current_depth=0,
                max_depth=depth,
                include_private=include_private,
            )
            module_tree.extend(nodes)

        module_tree.sort(key=lambda n: n.name)

        total_modules = 0
        total_packages = 0
        total_public_api = 0
        entry_points: list[str] = []
        self._aggregate(
            module_tree,
            entry_points=entry_points,
            counts={"modules": 0, "packages": 0, "public_api": 0},
        )
        # Read aggregated counts back
        counts: dict[str, int] = {"modules": 0, "packages": 0, "public_api": 0}
        self._aggregate(module_tree, entry_points=[], counts=counts)
        total_modules = counts["modules"]
        total_packages = counts["packages"]
        total_public_api = counts["public_api"]

        # Collect entry points
        entry_points_list: list[str] = []
        self._collect_entry_points(module_tree, entry_points_list)

        project_name = project_root.name

        return ModuleMap(
            project_root=str(project_root),
            project_name=project_name,
            module_tree=module_tree,
            entry_points=entry_points_list,
            total_modules=total_modules,
            total_packages=total_packages,
            public_api_count=total_public_api,
        )

    # ------------------------------------------------------------------
    # Source directory resolution
    # ------------------------------------------------------------------

    def _resolve_source_dirs(
        self,
        project_root: Path,
        source_dirs: list[str] | None,
    ) -> list[Path]:
        """Resolve source directories to scan."""
        if source_dirs is not None:
            resolved: list[Path] = []
            for sd in source_dirs:
                candidate = project_root / sd
                if candidate.is_dir():
                    resolved.append(candidate)
                else:
                    logger.warning("source_dir_not_found", path=sd)
            return resolved if resolved else [project_root]

        # Auto-detect: prefer src/ layout
        src_dir = project_root / "src"
        if src_dir.is_dir():
            # Look for package directories inside src/
            packages = [
                d
                for d in src_dir.iterdir()
                if d.is_dir()
                and not self._should_skip_dir(d)
                and (d / "__init__.py").exists()
            ]
            if packages:
                return packages
            # src/ exists but no packages — scan src/ itself
            return [src_dir]

        # Fall back to project root
        return [project_root]

    # ------------------------------------------------------------------
    # Directory walking
    # ------------------------------------------------------------------

    def _walk_directory(
        self,
        directory: Path,
        *,
        project_root: Path,
        current_depth: int,
        max_depth: int,
        include_private: bool,
    ) -> list[ModuleNode]:
        """Recursively walk a directory and build ModuleNode list."""
        if current_depth > max_depth:
            return []

        try:
            entries = sorted(directory.iterdir(), key=lambda p: p.name)
        except OSError:
            logger.warning("dir_read_error", path=str(directory))
            return []

        nodes: list[ModuleNode] = []

        # Separate files and subdirectories
        py_files: list[Path] = []
        subdirs: list[Path] = []

        for entry in entries:
            if entry.is_file() and entry.suffix == ".py":
                py_files.append(entry)
            elif entry.is_dir() and not self._should_skip_dir(entry):
                subdirs.append(entry)

        # Process .py files (non-__init__)
        for py_file in py_files:
            if py_file.name == "__init__.py":
                continue
            if not include_private and py_file.stem.startswith("_"):
                continue
            node = self._build_file_node(py_file, project_root)
            if node is not None:
                nodes.append(node)

        # Process subdirectories
        for subdir in subdirs:
            if not include_private and subdir.name.startswith("_"):
                continue
            init_file = subdir / "__init__.py"
            if init_file.exists():
                # This is a package
                node = self._build_package_node(
                    subdir,
                    project_root=project_root,
                    current_depth=current_depth,
                    max_depth=max_depth,
                    include_private=include_private,
                )
                if node is not None:
                    nodes.append(node)
            else:
                # Not a package, but might contain .py files - recurse
                child_nodes = self._walk_directory(
                    subdir,
                    project_root=project_root,
                    current_depth=current_depth + 1,
                    max_depth=max_depth,
                    include_private=include_private,
                )
                nodes.extend(child_nodes)

        nodes.sort(key=lambda n: n.name)
        return nodes

    # ------------------------------------------------------------------
    # Node building
    # ------------------------------------------------------------------

    def _build_file_node(
        self,
        file_path: Path,
        project_root: Path,
    ) -> ModuleNode | None:
        """Build a ModuleNode for a single .py file."""
        try:
            info = self._extractor.extract(file_path, project_root=project_root)
        except Exception:
            logger.warning("extract_error", path=str(file_path))
            return None

        try:
            size_bytes = file_path.stat().st_size
        except OSError:
            size_bytes = 0

        rel_path = self._relative_path(file_path, project_root)
        public_count = self._count_public_names(info)

        return ModuleNode(
            name=file_path.stem,
            path=rel_path,
            is_package=False,
            public_api_count=public_count,
            module_docstring=info.docstring,
            has_main=info.has_main_block,
            all_exports=info.all_exports,
            size_bytes=size_bytes,
            function_count=len(info.functions),
            class_count=len(info.classes),
        )

    def _build_package_node(
        self,
        directory: Path,
        *,
        project_root: Path,
        current_depth: int,
        max_depth: int,
        include_private: bool,
    ) -> ModuleNode | None:
        """Build a ModuleNode for a package directory (has __init__.py)."""
        init_file = directory / "__init__.py"
        try:
            info = self._extractor.extract(init_file, project_root=project_root)
        except Exception:
            logger.warning("extract_error", path=str(init_file))
            info = ModuleInfo(path=self._relative_path(init_file, project_root))

        try:
            size_bytes = init_file.stat().st_size
        except OSError:
            size_bytes = 0

        # Recurse into package contents
        submodules = self._walk_directory(
            directory,
            project_root=project_root,
            current_depth=current_depth + 1,
            max_depth=max_depth,
            include_private=include_private,
        )

        rel_path = self._relative_path(directory, project_root)
        public_count = self._count_public_names(info)

        return ModuleNode(
            name=directory.name,
            path=rel_path,
            is_package=True,
            submodules=submodules,
            public_api_count=public_count,
            module_docstring=info.docstring,
            has_main=info.has_main_block,
            all_exports=info.all_exports,
            size_bytes=size_bytes,
            function_count=len(info.functions),
            class_count=len(info.classes),
        )

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _aggregate(
        self,
        nodes: list[ModuleNode],
        *,
        entry_points: list[str],
        counts: dict[str, int],
    ) -> None:
        """Recursively aggregate statistics from the module tree."""
        for node in nodes:
            if node.is_package:
                counts["packages"] += 1
            else:
                counts["modules"] += 1
            counts["public_api"] += node.public_api_count
            if node.has_main or node.name == "__main__":
                entry_points.append(node.path)
            self._aggregate(
                node.submodules, entry_points=entry_points, counts=counts
            )

    def _collect_entry_points(
        self,
        nodes: list[ModuleNode],
        result: list[str],
    ) -> None:
        """Collect all entry point paths from the module tree."""
        for node in nodes:
            if node.has_main or node.name == "__main__":
                result.append(node.path)
            self._collect_entry_points(node.submodules, result)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _should_skip_dir(self, directory: Path) -> bool:
        """Check if a directory should be skipped during traversal."""
        name = directory.name
        if name in self.SKIP_DIRS:
            return True
        if name.startswith("."):
            return True
        if any(name.endswith(suffix) for suffix in self.SKIP_SUFFIXES):
            return True
        return False

    @staticmethod
    def _count_public_names(info: ModuleInfo) -> int:
        """Count public names exported by a module.

        If ``__all__`` is defined, its length is the public API count.
        Otherwise, count functions and classes not starting with ``_``.
        """
        if info.all_exports is not None:
            return len(info.all_exports)
        count = 0
        for func in info.functions:
            if not func.name.startswith("_"):
                count += 1
        for cls in info.classes:
            if not cls.name.startswith("_"):
                count += 1
        return count

    @staticmethod
    def _relative_path(path: Path, project_root: Path) -> str:
        """Make a path relative to the project root."""
        try:
            return str(path.relative_to(project_root)).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")
