"""Tests for tapps_repo_map: directory-level map over the call-graph +
import-graph indexes.

VAL-14: token_budget=1 truncates with dropped > 0, default budget on this
repo returns >= 5 directories plus a completeness block, and the
stale/missing-index trap returns `index_status: unavailable` (LANE_ISSUE).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.project.call_graph import build_call_graph_index
from tapps_mcp.project.repo_map import build_repo_map

pytestmark = pytest.mark.usefixtures("envelope_guard")

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "file_api_repo"
# Real source tree for this package — deep enough to exercise "default
# budget on this repo -> >= 5 directories" per VAL-14 without a synthetic
# fixture that only proves the code works on toy input.
TAPPS_MCP_SRC = Path(__file__).parents[2] / "src" / "tapps_mcp"


def _write(root: Path, rel: str, source: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# build_repo_map (pure function)
# ---------------------------------------------------------------------------


def test_directory_clusters_and_hubs_on_fixture_repo() -> None:
    index = build_call_graph_index(FIXTURE_REPO, force_rebuild=True)
    result = build_repo_map(index, FIXTURE_REPO, token_budget=4000, max_dirs=16)

    assert result["index_status"] == "ready"
    dirs_by_name = {d["directory"]: d for d in result["directories"]}
    assert dirs_by_name.keys() == {"pkg_a", "pkg_b/sub", "ts_pkg"}
    assert dirs_by_name["pkg_a"]["symbols"] == 5
    assert dirs_by_name["pkg_b/sub"]["symbols"] == 1
    # pkg_b/sub/utils.py calls pkg_a.calc.add -> one outbound edge from pkg_b/sub.
    assert dirs_by_name["pkg_b/sub"]["edges"] == 1
    # calculate_coupling (existing module, not re-implemented) surfaces
    # pkg_a.calc as afferent-coupled (imported by pkg_b.sub.utils).
    calc_hub = next(h for h in dirs_by_name["pkg_a"]["hubs"] if h["module"] == "pkg_a.calc")
    assert calc_hub["afferent"] == 1

    assert result["hotspots"] == [{"qualified_name": "pkg_a.calc.add", "in_degree": 1}]
    assert result["completeness"]["degraded"] is False


def test_deterministic_ordering_count_desc_then_name() -> None:
    index = build_call_graph_index(FIXTURE_REPO, force_rebuild=True)
    result = build_repo_map(index, FIXTURE_REPO)

    pairs = [(d["symbols"], d["directory"]) for d in result["directories"]]
    assert pairs == sorted(pairs, key=lambda p: (-p[0], p[1]))


def test_tiny_token_budget_truncates_with_dropped_positive() -> None:
    """VAL-14: token_budget=1 -> dropped > 0."""
    index = build_call_graph_index(FIXTURE_REPO, force_rebuild=True)
    result = build_repo_map(index, FIXTURE_REPO, token_budget=1, max_dirs=16)

    assert result["directories"] == []
    assert result["dropped"]["directories"] > 0
    assert result["total_directories"] > 0


def test_max_dirs_caps_before_token_trim() -> None:
    index = build_call_graph_index(FIXTURE_REPO, force_rebuild=True)
    result = build_repo_map(index, FIXTURE_REPO, token_budget=4000, max_dirs=1)

    assert len(result["directories"]) == 1
    assert result["dropped"]["directories"] == result["total_directories"] - 1


def test_default_budget_on_this_repo_returns_five_or_more_directories() -> None:
    """VAL-14: default budget on this repo -> >= 5 directories + completeness."""
    index = build_call_graph_index(TAPPS_MCP_SRC, force_rebuild=True)
    result = build_repo_map(index, TAPPS_MCP_SRC)

    assert result["index_status"] == "ready"
    assert len(result["directories"]) >= 5
    assert "completeness" in result
    assert "in_repo_gap_rate" in result["completeness"]


def test_unavailable_shape_on_missing_index_not_empty_list(tmp_path: Path) -> None:
    index = build_call_graph_index(tmp_path, force_rebuild=True)
    assert index.symbols == []  # sanity: genuinely empty project

    result = build_repo_map(index, tmp_path)

    assert result["index_status"] == "unavailable"
    assert result["directories"] == []
    assert result["total_directories"] == 0


# ---------------------------------------------------------------------------
# tapps_repo_map MCP handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tapps_repo_map_handler_success() -> None:
    """Drives the real handler end-to-end against the fixture repo — the
    handler body lives in project/repo_map.py (run_tapps_repo_map), not
    server_comprehension_tools.py, so project_root is passed explicitly rather
    than relying on patched settings (which the handler no longer imports
    from server_comprehension_tools)."""
    from tapps_mcp.server_comprehension_tools import tapps_repo_map

    result = await tapps_repo_map(project_root=str(FIXTURE_REPO))

    assert result["success"] is True
    assert result["data"]["project_root"] == str(FIXTURE_REPO)
    assert result["data"]["index_status"] == "ready"
    assert result["data"]["directories"]
