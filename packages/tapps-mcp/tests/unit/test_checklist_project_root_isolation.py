"""The checklist must grade the project it was handed, not the ambient one.

TAP-7234. ``tapps_checklist`` resolves three things per call: the required-tool
matrix (from the engagement level), the auto-run's validation target, and the
call log. The first two used to come from the process-wide settings singleton
-- ``TAPPS_MCP_PROJECT_ROOT`` or the CWD -- while the evaluation itself ran
against an explicitly passed ``project_root``. A checklist bound to project A
therefore graded A's calls against B's required-tool matrix and credited them
with a gate run over B's changed files.

That made the verdict a function of ambient process state rather than of the
session being graded, which is wrong for an HTTP fleet request bound to a
caller root and is what made ``test_empty_session`` order-dependent under
xdist: at engagement ``low`` a ``review`` needs only ``tapps_quality_gate``,
the auto-run credits exactly that via ``_TOOL_EQUIVALENTS``, and a non-zero
file count borrowed from the ambient tree suppressed the revocation that
would otherwise have taken the credit back.

The first two tests assert on the *call* rather than on the verdict: a verdict
assertion passes by coincidence whenever the ambient root happens to agree with
the evaluated one, which on a developer checkout is most of the time.
"""

from __future__ import annotations

import functools
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from tapps_core.config.settings import _reset_settings_cache, load_settings
from tapps_mcp.server import tapps_checklist
from tapps_mcp.tools.checklist import CallTracker

pytestmark = [pytest.mark.usefixtures("no_repo_wide_scans")]

_STUB_GAPS = {"gaps": [], "recommendations": [], "libraries_without_lookup": []}


def _init_git_repo_with_a_changed_python_file(root: Path) -> None:
    """A minimal git project whose working tree has one changed scorable file."""
    (root / "pyproject.toml").write_text('[project]\nname = "ambient"\n', encoding="utf-8")
    (root / "mod.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    run = functools.partial(subprocess.run, cwd=root, check=True, capture_output=True)
    run(["git", "init", "-q"])
    run(["git", "add", "-A"])
    run(["git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-qm", "init"])
    (root / "mod.py").write_text("def a():\n    return 2\n", encoding="utf-8")
    changed = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, check=True, capture_output=True, text=True
    ).stdout
    # Fail loudly rather than silently probing a tree with nothing in it.
    assert "mod.py" in changed, f"ambient tree has no changed file: {changed!r}"


def test_engagement_level_resolved_from_evaluated_project_root(tmp_path: Path) -> None:
    """``_resolve_task_tool_map`` must read settings for the root it grades."""
    seen: list[Any] = []
    real = load_settings

    def spy(project_root: Any = None) -> Any:
        seen.append(project_root)
        return real(project_root)

    CallTracker.reset()
    with patch("tapps_core.config.settings.load_settings", spy):
        CallTracker.evaluate("review", project_root=tmp_path)

    assert seen, "engagement level was not resolved through load_settings at all"
    assert seen == [tmp_path], (
        "engagement level read from the ambient settings singleton "
        f"instead of the evaluated project_root; load_settings got {seen!r}"
    )


@pytest.mark.asyncio
async def test_auto_run_validation_scoped_to_checklist_project_root(tmp_path: Path) -> None:
    """The auto-run must gate the checklist's own project, not the ambient one."""
    isolated = load_settings(project_root=tmp_path)
    vc = AsyncMock(return_value={"success": True, "data": {"files_validated": 0}})

    CallTracker.reset()
    with (
        patch("tapps_mcp.server_checklist_tools.load_settings", return_value=isolated),
        patch("tapps_mcp.server_pipeline_tools.tapps_validate_changed", vc),
        patch("tapps_mcp.tools.usage.compute_gaps", return_value=_STUB_GAPS),
    ):
        await tapps_checklist()

    assert vc.await_count == 1, "auto-run did not invoke tapps_validate_changed"
    assert vc.await_args.kwargs.get("project_root") == str(tmp_path), (
        "auto-run validated the ambient project root instead of the checklist's; "
        f"kwargs were {vc.await_args.kwargs!r}"
    )


@pytest.mark.asyncio
async def test_auto_run_does_not_borrow_a_foreign_tree_s_changed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An evidence-free session must not be completed by another repo's diff.

    This is the ``test_empty_session`` failure reduced to its mechanism. The
    ambient root is a real git repo with a changed Python file; the graded
    project is empty. Before the fix the auto-run gated the *ambient* tree,
    reported a non-zero file count, and that count suppressed the
    uncredited-auto-run revocation -- so a session that validated nothing in
    the graded project read as complete.

    Engagement ``low`` is the amplifier, not the defect: it shrinks ``review``
    to a single required tool that the auto-run credits, which is what turns a
    borrowed file count into a ``complete`` verdict rather than a merely
    inaccurate one.
    """
    ambient = tmp_path / "ambient"
    ambient.mkdir()
    _init_git_repo_with_a_changed_python_file(ambient)

    monkeypatch.setenv("TAPPS_MCP_PROJECT_ROOT", str(ambient))
    monkeypatch.setenv("TAPPS_MCP_LLM_ENGAGEMENT_LEVEL", "low")
    # A run where the hostile ambient state did not take would pass for a
    # reason unrelated to the defect, so assert the precondition.
    _reset_settings_cache()
    assert load_settings().llm_engagement_level == "low"
    assert load_settings().project_root == ambient

    graded = tmp_path / "graded"
    graded.mkdir()
    isolated = load_settings(project_root=graded)

    CallTracker.reset()
    with (
        patch("tapps_mcp.server_checklist_tools.load_settings", return_value=isolated),
        patch("tapps_mcp.tools.usage.compute_gaps", return_value=_STUB_GAPS),
    ):
        result = await tapps_checklist()

    assert result["success"] is True
    assert result["data"]["complete"] is False
