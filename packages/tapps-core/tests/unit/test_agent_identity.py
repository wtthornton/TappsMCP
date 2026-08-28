"""Tests for ``tapps_core.agent_identity`` (Ruling 9, TAP-6701; supersedes TAP-518).

``get_stable_agent_id`` is now pure and deterministic: no ``.tapps-mcp/agent.id``
file, no uuid suffix, no filesystem I/O outside the ``CLAUDE_AGENT_ID`` env
read. These tests pin that contract and the cross-checkout invariant it
exists for (Ruling 9: two worktrees of the same project resolve to the same
``X-Agent-Id``).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from tapps_core.agent_identity import (
    get_stable_agent_id,
    is_real_writable_root,
)
from tapps_core.config.settings import TappsMCPSettings

if TYPE_CHECKING:
    import pytest


def _make_settings(
    project_root: Path, *, project_id: str = "", brain_project_id: str = ""
) -> TappsMCPSettings:
    """Build a minimal settings object anchored at *project_root*."""
    settings = TappsMCPSettings(project_root=project_root)
    # These live on MemorySettings; override post-construction so we don't
    # depend on env vars leaking into the test runner. Setting only one of
    # the two (never both) avoids the auto-derive validator filling the
    # other in and masking which field this test is actually exercising.
    settings.memory.project_id = project_id
    settings.memory.brain_project_id = brain_project_id
    return settings


def test_agent_id_no_file_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolution never touches disk — no ``.tapps-mcp/agent.id`` file."""
    monkeypatch.delenv("CLAUDE_AGENT_ID", raising=False)
    project = tmp_path / "proj"
    project.mkdir()
    settings = _make_settings(project, brain_project_id="tapps-mcp")

    agent_id = get_stable_agent_id(settings)

    assert agent_id == "tapps-mcp"
    assert not (project / ".tapps-mcp" / "agent.id").exists()
    assert list(project.iterdir()) == []


def test_agent_id_stable_across_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated calls (simulating MCP server restarts) return the same id."""
    monkeypatch.delenv("CLAUDE_AGENT_ID", raising=False)
    project = tmp_path / "proj"
    project.mkdir()

    first = get_stable_agent_id(_make_settings(project, brain_project_id="tapps-mcp"))
    second = get_stable_agent_id(_make_settings(project, brain_project_id="tapps-mcp"))

    assert first == second == "tapps-mcp"


def test_agent_id_prefers_brain_project_id_over_project_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``brain_project_id`` — the field actually sent as X-Project-Id — wins."""
    monkeypatch.delenv("CLAUDE_AGENT_ID", raising=False)
    project = tmp_path / "proj"
    project.mkdir()
    settings = _make_settings(project, project_id="legacy-slug", brain_project_id="tapps-mcp")

    assert get_stable_agent_id(settings) == "tapps-mcp"


def test_agent_id_falls_back_to_project_id_when_brain_project_id_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CLAUDE_AGENT_ID", raising=False)
    project = tmp_path / "proj"
    project.mkdir()
    settings = _make_settings(project, project_id="tapps-mcp")

    assert get_stable_agent_id(settings) == "tapps-mcp"


def test_agent_id_falls_back_to_project_root_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When neither project id field is set, the project root dir name is used."""
    monkeypatch.delenv("CLAUDE_AGENT_ID", raising=False)
    project = tmp_path / "my-app"
    project.mkdir()
    settings = _make_settings(project)

    assert get_stable_agent_id(settings) == "my-app"


def test_agent_id_respects_claude_agent_id_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``CLAUDE_AGENT_ID`` env var still takes precedence (unchanged contract)."""
    monkeypatch.setenv("CLAUDE_AGENT_ID", "explicit-override")
    project = tmp_path / "proj"
    project.mkdir()
    settings = _make_settings(project, brain_project_id="tapps-mcp")

    assert get_stable_agent_id(settings) == "explicit-override"
    assert not (project / ".tapps-mcp" / "agent.id").exists()


def test_agent_id_slugifies_unsafe_project_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Characters outside ``[A-Za-z0-9_-]`` are collapsed into dashes."""
    monkeypatch.delenv("CLAUDE_AGENT_ID", raising=False)
    project = tmp_path / "proj"
    project.mkdir()
    settings = _make_settings(project, brain_project_id="my project/v2")

    assert get_stable_agent_id(settings) == "my-project-v2"


def test_cross_checkout_same_brain_project_id_resolves_to_same_agent_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ruling 9: two worktrees of the same project must agree on X-Agent-Id.

    This is the actual TAP-6701 regression target — the old uuid8-suffix
    design (persisted per ``project_root``) gave every worktree a distinct
    id. A shared ``brain_project_id`` across different ``project_root``s is
    exactly the multi-worktree scenario in production.
    """
    monkeypatch.delenv("CLAUDE_AGENT_ID", raising=False)
    worktree_a = tmp_path / "tapps-mcp"
    worktree_b = tmp_path / "mh-lane-M1"
    worktree_a.mkdir()
    worktree_b.mkdir()

    id_a = get_stable_agent_id(_make_settings(worktree_a, brain_project_id="tapps-mcp"))
    id_b = get_stable_agent_id(_make_settings(worktree_b, brain_project_id="tapps-mcp"))

    assert id_a == id_b == "tapps-mcp"


# --------------------------------------------------------------------------- #
# TAP-4573: mock/relative-root write guard (unrelated to identity resolution,
# but the guard function lives in this module and is exercised elsewhere).
# --------------------------------------------------------------------------- #


def test_is_real_writable_root_rejects_mock_and_relative() -> None:
    """The guard accepts only absolute filesystem paths."""
    assert is_real_writable_root(Path("/abs/real/path")) is True
    assert is_real_writable_root("/abs/real/path") is True
    # A bare MagicMock coerces (via os.fspath) to a *relative* "MagicMock/..."
    # path — the exact leak vector from TAP-4573.
    assert is_real_writable_root(MagicMock().project_root) is False
    assert is_real_writable_root(Path("relative/dir")) is False
    assert is_real_writable_root(object()) is False


def test_mock_settings_creates_no_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A bare MagicMock() settings must not mkdir/write under the CWD.

    Regression guard: even though identity resolution itself is now pure,
    a MagicMock's ``memory.brain_project_id``/``project_id`` also coerce to
    mock reprs rather than empty strings, so this pins that the root-name
    fallback path still never touches disk.
    """
    monkeypatch.delenv("CLAUDE_AGENT_ID", raising=False)
    monkeypatch.chdir(tmp_path)

    settings = MagicMock()
    settings.memory.project_id = ""
    settings.memory.brain_project_id = ""

    agent_id = get_stable_agent_id(settings)

    assert isinstance(agent_id, str) and agent_id
    assert not (tmp_path / "MagicMock").exists()
    assert list(tmp_path.iterdir()) == []
