"""Tests for ``scripts/context_floor_skill_body.py`` body resolution (TAP-7755).

## Round 1 (do not undo)

TAP-7755 (sub-goal 7, ``tmcp-plugin-installable``) originally alleged:
"the resolver follows only ``BinOp.left`` when resolving a string
concatenation, so a call spliced into a frontmatter concatenation at a
**non-leftmost** position makes the resolver raise". Round 1's negative
control was: run a fixture matching that description against the resolver
and observe ``MeasurementError``.

That negative control did **not** go red. Pre-round-2 the resolver only ever
descended through ``node.left``, so a call sitting at any position that is
*not* on the leftmost spine of the tree was provably unreachable code from
the resolver's perspective -- it was skipped, not visited, regardless of how
many operands separated it from the true leftmost literal. The five cases in
``TestNonLeftmostCallDoesNotRaise``/``TestLeftmostCallRaises`` were checked
exhaustively (2-operand and 3-operand concatenations, with and without
``ast.Name``/symtab indirection) before concluding: a **non-leftmost** call
never raised, and a **leftmost** call is what actually raised -- the opposite
of what TAP-7755's original wording described. So VAL-06 as *originally*
specified was unsatisfiable, and round 1 correctly reported ``blocked``.

## Round 2 (the real defect, corrected VAL-06)

The real defect is one level up: dropping everything past the leftmost
literal doesn't just "ignore" a non-leftmost call, it can **truncate the
frontmatter block itself** when a literal chunk carrying the ``description:``
line sits *after* the call. Round 2 made the resolver walk **both** operands
of every ``+`` concatenation, and resolved an unresolvable ``Call`` to ``""``.

**Round 2 was refuted:** resolving a call to ``""`` converted a loud failure
into a wrong number. ``"description: " + get_desc()`` stopped raising and
started reporting ``description=''``, measured at 0 bytes.

## Round 3 (the elision flag) -- also refuted

Round 3 added ``ResolvedBody(text, elided)`` and refused when ``elided and
not description``. That property is **too narrow**: it only fires when the
elided call supplies the *entire* description value. Four holes stayed open
on ``668b1efc``, each returning a confident, non-empty, wrong number:

1. ``'description: prefix-' + MID() + '-suffix'``  -> ``'prefix--suffix'``
2. ``'description: '        + MID() + '-suffix'``  -> ``'-suffix'``
3. ``f'description: outer {f"{1}"} tail'``          -> ``'outer'``
4. ``'description: "'       + INNER() + '   "'``    -> ``'   '``

## Round 4 (sentinel substitution) -- the property this file now pins

The correct property is **positional**, not one about emptiness:

> If any elided segment falls inside the span of a field this tool reports,
> refuse -- regardless of whether the resulting value is empty, non-empty, or
> whitespace.

The mechanism: stop tracking loss *beside* the text and write it *into* the
text. Every elided segment resolves to ``_ELIDED_SENTINEL`` (private-use
code points around a fixed tag), the frontmatter is parsed exactly as
before, and ``_skill_info_from_frontmatter`` refuses when the sentinel
survives into a frontmatter key or into any of ``_MEASURED_FIELDS``. One rule
closes start-of-value, middle-of-value, whole-value, f-string and
whitespace-quoted cases, because each leaves the sentinel inside the
extracted value.

Two consequences visible in the tests below, both deliberate:

* ``ResolvedBody`` and ``_leading_literal`` are **gone**. ``elided`` is no
  longer a separate fact to be discarded -- it is derivable from the text
  (``_ELIDED_SENTINEL in body``), so there is one source of truth and no
  flag-discarding accessor left for a future caller to measure through.
  ``_leading_literal`` had zero production callers.
* The three ``TestNonLeftmostCallDoesNotRaise`` assertions now expect the
  sentinel where the call sits. That is not a back-fitted expected value: a
  *correct* implementation under this design **must** put something
  improbable at the call's position, since occupying that position is the
  entire mechanism. Round 2 put ``""`` there and was refuted for exactly
  that. The classification those tests exist to document -- a non-leftmost
  call does not raise -- is unchanged, and the sentinel is referenced
  symbolically rather than hardcoded.

``TestSentinelSubstitutionDiscriminates`` is the positive control for the
sentinel itself: without it, ``TestElisionOutsideMeasuredFieldsResolves``
would be vacuous, since a fixture where no elision ever occurred would pass
trivially. ``TestNoSentinelLeakage`` pins the other end: no sentinel may ever
reach a returned value or a byte count.
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
    position of the concatenation. In every variant below the resolver
    returns text rather than raising; neither fixture reproduces the claimed
    ``MeasurementError``. Round 4: the call's position is now occupied by
    ``_ELIDED_SENTINEL`` instead of by nothing, so the returned text records
    *where* the resolver could not see."""

    def test_call_as_rightmost_of_two_operands(self, skill_body: ModuleType) -> None:
        tree = ast.parse(f"{_FRONTMATTER} + SOME_CALL()", mode="eval").body
        sentinel = skill_body._ELIDED_SENTINEL
        assert skill_body._resolve_skill_body(tree, {}) == f"---\nname: x\n---\n{sentinel}"

    def test_call_in_middle_of_three_operands(self, skill_body: ModuleType) -> None:
        """Round 2 made the trailing ``"\\nbody\\n"`` literal be included --
        it is walked and concatenated, not dropped, which is the same
        generalization that fixes VAL-06's truncation. Round 4 additionally
        marks the gap between the two literals."""
        tree = ast.parse(f'{_FRONTMATTER} + SOME_CALL() + "\\nbody\\n"', mode="eval").body
        sentinel = skill_body._ELIDED_SENTINEL
        assert skill_body._resolve_skill_body(tree, {}) == f"---\nname: x\n---\n{sentinel}\nbody\n"

    def test_call_in_middle_with_name_indirected_leftmost(self, skill_body: ModuleType) -> None:
        """Same shape, but the leftmost literal is reached via a symtab Name
        lookup rather than sitting directly in the expression -- the call is
        still not fatal, and the trailing literal is still included."""
        symtab = {"_HEADER": ast.parse(_FRONTMATTER, mode="eval").body}
        tree = ast.parse("_HEADER + SOME_CALL() + '\\nbody\\n'", mode="eval").body
        sentinel = skill_body._ELIDED_SENTINEL
        expected = f"---\nname: x\n---\n{sentinel}\nbody\n"
        assert skill_body._resolve_skill_body(tree, symtab) == expected


