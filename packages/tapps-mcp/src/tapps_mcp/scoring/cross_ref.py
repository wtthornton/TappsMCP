"""AST-based cross-file reference analyzer for detecting kwarg mismatches.

Performs lightweight cross-file type checking by:
1. Extracting function/method calls with keyword arguments from a source file
2. Resolving callee definitions via import path analysis
3. Comparing caller kwargs against callee parameter names
4. Flagging mismatches as potential type errors

This is intentionally best-effort — it catches the 80% case (wrong kwarg names)
without replicating mypy's full type system. Results are marked with confidence
levels to indicate analysis reliability.

Story 75.2: Cross-file type error detection in quick_check.
"""

from __future__ import annotations

import ast
import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CrossRefFinding:
    """A potential cross-file type error finding."""

    caller_file: str
    caller_line: int
    callee_name: str
    callee_file: str | None
    issue: str
    confidence: str  # "high", "medium", "low"
    caller_kwargs: list[str] = field(default_factory=list)
    callee_params: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for API response."""
        return {
            "caller_file": self.caller_file,
            "caller_line": self.caller_line,
            "callee_name": self.callee_name,
            "callee_file": self.callee_file,
            "issue": self.issue,
            "confidence": self.confidence,
            "caller_kwargs": self.caller_kwargs,
            "callee_params": self.callee_params,
        }


@dataclass
class CrossRefResult:
    """Result of cross-file reference analysis."""

    findings: list[CrossRefFinding] = field(default_factory=list)
    status: str = "full"  # "full", "partial", "degraded"
    files_resolved: int = 0
    files_unresolved: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for API response."""
        return {
            "cross_file_analysis": self.status,
            "findings_count": len(self.findings),
            "findings": [f.to_dict() for f in self.findings],
            "files_resolved": self.files_resolved,
            "files_unresolved": self.files_unresolved,
        }


def _extract_imports(tree: ast.Module) -> dict[str, str]:
    """Extract import mappings: name -> module path.

    Handles both ``import foo`` and ``from foo import bar`` forms.
    """
    imports: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name
                imports[name] = alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                name = alias.asname or alias.name
                imports[name] = f"{module}.{alias.name}" if module else alias.name
    return imports


def _extract_call_kwargs(tree: ast.Module) -> list[dict[str, Any]]:
    """Extract function/method calls that use keyword arguments."""
    calls: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        kwargs = [kw.arg for kw in node.keywords if kw.arg is not None]
        if not kwargs:
            continue

        # Determine the callee name
        callee_name = _resolve_callee_name(node.func)
        if not callee_name:
            continue

        calls.append({
            "callee_name": callee_name,
            "kwargs": kwargs,
            "line": node.lineno,
        })
    return calls


def _resolve_callee_name(func_node: ast.expr) -> str | None:
    """Resolve a call target to a dotted name string."""
    if isinstance(func_node, ast.Name):
        return func_node.id
    if isinstance(func_node, ast.Attribute):
        # e.g. obj.method() or module.func()
        value_name = _resolve_callee_name(func_node.value)
        if value_name:
            return f"{value_name}.{func_node.attr}"
        return func_node.attr
    return None


def _resolve_module_file(module_path: str, search_root: Path) -> Path | None:
    """Try to find the source file for a module path.

    Uses importlib.util.find_spec first, then falls back to file-system search
    relative to the search root.
    """
    # Try importlib first (works when package is installed/importable)
    try:
        spec = importlib.util.find_spec(module_path)
        if spec and spec.origin and spec.origin.endswith(".py"):
            return Path(spec.origin)
    except (ModuleNotFoundError, ValueError, AttributeError):
        pass

    # Fall back to file-system heuristic
    parts = module_path.split(".")
    # Try as a direct module file
    candidate = search_root / Path(*parts[:-1]) / f"{parts[-1]}.py" if len(parts) > 1 else None
    if candidate and candidate.is_file():
        return candidate

    # Try the module path as a package
    for i in range(len(parts), 0, -1):
        candidate = search_root / Path(*parts[:i]).with_suffix(".py")
        if candidate.is_file():
            return candidate
        # Try as __init__.py inside package dir
        candidate = search_root / Path(*parts[:i]) / "__init__.py"
        if candidate.is_file():
            return candidate

    return None


