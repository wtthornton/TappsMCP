"""Envelope-lie lint: success reported over a failed best-effort sub-result.

TAP-5660. Two defects escaped to a consuming project in 3.12.65 with the same
shape: a best-effort dependency failed, its failure was embedded in the
response ``data``, and the envelope still said ``success=true``. A caller that
did not read the nested key believed the operation had completed.

What this flags
---------------
A call to ``success_response(...)`` whose ``data`` carries a *best-effort
sub-result* that the enclosing function never examined, and which does not
mark the envelope degraded.

"Best-effort sub-result" is deliberately narrow, and type-driven rather than
name-driven: a field annotated ``dict[str, Any] | None`` on a dataclass or
model. That annotation is how this codebase spells "an operation that may not
have happened" — ``HandoffWriteResult.brain_mirror`` and
``.session_end`` are both exactly that, and both were real bugs. Anchoring on
the type keeps the false-positive rate near zero; anchoring on names like
``*_result`` would not.

A site is considered handled when any of these is true:
  * ``degraded=`` is passed to ``success_response``
  * the enclosing function branches on the value (``if`` / ``elif`` test, a
    boolean operator, or a comprehension condition mentioning it)
  * the site carries an allowlist comment (see below)

Intentional exceptions
----------------------
Put ``# envelope-ok: <reason>`` on the line where the value enters ``data``.
The reason is required; a bare marker is itself an error. Silence should cost
a sentence.

Known gaps (TAP-6618)
----------------------
The six live envelope inconsistencies the TAP-5659 sweep found were all
outside this lint's shape, for two independent reasons — neither is a small
extension, so they are documented here rather than papered over with a
speculative rewrite of the AST matcher:

1. **List-shaped best-effort results.** ``collect_best_effort_fields`` only
   recognises ``dict[str, Any] | None`` (``Optional[dict[...]]``) fields.
   ``skipped_files: list[dict[str, str]]`` (``server_analysis_tools.py``) and
   the batch ``results: list[dict[str, Any]]`` (``server_scoring_tools.py``)
   are lists of best-effort records, not an optional dict — extending the
   type match to "any container of dicts" would also have to teach the
   per-element "is *this* dict a failure" judgment the runtime
   ``assert_envelope_consistent`` fixture already does, duplicating that
   logic in the static checker with no shared source of truth.
2. **Cross-function payload assembly.** ``_dict_literal_for`` resolves the
   ``data``/``resp_data`` argument to a dict *literal* in the same function
   as the ``success_response`` call. ``tapps_validate_changed`` builds its
   payload in ``_build_response_data`` (a different function, in a different
   module) and passes the already-built dict by name — there is no local
   literal for the ``ast.Assign`` walk to find, so the site is invisible to
   this pass regardless of field typing. Following the value across a
   function-call boundary needs a call graph, not a per-function AST walk.

Both gaps are covered instead by the runtime ``envelope_guard`` fixture
(``tests/conftest.py``), which patches ``success_response`` itself and
therefore sees every envelope regardless of how ``data`` was assembled or
shaped. New best-effort sub-results should get a covering test using that
fixture; this lint remains a same-function early-warning for the simple case.

Usage
-----
    python3 scripts/check-response-envelope.py            # scan packages/*/src
    python3 scripts/check-response-envelope.py --test     # self-test
    python3 scripts/check-response-envelope.py --paths a.py b.py
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GLOBS = ("packages/*/src/**/*.py",)
RESPONSE_BUILDERS = frozenset({"success_response"})
ALLOW_MARKER = "envelope-ok:"


@dataclass(frozen=True)
class Finding:
    """One response site that reports success over an unexamined sub-result."""

    path: str
    line: int
    key: str
    func: str

    def render(self) -> str:
        return (
            f"{self.path}:{self.line}: {self.func}() puts best-effort "
            f"'{self.key}' into a success response without checking it. "
            f"Branch on it, pass degraded=, or add '# {ALLOW_MARKER} <reason>'."
        )


def _is_optional_dict(node: ast.expr | None) -> bool:
    """True for ``dict[str, Any] | None`` and ``Optional[dict[str, Any]]``."""
    if node is None:
        return False
    # dict[...] | None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        sides = (node.left, node.right)
        has_none = any(isinstance(s, ast.Constant) and s.value is None for s in sides)
        has_dict = any(_is_dict_subscript(s) for s in sides)
        return has_none and has_dict
    # Optional[dict[...]]
    if isinstance(node, ast.Subscript) and _name_of(node.value) == "Optional":
        return _is_dict_subscript(node.slice)
    return False


def _is_dict_subscript(node: ast.expr) -> bool:
    return isinstance(node, ast.Subscript) and _name_of(node.value) in {"dict", "Dict"}


def _name_of(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def collect_best_effort_fields(tree: ast.AST) -> set[str]:
    """Field names annotated as an optional dict on any class in *tree*."""
    fields: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and _is_optional_dict(stmt.annotation):
                target = _name_of(stmt.target)
                if target:
                    fields.add(target)
    return fields


COMPREHENSION_TYPES = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
CONDITIONAL_TYPES = (ast.If, ast.IfExp, ast.While)


def _condition_exprs(node: ast.AST) -> list[ast.expr]:
    """Return the conditional expressions this node contributes, if any."""
    if isinstance(node, CONDITIONAL_TYPES):
        return [node.test]
    if isinstance(node, ast.BoolOp):
        return list(node.values)
    if isinstance(node, COMPREHENSION_TYPES):
        return [cond for gen in node.generators for cond in gen.ifs]
    return []


def _tokens_in_conditions(func: ast.AST) -> set[str]:
    """Every name/attr appearing in a conditional test inside *func*."""
    tokens: set[str] = set()
    for node in ast.walk(func):
        for expr in _condition_exprs(node):
            for sub in ast.walk(expr):
                if isinstance(sub, (ast.Name, ast.Attribute)):
                    name = _name_of(sub)
                    if name:
                        tokens.add(name)
    return tokens


def _dict_literal_for(func: ast.AST, arg: ast.expr) -> ast.Dict | None:
    """Resolve the ``data`` argument to a dict literal in the same function."""
    if isinstance(arg, ast.Dict):
        return arg
    target_name = _name_of(arg)
    if target_name is None:
        return None
    found: ast.Dict | None = None
    for node in ast.walk(func):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(_name_of(t) == target_name for t in targets) and isinstance(
                node.value, ast.Dict
            ):
                found = node.value
    return found


def _allowlisted(lines: list[str], lineno: int) -> tuple[bool, bool]:
    """Return (marked, has_reason) for the allowlist comment on *lineno*."""
    if not (1 <= lineno <= len(lines)):
        return (False, False)
    line = lines[lineno - 1]
    if ALLOW_MARKER not in line:
        return (False, False)
    reason = line.split(ALLOW_MARKER, 1)[1].strip()
    return (True, bool(reason))


def check_source(source: str, path: str, known_fields: set[str] | None = None) -> list[Finding]:
    """Scan one module for unexamined best-effort sub-results in responses.

    *known_fields* carries best-effort field names discovered in other modules.
    It matters: the result dataclass is routinely declared in one module and
    serialised into a response in another — ``HandoffWriteResult.session_end``
    is defined in ``handoff_write.py`` and consumed in
    ``server_pipeline_tools.py``. Scanning each file in isolation misses
    exactly the cross-module case that escaped.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    best_effort = collect_best_effort_fields(tree) | (known_fields or set())
    if not best_effort:
        return []

    lines = source.splitlines()
    findings: list[Finding] = []

    for func in ast.walk(tree):
        if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            findings.extend(_check_function(func, path, lines, best_effort))

    return findings


