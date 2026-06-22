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
