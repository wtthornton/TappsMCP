"""Tree-sitter based Java extractor."""

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

logger: structlog.stdlib.BoundLogger = structlog.get_logger()  # type: ignore[assignment]

try:
    import tree_sitter  # type: ignore[import-untyped]
    import tree_sitter_java  # type: ignore[import-untyped]

    _JAVA_LANGUAGE = tree_sitter.Language(tree_sitter_java.language())
except ImportError:
    _JAVA_LANGUAGE = None


class JavaExtractor(TreeSitterExtractor):
    """Extract symbols from Java source files using tree-sitter."""

    @property
    def file_extensions(self) -> frozenset[str]:
        return frozenset({".java"})

    @property
    def language_obj(self) -> Any:
        return _JAVA_LANGUAGE

    def can_handle(self, file_path: Any) -> bool:
        if _JAVA_LANGUAGE is None:
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

            if node_type == "package_declaration":
                docstring = self._javadoc_before(child, source)
                imports.append(self._node_text(child, source).rstrip(";"))

            elif node_type == "import_declaration":
                imports.append(self._node_text(child, source).rstrip(";"))

            elif node_type == "class_declaration":
                cls = self._extract_class(child, source)
                if cls:
                    classes.append(cls)

            elif node_type == "interface_declaration":
                cls = self._extract_interface(child, source)
                if cls:
                    classes.append(cls)

            elif node_type == "enum_declaration":
                cls = self._extract_enum(child, source)
                if cls:
                    classes.append(cls)

        return ModuleInfo(
            path=rel_path,
            docstring=docstring,
            imports=imports,
            functions=functions,
            classes=classes,
            constants=constants,
        )

    # ------------------------------------------------------------------
    # Classes
    # ------------------------------------------------------------------

    def _extract_class(self, node: Any, source: bytes) -> ClassInfo | None:
        name_node = self._child_by_field(node, "name")
        if name_node is None:
            return None
        name = self._node_text(name_node, source)
        doc = self._javadoc_before(node, source)

        bases: list[str] = []
        # Superclass.
        superclass = self._child_by_field(node, "superclass")
        if superclass:
            bases.append(self._node_text(superclass, source))
        # Interfaces (super_interfaces).
        for child in node.children:
            if child.type == "super_interfaces":
                for iface in child.children:
                    if iface.type == "type_list":
                        for t in iface.children:
                            if t.type == "type_identifier":
                                bases.append(self._node_text(t, source))

        methods: list[FunctionInfo] = []
        class_vars: list[ConstantInfo] = []
        body = self._child_by_field(node, "body")
        if body:
            self._extract_body_members(body, source, methods, class_vars)

        return self._build_class(
            name=name,
            line=self._node_line(node),
            end_line=self._node_end_line(node),
            bases=bases,
            docstring=doc,
            methods=methods,
            class_variables=class_vars,
        )

    def _extract_interface(self, node: Any, source: bytes) -> ClassInfo | None:
        name_node = self._child_by_field(node, "name")
        if name_node is None:
            return None
        name = self._node_text(name_node, source)
        doc = self._javadoc_before(node, source)

        bases: list[str] = []
        for child in node.children:
            if child.type == "extends_interfaces":
                for iface in child.children:
                    if iface.type == "type_list":
                        for t in iface.children:
                            if t.type == "type_identifier":
                                bases.append(self._node_text(t, source))

        methods: list[FunctionInfo] = []
        class_vars: list[ConstantInfo] = []
        body = self._child_by_field(node, "body")
        if body:
            self._extract_body_members(body, source, methods, class_vars)

        return self._build_class(
            name=name,
            line=self._node_line(node),
            end_line=self._node_end_line(node),
            bases=bases,
            docstring=doc,
            methods=methods,
            class_variables=class_vars,
        )

    def _extract_enum(self, node: Any, source: bytes) -> ClassInfo | None:
        name_node = self._child_by_field(node, "name")
        if name_node is None:
            return None
        name = self._node_text(name_node, source)
        doc = self._javadoc_before(node, source)

        variants: list[ConstantInfo] = []
        body = self._child_by_field(node, "body")
        if body:
            for child in body.children:
                if child.type == "enum_constant":
                    vname_node = self._child_by_field(child, "name")
                    if vname_node:
                        vname = self._node_text(vname_node, source)
                        variants.append(ConstantInfo(
                            name=vname, line=self._node_line(child),
                        ))

        return self._build_class(
            name=name,
            line=self._node_line(node),
            end_line=self._node_end_line(node),
            docstring=doc,
            class_variables=variants,
        )

    # ------------------------------------------------------------------
    # Body members
    # ------------------------------------------------------------------

    def _extract_body_members(
        self,
        body: Any,
        source: bytes,
        methods: list[FunctionInfo],
        class_vars: list[ConstantInfo],
    ) -> None:
        """Extract methods and fields from a class/interface body."""
        for child in body.children:
            if child.type == "method_declaration":
                m = self._extract_method(child, source)
                if m:
                    methods.append(m)
            elif child.type == "constructor_declaration":
                m = self._extract_constructor(child, source)
                if m:
                    methods.append(m)
            elif child.type == "field_declaration":
                fields = self._extract_field(child, source)
                class_vars.extend(fields)
            elif child.type == "class_declaration":
                # Nested class — skip for now.
                pass
            elif child.type == "interface_declaration":
                pass

    # ------------------------------------------------------------------
    # Methods
    # ------------------------------------------------------------------

    def _extract_method(self, node: Any, source: bytes) -> FunctionInfo | None:
        name_node = self._child_by_field(node, "name")
        if name_node is None:
            return None
        name = self._node_text(name_node, source)
        params = self._extract_java_params(node, source)
        ret = self._extract_java_return_type(node, source)
        doc = self._javadoc_before(node, source)

        return self._build_function(
            name=name,
            line=self._node_line(node),
            end_line=self._node_end_line(node),
            parameters=params,
            return_annotation=ret,
            docstring=doc,
        )

    def _extract_constructor(self, node: Any, source: bytes) -> FunctionInfo | None:
        name_node = self._child_by_field(node, "name")
        if name_node is None:
            return None
        name = self._node_text(name_node, source)
        params = self._extract_java_params(node, source)
        doc = self._javadoc_before(node, source)

        return self._build_function(
            name=name,
            line=self._node_line(node),
            end_line=self._node_end_line(node),
            parameters=params,
            docstring=doc,
        )

    # ------------------------------------------------------------------
    # Parameters
    # ------------------------------------------------------------------

    def _extract_java_params(self, node: Any, source: bytes) -> list[ParameterInfo]:
        """Extract parameters from a Java method."""
        params_node = self._child_by_field(node, "parameters")
        if params_node is None:
            return []

        result: list[ParameterInfo] = []
        for child in params_node.children:
            if child.type == "formal_parameter":
                p = self._parse_java_param(child, source)
                if p:
                    result.append(p)
            elif child.type == "spread_parameter":
                p = self._parse_java_param(child, source)
                if p:
                    result.append(p)
        return result

    def _parse_java_param(self, node: Any, source: bytes) -> ParameterInfo | None:
        """Parse a single Java parameter."""
        name_node = self._child_by_field(node, "name")
        type_node = self._child_by_field(node, "type")
        if name_node is None:
            return None
        name = self._node_text(name_node, source)
        annotation = self._node_text(type_node, source) if type_node else None
        return ParameterInfo(name=name, annotation=annotation)

    def _extract_java_return_type(self, node: Any, source: bytes) -> str | None:
        """Extract the return type from a Java method."""
        type_node = self._child_by_field(node, "type")
        if type_node is None:
            return None
        text = self._node_text(type_node, source)
        return text.strip() if text.strip() != "void" else "void"

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------

    def _extract_field(self, node: Any, source: bytes) -> list[ConstantInfo]:
        """Extract field declarations from a Java class."""
        fields: list[ConstantInfo] = []
        type_node = self._child_by_field(node, "type")
        annotation = self._node_text(type_node, source) if type_node else None

        for child in node.children:
            if child.type == "variable_declarator":
                name_node = self._child_by_field(child, "name")
                if name_node is None:
                    continue
                name = self._node_text(name_node, source)
                val_node = self._child_by_field(child, "value")
                value = self._node_text(val_node, source) if val_node else None
                fields.append(ConstantInfo(
                    name=name,
                    line=self._node_line(node),
                    value=value,
                    annotation=annotation,
                ))
        return fields

    # ------------------------------------------------------------------
    # Javadoc
    # ------------------------------------------------------------------

    def _javadoc_before(self, node: Any, source: bytes) -> str | None:
        """Extract a Javadoc comment (/** ... */) preceding *node*."""
        return self._extract_block_comment_before(node, source)
