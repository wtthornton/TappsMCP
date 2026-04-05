"""Per-module API reference documentation generator.

Generates structured API reference docs from Python source files using
the existing PythonExtractor and docstring parser infrastructure.
Supports markdown, mkdocs, and Sphinx RST output formats.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, ClassVar

import structlog
from pydantic import BaseModel

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Skip directories when scanning
# ---------------------------------------------------------------------------

_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        "__pycache__",
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

_MAX_DIR_FILES = 50
_MAX_EXAMPLES = 5
_MAX_SNIPPET_LINES = 20

# Logger constant patterns to filter from API docs.
_LOGGER_PATTERNS: frozenset[str] = frozenset({
    "logger",
    "log",
    "LOG",
    "LOGGER",
})

# Noise constant name patterns (exact matches) to filter.
_NOISE_CONSTANTS: frozenset[str] = frozenset({
    "__all__",
    "__version__",
})

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class APIDocParam(BaseModel):
    """A documented parameter."""

    name: str
    type: str = ""
    description: str = ""
    default: str | None = None


class APIDocFunction(BaseModel):
    """A documented function or method."""

    name: str
    signature: str
    description: str = ""
    params: list[APIDocParam] = []
    returns: str = ""
    return_type: str = ""
    raises: list[str] = []
    examples: list[str] = []
    decorators: list[str] = []
    is_async: bool = False
    is_property: bool = False
    is_classmethod: bool = False
    is_staticmethod: bool = False
    line: int = 0


class APIDocClass(BaseModel):
    """A documented class."""

    name: str
    bases: list[str] = []
    description: str = ""
    methods: list[APIDocFunction] = []
    class_variables: list[APIDocParam] = []
    decorators: list[str] = []
    line: int = 0


class APIDocModule(BaseModel):
    """A documented module."""

    name: str
    source_path: str = ""
    docstring: str = ""
    functions: list[APIDocFunction] = []
    classes: list[APIDocClass] = []
    constants: list[APIDocParam] = []
    coverage: float = 0.0
    is_reexport: bool = False
    total_public: int = 0
    documented_count: int = 0
    missing_returns: int = 0
    missing_examples: int = 0


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class APIDocGenerator:
    """Generates per-module API reference documentation from Python sources.

    Uses PythonExtractor for AST-based extraction and the docstring parser
    for structured docstring parsing. Supports markdown, mkdocs, and
    Sphinx RST output formats with configurable depth filtering.
    """

    VALID_FORMATS: ClassVar[frozenset[str]] = frozenset(
        {
            "markdown",
            "mkdocs",
            "sphinx_rst",
        }
    )
    VALID_DEPTHS: ClassVar[frozenset[str]] = frozenset(
        {
            "public",
            "protected",
            "all",
        }
    )

    def generate(
        self,
        source_path: Path,
        *,
        project_root: Path,
        output_format: str = "markdown",
        depth: str = "public",
        include_examples: bool = True,
        include_private: bool = False,
    ) -> str:
        """Generate API reference documentation for a file or directory.

        Args:
            source_path: Path to a .py file or directory of .py files.
            project_root: Root directory of the project.
            output_format: Output format - ``"markdown"``, ``"mkdocs"``,
                or ``"sphinx_rst"``.
            depth: Symbol visibility filter - ``"public"`` (no underscore
                prefix except __init__), ``"protected"`` (include single
                underscore), or ``"all"`` (everything).
            include_examples: Whether to search tests for usage examples.
            include_private: When True, include private (``_prefix``)
                functions that have docstrings even in ``"public"`` depth.

        Returns:
            The rendered API documentation as a string, or empty string
            on error.
        """
        if output_format not in self.VALID_FORMATS:
            logger.warning("invalid_format", format=output_format)
            return ""
        if depth not in self.VALID_DEPTHS:
            logger.warning("invalid_depth", depth=depth)
            return ""

        try:
            source_path = source_path.resolve()
            project_root = project_root.resolve()
        except Exception:
            logger.debug("path_resolution_failed", exc_info=True)
            return ""

        if source_path.is_dir():
            return self._generate_directory(
                source_path,
                project_root=project_root,
                output_format=output_format,
                depth=depth,
                include_examples=include_examples,
                include_private=include_private,
            )

        if source_path.is_file() and source_path.suffix == ".py":
            return self._generate_file(
                source_path,
                project_root=project_root,
                output_format=output_format,
                depth=depth,
                include_examples=include_examples,
                include_private=include_private,
            )

        logger.warning("unsupported_source", path=str(source_path))
        return ""

    # ------------------------------------------------------------------
    # Directory handling
    # ------------------------------------------------------------------

    def _generate_directory(
        self,
        dir_path: Path,
        *,
        project_root: Path,
        output_format: str,
        depth: str,
        include_examples: bool,
        include_private: bool = False,
    ) -> str:
        """Generate docs for all .py files in a directory (recursively)."""
        py_files = self._collect_py_files(dir_path)
        if not py_files:
            return ""

        parts: list[str] = []
        for file_path in py_files[:_MAX_DIR_FILES]:
            result = self._generate_file(
                file_path,
                project_root=project_root,
                output_format=output_format,
                depth=depth,
                include_examples=include_examples,
                include_private=include_private,
            )
            if result:
                parts.append(result)

        if len(py_files) > _MAX_DIR_FILES:
            logger.info(
                "directory_file_limit_reached",
                total=len(py_files),
                limit=_MAX_DIR_FILES,
            )

        return "\n\n---\n\n".join(parts)

    @staticmethod
    def _collect_py_files(dir_path: Path) -> list[Path]:
        """Collect all .py files in a directory, skipping excluded dirs."""
        py_files: list[Path] = []
        for item in sorted(dir_path.rglob("*.py")):
            # Skip files inside excluded directories
            skip = False
            for parent in item.relative_to(dir_path).parents:
                if parent.name in _SKIP_DIRS:
                    skip = True
                    break
            if skip:
                continue
            py_files.append(item)
        return py_files

    # ------------------------------------------------------------------
    # Single-file handling
    # ------------------------------------------------------------------

    def _generate_file(
        self,
        file_path: Path,
        *,
        project_root: Path,
        output_format: str,
        depth: str,
        include_examples: bool,
        include_private: bool = False,
    ) -> str:
        """Generate docs for a single .py file."""
        try:
            module = self._extract_module(
                file_path,
                depth,
                include_examples,
                project_root,
                include_private=include_private,
            )
        except Exception:
            logger.debug(
                "module_extraction_failed",
                path=str(file_path),
                exc_info=True,
            )
            return ""

        if output_format == "mkdocs":
            return self._render_mkdocs(module)
        if output_format == "sphinx_rst":
            return self._render_sphinx_rst(module)
        return self._render_markdown(module)

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def _extract_module(
        self,
        file_path: Path,
        depth: str,
        include_examples: bool,
        project_root: Path,
        *,
        include_private: bool = False,
    ) -> APIDocModule:
        """Extract structured module information using PythonExtractor.

        Args:
            file_path: Path to the Python source file.
            depth: Visibility depth filter.
            include_examples: Whether to search for usage examples.
            project_root: Project root for relative path computation.
            include_private: When True, include private functions with
                docstrings even in ``"public"`` depth.

        Returns:
            An ``APIDocModule`` populated from the source file.
        """
        from docs_mcp.extractors.docstring_parser import parse_docstring
        from docs_mcp.extractors.python import PythonExtractor

        extractor = PythonExtractor()
        module_info = extractor.extract(file_path, project_root=project_root)

        # Derive module name from relative path
        try:
            rel = file_path.relative_to(project_root)
            module_name = str(rel).replace("\\", "/").replace("/", ".")
            if module_name.endswith(".py"):
                module_name = module_name[:-3]
            if module_name.endswith(".__init__"):
                module_name = module_name[:-9]
        except ValueError:
            module_name = file_path.stem

        # Track items for coverage calculation
        total_items = 0
        documented_items = 0

        # --- Functions ---
        functions: list[APIDocFunction] = []
        for func_info in module_info.functions:
            if not self._should_include_symbol(
                func_info.name, depth, include_private, func_info.docstring,
            ):
                continue
            total_items += 1
            parsed = parse_docstring(func_info.docstring or "")
            if func_info.docstring:
                documented_items += 1

            params = self._convert_params(func_info, parsed)
            returns_text = _format_returns(parsed)

            raises_list = [
                f"{r.exception}: {r.description}" if r.description else r.exception
                for r in parsed.raises
            ]

            examples: list[str] = [ex.code for ex in parsed.examples]
            if include_examples and not examples:
                examples = self._find_examples(func_info.name, project_root)

            decorators = [d.name for d in func_info.decorators]

            functions.append(
                APIDocFunction(
                    name=func_info.name,
                    signature=func_info.signature,
                    description=_full_description(parsed),
                    params=params,
                    returns=returns_text,
                    return_type=func_info.return_annotation or "",
                    raises=raises_list,
                    examples=examples,
                    decorators=decorators,
                    is_async=func_info.is_async,
                    is_property=func_info.is_property,
                    is_classmethod=func_info.is_classmethod,
                    is_staticmethod=func_info.is_staticmethod,
                    line=func_info.line,
                )
            )

        # --- Classes ---
        classes: list[APIDocClass] = []
        for class_info in module_info.classes:
            if not self._should_include(class_info.name, depth):
                continue
            total_items += 1
            parsed_cls = parse_docstring(class_info.docstring or "")
            if class_info.docstring:
                documented_items += 1

            methods, m_total, m_documented = self._extract_class_methods(
                class_info,
                depth,
                include_examples,
                project_root,
                parse_docstring,
                include_private=include_private,
            )
            total_items += m_total
            documented_items += m_documented

            class_vars: list[APIDocParam] = []
            for cv in class_info.class_variables:
                if not self._should_include(cv.name, depth):
                    continue
                class_vars.append(
                    APIDocParam(
                        name=cv.name,
                        type=cv.annotation or "",
                        default=cv.value,
                    )
                )

            decorators_cls = [d.name for d in class_info.decorators]

            classes.append(
                APIDocClass(
                    name=class_info.name,
                    bases=class_info.bases,
                    description=_full_description(parsed_cls),
                    methods=methods,
                    class_variables=class_vars,
                    decorators=decorators_cls,
                    line=class_info.line,
                )
            )

        # --- Constants (with noise filtering) ---
        constants: list[APIDocParam] = []
        for const_info in module_info.constants:
            if not self._should_include(const_info.name, depth):
                continue
            if _is_noise_constant(const_info.name, const_info.value):
                continue
            total_items += 1
            # Constants don't have docstrings, but if annotated, count it
            if const_info.annotation or const_info.value:
                documented_items += 1
            constants.append(
                APIDocParam(
                    name=const_info.name,
                    type=const_info.annotation or "",
                    default=const_info.value,
                )
            )

        coverage = (documented_items / total_items * 100.0) if total_items > 0 else 0.0

        # Detect re-export modules (__init__.py with no original definitions)
        is_reexport = _is_reexport_module(file_path, module_info)

        # Quality metrics
        missing_returns = sum(
            1 for f in functions if not f.returns and not f.return_type
        )
        missing_examples = sum(1 for f in functions if not f.examples)

        return APIDocModule(
            name=module_name,
            source_path=module_info.path,
            docstring=module_info.docstring or "",
            functions=functions,
            classes=classes,
            constants=constants,
            coverage=round(coverage, 1),
            is_reexport=is_reexport,
            total_public=total_items,
            documented_count=documented_items,
            missing_returns=missing_returns,
            missing_examples=missing_examples,
        )

    def _extract_class_methods(
        self,
        class_info: object,
        depth: str,
        include_examples: bool,
        project_root: Path,
        parse_docstring_fn: object,
        *,
        include_private: bool = False,
    ) -> tuple[list[APIDocFunction], int, int]:
        """Extract methods from a ClassInfo into APIDocFunction list.

        Returns:
            Tuple of (methods, total_items_counted, documented_items_counted).
        """
        from docs_mcp.extractors.models import ClassInfo

        if not isinstance(class_info, ClassInfo) or not callable(parse_docstring_fn):
            return [], 0, 0
        total = 0
        documented = 0
        methods: list[APIDocFunction] = []

        for method_info in class_info.methods:
            if not self._should_include_symbol(
                method_info.name, depth, include_private, method_info.docstring,
            ):
                continue
            total += 1
            parsed_method = parse_docstring_fn(method_info.docstring or "")
            if method_info.docstring:
                documented += 1

            m_params = self._convert_params(method_info, parsed_method)
            m_returns = _format_returns(parsed_method)

            m_raises = [
                f"{r.exception}: {r.description}" if r.description else r.exception
                for r in parsed_method.raises
            ]

            m_examples: list[str] = [ex.code for ex in parsed_method.examples]
            if include_examples and not m_examples:
                m_examples = self._find_examples(
                    method_info.name,
                    project_root,
                )

            m_decorators = [d.name for d in method_info.decorators]

            methods.append(
                APIDocFunction(
                    name=method_info.name,
                    signature=method_info.signature,
                    description=_full_description(parsed_method),
                    params=m_params,
                    returns=m_returns,
                    return_type=method_info.return_annotation or "",
                    raises=m_raises,
                    examples=m_examples,
                    decorators=m_decorators,
                    is_async=method_info.is_async,
                    is_property=method_info.is_property,
                    is_classmethod=method_info.is_classmethod,
                    is_staticmethod=method_info.is_staticmethod,
                    line=method_info.line,
                )
            )

        return methods, total, documented

    @staticmethod
    def _should_include(name: str, depth: str) -> bool:
        """Determine whether a symbol should be included based on depth.

        Args:
            name: The symbol name.
            depth: ``"public"``, ``"protected"``, or ``"all"``.

        Returns:
            True if the symbol should be included.
        """
        if depth == "all":
            return True
        if depth == "protected":
            # Include everything except dunder methods (other than __init__)
            return not (name.startswith("__") and name.endswith("__") and name != "__init__")
        # depth == "public"
        return not (name.startswith("_") and name != "__init__")

    @staticmethod
    def _should_include_symbol(
        name: str,
        depth: str,
        include_private: bool,
        docstring: str | None,
    ) -> bool:
        """Determine whether a symbol should be included.

        Extends ``_should_include`` with ``include_private`` support:
        when enabled, private functions (single ``_`` prefix) with
        docstrings are included even in ``"public"`` depth.

        Args:
            name: The symbol name.
            depth: ``"public"``, ``"protected"``, or ``"all"``.
            include_private: Whether to include documented privates.
            docstring: The symbol's docstring (used for private check).

        Returns:
            True if the symbol should be included.
        """
        if depth == "all":
            return True
        if depth == "protected":
            return not (name.startswith("__") and name.endswith("__") and name != "__init__")
        # depth == "public"
        if not name.startswith("_") or name == "__init__":
            return True
        # Private symbol — include if include_private and has docstring
        if include_private and docstring:
            return True
        return False

    @staticmethod
    def _convert_params(
        func_info: object,
        parsed: object,
    ) -> list[APIDocParam]:
        """Convert FunctionInfo parameters + parsed docstring into APIDocParam list.

        Merges AST-level parameter info with docstring-level descriptions.
        """
        from docs_mcp.extractors.docstring_parser import ParsedDocstring
        from docs_mcp.extractors.models import FunctionInfo

        if not isinstance(func_info, FunctionInfo) or not isinstance(parsed, ParsedDocstring):
            return []

        # Build a lookup from docstring params
        doc_params: dict[str, tuple[str, str]] = {}
        for dp in parsed.params:
            doc_params[dp.name] = (dp.type or "", dp.description)

        params: list[APIDocParam] = []
        for p in func_info.parameters:
            # Skip 'self' and 'cls'
            if p.name in ("self", "cls"):
                continue
            doc_type, doc_desc = doc_params.get(p.name, ("", ""))
            param_type = p.annotation or doc_type
            params.append(
                APIDocParam(
                    name=p.name,
                    type=param_type or "",
                    description=doc_desc,
                    default=p.default,
                )
            )

        return params

    # ------------------------------------------------------------------
    # Example finder
    # ------------------------------------------------------------------

    def _find_examples(
        self,
        func_name: str,
        project_root: Path,
    ) -> list[str]:
        """Search test files and source docstrings for usage examples.

        Looks for:
        - Test functions named ``test_*<func_name>*``
        - Test functions whose body references ``func_name``
        - Doctest ``>>>`` patterns referencing ``func_name``

        Args:
            func_name: The function name to search for.
            project_root: Project root to locate test directories.

        Returns:
            Up to ``_MAX_EXAMPLES`` code snippets from matching sources.
        """
        try:
            examples: list[str] = []

            # Search test directories
            for test_dir_name in ("tests", "test"):
                tests_dir = project_root / test_dir_name
                if not tests_dir.is_dir():
                    continue
                self._find_test_examples(
                    tests_dir, func_name, examples,
                )
                if len(examples) >= _MAX_EXAMPLES:
                    break

            return examples[:_MAX_EXAMPLES]
        except Exception:
            logger.debug(
                "example_search_failed",
                func_name=func_name,
                exc_info=True,
            )
            return []

    def _find_test_examples(
        self,
        tests_dir: Path,
        func_name: str,
        examples: list[str],
    ) -> None:
        """Collect test examples from a test directory into *examples*."""
        test_pattern = re.compile(
            r"^(test_.*\.py|.*_test\.py)$",
        )

        for test_file in sorted(tests_dir.rglob("*.py")):
            if len(examples) >= _MAX_EXAMPLES:
                return
            if not test_pattern.match(test_file.name):
                continue
            try:
                content = test_file.read_text(encoding="utf-8")
            except Exception:
                continue

            if func_name not in content:
                continue

            # Try test function snippets
            snippet = self._extract_test_snippet(content, func_name)
            if snippet:
                examples.append(snippet)

            # Try doctest patterns (>>> func_name(...))
            if len(examples) < _MAX_EXAMPLES:
                doctest_snippet = _extract_doctest(content, func_name)
                if doctest_snippet:
                    examples.append(doctest_snippet)

    @staticmethod
    def _extract_test_snippet(content: str, func_name: str) -> str:
        """Extract a test function body that references the given function.

        Args:
            content: The full test file content.
            func_name: The function name to look for.

        Returns:
            The test function body as a string, or empty string.
        """
        # Find test functions containing the function name
        pattern = re.compile(
            r"^(def\s+test_\w*" + re.escape(func_name) + r"\w*\s*\([^)]*\)\s*(?:->[^:]*)?:)",
            re.MULTILINE,
        )
        match = pattern.search(content)
        if not match:
            # Try a broader search: any test function that uses the name
            pattern_broad = re.compile(
                r"^(def\s+test_\w+\s*\([^)]*\)\s*(?:->[^:]*)?:)",
                re.MULTILINE,
            )
            for m in pattern_broad.finditer(content):
                # Check if the function body mentions func_name
                start = m.end()
                body_end = _find_function_end(content, start)
                body = content[start:body_end]
                if func_name in body:
                    match = m
                    break

        if not match:
            return ""

        start = match.start()
        body_start = match.end()
        body_end = _find_function_end(content, body_start)
        snippet = content[start:body_end].rstrip()

        # Limit snippet length
        lines = snippet.split("\n")
        if len(lines) > _MAX_SNIPPET_LINES:
            lines = lines[:_MAX_SNIPPET_LINES]
            lines.append("    ...")
            snippet = "\n".join(lines)

        return snippet

    # ------------------------------------------------------------------
    # Cross-reference resolution
    # ------------------------------------------------------------------

    def _resolve_cross_refs(
        self,
        text: str,
        known_symbols: set[str],
    ) -> str:
        """Convert backtick-wrapped symbol names to markdown links.

        Only applies to the ``"markdown"`` format. Backtick-wrapped names
        that match a known symbol become anchor links.

        Args:
            text: The text to process.
            known_symbols: Set of symbol names defined in the module.

        Returns:
            Text with cross-references resolved.
        """
        if not text or not known_symbols:
            return text

        def _replace(m: re.Match[str]) -> str:
            name = m.group(1)
            if name in known_symbols:
                anchor = name.lower().replace("_", "-")
                return f"[`{name}`](#{anchor})"
            return m.group(0)

        return re.sub(r"`(\w+)`", _replace, text)

    # ------------------------------------------------------------------
    # Markdown renderer
    # ------------------------------------------------------------------

    def _render_markdown(self, module: APIDocModule) -> str:
        """Render API documentation as GitHub-flavored markdown.

        Args:
            module: The extracted module information.

        Returns:
            The rendered markdown string.
        """
        known_symbols = self._collect_symbols(module)
        lines: list[str] = []

        # Module header
        lines.append(f"# `{module.name}`")
        lines.append("")
        if module.docstring:
            lines.append(
                self._resolve_cross_refs(module.docstring, known_symbols),
            )
            lines.append("")

        # Classes section
        if module.classes:
            lines.append("## Classes")
            lines.append("")
            for class_doc in module.classes:
                lines.extend(
                    self._render_class_markdown(class_doc, known_symbols),
                )

        # Functions section
        if module.functions:
            lines.append("## Functions")
            lines.append("")
            for func in module.functions:
                lines.extend(
                    self._render_function_markdown(func, known_symbols, level=3),
                )

        # Constants section
        if module.constants:
            lines.append("## Constants")
            lines.append("")
            lines.append("| Name | Type | Value |")
            lines.append("|------|------|-------|")
            for const in module.constants:
                c_type = self._escape_md(const.type) if const.type else ""
                c_val = self._escape_md(const.default or "") if const.default else ""
                lines.append(f"| `{const.name}` | `{c_type}` | `{c_val}` |")
            lines.append("")

        # Re-export notice
        if module.is_reexport:
            lines.append("> **Note:** This module re-exports symbols from "
                         "other modules. See source modules for full documentation.")
            lines.append("")

        # Quality footer
        lines.append("---")
        lines.append("")
        lines.append(f"*Documentation coverage: {module.coverage}%*")
        if module.missing_returns > 0 or module.missing_examples > 0:
            quality_notes: list[str] = []
            if module.missing_returns:
                label = "function" if module.missing_returns == 1 else "functions"
                quality_notes.append(
                    f"{module.missing_returns} {label} missing return docs"
                )
            if module.missing_examples:
                label = "function" if module.missing_examples == 1 else "functions"
                quality_notes.append(
                    f"{module.missing_examples} {label} missing examples"
                )
            lines.append(f"*Quality: {", ".join(quality_notes)}*")
        lines.append("")
        lines.append(
            f"*Auto-generated by DocsMCP on {_generation_date()}*"
        )
        lines.append("")

        return "\n".join(lines)

    def _render_class_markdown(
        self,
        class_doc: APIDocClass,
        known_symbols: set[str],
    ) -> list[str]:
        """Render a single class in markdown."""
        lines: list[str] = []

        # Class heading
        bases_str = f"({', '.join(class_doc.bases)})" if class_doc.bases else ""
        lines.append(f"### `{class_doc.name}`{bases_str}")
        lines.append("")

        if class_doc.decorators:
            lines.append(
                "Decorators: " + ", ".join(f"`@{d}`" for d in class_doc.decorators),
            )
            lines.append("")

        if class_doc.description:
            lines.append(
                self._resolve_cross_refs(class_doc.description, known_symbols),
            )
            lines.append("")

        # Class variables
        if class_doc.class_variables:
            lines.append("**Class Variables:**")
            lines.append("")
            lines.append("| Name | Type | Default |")
            lines.append("|------|------|---------|")
            for cv in class_doc.class_variables:
                cv_type = f"`{cv.type}`" if cv.type else ""
                cv_default = f"`{cv.default}`" if cv.default else ""
                lines.append(f"| `{cv.name}` | {cv_type} | {cv_default} |")
            lines.append("")

        # Methods
        if class_doc.methods:
            lines.append("**Methods:**")
            lines.append("")
            for method in class_doc.methods:
                lines.extend(
                    self._render_function_markdown(
                        method,
                        known_symbols,
                        level=4,
                    ),
                )

        return lines

    def _render_function_markdown(
        self,
        func: APIDocFunction,
        known_symbols: set[str],
        level: int = 3,
    ) -> list[str]:
        """Render a single function or method in markdown.

        Args:
            func: The function to render.
            known_symbols: Known symbols for cross-referencing.
            level: Heading level (3 = ###, 4 = ####).

        Returns:
            Lines of markdown.
        """
        heading = "#" * level
        lines: list[str] = []

        # Function heading
        prefix_parts: list[str] = []
        if func.is_async:
            prefix_parts.append("async")
        if func.is_classmethod:
            prefix_parts.append("classmethod")
        if func.is_staticmethod:
            prefix_parts.append("staticmethod")
        if func.is_property:
            prefix_parts.append("property")

        prefix = " ".join(prefix_parts)
        label = f"{prefix} " if prefix else ""
        lines.append(f"{heading} {label}`{func.name}`")
        lines.append("")

        # Signature
        lines.append(f"```python\n{func.signature}\n```")
        lines.append("")

        # Description
        if func.description:
            lines.append(
                self._resolve_cross_refs(func.description, known_symbols),
            )
            lines.append("")

        # Parameters table
        if func.params:
            lines.append("**Parameters:**")
            lines.append("")
            lines.append("| Name | Type | Description | Default |")
            lines.append("|------|------|-------------|---------|")
            for p in func.params:
                p_type = self._escape_md(p.type) if p.type else ""
                p_desc = self._escape_md(p.description) if p.description else ""
                p_default = self._escape_md(p.default) if p.default else "*required*"
                lines.append(
                    f"| `{p.name}` | `{p_type}` | {p_desc} | {p_default} |",
                )
            lines.append("")

        # Returns
        if func.returns or func.return_type:
            ret_parts: list[str] = []
            if func.return_type:
                ret_parts.append(f"`{func.return_type}`")
            if func.returns:
                ret_parts.append(func.returns)
            lines.append(f"**Returns:** {' - '.join(ret_parts)}")
            lines.append("")

        # Raises
        if func.raises:
            lines.append("**Raises:**")
            lines.append("")
            for r in func.raises:
                lines.append(f"- {r}")
            lines.append("")

        # Examples
        if func.examples:
            lines.append("**Examples:**")
            lines.append("")
            for example in func.examples:
                lines.append(f"```python\n{example}\n```")
                lines.append("")

        return lines

    # ------------------------------------------------------------------
    # MkDocs renderer
    # ------------------------------------------------------------------

    def _render_mkdocs(self, module: APIDocModule) -> str:
        """Render API documentation in MkDocs-compatible markdown.

        Adds YAML frontmatter and `:::` autodoc syntax for compatibility
        with mkdocstrings.

        Args:
            module: The extracted module information.

        Returns:
            The rendered mkdocs markdown string.
        """
        lines: list[str] = []

        # YAML frontmatter
        description = module.docstring.split("\n")[0] if module.docstring else ""
        lines.append("---")
        lines.append(f"title: {module.name}")
        if description:
            lines.append(f"description: {description}")
        lines.append("---")
        lines.append("")

        # Autodoc reference
        lines.append(f"::: {module.name}")
        lines.append("")

        # Append the standard markdown rendering
        md = self._render_markdown(module)
        lines.append(md)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Sphinx RST renderer
    # ------------------------------------------------------------------

    def _render_sphinx_rst(self, module: APIDocModule) -> str:
        """Render API documentation as Sphinx reStructuredText.

        Args:
            module: The extracted module information.

        Returns:
            The rendered RST string.
        """
        lines: list[str] = []

        # Module title
        title = f"``{module.name}``"
        lines.append(title)
        lines.append("=" * len(title))
        lines.append("")

        if module.docstring:
            lines.append(module.docstring)
            lines.append("")

        # Classes
        if module.classes:
            lines.append("Classes")
            lines.append("-" * len("Classes"))
            lines.append("")
            for class_doc in module.classes:
                lines.extend(_render_class_rst(class_doc))

        # Functions
        if module.functions:
            lines.append("Functions")
            lines.append("-" * len("Functions"))
            lines.append("")
            for func in module.functions:
                lines.extend(_render_function_rst(func))

        # Constants
        if module.constants:
            lines.append("Constants")
            lines.append("-" * len("Constants"))
            lines.append("")
            for const in module.constants:
                ann = f" : {const.type}" if const.type else ""
                val = f" = {const.default}" if const.default else ""
                lines.append(f".. data:: {const.name}{ann}{val}")
                lines.append("")

        # Coverage
        lines.append("")
        lines.append(f"*Documentation coverage: {module.coverage}%*")
        lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_symbols(module: APIDocModule) -> set[str]:
        """Collect all symbol names defined in the module."""
        symbols: set[str] = set()
        for func in module.functions:
            symbols.add(func.name)
        for class_doc in module.classes:
            symbols.add(class_doc.name)
            for method in class_doc.methods:
                symbols.add(method.name)
        for const in module.constants:
            symbols.add(const.name)
        return symbols

    @staticmethod
    def _escape_md(text: str) -> str:
        """Escape pipe characters for markdown table cells."""
        return text.replace("|", "\\|")


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _is_reexport_module(file_path: Path, module_info: object) -> bool:
    """Detect whether a module is a pure re-export (no original definitions).

    A re-export module is typically an ``__init__.py`` that only imports
    and re-exports symbols from submodules.
    """
    from docs_mcp.extractors.models import ModuleInfo

    if not isinstance(module_info, ModuleInfo):
        return False
    if file_path.name != "__init__.py":
        return False
    # A re-export module has no original functions or classes of its own
    # but may have constants like __all__
    has_original = len(module_info.functions) > 0 or len(module_info.classes) > 0
    return not has_original


def _generation_date() -> str:
    """Return the current date as an ISO string for freshness hints."""
    import datetime

    return datetime.date.today().isoformat()


def _full_description(parsed: object) -> str:
    """Build a full description from summary + body of a ParsedDocstring.

    Returns the summary line followed by the extended description (if any),
    separated by a blank line.
    """
    from docs_mcp.extractors.docstring_parser import ParsedDocstring

    if not isinstance(parsed, ParsedDocstring):
        return ""
    parts: list[str] = []
    if parsed.summary:
        parts.append(parsed.summary)
    if parsed.description:
        parts.append(parsed.description)
    return "\n\n".join(parts)


def _is_noise_constant(name: str, value: str | None) -> bool:
    """Return True if a constant is noise and should be filtered.

    Filters logger instances (``logger = structlog.get_logger()``) and
    well-known noise constants (``__all__``, ``__version__``).
    """
    if name in _NOISE_CONSTANTS:
        return True
    # Check for logger patterns (case-insensitive name match)
    name_lower = name.lower()
    if name_lower in _LOGGER_PATTERNS:
        return True
    # Check value for common logger factory calls
    if value and ("get_logger" in value or "getLogger" in value):
        return True
    return False


def _format_returns(parsed: object) -> str:
    """Format the returns section from a ParsedDocstring."""
    from docs_mcp.extractors.docstring_parser import ParsedDocstring

    if not isinstance(parsed, ParsedDocstring) or not parsed.returns:
        return ""
    parts: list[str] = []
    if parsed.returns.type:
        parts.append(parsed.returns.type)
    if parsed.returns.description:
        parts.append(parsed.returns.description)
    return " - ".join(parts) if parts else ""


def _render_class_rst(class_doc: APIDocClass) -> list[str]:
    """Render a single class in RST format."""
    lines: list[str] = []

    bases_str = f"({', '.join(class_doc.bases)})" if class_doc.bases else ""
    lines.append(f".. class:: {class_doc.name}{bases_str}")
    lines.append("")

    if class_doc.description:
        lines.append(f"   {class_doc.description}")
        lines.append("")

    for cv in class_doc.class_variables:
        ann = f" : {cv.type}" if cv.type else ""
        val = f" = {cv.default}" if cv.default else ""
        lines.append(f"   .. attribute:: {cv.name}{ann}{val}")
        lines.append("")

    for method in class_doc.methods:
        method_lines = _render_function_rst(method, indent=3)
        lines.extend(method_lines)

    return lines


def _render_function_rst(
    func: APIDocFunction,
    indent: int = 0,
) -> list[str]:
    """Render a single function in RST format.

    Args:
        func: The function to render.
        indent: Number of spaces to indent (for class methods).

    Returns:
        Lines of RST.
    """
    lines: list[str] = []
    prefix = " " * indent

    # Function directive
    directive = "method" if indent > 0 else "function"
    lines.append(f"{prefix}.. {directive}:: {func.signature}")
    lines.append("")

    inner = prefix + "   "

    if func.description:
        lines.append(f"{inner}{func.description}")
        lines.append("")

    for p in func.params:
        lines.append(f"{inner}:param {p.name}: {p.description}")
        if p.type:
            lines.append(f"{inner}:type {p.name}: {p.type}")

    if func.returns or func.return_type:
        # Use return_type annotation if available, otherwise parse from returns text
        if func.return_type:
            lines.append(f"{inner}:rtype: {func.return_type}")
            if func.returns:
                lines.append(f"{inner}:returns: {func.returns}")
        elif " - " in func.returns:
            rtype, rdesc = func.returns.split(" - ", 1)
            lines.append(f"{inner}:returns: {rdesc}")
            lines.append(f"{inner}:rtype: {rtype}")
        else:
            lines.append(f"{inner}:returns: {func.returns}")

    for r in func.raises:
        if ":" in r:
            exc, desc = r.split(":", 1)
            lines.append(f"{inner}:raises {exc.strip()}: {desc.strip()}")
        else:
            lines.append(f"{inner}:raises {r}:")

    lines.append("")
    return lines


def _extract_doctest(content: str, func_name: str) -> str:
    """Extract a doctest block referencing *func_name* from *content*.

    Looks for ``>>> func_name(`` patterns and collects the full
    doctest block (``>>>`` and ``...`` continuation lines plus
    expected output lines).

    Returns:
        The doctest block as a string, or empty string.
    """
    pattern = re.compile(
        r"^(\s*>>>.*" + re.escape(func_name) + r"\s*\()",
        re.MULTILINE,
    )
    match = pattern.search(content)
    if not match:
        return ""

    lines = content[match.start():].split("\n")
    block: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(">>>") or stripped.startswith("..."):
            block.append(line)
        elif block and stripped:
            # Output line following a doctest
            block.append(line)
        elif block:
            break

    if not block:
        return ""

    # Dedent the block
    result = "\n".join(block)
    if len(result.split("\n")) > _MAX_SNIPPET_LINES:
        result_lines = result.split("\n")[:_MAX_SNIPPET_LINES]
        result_lines.append("...")
        result = "\n".join(result_lines)
    return result


def _find_function_end(content: str, body_start: int) -> int:
    """Find the end of a function body by tracking indentation.

    Args:
        content: Full file content.
        body_start: Character index where the function body begins.

    Returns:
        Character index where the function body ends.
    """
    lines = content[body_start:].split("\n")
    if not lines:
        return body_start

    # Find the indentation of the first non-empty body line
    base_indent: int | None = None
    for line in lines:
        if line.strip():
            base_indent = len(line) - len(line.lstrip())
            break

    if base_indent is None:
        return body_start

    end_offset = 0
    for line in lines:
        if line.strip() and (len(line) - len(line.lstrip())) < base_indent:
            break
        end_offset += len(line) + 1  # +1 for newline

    return body_start + end_offset
