"""TAP-7425 (GAP 2 / box 4): every string-literal artifact name passed to a
skip-token gate must be a registered ``SKIP_TOKENS`` key.

``skipped()`` now raises ``KeyError`` on an unregistered name (TAP-7425), but
that guard only fires when the call site actually *executes* at runtime. A
call site holding a bad literal that is never exercised by any test stays
invisible. A hand-maintained list of call sites drifts the same way the
restated-fact problem this program has already filed issues about drifts —
so this test derives the call-site set by walking the source AST instead of
trusting a list (including the one in this lane's own brief).

Per the lane's own warning ("the one thing that will silently give a wrong
result"): an AST walk that matches too narrow a node shape, walks the wrong
directory, or swallows a parse error collects zero call sites and passes
vacuously — worse than no test, since it would then be cited as coverage.
``test_walker_finds_at_least_the_known_call_sites`` guards exactly that by
asserting a floor derived from grepping the source tree independently
(documented below), not a placeholder like ``>= 1``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import tapps_mcp
from tapps_mcp.pipeline.upgrade_skip_tokens import SKIP_TOKENS

# Functions whose named argument is an ``upgrade_skip_files`` artifact/token,
# and the positional index of that argument -- ``skipped``/``_skipped``/
# ``dry_run_status`` take it first; ``apply_or_skip`` takes ``result`` first,
# so the artifact name is its second positional argument.
_GATE_FUNCS: dict[str, int] = {
    "skipped": 0,
    "_skipped": 0,
    "dry_run_status": 0,
    "apply_or_skip": 1,
}

# Independently grepped floor (2026-09-11, at 841fda15 + this lane's tests):
#   grep -rn 'skipped(\|dry_run_status(\|apply_or_skip(' pipeline/*.py
# found 11 call sites outside upgrade_report.py's own definitions (10 with a
# literal first arg, 1 loop variable in upgrade_github.py). The AST walk also
# counts upgrade_report.py's own 2 internal calls to ``skipped()`` inside
# ``dry_run_status``/``apply_or_skip`` (both non-literal -- they forward
# their *own* ``name``/``artifact`` parameter, per the lane brief), for 14
# total: 10 literal + 4 non-literal. Any future call site only grows this
# number; a walk that finds fewer than this either regressed a call site's
# gating or the walk itself is broken.
_MIN_EXPECTED_CALL_SITES = 14


def _src_root() -> Path:
    """The ``tapps_mcp`` package directory, resolved from the installed module
    rather than a hardcoded relative path -- correct regardless of where the
    checkout lives."""
    return Path(tapps_mcp.__file__).resolve().parent


def _func_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


class CallSite:
    __slots__ = ("func", "lineno", "literal", "path", "resolved")

    def __init__(
        self, path: Path, lineno: int, func: str, literal: str | None, resolved: bool
    ) -> None:
        self.path = path
        self.lineno = lineno
        self.func = func
        self.literal = literal
        self.resolved = resolved

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"{self.path.name}:{self.lineno} {self.func}({self.literal!r})"


def _walk_call_sites() -> tuple[list[CallSite], list[Path]]:
    """Return (call sites, files that failed to parse).

    A parse failure is reported, never swallowed -- a silently-skipped file
    is exactly the "walked the wrong directory" failure mode this test
    exists to rule out.
    """
    root = _src_root()
    py_files = sorted(root.rglob("*.py"))
    assert py_files, f"found zero .py files under {root} -- walked the wrong directory"

    sites: list[CallSite] = []
    parse_failures: list[Path] = []

    for path in py_files:
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            parse_failures.append(path)
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _func_name(node.func)
            if name not in _GATE_FUNCS:
                continue
            arg_index = _GATE_FUNCS[name]
            if len(node.args) <= arg_index:
                # No positional arg at the expected slot (e.g. called by
                # keyword) -- can't resolve here; report it as unresolved
                # rather than silently dropping it from the count.
                sites.append(CallSite(path, node.lineno, name, None, resolved=False))
                continue
            arg_node = node.args[arg_index]
            if isinstance(arg_node, ast.Constant) and isinstance(arg_node.value, str):
                sites.append(CallSite(path, node.lineno, name, arg_node.value, resolved=True))
            else:
                # Non-literal (e.g. a parameter or loop variable) -- the
                # brief explicitly allows skipping these as long as the
                # count is reported, rather than trying to trace every
                # variable back to its literal origin.
                sites.append(CallSite(path, node.lineno, name, None, resolved=False))

    return sites, parse_failures


def test_walker_finds_at_least_the_known_call_sites() -> None:
    """The probe-validation floor: a walk that matches nothing must not pass."""
    sites, parse_failures = _walk_call_sites()

    assert not parse_failures, f"AST walk silently could not parse: {parse_failures}"
    assert len(sites) >= _MIN_EXPECTED_CALL_SITES, (
        f"found only {len(sites)} skip-token gate call sites, expected at least "
        f"{_MIN_EXPECTED_CALL_SITES}. Either a call site regressed or the walker "
        "itself stopped matching (e.g. an ast.Attribute call shape it no longer sees)."
    )


def test_every_literal_artifact_argument_is_a_registered_skip_token() -> None:
    """Box 4 itself: every string-literal artifact name is a real SKIP_TOKENS key."""
    sites, _ = _walk_call_sites()

    literal_sites = [s for s in sites if s.resolved]
    unresolved_sites = [s for s in sites if not s.resolved]

    assert literal_sites, "no literal artifact arguments found -- walk matched nothing resolvable"

    bad = [s for s in literal_sites if s.literal not in SKIP_TOKENS]
    assert not bad, "unregistered SKIP_TOKENS literal(s) passed to a skip-token gate:\n" + "\n".join(
        f"  {s.path.relative_to(_src_root())}:{s.lineno} {s.func}({s.literal!r})" for s in bad
    )

    # Coverage denominator, per the lane brief: state how many call sites
    # were literal (checked) vs. non-literal (a parameter or loop variable,
    # not traced back to its origin -- e.g. upgrade_github.py's
    # ``for token, key, generate in (...)`` loop and upgrade_host_context.py's
    # ``resolve_component(..., skip_key=...)`` indirection).
    print(
        f"skip-token call-site walk: {len(literal_sites)} literal (checked), "
        f"{len(unresolved_sites)} non-literal (skipped, not traced)."
    )
