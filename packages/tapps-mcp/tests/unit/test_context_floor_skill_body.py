"""Tests for scripts/context_floor_skill_body.py -- skill body resolution.

TAP-7755: ``_leading_literal`` resolved a concatenated skill body by following
only ``BinOp.left``, so any segment after a spliced call was never seen. A
``description:`` sitting after such a call was silently truncated away and the
caller then raised ``no description field in frontmatter``.

Five earlier fixes were independently refuted. Each of the five shapes is
replayed below as its own control so that a sixth attempt cannot be a
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
   the folding code at all;
5. the guard moved onto the field's *raw span* -- but the span's boundaries are
   computed by ``_opens_key`` running over sentinel-bearing text, so a column-0
   sentinel line containing a colon opened a bogus key, moved the boundary, and
   carried the sentinel out of the only span the guard reads (PAIR-2 below,
   one character away from PAIR-1, which does raise).

The shape of all five: *a positional guard inherits every position the parser
discards.* The controls below therefore pin the positions as well as the
values -- including the two regions no field's span covers at all, and a
duplicate key whose shadowed occurrence used to be overwritten.

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
        # The literal total the fix's commit message cites. Pinned so the number
        # the message leans on has a committed guard rather than an unasserted
        # sum-consistency check that any two wrong values satisfy.
        assert result.description_bytes == 7750
        leaked = [
            s.name for s in result.skills if any("\ue000" <= ch <= "\uf8ff" for ch in s.description)
        ]
        assert leaked == [], f"elision marker leaked into measured descriptions: {leaked}"


# Attempt 5's minimal pair. These three bodies differ only in what follows the
# block scalar's first continuation line: nothing spliced, a spliced segment, or
# a spliced segment whose first character is a colon. One colon was the whole
# refutation -- ``_opens_key`` read the sentinel line as opening a new field, so
# the sentinel was reassigned out of ``description``'s raw span into a bogus key
# that ``_reject_elided_fields`` does not measure.
_FOLDED_HEAD = "'---\\nname: fixture-skill\\ndescription: >-\\n  Lead sentence.\\n'"
_FOLDED_TAIL = "'---\\n'"


def _folded_with_splice(suffix: str) -> ast.expr:
    return _expr(f"{_FOLDED_HEAD} + {_CALL} + '{suffix}\\n' + {_FOLDED_TAIL}")


class TestAttemptFiveShape:
    """Control 6 -- attempt 5 (the sentinel reassigned out of the span).

    ``_fold_block_scalar`` was fixed by reading the field's raw span instead of
    the folded value, but the span's *boundaries* are themselves computed by a
    predicate running over sentinel-bearing text. A column-0 sentinel line
    containing a colon opened a new key, moving the span boundary so that the
    sentinel landed in an unmeasured field.

    The elision-free twin runs first: it must fold two continuation lines into
    one space-joined value, which only ``_fold_block_scalar`` produces. Without
    it the two raises below could pass for a reason unrelated to folding."""

    def test_elision_free_twin_folds_and_is_accepted(self, body_mod: ModuleType) -> None:
        expr = _expr(f"{_FOLDED_HEAD} + '  trailing words\\n' + {_FOLDED_TAIL}")
        info = body_mod.resolve_skill_info("fixture-skill", expr, {})
        assert info.description == "Lead sentence. trailing words", (
            "fixture does not reach _fold_block_scalar -- the pair below would be vacuous"
        )

    def test_pair_one_splice_without_colon_raises(self, body_mod: ModuleType) -> None:
        with pytest.raises(body_mod.MeasurementError) as excinfo:
            info = body_mod.resolve_skill_info(
                "fixture-skill", _folded_with_splice(" trailing words"), {}
            )
            pytest.fail(f"no raise; reported truncated folded value {info.description!r}")
        assert "description" in str(excinfo.value)

    def test_pair_two_splice_followed_by_a_colon_raises(self, body_mod: ModuleType) -> None:
        """THE refutation of attempt 5. Identical to PAIR-1 but for one colon;
        at base this reports ``'Lead sentence.'`` / 14 bytes and never raises."""
        with pytest.raises(body_mod.MeasurementError) as excinfo:
            info = body_mod.resolve_skill_info(
                "fixture-skill", _folded_with_splice(": trailing words"), {}
            )
            pytest.fail(
                f"no raise; reported {info.description!r} ({info.description_bytes} bytes) -- "
                "the sentinel line opened a bogus key and left description's span"
            )
        assert "description" in str(excinfo.value)


class TestElisionAttributedToNoSpan:
    """Defect 2 -- a position no field's span covers is checked by nobody.

    Two such positions exist: inside the frontmatter but above the first key,
    and above the frontmatter's opening ``---`` altogether. Neither is inside
    any span, so the per-field guard never looks at them; and the text an
    elision stands for is unknown, so either could contain the ``---`` or the
    ``description:`` that decides what this script measures."""

    def test_clean_preamble_line_is_still_accepted(self, body_mod: ModuleType) -> None:
        expr = _expr("'---\\n\\nname: preamble\\ndescription: A real description.\\n---\\n'")
        info = body_mod.resolve_skill_info("preamble", expr, {})
        assert info.description == "A real description.", (
            "a blank line above the first key must not by itself be a failure -- "
            "otherwise the raises below prove nothing about the elision"
        )

    def test_elision_above_the_first_key_raises(self, body_mod: ModuleType) -> None:
        expr = _expr(
            "'---\\n' + "
            + _CALL
            + " + '\\nname: preamble\\ndescription: A real description.\\n---\\n'"
        )
        with pytest.raises(body_mod.MeasurementError) as excinfo:
            info = body_mod.resolve_skill_info("preamble", expr, {})
            pytest.fail(f"no raise; reported description {info.description!r}")
        assert "first key" in str(excinfo.value)

    def test_elision_above_the_start_delimiter_raises(self, body_mod: ModuleType) -> None:
        expr = _expr(
            _CALL + " + '\\n---\\nname: prologue\\ndescription: A real description.\\n---\\n'"
        )
        with pytest.raises(body_mod.MeasurementError) as excinfo:
            info = body_mod.resolve_skill_info("prologue", expr, {})
            pytest.fail(f"no raise; reported description {info.description!r}")
        assert "start delimiter" in str(excinfo.value)


class TestDuplicateKeyShadowing:
    """Defect 3 -- ``result[key] = ...`` overwrote the elided occurrence.

    The clean twin first: it pins that this parser reports the *last*
    occurrence, so the fixture below really is two ``description`` keys and the
    elided one really is the shadowed one."""

    def test_clean_duplicate_reports_the_last_occurrence(self, body_mod: ModuleType) -> None:
        expr = _expr(
            "'---\\nname: dup\\ndescription: first clean value\\n"
            "description: second clean value\\n---\\n'"
        )
        info = body_mod.resolve_skill_info("dup", expr, {})
        assert info.description == "second clean value"

    def test_elided_shadowed_occurrence_raises(self, body_mod: ModuleType) -> None:
        expr = _expr(
            "'---\\nname: dup\\ndescription: ' + "
            + _CALL
            + " + '\\ndescription: second clean value\\n---\\n'"
        )
        with pytest.raises(body_mod.MeasurementError) as excinfo:
            info = body_mod.resolve_skill_info("dup", expr, {})
            pytest.fail(f"no raise; reported description {info.description!r}")
        assert "description" in str(excinfo.value)


# A skill-template module whose bodies are inline string expressions, so
# ``_collect_skill_set`` cannot take the ``_load_claude_skill`` asset shortcut
# and must route through ``resolve_skill_info`` -> ``_resolve_body_text``.
_RESOLVER_FIXTURE_MODULE = """\
CLAUDE_SKILLS: dict[str, str] = {
    "fixture-inline": "---\\nname: fixture-inline\\ndescription: an inline literal body\\n---\\nbody\\n",
    "fixture-concat": "---\\nname: fixture-concat\\n"
    + "description: a concatenated literal body\\n---\\nbody\\n",
}
"""
_RESOLVER_FIXTURE_BYTES = len("an inline literal body") + len("a concatenated literal body")
_CORRUPTION = "broken "


class TestResolverPathPositiveControl:
    """Positive control for the *resolver*, which the real-tree control cannot
    reach at all.

    Over the real tree ``_resolve_body_text`` has **zero** top-level
    invocations: 29 of the 32 skills are read straight off their ``.md`` asset
    by ``_skill_info_from_asset`` and the other 3 take the
    ``_claude_domain_skill`` branch. So ``TestRealTreeMeasurementUnchanged``
    below is evidence about the frontmatter *parser* and no evidence at all
    about the resolver. This fixture tree routes through the resolver, and the
    second half breaks the resolver to show the measurement move -- a control
    nobody has seen go red is not a control."""

    @staticmethod
    def _measure(skills_mod: ModuleType, module: Path) -> int:
        collected = skills_mod._collect_skill_set(module, "CLAUDE_SKILLS")
        assert sorted(collected) == ["fixture-concat", "fixture-inline"]
        return sum(info.description_bytes for info in collected.values())

    def test_breaking_the_resolver_moves_the_measurement(
        self,
        body_mod: ModuleType,
        skills_mod: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        module = tmp_path / "platform_fixture_skills.py"
        module.write_text(_RESOLVER_FIXTURE_MODULE, encoding="utf-8")
        real = body_mod._resolve_body_text

        top_level_calls: list[str] = []

        def counting(node: ast.expr, symtab: dict[str, ast.expr], depth: int = 0) -> str:
            if depth == 0:
                top_level_calls.append(ast.dump(node)[:40])
            return real(node, symtab, depth)

        monkeypatch.setattr(body_mod, "_resolve_body_text", counting)
        clean_bytes = self._measure(skills_mod, module)
        assert len(top_level_calls) == 2, (
            "fixture tree does not reach _resolve_body_text -- this control would be "
            f"as vacuous as the real-tree one (top-level calls: {top_level_calls})"
        )
        assert clean_bytes == _RESOLVER_FIXTURE_BYTES

        def broken(node: ast.expr, symtab: dict[str, ast.expr], depth: int = 0) -> str:
            text = real(node, symtab, depth)
            return (
                text.replace("description: ", f"description: {_CORRUPTION}") if depth == 0 else text
            )

        monkeypatch.setattr(body_mod, "_resolve_body_text", broken)
        broken_bytes = self._measure(skills_mod, module)
        assert broken_bytes == clean_bytes + 2 * len(_CORRUPTION), (
            f"breaking _resolve_body_text did not move the measurement as expected "
            f"({clean_bytes} -> {broken_bytes})"
        )
