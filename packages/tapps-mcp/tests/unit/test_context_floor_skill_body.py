"""Tests for ``scripts/context_floor_skill_body.py::_leading_literal`` (TAP-7755).

## Round 1 (do not undo)

TAP-7755 (sub-goal 7, ``tmcp-plugin-installable``) originally alleged:
"``_leading_literal`` follows only ``BinOp.left`` when resolving a string
concatenation, so a call spliced into a frontmatter concatenation at a
**non-leftmost** position makes the resolver raise". Round 1's negative
control was: run a fixture matching that description against the resolver
and observe ``MeasurementError``.

That negative control did **not** go red. Pre-round-2, ``_leading_literal``
only ever descended through ``node.left``, so a call sitting at any position
that is *not* on the leftmost spine of the tree was provably unreachable code
from the resolver's perspective -- it was skipped, not visited, regardless of
how many operands separated it from the true leftmost literal. The five cases
in ``TestNonLeftmostCallDoesNotRaise``/``TestLeftmostCallRaises`` were checked
exhaustively (2-operand and 3-operand concatenations, with and without
``ast.Name``/symtab indirection) before concluding: a **non-leftmost** call
never raised, and a **leftmost** call is what actually raised -- the opposite
of what TAP-7755's original wording described. So VAL-06 as *originally*
specified was unsatisfiable, and round 1 correctly reported ``blocked``.

## Round 2 (the real defect, corrected VAL-06)

The real defect is one level up from ``_leading_literal`` raising: dropping
everything past the leftmost literal doesn't just "ignore" a non-leftmost
call, it can **truncate the frontmatter block itself** when a literal chunk
carrying the ``description:`` line sits *after* the call. That truncated
text then fails frontmatter parsing, and the CALLER
(``_skill_info_from_frontmatter``, ``context_floor_skill_body.py:162``)
raises ``MeasurementError: ...: no description field in frontmatter`` --
reproduced end-to-end via ``resolve_skill_info()``, the exact entry point
``context_floor_skills._collect_skill_set`` calls for a non-asset,
non-domain-call dict entry.

The fix makes ``_leading_literal`` walk **both** operands of every ``+``
concatenation (see its docstring), treating an unresolvable ``Call`` as
empty text when it is *not* on the leftmost spine, so a literal chunk that
follows a call is concatenated rather than dropped. Two round-1 assertions
below (``test_call_in_middle_of_three_operands`` and
``test_call_in_middle_with_name_indirected_leftmost``) had their *expected
string* updated as a direct, unavoidable consequence: those fixtures also
have a literal chunk after the call, and correctly including it is the same
change that fixes VAL-06. The **classification** those two tests exist to
document -- a non-leftmost call does not raise -- is unchanged; only the
returned text grew to include what follows the call, which used to be
silently dropped. The three other round-1 tests (the leftmost-call-raises
pair, plus the simple non-leftmost/nothing-follows case) are byte-for-byte
unchanged: round 2 deliberately keeps a leftmost call raising (see
``_resolve_literal_text``'s ``strict`` parameter and its docstring).
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
        """Round 2: the trailing ``"\\nbody\\n"`` literal is now included --
        it is walked and concatenated, not dropped, which is the same
        generalization that fixes VAL-06's truncation."""
        tree = ast.parse(f'{_FRONTMATTER} + SOME_CALL() + "\\nbody\\n"', mode="eval").body
        assert skill_body._leading_literal(tree, {}) == "---\nname: x\n---\n\nbody\n"

    def test_call_in_middle_with_name_indirected_leftmost(self, skill_body: ModuleType) -> None:
        """Same shape, but the leftmost literal is reached via a symtab Name
        lookup rather than sitting directly in the expression -- the call is
        still skipped (empty), and the trailing literal is still included
        (round 2)."""
        symtab = {"_HEADER": ast.parse(_FRONTMATTER, mode="eval").body}
        tree = ast.parse("_HEADER + SOME_CALL() + '\\nbody\\n'", mode="eval").body
        assert skill_body._leading_literal(tree, symtab) == "---\nname: x\n---\n\nbody\n"


class TestLeftmostCallRaises:
    """The shape that actually raises: a call reached via ``.left`` before any
    literal/Name/JoinedStr is found -- the inverse of TAP-7755's original
    description. **Round 2 deliberate decision:** a leftmost call still
    raises after the fix -- it means there is no leading literal at all,
    which is a genuinely different (and still worth-surfacing) authoring
    mistake than a call splicing two literals together. These two tests are
    byte-for-byte unchanged from round 1 and are round 2's evidence that the
    decision holds (``_resolve_literal_text``'s ``strict`` parameter)."""

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


