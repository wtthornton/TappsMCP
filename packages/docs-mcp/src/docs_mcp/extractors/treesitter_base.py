"""Base class for tree-sitter powered source code extractors."""

from __future__ import annotations

import abc
from pathlib import Path
from typing import Any

import structlog

from docs_mcp.extractors.models import (
    ClassInfo,
    ConstantInfo,
    FunctionInfo,
    ModuleInfo,
    ParameterInfo,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Guard tree-sitter imports for graceful degradation.
try:
    import tree_sitter

    HAS_TREE_SITTER = True
except ImportError:
    tree_sitter = None  # type: ignore[assignment]
    HAS_TREE_SITTER = False

# Max file size to parse (10 MB).
_MAX_FILE_SIZE = 10 * 1024 * 1024


class TreeSitterExtractor(abc.ABC):
    """Base class for tree-sitter powered extractors.

    Subclasses implement language-specific node traversal. The base class
    provides shared parsing logic and model conversion helpers.

    If tree-sitter is not installed, ``can_handle()`` returns False so the
    dispatcher falls back to ``GenericExtractor``.
    """

    @property
    @abc.abstractmethod
    def language_obj(self) -> Any:
        """Return the tree-sitter Language object for this extractor."""

    @property
    @abc.abstractmethod
    def file_extensions(self) -> frozenset[str]:
        """Return the set of file extensions this extractor handles."""

    # ------------------------------------------------------------------
    # Protocol methods
    # ------------------------------------------------------------------

    def can_handle(self, file_path: Path) -> bool:
        """Return True if tree-sitter is available and extension matches."""
        if not HAS_TREE_SITTER:
            return False
        return file_path.suffix.lower() in self.file_extensions

    def extract(self, file_path: Path, *, project_root: Path | None = None) -> ModuleInfo:
        """Parse with tree-sitter and delegate to subclass traversal. Never raises."""
        rel_path = _relative_path(file_path, project_root)
        try:
            return self._do_extract(file_path, rel_path)
        except Exception:
            logger.warning("treesitter_extract_failed", path=str(file_path))
            return ModuleInfo(path=rel_path)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _do_extract(self, file_path: Path, rel_path: str) -> ModuleInfo:
        if not file_path.exists():
            return ModuleInfo(path=rel_path)

        try:
            size = file_path.stat().st_size
        except OSError:
            return ModuleInfo(path=rel_path)
        if size > _MAX_FILE_SIZE:
            return ModuleInfo(path=rel_path)

        try:
            source_bytes = file_path.read_bytes()
        except OSError:
            return ModuleInfo(path=rel_path)

        parser = tree_sitter.Parser(self.language_obj)
        tree = parser.parse(source_bytes)
        return self._traverse(tree.root_node, source_bytes, rel_path)

    @abc.abstractmethod
    def _traverse(
        self,
        root: Any,
        source: bytes,
        rel_path: str,
    ) -> ModuleInfo:
        """Walk the tree-sitter AST and produce a ``ModuleInfo``."""

    # ------------------------------------------------------------------
    # Shared helpers for subclasses
    # ------------------------------------------------------------------

    @staticmethod
    def _node_text(node: Any, source: bytes) -> str:
        """Extract the UTF-8 text of a tree-sitter node."""
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    @staticmethod
    def _node_line(node: Any) -> int:
        """Return the 1-based line number of a node."""
        return int(node.start_point[0]) + 1

    @staticmethod
    def _node_end_line(node: Any) -> int:
        """Return the 1-based end line number of a node."""
        return int(node.end_point[0]) + 1

    def _children_by_type(self, node: Any, type_name: str) -> list[Any]:
        """Return direct children matching *type_name*."""
        return [c for c in node.children if c.type == type_name]

    def _child_by_field(self, node: Any, field: str) -> Any | None:
        """Return first child matching the given field name."""
        return node.child_by_field_name(field)

    def _build_function(
        self,
        *,
        name: str,
        line: int,
        end_line: int | None = None,
        parameters: list[ParameterInfo] | None = None,
        return_annotation: str | None = None,
        docstring: str | None = None,
        is_async: bool = False,
    ) -> FunctionInfo:
        """Build a ``FunctionInfo`` with a computed signature."""
        params = parameters or []
        params_str = ", ".join(
            self._format_param(p) for p in params
        )
        sig = f"({params_str})"
        if return_annotation:
            sig += f" -> {return_annotation}"
        return FunctionInfo(
            name=name,
            line=line,
            end_line=end_line,
            signature=sig,
            parameters=params,
            return_annotation=return_annotation,
            docstring=docstring,
            is_async=is_async,
        )

    def _build_class(
        self,
        *,
        name: str,
        line: int,
        end_line: int | None = None,
        bases: list[str] | None = None,
        docstring: str | None = None,
        methods: list[FunctionInfo] | None = None,
        class_variables: list[ConstantInfo] | None = None,
    ) -> ClassInfo:
        """Build a ``ClassInfo``."""
        return ClassInfo(
            name=name,
            line=line,
            end_line=end_line,
            bases=bases or [],
            docstring=docstring,
            methods=methods or [],
            class_variables=class_variables or [],
        )

    @staticmethod
    def _format_param(p: ParameterInfo) -> str:
        """Format a single parameter for signature display."""
        result = p.name
        if p.annotation:
            result = f"{p.name}: {p.annotation}"
        if p.default is not None:
            result = f"{result} = {p.default}" if p.annotation else f"{result}={p.default}"
        return result

    def _collect_comment_before(
        self,
        node: Any,
        source: bytes,
        *,
        prefix: str = "//",
    ) -> str | None:
        """Collect contiguous comment lines immediately before *node*.

        Works for ``//``, ``///``, and ``#`` style line comments.
        """
        lines = source[:node.start_byte].decode("utf-8", errors="replace").split("\n")
        doc_lines: list[str] = []
        idx = len(lines) - 2  # line before the node
        while idx >= 0:
            stripped = lines[idx].strip()
            if stripped.startswith(prefix):
                text = stripped[len(prefix):].strip()
                doc_lines.append(text)
                idx -= 1
            elif stripped == "":
                break
            else:
                break
        if doc_lines:
            doc_lines.reverse()
            return "\n".join(doc_lines)
        return None

    def _extract_block_comment_before(
        self,
        node: Any,
        source: bytes,
    ) -> str | None:
        """Extract a JSDoc/Javadoc-style ``/** ... */`` comment before *node*."""
        # Look at the previous sibling for a comment node.
        prev = node.prev_named_sibling
        if prev is None:
            return None
        if prev.type in ("comment", "block_comment"):
            text = self._node_text(prev, source)
            if text.startswith("/**") and text.endswith("*/"):
                body = text[3:-2]
                cleaned = "\n".join(
                    line.strip().lstrip("*").strip()
                    for line in body.split("\n")
                ).strip()
                return cleaned or None
        return None


def _relative_path(file_path: Path, project_root: Path | None) -> str:
    """Make *file_path* relative to *project_root* when possible."""
    if project_root is not None:
        try:
            return str(file_path.relative_to(project_root))
        except ValueError:
            pass
    return str(file_path)
