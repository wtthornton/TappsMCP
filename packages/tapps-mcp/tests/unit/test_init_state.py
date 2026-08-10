"""Tests for the bootstrap pipeline's shared config and state (TAP-5733)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tapps_core.common.file_operations import WriteMode
from tapps_mcp.pipeline.init_state import BootstrapConfig, _BootstrapState

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def state(tmp_path: Path) -> _BootstrapState:
    return _BootstrapState(project_root=tmp_path.resolve())


class TestBootstrapConfig:
    def test_defaults(self) -> None:
        cfg = BootstrapConfig()
        assert cfg.llm_engagement_level == "medium"
        assert cfg.skill_tier == "full"
        assert cfg.mcp_bundle == "full"
        assert cfg.dry_run is False

    def test_from_params_passes_through_explicit_values(self) -> None:
        cfg = BootstrapConfig.from_params(
            llm_engagement_level="high",
            skill_tier="core",
            dry_run=True,
        )
        assert cfg.llm_engagement_level == "high"
        assert cfg.skill_tier == "core"
        assert cfg.dry_run is True

    def test_from_params_rejects_unknown_skill_tier(self) -> None:
        cfg = BootstrapConfig.from_params(llm_engagement_level="low", skill_tier="bogus")
        assert cfg.skill_tier == "full"

    def test_from_params_reads_settings_when_omitted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Settings:
            llm_engagement_level = "high"
            skill_tier = "core"

        monkeypatch.setattr(
            "tapps_core.config.settings.load_settings",
            lambda *a, **k: _Settings(),
        )
        cfg = BootstrapConfig.from_params()
        assert cfg.llm_engagement_level == "high"
        assert cfg.skill_tier == "core"


class TestSafeWrite:
    def test_writes_new_file(self, state: _BootstrapState, tmp_path: Path) -> None:
        state.safe_write("docs/NOTES.md", "hello")
        assert (tmp_path / "docs/NOTES.md").read_text(encoding="utf-8") == "hello"
        assert state.created == ["docs/NOTES.md"]

    def test_skips_existing_file(self, state: _BootstrapState, tmp_path: Path) -> None:
        target = tmp_path / "KEEP.md"
        target.write_text("original", encoding="utf-8")
        state.safe_write("KEEP.md", "replacement")
        assert target.read_text(encoding="utf-8") == "original"
        assert state.skipped == ["KEEP.md"]
        assert state.created == []

    def test_rejects_path_escaping_project_root(self, state: _BootstrapState) -> None:
        state.safe_write("../escaped.md", "nope")
        assert state.created == []
        assert any("escapes project root" in err for err in state.errors)

    def test_dry_run_records_without_writing(self, tmp_path: Path) -> None:
        state = _BootstrapState(project_root=tmp_path.resolve(), dry_run=True)
        state.safe_write("docs/NOTES.md", "hello")
        assert not (tmp_path / "docs/NOTES.md").exists()
        assert state.created == ["docs/NOTES.md"]


class TestSafeWriteOrOverwrite:
    def test_returns_created_for_new_file(self, state: _BootstrapState, tmp_path: Path) -> None:
        assert state.safe_write_or_overwrite("A.md", "one") == "created"
        assert (tmp_path / "A.md").read_text(encoding="utf-8") == "one"
        assert state.created == ["A.md"]

    def test_returns_updated_and_overwrites(self, state: _BootstrapState, tmp_path: Path) -> None:
        (tmp_path / "A.md").write_text("old", encoding="utf-8")
        assert state.safe_write_or_overwrite("A.md", "new") == "updated"
        assert (tmp_path / "A.md").read_text(encoding="utf-8") == "new"
        assert state.created == []

    def test_rejects_path_escaping_project_root(self, state: _BootstrapState) -> None:
        assert state.safe_write_or_overwrite("../escaped.md", "nope") == "skipped"
        assert any("escapes project root" in err for err in state.errors)


class TestContentReturnMode:
    @pytest.fixture
    def state(self, tmp_path: Path) -> _BootstrapState:
        return _BootstrapState(
            project_root=tmp_path.resolve(),
            write_mode=WriteMode.CONTENT_RETURN,
        )

    def test_content_return_flag(self, state: _BootstrapState) -> None:
        assert state.content_return is True

    def test_safe_write_queues_operation_without_touching_disk(
        self, state: _BootstrapState, tmp_path: Path
    ) -> None:
        state.safe_write("docs/NOTES.md", "hello")
        assert not (tmp_path / "docs/NOTES.md").exists()
        assert len(state.file_ops) == 1
        assert state.file_ops[0].path == "docs/NOTES.md"
        assert state.file_ops[0].mode == "create"
        assert state.created == ["docs/NOTES.md"]

    def test_safe_write_or_overwrite_marks_existing_as_overwrite(
        self, state: _BootstrapState, tmp_path: Path
    ) -> None:
        (tmp_path / "A.md").write_text("old", encoding="utf-8")
        assert state.safe_write_or_overwrite("A.md", "new") == "updated"
        assert (tmp_path / "A.md").read_text(encoding="utf-8") == "old"
        assert state.file_ops[0].mode == "overwrite"
        assert state.created == []

    def test_build_manifest_packages_file_ops(self, state: _BootstrapState) -> None:
        state.safe_write("A.md", "one")
        state.safe_write("B.md", "two")
        manifest = state.build_manifest()
        assert len(manifest.files) == 2
        assert "2 file(s) to write" in manifest.summary
        assert manifest.agent_instructions is not None


class TestFinalize:
    def test_success_when_no_errors(self, state: _BootstrapState) -> None:
        state.safe_write("A.md", "one")
        result = state.finalize()
        assert result["success"] is True
        assert result["created"] == ["A.md"]
        assert result["errors"] == []

    def test_failure_when_errors_present(self, state: _BootstrapState) -> None:
        state.errors.append("boom")
        result = state.finalize()
        assert result["success"] is False
        assert result["errors"] == ["boom"]

    def test_preserves_preexisting_result_keys(self, state: _BootstrapState) -> None:
        state.result["docsmcp_detected"] = True
        result = state.finalize()
        assert result["docsmcp_detected"] is True
        assert result["success"] is True
