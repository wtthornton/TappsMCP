"""Tree-sitter based Go extractor."""

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
    import tree_sitter_go  # type: ignore[import-untyped]

    _GO_LANGUAGE = tree_sitter.Language(tree_sitter_go.language())
except ImportError:
    _GO_LANGUAGE = None


class GoExtractor(TreeSitterExtractor):
    """Extract symbols from Go source files using tree-sitter."""

    @property
    def file_extensions(self) -> frozenset[str]:
        return frozenset({".go"})

    @property
    def language_obj(self) -> Any:
        return _GO_LANGUAGE

    def can_handle(self, file_path: Any) -> bool:
        if _GO_LANGUAGE is None:
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

            if node_type == "package_clause":
                # Use package doc comment as module docstring.
                docstring = self._go_comment_before(child, source)

            elif node_type == "import_declaration":
                imports.append(self._node_text(child, source))

            elif node_type == "function_declaration":
                func = self._extract_function(child, source)
                if func:
                    functions.append(func)

            elif node_type == "method_declaration":
                func = self._extract_method(child, source)
                if func:
                    functions.append(func)

            elif node_type == "type_declaration":
                for spec in child.children:
                    if spec.type == "type_spec":
                        cls = self._extract_type_spec(spec, source)
                        if cls:
                            classes.append(cls)

            elif node_type in ("const_declaration", "var_declaration"):
                consts = self._extract_constants(child, source)
                constants.extend(consts)

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
        params = self._extract_go_params(node, source)
        ret = self._extract_go_return(node, source)
        doc = self._go_comment_before(node, source)

        return self._build_function(
            name=name,
            line=self._node_line(node),
            end_line=self._node_end_line(node),
            parameters=params,
            return_annotation=ret,
            docstring=doc,
        )

    def _extract_method(self, node: Any, source: bytes) -> FunctionInfo | None:
        """Extract a Go method (func (receiver) Name(...) ...)."""
        name_node = self._child_by_field(node, "name")
        if name_node is None:
            return None
        name = self._node_text(name_node, source)
        params = self._extract_go_params(node, source)
        ret = self._extract_go_return(node, source)
        doc = self._go_comment_before(node, source)

        # Include the receiver in the parameter list as first param.
        receiver_params: list[ParameterInfo] = []
        for child in node.children:
            if child.type == "parameter_list":
                # The first parameter_list is the receiver.
                for p in child.children:
                    if p.type == "parameter_declaration":
                        rp = self._parse_go_param(p, source)
                        if rp:
                            receiver_params.append(rp)
                break

        all_params = receiver_params + params

        return self._build_function(
            name=name,
            line=self._node_line(node),
            end_line=self._node_end_line(node),
            parameters=all_params,
            return_annotation=ret,
            docstring=doc,
        )

    # ------------------------------------------------------------------
    # Parameters
    # ------------------------------------------------------------------

    def _extract_go_params(self, node: Any, source: bytes) -> list[ParameterInfo]:
        """Extract parameters from a Go function's formal parameters."""
        params_node = self._child_by_field(node, "parameters")
        if params_node is None:
            return []

        result: list[ParameterInfo] = []
        for child in params_node.children:
            if child.type == "parameter_declaration":
                p = self._parse_go_param(child, source)
                if p:
                    result.append(p)
            elif child.type == "variadic_parameter_declaration":
                p = self._parse_go_param(child, source)
                if p:
                    result.append(p)
        return result

    def _parse_go_param(self, node: Any, source: bytes) -> ParameterInfo | None:
        """Parse a single Go parameter_declaration node."""
        name_node = self._child_by_field(node, "name")
        type_node = self._child_by_field(node, "type")
        name = self._node_text(name_node, source) if name_node else ""
        annotation = self._node_text(type_node, source) if type_node else None
        if not name and annotation:
            # Unnamed parameter — type only.
            name = annotation
            annotation = None
        return ParameterInfo(name=name, annotation=annotation) if name else None

    def _extract_go_return(self, node: Any, source: bytes) -> str | None:
        """Extract the return type from a Go function."""
        result_node = self._child_by_field(node, "result")
        if result_node is None:
            return None
        return self._node_text(result_node, source).strip() or None

    # ------------------------------------------------------------------
    # Types (struct / interface)
    # ------------------------------------------------------------------

    def _extract_type_spec(self, node: Any, source: bytes) -> ClassInfo | None:
        """Extract a type spec (struct or interface)."""
        name_node = self._child_by_field(node, "name")
        if name_node is None:
            return None
        name = self._node_text(name_node, source)
        doc = self._go_comment_before(node.parent, source)

        type_node = self._child_by_field(node, "type")
        methods: list[FunctionInfo] = []
        class_vars: list[ConstantInfo] = []

        if type_node is not None:
            if type_node.type == "struct_type":
                class_vars = self._extract_struct_fields(type_node, source)
            elif type_node.type == "interface_type":
                methods = self._extract_interface_methods(type_node, source)

        return self._build_class(
            name=name,
            line=self._node_line(node),
            end_line=self._node_end_line(node),
            docstring=doc,
            methods=methods,
            class_variables=class_vars,
        )

    def _extract_struct_fields(
        self, node: Any, source: bytes,
    ) -> list[ConstantInfo]:
        """Extract struct field declarations as ConstantInfo."""
        fields: list[ConstantInfo] = []
        for child in node.children:
            if child.type == "field_declaration_list":
                for fc in child.children:
                    if fc.type == "field_declaration":
                        name_node = self._child_by_field(fc, "name")
                        type_node = self._child_by_field(fc, "type")
                        if name_node:
                            name = self._node_text(name_node, source)
                            ann = self._node_text(type_node, source) if type_node else None
                            fields.append(ConstantInfo(
                                name=name,
                                line=self._node_line(fc),
                                annotation=ann,
                            ))
            elif child.type == "field_declaration":
                name_node = self._child_by_field(child, "name")
                type_node = self._child_by_field(child, "type")
                if name_node:
                    name = self._node_text(name_node, source)
                    ann = self._node_text(type_node, source) if type_node else None
                    fields.append(ConstantInfo(
                        name=name,
                        line=self._node_line(child),
                        annotation=ann,
                    ))
        return fields

    def _extract_interface_methods(
        self, node: Any, source: bytes,
    ) -> list[FunctionInfo]:
        """Extract interface method specs."""
        methods: list[FunctionInfo] = []
        for child in node.children:
            if child.type in ("method_spec", "method_elem"):
                name_node = self._child_by_field(child, "name")
                if name_node is None:
                    continue
                name = self._node_text(name_node, source)
                params = self._extract_go_params(child, source)
                ret = self._extract_go_return(child, source)
                methods.append(self._build_function(
                    name=name,
                    line=self._node_line(child),
                    parameters=params,
                    return_annotation=ret,
                ))
        return methods

    # ------------------------------------------------------------------
    # Constants
    # ------------------------------------------------------------------

    def _extract_constants(
        self, node: Any, source: bytes,
    ) -> list[ConstantInfo]:
        """Extract const/var declarations."""
        consts: list[ConstantInfo] = []
        for child in node.children:
            if child.type in ("const_spec", "var_spec"):
                name_node = self._child_by_field(child, "name")
                if name_node is None:
                    continue
                name = self._node_text(name_node, source)
                type_node = self._child_by_field(child, "type")
                val_node = self._child_by_field(child, "value")
                ann = self._node_text(type_node, source) if type_node else None
                val = self._node_text(val_node, source) if val_node else None
                consts.append(ConstantInfo(
                    name=name,
                    line=self._node_line(child),
                    value=val,
                    annotation=ann,
                ))
        return consts

    # ------------------------------------------------------------------
    # Go doc comments
    # ------------------------------------------------------------------

    def _go_comment_before(self, node: Any, source: bytes) -> str | None:
        """Collect ``//`` comment lines immediately before a Go definition."""
        return self._collect_comment_before(node, source, prefix="//")
