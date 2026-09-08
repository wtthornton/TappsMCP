"""Tests for tapps_file_api: file-skeleton queries over the call-graph index.

VAL-13: negative control on a real multi-line signature (the body line must
never leak into `signature`), plus the "stale/missing index looks like an
empty file" trap (LANE_ISSUE).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.project.call_graph import build_call_graph_index
from tapps_mcp.project.file_api import query_file_skeleton, resolve_file_in_index

pytestmark = pytest.mark.usefixtures("envelope_guard")

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "file_api_repo"


def _write(root: Path, rel: str, source: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# query_file_skeleton (pure function)
# ---------------------------------------------------------------------------


def test_fixture_file_has_exactly_four_symbols_with_matching_lines() -> None:
    """VAL-13: fixture with 4 symbols -> 4 signatures with lines matching grep -n."""
    index = build_call_graph_index(FIXTURE_REPO, force_rebuild=True)
    result = query_file_skeleton(index, FIXTURE_REPO, "pkg_a/calc.py")

    assert result["index_status"] == "ready"
    assert result["found"] is True
    symbols = result["symbols"]
    assert len(symbols) == 4

    # `grep -n "^def \|^    def "` against the fixture, recorded by hand and
    # re-verified against the file so this test fails loudly if the fixture
    # ever drifts from these line numbers.
    expected_lines = {
        "pkg_a.calc.add": 4,
        "pkg_a.calc.subtract": 8,
        "pkg_a.calc.Calculator.multiply": 13,
        "pkg_a.calc.Calculator.divide": 16,
    }
    assert {s["qualified_name"] for s in symbols} == set(expected_lines)
    for sym in symbols:
        assert sym["line"] == expected_lines[sym["qualified_name"]]
        assert sym["signature"], sym


def test_multiline_signature_joins_up_to_closing_paren_never_a_body_line() -> None:
    """VAL-13 negative control: the body line must not appear in `signature`."""
    index = build_call_graph_index(FIXTURE_REPO, force_rebuild=True)
    result = query_file_skeleton(index, FIXTURE_REPO, "pkg_a/calc.py")

    divide = next(
        s for s in result["symbols"] if s["qualified_name"] == "pkg_a.calc.Calculator.divide"
    )
    assert divide["signature"] == "def divide( self, a, b, ):"
    # The real negative-control assertion: the body line that follows the
    # closing paren must never leak into the signature.
    assert "return a / b" not in divide["signature"]


def test_single_line_signature_is_verbatim_header_not_body() -> None:
    index = build_call_graph_index(FIXTURE_REPO, force_rebuild=True)
    result = query_file_skeleton(index, FIXTURE_REPO, "pkg_a/calc.py")

    add = next(s for s in result["symbols"] if s["qualified_name"] == "pkg_a.calc.add")
    assert add["signature"] == "def add(a, b):"
    assert "return a + b" not in add["signature"]


def test_ambiguous_basename_lists_candidates_never_guesses() -> None:
    index = build_call_graph_index(FIXTURE_REPO, force_rebuild=True)
    result = query_file_skeleton(index, FIXTURE_REPO, "utils.py")

    assert result["found"] is False
    assert result["ambiguous"] is True
    assert result["symbols"] == []
    assert set(result["candidates"]) == {"pkg_a/utils.py", "pkg_b/sub/utils.py"}


def test_unambiguous_basename_resolves() -> None:
    index = build_call_graph_index(FIXTURE_REPO, force_rebuild=True)
    resolved, candidates = resolve_file_in_index(index, "calc.py")
    assert resolved == "pkg_a/calc.py"
    assert candidates == []


def test_unavailable_shape_on_missing_index_not_empty_list(tmp_path: Path) -> None:
    """The trap named in the task: an index with nothing to scan must not
    look identical to "this file has no symbols"."""
    index = build_call_graph_index(tmp_path, force_rebuild=True)
    assert index.symbols == []  # sanity: genuinely empty project

    result = query_file_skeleton(index, tmp_path, "anything.py")

    assert result["index_status"] == "unavailable"
    assert result["found"] is False
    assert result["symbols"] == []


def test_unavailable_shape_when_requested_file_failed_to_parse(tmp_path: Path) -> None:
    _write(tmp_path, "broken.py", "def f(:\n    pass\n")
    index = build_call_graph_index(tmp_path, force_rebuild=True)
    assert len(index.parse_failures) == 1

    result = query_file_skeleton(index, tmp_path, "broken.py")

    assert result["index_status"] == "unavailable"
    assert result["reason"] == "parse_failure"
    assert result["symbols"] == []


def test_ready_index_with_zero_symbols_in_one_file_is_a_real_empty_result(
    tmp_path: Path,
) -> None:
    """Distinguish a genuinely empty file from an unavailable index: the
    global index is non-empty (other files have symbols), so this file's
    own empty symbol list is trustworthy, not a stale-index artifact."""
    _write(tmp_path, "constants.py", "X = 1\nY = 2\n")
    _write(tmp_path, "funcs.py", "def f():\n    return 1\n")
    index = build_call_graph_index(tmp_path, force_rebuild=True)

    result = query_file_skeleton(index, tmp_path, "constants.py")

    assert result["index_status"] == "ready"
    assert result["found"] is True
    assert result["symbols"] == []


# ---------------------------------------------------------------------------
# tapps_file_api MCP handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tapps_file_api_handler_success() -> None:
    """Drives the real handler end-to-end against the fixture repo — the
    handler body lives in project/file_api.py (run_tapps_file_api), not
    server_analysis_tools.py, so project_root is passed explicitly rather
    than relying on patched settings (which the handler no longer imports
    from server_analysis_tools)."""
    from tapps_mcp.server_analysis_tools import tapps_file_api

    result = await tapps_file_api(file_path="pkg_a/calc.py", project_root=str(FIXTURE_REPO))

    assert result["success"] is True
    assert result["data"]["file_path"] == "pkg_a/calc.py"
    assert result["data"]["index_status"] == "ready"
    assert len(result["data"]["symbols"]) == 4
