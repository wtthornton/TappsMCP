"""Call-graph edge precision/recall eval harness (TAP: resolver-quality gate).

The existing ``test_call_graph.py`` suite is functional (happy-path assertions
on individual edges). It cannot answer the load-bearing question for resolver
work: *are we resolving MORE in-repo call sites than before, or fewer?* The
session_start summary reports an aggregate in-repo gap rate (~54% on this repo),
but an aggregate over uncontrolled source cannot distinguish "resolver got
better" from "the code changed".

This module gives a controlled, hand-labeled corpus and a precision/recall
metric over resolved edges, so resolver changes can be gated on a ratchet:

* **Recall** = fraction of the golden in-repo edges the resolver actually
  produced. Low recall == the resolver debt (unresolved in-repo static calls).
* **Precision** = fraction of resolved edges that are correct. This guards
  against a resolver "improvement" that inflates recall by fabricating or
  mis-binding edges (e.g. resolving ``foo()`` to the wrong ``foo``).

Every fixture enumerates *all* of its expected in-repo resolved edges, so any
resolved edge not in the golden set is a genuine false positive — not an edge
the author merely forgot to list.

The corpus deliberately spans easy patterns (resolved today) and hard patterns
(the resolver debt: cross-module aliased imports, module-attribute calls,
re-exports, instance-method calls). Keeping known-hard cases in the corpus is
the point: they give recall headroom for the resolver work to move.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from tapps_mcp.project.call_graph import build_call_graph_index
from tapps_mcp.project.call_graph_gap_classify import split_gap_counts

Edge = tuple[str, str]


@dataclass(frozen=True)
class GoldenCase:
    """One fixture: a small package + the complete set of in-repo edges it should yield.

    ``expected_edges`` MUST be exhaustive for in-repo calls in ``files`` — the
    precision metric treats any resolved edge outside this set as a false
    positive. ``hard`` flags patterns that exercise known resolver debt; it is
    informational (surfaced in the report) and does not change scoring.
    """

    name: str
    files: dict[str, str]
    expected_edges: frozenset[Edge]
    hard: bool = False


@dataclass
class CaseResult:
    name: str
    hard: bool
    expected: frozenset[Edge]
    resolved: frozenset[Edge]
    in_repo_gaps: int

    @property
    def true_positives(self) -> frozenset[Edge]:
        return self.expected & self.resolved

    @property
    def false_negatives(self) -> frozenset[Edge]:
        return self.expected - self.resolved

    @property
    def false_positives(self) -> frozenset[Edge]:
        return self.resolved - self.expected


@dataclass
class EvalReport:
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def tp(self) -> int:
        return sum(len(c.true_positives) for c in self.cases)

    @property
    def fp(self) -> int:
        return sum(len(c.false_positives) for c in self.cases)

    @property
    def fn(self) -> int:
        return sum(len(c.false_negatives) for c in self.cases)

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return round(self.tp / denom, 4) if denom else 1.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return round(self.tp / denom, 4) if denom else 1.0

    def summary(self) -> dict[str, object]:
        return {
            "cases": len(self.cases),
            "true_positives": self.tp,
            "false_positives": self.fp,
            "false_negatives": self.fn,
            "precision": self.precision,
            "recall": self.recall,
            "missed_edges": sorted(
                f"{c.name}: {caller} -> {callee}"
                for c in self.cases
                for caller, callee in c.false_negatives
            ),
            "spurious_edges": sorted(
                f"{c.name}: {caller} -> {callee}"
                for c in self.cases
                for caller, callee in c.false_positives
            ),
        }


def evaluate_case(root: Path, case: GoldenCase) -> CaseResult:
    """Materialize one case under ``root/<name>`` and score its resolved edges."""
    case_dir = root / case.name
    for rel, source in case.files.items():
        path = case_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    index = build_call_graph_index(case_dir, force_rebuild=True)
    resolved: frozenset[Edge] = frozenset(
        (e.caller, e.callee) for e in index.edges if e.resolved
    )
    _external, in_repo_gaps, _reasons = split_gap_counts(index.resolution_gaps)
    return CaseResult(
        name=case.name,
        hard=case.hard,
        expected=case.expected_edges,
        resolved=resolved,
        in_repo_gaps=in_repo_gaps,
    )


def evaluate(root: Path, cases: list[GoldenCase]) -> EvalReport:
    """Run the whole corpus and aggregate precision/recall."""
    return EvalReport(cases=[evaluate_case(root, c) for c in cases])


# ---------------------------------------------------------------------------
# Golden corpus. Every entry enumerates ALL expected in-repo resolved edges.
# `pkg/` is used so every module is importable as `pkg.<mod>`.
# ---------------------------------------------------------------------------

GOLDEN_CASES: list[GoldenCase] = [
    # --- Easy: resolved by the per-file analyzer today -------------------
    GoldenCase(
        name="direct_call",
        files={
            "pkg/mod.py": (
                "def callee():\n"
                "    return 1\n"
                "\n"
                "def caller():\n"
                "    return callee()\n"
            )
        },
        expected_edges=frozenset({("pkg.mod.caller", "pkg.mod.callee")}),
    ),
    GoldenCase(
        name="self_method",
        files={
            "pkg/svc.py": (
                "class Worker:\n"
                "    def helper(self):\n"
                "        return 0\n"
                "\n"
                "    def run(self):\n"
                "        return self.helper()\n"
            )
        },
        expected_edges=frozenset({("pkg.svc.Worker.run", "pkg.svc.Worker.helper")}),
    ),
    GoldenCase(
        name="from_import_call",
        files={
            "pkg/util.py": "def compute():\n    return 42\n",
            "pkg/app.py": (
                "from pkg.util import compute\n"
                "\n"
                "def handler():\n"
                "    return compute()\n"
            ),
        },
        expected_edges=frozenset({("pkg.app.handler", "pkg.util.compute")}),
    ),
    # --- Hard: known resolver debt (recall headroom for #3) ---------------
    GoldenCase(
        name="aliased_import_call",
        files={
            "pkg/util.py": "def compute():\n    return 42\n",
            "pkg/app.py": (
                "from pkg.util import compute as run_it\n"
                "\n"
                "def handler():\n"
                "    return run_it()\n"
            ),
        },
        expected_edges=frozenset({("pkg.app.handler", "pkg.util.compute")}),
        hard=True,
    ),
    GoldenCase(
        name="module_attribute_call",
        files={
            "pkg/util.py": "def compute():\n    return 42\n",
            "pkg/app.py": (
                "from pkg import util\n"
                "\n"
                "def handler():\n"
                "    return util.compute()\n"
            ),
        },
        expected_edges=frozenset({("pkg.app.handler", "pkg.util.compute")}),
        hard=True,
    ),
    GoldenCase(
        name="module_import_alias_attr",
        files={
            "pkg/util.py": "def compute():\n    return 42\n",
            "pkg/app.py": (
                "import pkg.util as u\n"
                "\n"
                "def handler():\n"
                "    return u.compute()\n"
            ),
        },
        expected_edges=frozenset({("pkg.app.handler", "pkg.util.compute")}),
        hard=True,
    ),
    GoldenCase(
        name="reexport_call",
        files={
            "pkg/core.py": "def engine():\n    return 1\n",
            "pkg/api.py": "from pkg.core import engine\n",
            "pkg/app.py": (
                "from pkg.api import engine\n"
                "\n"
                "def handler():\n"
                "    return engine()\n"
            ),
        },
        # Correct binding is the definition site, regardless of the re-export hop.
        expected_edges=frozenset({("pkg.app.handler", "pkg.core.engine")}),
        hard=True,
    ),
    GoldenCase(
        name="instance_method_call",
        files={
            "pkg/svc.py": (
                "class Worker:\n"
                "    def helper(self):\n"
                "        return 0\n"
            ),
            "pkg/app.py": (
                "from pkg.svc import Worker\n"
                "\n"
                "def handler():\n"
                "    w = Worker()\n"
                "    return w.helper()\n"
            ),
        },
        # Two real edges: the constructor call ``Worker()`` and the method call.
        expected_edges=frozenset(
            {
                ("pkg.app.handler", "pkg.svc.Worker"),
                ("pkg.app.handler", "pkg.svc.Worker.helper"),
            }
        ),
        hard=True,
    ),
    GoldenCase(
        name="typed_param_method_call",
        files={
            "pkg/svc.py": (
                "class Worker:\n"
                "    def helper(self):\n"
                "        return 0\n"
            ),
            "pkg/app.py": (
                "from pkg.svc import Worker\n"
                "\n"
                "def handler(w: Worker):\n"
                "    return w.helper()\n"
            ),
        },
        expected_edges=frozenset({("pkg.app.handler", "pkg.svc.Worker.helper")}),
        hard=True,
    ),
    GoldenCase(
        name="annotated_local_method_call",
        files={
            "pkg/svc.py": (
                "class Worker:\n"
                "    def helper(self):\n"
                "        return 0\n"
                "\n"
                "def make():\n"
                "    return Worker()\n"
            ),
            "pkg/app.py": (
                "from pkg.svc import Worker, make\n"
                "\n"
                "def handler():\n"
                "    w: Worker = make()\n"
                "    return w.helper()\n"
            ),
        },
        # handler -> make (call) and handler -> Worker.helper (annotated local).
        expected_edges=frozenset(
            {
                ("pkg.app.handler", "pkg.svc.make"),
                ("pkg.app.handler", "pkg.svc.Worker.helper"),
            }
        ),
        hard=True,
    ),
    GoldenCase(
        name="relative_import_call",
        files={
            "pkg/util.py": "def compute():\n    return 42\n",
            "pkg/app.py": (
                "from .util import compute\n"
                "\n"
                "def handler():\n"
                "    return compute()\n"
            ),
        },
        expected_edges=frozenset({("pkg.app.handler", "pkg.util.compute")}),
        hard=True,
    ),
    GoldenCase(
        name="nested_local_call",
        files={
            "pkg/mod.py": (
                "def leaf():\n"
                "    return 1\n"
                "\n"
                "def outer():\n"
                "    def inner():\n"
                "        return leaf()\n"
                "    return inner()\n"
            )
        },
        # outer -> inner (local def) and inner -> leaf (module scope). The
        # resolver currently ALSO emits a spurious outer -> leaf (nested-scope
        # over-attribution) — tracked as known debt in the eval test.
        expected_edges=frozenset(
            {
                ("pkg.mod.outer", "pkg.mod.outer.inner"),
                ("pkg.mod.outer.inner", "pkg.mod.leaf"),
            }
        ),
        hard=True,
    ),
]


def run_default_eval(root: Path) -> EvalReport:
    """Evaluate the built-in golden corpus under a scratch ``root``."""
    return evaluate(root, GOLDEN_CASES)
