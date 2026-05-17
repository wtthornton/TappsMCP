"""Tests for the audit-campaign orchestrator."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tapps_mcp.tools.audit_campaign import (
    _EPIC_REF_PLACEHOLDER,
    _build_campaign_id,
    _slug,
    build_campaign_spec,
)


def _write_two_cluster_project(root: Path) -> None:
    pkg = root / "mypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "a.py").write_text(
        textwrap.dedent("""
            from mypkg import b

            def use_b() -> int:
                return b.value()
        """).lstrip()
    )
    (pkg / "b.py").write_text(
        textwrap.dedent("""
            def value() -> int:
                return 1
        """).lstrip()
    )
    (pkg / "c.py").write_text(
        textwrap.dedent("""
            from mypkg import d

            def go() -> int:
                return d.compute()
        """).lstrip()
    )
    (pkg / "d.py").write_text(
        textwrap.dedent("""
            def compute() -> int:
                return 2
        """).lstrip()
    )


class TestSlug:
    def test_simple(self) -> None:
        assert _slug("tools") == "tools"

    def test_strips_special_chars(self) -> None:
        assert _slug("my/pkg.sub") == "my-pkg-sub"

    def test_lowercase(self) -> None:
        assert _slug("TappsMCP") == "tappsmcp"

    def test_max_30(self) -> None:
        out = _slug("x" * 100)
        assert len(out) == 30


class TestCampaignId:
    def test_includes_date_and_sha(self) -> None:
        cid = _build_campaign_id(Path("/repo/tools"), "abc1234567")
        assert cid.startswith("audit-")
        assert "tools" in cid
        assert cid.endswith("abc1234")

    def test_no_sha(self) -> None:
        cid = _build_campaign_id(Path("/repo/tools"), "")
        assert cid.endswith("nosha")


class TestBuildCampaignSpec:
    def test_basic(self, tmp_path: Path) -> None:
        _write_two_cluster_project(tmp_path)
        spec = build_campaign_spec(
            tmp_path,
            tmp_path / "mypkg",
            commit_sha="deadbee",
            categories=["quality"],
            min_size=2,
            chunk_size=3,
            max_size=4,
        )

        assert spec.total_files == 4
        assert spec.total_chunks >= 1
        assert spec.categories == ["quality"]
        assert spec.commit_sha == "deadbee"
        assert spec.campaign_id.endswith("deadbee")

    def test_sessions_have_titles_and_bodies(self, tmp_path: Path) -> None:
        _write_two_cluster_project(tmp_path)
        spec = build_campaign_spec(
            tmp_path,
            tmp_path / "mypkg",
            commit_sha="abc1234",
            min_size=2,
            chunk_size=3,
            max_size=4,
        )

        for session in spec.sessions:
            assert session.title.startswith("audit: ")
            assert len(session.title) <= 80
            assert session.body.startswith("## What")
            assert _EPIC_REF_PLACEHOLDER in session.body
            assert "abc1234" in session.body

    def test_epic_title_and_body(self, tmp_path: Path) -> None:
        _write_two_cluster_project(tmp_path)
        spec = build_campaign_spec(
            tmp_path,
            tmp_path / "mypkg",
            commit_sha="abc1234",
            min_size=2,
            chunk_size=3,
            max_size=4,
        )
        assert spec.epic.title.startswith("audit campaign:")
        assert len(spec.epic.title) <= 80
        assert spec.epic.body.startswith("## Purpose & Intent")
        # Every session shows up in acceptance criteria.
        for s in spec.sessions:
            assert s.title in spec.epic.body
        # Campaign id + commit appear in technical notes.
        assert spec.campaign_id in spec.epic.body
        assert "abc1234" in spec.epic.body

    def test_default_categories(self, tmp_path: Path) -> None:
        _write_two_cluster_project(tmp_path)
        spec = build_campaign_spec(
            tmp_path,
            tmp_path / "mypkg",
            commit_sha="abc1234",
            min_size=2,
            chunk_size=3,
            max_size=4,
        )
        assert set(spec.categories) == {"quality", "security", "dead_code"}

    def test_unknown_category_raises(self, tmp_path: Path) -> None:
        _write_two_cluster_project(tmp_path)
        with pytest.raises(ValueError, match="Unknown categories"):
            build_campaign_spec(
                tmp_path,
                tmp_path / "mypkg",
                commit_sha="abc1234",
                categories=["quality", "bogus"],
                min_size=2,
                chunk_size=3,
                max_size=4,
            )

    def test_explicit_campaign_id(self, tmp_path: Path) -> None:
        _write_two_cluster_project(tmp_path)
        spec = build_campaign_spec(
            tmp_path,
            tmp_path / "mypkg",
            commit_sha="abc1234",
            min_size=2,
            chunk_size=3,
            max_size=4,
            campaign_id="my-fixed-id",
        )
        assert spec.campaign_id == "my-fixed-id"

    def test_skipped_trivial_propagated(self, tmp_path: Path) -> None:
        _write_two_cluster_project(tmp_path)
        spec = build_campaign_spec(
            tmp_path,
            tmp_path / "mypkg",
            commit_sha="abc1234",
            min_size=2,
            chunk_size=3,
            max_size=4,
        )
        # __init__.py is empty → trivial.
        assert any("__init__.py" in p for p in spec.skipped_trivial)

    def test_team_project_carried_through(self, tmp_path: Path) -> None:
        _write_two_cluster_project(tmp_path)
        spec = build_campaign_spec(
            tmp_path,
            tmp_path / "mypkg",
            commit_sha="abc1234",
            min_size=2,
            chunk_size=3,
            max_size=4,
            team="TappsCodingAgents",
            project="TappsMCP Platform",
        )
        assert spec.team == "TappsCodingAgents"
        assert spec.project == "TappsMCP Platform"

    def test_session_indices_sequential(self, tmp_path: Path) -> None:
        _write_two_cluster_project(tmp_path)
        spec = build_campaign_spec(
            tmp_path,
            tmp_path / "mypkg",
            commit_sha="abc1234",
            min_size=2,
            chunk_size=3,
            max_size=4,
        )
        indices = [s.session_index for s in spec.sessions]
        assert indices == list(range(1, len(indices) + 1))


class TestMCPHandler:
    """Smoke-test the ``tapps_audit_campaign`` MCP handler end-to-end."""

    @pytest.mark.asyncio
    async def test_plan_returns_success_envelope(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_two_cluster_project(tmp_path)

        from tapps_mcp.server_analysis_tools import tapps_audit_campaign

        resp = await tapps_audit_campaign(
            scope=str(tmp_path / "mypkg"),
            categories="quality",
            chunk_size=3,
            project_root=str(tmp_path),
        )

        assert resp["success"] is True
        data = resp["data"]
        assert data["total_files"] == 4
        assert data["total_chunks"] >= 1
        assert data["categories"] == ["quality"]
        assert data["epic"]["title"].startswith("audit campaign:")
        assert data["sessions"]
        for session in data["sessions"]:
            assert session["title"].startswith("audit: ")
            assert session["body"].startswith("## What")

    @pytest.mark.asyncio
    async def test_unknown_category_returns_error_envelope(
        self, tmp_path: Path
    ) -> None:
        _write_two_cluster_project(tmp_path)
        from tapps_mcp.server_analysis_tools import tapps_audit_campaign

        resp = await tapps_audit_campaign(
            scope=str(tmp_path / "mypkg"),
            categories="quality,bogus",
            project_root=str(tmp_path),
        )
        assert resp["success"] is False
        assert resp["error"]["code"] == "invalid_categories"

    @pytest.mark.asyncio
    async def test_invalid_scope_returns_error_envelope(
        self, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_analysis_tools import tapps_audit_campaign

        resp = await tapps_audit_campaign(
            scope=str(tmp_path / "does-not-exist"),
            project_root=str(tmp_path),
        )
        assert resp["success"] is False
        assert resp["error"]["code"] == "invalid_scope"
