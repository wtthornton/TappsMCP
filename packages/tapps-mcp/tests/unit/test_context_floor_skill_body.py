"""Tests for scripts/context_floor_skill_body.py -- skill body resolution.

TAP-7755: ``_leading_literal`` resolved a concatenated skill body by following
only ``BinOp.left``, so any segment after a spliced call was never seen. A
``description:`` sitting after such a call was silently truncated away and the
caller then raised ``no description field in frontmatter``.

Four earlier fixes were independently refuted. Each of the four shapes is
replayed below as its own control so that a fifth attempt cannot be a
rediscovery of one of them:

1. walk both ``BinOp`` operands, resolving an elided call to ``""`` -- turned a
   loud failure into a wrong number (``'prefix-' + CALL() + '-suffix'`` measured
   as ``prefix--suffix``);
2. a ``ResolvedBody(text, elided)`` flag refusing only when
   ``elided and not description`` -- silent on a partly-elided, non-empty value
   and on a quoted whitespace-only one;
3. sentinel substitution guarded on the *parsed* value -- ``_fold_block_scalar``
   continues only while a line is indented or blank, so a sentinel-bearing line
   aborts folding, is excluded from the value, and the guard never fires;
4. the same, shipped with a block-folding control whose fixture never reached
   the folding code at all.

Every control here exercises only names that exist in the *unfixed* module, so
the red it produces at base is the defect and not an ``AttributeError``.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = REPO_ROOT / "scripts"


@pytest.fixture(scope="module")
def body_mod() -> ModuleType:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        "context_floor_skill_body", SCRIPTS_DIR / "context_floor_skill_body.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["context_floor_skill_body"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def skills_mod() -> ModuleType:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        "context_floor_skills", SCRIPTS_DIR / "context_floor_skills.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["context_floor_skills"] = module
    spec.loader.exec_module(module)
    return module


def _expr(source: str) -> ast.expr:
    """Parse *source* as a single expression, the way the real scripts see a
    ``CLAUDE_SKILLS[...]`` dict value."""
    parsed = ast.parse(source, mode="eval")
    return parsed.body


# ``_spliced()`` stands in for every expression the resolver cannot evaluate
# statically: a helper call, an imported name, an f-string interpolation.
_CALL = "_spliced()"


class TestCallSplicedAheadOfDescription:
    """Control 1 -- the shape on the issue. RED at base: the resolver stops at
    the call, the description is never seen, and the caller raises."""

    def test_description_after_a_spliced_call_resolves_whole(self, body_mod: ModuleType) -> None:
        expr = _expr(
            "'---\\nname: after-splice\\n' + "
            + _CALL
            + " + '\\ndescription: the whole description, not a fragment\\n---\\nbody\\n'"
        )
        info = body_mod.resolve_skill_info("after-splice", expr, {})
        assert info.description == "the whole description, not a fragment"


class TestAttemptOneShape:
    """Control 2 -- attempt 1 (walk both operands, elided call -> ``""``).

    A call spliced *inside* the description value must raise. Attempt 1 reported
    ``prefix--suffix``; the unfixed code reports ``prefix-``. Both are wrong
    numbers where a loud failure is required."""

    def test_call_inside_description_value_raises(self, body_mod: ModuleType) -> None:
        expr = _expr(
            "'---\\nname: mid-value\\ndescription: prefix-' + " + _CALL + " + '-suffix\\n---\\n'"
        )
        with pytest.raises(body_mod.MeasurementError) as excinfo:
            info = body_mod.resolve_skill_info("mid-value", expr, {})
            pytest.fail(
                f"no raise; reported description {info.description!r} "
                "(attempt 1 reported 'prefix--suffix', unfixed reports 'prefix-')"
            )
        assert "mid-value" in str(excinfo.value)


class TestAttemptTwoShape:
    """Control 3 -- attempt 2 (``elided and not description``).

    That guard fired only when the elision was the *entire* value. Both fixtures
    below survive it: one leaves a non-empty tail, the other a quoted
    whitespace-only value that satisfies the falsiness check."""

    def test_partly_elided_non_empty_description_raises(self, body_mod: ModuleType) -> None:
        expr = _expr(
            "'---\\nname: partly\\ndescription: ' + "
            + _CALL
            + " + ' and a non-empty tail\\n---\\n'"
        )
        with pytest.raises(body_mod.MeasurementError):
            info = body_mod.resolve_skill_info("partly", expr, {})
            pytest.fail(f"no raise; reported description {info.description!r}")

    def test_quoted_whitespace_only_description_raises(self, body_mod: ModuleType) -> None:
        expr = _expr(
            "'---\\nname: whitespace\\ndescription: \"' + " + _CALL + " + '   \"\\n---\\n'"
        )
        with pytest.raises(body_mod.MeasurementError):
            info = body_mod.resolve_skill_info("whitespace", expr, {})
            pytest.fail(f"no raise; reported description {info.description!r}")


class TestAttemptThreeShape:
    """Control 4 -- attempt 3 (sentinel read off the *parsed* value).

    ``_fold_block_scalar`` continues only while a line is indented or blank, so
    a spliced segment occupying its own line aborts folding and never reaches
    the parsed value. The guard must therefore read the field's *raw*
    frontmatter span, not the folded string."""

    def test_elision_in_block_scalar_continuation_raises(self, body_mod: ModuleType) -> None:
        expr = _expr(
            "'---\\nname: folded\\ndescription: >-\\n  first continuation line\\n' + "
            + _CALL
            + " + '\\n  second continuation line\\n---\\n'"
        )
        with pytest.raises(body_mod.MeasurementError):
            info = body_mod.resolve_skill_info("folded", expr, {})
            pytest.fail(f"no raise; reported a truncated folded value {info.description!r}")


class TestAttemptFourShape:
    """Control 5 -- attempt 4 (a folding control whose fixture never reached the
    folding code).

    The first assertion proves the fixture family genuinely exercises
    ``_fold_block_scalar``: an elision-free twin must fold two continuation
    lines into one space-joined value, which only the folder produces. The
    second then requires the raise on the elided twin. If the fixture stopped
    reaching the folder, the first assertion fails rather than passing
    vacuously."""

    def test_folding_is_reached_and_elided_twin_raises(self, body_mod: ModuleType) -> None:
        clean = _expr(
            "'---\\nname: folded-twin\\ndescription: >-\\n"
            "  first continuation line\\n  second continuation line\\n---\\n'"
        )
        clean_info = body_mod.resolve_skill_info("folded-twin", clean, {})
        assert clean_info.description == "first continuation line second continuation line", (
            "fixture does not reach _fold_block_scalar -- the control would be vacuous"
        )

        elided = _expr(
            "'---\\nname: folded-twin\\ndescription: >-\\n  first continuation line\\n' + "
            + _CALL
            + " + '\\n  second continuation line\\n---\\n'"
        )
        with pytest.raises(body_mod.MeasurementError):
            info = body_mod.resolve_skill_info("folded-twin", elided, {})
            pytest.fail(f"no raise; reported {info.description!r}")


class TestElisionOutsideMeasuredFields:
    """An elision that lands outside every measured field still resolves.

    Non-vacuity: the two fixtures differ *only* in where the same spliced call
    sits. The second raises, which is only possible if the resolver emitted a
    detectable marker for that call -- so the elision in the first genuinely
    occurred and was not silently dropped."""

    def test_elision_in_unmeasured_field_still_measures(self, body_mod: ModuleType) -> None:
        outside = _expr(
            "'---\\nname: outside-' + " + _CALL + " + '\\ndescription: measured whole\\n---\\n'"
        )
        info = body_mod.resolve_skill_info("outside", outside, {})
        assert info.description == "measured whole"

        inside = _expr(
            "'---\\nname: outside\\ndescription: measured-' + " + _CALL + " + '\\n---\\n'"
        )
        with pytest.raises(body_mod.MeasurementError):
            body_mod.resolve_skill_info("outside", inside, {})


class TestLoudFailurePreserved:
    """A body with no ``description:`` anywhere still raises."""

    def test_no_description_anywhere_raises(self, body_mod: ModuleType) -> None:
        expr = _expr("'---\\nname: bare\\n---\\nmarkdown body only\\n'")
        with pytest.raises(body_mod.MeasurementError) as excinfo:
            body_mod.resolve_skill_info("bare", expr, {})
        assert "no description field in frontmatter" in str(excinfo.value)

    def test_no_description_after_an_elision_raises(self, body_mod: ModuleType) -> None:
        expr = _expr("'---\\nname: bare\\n' + " + _CALL)
        with pytest.raises(body_mod.MeasurementError) as excinfo:
            body_mod.resolve_skill_info("bare", expr, {})
        assert "no description field in frontmatter" in str(excinfo.value)


class TestContextAndInvocationFieldsAreMeasured:
    """``context:`` and ``disable-model-invocation:`` feed ``SkillInfo`` too, so
    an elision inside either is an elision inside a measured field."""

    @pytest.mark.parametrize("field", ["context", "disable-model-invocation"])
    def test_elision_in_other_measured_field_raises(self, body_mod: ModuleType, field: str) -> None:
        expr = _expr(
            f"'---\\nname: flags\\ndescription: fine\\n{field}: ' + " + _CALL + " + '\\n---\\n'"
        )
        with pytest.raises(body_mod.MeasurementError):
            body_mod.resolve_skill_info("flags", expr, {})


class TestFStringBodies:
    """An f-string body is the same defect in another node type: everything
    after the leading literal chunk was discarded."""

    def test_description_after_an_interpolation_resolves(self, body_mod: ModuleType) -> None:
        expr = _expr(
            "f'---\\nname: fstring-{model}\\ndescription: resolved past the interpolation\\n---\\n'"
        )
        info = body_mod.resolve_skill_info("fstring", expr, {})
        assert info.description == "resolved past the interpolation"

    def test_interpolation_inside_description_raises(self, body_mod: ModuleType) -> None:
        expr = _expr("f'---\\nname: fstring\\ndescription: uses {model} inline\\n---\\n'")
        with pytest.raises(body_mod.MeasurementError):
            body_mod.resolve_skill_info("fstring", expr, {})


class TestRealTreeMeasurementUnchanged:
    """Positive control. Non-vacuous: it fails if the fix changes how many
    skills resolve, if the per-skill bytes stop summing to the reported total,
    or if any elision marker leaks into a measured description."""

    def test_measure_skills_still_reports_thirty_two_clean_skills(
        self, skills_mod: ModuleType
    ) -> None:
        result = skills_mod.measure_skills()
        assert len(result.skills) == 32
        assert result.description_bytes == sum(s.description_bytes for s in result.skills)
        assert result.description_bytes > 0
        leaked = [
            s.name for s in result.skills if any("\ue000" <= ch <= "\uf8ff" for ch in s.description)
        ]
        assert leaked == [], f"elision marker leaked into measured descriptions: {leaked}"