def _response_payload(func: ast.AST, call: ast.Call) -> ast.Dict | None:
    """Return the ``data`` dict literal of an unguarded response call.

    ``None`` when the call is not a response builder, already passes
    ``degraded=``, or its payload cannot be resolved to a dict literal.
    """
    if _name_of(call.func) not in RESPONSE_BUILDERS:
        return None
    if any(kw.arg == "degraded" for kw in call.keywords):
        return None
    # success_response(tool_name, elapsed_ms, data, *, ...) — the payload is
    # positional index 2. Picking "first Name-ish argument" instead silently
    # resolves to elapsed_ms and finds nothing.
    data_arg = next(
        (kw.value for kw in call.keywords if kw.arg == "data"),
        call.args[2] if len(call.args) > 2 else None,
    )
    if data_arg is None:
        return None
    return _dict_literal_for(func, data_arg)


def _key_name(key_node: ast.expr | None, fallback: str) -> str:
    """Prefer the literal response key; fall back to the source token."""
    if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
        return key_node.value
    return fallback


def _check_function(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    path: str,
    lines: list[str],
    best_effort: set[str],
) -> list[Finding]:
    """Return findings for every unexamined sub-result in one function."""
    guarded = _tokens_in_conditions(func)
    findings: list[Finding] = []

    for call in ast.walk(func):
        if not isinstance(call, ast.Call):
            continue
        literal = _response_payload(func, call)
        if literal is None:
            continue

        # ast.Dict always pairs keys with values (a None key is ``**expr``).
        for key_node, value_node in zip(literal.keys, literal.values, strict=True):
            token = _name_of(value_node)
            if token is None or token not in best_effort or token in guarded:
                continue
            lineno = getattr(value_node, "lineno", call.lineno)
            marked, has_reason = _allowlisted(lines, lineno)
            if marked and has_reason:
                continue
            key = _key_name(key_node, token)
            if marked:
                key = f"{key} (allowlisted with no reason)"
            findings.append(Finding(path, lineno, key, func.name))

    return findings


def iter_target_files(paths: list[str]) -> list[Path]:
    if paths:
        return [Path(p) for p in paths]
    files: list[Path] = []
    for pattern in DEFAULT_GLOBS:
        files.extend(sorted(REPO_ROOT.glob(pattern)))
    return files


def run_sweep(targets: list[Path]) -> list[Finding]:
    """Scan *targets* and return every unexamined best-effort sub-result.

    Two passes: the first collects every best-effort field declared anywhere,
    so a response built in one module is still checked against a result type
    declared in another; the second checks each response site against that
    union. Split out of ``main`` so the sweep CI runs is also callable from
    the test suite.
    """
    sources: list[tuple[str, str]] = []
    for path in targets:
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        rel = str(path.relative_to(REPO_ROOT)) if path.is_absolute() else str(path)
        sources.append((rel, source))

    known_fields: set[str] = set()
    for _rel, source in sources:
        try:
            known_fields |= collect_best_effort_fields(ast.parse(source))
        except SyntaxError:
            continue

    findings: list[Finding] = []
    for rel, source in sources:
        findings.extend(check_source(source, rel, known_fields))
    return findings