class TestLeftmostCallRaises:
    """The shape that actually raises: a call reached via ``.left`` before any
    literal/Name/JoinedStr is found -- the inverse of TAP-7755's original
    description. **Kept deliberately in rounds 2, 3 and 4.** Round 4 supplies
    the mechanical reason a sentinel is *not* substituted there: sentinel
    characters ahead of the opening ``---`` would stop
    ``_frontmatter_bounds`` recognising that line as a delimiter, so the
    block would be located from the closing ``---`` and parse empty. Raising
    names the situation; substituting could only mis-parse it. These two
    assertions are behaviourally unchanged from round 1 (only the resolver's
    function name moved, ``_leading_literal`` -> ``_resolve_skill_body``,
    when the flag-discarding accessor was deleted)."""

    def test_call_as_leftmost_of_two_operands(
        self, skill_body: ModuleType, measurement_error: type[Exception]
    ) -> None:
        tree = ast.parse(f"SOME_CALL() + {_FRONTMATTER}", mode="eval").body
        with pytest.raises(measurement_error, match="unsupported skill-body expression"):
            skill_body._resolve_skill_body(tree, {})

    def test_call_via_leftmost_name_indirection(
        self, skill_body: ModuleType, measurement_error: type[Exception]
    ) -> None:
        symtab = {"HELPER": ast.parse("SOME_CALL()", mode="eval").body}
        tree = ast.parse(f"HELPER + {_FRONTMATTER}", mode="eval").body
        with pytest.raises(measurement_error, match="unsupported skill-body expression"):
            skill_body._resolve_skill_body(tree, symtab)


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

# Control 1 as the round-4 brief states it verbatim -- the same shape with
# the ``model:`` value supplied ENTIRELY by the call, so the elision is the
# whole of an unreported field rather than a prefix of one.
_VAL06_BRIEF_SOURCE = (
    '"---\\nname: x\\nmodel: " + CALL() + "\\ndescription: the description text\\n---\\nbody\\n"'
)

