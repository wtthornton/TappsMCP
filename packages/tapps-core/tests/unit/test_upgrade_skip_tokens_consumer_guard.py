"""VAL-07 (tmcp-plugin-dist program, lane 4): guard the cross-repo skip-token
contract that ``nlt-orchestrator/scripts/check-skip-tokens.py`` depends on.

That script never ``import``s tapps-core as a package. At
``check-skip-tokens.py:124-138`` it ``exec()``s this module's SOURCE TEXT
into a bare ``types.ModuleType`` -- read via ``git show origin/HEAD:<path>``
against the TappsMCP checkout path named in nlt-orchestrator's
``fleet.paths.json`` (``/home/wtthornton/code/tapps-mcp`` at the time this
guard was written), never this working tree -- and then does a plain
``hasattr(module, attr)`` check for three names: ``ALL_SKIP_TOKENS``,
``unknown_skip_tokens``, ``nearest_token``. Nothing in tapps-mcp's own test
suite previously noticed a break on that surface, because the consumer
lives in a different repo and a normal ``import`` would tolerate re-export
tricks (``__getattr__``, a shim re-export) that the consumer's raw exec
will not resolve the same way.

A green run of this file is NECESSARY BUT NOT SUFFICIENT for "the fleet
checker passes": the checker reads ``origin/HEAD`` of the TappsMCP
checkout, not this branch's working tree, so this guard is invisible to
that consumer until this branch is merged to ``master`` and ``origin/HEAD``
moves. See ``prompts/tmcp-plugin-lane-4-skip-token-guard.md`` for the full
execution-path argument this lane was told to state plainly.

``TestPositiveControlRealModuleExecsLikeTheConsumer`` and
``TestNegativeControlRenamedSymbolFailsTheSameWay`` replicate the
consumer's own exec-and-hasattr mechanism against, respectively, the real
module source and a SCRATCH COPY (a pytest ``tmp_path``, never the real
file) with ``ALL_SKIP_TOKENS`` renamed -- proving the positive-control
assertions actually would catch the exact regression VAL-07 names, rather
than being a vacuous "the module currently imports" check.
"""

from __future__ import annotations

import types
from pathlib import Path

from tapps_core.config import upgrade_skip_tokens
from tapps_core.config.upgrade_skip_tokens import (
    ALL_SKIP_TOKENS,
    nearest_token,
    unknown_skip_tokens,
)

# Pinned via the imported module's own __file__ (same pattern as
# test_upgrade_skip_token_call_site_walker.py's `Path(tapps_mcp.__file__)`)
# -- never located by a filesystem search, per the lane brief.
_MODULE_PATH = Path(upgrade_skip_tokens.__file__).resolve()

# The three names check-skip-tokens.py's _load_vocabulary() hasattr-checks,
# in the order it checks them (check-skip-tokens.py:132).
_REQUIRED_ATTRS = ("unknown_skip_tokens", "nearest_token", "ALL_SKIP_TOKENS")


def _exec_module_source(source: str, label: str) -> types.ModuleType:
    """Reproduce the consumer's own loading mechanism exactly.

    ``check-skip-tokens.py._load_vocabulary()`` does precisely this:
    compile the source text and exec it into a bare ``ModuleType``'s
    ``__dict__``, then hasattr-check three names. A plain ``import`` would
    tolerate re-export shims and ``__getattr__`` tricks the consumer's raw
    exec cannot -- so this test must use the same mechanism to guard the
    same contract, not a friendlier one.
    """
    module = types.ModuleType("upgrade_skip_tokens_under_test")
    exec(compile(source, label, "exec"), module.__dict__)  # noqa: S102 - mirrors the consumer's own exec() load
    return module


