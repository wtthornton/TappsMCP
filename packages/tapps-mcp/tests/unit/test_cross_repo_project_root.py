"""Cross-repo MCP tool tests: host root A, project_root B (EPIC-112)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tapps_mcp.server_analysis_tools import tapps_audit_campaign
from tapps_mcp.tools.audit_campaign import build_campaign_spec


def _write_monorepo_pkg(root: Path) -> Path:
    """Minimal packages/foo/src layout with two linked modules."""
    pkg_src = root / "packages" / "foo" / "src" / "foo_pkg"
    pkg_src.mkdir(parents=True)
    (root / "packages" / "foo" / "pyproject.toml").write_text(
        "[project]\nname='foo'\n",
        encoding="utf-8",
    )
    (pkg_src / "a.py").write_text("from foo_pkg import b\nx = 1\n", encoding="utf-8")
    (pkg_src / "b.py").write_text("y = 2\n", encoding="utf-8")
    (pkg_src / "__init__.py").write_text("", encoding="utf-8")
    return pkg_src


@pytest.fixture()
def _patch_audit_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tapps_mcp.server_analysis_tools._record_call", lambda *_a, **_k: None)
    monkeypatch.setattr("tapps_mcp.server_analysis_tools._record_execution", lambda *_a, **_k: None)
    monkeypatch.setattr("tapps_mcp.server_analysis_tools._with_nudges", lambda _t, r, *_a, **_k: r)
    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools.ensure_session_initialized",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools._resolve_git_short_sha",
        AsyncMock(return_value="abc1234"),
    )


class TestAuditCampaignCrossRepo:
    @pytest.mark.asyncio()
    @pytest.mark.usefixtures("_patch_audit_helpers")
    async def test_relative_scope_with_project_root_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        host_root = tmp_path / "host"
        target_root = tmp_path / "target"
        host_root.mkdir()
        _write_monorepo_pkg(target_root)
        rel_scope = "packages/foo/src/foo_pkg"

        monkeypatch.chdir(host_root)
        monkeypatch.setattr(
            "tapps_mcp.server_analysis_tools.load_settings",
            lambda: SimpleNamespace(project_root=host_root),
        )

        resp = await tapps_audit_campaign(
            scope=rel_scope,
            categories="quality",
            chunk_size=3,
            project_root=str(target_root),
        )

        assert resp["success"] is True, resp
        data = resp["data"]
        assert data["project_root"] == str(target_root.resolve())
        assert data["scope"] == rel_scope
        assert data["graph_root"] == "packages/foo/src"
        assert data["total_files"] >= 2

    def test_build_campaign_spec_auto_graph_root(self, tmp_path: Path) -> None:
        scope = _write_monorepo_pkg(tmp_path)
        spec = build_campaign_spec(
            tmp_path,
            scope,
            categories=["quality"],
            chunk_size=3,
        )
        assert spec.graph_root == "packages/foo/src"
        assert spec.total_files >= 2


class TestValidateChangedCrossRepo:
    def test_discover_changed_files_under_project_root_override(self, tmp_path: Path) -> None:
        target_root = tmp_path / "target"
        target_file = target_root / "packages" / "foo" / "bar.py"
        target_file.parent.mkdir(parents=True)
        target_file.write_text("x = 1\n", encoding="utf-8")

        from tapps_mcp.tools.validate_changed_collection import _discover_changed_files

        paths = _discover_changed_files(
            "packages/foo/bar.py",
            "HEAD",
            target_root.resolve(),
            cross_repo_root=target_root.resolve(),
        )
        assert len(paths) == 1
        assert paths[0] == target_file.resolve()
