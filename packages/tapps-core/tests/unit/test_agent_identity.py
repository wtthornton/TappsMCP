"""Tests for ``tapps_core.agent_identity`` (TAP-518)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from tapps_core.agent_identity import get_stable_agent_id
from tapps_core.config.settings import TappsMCPSettings

if TYPE_CHECKING:
    import pytest

_AGENT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+-[0-9a-f]{8}$")


def _make_settings(project_root: Path, *, project_id: str = "") -> TappsMCPSettings:
    """Build a minimal settings object anchored at *project_root*."""
    settings = TappsMCPSettings(project_root=project_root)
    # ``project_id`` lives on MemorySettings; override post-construction so we
    # don't depend on env vars leaking into the test runner.
    settings.memory.project_id = project_id
    return settings


def test_agent_id_created_on_first_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """First call writes ``.tapps-mcp/agent.id`` with a UUID4 hex."""
    monkeypatch.delenv("CLAUDE_AGENT_ID", raising=False)
    project = tmp_path / "proj"
    project.mkdir()
    settings = _make_settings(project, project_id="tapps-mcp")

    id_path = project / ".tapps-mcp" / "agent.id"
    assert not id_path.exists()

    agent_id = get_stable_agent_id(settings)

    assert id_path.exists(), "agent.id should be created on first call"
    persisted = id_path.read_text(encoding="utf-8").strip()
    assert len(persisted) == 32, "persisted UUID should be 32 hex chars"
    assert agent_id.endswith(persisted[:8])


def test_agent_id_stable_across_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-reading the persisted file yields the same agent_id across instances."""
    monkeypatch.delenv("CLAUDE_AGENT_ID", raising=False)
    project = tmp_path / "proj"
    project.mkdir()

    first = get_stable_agent_id(_make_settings(project, project_id="tapps-mcp"))
    # Fresh settings instance — simulates MCP server restart.
    second = get_stable_agent_id(_make_settings(project, project_id="tapps-mcp"))

    assert first == second
    # Third call on the same instance is also stable.
    settings = _make_settings(project, project_id="tapps-mcp")
    assert get_stable_agent_id(settings) == get_stable_agent_id(settings)


def test_agent_id_format(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Returned id has shape ``<slug>-<8 hex chars>``."""
    monkeypatch.delenv("CLAUDE_AGENT_ID", raising=False)
    project = tmp_path / "proj"
    project.mkdir()
    settings = _make_settings(project, project_id="tapps-mcp")

    agent_id = get_stable_agent_id(settings)

    assert _AGENT_ID_RE.match(agent_id), f"unexpected format: {agent_id!r}"
    assert agent_id.startswith("tapps-mcp-")


def test_agent_id_falls_back_to_project_root_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When ``memory.project_id`` is empty, the project root dir name is used."""
    monkeypatch.delenv("CLAUDE_AGENT_ID", raising=False)
    project = tmp_path / "my-app"
    project.mkdir()
    settings = _make_settings(project, project_id="")

    agent_id = get_stable_agent_id(settings)

    assert agent_id.startswith("my-app-")
    assert _AGENT_ID_RE.match(agent_id)


def test_agent_id_respects_claude_agent_id_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``CLAUDE_AGENT_ID`` env var still takes precedence (unchanged contract)."""
    monkeypatch.setenv("CLAUDE_AGENT_ID", "explicit-override")
    project = tmp_path / "proj"
    project.mkdir()
    settings = _make_settings(project, project_id="tapps-mcp")

    agent_id = get_stable_agent_id(settings)

    assert agent_id == "explicit-override"
    # No file should be created when the env var short-circuits.
    assert not (project / ".tapps-mcp" / "agent.id").exists()


def test_agent_id_slugifies_unsafe_project_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Characters outside ``[A-Za-z0-9_-]`` are collapsed into dashes."""
    monkeypatch.delenv("CLAUDE_AGENT_ID", raising=False)
    project = tmp_path / "proj"
    project.mkdir()
    settings = _make_settings(project, project_id="my project/v2")

    agent_id = get_stable_agent_id(settings)

    assert agent_id.startswith("my-project-v2-")
    assert _AGENT_ID_RE.match(agent_id)
