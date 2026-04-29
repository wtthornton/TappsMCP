"""Public API surface detector for source modules (Python + multi-language)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import BaseModel

from docs_mcp.extractors.docstring_parser import parse_docstring

if TYPE_CHECKING:
    from pathlib import Path

    from docs_mcp.extractors.base import Extractor
    from docs_mcp.extractors.models import ClassInfo, ConstantInfo, FunctionInfo, ModuleInfo


class APIFunction(BaseModel):
    """Public function in the API surface."""

    name: str
    signature: str
    line: int
    docstring_present: bool = False
    docstring_summary: str = ""
    is_async: bool = False
    decorators: list[str] = []
    parameters: list[dict[str, str | None]] = []
    return_type: str | None = None


class APIClass(BaseModel):
    """Public class in the API surface."""

    name: str
    line: int
    bases: list[str] = []
    docstring_present: bool = False
    docstring_summary: str = ""
    method_count: int = 0
    public_methods: list[str] = []
    decorators: list[str] = []


class APIConstant(BaseModel):
    """Public constant in the API surface."""

    name: str
    line: int
    type: str | None = None
    value: str | None = None


class APISurface(BaseModel):
    """Complete public API surface for a module."""

    source_path: str
    functions: list[APIFunction] = []
    classes: list[APIClass] = []
    constants: list[APIConstant] = []
    type_aliases: list[str] = []
    re_exports: list[str] = []
    all_exports: list[str] | None = None
    coverage: float = 0.0
    missing_docs: list[str] = []
    total_public: int = 0


# Regex to detect relative imports: from .something import name
_RELATIVE_IMPORT_RE = re.compile(r"^from\s+\.[\w.]*\s+import\s+(.+)$")


class APISurfaceAnalyzer:
    """Detects public API surface of source modules.

    Supports Python (AST-based), TypeScript, Go, Rust, and Java
    (tree-sitter-based, when installed). Uses the dispatcher to
    auto-select the best extractor for each file.
    """

    def __init__(self, extractor: Extractor | None = None) -> None:
        self._extractor = extractor

    def _get_extractor(self, file_path: Path) -> Extractor:
        """Return the extractor for *file_path*, falling back to dispatcher."""
        if self._extractor is not None:
            return self._extractor
        from docs_mcp.extractors.dispatcher import get_extractor

        return get_extractor(file_path)

    def analyze(
        self,
        file_path: Path,
        *,
        project_root: Path | None = None,
        depth: str = "public",
        include_types: bool = True,
    ) -> APISurface:
        """Analyze the public API surface of a source file.

        Supports Python (.py), TypeScript (.ts/.tsx), Go (.go), Rust (.rs),
        and Java (.java). The appropriate extractor is selected automatically
        via the dispatcher when no explicit extractor was provided.

        Args:
            file_path: Path to the source file.
            project_root: Optional project root for relative paths.
            depth: Visibility depth - "public", "protected", or "all".
            include_types: Whether to include type alias detection.

        Returns:
            An APISurface describing the module's public API.
        """
        if not file_path.exists():
            return APISurface(source_path=str(file_path))

        extractor = self._get_extractor(file_path)
        module_info = extractor.extract(file_path, project_root=project_root)
        all_exports = module_info.all_exports

        # Build API surface components
        functions = self._build_functions(module_info.functions, all_exports, depth)
        classes = self._build_classes(module_info.classes, all_exports, depth)
        constants = self._build_constants(module_info.constants, all_exports, depth)
        type_aliases = (
            self._detect_type_aliases(module_info, all_exports, depth) if include_types else []
        )
        re_exports = self._detect_re_exports(module_info, file_path)

        # Calculate coverage
        all_public_names: list[str] = (
            [f.name for f in functions] + [c.name for c in classes] + [c.name for c in constants]
        )
        total_public = len(all_public_names)

        documented_names = {f.name for f in functions if f.docstring_present} | {
            c.name for c in classes if c.docstring_present
        }
        # Constants don't have docstrings, so they don't count for coverage
        docstring_eligible = [f.name for f in functions] + [c.name for c in classes]
        eligible_count = len(docstring_eligible)

        if eligible_count > 0:
            coverage = len(documented_names) / eligible_count
        else:
            coverage = 1.0 if total_public > 0 else 0.0

        missing_docs = [n for n in docstring_eligible if n not in documented_names]

        return APISurface(
            source_path=module_info.path,
            functions=functions,
            classes=classes,
            constants=constants,
            type_aliases=type_aliases,
            re_exports=re_exports,
            all_exports=all_exports,
            coverage=coverage,
            missing_docs=missing_docs,
            total_public=total_public,
        )

    def analyze_from_source(
        self,
        file_path: "Path",
        source: str,
        *,
        project_root: "Path | None" = None,
        depth: str = "public",
        include_types: bool = True,
    ) -> APISurface:
        """Analyze API surface from pre-read source content (avoids file I/O).

        Falls back to the normal file-based ``analyze`` path for non-Python files
        where the extractor does not support pre-read source.
        """
        from docs_mcp.extractors.python import PythonExtractor

        extractor = self._get_extractor(file_path)
        if isinstance(extractor, PythonExtractor):
            module_info = extractor.extract_from_source(source, file_path, project_root=project_root)
        else:
            module_info = extractor.extract(file_path, project_root=project_root)

        all_exports = module_info.all_exports
        functions = self._build_functions(module_info.functions, all_exports, depth)
        classes = self._build_classes(module_info.classes, all_exports, depth)
        constants = self._build_constants(module_info.constants, all_exports, depth)
        type_aliases = (
            self._detect_type_aliases(module_info, all_exports, depth) if include_types else []
        )
        re_exports = self._detect_re_exports(module_info, file_path)

        all_public_names: list[str] = (
            [f.name for f in functions] + [c.name for c in classes] + [c.name for c in constants]
        )
        total_public = len(all_public_names)
        documented_names = {f.name for f in functions if f.docstring_present} | {
            c.name for c in classes if c.docstring_present
        }
        docstring_eligible = [f.name for f in functions] + [c.name for c in classes]
        eligible_count = len(docstring_eligible)
        coverage = (
            len(documented_names) / eligible_count
            if eligible_count > 0
            else (1.0 if total_public > 0 else 0.0)
        )
        missing_docs = [n for n in docstring_eligible if n not in documented_names]

        return APISurface(
            source_path=module_info.path,
            functions=functions,
            classes=classes,
            constants=constants,
            type_aliases=type_aliases,
            re_exports=re_exports,
            all_exports=all_exports,
            coverage=coverage,
            missing_docs=missing_docs,
            total_public=total_public,
        )

    def _is_visible(self, name: str, all_exports: list[str] | None, depth: str) -> bool:
        """Determine if a name should be included based on visibility rules."""
        if depth == "all":
            return True

        if all_exports is not None:
            return name in all_exports

        # No __all__ defined: use naming conventions
        if depth == "protected":
            # Include public + single underscore, exclude dunder and double underscore private
            return not (name.startswith("__") and name.endswith("__"))

        # depth == "public"
        return self._is_public(name, all_exports)

    def _is_public(self, name: str, all_exports: list[str] | None) -> bool:
        """Determine if a name is part of the public API."""
        if all_exports is not None:
            return name in all_exports
        return not name.startswith("_")

    def _is_protected(self, name: str) -> bool:
        """Check if a name is protected (single underscore prefix)."""
        return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))

    def _build_functions(
        self,
        functions: list[FunctionInfo],
        all_exports: list[str] | None,
        depth: str,
    ) -> list[APIFunction]:
        """Build APIFunction list from extracted functions."""
        result: list[APIFunction] = []
        for func in functions:
            if not self._is_visible(func.name, all_exports, depth):
                continue

            docstring_summary = ""
            has_docstring = func.docstring is not None and func.docstring.strip() != ""
            if has_docstring and func.docstring is not None:
                parsed = parse_docstring(func.docstring)
                docstring_summary = parsed.summary

            params: list[dict[str, str | None]] = [
                {
                    "name": p.name,
                    "type": p.annotation,
                    "default": p.default,
                }
                for p in func.parameters
            ]

            result.append(
                APIFunction(
                    name=func.name,
                    signature=func.signature,
                    line=func.line,
                    docstring_present=has_docstring,
                    docstring_summary=docstring_summary,
                    is_async=func.is_async,
                    decorators=[d.name for d in func.decorators],
                    parameters=params,
                    return_type=func.return_annotation,
                )
            )
        return result

    def _build_classes(
        self,
        classes: list[ClassInfo],
        all_exports: list[str] | None,
        depth: str,
    ) -> list[APIClass]:
        """Build APIClass list from extracted classes."""
        result: list[APIClass] = []
        for cls in classes:
            if not self._is_visible(cls.name, all_exports, depth):
                continue

            has_docstring = cls.docstring is not None and cls.docstring.strip() != ""
            docstring_summary = ""
            if has_docstring and cls.docstring is not None:
                parsed = parse_docstring(cls.docstring)
                docstring_summary = parsed.summary

            public_methods = [m.name for m in cls.methods if not m.name.startswith("_")]

            result.append(
                APIClass(
                    name=cls.name,
                    line=cls.line,
                    bases=cls.bases,
                    docstring_present=has_docstring,
                    docstring_summary=docstring_summary,
                    method_count=len(cls.methods),
                    public_methods=public_methods,
                    decorators=[d.name for d in cls.decorators],
                )
            )
        return result

    def _build_constants(
        self,
        constants: list[ConstantInfo],
        all_exports: list[str] | None,
        depth: str,
    ) -> list[APIConstant]:
        """Build APIConstant list from extracted constants."""
        result: list[APIConstant] = []
        for const in constants:
            # Skip __all__ and other dunder assignments
            if const.name.startswith("__") and const.name.endswith("__"):
                continue
            if not self._is_visible(const.name, all_exports, depth):
                continue

            result.append(
                APIConstant(
                    name=const.name,
                    line=const.line,
                    type=const.annotation,
                    value=const.value,
                )
            )
        return result

    def _detect_type_aliases(
        self,
        module_info: ModuleInfo,
        all_exports: list[str] | None,
        depth: str,
    ) -> list[str]:
        """Detect type alias assignments (e.g., MyType = Union[int, str])."""
        aliases: list[str] = []
        for const in module_info.constants:
            if not self._is_visible(const.name, all_exports, depth):
                continue
            # Heuristic: annotated with TypeAlias or assigned to a typing construct
            is_type_alias = const.annotation and "TypeAlias" in const.annotation
            is_typing_construct = const.value and any(
                kw in const.value for kw in ("Union[", "Optional[", "Literal[", "TypeVar(")
            )
            if is_type_alias or is_typing_construct:
                aliases.append(const.name)
        return aliases

    def _detect_re_exports(
        self,
        module_info: ModuleInfo,
        file_path: Path,
    ) -> list[str]:
        """Detect names re-exported from __init__.py files."""
        if file_path.name != "__init__.py":
            return []

        re_exported: list[str] = []
        for imp in module_info.imports:
            match = _RELATIVE_IMPORT_RE.match(imp)
            if match:
                names_str = match.group(1)
                # Parse comma-separated imported names
                for name_part in names_str.split(","):
                    name = name_part.strip()
                    # Handle "name as alias" — use the alias
                    if " as " in name:
                        name = name.split(" as ")[-1].strip()
                    if name and not name.startswith("_"):
                        re_exported.append(name)
        return re_exported