# --- Round 2: the corrected VAL-06 (TAP-7755) -------------------------------
#
# Fixture shape per the lane brief, verbatim: a synthetic module source
# ``SKILL = LEADING_LITERAL + call(...) + TRAILING_LITERAL_WITH_DESCRIPTION``
# (call spliced mid-frontmatter, non-leftmost, ``description:`` after the
# call), resolved via ``resolve_skill_info()`` directly -- the exact call
# ``context_floor_skills._collect_skill_set`` makes for any non-asset,
# non-domain-call dict entry.

_LEADING_NO_CLOSE = '"---\\nname: test-skill\\nmodel: "'
_TRAILING_WITH_DESCRIPTION = '"opus\\ndescription: the description text\\n---\\n"'
_VAL06_DEFECT_SOURCE = f"{_LEADING_NO_CLOSE} + SOME_CALL() + {_TRAILING_WITH_DESCRIPTION}"

# Anti-vacuity control (designed by the verifier who reproduced this): the
# SAME shape, but ``description:`` moved BEFORE the call -- proves the test
# is sensitive to splice *position*, not merely the presence of a call.
_COMPLETE_WITH_DESCRIPTION = (
    '"---\\nname: test-skill\\ndescription: the description text\\n---\\n"'
)
_TRAILING_BODY = '"\\nbody\\n"'
_ANTI_VACUITY_SOURCE = f"{_COMPLETE_WITH_DESCRIPTION} + SOME_CALL() + {_TRAILING_BODY}"

# Malformed-body control: same call splice, but no ``description:`` anywhere
# in the (now fully resolved, closed) frontmatter -- must still raise after
# the fix. Loud failure must not become a silent zero.
_TRAILING_NO_DESCRIPTION = '"opus\\n---\\n"'
_MALFORMED_SOURCE = f"{_LEADING_NO_CLOSE} + SOME_CALL() + {_TRAILING_NO_DESCRIPTION}"


class TestVal06TruncationFix:
    """TAP-7755 round 2, corrected VAL-06. Pre-fix, ``_VAL06_DEFECT_SOURCE``
    raises ``MeasurementError: test-skill: no description field in
    frontmatter`` from ``_skill_info_from_frontmatter``
    (``context_floor_skill_body.py:162``) -- confirmed by traceback, not by
    grepping the error string, since an identical message also exists at
    the unreachable ``context_floor_skills.py:105`` decoy site. Post-fix it
    must resolve. This class only exercises the fixed (current) tree; the
    pre-fix negative-control run and its traceback are reported in the
    lane's evidence block, not re-derivable here since round 1's fix is
    already applied to this file."""

    def test_val06_defect_fixture_resolves_after_fix(
        self, skill_body: ModuleType
    ) -> None:
        tree = ast.parse(_VAL06_DEFECT_SOURCE, mode="eval").body
        info = skill_body.resolve_skill_info("test-skill", tree, {})
        assert info.description == "the description text"

    def test_anti_vacuity_description_before_call_resolves(
        self, skill_body: ModuleType
    ) -> None:
        """Mandatory anti-vacuity control: description BEFORE the call.
        This resolved under the UNFIXED resolver too (confirmed in the
        lane's evidence block) because the frontmatter was already complete
        before the call was ever reached -- so this alone would not prove
        the fix does anything. It must ALSO still resolve post-fix."""
        tree = ast.parse(_ANTI_VACUITY_SOURCE, mode="eval").body
        info = skill_body.resolve_skill_info("test-skill", tree, {})
        assert info.description == "the description text"

    def test_malformed_body_with_call_splice_still_raises(
        self, skill_body: ModuleType, measurement_error: type[Exception]
    ) -> None:
        """A genuinely malformed body -- no ``description:`` anywhere, even
        after the call-splice fix fully resolves the frontmatter text --
        must still raise loudly. The fix trades a truncation bug for a
        correct resolution, never for a silently-wrong or silently-empty
        description."""
        tree = ast.parse(_MALFORMED_SOURCE, mode="eval").body
        with pytest.raises(measurement_error, match="no description field in frontmatter"):
            skill_body.resolve_skill_info("test-skill", tree, {})