# Anti-vacuity control (designed by the verifier who reproduced this): the
# SAME shape, but ``description:`` moved BEFORE the call -- proves the test
# is sensitive to splice *position*, not merely the presence of a call.
_COMPLETE_WITH_DESCRIPTION = '"---\\nname: test-skill\\ndescription: the description text\\n---\\n"'
_TRAILING_BODY = '"\\nbody\\n"'
_ANTI_VACUITY_SOURCE = f"{_COMPLETE_WITH_DESCRIPTION} + SOME_CALL() + {_TRAILING_BODY}"

# Malformed-body control: same call splice, but no ``description:`` anywhere
# in the (now fully resolved, closed) frontmatter -- must still raise after
# the fix. Loud failure must not become a silent zero.
_TRAILING_NO_DESCRIPTION = '"opus\\n---\\n"'
_MALFORMED_SOURCE = f"{_LEADING_NO_CLOSE} + SOME_CALL() + {_TRAILING_NO_DESCRIPTION}"


class TestVal06TruncationFix:
    """TAP-7755 corrected VAL-06 -- control 1. On base (``6552b185``)
    ``_VAL06_DEFECT_SOURCE`` raises ``MeasurementError: test-skill: no
    description field in frontmatter`` because the trailing literal carrying
    ``description:`` is dropped. It must resolve here, and the elision (which
    lands on the ``model:`` value, a field this module does not report) must
    not block it."""

    def test_val06_defect_fixture_resolves_after_fix(self, skill_body: ModuleType) -> None:
        tree = ast.parse(_VAL06_DEFECT_SOURCE, mode="eval").body
        info = skill_body.resolve_skill_info("test-skill", tree, {})
        assert info.description == "the description text"

    def test_val06_brief_fixture_resolves(self, skill_body: ModuleType) -> None:
        """Control 1 exactly as the round-4 brief words it: the whole
        ``model:`` value is elided, and the measurement still comes back."""
        tree = ast.parse(_VAL06_BRIEF_SOURCE, mode="eval").body
        info = skill_body.resolve_skill_info("x", tree, {})
        assert info.description == "the description text"

    def test_val06_fixture_genuinely_elides(self, skill_body: ModuleType) -> None:
        """Non-vacuity for the test above: the fixture really does elide, and
        the sentinel really does land on ``model:`` -- an unreported field --
        which is why the measurement is allowed through."""
        tree = ast.parse(_VAL06_DEFECT_SOURCE, mode="eval").body
        body = skill_body._resolve_skill_body(tree, {})
        assert skill_body._ELIDED_SENTINEL in body
        frontmatter = skill_body._parse_skill_frontmatter(body)
        assert skill_body._ELIDED_SENTINEL in frontmatter["model"]
        assert skill_body._ELIDED_SENTINEL not in frontmatter["description"]

    def test_anti_vacuity_description_before_call_resolves(self, skill_body: ModuleType) -> None:
        """Mandatory anti-vacuity control: description BEFORE the call.
        This resolved under the UNFIXED resolver too (confirmed in the
        lane's evidence block) because the frontmatter was already complete
        before the call was ever reached -- so this alone would not prove
        the fix does anything. It must ALSO still resolve."""
        tree = ast.parse(_ANTI_VACUITY_SOURCE, mode="eval").body
        info = skill_body.resolve_skill_info("test-skill", tree, {})
        assert info.description == "the description text"

    def test_malformed_body_with_call_splice_still_raises(
        self, skill_body: ModuleType, measurement_error: type[Exception]
    ) -> None:
        """Control 8. A genuinely malformed body -- no ``description:``
        anywhere, even after the call-splice fix fully resolves the
        frontmatter text -- must still raise the historical error. The fix
        trades a truncation bug for a correct resolution, never for a
        silently-wrong or silently-empty description."""
        tree = ast.parse(_MALFORMED_SOURCE, mode="eval").body
        with pytest.raises(measurement_error, match="no description field in frontmatter"):
            skill_body.resolve_skill_info("test-skill", tree, {})


