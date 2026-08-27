"""Gap-rate ceiling and gap-cause accuracy for the Python call graph (TAP-6439).

The regression this pins: ``in_repo_gap_rate`` counted every unresolved
attribute call as in-repo resolution debt, because the classifier decided
in-repo vs external from the *root* token of the call expression and so could
not see instance-method calls on stdlib/builtin/third-party receivers. On this
repo that put the rate at 0.471 and made ``tapps_call_graph`` report
``degraded`` on 89% of calls.

These tests pin the behaviour against a FIXTURE project with a hand-known
ground-truth graph rather than the live repo's moving number: every call the
fixture makes is enumerated below, so the expected gap rate is an exact value,
not a threshold that silently drifts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.project.call_graph import build_call_graph_index
from tapps_mcp.project.call_graph_gap_classify import (
    degrades_answer,
    is_external_gap,
    reclassify_external_attr_gaps,
    split_gap_counts,
)
from tapps_mcp.project.call_graph_queries import query_call_graph
from tapps_mcp.project.call_graph_types import ResolutionGap

# The fixture below is written so its whole call graph fits in a comment.
# Every call site, with its ground truth:
#
#   pkg/models.py   Worker.run   -> self.step()        EDGE  Worker.step
#                   Worker.step  -> "  x  ".strip()    gap   str receiver, external
#   pkg/util.py     helper       -> os.getcwd()        EDGE  stdlib module target
#   pkg/service.py  handle       -> Worker()           EDGE  imported class
#                                -> worker.run()       EDGE  Worker.run (typed local)
#                                -> lines.append() x2  gap   list receiver, external
#                                -> path.read_text()   EDGE  pathlib.Path (annotation)
#                                -> helper()           EDGE  imported function
#                                -> len/int/bool()     gap   builtins, external
#
# 6 edges, 6 gaps, and NOT ONE of those gaps is an in-repo edge we failed to
# draw -> in_repo_gap_rate is exactly 0.0. Before TAP-6439 the three receiver
# gaps ('  x  '.strip, lines.append x2) took the in-repo branch, giving 3/6 =
# 0.5 on a fixture with no resolution debt at all.
_FIXTURE: dict[str, str] = {
    "pkg/__init__.py": "",
    "pkg/models.py": """
class Worker:
    def run(self):
        return self.step()

    def step(self):
        return "  x  ".strip()
""",
    "pkg/util.py": """
import os


def helper():
    return os.getcwd()
""",
    "pkg/service.py": """
from pathlib import Path

from pkg.models import Worker
from pkg.util import helper


def handle(path: Path):
    lines = []
    worker = Worker()
    lines.append(worker.run())
    lines.append(path.read_text())
    return len(lines) + int(bool(helper()))
""",
}

_EXPECTED_EDGES = {
    ("pkg.models.Worker.run", "pkg.models.Worker.step"),
    ("pkg.service.handle", "pkg.models.Worker"),
    ("pkg.service.handle", "pkg.models.Worker.run"),
    ("pkg.service.handle", "pathlib.Path.read_text"),
    ("pkg.service.handle", "pkg.util.helper"),
    ("pkg.util.helper", "os.getcwd"),
}
_EXPECTED_GAP_COUNT = 6

# Same shape, plus ONE genuine in-repo miss: ``run_task`` is defined in the repo
# but called on an untyped receiver, so no sound resolver can draw the edge and
# it MUST keep counting as debt. Pins the ceiling from below — a pass that
# reclassified everything would show 0.0 here too.
_DEBT_FIXTURE: dict[str, str] = {
    "pkg/__init__.py": "",
    "pkg/tasks.py": "\nclass Task:\n    def run_task(self):\n        return 1\n",
    "pkg/runner.py": (
        "\ndef drive(anything):\n"
        "    buf = []\n"
        "    buf.append(anything.run_task())\n"
        "    return buf\n"
    ),
}


@pytest.fixture
def fixture_index(tmp_path: Path):
    for rel, source in _FIXTURE.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    return build_call_graph_index(tmp_path, force_rebuild=True)


class TestFixtureGapRate:
    def test_every_resolvable_call_resolves(self, fixture_index) -> None:
        """Ground truth: the fixture's four in-repo-resolvable calls are edges."""
        drawn = {(e.caller, e.callee) for e in fixture_index.edges}
        assert drawn >= _EXPECTED_EDGES, f"missing edges: {_EXPECTED_EDGES - drawn}"

    def test_in_repo_gap_rate_is_exactly_zero(self, fixture_index) -> None:
        """No call in the fixture is in-repo debt, so the rate is 0.0 exactly.

        Before TAP-6439 this was non-zero: ``lines.append`` / ``path.read_text``
        / ``"x".strip()`` all took the in-repo branch of the classifier.
        """
        external, in_repo, reasons = split_gap_counts(fixture_index.resolution_gaps)
        assert in_repo == 0, f"unexpected in-repo gaps: {reasons}"
        assert external == len(fixture_index.resolution_gaps)
        assert in_repo / max(len(fixture_index.edges), 1) == 0.0

    def test_receiver_gaps_carry_the_accurate_cause(self, fixture_index) -> None:
        """A stdlib/builtin receiver is labelled ``external_attr_call``, not
        ``unresolved_static_call`` — the flag has to explain itself."""
        by_expr = {gap.expr: gap.reason for gap in fixture_index.resolution_gaps}
        assert by_expr["lines.append"] == "external_attr_call"
        assert by_expr["'  x  '.strip"] == "external_attr_call"
        # Builtins were already handled by the root heuristic; they keep their
        # existing reason and stay external.
        assert by_expr["len"] == "unresolved_static_call"

    def test_gap_and_edge_counts_are_exact(self, fixture_index) -> None:
        """Pins the denominator too: a pass that quietly dropped gaps or
        invented edges would move the rate without moving the ratio."""
        assert len(fixture_index.edges) == len(_EXPECTED_EDGES)
        assert len(fixture_index.resolution_gaps) == _EXPECTED_GAP_COUNT

    def test_query_on_a_fixture_symbol_is_not_degraded(self, fixture_index) -> None:
        """Acceptance 3: a normal symbol that only calls out to stdlib is clean."""
        result = query_call_graph(fixture_index, "pkg.service.handle", mode="all")
        assert result["found"] is True
        assert result["degraded"] is False
        completeness = result["completeness"]
        assert completeness["complete"] is True
        assert completeness["gap_count"] == 0
        # ...and the external calls are still reported, not hidden.
        assert completeness["external_gap_count"] >= 3
        assert completeness["external_gap_reasons"]["external_attr_call"] >= 2
        assert len(result["resolution_gaps"]) >= 3


