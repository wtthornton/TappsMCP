"""Tests for ``scripts/context_floor_skill_body.py::_leading_literal`` (TAP-7755).

TAP-7755 (sub-goal 7, ``tmcp-plugin-installable``) alleged: "``_leading_literal``
follows only ``BinOp.left`` when resolving a string concatenation, so a call
spliced into a frontmatter concatenation at a **non-leftmost** position makes the
resolver raise". VAL-06's mandated negative control was: run a fixture matching
that description against the unfixed resolver and observe ``MeasurementError``.

That negative control does **not** go red. ``_leading_literal`` only ever
descends through ``node.left`` (see the function's own docstring: "the rest of
the concatenation ... is never inspected"), so a call sitting at any position
that is *not* on the leftmost spine of the tree is provably unreachable code
from the resolver's perspective -- it is skipped, not visited, regardless of
how many operands separate it from the true leftmost literal. The five cases
below were checked exhaustively (2-operand and 3-operand concatenations, with
and without ``ast.Name``/symtab indirection) before concluding this:

- A **non-leftmost** call (2nd operand of two, or the middle of three) never
  raises -- it resolves to the true leftmost literal, silently and correctly
  ignoring the call, exactly as the docstring says it should.
- A **leftmost** call (the call is the first operand, or is reached by
  following ``.left``/``Name`` lookups all the way down) is what actually
  raises ``MeasurementError: unsupported skill-body expression: ...`` -- the
  opposite of what TAP-7755 described.

So VAL-06 as specified is unsatisfiable: there is no legitimate "fix" to make
here, because the described defect does not reproduce, and the actual raising
case (a leftmost call) is the resolver behaving as documented for a source
shape that would represent a genuinely different frontmatter authoring
mistake. These tests lock in the resolver's real, current, correct behavior
so this finding is re-derivable rather than only asserted in prose.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = REPO_ROOT / "scripts"

_FRONTMATTER = '"---\\nname: x\\n---\\n"'


@pytest.fixture(scope="module")
def skill_body() -> ModuleType:
    """Import scripts/context_floor_skill_body.py -- scripts/ is not a package."""
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    import context_floor_skill_body

    return context_floor_skill_body


@pytest.fixture(scope="module")
def measurement_error(skill_body: ModuleType) -> type[Exception]:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    import context_floor_core

    return context_floor_core.MeasurementError


class TestNonLeftmostCallDoesNotRaise:
    """The shape TAP-7755/VAL-06 described -- a call NOT in the leftmost
    position of the concatenation. In both variants below the resolver
    correctly ignores the call and returns the leading literal; neither
    fixture reproduces the claimed ``MeasurementError``."""

    def test_call_as_rightmost_of_two_operands(self, skill_body: ModuleType) -> None:
        tree = ast.parse(f"{_FRONTMATTER} + SOME_CALL()", mode="eval").body
        assert skill_body._leading_literal(tree, {}) == "---\nname: x\n---\n"

    def test_call_in_middle_of_three_operands(self, skill_body: ModuleType) -> None:
        tree = ast.parse(f'{_FRONTMATTER} + SOME_CALL() + "\\nbody\\n"', mode="eval").body
        assert skill_body._leading_literal(tree, {}) == "---\nname: x\n---\n"

    def test_call_in_middle_with_name_indirected_leftmost(self, skill_body: ModuleType) -> None:
        """Same shape, but the leftmost literal is reached via a symtab Name
        lookup rather than sitting directly in the expression -- still never
        touches the call."""
        symtab = {"_HEADER": ast.parse(_FRONTMATTER, mode="eval").body}
        tree = ast.parse("_HEADER + SOME_CALL() + '\\nbody\\n'", mode="eval").body
        assert skill_body._leading_literal(tree, symtab) == "---\nname: x\n---\n"


class TestLeftmostCallRaises:
    """The shape that actually raises: a call reached via ``.left`` before any
    literal/Name/JoinedStr is found -- the inverse of TAP-7755's description."""

    def test_call_as_leftmost_of_two_operands(
        self, skill_body: ModuleType, measurement_error: type[Exception]
    ) -> None:
        tree = ast.parse(f"SOME_CALL() + {_FRONTMATTER}", mode="eval").body
        with pytest.raises(measurement_error, match="unsupported skill-body expression"):
            skill_body._leading_literal(tree, {})

    def test_call_via_leftmost_name_indirection(
        self, skill_body: ModuleType, measurement_error: type[Exception]
    ) -> None:
        symtab = {"HELPER": ast.parse("SOME_CALL()", mode="eval").body}
        tree = ast.parse(f"HELPER + {_FRONTMATTER}", mode="eval").body
        with pytest.raises(measurement_error, match="unsupported skill-body expression"):
            skill_body._leading_literal(tree, symtab)