# --- Round 4: the positional guard (TAP-7755) -------------------------------
#
# The property under test, stated once: *if an elided segment falls inside
# the span of a field this module reports -- a frontmatter key, or any of
# ``_MEASURED_FIELDS`` -- resolution RAISES, whatever the resulting value
# looks like.*

# Control 2 -- the round-2 regression. ``description``'s VALUE comes from
# CALL2(); CALL1() additionally straddles a ``key: value`` boundary. Base
# RAISED here; round 2 (f9c5be6f) returned ``description=''``.
_DESCRIPTION_VALUE_FROM_CALL = (
    '"---\\nname: test-skill\\n" + CALL1() + "description: " + CALL2() + "\\n---\\n"'
)

# Control 3 -- round-3 hole A. Elision in the MIDDLE of the value; round 3
# returned ``'prefix--suffix'`` (14 bytes), non-empty, so its emptiness guard
# never fired.
_VALUE_PREFIX_ELIDED = "'---\\nname: x\\ndescription: prefix-' + MID() + '-suffix\\n---\\n'"

# Control 4 -- round-3 hole B. Elision at the START of the value; round 3
# returned ``'-suffix'`` (7 bytes).
_VALUE_START_ELIDED = "'---\\nname: x\\ndescription: ' + MID() + '-suffix\\n---\\n'"

# Control 5 -- round-3 hole C. Nested f-string; round 3 kept only the leading
# literal chunk and returned ``'outer'``, dropping ``' 1 tail'``.
_FSTRING_MID_DESCRIPTION = "f'---\\nname: x\\ndescription: outer {f\"{1}\"} tail\\n---\\n'"

# Control 6 -- round-3 hole D. The elided value sits inside YAML quotes with
# trailing spaces; round 3 returned ``'   '``, which is TRUTHY and so slipped
# past a falsiness check.
_QUOTED_WHITESPACE_DESCRIPTION = "'---\\nname: x\\ndescription: \"' + INNER() + '   \"\\n---\\n'"

# The pre-existing hole, present identically on base and on round 2 (both
# returned ``''`` with no exception); round 3 closed this one.
_DESCRIPTION_VALUE_FROM_SINGLE_CALL = (
    '"---\\nname: x\\ndescription: " + get_desc() + "\\n---\\nbody\\n"'
)

# Control 7 -- the guard against over-correcting into raise-on-any-elision.
# The call sits in the markdown body, well past the closing ``---``; the
# description is fully literal and intact, so this MUST still resolve.
_ELISION_OUTSIDE_FRONTMATTER = (
    '"---\\nname: x\\ndescription: real text\\n---\\nbody " + CALL() + " more\\n"'
)

# Same shapes in the f-string channel -- the identical defect class.
_FSTRING_DESCRIPTION_INTERPOLATED = 'f"---\\nname: x\\ndescription: {d}\\n---\\n"'
_FSTRING_TAIL_INTERPOLATED = 'f"---\\nname: x\\ndescription: real text\\n---\\n{tail}"'
_FSTRING_NO_INTERPOLATION = 'f"---\\nname: x\\ndescription: real text\\n---\\n"'

# (test id, source expression, expected message fragment)
_ELIDED_IN_MEASURED_FIELD = [
    ("c2-two-calls-key-straddled", _DESCRIPTION_VALUE_FROM_CALL, "field NAME"),
    ("c3-hole-a-value-prefix", _VALUE_PREFIX_ELIDED, "elided segment"),
    ("c4-hole-b-value-start", _VALUE_START_ELIDED, "elided segment"),
    ("c5-hole-c-nested-fstring", _FSTRING_MID_DESCRIPTION, "elided segment"),
    ("c6-hole-d-quoted-whitespace", _QUOTED_WHITESPACE_DESCRIPTION, "elided segment"),
    ("whole-value-elided", _DESCRIPTION_VALUE_FROM_SINGLE_CALL, "elided segment"),
    ("fstring-value-interpolated", _FSTRING_DESCRIPTION_INTERPOLATED, "elided segment"),
]
_RAISE_PARAMS = [
    pytest.param(source, fragment, id=test_id)
    for test_id, source, fragment in _ELIDED_IN_MEASURED_FIELD
]
_SOURCE_PARAMS = [
    pytest.param(source, id=test_id) for test_id, source, _ in _ELIDED_IN_MEASURED_FIELD
]