class TestReclassificationIsSound:
    def test_name_collision_keeps_the_gap_in_repo(self) -> None:
        """``x.append()`` stays in-repo debt when the repo defines an ``append``.

        Over-counting debt is the safe direction; the pass must never claim a
        call is external just because the receiver type is unknown.
        """
        gaps = [ResolutionGap("pkg.a.run", "buf.append", 3, "unresolved_static_call")]
        out = reclassify_external_attr_gaps(gaps, ["pkg.buffer.Buffer.append"])
        assert out[0].reason == "unresolved_static_call"
        assert is_external_gap(out[0]) is False

    def test_bare_name_gaps_are_never_reclassified(self) -> None:
        """Only attribute calls are in scope — a bare ``helper()`` miss is real
        in-repo debt regardless of whether a symbol of that name is indexed."""
        gaps = [ResolutionGap("pkg.a.run", "helper", 3, "unresolved_static_call")]
        out = reclassify_external_attr_gaps(gaps, [])
        assert out[0].reason == "unresolved_static_call"

    def test_input_gaps_are_not_mutated(self) -> None:
        """The per-file raw material must keep its original reason so an
        incremental update recomputes the same labels a full rebuild would."""
        gap = ResolutionGap("pkg.a.run", "lines.append", 3, "unresolved_static_call")
        out = reclassify_external_attr_gaps([gap], [])
        assert out[0].reason == "external_attr_call"
        assert gap.reason == "unresolved_static_call"

    def test_typescript_gaps_are_untouched(self) -> None:
        gap = ResolutionGap(
            "consumer.run", "svc.load", 1, "receiver_untyped", language="typescript"
        )
        assert reclassify_external_attr_gaps([gap], [])[0].reason == "receiver_untyped"


class TestDegradesAnswer:
    def test_dynamic_dispatch_still_degrades_the_answer(self) -> None:
        """Not fixable debt, but it may still hide an in-repo edge — so the
        per-query flag must stay True even though the rate excludes it."""
        gap = ResolutionGap("pkg.a.run", "getattr(obj, name)()", 1, "dynamic_dispatch")
        assert is_external_gap(gap) is True
        assert degrades_answer(gap) is True

    def test_external_attr_call_does_not_degrade(self) -> None:
        gap = ResolutionGap("pkg.a.run", "lines.append", 1, "external_attr_call")
        assert degrades_answer(gap) is False

    def test_in_repo_unresolved_call_degrades(self) -> None:
        gap = ResolutionGap("pkg.a.run", "helper", 1, "unresolved_static_call")
        assert degrades_answer(gap) is True

    def test_stdlib_module_call_does_not_degrade(self) -> None:
        gap = ResolutionGap("pkg.a.run", "os.getcwd", 1, "unresolved_static_call")
        assert degrades_answer(gap) is False


