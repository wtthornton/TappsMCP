"""Tree-sitter based Rust extractor."""

from __future__ import annotations

from typing import Any

import structlog

from docs_mcp.extractors.models import (
    ClassInfo,
    ConstantInfo,
    FunctionInfo,
    ModuleInfo,
    ParameterInfo,
)
from docs_mcp.extractors.treesitter_base import TreeSitterExtractor

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

_RUST_LANGUAGE: Any = None
try:
    import tree_sitter
    import tree_sitter_rust

    _RUST_LANGUAGE = tree_sitter.Language(tree_sitter_rust.language())
except ImportError:
    pass


class RustExtractor(TreeSitterExtractor):
    """Extract symbols from Rust source files using tree-sitter."""

    @property
    def file_extensions(self) -> frozenset[str]:
        return frozenset({".rs"})

    @property
    def language_obj(self) -> Any:
        return _RUST_LANGUAGE

    def can_handle(self, file_path: Any) -> bool:
        if _RUST_LANGUAGE is None:
            return False
        from pathlib import Path as _Path

        p = _Path(file_path) if not isinstance(file_path, _Path) else file_path
        return p.suffix.lower() in self.file_extensions

    # ------------------------------------------------------------------
    # Traversal
    # ------------------------------------------------------------------

    def _traverse(
        self,
        root: Any,
        source: bytes,
        rel_path: str,
    ) -> ModuleInfo:
        functions: list[FunctionInfo] = []
        classes: list[ClassInfo] = []
        constants: list[ConstantInfo] = []
        imports: list[str] = []
        docstring: str | None = None

        for child in root.children:
            node_type = child.type

            if node_type == "use_declaration":
                imports.append(self._node_text(child, source).rstrip(";"))

            elif node_type == "function_item":
                func = self._extract_function(child, source)
                if func:
                    functions.append(func)
                    # Use first top-level doc comment as module docstring.
                    if docstring is None and func.docstring:
                        pass  # Don't steal function docs as module doc.

            elif node_type == "struct_item":
                cls = self._extract_struct(child, source)
                if cls:
                    classes.append(cls)

            elif node_type == "enum_item":
                cls = self._extract_enum(child, source)
                if cls:
                    classes.append(cls)

            elif node_type == "trait_item":
                cls = self._extract_trait(child, source)
                if cls:
                    classes.append(cls)

            elif node_type == "impl_item":
                self._extract_impl(child, source, functions)

            elif node_type == "const_item" or node_type == "static_item":
                const = self._extract_const(child, source)
                if const:
                    constants.append(const)

            elif node_type == "line_comment" and docstring is None:
                # Module-level doc comment (//! style)
                text = self._node_text(child, source)
                if text.startswith("//!"):
                    docstring = text[3:].strip()

        # Collect consecutive //! comments as module docstring.
        module_doc = self._collect_module_doc(root, source)
        if module_doc:
            docstring = module_doc

        return ModuleInfo(
            path=rel_path,
            docstring=docstring,
            imports=imports,
            functions=functions,
            classes=classes,
            constants=constants,
        )

    # ------------------------------------------------------------------
    # Functions
    # ------------------------------------------------------------------

    def _extract_function(self, node: Any, source: bytes) -> FunctionInfo | None:
        name_node = self._child_by_field(node, "name")
        if name_node is None:
            return None
        name = self._node_text(name_node, source)

        self._get_visibility(node, source)
        is_async = any(
            c.type in ("async", "function_modifiers") and "async" in self._node_text(c, source)
            for c in node.children
        )
        params = self._extract_rust_params(node, source)
        ret = self._extract_rust_return(node, source)
        doc = self._rust_doc_before(node, source)

        return self._build_function(
            name=name,
            line=self._node_line(node),
            end_line=self._node_end_line(node),
            parameters=params,
            return_annotation=ret,
            docstring=doc,
            is_async=is_async,
        )

    # ------------------------------------------------------------------
    # Parameters
    # ------------------------------------------------------------------

    def _extract_rust_params(self, node: Any, source: bytes) -> list[ParameterInfo]:
        """Extract parameters from a Rust function's parameter list."""
        params_node = self._child_by_field(node, "parameters")
        if params_node is None:
            return []

        result: list[ParameterInfo] = []
        for child in params_node.children:
            if child.type == "parameter":
                p = self._parse_rust_param(child, source)
                if p:
                    result.append(p)
            elif child.type == "self_parameter":
                self_text = self._node_text(child, source)
                result.append(ParameterInfo(name=self_text))
        return result

    def _parse_rust_param(self, node: Any, source: bytes) -> ParameterInfo | None:
        """Parse a Rust parameter node."""
        pattern_node = self._child_by_field(node, "pattern")
        type_node = self._child_by_field(node, "type")
        name = self._node_text(pattern_node, source) if pattern_node else ""
        annotation = self._node_text(type_node, source) if type_node else None
        return ParameterInfo(name=name, annotation=annotation) if name else None

    def _extract_rust_return(self, node: Any, source: bytes) -> str | None:
        """Extract the return type from a Rust function."""
        ret_node = self._child_by_field(node, "return_type")
        if ret_node is None:
            return None
        text = self._node_text(ret_node, source)
        # Strip leading "-> "
        text = text.lstrip("-").lstrip(">").strip()
        return text or None

    # ------------------------------------------------------------------
    # Structs
    # ------------------------------------------------------------------

    def _extract_struct(self, node: Any, source: bytes) -> ClassInfo | None:
        name_node = self._child_by_field(node, "name")
        if name_node is None:
            return None
        name = self._node_text(name_node, source)
        doc = self._rust_doc_before(node, source)

        fields: list[ConstantInfo] = []
        body = self._child_by_field(node, "body")
        if body:
            for child in body.children:
                if child.type == "field_declaration":
                    field_name_node = self._child_by_field(child, "name")
                    field_type_node = self._child_by_field(child, "type")
                    if field_name_node:
                        fname = self._node_text(field_name_node, source)
                        fann = self._node_text(field_type_node, source) if field_type_node else None
                        fields.append(
                            ConstantInfo(
                                name=fname,
                                line=self._node_line(child),
                                annotation=fann,
                            )
                        )

        return self._build_class(
            name=name,
            line=self._node_line(node),
            end_line=self._node_end_line(node),
            docstring=doc,
            class_variables=fields,
        )

    # ------------------------------------------------------------------
    # Enums
    # ------------------------------------------------------------------

    def _extract_enum(self, node: Any, source: bytes) -> ClassInfo | None:
        name_node = self._child_by_field(node, "name")
        if name_node is None:
            return None
        name = self._node_text(name_node, source)
        doc = self._rust_doc_before(node, source)

        # Collect enum variants as class variables.
        variants: list[ConstantInfo] = []
        body = self._child_by_field(node, "body")
        if body:
            for child in body.children:
                if child.type == "enum_variant":
                    vname_node = self._child_by_field(child, "name")
                    if vname_node:
                        vname = self._node_text(vname_node, source)
                        variants.append(
                            ConstantInfo(
                                name=vname,
                                line=self._node_line(child),
                            )
                        )

        return self._build_class(
            name=name,
            line=self._node_line(node),
            end_line=self._node_end_line(node),
            docstring=doc,
            class_variables=variants,
        )

    # ------------------------------------------------------------------
    # Traits
    # ------------------------------------------------------------------

    def _extract_trait(self, node: Any, source: bytes) -> ClassInfo | None:
        name_node = self._child_by_field(node, "name")
        if name_node is None:
            return None
        name = self._node_text(name_node, source)
        doc = self._rust_doc_before(node, source)

        methods: list[FunctionInfo] = []
        body = self._child_by_field(node, "body")
        if body:
            for child in body.children:
                if child.type == "function_item":
                    func = self._extract_function(child, source)
                    if func:
                        methods.append(func)
                elif child.type == "function_signature_item":
                    func = self._extract_function_signature(child, source)
                    if func:
                        methods.append(func)

        return self._build_class(
            name=name,
            line=self._node_line(node),
            end_line=self._node_end_line(node),
            docstring=doc,
            methods=methods,
        )

    def _extract_function_signature(
        self,
        node: Any,
        source: bytes,
    ) -> FunctionInfo | None:
        """Extract a function signature item (trait method without body)."""
        name_node = self._child_by_field(node, "name")
        if name_node is None:
            return None
        name = self._node_text(name_node, source)
        params = self._extract_rust_params(node, source)
        ret = self._extract_rust_return(node, source)
        doc = self._rust_doc_before(node, source)

        return self._build_function(
            name=name,
            line=self._node_line(node),
            end_line=self._node_end_line(node),
            parameters=params,
            return_annotation=ret,
            docstring=doc,
        )

    # ------------------------------------------------------------------
    # Impl blocks
    # ------------------------------------------------------------------

    def _extract_impl(
        self,
        node: Any,
        source: bytes,
        functions: list[FunctionInfo],
    ) -> None:
        """Extract methods from an impl block and add to the functions list."""
        body = self._child_by_field(node, "body")
        if body is None:
            return
        for child in body.children:
            if child.type == "function_item":
                func = self._extract_function(child, source)
                if func:
                    functions.append(func)

    # ------------------------------------------------------------------
    # Constants
    # ------------------------------------------------------------------

    def _extract_const(self, node: Any, source: bytes) -> ConstantInfo | None:
        name_node = self._child_by_field(node, "name")
        if name_node is None:
            return None
        name = self._node_text(name_node, source)
        type_node = self._child_by_field(node, "type")
        val_node = self._child_by_field(node, "value")
        ann = self._node_text(type_node, source) if type_node else None
        val = self._node_text(val_node, source) if val_node else None

        return ConstantInfo(name=name, line=self._node_line(node), value=val, annotation=ann)

    # ------------------------------------------------------------------
    # Visibility
    # ------------------------------------------------------------------

    @staticmethod
    def _get_visibility(node: Any, source: bytes) -> str | None:
        """Get the visibility modifier (pub, pub(crate), etc.)."""
        for child in node.children:
            if child.type == "visibility_modifier":
                return source[child.start_byte : child.end_byte].decode(
                    "utf-8",
                    errors="replace",
                )
        return None

    # ------------------------------------------------------------------
    # Doc comments
    # ------------------------------------------------------------------

    def _rust_doc_before(self, node: Any, source: bytes) -> str | None:
        """Collect ``///`` doc-comment lines before a Rust item."""
        return self._collect_comment_before(node, source, prefix="///")

    def _collect_module_doc(self, root: Any, source: bytes) -> str | None:
        """Collect consecutive ``//!`` module doc comments at the start of file."""
        doc_lines: list[str] = []
        for child in root.children:
            if child.type == "line_comment":
                text = self._node_text(child, source)
                if text.startswith("//!"):
                    doc_lines.append(text[3:].strip())
                else:
                    break
            else:
                break
        return "\n".join(doc_lines) if doc_lines else None