class TestSentinelSubstitutionDiscriminates:
    """Positive control for ``_ELIDED_SENTINEL`` itself.

    A sentinel that were never substituted would make every raise test below
    unreachable; one substituted unconditionally would make
    ``TestElisionOutsideMeasuredFieldsResolves`` prove nothing. Pin both ends,
    in both channels."""

    def test_pure_literal_concatenation_has_no_sentinel(self, skill_body: ModuleType) -> None:
        tree = ast.parse(f'{_COMPLETE_WITH_DESCRIPTION} + "body\\n"', mode="eval").body
        assert skill_body._ELIDED_SENTINEL not in skill_body._resolve_skill_body(tree, {})

    def test_call_substitutes_a_sentinel(self, skill_body: ModuleType) -> None:
        tree = ast.parse(_ELISION_OUTSIDE_FRONTMATTER, mode="eval").body
        assert skill_body._ELIDED_SENTINEL in skill_body._resolve_skill_body(tree, {})

    def test_fstring_without_interpolation_has_no_sentinel(self, skill_body: ModuleType) -> None:
        tree = ast.parse(_FSTRING_NO_INTERPOLATION, mode="eval").body
        assert skill_body._ELIDED_SENTINEL not in skill_body._resolve_skill_body(tree, {})

    def test_fstring_interpolation_substitutes_a_sentinel(self, skill_body: ModuleType) -> None:
        tree = ast.parse(_FSTRING_TAIL_INTERPOLATED, mode="eval").body
        assert skill_body._ELIDED_SENTINEL in skill_body._resolve_skill_body(tree, {})

    def test_sentinel_survives_frontmatter_parsing_intact(self, skill_body: ModuleType) -> None:
        """The whole design rests on the sentinel being inert to
        ``_parse_skill_frontmatter``'s transformations (``strip()``,
        ``strip('"')``, the ``line[0] in " \\t-"`` skip, block folding). If
        any of them eroded it, the guards below would silently stop firing --
        so assert survival directly, in the hostile case: inside YAML quotes,
        with surrounding whitespace, mid-value."""
        tree = ast.parse(_QUOTED_WHITESPACE_DESCRIPTION, mode="eval").body
        frontmatter = skill_body._parse_skill_frontmatter(skill_body._resolve_skill_body(tree, {}))
        assert skill_body._ELIDED_SENTINEL in frontmatter["description"]


class TestElidedInMeasuredFieldRaises:
    """Controls 2-6 plus the two cases round 3 already closed.

    Every fixture here puts an elided segment inside the span of a reported
    field. Round 3 refused only the subset whose resulting ``description``
    came out falsy, so the four holes below returned confident wrong numbers
    (``'prefix--suffix'``, ``'-suffix'``, ``'outer'``, ``'   '``). The
    positional rule refuses all of them on one property."""

    @pytest.mark.parametrize(("source", "fragment"), _RAISE_PARAMS)
    def test_raises(
        self,
        skill_body: ModuleType,
        measurement_error: type[Exception],
        source: str,
        fragment: str,
    ) -> None:
        tree = ast.parse(source, mode="eval").body
        with pytest.raises(measurement_error, match=fragment):
            skill_body.resolve_skill_info("test-skill", tree, {})

    @pytest.mark.parametrize("source", _SOURCE_PARAMS)
    def test_each_fixture_really_elides_inside_the_field(
        self, skill_body: ModuleType, source: str
    ) -> None:
        """Non-vacuity for the parametrization above: a fixture that failed to
        elide, or whose sentinel landed somewhere harmless, would make the
        corresponding raise test pass for the wrong reason. Assert the
        sentinel is present in the resolved body AND lands in the frontmatter
        block (not in the trailing markdown)."""
        tree = ast.parse(source, mode="eval").body
        body = skill_body._resolve_skill_body(tree, {})
        sentinel = skill_body._ELIDED_SENTINEL
        assert sentinel in body
        frontmatter = skill_body._parse_skill_frontmatter(body)
        assert any(sentinel in key or sentinel in value for key, value in frontmatter.items()), (
            f"sentinel never reached the frontmatter block for {source!r}"
        )


