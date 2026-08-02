"""Regressions for path-dependent scoring (TAP-5401 / TAP-5402 / TAP-5403).

Three defects reported together, all rooted in the same assumption — that a
file's quality score is a function of its bytes alone:

* TAP-5401 — ``tapps_quick_check``'s result cache was keyed on content only,
  so byte-identical files at different depths shared one entry.
* TAP-5402 — ``tapps_validate_changed`` quick mode scored ``linting`` only and
  published it on the 0-100 scale, so the documented pre-completion gate
  disagreed with ``tapps_quick_check`` on the same file.
* TAP-5403 — the scoring tools had no ``project_root`` override, so scoring a
  pristine copy outside the repo returned ``path_denied``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.scoring.scorer import CodeScorer
from tapps_mcp.tools import content_hash_cache as cache

# Byte-identical source used at both depths. Clean-linting on purpose: the
# whole point is that lint alone cannot distinguish the two locations.
SOURCE = '''"""Module docstring."""

from __future__ import annotations


def add(a: int, b: int) -> int:
    """Return the sum of two integers."""
    return a + b
'''


@pytest.fixture
def two_depths(tmp_path: Path) -> tuple[Path, Path]:
    """A project root with AGENTS.md, plus a nested service dir without one."""
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'demo'\n\n[tool.ruff]\nline-length = 100\n"
    )
    (tmp_path / "AGENTS.md").write_text("# Agents\n")
    (tmp_path / "docs").mkdir()
    root_file = tmp_path / "mod.py"
    root_file.write_text(SOURCE)

    service_src = tmp_path / "domains" / "billing" / "service" / "src"
    service_src.mkdir(parents=True)
    (service_src.parent / "pyproject.toml").write_text("[project]\nname = 'svc'\n")
    deep_file = service_src / "mod.py"
    deep_file.write_text(SOURCE)
    return root_file, deep_file


def test_devex_differs_by_directory_context(two_depths: tuple[Path, Path]) -> None:
    """Premise check: identical bytes genuinely score differently by location."""
    root_file, deep_file = two_depths
    scorer = CodeScorer()
    root_score = scorer.score_file_quick_enriched(root_file)
    deep_score = scorer.score_file_quick_enriched(deep_file)

    assert root_file.read_bytes() == deep_file.read_bytes()
    assert root_score.categories["devex"].score != deep_score.categories["devex"].score
    assert root_score.overall_score != deep_score.overall_score


def test_cache_does_not_leak_scores_across_depths(two_depths: tuple[Path, Path]) -> None:
    """TAP-5401: the deeper file must not be served the shallow file's entry."""
    root_file, deep_file = two_depths
    cache.clear()

    scorer = CodeScorer()
    root_score = scorer.score_file_quick_enriched(root_file)
    cache.set(
        cache.KIND_QUICK_CHECK,
        cache.result_key(root_file, preset="standard"),
        {"file_path": str(root_file), "overall_score": root_score.overall_score},
    )

    assert cache.get(cache.KIND_QUICK_CHECK, cache.result_key(deep_file, preset="standard")) is None


@pytest.mark.asyncio
async def test_quick_check_and_validate_changed_agree(tmp_path: Path) -> None:
    """TAP-5402: the two tools must return the same score and verdict.

    A file with clean lint but high complexity used to score 100/pass under
    ``validate_changed`` quick mode (lint-only) and well below that under
    ``quick_check`` (all seven categories).
    """
    import asyncio

    from tapps_mcp.server_scoring_tools import _quick_check_single
    from tapps_mcp.tools.validate_changed_orchestrator import _validate_single_file

    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    target = tmp_path / "gnarly.py"
    # Deeply nested branching: ruff-clean, but poor on complexity /
    # maintainability / test_coverage / structure / devex.
    body = ["def f(a, b, c, d, e):"]
    body += [f"{'    ' * (i + 1)}if a == {i}:" for i in range(8)]
    body.append(f"{'    ' * 9}return b + c + d + e")
    body.append("    return 0")
    target.write_text("\n".join(body) + "\n")

    cache.clear()

    from tapps_core.config.settings import load_settings

    settings = load_settings(project_root=tmp_path)
    qc = await _quick_check_single(target, "standard", False, settings)
    vc = await _validate_single_file(
        target, "standard", True, False, asyncio.Semaphore(1), None, None
    )

    assert vc["overall_score"] == pytest.approx(qc["overall_score"], abs=0.01)
    assert vc["gate_passed"] is qc["gate_passed"]
    assert vc["categories_scored"] == qc["categories_scored"]


@pytest.mark.asyncio
async def test_quick_check_accepts_project_root_override(tmp_path: Path) -> None:
    """TAP-5403: a scratch dir outside the repo is scorable, not path_denied."""
    from tapps_mcp.server_scoring_tools import tapps_quick_check

    scratch = tmp_path / "baseline"
    scratch.mkdir()
    (scratch / "pyproject.toml").write_text("[project]\nname = 'baseline'\n")
    target = scratch / "mod.py"
    target.write_text(SOURCE)

    denied = await tapps_quick_check(str(target))
    assert denied["success"] is False
    assert denied["error"]["code"] == "path_denied"

    allowed = await tapps_quick_check(str(target), project_root=str(scratch))
    assert allowed["success"] is True
    assert allowed["data"]["file_path"] == str(target)


@pytest.mark.asyncio
async def test_project_root_override_rejects_missing_dir(tmp_path: Path) -> None:
    """An override pointing at a non-directory is a user error, not a pass."""
    from tapps_mcp.server_scoring_tools import tapps_quick_check

    target = tmp_path / "mod.py"
    target.write_text(SOURCE)
    resp = await tapps_quick_check(str(target), project_root=str(tmp_path / "nope"))
    assert resp["success"] is False
    assert resp["error"]["code"] == "path_denied"