class TestFixtureWithRealDebt:
    """The ceiling has to bind from below as well as above."""

    @pytest.fixture
    def debt_index(self, tmp_path: Path):
        for rel, source in _DEBT_FIXTURE.items():
            target = tmp_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")
        return build_call_graph_index(tmp_path, force_rebuild=True)

    def test_unresolvable_in_repo_call_still_counts_as_debt(self, debt_index) -> None:
        external, in_repo, reasons = split_gap_counts(debt_index.resolution_gaps)
        assert reasons == {"unresolved_static_call": 1}
        assert in_repo == 1
        assert external == 1  # buf.append
        by_expr = {gap.expr: gap.reason for gap in debt_index.resolution_gaps}
        assert by_expr["anything.run_task"] == "unresolved_static_call"
        assert by_expr["buf.append"] == "external_attr_call"

    def test_debt_fixture_gap_rate_is_its_known_value(self, debt_index) -> None:
        _external, in_repo, _reasons = split_gap_counts(debt_index.resolution_gaps)
        # ``drive`` draws no edges at all, so the rate uses the same max(edges, 1)
        # floor the cache status does: 1 in-repo gap over 0 edges.
        assert len(debt_index.edges) == 0
        assert in_repo / max(len(debt_index.edges), 1) == 1.0

    def test_query_on_the_debt_symbol_is_degraded(self, debt_index) -> None:
        result = query_call_graph(debt_index, "pkg.runner.drive", mode="all")
        assert result["degraded"] is True
        completeness = result["completeness"]
        assert completeness["gap_count"] == 1
        assert completeness["gap_reasons"] == {"unresolved_static_call": 1}
        assert completeness["external_gap_reasons"] == {"external_attr_call": 1}


class TestBuiltinReceiverInference:
    """``lines = []`` proves ``lines.append`` is ``list.append`` (TAP-6439).

    The index-wide name pass cannot help when the called name collides with an
    in-repo one (``get``, ``add``, ``search``): it keeps those gaps as debt, by
    design. A receiver whose type is written down in the source settles it.
    """

    @staticmethod
    def _index(tmp_path: Path, source: str):
        (tmp_path / "pkg").mkdir(parents=True, exist_ok=True)
        (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
        # A same-named in-repo method, so the name pass alone cannot classify.
        (tmp_path / "pkg" / "store.py").write_text(
            "class Store:\n"
            "    def get(self, k):\n        return k\n\n"
            "    def add(self, k):\n        return k\n\n"
            "    def append(self, k):\n        return k\n",
            encoding="utf-8",
        )
        (tmp_path / "pkg" / "user.py").write_text(source, encoding="utf-8")
        return build_call_graph_index(tmp_path, force_rebuild=True)

    def test_display_literal_receiver_is_external(self, tmp_path: Path) -> None:
        index = self._index(
            tmp_path,
            "def run():\n"
            "    buf = []\n"
            "    seen = set()\n"
            "    buf.append(1)\n"
            "    seen.add(1)\n"
            "    return buf\n",
        )
        by_expr = {g.expr: g.reason for g in index.resolution_gaps}
        assert by_expr["buf.append"] == "external_attr_call"
        assert by_expr["seen.add"] == "external_attr_call"
        _external, in_repo, _reasons = split_gap_counts(index.resolution_gaps)
        assert in_repo == 0

    def test_builtin_annotation_receiver_is_external(self, tmp_path: Path) -> None:
        index = self._index(
            tmp_path,
            "def run():\n    table: dict[str, str] = {}\n    return table.get('k')\n",
        )
        by_expr = {g.expr: g.reason for g in index.resolution_gaps}
        assert by_expr["table.get"] == "external_attr_call"

    def test_string_literal_receiver_is_external(self, tmp_path: Path) -> None:
        index = self._index(tmp_path, "def run(parts):\n    return ', '.join(parts)\n")
        by_expr = {g.expr: g.reason for g in index.resolution_gaps}
        assert by_expr["', '.join"] == "external_attr_call"

    def test_class_annotation_still_wins_over_the_builtin_check(self, tmp_path: Path) -> None:
        """An in-repo class annotation must keep resolving to a real edge."""
        index = self._index(
            tmp_path,
            "from pkg.store import Store\n\n\ndef run():\n"
            "    s: Store = Store()\n"
            "    return s.get('k')\n",
        )
        assert ("pkg.user.run", "pkg.store.Store.get") in {
            (e.caller, e.callee) for e in index.edges
        }

    def test_rebinding_to_an_object_wins_over_the_literal(self, tmp_path: Path) -> None:
        """Last assignment wins, as it already did for class bindings."""
        index = self._index(
            tmp_path,
            "from pkg.store import Store\n\n\ndef run():\n"
            "    s = []\n"
            "    s = Store()\n"
            "    return s.get('k')\n",
        )
        assert ("pkg.user.run", "pkg.store.Store.get") in {
            (e.caller, e.callee) for e in index.edges
        }