class TestElisionOutsideMeasuredFieldsResolves:
    """Control 7, and the one that keeps the guard honest: an elision that
    leaves every reported field intact must STILL RESOLVE.

    Raising on any elision whatsoever would be trivially "safe" and would
    re-break TAP-7755 itself -- every fixture in ``TestVal06TruncationFix``
    contains an elided call. Each test here carries its own non-vacuity
    assertion that an elision genuinely occurred."""

    def test_call_in_markdown_body_still_resolves(self, skill_body: ModuleType) -> None:
        tree = ast.parse(_ELISION_OUTSIDE_FRONTMATTER, mode="eval").body
        sentinel = skill_body._ELIDED_SENTINEL
        body = skill_body._resolve_skill_body(tree, {})
        assert sentinel in body, "fixture did not elide -- this control would be vacuous"
        assert sentinel not in skill_body._parse_skill_frontmatter(body)["description"]
        info = skill_body.resolve_skill_info("test-skill", tree, {})
        assert info.description == "real text"

    def test_fstring_tail_interpolation_still_resolves(self, skill_body: ModuleType) -> None:
        tree = ast.parse(_FSTRING_TAIL_INTERPOLATED, mode="eval").body
        assert skill_body._ELIDED_SENTINEL in skill_body._resolve_skill_body(tree, {})
        assert skill_body.resolve_skill_info("fs-skill", tree, {}).description == "real text"

    def test_unreported_frontmatter_field_may_be_elided(self, skill_body: ModuleType) -> None:
        """The distinction is per-FIELD, not per-block: an elision inside the
        frontmatter is fine so long as it lands on a field this module does
        not report. ``model:`` here; ``description`` is literal and intact."""
        tree = ast.parse(_VAL06_DEFECT_SOURCE, mode="eval").body
        frontmatter = skill_body._parse_skill_frontmatter(skill_body._resolve_skill_body(tree, {}))
        assert skill_body._ELIDED_SENTINEL in frontmatter["model"]
        info = skill_body.resolve_skill_info("test-skill", tree, {})
        assert info.description == "the description text"


class TestNoSentinelLeakage:
    """Control 10. The sentinel exists to be caught, never to be reported.
    No returned ``SkillInfo`` field and no byte count may contain it."""

    _RESOLVING_FIXTURES = (
        _VAL06_DEFECT_SOURCE,
        _VAL06_BRIEF_SOURCE,
        _ANTI_VACUITY_SOURCE,
        _ELISION_OUTSIDE_FRONTMATTER,
        _FSTRING_TAIL_INTERPOLATED,
        _FSTRING_NO_INTERPOLATION,
    )

    @pytest.mark.parametrize("source", _RESOLVING_FIXTURES)
    def test_returned_skillinfo_is_sentinel_free(self, skill_body: ModuleType, source: str) -> None:
        tree = ast.parse(source, mode="eval").body
        info = skill_body.resolve_skill_info("test-skill", tree, {})
        sentinel = skill_body._ELIDED_SENTINEL
        assert sentinel not in info.name
        assert sentinel not in info.description
        assert info.description_bytes == len(info.description.encode("utf-8"))
        assert sentinel not in repr(info)

    def test_real_tree_descriptions_are_sentinel_free(self, skill_body: ModuleType) -> None:
        """The leakage check over the population that actually gets measured."""
        if str(SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPTS_DIR))
        from context_floor_skills import measure_skills

        sentinel = skill_body._ELIDED_SENTINEL
        for skill in measure_skills().skills:
            assert sentinel not in skill.description, skill.name


class TestRealSkillTreeUnchanged:
    """The fix must not move the measurement it exists to protect."""

    def test_measure_skills_totals_unchanged(self) -> None:
        if str(SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPTS_DIR))
        from context_floor_skills import measure_skills

        result = measure_skills()
        assert len(result.skills) == 32
        assert result.description_bytes == 7761
        assert [s.name for s in result.skills if not s.description] == []
