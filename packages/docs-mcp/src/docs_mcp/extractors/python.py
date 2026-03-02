"""Python AST-based source code extractor."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pathlib import Path

from docs_mcp.extractors.models import (
    ClassInfo,
    ConstantInfo,
    DecoratorInfo,
    FunctionInfo,
    ModuleInfo,
    ParameterInfo,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()  # type: ignore[assignment]

_PYTHON_SUFFIXES = frozenset({".py", ".pyi"})


class PythonExtractor:
    """Extracts structured information from Python source files using the AST."""

    def can_handle(self, file_path: Path) -> bool:
        """Return True for .py and .pyi files."""
        return file_path.suffix in _PYTHON_SUFFIXES

    def extract(self, file_path: Path, *, project_root: Path | None = None) -> ModuleInfo:
        """Extract module information from a Python file.

        Never raises on malformed input — returns degraded ModuleInfo instead.
        """
        rel_path = self._relative_path(file_path, project_root)

        try:
            source = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                source = file_path.read_text(encoding="latin-1")
            except Exception:
                logger.warning("encoding_error", path=str(file_path))
                return ModuleInfo(path=rel_path)
        except OSError:
            logger.warning("read_error", path=str(file_path))
            return ModuleInfo(path=rel_path)

        try:
            tree = ast.parse(source, filename=str(file_path), type_comments=True)
        except SyntaxError:
            logger.warning("syntax_error", path=str(file_path))
            return ModuleInfo(path=rel_path)

        return self._extract_module(tree, rel_path)

    # ------------------------------------------------------------------
    # Module-level extraction
    # ------------------------------------------------------------------

    def _extract_module(self, tree: ast.Module, path: str) -> ModuleInfo:
        """Extract all information from a parsed module AST."""
        functions: list[FunctionInfo] = []
        classes: list[ClassInfo] = []
        constants: list[ConstantInfo] = []
        imports: list[str] = []
        has_main_block = False
        all_exports: list[str] | None = None

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(self._extract_function(node))
            elif isinstance(node, ast.ClassDef):
                classes.append(self._extract_class(node))
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(self._format_import(node))
            elif isinstance(node, ast.Assign):
                consts = self._extract_assign_constants(node)
                constants.extend(consts)
                if all_exports is None:
                    all_exports = self._try_extract_all(node)
            elif isinstance(node, ast.AnnAssign):
                const = self._extract_ann_assign_constant(node)
                if const is not None:
                    constants.append(const)
            elif isinstance(node, ast.If) and self._is_main_block(node):
                has_main_block = True

        return ModuleInfo(
            path=path,
            docstring=ast.get_docstring(tree),
            imports=imports,
            functions=functions,
            classes=classes,
            constants=constants,
            has_main_block=has_main_block,
            all_exports=all_exports,
        )

    # ------------------------------------------------------------------
    # Function extraction
    # ------------------------------------------------------------------

    def _extract_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> FunctionInfo:
        """Extract information from a function or async function definition."""
        decorators = [self._extract_decorator(d) for d in node.decorator_list]
        parameters = self._extract_parameters(node.args)
        return_annotation = (
            ast.unparse(node.returns) if node.returns is not None else None
        )
        signature = self._build_signature(node, parameters, return_annotation)

        return FunctionInfo(
            name=node.name,
            line=node.lineno,
            end_line=node.end_lineno,
            signature=signature,
            parameters=parameters,
            return_annotation=return_annotation,
            decorators=decorators,
            docstring=ast.get_docstring(node),
            is_async=isinstance(node, ast.AsyncFunctionDef),
            is_property=any(d.name == "property" for d in decorators),
            is_staticmethod=any(d.name == "staticmethod" for d in decorators),
            is_classmethod=any(d.name == "classmethod" for d in decorators),
            is_abstractmethod=any(d.name == "abstractmethod" for d in decorators),
        )

    def _extract_parameters(self, args: ast.arguments) -> list[ParameterInfo]:
        """Extract parameter information from function arguments."""
        params: list[ParameterInfo] = []

        # Positional-only parameters
        for i, arg in enumerate(args.posonlyargs):
            default = self._get_positional_default(
                i, args.posonlyargs, args.args, args.defaults
            )
            params.append(
                ParameterInfo(
                    name=arg.arg,
                    annotation=ast.unparse(arg.annotation) if arg.annotation else None,
                    default=default,
                    kind="POSITIONAL_ONLY",
                )
            )

        # Regular positional-or-keyword parameters
        for i, arg in enumerate(args.args):
            default = self._get_positional_default(
                len(args.posonlyargs) + i, args.posonlyargs, args.args, args.defaults
            )
            params.append(
                ParameterInfo(
                    name=arg.arg,
                    annotation=ast.unparse(arg.annotation) if arg.annotation else None,
                    default=default,
                    kind="POSITIONAL_OR_KEYWORD",
                )
            )

        # *args
        if args.vararg:
            params.append(
                ParameterInfo(
                    name=args.vararg.arg,
                    annotation=(
                        ast.unparse(args.vararg.annotation)
                        if args.vararg.annotation
                        else None
                    ),
                    kind="VAR_POSITIONAL",
                )
            )

        # Keyword-only parameters
        for i, arg in enumerate(args.kwonlyargs):
            default = None
            if i < len(args.kw_defaults) and args.kw_defaults[i] is not None:
                default = ast.unparse(args.kw_defaults[i])  # type: ignore[arg-type]
            params.append(
                ParameterInfo(
                    name=arg.arg,
                    annotation=ast.unparse(arg.annotation) if arg.annotation else None,
                    default=default,
                    kind="KEYWORD_ONLY",
                )
            )

        # **kwargs
        if args.kwarg:
            params.append(
                ParameterInfo(
                    name=args.kwarg.arg,
                    annotation=(
                        ast.unparse(args.kwarg.annotation)
                        if args.kwarg.annotation
                        else None
                    ),
                    kind="VAR_KEYWORD",
                )
            )

        return params

    def _get_positional_default(
        self,
        index: int,
        posonlyargs: list[ast.arg],
        args: list[ast.arg],
        defaults: list[ast.expr],
    ) -> str | None:
        """Get the default value for a positional parameter, if any."""
        total_positional = len(posonlyargs) + len(args)
        default_offset = total_positional - len(defaults)
        default_index = index - default_offset
        if default_index >= 0 and default_index < len(defaults):
            return ast.unparse(defaults[default_index])
        return None

    def _build_signature(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        parameters: list[ParameterInfo],
        return_annotation: str | None,
    ) -> str:
        """Build a full signature string from extracted parameters."""
        parts: list[str] = []
        has_posonly = any(p.kind == "POSITIONAL_ONLY" for p in parameters)
        seen_kwonly = False

        for param in parameters:
            if param.kind == "VAR_POSITIONAL":
                part = f"*{param.name}"
                if param.annotation:
                    part = f"*{param.name}: {param.annotation}"
                parts.append(part)
                seen_kwonly = True
            elif param.kind == "VAR_KEYWORD":
                part = f"**{param.name}"
                if param.annotation:
                    part = f"**{param.name}: {param.annotation}"
                parts.append(part)
            elif param.kind == "KEYWORD_ONLY" and not seen_kwonly:
                # Insert bare * before first keyword-only if no *args
                parts.append("*")
                seen_kwonly = True
                parts.append(self._format_param(param))
            else:
                if has_posonly and param.kind == "POSITIONAL_OR_KEYWORD":
                    # Insert / separator after positional-only params
                    if parts and all(
                        p.kind == "POSITIONAL_ONLY"
                        for p in parameters[: len(parts)]
                    ):
                        parts.append("/")
                    has_posonly = False
                parts.append(self._format_param(param))

        # Handle trailing / for positional-only only params
        if has_posonly and all(p.kind == "POSITIONAL_ONLY" for p in parameters):
            parts.append("/")

        params_str = ", ".join(parts)
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        ret = f" -> {return_annotation}" if return_annotation else ""
        return f"{prefix} {node.name}({params_str}){ret}:"

    @staticmethod
    def _format_param(param: ParameterInfo) -> str:
        """Format a single parameter for signature display."""
        result = param.name
        if param.annotation:
            result = f"{param.name}: {param.annotation}"
        if param.default is not None:
            if param.annotation:
                result = f"{result} = {param.default}"
            else:
                result = f"{result}={param.default}"
        return result

    # ------------------------------------------------------------------
    # Class extraction
    # ------------------------------------------------------------------

    def _extract_class(self, node: ast.ClassDef) -> ClassInfo:
        """Extract information from a class definition."""
        decorators = [self._extract_decorator(d) for d in node.decorator_list]
        bases = [ast.unparse(base) for base in node.bases]

        methods: list[FunctionInfo] = []
        class_variables: list[ConstantInfo] = []

        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(self._extract_function(child))
            elif isinstance(child, ast.Assign):
                class_variables.extend(self._extract_assign_constants(child))
            elif isinstance(child, ast.AnnAssign):
                const = self._extract_ann_assign_constant(child)
                if const is not None:
                    class_variables.append(const)

        return ClassInfo(
            name=node.name,
            line=node.lineno,
            end_line=node.end_lineno,
            bases=bases,
            decorators=decorators,
            docstring=ast.get_docstring(node),
            methods=methods,
            class_variables=class_variables,
        )

    # ------------------------------------------------------------------
    # Decorator extraction
    # ------------------------------------------------------------------

    def _extract_decorator(self, node: ast.expr) -> DecoratorInfo:
        """Extract decorator name and arguments from a decorator AST node."""
        if isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            # Reconstruct arguments string
            arg_parts: list[str] = []
            for arg in node.args:
                arg_parts.append(ast.unparse(arg))
            for kw in node.keywords:
                if kw.arg is not None:
                    arg_parts.append(f"{kw.arg}={ast.unparse(kw.value)}")
                else:
                    arg_parts.append(f"**{ast.unparse(kw.value)}")
            arguments = ", ".join(arg_parts) if arg_parts else None
            return DecoratorInfo(name=name, arguments=arguments, line=node.lineno)

        name = ast.unparse(node)
        return DecoratorInfo(name=name, line=node.lineno)

    # ------------------------------------------------------------------
    # Constant / variable extraction
    # ------------------------------------------------------------------

    def _extract_assign_constants(self, node: ast.Assign) -> list[ConstantInfo]:
        """Extract constants from an assignment statement."""
        constants: list[ConstantInfo] = []
        value_str = ast.unparse(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                constants.append(
                    ConstantInfo(
                        name=target.id,
                        line=node.lineno,
                        value=value_str,
                    )
                )
        return constants

    def _extract_ann_assign_constant(self, node: ast.AnnAssign) -> ConstantInfo | None:
        """Extract a constant from an annotated assignment."""
        if not isinstance(node.target, ast.Name):
            return None
        return ConstantInfo(
            name=node.target.id,
            line=node.lineno,
            value=ast.unparse(node.value) if node.value is not None else None,
            annotation=ast.unparse(node.annotation),
        )

    # ------------------------------------------------------------------
    # Import extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _format_import(node: ast.Import | ast.ImportFrom) -> str:
        """Format an import statement back to source text."""
        return ast.unparse(node)

    # ------------------------------------------------------------------
    # __all__ and __main__ detection
    # ------------------------------------------------------------------

    @staticmethod
    def _try_extract_all(node: ast.Assign) -> list[str] | None:
        """Try to extract __all__ from an assignment node."""
        for target in node.targets:
            if (
                isinstance(target, ast.Name)
                and target.id == "__all__"
                and isinstance(node.value, (ast.List, ast.Tuple))
            ):
                names: list[str] = []
                for elt in node.value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(
                        elt.value, str
                    ):
                        names.append(elt.value)
                return names
        return None

    @staticmethod
    def _is_main_block(node: ast.If) -> bool:
        """Check if an if-statement is ``if __name__ == '__main__':``."""
        test = node.test
        if not isinstance(test, ast.Compare):
            return False
        if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
            return False
        if len(test.comparators) != 1:
            return False

        left = test.left
        right = test.comparators[0]

        # __name__ == "__main__"
        if (
            isinstance(left, ast.Name)
            and left.id == "__name__"
            and isinstance(right, ast.Constant)
            and right.value == "__main__"
        ):
            return True

        # "__main__" == __name__
        return (
            isinstance(right, ast.Name)
            and right.id == "__name__"
            and isinstance(left, ast.Constant)
            and left.value == "__main__"
        )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _relative_path(file_path: Path, project_root: Path | None) -> str:
        """Make a path relative to project_root if provided."""
        if project_root is not None:
            try:
                return str(file_path.relative_to(project_root))
            except ValueError:
                pass
        return str(file_path)