class TestPositiveControlRealModuleExecsLikeTheConsumer:
    """The real module, loaded the way the consumer loads it, must satisfy
    every hasattr check and hand back the shapes the consumer relies on."""

    def test_all_three_symbols_resolve_via_the_consumers_own_exec_mechanism(self) -> None:
        source = _MODULE_PATH.read_text(encoding="utf-8")
        module = _exec_module_source(source, str(_MODULE_PATH))
        for attr in _REQUIRED_ATTRS:
            assert hasattr(module, attr), f"consumer's hasattr({attr!r}) would fail"

    def test_all_skip_tokens_is_a_nonempty_string_collection(self) -> None:
        # What the consumer does with it: `len(vocab.ALL_SKIP_TOKENS)` in its
        # summary line -- so it must be sized, and each member str (it is
        # joined into a comma-separated message elsewhere in this module).
        assert isinstance(ALL_SKIP_TOKENS, (frozenset, set))
        assert len(ALL_SKIP_TOKENS) > 0
        assert all(isinstance(token, str) for token in ALL_SKIP_TOKENS)

    def test_unknown_skip_tokens_returns_list_of_str_and_filters_correctly(self) -> None:
        # What the consumer does: entries, _ = _read_skip_entries(path);
        # for bad in vocab.unknown_skip_tokens(entries): f["entry"] = bad
        valid = sorted(ALL_SKIP_TOKENS)[:2]
        bad_entry = "not-a-real-token-xyz"
        result = unknown_skip_tokens([*valid, bad_entry])
        assert result == [bad_entry]
        assert all(isinstance(item, str) for item in result)
        assert unknown_skip_tokens(valid) == []

    def test_nearest_token_returns_optional_str_the_consumer_can_print_or_skip(self) -> None:
        # What the consumer does: f["use_instead"] = vocab.nearest_token(bad);
        # later: `fix = f"use '{f['use_instead']}'" if f["use_instead"] else
        # "no token covers this path"` -- so both a str and None must work.
        inside_directory_token = ".claude/skills/some-skill/SKILL.md"
        covering = nearest_token(inside_directory_token)
        assert isinstance(covering, str)
        assert covering in ALL_SKIP_TOKENS  # the directory token is itself a valid token

        no_match = nearest_token("totally/unrelated/path.txt")
        assert no_match is None


class TestNegativeControlRenamedSymbolFailsTheSameWay:
    """Mutate a SCRATCH COPY of the module source (never the real file) so
    ``ALL_SKIP_TOKENS`` no longer exists under that name, load it exactly
    the way the consumer does, and require the consumer's own hasattr
    check to fail -- proving the positive-control assertions above are not
    vacuous against the exact regression VAL-07 exists to catch. Run this
    class FIRST when reading evidence: it must go RED before anything else
    is trusted green."""

    def test_renamed_all_skip_tokens_fails_the_consumers_hasattr_check(
        self, tmp_path: Path
    ) -> None:
        real_source = _MODULE_PATH.read_text(encoding="utf-8")
        # A plain identifier rename. Confirmed by grep against the real
        # module (2026-09-16) that "ALL_SKIP_TOKENS" occurs only as the
        # export's own definition, its __all__ entry, and mentions of
        # itself in comments/docstrings -- never as a substring inside a
        # different identifier -- so a bare str.replace is safe here.
        mutated_source = real_source.replace("ALL_SKIP_TOKENS", "RENAMED_TOKENS")
        assert "ALL_SKIP_TOKENS" not in mutated_source  # mutation actually landed
        assert "RENAMED_TOKENS" in mutated_source

        scratch_copy = tmp_path / "upgrade_skip_tokens_scratch.py"
        scratch_copy.write_text(mutated_source, encoding="utf-8")

        module = _exec_module_source(scratch_copy.read_text(encoding="utf-8"), str(scratch_copy))

        # RED: this is the exact condition under which check-skip-tokens.py's
        # _load_vocabulary() calls _fail_compare() and the fleet checker
        # exits 2 ("cannot compare").
        assert not hasattr(module, "ALL_SKIP_TOKENS")
        # The rename did not remove the OTHER two required symbols -- proves
        # this control isolates ALL_SKIP_TOKENS specifically, rather than
        # "exec blew up" for an unrelated reason that would also hide a
        # real regression in the other two.
        assert hasattr(module, "unknown_skip_tokens")
        assert hasattr(module, "nearest_token")

        # Delete the scratch copy explicitly (the brief's instruction),
        # rather than relying only on pytest's tmp_path cleanup.
        scratch_copy.unlink()

        # Untouched: the negative control never wrote to the real file.
        assert _MODULE_PATH.read_text(encoding="utf-8") == real_source

    def test_real_module_is_unaffected_by_the_scratch_mutation(self) -> None:
        """Sanity: the real module still exposes every symbol after the
        mutation above -- proves the scratch copy was never the source of
        truth this file (or the real consumer) reads from."""
        assert hasattr(upgrade_skip_tokens, "ALL_SKIP_TOKENS")
        assert hasattr(upgrade_skip_tokens, "unknown_skip_tokens")
        assert hasattr(upgrade_skip_tokens, "nearest_token")
