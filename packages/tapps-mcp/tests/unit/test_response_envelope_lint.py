"""Tests for scripts/response_envelope_lint.py — the envelope-lie gate (TAP-5660).

The script ships its own ``--test`` self-test, which is what CI runs before the
sweep. These tests cover it from pytest too, so the lint is exercised by
``scripts/run-regression.sh`` and can be extended with cases that would make the
inline fixture block unwieldy.

The failure mode being gated: a response embeds a best-effort sub-result that
failed, and still reports plain success. See TAP-5656.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = REPO_ROOT / "scripts"


@pytest.fixture(scope="module")
def lint() -> ModuleType:
    """Import scripts/response_envelope_lint.py — scripts/ is not a package."""
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    import response_envelope_lint

    return response_envelope_lint


_PREAMBLE = """
from dataclasses import dataclass
from typing import Any

@dataclass
class R:
    brain_mirror: dict[str, Any] | None = None

"""


def _source(body: str) -> str:
    """Prepend the dataclass preamble to an already-flush function body."""
    return _PREAMBLE + textwrap.dedent(body).strip() + "\n"


class TestScriptSelfTest:
    def test_bundled_self_test_passes(self, lint: ModuleType) -> None:
        """The same fixtures CI runs via ``check-response-envelope.py --test``."""
        assert lint is not None  # the fixture puts scripts/ on sys.path
        import response_envelope_selftest

        assert response_envelope_selftest.self_test() == 0


class TestUnhandledSites:
    """The shape that shipped the defects."""

    def test_flags_unexamined_sub_result(self, lint: ModuleType) -> None:
        src = _source("""
            def tool(result: R):
                data = {"brain_mirror": result.brain_mirror}
                return success_response("tool", 1, data)
        """)
        findings = lint.check_source(src, "<t>")
        assert len(findings) == 1
        assert findings[0].key == "brain_mirror"
        assert findings[0].func == "tool"
        assert "without checking it" in findings[0].render()

    def test_flags_each_unexamined_field_separately(self, lint: ModuleType) -> None:
        """Two best-effort fields in one response are two distinct defects."""
        src = textwrap.dedent("""
            from dataclasses import dataclass
            from typing import Any

            @dataclass
            class R:
                brain_mirror: dict[str, Any] | None = None
                session_end: dict[str, Any] | None = None

            def tool(result: R):
                data = {
                    "brain_mirror": result.brain_mirror,
                    "session_end": result.session_end,
                }
                return success_response("tool", 1, data)
        """)
        assert len(lint.check_source(src, "<t>")) == 2


class TestHandledSites:
    """Each documented way of handling a sub-result must clear the gate."""

    def test_degraded_kwarg_clears(self, lint: ModuleType) -> None:
        src = _source("""
            def tool(result: R):
                data = {"brain_mirror": result.brain_mirror}
                return success_response("tool", 1, data, degraded=True)
        """)
        assert lint.check_source(src, "<t>") == []

    def test_branching_clears(self, lint: ModuleType) -> None:
        src = _source("""
            def tool(result: R):
                data = {"brain_mirror": result.brain_mirror}
                if result.brain_mirror and result.brain_mirror.get("error"):
                    return success_response("tool", 1, data, degraded=True)
                return success_response("tool", 1, data)
        """)
        assert lint.check_source(src, "<t>") == []

    def test_justified_allowlist_comment_clears(self, lint: ModuleType) -> None:
        src = _source("""
            def tool(result: R):
                data = {"brain_mirror": result.brain_mirror}  # envelope-ok: advisory only
                return success_response("tool", 1, data)
        """)
        assert lint.check_source(src, "<t>") == []

    def test_bare_allowlist_marker_does_not_clear(self, lint: ModuleType) -> None:
        """An allowlist entry without a reason is not a decision, it is a mute."""
        src = _source("""
            def tool(result: R):
                data = {"brain_mirror": result.brain_mirror}  # envelope-ok:
                return success_response("tool", 1, data)
        """)
        assert len(lint.check_source(src, "<t>")) == 1

    def test_plain_value_is_not_a_best_effort_sub_result(self, lint: ModuleType) -> None:
        """Anchoring on the optional-dict annotation keeps false positives near zero."""
        src = textwrap.dedent("""
            from dataclasses import dataclass

            @dataclass
            class R:
                file_path: str = ""

            def tool(result: R):
                data = {"file_path": result.file_path}
                return success_response("tool", 1, data)
        """)
        assert lint.check_source(src, "<t>") == []


class TestLiveRepository:
    """The gate's point: assert it against the real tree."""

    def test_repo_has_no_unexamined_sub_results(self, lint: ModuleType) -> None:
        """Same sweep CI runs — an empty result here is the contract holding."""
        findings = lint.run_sweep(lint.iter_target_files([]))
        assert findings == [], "\n".join(str(f) for f in findings)
