"""Tests for server verification and cache warming in the bootstrap pipeline (TAP-5733)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from pydantic import SecretStr

from tapps_core.common.models import InstalledTool
from tapps_mcp.pipeline.init_state import BootstrapConfig, _BootstrapState
from tapps_mcp.pipeline.init_verification import (
    _build_verification_result,
    _extract_pip_package,
    _run_cache_warming,
    _run_expert_rag_warming,
    _run_server_verification,
    _warm_caches,
)
from tapps_mcp.project.models import ProjectProfile, TechStack

if TYPE_CHECKING:
    from pathlib import Path


class _FakeSettings:
    def __init__(self, api_key: SecretStr | None) -> None:
        self.context7_api_key = api_key
        self.cache_max_mb = 64


class _FakeCache:
    def __init__(self, cache_dir: Path, max_mb: int = 0) -> None:
        self.cache_dir = cache_dir
        self.max_mb = max_mb


@pytest.fixture
def state(tmp_path: Path) -> _BootstrapState:
    return _BootstrapState(project_root=tmp_path.resolve())


def _tool(name: str, *, available: bool) -> InstalledTool:
    return InstalledTool(
        name=name,
        available=available,
        install_hint=None if available else f"pip install {name}",
    )


class TestExtractPipPackage:
    @pytest.mark.parametrize("pkg", ["ruff", "mypy", "bandit", "pip-audit", "perflint"])
    def test_accepts_allowlisted_packages(self, pkg: str) -> None:
        assert _extract_pip_package(f"pip install {pkg}") == pkg

    def test_strips_surrounding_whitespace(self) -> None:
        assert _extract_pip_package("pip install   ruff  ") == "ruff"

    def test_rejects_non_allowlisted_package(self) -> None:
        assert _extract_pip_package("pip install totally-not-a-checker") is None

    def test_rejects_empty_hint(self) -> None:
        assert _extract_pip_package("") is None

    @pytest.mark.parametrize(
        "hint",
        [
            "brew install ruff",
            "uv tool install ruff",
            "ruff",
            "pip install ruff; rm -rf /",
            "  pip install ruff",
        ],
    )
    def test_rejects_garbage_hints(self, hint: str) -> None:
        assert _extract_pip_package(hint) is None


class TestBuildVerificationResult:
    def test_all_tools_available(self) -> None:
        result = _build_verification_result([_tool("ruff", available=True)])
        assert result == {
            "ok": True,
            "missing_checkers": [],
            "installed": ["ruff"],
            "install_hints": [],
            "checker_install_attempted": False,
        }

    def test_some_tools_missing(self) -> None:
        result = _build_verification_result(
            [_tool("ruff", available=True), _tool("vulture", available=False)]
        )
        assert result["ok"] is False
        assert result["missing_checkers"] == ["vulture"]
        assert result["installed"] == ["ruff"]
        assert result["install_hints"] == ["pip install vulture"]

    def test_empty_tool_list_is_ok(self) -> None:
        assert _build_verification_result([])["ok"] is True


class TestRunServerVerification:
    def test_reports_ok_when_nothing_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "tapps_mcp.tools.tool_detection.detect_installed_tools",
            lambda **_kwargs: [_tool("ruff", available=True)],
        )
        result = _run_server_verification(tmp_path)
        assert result["ok"] is True
        assert result["checker_install_attempted"] is False

    def test_does_not_install_when_install_missing_is_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        installed_calls: list[list[str]] = []
        monkeypatch.setattr(
            "tapps_mcp.tools.tool_detection.detect_installed_tools",
            lambda **_kwargs: [_tool("vulture", available=False)],
        )
        monkeypatch.setattr(
            "tapps_mcp.pipeline.init_verification._install_missing_checkers",
            lambda hints, root: installed_calls.append(hints),
        )
        result = _run_server_verification(tmp_path, install_missing=False)
        assert result["ok"] is False
        assert result["missing_checkers"] == ["vulture"]
        assert result["checker_install_attempted"] is False
        assert installed_calls == []

    def test_installs_missing_checkers_and_redetects(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        detections = [
            [_tool("ruff", available=True), _tool("vulture", available=False)],
            [_tool("ruff", available=True), _tool("vulture", available=True)],
        ]
        install_args: list[tuple[list[str], Path]] = []

        def _detect(**_kwargs: Any) -> list[InstalledTool]:
            return detections.pop(0)

        monkeypatch.setattr("tapps_mcp.tools.tool_detection.detect_installed_tools", _detect)
        monkeypatch.setattr(
            "tapps_mcp.pipeline.init_verification._install_missing_checkers",
            lambda hints, root: install_args.append((hints, root)),
        )

        result = _run_server_verification(tmp_path, install_missing=True)

        assert install_args == [(["pip install vulture"], tmp_path)]
        assert result["ok"] is True
        assert result["missing_checkers"] == []
        assert result["installed"] == ["ruff", "vulture"]
        assert result["checker_install_attempted"] is True

    def test_install_that_does_not_help_still_reports_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "tapps_mcp.tools.tool_detection.detect_installed_tools",
            lambda **_kwargs: [_tool("vulture", available=False)],
        )
        monkeypatch.setattr(
            "tapps_mcp.pipeline.init_verification._install_missing_checkers",
            lambda hints, root: None,
        )
        result = _run_server_verification(tmp_path, install_missing=True)
        assert result["ok"] is False
        assert result["missing_checkers"] == ["vulture"]
        assert result["checker_install_attempted"] is True


class TestRunCacheWarming:
    def test_skips_when_api_key_is_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "tapps_core.config.settings.load_settings",
            lambda *a, **k: _FakeSettings(None),
        )
        result = _run_cache_warming(tmp_path, ["fastapi"])
        assert result == {
            "warmed": 0,
            "attempted": 0,
            "skipped": "no_api_key",
            "libraries": ["fastapi"],
        }

    def test_skips_when_api_key_is_blank(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "tapps_core.config.settings.load_settings",
            lambda *a, **k: _FakeSettings(SecretStr("")),
        )
        assert _run_cache_warming(tmp_path, ["fastapi"])["skipped"] == "no_api_key"

    def test_skips_when_no_libraries(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "tapps_core.config.settings.load_settings",
            lambda *a, **k: _FakeSettings(SecretStr("sk-test")),
        )
        result = _run_cache_warming(tmp_path, [])
        assert result == {
            "warmed": 0,
            "attempted": 0,
            "skipped": "no_libraries",
            "libraries": [],
        }

    def test_warms_and_truncates_to_twenty_libraries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[list[str]] = []

        async def _warm_cache(
            project_root: Path,
            cache: _FakeCache,
            *,
            api_key: SecretStr,
            libraries: list[str],
            max_libraries: int,
        ) -> int:
            seen.append(libraries)
            return len(libraries)

        monkeypatch.setattr(
            "tapps_core.config.settings.load_settings",
            lambda *a, **k: _FakeSettings(SecretStr("sk-test")),
        )
        monkeypatch.setattr("tapps_core.knowledge.cache.KBCache", _FakeCache)
        monkeypatch.setattr("tapps_core.knowledge.warming.warm_cache", _warm_cache)

        libraries = [f"lib{i}" for i in range(25)]
        result = _run_cache_warming(tmp_path, libraries)

        assert seen == [libraries[:20]]
        assert result["warmed"] == 20
        assert result["attempted"] == 20
        assert result["skipped"] is None
        assert result["error"] is None
        assert result["libraries"] == libraries[:20]

    def test_reports_error_when_warming_hits_a_running_loop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _warm_cache(*args: Any, **kwargs: Any) -> int:
            raise RuntimeError("event loop is already running")

        monkeypatch.setattr(
            "tapps_core.config.settings.load_settings",
            lambda *a, **k: _FakeSettings(SecretStr("sk-test")),
        )
        monkeypatch.setattr("tapps_core.knowledge.cache.KBCache", _FakeCache)
        monkeypatch.setattr("tapps_core.knowledge.warming.warm_cache", _warm_cache)

        result = _run_cache_warming(tmp_path, ["fastapi"])

        assert result["warmed"] == 0
        assert result["error"] == "RuntimeError: event loop is already running"
        assert result["skipped"] is None


class TestWarmCaches:
    def test_records_disabled_when_warming_is_off(self, state: _BootstrapState) -> None:
        state.profile = ProjectProfile()
        _warm_caches(BootstrapConfig(), state)
        assert state.result["cache_warming"]["skipped"] == "disabled"
        assert state.result["expert_rag_warming"]["skipped"] == "disabled"
        assert state.errors == []

    def test_records_profile_failed_when_profile_is_missing(self, state: _BootstrapState) -> None:
        cfg = BootstrapConfig(
            warm_cache_from_tech_stack=True,
            warm_expert_rag_from_tech_stack=True,
        )
        _warm_caches(cfg, state)
        assert state.result["cache_warming"]["skipped"] == "profile_failed"
        assert state.result["expert_rag_warming"]["skipped"] == "profile_failed"

    def test_promotes_missing_api_key_to_a_warning(
        self, state: _BootstrapState, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state.profile = ProjectProfile(tech_stack=TechStack(context7_priority=["fastapi"]))
        monkeypatch.setattr(
            "tapps_mcp.pipeline.init_verification._run_cache_warming",
            lambda root, libs: {"warmed": 0, "attempted": 0, "skipped": "no_api_key"},
        )
        _warm_caches(BootstrapConfig(warm_cache_from_tech_stack=True), state)

        warning = state.result["cache_warming"]["warning"]
        assert "CONTEXT7_API_KEY not set" in warning
        assert state.warnings == [warning]
        assert state.errors == []

    def test_promotes_warming_error_to_a_bootstrap_error(
        self, state: _BootstrapState, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state.profile = ProjectProfile(tech_stack=TechStack(context7_priority=["fastapi"]))
        monkeypatch.setattr(
            "tapps_mcp.pipeline.init_verification._run_cache_warming",
            lambda root, libs: {"warmed": 0, "attempted": 1, "error": "boom"},
        )
        _warm_caches(BootstrapConfig(warm_cache_from_tech_stack=True), state)

        assert state.errors == ["Cache warming failed: boom"]

    def test_passes_context7_priority_through(
        self, state: _BootstrapState, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state.profile = ProjectProfile(tech_stack=TechStack(context7_priority=["httpx", "pytest"]))
        seen: list[tuple[Path, list[str]]] = []

        def _warming(root: Path, libs: list[str]) -> dict[str, Any]:
            seen.append((root, libs))
            return {"warmed": 2, "attempted": 2}

        monkeypatch.setattr("tapps_mcp.pipeline.init_verification._run_cache_warming", _warming)
        _warm_caches(BootstrapConfig(warm_cache_from_tech_stack=True), state)

        assert seen == [(state.project_root, ["httpx", "pytest"])]


class TestRunExpertRagWarming:
    def test_reports_removed(self) -> None:
        assert _run_expert_rag_warming()["status"] == "removed"

    def test_reports_no_failed_domains(self, state: _BootstrapState) -> None:
        state.profile = ProjectProfile()
        _warm_caches(BootstrapConfig(warm_expert_rag_from_tech_stack=True), state)
        assert state.result["expert_rag_warming"]["status"] == "removed"
        assert state.errors == []
