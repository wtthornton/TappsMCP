"""Tests for the bootstrap pipeline's GitHub scaffolding steps (TAP-5733)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tapps_mcp.pipeline.init_github import (
    _setup_github_ci,
    _setup_github_copilot,
    _setup_github_governance,
    _setup_github_templates,
)
from tapps_mcp.pipeline.init_state import _BootstrapState

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


_STEPS = [
    pytest.param(
        _setup_github_templates,
        "tapps_mcp.pipeline.github_templates.generate_all_github_templates",
        "github_templates",
        "GitHub templates",
        id="templates",
    ),
    pytest.param(
        _setup_github_ci,
        "tapps_mcp.pipeline.github_ci.generate_all_ci_workflows",
        "ci_workflows",
        "CI workflows",
        id="ci",
    ),
    pytest.param(
        _setup_github_copilot,
        "tapps_mcp.pipeline.github_copilot.generate_all_copilot_config",
        "github_copilot",
        "Copilot config",
        id="copilot",
    ),
    pytest.param(
        _setup_github_governance,
        "tapps_mcp.pipeline.github_governance.generate_all_governance",
        "governance",
        "Governance",
        id="governance",
    ),
]


@pytest.fixture
def state(tmp_path: Path) -> _BootstrapState:
    return _BootstrapState(project_root=tmp_path.resolve())


class TestGithubSetupSteps:
    @pytest.mark.parametrize(("setup", "target", "key", "label"), _STEPS)
    def test_records_generator_result(
        self,
        state: _BootstrapState,
        monkeypatch: pytest.MonkeyPatch,
        setup: Callable[[_BootstrapState], None],
        target: str,
        key: str,
        label: str,
    ) -> None:
        del label
        calls: list[Path] = []

        def _generator(project_root: Path) -> dict[str, Any]:
            calls.append(project_root)
            return {"created": [f"{key}.yml"]}

        monkeypatch.setattr(target, _generator)
        setup(state)

        assert calls == [state.project_root]
        assert state.result[key] == {"created": [f"{key}.yml"]}
        assert state.errors == []

    @pytest.mark.parametrize(("setup", "target", "key", "label"), _STEPS)
    def test_records_error_when_generator_raises(
        self,
        state: _BootstrapState,
        monkeypatch: pytest.MonkeyPatch,
        setup: Callable[[_BootstrapState], None],
        target: str,
        key: str,
        label: str,
    ) -> None:
        def _generator(project_root: Path) -> dict[str, Any]:
            raise RuntimeError("generator exploded")

        monkeypatch.setattr(target, _generator)
        setup(state)

        assert state.result[key] == {"error": "generator exploded"}
        assert state.errors == [f"{label}: generator exploded"]

    @pytest.mark.parametrize(("setup", "target", "key", "label"), _STEPS)
    def test_failure_does_not_abort_finalize(
        self,
        state: _BootstrapState,
        monkeypatch: pytest.MonkeyPatch,
        setup: Callable[[_BootstrapState], None],
        target: str,
        key: str,
        label: str,
    ) -> None:
        del key, label

        def _generator(project_root: Path) -> dict[str, Any]:
            raise ValueError("nope")

        monkeypatch.setattr(target, _generator)
        setup(state)

        assert state.finalize()["success"] is False


class TestPlatformWiring:
    """These run from ``init_platform``, which is the only caller."""

    def test_init_platform_binds_the_setup_functions(self) -> None:
        from tapps_mcp.pipeline import init_platform

        assert init_platform._setup_github_templates is _setup_github_templates
        assert init_platform._setup_github_ci is _setup_github_ci
        assert init_platform._setup_github_copilot is _setup_github_copilot
        assert init_platform._setup_github_governance is _setup_github_governance