def _extract_function_params(
    tree: ast.Module, func_name: str,
) -> list[str] | None:
    """Extract parameter names from a function/method definition.

    Returns None if the function is not found.
    Returns parameter names excluding 'self' and 'cls'.
    """
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name != func_name:
                continue
            params: list[str] = []
            for arg in node.args.args:
                name = arg.arg
                if name not in ("self", "cls"):
                    params.append(name)
            # Check for **kwargs — if present, any kwarg is valid
            if node.args.kwarg is not None:
                return None  # Signals "accepts any kwargs"
            return params
    return None


def _has_var_keyword(tree: ast.Module, func_name: str) -> bool:
    """Check if a function accepts **kwargs."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == func_name and node.args.kwarg is not None:
                return True
    return False


def analyze_cross_references(
    file_path: Path,
    project_root: Path | None = None,
) -> CrossRefResult:
    """Analyze a Python file for cross-file kwarg mismatches.

    Args:
        file_path: Path to the Python source file to analyze.
        project_root: Project root for resolving imports. Defaults to file's parent.

    Returns:
        CrossRefResult with findings and analysis status.
    """
    result = CrossRefResult()

    if not file_path.suffix == ".py" or not file_path.is_file():
        result.status = "degraded"
        return result

    search_root = project_root or file_path.parent

    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, OSError) as exc:
        logger.debug("cross_ref_parse_failed", file=str(file_path), error=str(exc))
        result.status = "degraded"
        return result

    imports = _extract_imports(tree)
    calls = _extract_call_kwargs(tree)

    if not calls:
        return result

    # Cache parsed callee files to avoid re-reading
    callee_cache: dict[str, ast.Module | None] = {}

    for call in calls:
        callee_name: str = call["callee_name"]
        kwargs: list[str] = call["kwargs"]
        line: int = call["line"]

        # Resolve the function name to a module
        # For "obj.method()" we need the base object's type
        parts = callee_name.split(".")
        base_name = parts[0]
        method_name = parts[-1] if len(parts) > 1 else base_name

        # Try to find the module for the base name
        module_path = imports.get(base_name)
        if not module_path:
            result.files_unresolved += 1
            continue

        # Resolve to file
        callee_file = _resolve_module_file(module_path, search_root)

        # For "from module import Class" followed by Class.method(),
        # we need to find the method in the class
        if callee_file is None:
            # Try parent module
            parent_module = ".".join(module_path.split(".")[:-1])
            if parent_module:
                callee_file = _resolve_module_file(parent_module, search_root)

        if callee_file is None:
            result.files_unresolved += 1
            continue

        result.files_resolved += 1

        # Parse callee file (cached)
        callee_key = str(callee_file)
        if callee_key not in callee_cache:
            try:
                callee_source = callee_file.read_text(encoding="utf-8")
                callee_cache[callee_key] = ast.parse(callee_source)
            except (SyntaxError, OSError):
                callee_cache[callee_key] = None

        callee_tree = callee_cache.get(callee_key)
        if callee_tree is None:
            continue

        # Extract the function/method parameters
        params = _extract_function_params(callee_tree, method_name)

        if params is None:
            # Function not found or accepts **kwargs — skip
            continue

        # Compare caller kwargs against callee params
        mismatched = [k for k in kwargs if k not in params]
        if mismatched:
            result.findings.append(
                CrossRefFinding(
                    caller_file=str(file_path),
                    caller_line=line,
                    callee_name=callee_name,
                    callee_file=callee_key,
                    issue=f"Unexpected keyword argument(s): {', '.join(mismatched)}",
                    confidence="medium",
                    caller_kwargs=kwargs,
                    callee_params=params,
                )
            )

    # Determine analysis status
    if result.files_unresolved > 0 and result.files_resolved == 0:
        result.status = "degraded"
    elif result.files_unresolved > 0:
        result.status = "partial"
    else:
        result.status = "full"

    return result
