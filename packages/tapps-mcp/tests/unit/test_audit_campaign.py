"""Tests for the audit-campaign orchestrator."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from tapps_mcp.tools.audit_campaign import (
    _EPIC_REF_PLACEHOLDER,
    _build_campaign_id,
    _slug,
    build_campaign_spec,
    finalize_session_bodies,
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
            assert session.body.startswith("<!-- audit-readonly -->")
            assert "## What" in session.body[:500]
            assert _EPIC_REF_PLACEHOLDER in session.body
            assert "abc1234" in session.body
            assert session.labels == ["audit-readonly"]

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
            assert session["body"].startswith("<!-- audit-readonly -->")
            assert "## What" in session["body"][:500]
            assert session["labels"] == ["audit-readonly"]
        # persisted_to_brain key is present (value may be True or False
        # depending on bridge availability in the test env).
        assert "persisted_to_brain" in data

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

    @pytest.mark.asyncio
    async def test_invalid_mode_returns_error_envelope(
        self, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_analysis_tools import tapps_audit_campaign

        resp = await tapps_audit_campaign(
            scope=str(tmp_path),
            project_root=str(tmp_path),
            mode="bogus",
        )
        assert resp["success"] is False
        assert resp["error"]["code"] == "invalid_mode"


class TestFinalizeSessionBodies:
    def test_substitutes_placeholder_in_all_sessions(self) -> None:
        spec = {
            "campaign_id": "c1",
            "sessions": [
                {
                    "session_index": 1,
                    "body": "Parent epic: <campaign-epic>\nfoo",
                },
                {
                    "session_index": 2,
                    "body": "see <campaign-epic> for context",
                },
            ],
        }
        out = finalize_session_bodies(spec, "TAP-1234")
        assert out["epic_ref"] == "TAP-1234"
        assert out["sessions"][0]["body"] == "Parent epic: TAP-1234\nfoo"
        assert out["sessions"][1]["body"] == "see TAP-1234 for context"

    def test_preserves_session_metadata(self) -> None:
        spec = {
            "campaign_id": "c1",
            "sessions": [
                {
                    "session_index": 1,
                    "title": "audit: ...",
                    "body": "x <campaign-epic> y",
                    "files": ["a.py"],
                    "intra_edges": 3,
                }
            ],
        }
        out = finalize_session_bodies(spec, "TAP-1234")
        assert out["sessions"][0]["title"] == "audit: ..."
        assert out["sessions"][0]["files"] == ["a.py"]
        assert out["sessions"][0]["intra_edges"] == 3

    def test_idempotent_when_no_placeholders_remain(self) -> None:
        spec = {
            "sessions": [{"body": "already TAP-1234 substituted"}],
        }
        out = finalize_session_bodies(spec, "TAP-1234")
        assert out["sessions"][0]["body"] == "already TAP-1234 substituted"

    def test_empty_epic_ref_raises(self) -> None:
        spec = {"sessions": [{"body": "<campaign-epic>"}]}
        with pytest.raises(ValueError, match="epic_ref is required"):
            finalize_session_bodies(spec, "")

    def test_empty_sessions_list(self) -> None:
        spec = {"campaign_id": "c1", "sessions": []}
        out = finalize_session_bodies(spec, "TAP-1234")
        assert out["sessions"] == []
        assert out["epic_ref"] == "TAP-1234"


class TestDispatchMode:
    """End-to-end: plan persists, dispatch loads + finalizes + re-persists."""

    @pytest.mark.asyncio
    async def test_missing_campaign_id_returns_error(
        self, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_analysis_tools import tapps_audit_campaign

        resp = await tapps_audit_campaign(
            mode="dispatch",
            epic_ref="TAP-1234",
            project_root=str(tmp_path),
        )
        assert resp["success"] is False
        assert resp["error"]["code"] == "missing_campaign_id"

    @pytest.mark.asyncio
    async def test_missing_epic_ref_returns_error(
        self, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_analysis_tools import tapps_audit_campaign

        resp = await tapps_audit_campaign(
            mode="dispatch",
            campaign_id="some-id",
            project_root=str(tmp_path),
        )
        assert resp["success"] is False
        assert resp["error"]["code"] == "missing_epic_ref"

    @pytest.mark.asyncio
    async def test_campaign_not_in_brain_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Bridge returns None for any key.
        monkeypatch.setattr(
            "tapps_mcp.tools.audit_manifest._get_bridge_or_none",
            lambda: None,
        )

        from tapps_mcp.server_analysis_tools import tapps_audit_campaign

        resp = await tapps_audit_campaign(
            mode="dispatch",
            campaign_id="not-found",
            epic_ref="TAP-1234",
            project_root=str(tmp_path),
        )
        assert resp["success"] is False
        assert resp["error"]["code"] == "campaign_not_found"

    @pytest.mark.asyncio
    async def test_round_trip_plan_then_dispatch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # In-memory bridge so plan persists and dispatch can load.
        class _Bridge:
            def __init__(self) -> None:
                self.store: dict[str, dict[str, Any]] = {}

            async def save(self, **kwargs: Any) -> dict[str, Any]:
                entry = {"key": kwargs["key"], "value": kwargs["value"], "status": "saved"}
                self.store[kwargs["key"]] = entry
                return entry

            async def get(self, key: str) -> dict[str, Any] | None:
                return self.store.get(key)

        bridge = _Bridge()
        monkeypatch.setattr(
            "tapps_mcp.tools.audit_manifest._get_bridge_or_none",
            lambda: bridge,
        )

        _write_two_cluster_project(tmp_path)
        from tapps_mcp.server_analysis_tools import tapps_audit_campaign

        plan_resp = await tapps_audit_campaign(
            scope=str(tmp_path / "mypkg"),
            categories="quality",
            chunk_size=3,
            project_root=str(tmp_path),
        )
        assert plan_resp["success"] is True
        campaign_id = plan_resp["data"]["campaign_id"]
        # Plan-mode bodies still carry the placeholder.
        for session in plan_resp["data"]["sessions"]:
            assert "<campaign-epic>" in session["body"]

        dispatch_resp = await tapps_audit_campaign(
            mode="dispatch",
            campaign_id=campaign_id,
            epic_ref="TAP-9999",
            project_root=str(tmp_path),
        )
        assert dispatch_resp["success"] is True
        assert dispatch_resp["data"]["epic_ref"] == "TAP-9999"
        for session in dispatch_resp["data"]["sessions"]:
            assert "<campaign-epic>" not in session["body"]
            assert "TAP-9999" in session["body"]
        assert dispatch_resp["data"]["persisted_to_brain"] is True


class TestFixPlanMode:
    """Round-trip and error tests for mode='fix_plan'."""

    @pytest.mark.asyncio
    async def test_fix_plan_missing_campaign_id_returns_error(
        self, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_analysis_tools import tapps_audit_campaign

        resp = await tapps_audit_campaign(
            mode="fix_plan",
            project_root=str(tmp_path),
        )
        assert resp["success"] is False
        assert resp["error"]["code"] == "missing_campaign_id"

    @pytest.mark.asyncio
    async def test_fix_plan_campaign_not_in_brain_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "tapps_mcp.tools.audit_manifest._get_bridge_or_none",
            lambda: None,
        )
        from tapps_mcp.server_analysis_tools import tapps_audit_campaign

        resp = await tapps_audit_campaign(
            mode="fix_plan",
            campaign_id="not-found",
            project_root=str(tmp_path),
        )
        assert resp["success"] is False
        assert resp["error"]["code"] == "campaign_not_found"

    @pytest.mark.asyncio
    async def test_plan_then_fix_plan_round_trip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """plan mode persists; fix_plan loads and emits a fix epic + stories."""

        class _Bridge:
            def __init__(self) -> None:
                self.store: dict[str, dict[str, Any]] = {}

            async def save(self, **kwargs: Any) -> dict[str, Any]:
                entry = {"key": kwargs["key"], "value": kwargs["value"], "status": "saved"}
                self.store[kwargs["key"]] = entry
                return entry

            async def get(self, key: str) -> dict[str, Any] | None:
                return self.store.get(key)

        bridge = _Bridge()
        monkeypatch.setattr(
            "tapps_mcp.tools.audit_manifest._get_bridge_or_none",
            lambda: bridge,
        )

        _write_two_cluster_project(tmp_path)
        from tapps_mcp.server_analysis_tools import tapps_audit_campaign

        # Step 1: plan
        plan_resp = await tapps_audit_campaign(
            scope=str(tmp_path / "mypkg"),
            categories="quality",
            chunk_size=3,
            project_root=str(tmp_path),
        )
        assert plan_resp["success"] is True
        campaign_id = plan_resp["data"]["campaign_id"]
        assert plan_resp["data"]["persisted_to_brain"] is True

        # Step 2: fix_plan
        fix_resp = await tapps_audit_campaign(
            mode="fix_plan",
            campaign_id=campaign_id,
            project_root=str(tmp_path),
        )
        assert fix_resp["success"] is True, fix_resp.get("error")
        fix_data = fix_resp["data"]

        # Fix epic is present with proper structure.
        assert "fix_epic" in fix_data
        assert fix_data["fix_epic"]["title"].startswith("fix campaign:")
        assert len(fix_data["fix_epic"]["title"]) <= 80
        assert "## Purpose & Intent" in fix_data["fix_epic"]["body"]
        assert "## Acceptance Criteria" in fix_data["fix_epic"]["body"]

        # Fix stories map 1-to-1 with audit sessions.
        plan_session_count = plan_resp["data"]["total_chunks"]
        assert fix_data["total_fix_stories"] == plan_session_count
        assert len(fix_data["fix_stories"]) == plan_session_count

        # Each fix story meets the agent_ready contract.
        for story in fix_data["fix_stories"]:
            assert story["agent_ready"] is True
            assert story["title"]
            assert "## What" in story["body"]
            assert "## Where" in story["body"]
            assert "## Acceptance" in story["body"]
            assert story["labels"] == ["audit-fix"]
            assert story["files"]  # non-empty file list
            # TAP-2720: estimate and priority must be surfaced per story.
            assert isinstance(story["estimate"], int)
            assert story["estimate"] >= 1
            assert isinstance(story["priority"], int)
            assert story["priority"] in {1, 2, 3, 4}  # valid Linear priority range

        # Fix plan is stored under a distinct brain key (fix.campaign.)
        # while audit plan lives under audit.campaign.
        from tapps_mcp.tools.audit_manifest import campaign_key, fix_campaign_key

        audit_key = campaign_key(campaign_id)
        fix_key = fix_campaign_key(campaign_id)
        assert audit_key in bridge.store
        assert fix_key in bridge.store
        assert audit_key != fix_key

        # persisted flag is set on the fix_plan response too.
        assert fix_data["persisted_to_brain"] is True
