"""Tests for resolution gap classification (TAP-4269)."""

from __future__ import annotations

from tapps_mcp.project.call_graph_gap_classify import (
    expr_root,
    is_external_gap,
    split_gap_counts,
)
from tapps_mcp.project.call_graph_types import ResolutionGap


def test_expr_root_simple_call() -> None:
    assert expr_root("json.loads(x)") == "json"


def test_is_external_gap_stdlib() -> None:
    gap = ResolutionGap("demo.main.run", "len(items)", 10, "unresolved_static_call")
    assert is_external_gap(gap) is True


def test_is_external_gap_dynamic_dispatch() -> None:
    gap = ResolutionGap("demo.main.run", "getattr(obj, name)()", 10, "dynamic_dispatch")
    assert is_external_gap(gap) is True


def test_is_external_gap_in_repo_unresolved() -> None:
    gap = ResolutionGap(
        "demo.main.run",
        "helper()",
        10,
        "unresolved_static_call",
    )
    assert is_external_gap(gap) is False


def test_split_gap_counts() -> None:
    gaps = [
        ResolutionGap("a", "len(x)", 1, "unresolved_static_call"),
        ResolutionGap("a", "helper()", 2, "unresolved_static_call"),
        ResolutionGap("a", "getattr(x)", 3, "dynamic_dispatch"),
    ]
    external, in_repo, reasons = split_gap_counts(gaps)
    assert external == 2
    assert in_repo == 1
    assert reasons == {"unresolved_static_call": 1}


# --- Language-aware classification (TAP-4539) ---


def test_ts_external_package_gap_is_external() -> None:
    # `fs`/`lodash` are not in Python's stdlib set — without the language branch
    # they'd wrongly count as in-repo and inflate the gap rate.
    gap = ResolutionGap(
        "consumer.run", "readFile()", 1, "import_unresolved", language="typescript"
    )
    assert is_external_gap(gap) is True


def test_ts_stdlib_named_expr_does_not_borrow_python_heuristics() -> None:
    # A TS gap whose root happens to be a Python stdlib name (`os`) must NOT be
    # classified external via the Python heuristic — only its reason decides.
    gap = ResolutionGap(
        "consumer.run", "os.stuff()", 1, "receiver_untyped", language="typescript"
    )
    assert is_external_gap(gap) is False


def test_ts_deferred_reasons_are_in_repo() -> None:
    for reason in (
        "unresolved_default_export",
        "reexport_unresolved",
        "path_alias_unresolved",
        "receiver_untyped",
    ):
        gap = ResolutionGap("consumer.run", "x()", 1, reason, language="typescript")
        assert is_external_gap(gap) is False, reason


def test_ts_external_gap_does_not_inflate_in_repo_rate() -> None:
    # AC5: a TS external (`fs`) gap alongside a real in-repo deferred gap must
    # leave the in-repo count at 1, not 2.
    gaps = [
        ResolutionGap(
            "consumer.run", "readFile()", 1, "import_unresolved", language="typescript"
        ),
        ResolutionGap(
            "consumer.run",
            "makeDefault()",
            2,
            "unresolved_default_export",
            language="typescript",
        ),
    ]
    external, in_repo, reasons = split_gap_counts(gaps)
    assert external == 1
    assert in_repo == 1
    assert reasons == {"unresolved_default_export": 1}


def test_python_gap_still_uses_heuristics() -> None:
    # Regression: the Python path is unchanged — stdlib root => external.
    gap = ResolutionGap("demo.run", "os.getcwd()", 1, "unresolved_static_call")
    assert is_external_gap(gap) is True
