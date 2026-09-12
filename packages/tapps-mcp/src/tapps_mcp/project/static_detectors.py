"""Static detectors for two validation-checklist gaps (CB lane L3):

- ``declared-uncalled`` (VAL-04): a production constant or function that has
  zero non-test references anywhere in the package.
- ``consumed-no-producer`` (VAL-05): a dataclass-shaped field that some
  non-test consumer reads, but no non-test producer ever assigns.

Engine-reuse decision (see ``docs/adr/0017`` for the call-graph contract):
``build_call_graph_index`` (Epic 114 / ADR-0017) indexes only *resolved
function/method CALL edges* — it has no representation for a module-level
constant, and no representation for attribute assignment vs. attribute read
(what VAL-05 needs). Reusing it for the constant half of VAL-04 is not
possible; reusing it for the function half is possible but narrower than
what VAL-04 needs: a function referenced only as a value (passed to a
registry, stored as a callback, imported and aliased) has no CALL edge at
all, so keying VAL-04 purely off ``callers_of`` would misreport a
still-referenced function as "uncalled". Both detectors therefore share one
new, deliberately small AST reference index (Name-Load and Attribute-Load
identifiers, plus Store/keyword sites for VAL-05) built once per run over
the ``tapps-mcp`` package — not a parallel copy of the call-graph engine,
since it answers a different question (identifier reference presence, not
resolved call-edge presence) that the call graph cannot answer for either
detector.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from tapps_mcp.tools.vulture import collect_python_files

_PACKAGE_DIR = "packages/tapps-mcp"
_PACKAGE_SRC_PREFIX = f"{_PACKAGE_DIR}/src/tapps_mcp/"

VALID_MODES = ("declared-uncalled", "consumed-no-producer")


@dataclass
class Finding:
    kind: str  # "constant" | "function" | "field"
    name: str
    file_path: str
    line: int
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "name": self.name,
            "file_path": self.file_path,
            "line": self.line,
            "reason": self.reason,
        }


@dataclass
class DetectorResult:
    mode: str
    population: str
    examined: int
    findings: list[Finding] = field(default_factory=list)

    @property
    def flagged(self) -> int:
        return len(self.findings)

    @property
    def fire_rate(self) -> float:
        return (self.flagged / self.examined) if self.examined else 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "population": self.population,
            "examined": self.examined,
            "flagged": self.flagged,
            "fire_rate": round(self.fire_rate, 4),
            "findings": [f.to_dict() for f in self.findings],
        }


def _is_test_rel_path(rel_posix: str) -> bool:
    parts = rel_posix.split("/")
    name = parts[-1]
    return "tests" in parts or name.startswith("test_") or name.endswith("_test.py")


def _in_production_scope(rel_posix: str) -> bool:
    return rel_posix.startswith(_PACKAGE_SRC_PREFIX) and not _is_test_rel_path(rel_posix)


def _in_package_scope(rel_posix: str) -> bool:
    return rel_posix.startswith(f"{_PACKAGE_DIR}/")


def _parse(root: Path, rel_posix: str) -> ast.Module | None:
    try:
        source = (root / rel_posix).read_text(encoding="utf-8")
        return ast.parse(source, filename=rel_posix)
    except (SyntaxError, UnicodeDecodeError, OSError):
        return None


def _is_literal(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
        return all(_is_literal(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(v is not None and _is_literal(v) for v in node.values)
    return False


@dataclass
class _ReferenceIndex:
    """Identifier -> set of rel_posix files referencing it, split by role.

    ``loaded``: ``Name``/``Attribute`` nodes in ``Load`` context (a read or a
    call). ``stored``: ``Attribute`` nodes in ``Store`` context
    (``obj.field = ...``). ``kwarg``: names used as a call keyword argument
    (``Cls(field=...)``) — dataclass construction is how most fields are
    actually produced, not attribute assignment.
    """

    loaded: dict[str, set[str]] = field(default_factory=dict)
    stored: dict[str, set[str]] = field(default_factory=dict)
    kwarg: dict[str, set[str]] = field(default_factory=dict)

    def _add(self, table: dict[str, set[str]], name: str, rel_posix: str) -> None:
        table.setdefault(name, set()).add(rel_posix)

    def record(self, node: ast.AST, rel_posix: str) -> None:
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            self._add(self.loaded, node.id, rel_posix)
        elif isinstance(node, ast.Attribute):
            if isinstance(node.ctx, ast.Load):
                self._add(self.loaded, node.attr, rel_posix)
            elif isinstance(node.ctx, ast.Store):
                self._add(self.stored, node.attr, rel_posix)
        elif isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg:
                    self._add(self.kwarg, kw.arg, rel_posix)


def _build_reference_index(root: Path, files: list[str]) -> _ReferenceIndex:
    idx = _ReferenceIndex()
    for rel_posix in files:
        tree = _parse(root, rel_posix)
        if tree is None:
            continue
        for node in ast.walk(tree):
            idx.record(node, rel_posix)
    return idx


def _package_files(root: Path) -> list[str]:
    return [
        rel.replace("\\", "/")
        for rel in collect_python_files(root)
        if _in_package_scope(rel.replace("\\", "/"))
    ]


# ---------------------------------------------------------------------------
# VAL-04: declared-uncalled
# ---------------------------------------------------------------------------


def _iter_production_module_bodies(
    root: Path, files: list[str]
) -> list[tuple[str, list[ast.stmt]]]:
    """Yield (rel_posix, module.body) for every parseable production-scope file."""
    bodies: list[tuple[str, list[ast.stmt]]] = []
    for rel_posix in files:
        if not _in_production_scope(rel_posix):
            continue
        tree = _parse(root, rel_posix)
        if tree is not None:
            bodies.append((rel_posix, tree.body))
    return bodies


def _module_constant_name(node: ast.stmt) -> str | None:
    """Return the constant name for an ``ALL_CAPS = <literal>``-shaped
    top-level statement, else ``None``."""
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        tgt = node.targets[0]
        if isinstance(tgt, ast.Name) and tgt.id.isupper() and _is_literal(node.value):
            return tgt.id
    elif (
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id.isupper()
        and node.value is not None
        and _is_literal(node.value)
    ):
        return node.target.id
    return None


def _find_module_constants(root: Path, files: list[str]) -> list[tuple[str, str, int]]:
    found: list[tuple[str, str, int]] = []
    for rel_posix, body in _iter_production_module_bodies(root, files):
        for node in body:
            name = _module_constant_name(node)
            if name is not None:
                found.append((name, rel_posix, node.lineno))
    return found


def _find_module_functions(root: Path, files: list[str]) -> list[tuple[str, str, int]]:
    found: list[tuple[str, str, int]] = []
    for rel_posix, body in _iter_production_module_bodies(root, files):
        for node in body:
            if isinstance(
                node, ast.FunctionDef | ast.AsyncFunctionDef
            ) and not node.name.startswith("_"):
                found.append((node.name, rel_posix, node.lineno))
    return found


def run_declared_uncalled(root: Path) -> DetectorResult:
    files = _package_files(root)
    idx = _build_reference_index(root, files)

    constants = _find_module_constants(root, files)
    functions = _find_module_functions(root, files)

    findings: list[Finding] = []
    for name, decl_file, line in constants:
        referencing = idx.loaded.get(name, set())
        non_test_refs = {f for f in referencing if not _is_test_rel_path(f)}
        if not non_test_refs:
            findings.append(
                Finding(
                    kind="constant",
                    name=name,
                    file_path=decl_file,
                    line=line,
                    reason="zero non-test references",
                )
            )

    for name, decl_file, line in functions:
        referencing = idx.loaded.get(name, set())
        non_test_refs = {f for f in referencing if not _is_test_rel_path(f)}
        # A function's own definition file trivially "loads" its own name if
        # it is referenced by other code in the same file; that is a genuine
        # non-test in-repo use, so it is intentionally NOT excluded here.
        if not non_test_refs:
            findings.append(
                Finding(
                    kind="function",
                    name=name,
                    file_path=decl_file,
                    line=line,
                    reason="zero non-test call sites",
                )
            )

    examined = len(constants) + len(functions)
    population = (
        "every top-level ALL_CAPS literal constant and every top-level, "
        "non-underscore-prefixed function defined directly under "
        f"{_PACKAGE_SRC_PREFIX} (excluding tests/ and vendored code)"
    )
    return DetectorResult(
        mode="declared-uncalled", population=population, examined=examined, findings=findings
    )


# ---------------------------------------------------------------------------
# VAL-05: consumed-no-producer
# ---------------------------------------------------------------------------


def _is_dataclass_decorated(node: ast.ClassDef) -> bool:
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Name) and target.id == "dataclass":
            return True
        if isinstance(target, ast.Attribute) and target.attr == "dataclass":
            return True
    return False


def _find_dataclass_fields(root: Path, files: list[str]) -> list[tuple[str, str, str, int]]:
    """Return (class_name, field_name, rel_path, line) for fields declared
    with no default value (``field: Type``) directly in a ``@dataclass``
    class body."""
    found: list[tuple[str, str, str, int]] = []
    for rel_posix in files:
        if not _in_production_scope(rel_posix):
            continue
        tree = _parse(root, rel_posix)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not _is_dataclass_decorated(node):
                continue
            for stmt in node.body:
                if (
                    isinstance(stmt, ast.AnnAssign)
                    and isinstance(stmt.target, ast.Name)
                    and stmt.value is None
                ):
                    found.append((node.name, stmt.target.id, rel_posix, stmt.lineno))
    return found


def run_consumed_no_producer(root: Path) -> DetectorResult:
    files = _package_files(root)
    idx = _build_reference_index(root, files)

    fields = _find_dataclass_fields(root, files)
    findings: list[Finding] = []
    for class_name, field_name, decl_file, line in fields:
        consumers = {f for f in idx.loaded.get(field_name, set()) if not _is_test_rel_path(f)}
        producers = {
            f
            for f in (idx.stored.get(field_name, set()) | idx.kwarg.get(field_name, set()))
            if not _is_test_rel_path(f)
        }
        if consumers and not producers:
            findings.append(
                Finding(
                    kind="field",
                    name=f"{class_name}.{field_name}",
                    file_path=decl_file,
                    line=line,
                    reason="read by a non-test consumer, assigned by no non-test producer",
                )
            )

    examined = len(fields)
    population = (
        "every field declared with no default value directly in the body of a "
        f"@dataclass-decorated class under {_PACKAGE_SRC_PREFIX} (excluding "
        "tests/ and vendored code)"
    )
    return DetectorResult(
        mode="consumed-no-producer", population=population, examined=examined, findings=findings
    )


def run_static_detector(mode: str, root: Path) -> DetectorResult:
    if mode == "declared-uncalled":
        return run_declared_uncalled(root)
    if mode == "consumed-no-producer":
        return run_consumed_no_producer(root)
    raise ValueError(f"mode must be one of {VALID_MODES}, got {mode!r}")


async def run_static_detector_tool(mode: str, project_root: str = "") -> dict[str, object]:
    """MCP-facing glue for ``tapps_static_detectors`` (kept out of the
    already-oversized ``server_analysis_tools.py`` to avoid growing that
    file's blast radius further — see its thin delegator)."""
    import asyncio
    import time

    from tapps_core.config.settings import load_settings
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges
    from tapps_mcp.server_helpers import error_response, success_response
    from tapps_mcp.tools.event_loop_guard import heavy_cpu
    from tapps_mcp.tools.project_paths import resolve_effective_project_root

    start = time.perf_counter_ns()
    _record_call("tapps_static_detectors")

    normalized_mode = mode.strip().lower()
    if normalized_mode not in VALID_MODES:
        return error_response(
            "tapps_static_detectors",
            "invalid_mode",
            f"mode must be one of {VALID_MODES}, got {mode!r}",
        )

    settings = load_settings()
    root_result = resolve_effective_project_root(settings.project_root, project_root)
    if root_result.error_code:
        return error_response(
            "tapps_static_detectors", root_result.error_code, root_result.error_message or ""
        )

    async with heavy_cpu():
        result = await asyncio.to_thread(run_static_detector, normalized_mode, root_result.root)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_static_detectors", start)
    resp = success_response("tapps_static_detectors", elapsed_ms, result.to_dict())
    return _with_nudges("tapps_static_detectors", resp)
