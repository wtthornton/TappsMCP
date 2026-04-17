"""Tree-sitter based TypeScript/TSX extractor."""

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

_TS_LANGUAGE: Any = None
_TSX_LANGUAGE: Any = None
try:
    import tree_sitter
    import tree_sitter_typescript

    _TS_LANGUAGE = tree_sitter.Language(tree_sitter_typescript.language_typescript())
    _TSX_LANGUAGE = tree_sitter.Language(tree_sitter_typescript.language_tsx())
except ImportError:
    pass


class TypeScriptExtractor(TreeSitterExtractor):
    """Extract symbols from TypeScript and TSX files using tree-sitter."""

    _is_tsx: bool = False

    @property
    def file_extensions(self) -> frozenset[str]:
        return frozenset({".ts", ".tsx"})

    @property
    def language_obj(self) -> Any:
        if self._is_tsx:
            return _TSX_LANGUAGE
        return _TS_LANGUAGE

    def can_handle(self, file_path: Any) -> bool:
        """Check availability and extension."""
        if _TS_LANGUAGE is None:
            return False
        from pathlib import Path as _Path

        p = _Path(file_path) if not isinstance(file_path, _Path) else file_path
        return p.suffix.lower() in self.file_extensions

    def extract(self, file_path: Any, *, project_root: Any | None = None) -> ModuleInfo:
        """Override to select TSX parser for .tsx files."""
        from pathlib import Path as _Path

        p = _Path(file_path) if not isinstance(file_path, _Path) else file_path
        self._is_tsx = p.suffix.lower() == ".tsx"
        return super().extract(p, project_root=project_root)

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

        for child in root.children:
            node_type = child.type

            if node_type == "import_statement":
                imports.append(self._node_text(child, source).rstrip(";"))

            elif node_type == "function_declaration":
                func = self._extract_function(child, source)
                if func:
                    functions.append(func)

            elif node_type == "export_statement":
                self._handle_export(
                    child,
                    source,
                    functions,
                    classes,
                    constants,
                    imports,
                )

            elif node_type == "class_declaration":
                cls = self._extract_class(child, source)
                if cls:
                    classes.append(cls)

            elif node_type == "lexical_declaration":
                self._handle_lexical_declaration(
                    child,
                    source,
                    functions,
                    constants,
                )

            elif node_type in ("type_alias_declaration", "interface_declaration"):
                cls = self._extract_type_or_interface(child, source)
                if cls:
                    classes.append(cls)

        return ModuleInfo(
            path=rel_path,
            imports=imports,
            functions=functions,
            classes=classes,
            constants=constants,
        )

    # ------------------------------------------------------------------
    # Export handling
    # ------------------------------------------------------------------

    def _handle_export(
        self,
        node: Any,
        source: bytes,
        functions: list[FunctionInfo],
        classes: list[ClassInfo],
        constants: list[ConstantInfo],
        imports: list[str],
    ) -> None:
        """Process an export_statement, extracting its inner declaration."""
        for child in node.children:
            ct = child.type
            if ct == "function_declaration":
                func = self._extract_function(child, source, exported=True)
                if func:
                    functions.append(func)
            elif ct == "class_declaration":
                cls = self._extract_class(child, source)
                if cls:
                    classes.append(cls)
            elif ct == "lexical_declaration":
                self._handle_lexical_declaration(child, source, functions, constants)
            elif ct in ("type_alias_declaration", "interface_declaration"):
                cls = self._extract_type_or_interface(child, source)
                if cls:
                    classes.append(cls)
            elif ct == "import_statement":
                imports.append(self._node_text(child, source).rstrip(";"))

    # ------------------------------------------------------------------
    # Function extraction
    # ------------------------------------------------------------------

    def _extract_function(
        self,
        node: Any,
        source: bytes,
        *,
        exported: bool = False,
    ) -> FunctionInfo | None:
        name_node = self._child_by_field(node, "name")
        if name_node is None:
            return None
        name = self._node_text(name_node, source)
        is_async = any(c.type == "async" for c in node.children)

        params = self._extract_parameters(node, source)
        ret = self._extract_return_type(node, source)
        doc = self._extract_jsdoc_before(node, source)

        return self._build_function(
            name=name,
            line=self._node_line(node),
            end_line=self._node_end_line(node),
            parameters=params,
            return_annotation=ret,
            docstring=doc,
            is_async=is_async,
        )

    def _extract_arrow_function(
        self,
        name: str,
        value_node: Any,
        decl_node: Any,
        source: bytes,
    ) -> FunctionInfo | None:
        """Extract an arrow function assigned to a variable."""
        is_async = any(c.type == "async" for c in value_node.children)
        params = self._extract_parameters(value_node, source)
        ret = self._extract_return_type(value_node, source)
        doc = self._extract_jsdoc_before(decl_node, source)

        return self._build_function(
            name=name,
            line=self._node_line(decl_node),
            end_line=self._node_end_line(value_node),
            parameters=params,
            return_annotation=ret,
            docstring=doc,
            is_async=is_async,
        )

    # ------------------------------------------------------------------
    # Parameters
    # ------------------------------------------------------------------

    def _extract_parameters(self, node: Any, source: bytes) -> list[ParameterInfo]:
        """Extract parameters from a function or arrow function node."""
        params: list[ParameterInfo] = []
        params_node = self._child_by_field(node, "parameters")
        if params_node is None:
            # Arrow functions may use formal_parameters
            for child in node.children:
                if child.type == "formal_parameters":
                    params_node = child
                    break
        if params_node is None:
            return params

        for child in params_node.children:
            if child.type in (
                "required_parameter",
                "optional_parameter",
                "rest_parameter",
            ):
                param = self._parse_single_param(child, source)
                if param:
                    params.append(param)
        return params

    def _parse_single_param(self, node: Any, source: bytes) -> ParameterInfo | None:
        """Parse a single parameter node."""
        # The pattern node holds the parameter name (may be identifier or rest).
        pattern = self._child_by_field(node, "pattern")
        name_node = pattern if pattern else self._child_by_field(node, "name")
        if name_node is None:
            return None
        name = self._node_text(name_node, source)

        annotation: str | None = None
        type_node = self._child_by_field(node, "type")
        if type_node is not None:
            ann_text = self._node_text(type_node, source)
            # Strip leading ":"
            annotation = ann_text.lstrip(":").strip() or None

        default: str | None = None
        val_node = self._child_by_field(node, "value")
        if val_node is not None:
            default = self._node_text(val_node, source)

        return ParameterInfo(name=name, annotation=annotation, default=default)

    # ------------------------------------------------------------------
    # Return type
    # ------------------------------------------------------------------

    def _extract_return_type(self, node: Any, source: bytes) -> str | None:
        """Extract a return type annotation from a function node."""
        ret_node = self._child_by_field(node, "return_type")
        if ret_node is None:
            return None
        text = self._node_text(ret_node, source)
        return text.lstrip(":").strip() or None

    # ------------------------------------------------------------------
    # Classes
    # ------------------------------------------------------------------

    def _extract_class(self, node: Any, source: bytes) -> ClassInfo | None:
        name_node = self._child_by_field(node, "name")
        if name_node is None:
            return None
        name = self._node_text(name_node, source)
        doc = self._extract_jsdoc_before(node, source)

        bases: list[str] = []
        # Heritage clauses (extends / implements)
        for child in node.children:
            if child.type == "class_heritage":
                for hc in child.children:
                    if hc.type in ("extends_clause", "implements_clause"):
                        for type_node in hc.children:
                            if type_node.type in ("type_identifier", "identifier"):
                                bases.append(self._node_text(type_node, source))

        methods: list[FunctionInfo] = []
        class_vars: list[ConstantInfo] = []
        body = self._child_by_field(node, "body")
        if body:
            for child in body.children:
                if child.type in ("method_definition", "public_field_definition"):
                    if child.type == "method_definition":
                        m = self._extract_method(child, source)
                        if m:
                            methods.append(m)
                    else:
                        cv = self._extract_class_property(child, source)
                        if cv:
                            class_vars.append(cv)

        return self._build_class(
            name=name,
            line=self._node_line(node),
            end_line=self._node_end_line(node),
            bases=bases,
            docstring=doc,
            methods=methods,
            class_variables=class_vars,
        )

    def _extract_method(self, node: Any, source: bytes) -> FunctionInfo | None:
        name_node = self._child_by_field(node, "name")
        if name_node is None:
            return None
        name = self._node_text(name_node, source)
        is_async = any(c.type == "async" for c in node.children)
        params = self._extract_parameters(node, source)
        ret = self._extract_return_type(node, source)
        doc = self._extract_jsdoc_before(node, source)

        return self._build_function(
            name=name,
            line=self._node_line(node),
            end_line=self._node_end_line(node),
            parameters=params,
            return_annotation=ret,
            docstring=doc,
            is_async=is_async,
        )

    def _extract_class_property(self, node: Any, source: bytes) -> ConstantInfo | None:
        name_node = self._child_by_field(node, "name")
        if name_node is None:
            return None
        name = self._node_text(name_node, source)
        annotation: str | None = None
        type_node = self._child_by_field(node, "type")
        if type_node is not None:
            annotation = self._node_text(type_node, source).lstrip(":").strip() or None
        val_node = self._child_by_field(node, "value")
        value = self._node_text(val_node, source) if val_node else None

        return ConstantInfo(
            name=name, line=self._node_line(node), value=value, annotation=annotation
        )

    # ------------------------------------------------------------------
    # Type aliases and interfaces
    # ------------------------------------------------------------------

    def _extract_type_or_interface(self, node: Any, source: bytes) -> ClassInfo | None:
        """Treat TS interfaces / type aliases as ClassInfo for doc purposes."""
        name_node = self._child_by_field(node, "name")
        if name_node is None:
            return None
        name = self._node_text(name_node, source)
        doc = self._extract_jsdoc_before(node, source)

        methods: list[FunctionInfo] = []
        class_vars: list[ConstantInfo] = []

        # For interfaces, extract method/property signatures from the body.
        body = self._child_by_field(node, "body")
        if body:
            for child in body.children:
                if child.type in ("method_signature", "property_signature"):
                    prop_name_node = self._child_by_field(child, "name")
                    if prop_name_node is None:
                        continue
                    prop_name = self._node_text(prop_name_node, source)
                    if child.type == "method_signature":
                        params = self._extract_parameters(child, source)
                        ret = self._extract_return_type(child, source)
                        methods.append(
                            self._build_function(
                                name=prop_name,
                                line=self._node_line(child),
                                parameters=params,
                                return_annotation=ret,
                            )
                        )
                    else:
                        type_node = self._child_by_field(child, "type")
                        ann = None
                        if type_node:
                            ann = self._node_text(type_node, source).lstrip(":").strip()
                        class_vars.append(
                            ConstantInfo(
                                name=prop_name,
                                line=self._node_line(child),
                                annotation=ann,
                            )
                        )

        return self._build_class(
            name=name,
            line=self._node_line(node),
            end_line=self._node_end_line(node),
            docstring=doc,
            methods=methods,
            class_variables=class_vars,
        )

    # ------------------------------------------------------------------
    # Lexical declarations (const/let/var)
    # ------------------------------------------------------------------

    def _handle_lexical_declaration(
        self,
        node: Any,
        source: bytes,
        functions: list[FunctionInfo],
        constants: list[ConstantInfo],
    ) -> None:
        """Handle const/let/var declarations."""
        for child in node.children:
            if child.type != "variable_declarator":
                continue
            name_node = self._child_by_field(child, "name")
            if name_node is None:
                continue
            name = self._node_text(name_node, source)
            value_node = self._child_by_field(child, "value")
            if value_node is None:
                continue

            # Arrow functions / function expressions.
            if value_node.type in ("arrow_function", "function"):
                func = self._extract_arrow_function(name, value_node, node, source)
                if func:
                    functions.append(func)
            else:
                annotation: str | None = None
                type_node = self._child_by_field(child, "type")
                if type_node is not None:
                    annotation = self._node_text(type_node, source).lstrip(":").strip() or None
                constants.append(
                    ConstantInfo(
                        name=name,
                        line=self._node_line(node),
                        value=self._node_text(value_node, source),
                        annotation=annotation,
                    )
                )

    # ------------------------------------------------------------------
    # JSDoc
    # ------------------------------------------------------------------

    def _extract_jsdoc_before(self, node: Any, source: bytes) -> str | None:
        """Extract a JSDoc comment (/** ... */) preceding *node*.

        Handles the case where the comment is a sibling of the outer
        ``export_statement`` rather than the inner declaration.
        """
        # Try direct previous sibling first.
        result = self._check_jsdoc_sibling(node, source)
        if result is not None:
            return result

        # For nodes inside an export_statement, the JSDoc comment is a
        # sibling of the export_statement, not the inner declaration.
        if node.parent is not None and node.parent.type == "export_statement":
            result = self._check_jsdoc_sibling(node.parent, source)
            if result is not None:
                return result

        return None

    def _check_jsdoc_sibling(self, node: Any, source: bytes) -> str | None:
        """Check named and unnamed previous siblings for a JSDoc comment."""
        prev = node.prev_named_sibling
        if prev is not None and prev.type == "comment":
            text = self._node_text(prev, source)
            if text.startswith("/**") and text.endswith("*/"):
                return self._clean_jsdoc(text)

        # Also check unnamed siblings (comment nodes may not be named).
        if node.parent is not None:
            idx = None
            for i, sib in enumerate(node.parent.children):
                if sib.id == node.id:
                    idx = i
                    break
            if idx is not None and idx > 0:
                prev_sib = node.parent.children[idx - 1]
                if prev_sib.type == "comment":
                    text = self._node_text(prev_sib, source)
                    if text.startswith("/**") and text.endswith("*/"):
                        return self._clean_jsdoc(text)

        return None

    @staticmethod
    def _clean_jsdoc(text: str) -> str | None:
        """Clean a raw JSDoc string to plain text."""
        body = text[3:-2]
        cleaned = "\n".join(line.strip().lstrip("*").strip() for line in body.split("\n")).strip()
        return cleaned or None
